"""Value and temporal validation for OneFlorida+ PCORnet CDM.

Validates coded fields against CDM value sets, checks vital/lab plausibility,
verifies ICD version-date concordance, validates temporal consistency, applies
HL-specific tumor registry checks, and adds binary flag columns to Parquet files.

Usage:
    python scripts/validate_values.py [config/paths.toml]

Designed for HPC interactive sessions (srun --pty bash).
"""

import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.load.config import load_config
from src.load.schema import parse_datastructure
from src.validate.structural import (
    PATID_COL,
    TUMOR_REGISTRY_TABLES,
    flag_small_cell,
)
from src.validate.values import (
    ICD10_TRANSITION,
    MASKED_BIRTH_DATE,
    build_valueset_lookup,
    detect_mapped_partners,
    drop_existing_flags,
    validate_coded_fields,
    validate_enrollment_dates,
    validate_future_dates,
    validate_icd_concordance,
    validate_lab_plausibility,
    validate_temporal_encounter,
    validate_tumor_registry,
    validate_vital_plausibility,
    write_validated,
)
from src.validate.cohort import (
    ALL_HL_CODES,
    ALL_HL_NORMALIZED,
    detect_dx_format,
)

import polars as pl


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HL_TREATMENT_CPTS: set[str] = {
    "38240", "38241", "38242",              # stem cell transplant
    "38230", "38232",                        # bone marrow harvest
    "77385", "77386",                        # IMRT delivery
    "77401", "77402", "77407", "77412",      # external-beam radiation
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_table_map(
    table_filenames: list[str], parquet_dir: Path,
) -> dict[str, Path]:
    """Build mapping from table_name -> parquet_path."""
    table_map: dict[str, Path] = {}
    for filename in table_filenames:
        stem = Path(filename).stem
        table_name = stem.split("_Mailhot_V1")[0]
        parquet_path = parquet_dir / (stem + ".parquet")
        table_map[table_name] = parquet_path
    return table_map


def _load_birth_death_lookup(
    table_map: dict[str, Path],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Load DEMOGRAPHIC birth dates and DEATH dates for cross-table checks.

    For patients with masked BIRTH_DATE (1900-01-01), attempts recovery
    via AGE_AT_DIAGNOSIS + DATE_OF_DIAGNOSIS from TUMOR_REGISTRY tables.
    """
    empty_birth = pl.DataFrame(schema={PATID_COL: pl.String, "BIRTH_DATE": pl.Date})
    empty_death = pl.DataFrame(schema={PATID_COL: pl.String, "DEATH_DATE": pl.Date})

    demo_path = table_map.get("DEMOGRAPHIC")
    if demo_path is None or not demo_path.exists():
        return empty_birth, empty_death

    demo_schema = pl.read_parquet_schema(demo_path)
    if "BIRTH_DATE" not in demo_schema:
        return empty_birth, empty_death

    birth_df = (
        pl.read_parquet(demo_path)
        .select(pl.col(PATID_COL).cast(pl.String), "BIRTH_DATE")
    )

    # Death dates
    death_path = table_map.get("DEATH")
    if death_path is not None and death_path.exists():
        d_schema = pl.read_parquet_schema(death_path)
        if "DEATH_DATE" in d_schema:
            death_df = (
                pl.read_parquet(death_path)
                .select(pl.col(PATID_COL).cast(pl.String), "DEATH_DATE")
            )
        else:
            death_df = empty_death
    else:
        death_df = empty_death

    # Recover masked birth dates from TUMOR_REGISTRY
    masked_ids = birth_df.filter(pl.col("BIRTH_DATE") == MASKED_BIRTH_DATE)
    if masked_ids.height > 0:
        tr_frames: list[pl.DataFrame] = []
        for tr_name in TUMOR_REGISTRY_TABLES:
            tr_path = table_map.get(tr_name)
            if tr_path is None or not tr_path.exists():
                continue
            tr_schema = pl.read_parquet_schema(tr_path)
            if "AGE_AT_DIAGNOSIS" not in tr_schema or "DATE_OF_DIAGNOSIS" not in tr_schema:
                continue
            tr_df = (
                pl.read_parquet(tr_path)
                .select(
                    pl.col(PATID_COL).cast(pl.String),
                    "AGE_AT_DIAGNOSIS",
                    "DATE_OF_DIAGNOSIS",
                )
                .filter(
                    pl.col("AGE_AT_DIAGNOSIS").is_not_null()
                    & pl.col("DATE_OF_DIAGNOSIS").is_not_null()
                )
            )
            tr_frames.append(tr_df)

        if tr_frames:
            tr_all = pl.concat(tr_frames)
            if tr_all.schema["AGE_AT_DIAGNOSIS"] in (pl.String, pl.Utf8):
                tr_all = tr_all.with_columns(
                    pl.col("AGE_AT_DIAGNOSIS").cast(pl.Float64, strict=False)
                )

            recovery = (
                tr_all
                .with_columns(
                    (
                        pl.col("DATE_OF_DIAGNOSIS").dt.year()
                        - pl.col("AGE_AT_DIAGNOSIS").cast(pl.Int32, strict=False)
                    ).alias("_approx_year")
                )
                .filter(
                    pl.col("_approx_year").is_not_null()
                    & (pl.col("_approx_year") >= 1900)
                    & (pl.col("_approx_year") <= 2025)
                )
                .group_by(PATID_COL)
                .agg(pl.col("_approx_year").median().cast(pl.Int32).alias("_year"))
            )

            if recovery.height > 0:
                recovery = recovery.with_columns(
                    (pl.col("_year").cast(pl.String) + pl.lit("-01-01"))
                    .str.strptime(pl.Date, "%Y-%m-%d")
                    .alias("_RECOVERED")
                )
                birth_df = (
                    birth_df
                    .join(
                        recovery.select(PATID_COL, "_RECOVERED"),
                        on=PATID_COL,
                        how="left",
                    )
                    .with_columns(
                        pl.when(
                            (pl.col("BIRTH_DATE") == MASKED_BIRTH_DATE)
                            & pl.col("_RECOVERED").is_not_null()
                        )
                        .then(pl.col("_RECOVERED"))
                        .otherwise(pl.col("BIRTH_DATE"))
                        .alias("BIRTH_DATE")
                    )
                    .drop("_RECOVERED")
                )

    return birth_df, death_df


def _get_date_columns(df: pl.DataFrame) -> list[str]:
    """Return date/datetime column names, excluding existing flag columns."""
    result: list[str] = []
    for col in df.columns:
        if "_val_" in col:
            continue
        dtype = df.schema[col]
        if dtype == pl.Date or dtype == pl.Datetime or isinstance(dtype, pl.Datetime):
            result.append(col)
    return result


def _validate_against_birth(
    df: pl.DataFrame,
    birth_df: pl.DataFrame,
    date_cols: list[str],
) -> pl.DataFrame:
    """Add ``{col}_val_before_birth`` flags for dates preceding BIRTH_DATE."""
    if birth_df.is_empty() or not date_cols or PATID_COL not in df.columns:
        return df

    lookup = birth_df.rename({"BIRTH_DATE": "_LOOKUP_BD"})
    df = df.join(lookup, on=PATID_COL, how="left")

    for col in date_cols:
        flag_col = f"{col}_val_before_birth"
        df = df.with_columns(
            pl.when(
                pl.col("_LOOKUP_BD").is_not_null()
                & (pl.col("_LOOKUP_BD") != MASKED_BIRTH_DATE)
                & pl.col(col).is_not_null()
                & (pl.col(col).cast(pl.Date, strict=False) < pl.col("_LOOKUP_BD"))
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias(flag_col)
        )

    df = df.drop("_LOOKUP_BD")
    return df


def _validate_against_death(
    df: pl.DataFrame,
    death_df: pl.DataFrame,
    date_cols: list[str],
) -> pl.DataFrame:
    """Add ``{col}_val_after_death`` flags for dates following DEATH_DATE."""
    if death_df.is_empty() or not date_cols or PATID_COL not in df.columns:
        return df

    lookup = death_df.rename({"DEATH_DATE": "_LOOKUP_DD"})
    df = df.join(lookup, on=PATID_COL, how="left")

    for col in date_cols:
        flag_col = f"{col}_val_after_death"
        df = df.with_columns(
            pl.when(
                pl.col("_LOOKUP_DD").is_not_null()
                & pl.col(col).is_not_null()
                & (pl.col(col).cast(pl.Date, strict=False) > pl.col("_LOOKUP_DD"))
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias(flag_col)
        )

    df = df.drop("_LOOKUP_DD")
    return df


def _collect_concordance_data(
    df: pl.DataFrame, mapped_partners: set[str],
) -> dict:
    """Collect per-partner ICD concordance statistics from DIAGNOSIS."""
    if "DX_val_icd_concordance" not in df.columns or "DX" not in df.columns:
        return {}

    is_icd10 = pl.col("DX").str.to_uppercase().str.contains(r"^[A-Z]")
    total_dx = df.height
    total_flagged = int(df["DX_val_icd_concordance"].sum() or 0)

    partner_col = "SOURCE" if "SOURCE" in df.columns else None
    per_partner: dict[str, dict] = {}

    if partner_col:
        for partner in df[partner_col].unique().sort().to_list():
            p_name = str(partner) if partner is not None else "NULL"
            p_df = (
                df.filter(pl.col(partner_col) == partner)
                if partner is not None
                else df.filter(pl.col(partner_col).is_null())
            )
            p_total = p_df.height
            p_icd10 = p_df.filter(is_icd10).height
            p_icd9 = p_total - p_icd10
            p_flagged = int(p_df["DX_val_icd_concordance"].sum() or 0)

            pre_icd10 = 0
            if "DX_DATE" in p_df.columns:
                pre_icd10 = p_df.filter(
                    is_icd10
                    & pl.col("DX_DATE").is_not_null()
                    & (pl.col("DX_DATE") < ICD10_TRANSITION)
                ).height

            per_partner[p_name] = {
                "total": p_total,
                "icd9": p_icd9,
                "icd10": p_icd10,
                "pre_transition_icd10": pre_icd10,
                "flagged": p_flagged,
                "is_mapped": p_name in mapped_partners,
            }

    return {
        "total_dx": total_dx,
        "total_flagged": total_flagged,
        "mapped_partners": mapped_partners,
        "per_partner": per_partner,
    }


def _write_icd_concordance_csv(
    concordance_data: dict, reports_dir: Path,
) -> None:
    """Write per-partner ICD concordance breakdown to CSV."""
    per_partner = concordance_data.get("per_partner", {})
    if not per_partner:
        return

    rows = []
    for partner, stats in sorted(per_partner.items()):
        rows.append({
            "partner": partner,
            "total_dx": stats["total"],
            "icd9_count": stats["icd9"],
            "icd10_count": stats["icd10"],
            "pre_transition_icd10": stats["pre_transition_icd10"],
            "flagged_count": stats["flagged"],
            "is_mapped": str(stats["is_mapped"]),
        })

    pl.DataFrame(rows).write_csv(reports_dir / "icd_concordance.csv")


def _compute_hl_timeline(table_map: dict[str, Path]) -> dict:
    """Compute HL disease timeline summary: DX-to-treatment timing.

    Cross-table analysis — not per-row flags. Uses PROCEDURES CPT codes
    and TUMOR_REGISTRY treatment dates to find first treatment per patient.
    """
    result: dict = {
        "total_patients": 0,
        "with_treatment": 0,
        "median_dx_to_tx": None,
        "flagged_before_dx": 0,
        "flagged_over_365": 0,
        "distribution_buckets": {},
    }

    diag_path = table_map.get("DIAGNOSIS")
    if diag_path is None or not diag_path.exists():
        return result

    dx_format = detect_dx_format(diag_path)
    code_set = ALL_HL_CODES if dx_format == "dotted" else ALL_HL_NORMALIZED

    dx_match_expr = (
        pl.col("DX")
        if dx_format == "dotted"
        else pl.col("DX").str.to_uppercase().str.replace_all(r"\.", "")
    )

    hl_dx = (
        pl.scan_parquet(diag_path)
        .with_columns(
            pl.col(PATID_COL).cast(pl.String),
            dx_match_expr.alias("_DX"),
        )
        .filter(pl.col("_DX").is_in(code_set) & pl.col("DX_DATE").is_not_null())
        .select(PATID_COL, "DX_DATE")
        .collect()
    )

    if hl_dx.is_empty():
        return result

    first_dx = (
        hl_dx
        .group_by(PATID_COL)
        .agg(pl.col("DX_DATE").min().alias("FIRST_DX"))
    )
    result["total_patients"] = first_dx.height

    # Gather treatment dates from PROCEDURES and TUMOR_REGISTRY
    tx_frames: list[pl.DataFrame] = []

    px_path = table_map.get("PROCEDURES")
    if px_path is not None and px_path.exists():
        px_schema = pl.read_parquet_schema(px_path)
        if "PX" in px_schema and "PX_DATE" in px_schema:
            px_df = (
                pl.scan_parquet(px_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(
                    pl.col("PX").is_in(HL_TREATMENT_CPTS)
                    & pl.col("PX_DATE").is_not_null()
                )
                .select(PATID_COL, pl.col("PX_DATE").cast(pl.Date).alias("TX_DATE"))
                .collect()
            )
            if not px_df.is_empty():
                tx_frames.append(px_df)

    for tr_name in TUMOR_REGISTRY_TABLES:
        tr_path = table_map.get(tr_name)
        if tr_path is None or not tr_path.exists():
            continue
        tr_schema = pl.read_parquet_schema(tr_path)
        for tc in ("DT_SURG", "DT_RAD", "DT_CHEMO"):
            if tc not in tr_schema:
                continue
            chunk = (
                pl.read_parquet(tr_path)
                .select(pl.col(PATID_COL).cast(pl.String), tc)
                .filter(pl.col(tc).is_not_null())
                .with_columns(pl.col(tc).cast(pl.Date, strict=False).alias("TX_DATE"))
                .select(PATID_COL, "TX_DATE")
            )
            if not chunk.is_empty():
                tx_frames.append(chunk)

    if not tx_frames:
        return result

    all_tx = pl.concat(tx_frames)
    first_tx = (
        all_tx
        .group_by(PATID_COL)
        .agg(pl.col("TX_DATE").min().alias("FIRST_TX"))
    )

    timeline = first_dx.join(first_tx, on=PATID_COL, how="inner")
    result["with_treatment"] = timeline.height

    if timeline.is_empty():
        return result

    timeline = timeline.with_columns(
        (pl.col("FIRST_TX") - pl.col("FIRST_DX")).dt.total_days().alias("DAYS")
    )

    median_val = timeline["DAYS"].median()
    result["median_dx_to_tx"] = int(median_val) if median_val is not None else None
    result["flagged_before_dx"] = timeline.filter(pl.col("DAYS") < 0).height
    result["flagged_over_365"] = timeline.filter(pl.col("DAYS") > 365).height
    result["distribution_buckets"] = {
        "<0 (before DX)": timeline.filter(pl.col("DAYS") < 0).height,
        "0-30 days": timeline.filter(
            (pl.col("DAYS") >= 0) & (pl.col("DAYS") <= 30)
        ).height,
        "31-90 days": timeline.filter(
            (pl.col("DAYS") >= 31) & (pl.col("DAYS") <= 90)
        ).height,
        "91-180 days": timeline.filter(
            (pl.col("DAYS") >= 91) & (pl.col("DAYS") <= 180)
        ).height,
        "181-365 days": timeline.filter(
            (pl.col("DAYS") >= 181) & (pl.col("DAYS") <= 365)
        ).height,
        ">365 days": timeline.filter(pl.col("DAYS") > 365).height,
    }

    return result


# ---------------------------------------------------------------------------
# Report generation (populated in Task 2)
# ---------------------------------------------------------------------------


def _section_overview(report_data: dict) -> str:
    """Stub — populated in Task 2."""
    return ""


def _section_valueset(report_data: dict) -> str:
    """Stub — populated in Task 2."""
    return ""


def _section_plausibility(report_data: dict) -> str:
    """Stub — populated in Task 2."""
    return ""


def _section_icd_concordance(concordance_data: dict) -> str:
    """Stub — populated in Task 2."""
    return ""


def _section_temporal(report_data: dict, hl_timeline: dict) -> str:
    """Stub — populated in Task 2."""
    return ""


def _section_tumor_registry(report_data: dict) -> str:
    """Stub — populated in Task 2."""
    return ""


def _write_temporal_issues_csv(
    report_data: dict, hl_timeline: dict, reports_dir: Path,
) -> None:
    """Stub — populated in Task 2."""
    pass


def _write_tumor_registry_csv(report_data: dict, reports_dir: Path) -> None:
    """Stub — populated in Task 2."""
    pass


def _generate_reports(
    report_data: dict,
    concordance_data: dict,
    hl_timeline: dict,
    paths,
    reports_dir: Path,
    validated_count: int,
) -> None:
    """Assemble and write all report files."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    parts: list[str] = []
    parts.append("# Value & Temporal Validation Report\n")
    parts.append(f"**Generated:** {timestamp}")
    parts.append(f"**Data source:** {paths.data_root}")
    parts.append(f"**Parquet directory:** {paths.parquet_dir}")
    parts.append(f"**Tables validated:** {validated_count}\n")

    parts.append("## Table of Contents\n")
    parts.append("1. [Validation Overview](#1-validation-overview)")
    parts.append("2. [Value Set Conformance](#2-value-set-conformance)")
    parts.append("3. [Plausibility Checks](#3-plausibility-checks)")
    parts.append("4. [ICD Version-Date Concordance](#4-icd-version-date-concordance)")
    parts.append("5. [Temporal Consistency](#5-temporal-consistency)")
    parts.append("6. [Tumor Registry Validation](#6-tumor-registry-validation)\n")
    parts.append("---\n")

    parts.append(_section_overview(report_data))
    parts.append(_section_valueset(report_data))
    parts.append(_section_plausibility(report_data))
    parts.append(_section_icd_concordance(concordance_data))
    parts.append(_section_temporal(report_data, hl_timeline))
    parts.append(_section_tumor_registry(report_data))

    report_path = reports_dir / "value_validation.md"
    report_path.write_text("\n".join(parts), encoding="utf-8")

    _write_temporal_issues_csv(report_data, hl_timeline, reports_dir)
    _write_tumor_registry_csv(report_data, reports_dir)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(config_path: Path | None = None) -> None:
    print("=" * 60)
    print("HL DATA LOADING & CLEANING — VALUE & TEMPORAL VALIDATION")
    print("=" * 60)

    paths = load_config(config_path)
    print(f"\n  data_root:    {paths.data_root}")
    print(f"  parquet_dir:  {paths.parquet_dir}")

    _, table_filenames = parse_datastructure(paths.datastructure_path)
    table_map = _build_table_map(table_filenames, paths.parquet_dir)
    print(f"\n  Tables found: {len(table_map)}")

    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    overall_start = time.time()

    # Build value set lookup
    lookup = build_valueset_lookup(paths.valuesets_path)
    print(f"  Value sets loaded: {len(lookup)} table-field pairs")

    # Load birth/death lookup for cross-table temporal checks
    birth_df, death_df = _load_birth_death_lookup(table_map)
    print(f"  Birth dates: {birth_df.height:,} patients")
    print(f"  Death dates: {death_df.height:,} records")

    # Detect partners that retrospectively mapped ICD-9 → ICD-10
    diag_path = table_map.get("DIAGNOSIS")
    mapped_partners: set[str] = set()
    if diag_path and diag_path.exists():
        diag_tmp = pl.read_parquet(diag_path)
        mapped_partners = detect_mapped_partners(diag_tmp)
        print(f"  Mapped partners: {', '.join(sorted(mapped_partners)) or 'none'}")
        del diag_tmp

    report_data: dict[str, dict] = {}
    concordance_data: dict = {}
    total_tables = len(table_map)
    validated_count = 0

    # ----- Main validation loop -----
    print(f"\n{'─' * 60}")
    print("  VALUE & TEMPORAL VALIDATION")
    print(f"{'─' * 60}")

    for idx, (table_name, pq_path) in enumerate(sorted(table_map.items()), 1):
        if not pq_path.exists():
            print(f"  [{idx}/{total_tables}] {table_name} — SKIP (not found)")
            continue

        print(f"  [{idx}/{total_tables}] {table_name}", end="")
        df = pl.read_parquet(pq_path)
        df = drop_existing_flags(df)

        if PATID_COL in df.columns:
            df = df.with_columns(pl.col(PATID_COL).cast(pl.String))

        is_tr = table_name in TUMOR_REGISTRY_TABLES

        # Value set validation (skip TUMOR_REGISTRY — NAACCR, not CDM)
        if not is_tr:
            df = validate_coded_fields(df, table_name, lookup)

        # Table-specific checks
        if table_name == "VITAL":
            df = validate_vital_plausibility(df)
        elif table_name == "LAB_RESULT_CM":
            df = validate_lab_plausibility(df)
        elif table_name == "DIAGNOSIS":
            df = validate_icd_concordance(df, mapped_partners)
            concordance_data = _collect_concordance_data(df, mapped_partners)
        elif table_name == "ENCOUNTER":
            df = validate_temporal_encounter(df)
        elif table_name == "ENROLLMENT":
            df = validate_enrollment_dates(df)
        elif is_tr:
            df = validate_tumor_registry(df)

        # Universal: future date check
        df = validate_future_dates(df)

        # Cross-table: birth/death temporal checks
        skip_birth_death = {"DEMOGRAPHIC", "DEATH"} | TUMOR_REGISTRY_TABLES
        if table_name not in skip_birth_death:
            date_cols = _get_date_columns(df)
            if date_cols:
                df = _validate_against_birth(df, birth_df, date_cols)
                df = _validate_against_death(df, death_df, date_cols)

        # Write back to Parquet with flag columns
        stats = write_validated(df, pq_path)
        report_data[table_name] = stats
        validated_count += 1

        flag_count = stats["flag_columns_added"]
        flagged_vals = sum(stats["flags"].values())
        print(f" — {flag_count} flags, {flagged_vals:,} flagged values")

    # ----- HL disease timeline -----
    print(f"\n{'─' * 60}")
    print("  HL DISEASE TIMELINE")
    print(f"{'─' * 60}")

    hl_timeline = _compute_hl_timeline(table_map)
    print(f"  HL patients: {hl_timeline['total_patients']:,}")
    print(f"  With treatment: {hl_timeline['with_treatment']:,}")
    if hl_timeline["median_dx_to_tx"] is not None:
        print(f"  Median DX\u2192TX: {hl_timeline['median_dx_to_tx']} days")
    print(f"  TX before DX: {hl_timeline['flagged_before_dx']}")
    print(f"  TX >365 days: {hl_timeline['flagged_over_365']}")

    # ----- ICD concordance CSV -----
    if concordance_data:
        _write_icd_concordance_csv(concordance_data, reports_dir)
        print(f"\n  ICD concordance CSV: {reports_dir / 'icd_concordance.csv'}")

    # ----- Reports -----
    print(f"\n{'─' * 60}")
    print("  GENERATING REPORTS")
    print(f"{'─' * 60}")

    _generate_reports(
        report_data, concordance_data, hl_timeline,
        paths, reports_dir, validated_count,
    )

    # ----- Console summary -----
    overall_elapsed = time.time() - overall_start
    total_flags = sum(s["flag_columns_added"] for s in report_data.values())
    total_flagged = sum(sum(s["flags"].values()) for s in report_data.values())
    icd_flagged = concordance_data.get("total_flagged", 0)
    icd_total = concordance_data.get("total_dx", 0)

    print(f"\n{'=' * 60}")
    print("  VALUE & TEMPORAL VALIDATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Tables validated:     {validated_count}")
    print(f"  Total flag columns:   {total_flags}")
    print(f"  Total flagged values: {total_flagged:,}")
    if icd_total:
        print(f"  ICD concordance:      {icd_flagged:,}/{icd_total:,} flagged")
    if hl_timeline["median_dx_to_tx"] is not None:
        print(f"  HL timeline median:   {hl_timeline['median_dx_to_tx']} days DX\u2192TX")
    print(f"  Elapsed:              {overall_elapsed:.1f}s")
    print(f"  Reports:")
    print(f"    - {reports_dir / 'value_validation.md'}")
    print(f"    - {reports_dir / 'icd_concordance.csv'}")
    print(f"    - {reports_dir / 'temporal_issues.csv'}")
    print(f"    - {reports_dir / 'tumor_registry_validation.csv'}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    try:
        cfg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
        main(cfg)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"\n{'=' * 60}")
        print("  VALUE & TEMPORAL VALIDATION FAILED")
        print(f"{'=' * 60}")
        print(f"  Error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
