"""Value and temporal validation for OneFlorida+ PCORnet CDM.

Small-cell: all report counts use flag_small_cell/_suppress per REQ-05.

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

import polars as pl

from src.load.config import load_config
from src.load.schema import parse_datastructure, resolve_table_name
from src.validate.cohort import (
    ALL_HL_CODES,
    ALL_HL_NORMALIZED,
    detect_dx_format,
)
from src.validate.structural import (
    PATID_COL,
    SMALL_CELL_THRESHOLD,
    TUMOR_REGISTRY_TABLES,
    flag_small_cell,
)
from src.validate.values import (
    HL_LAB_RANGES,
    ICD10_TRANSITION,
    MASKED_BIRTH_DATE,
    VITAL_RANGES,
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_table_map(table_filenames: list[str], parquet_dir: Path) -> dict[str, Path]:
    """Build mapping from CDM table name to parquet file path.

    Resolves table names using schema.py naming rules (e.g., "DEMOGRAPHIC_Mailhot_V1" → "DEMOGRAPHIC").
    Used to locate parquet files for value validation and temporal checks.

    Args:
        table_filenames: List of CSV filenames from datastructure.txt
        parquet_dir: Directory containing parquet files

    Returns:
        Dict mapping table name to parquet path (e.g., {"DEMOGRAPHIC": Path("parquet/DEMOGRAPHIC_Mailhot_V1.parquet")})
    """
    table_map: dict[str, Path] = {}
    for filename in table_filenames:
        stem = Path(filename).stem
        table_name = resolve_table_name(stem)
        parquet_path = parquet_dir / (stem + ".parquet")
        table_map[table_name] = parquet_path
    return table_map


def _load_birth_death_lookup(
    table_map: dict[str, Path],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Load DEMOGRAPHIC birth dates and DEATH dates for cross-table temporal validation.

    Reads DEMOGRAPHIC.BIRTH_DATE and DEATH.DEATH_DATE into lookup DataFrames for validating that
    event dates (ADMIT_DATE, DX_DATE, etc.) fall between birth and death. For patients with
    BIRTH_DATE == 1900-01-01 (masked per HIPAA), attempts recovery using TUMOR_REGISTRY.AGE_AT_DIAGNOSIS
    and DATE_OF_DIAGNOSIS (approximates birth year as dx_year - age, creates 1900-01-01 date).

    Masked birth date recovery helps reduce false positives for "before birth" temporal validation
    flags, though recovered dates are approximate (year-level precision only).

    Prints progress messages for masked birth date recovery attempts.

    Args:
        table_map: Dict mapping table names to parquet paths (must include DEMOGRAPHIC, DEATH, TUMOR_REGISTRY*)

    Returns:
        Tuple of (birth_df, death_df) where:
        - birth_df: DataFrame with columns (PATID: String, BIRTH_DATE: Date), recovered masked dates if possible
        - death_df: DataFrame with columns (PATID: String, DEATH_DATE: Date)
        If tables missing, returns empty DataFrames with correct schema
    """
    demo_path = table_map.get("DEMOGRAPHIC")
    if not demo_path or not demo_path.exists():
        return pl.DataFrame(schema={PATID_COL: pl.String, "BIRTH_DATE": pl.Date}), pl.DataFrame(
            schema={PATID_COL: pl.String, "DEATH_DATE": pl.Date}
        )

    demo = pl.read_parquet(demo_path)
    select_cols = [PATID_COL, "BIRTH_DATE"]
    available = [c for c in select_cols if c in demo.columns]
    if "BIRTH_DATE" not in available:
        birth_df = pl.DataFrame(schema={PATID_COL: pl.String, "BIRTH_DATE": pl.Date})
    else:
        birth_df = demo.select(
            pl.col(PATID_COL).cast(pl.String),
            pl.col("BIRTH_DATE"),
        )

    # Masked birth date recovery from TUMOR_REGISTRY
    masked = birth_df.filter(pl.col("BIRTH_DATE").is_not_null() & (pl.col("BIRTH_DATE") == MASKED_BIRTH_DATE))
    if masked.height > 0:
        masked_ids = set(masked[PATID_COL].to_list())
        for tr_name in sorted(TUMOR_REGISTRY_TABLES):
            tr_path = table_map.get(tr_name)
            if not tr_path or not tr_path.exists():
                continue
            tr_schema = pl.read_parquet_schema(tr_path)
            if "AGE_AT_DIAGNOSIS" not in tr_schema or "DATE_OF_DIAGNOSIS" not in tr_schema:
                continue
            tr = pl.read_parquet(tr_path, columns=[PATID_COL, "AGE_AT_DIAGNOSIS", "DATE_OF_DIAGNOSIS"])
            tr = tr.with_columns(pl.col(PATID_COL).cast(pl.String))
            tr = tr.filter(pl.col(PATID_COL).is_in(masked_ids))
            if tr.is_empty():
                continue
            tr = tr.with_columns(pl.col("AGE_AT_DIAGNOSIS").cast(pl.Float64, strict=False))
            tr = tr.filter(
                pl.col("AGE_AT_DIAGNOSIS").is_not_null()
                & pl.col("DATE_OF_DIAGNOSIS").is_not_null()
                & (pl.col("AGE_AT_DIAGNOSIS") >= 0)
                & (pl.col("AGE_AT_DIAGNOSIS") <= 120)
            )
            if tr.is_empty():
                continue
            dx_col = pl.col("DATE_OF_DIAGNOSIS")
            dx_dtype = tr["DATE_OF_DIAGNOSIS"].dtype
            if dx_dtype == pl.String or dx_dtype == pl.Utf8:
                tr = tr.with_columns(
                    dx_col.str.to_date("%m/%d/%Y", strict=False)
                    .fill_null(dx_col.str.to_date("%d%b%Y", strict=False))
                    .fill_null(dx_col.str.to_date("%Y%m%d", strict=False))
                    .alias("DATE_OF_DIAGNOSIS")
                )
            approx = (
                tr.group_by(PATID_COL)
                .agg(
                    pl.col("DATE_OF_DIAGNOSIS").first().alias("_dx_date"),
                    pl.col("AGE_AT_DIAGNOSIS").first().alias("_age"),
                )
                .with_columns((pl.col("_dx_date").dt.year() - pl.col("_age").cast(pl.Int32)).alias("_birth_year"))
                .with_columns(pl.date(pl.col("_birth_year"), 1, 1).alias("_approx_birth"))
                .select(PATID_COL, "_approx_birth")
            )
            # Update birth_df for recovered patients
            birth_df = (
                birth_df.join(approx, on=PATID_COL, how="left")
                .with_columns(
                    pl.when(pl.col("BIRTH_DATE").eq(MASKED_BIRTH_DATE) & pl.col("_approx_birth").is_not_null())
                    .then(pl.col("_approx_birth"))
                    .otherwise(pl.col("BIRTH_DATE"))
                    .alias("BIRTH_DATE")
                )
                .drop("_approx_birth")
            )
            recovered = birth_df.filter(pl.col(PATID_COL).is_in(masked_ids) & (pl.col("BIRTH_DATE") != MASKED_BIRTH_DATE)).height
            print(f"    Recovered {recovered} masked birth dates from {tr_name}")
            break  # one TR table is enough

    # Death dates
    death_path = table_map.get("DEATH")
    if death_path and death_path.exists():
        death = pl.read_parquet(death_path)
        if "DEATH_DATE" in death.columns:
            death_df = death.select(
                pl.col(PATID_COL).cast(pl.String),
                pl.col("DEATH_DATE"),
            )
        else:
            death_df = pl.DataFrame(schema={PATID_COL: pl.String, "DEATH_DATE": pl.Date})
    else:
        death_df = pl.DataFrame(schema={PATID_COL: pl.String, "DEATH_DATE": pl.Date})

    return birth_df, death_df


def _validate_against_birth(
    df: pl.DataFrame,
    birth_df: pl.DataFrame,
    date_cols: list[str],
) -> pl.DataFrame:
    """Add temporal validation flags for date columns occurring before patient's birth date.

    Joins birth_df (PATID, BIRTH_DATE) to df and creates {col}_val_before_birth flag columns
    (Int8, 0/1) for each date column. Flag = 1 when date < BIRTH_DATE (excluding nulls and
    masked birth dates 1900-01-01). Used to identify data quality issues where event dates
    precede birth dates (impossible temporal relationship).

    Drops BIRTH_DATE column after flagging to avoid schema pollution.

    Args:
        df: DataFrame with PATID and date columns to validate
        birth_df: Lookup DataFrame with PATID and BIRTH_DATE columns
        date_cols: List of date column names to validate (from _get_date_columns)

    Returns:
        DataFrame with added {col}_val_before_birth flag columns (Int8), BIRTH_DATE dropped
    """
    if birth_df.is_empty() or not date_cols:
        return df

    df = df.join(birth_df, on=PATID_COL, how="left")

    for col in date_cols:
        flag_name = f"{col}_val_before_birth"
        df = df.with_columns(
            pl.when(
                pl.col("BIRTH_DATE").is_not_null()
                & (pl.col("BIRTH_DATE") != MASKED_BIRTH_DATE)
                & pl.col(col).is_not_null()
                & (pl.col(col).cast(pl.Date) < pl.col("BIRTH_DATE"))
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias(flag_name)
        )

    df = df.drop("BIRTH_DATE")
    return df


def _validate_against_death(
    df: pl.DataFrame,
    death_df: pl.DataFrame,
    date_cols: list[str],
) -> pl.DataFrame:
    """Add temporal validation flags for date columns occurring after patient's death date.

    Joins death_df (PATID, DEATH_DATE) to df and creates {col}_val_after_death flag columns
    (Int8, 0/1) for each date column. Flag = 1 when date > DEATH_DATE (excluding nulls). Used
    to identify data quality issues where event dates occur after death dates (impossible
    temporal relationship suggesting retrospective data entry errors or death date errors).

    Drops DEATH_DATE column after flagging to avoid schema pollution.

    Args:
        df: DataFrame with PATID and date columns to validate
        death_df: Lookup DataFrame with PATID and DEATH_DATE columns
        date_cols: List of date column names to validate (from _get_date_columns)

    Returns:
        DataFrame with added {col}_val_after_death flag columns (Int8), DEATH_DATE dropped
    """
    if death_df.is_empty() or not date_cols:
        return df

    df = df.join(death_df, on=PATID_COL, how="left")

    for col in date_cols:
        flag_name = f"{col}_val_after_death"
        df = df.with_columns(
            pl.when(pl.col("DEATH_DATE").is_not_null() & pl.col(col).is_not_null() & (pl.col(col).cast(pl.Date) > pl.col("DEATH_DATE")))
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias(flag_name)
        )

    df = df.drop("DEATH_DATE")
    return df


def _get_date_columns(df: pl.DataFrame) -> list[str]:
    """Return list of date/datetime column names, excluding existing validation flag columns.

    Filters for columns with dtype pl.Date or pl.Datetime, excluding columns with "_val_"
    infix (which are validation flag columns added in previous passes). Used to identify
    which columns need temporal validation (before birth, after death, future dates).

    Args:
        df: DataFrame to inspect for date columns

    Returns:
        List of date/datetime column names (excluding flag columns)
    """
    return [c for c in df.columns if df.schema[c] in (pl.Date, pl.Datetime) or isinstance(df.schema[c], pl.Datetime) if "_val_" not in c]


def _compute_hl_timeline(
    table_map: dict[str, Path],
    reports_dir: Path,
) -> dict:
    """Compute HL disease timeline metrics from first diagnosis to first treatment (cross-table summary).

    Aggregates DIAGNOSIS (HL ICD codes), PROCEDURES (SCT/radiation CPTs), PRESCRIBING (chemo J-codes),
    and TUMOR_REGISTRY (treatment dates) to compute: (1) Total HL patients; (2) Patients with treatment;
    (3) Median days from first HL DX to first treatment; (4) Patients with treatment before DX
    (temporal flag); (5) Patients with >365 day DX-to-treatment gap; (6) Distribution of gap buckets.

    This is a cross-table analysis (not per-row flags). Used in Section 5 (Temporal Consistency)
    of the values_validation.md report to identify temporal anomalies at the cohort level.

    Args:
        table_map: Dict mapping table names to parquet paths (must include DIAGNOSIS, optionally PROCEDURES,
            PRESCRIBING, TUMOR_REGISTRY*)
        reports_dir: Output directory for reports (currently unused but reserved for future CSV output)

    Returns:
        Dict with keys: total_patients (int), with_treatment (int), median_dx_to_tx (float or None),
        flagged_before_dx (int), flagged_over_365 (int), distribution_buckets (dict mapping bucket name to count)
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
    if not diag_path or not diag_path.exists():
        return result

    # Determine code format and get HL diagnoses
    dx_format = detect_dx_format(diag_path)
    code_set = ALL_HL_CODES if dx_format == "dotted" else ALL_HL_NORMALIZED

    dx_match_col = pl.col("DX") if dx_format == "dotted" else pl.col("DX").str.to_uppercase().str.replace_all(r"\.", "")

    diag = (
        pl.scan_parquet(diag_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .with_columns(dx_match_col.alias("_DX_MATCH"))
        .filter(pl.col("_DX_MATCH").is_in(code_set))
        .filter(pl.col("DX_DATE").is_not_null())
        .select(PATID_COL, "DX_DATE")
        .collect()
    )
    if diag.is_empty():
        return result

    first_dx = diag.group_by(PATID_COL).agg(pl.col("DX_DATE").min().alias("FIRST_HL_DX_DATE"))
    result["total_patients"] = first_dx.height

    # Collect first treatment dates from multiple sources
    tx_frames: list[pl.DataFrame] = []

    # PROCEDURES — stem cell transplant and radiation CPTs
    sct_cpts = {
        "38240",
        "38241",
        "38242",  # stem cell transplant
        "38230",
        "38232",  # bone marrow harvest
        "77401",
        "77402",
        "77407",
        "77412",  # radiation therapy
        "77427",  # radiation management
    }
    px_path = table_map.get("PROCEDURES")
    if px_path and px_path.exists():
        px_schema = pl.read_parquet_schema(px_path)
        px_date_col = "PX_DATE" if "PX_DATE" in px_schema else None
        px_code_col = "PX" if "PX" in px_schema else None
        if px_date_col and px_code_col:
            px = (
                pl.scan_parquet(px_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(pl.col(px_code_col).is_in(sct_cpts))
                .filter(pl.col(px_date_col).is_not_null())
                .group_by(PATID_COL)
                .agg(pl.col(px_date_col).min().alias("FIRST_TX_DATE"))
                .collect()
            )
            if not px.is_empty():
                tx_frames.append(px)

    # PRESCRIBING
    rx_path = table_map.get("PRESCRIBING")
    if rx_path and rx_path.exists():
        rx_schema = pl.read_parquet_schema(rx_path)
        rx_date_col = "RX_ORDER_DATE" if "RX_ORDER_DATE" in rx_schema else None
        if rx_date_col:
            rx = (
                pl.scan_parquet(rx_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(pl.col(PATID_COL).is_in(first_dx[PATID_COL].implode()))
                .filter(pl.col(rx_date_col).is_not_null())
                .group_by(PATID_COL)
                .agg(pl.col(rx_date_col).min().alias("FIRST_TX_DATE"))
                .collect()
            )
            if not rx.is_empty():
                tx_frames.append(rx)

    # TUMOR_REGISTRY treatment dates
    tr_date_cols = ["DT_SURG", "DT_RAD", "DT_CHEMO"]
    for tr_name in sorted(TUMOR_REGISTRY_TABLES):
        tr_path = table_map.get(tr_name)
        if not tr_path or not tr_path.exists():
            continue
        tr_schema = pl.read_parquet_schema(tr_path)
        available_tx = [c for c in tr_date_cols if c in tr_schema]
        if not available_tx:
            continue
        tr = (
            pl.scan_parquet(tr_path)
            .with_columns(pl.col(PATID_COL).cast(pl.String))
            .filter(pl.col(PATID_COL).is_in(first_dx[PATID_COL].implode()))
            .select([PATID_COL] + available_tx)
            .collect()
        )
        if tr.is_empty():
            continue
        for tc in available_tx:
            if tr[tc].dtype == pl.String or tr[tc].dtype == pl.Utf8:
                tr = tr.with_columns(
                    pl.col(tc)
                    .str.to_date("%Y.%m.%d", strict=False)
                    .fill_null(pl.col(tc).str.to_date("%m/%d/%Y", strict=False))
                    .fill_null(pl.col(tc).str.to_date("%d%b%Y", strict=False))
                    .fill_null(pl.col(tc).str.to_date("%Y%m%d", strict=False))
                )
            tc_df = tr.filter(pl.col(tc).is_not_null()).group_by(PATID_COL).agg(pl.col(tc).min().alias("FIRST_TX_DATE"))
            if not tc_df.is_empty():
                tx_frames.append(tc_df)

    if not tx_frames:
        return result

    # Combine all treatment dates and pick earliest per patient
    all_tx = pl.concat(tx_frames)
    earliest_tx = all_tx.group_by(PATID_COL).agg(pl.col("FIRST_TX_DATE").min().alias("FIRST_TX_DATE"))

    # Join with first DX date
    timeline = first_dx.join(earliest_tx, on=PATID_COL, how="left")
    with_tx = timeline.filter(pl.col("FIRST_TX_DATE").is_not_null())
    result["with_treatment"] = with_tx.height

    if with_tx.is_empty():
        return result

    with_tx = with_tx.with_columns((pl.col("FIRST_TX_DATE") - pl.col("FIRST_HL_DX_DATE")).dt.total_days().alias("DX_TO_TX_DAYS"))

    median_val = with_tx["DX_TO_TX_DAYS"].median()
    result["median_dx_to_tx"] = int(median_val) if median_val is not None else None
    result["flagged_before_dx"] = with_tx.filter(pl.col("DX_TO_TX_DAYS") < 0).height
    result["flagged_over_365"] = with_tx.filter(pl.col("DX_TO_TX_DAYS") > 365).height

    # Distribution buckets
    buckets = {"<0": 0, "0-30": 0, "31-90": 0, "91-180": 0, "181-365": 0, ">365": 0}
    for row in with_tx.select("DX_TO_TX_DAYS").iter_rows():
        d = row[0]
        if d is None:
            continue
        if d < 0:
            buckets["<0"] += 1
        elif d <= 30:
            buckets["0-30"] += 1
        elif d <= 90:
            buckets["31-90"] += 1
        elif d <= 180:
            buckets["91-180"] += 1
        elif d <= 365:
            buckets["181-365"] += 1
        else:
            buckets[">365"] += 1
    result["distribution_buckets"] = buckets

    return result


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------


def _section_overview(report_data: dict) -> str:
    """Generate Section 1: Validation Overview for values_validation.md report.

    Creates markdown table showing per-table summary: total rows, flag columns added, and rows
    with any validation flag. Provides quick overview of validation scope and impact across all
    CDM tables.

    Small-cell suppression applied via flag_small_cell for flagged row counts per REQ-05.

    Args:
        report_data: Dict mapping table_name to stats dict (keys: total_rows, flag_columns_added,
            rows_with_any_flag, flags)

    Returns:
        Markdown string for Section 1 (validation overview) including summary table
    """
    lines: list[str] = []
    lines.append("## 1. Validation Overview\n")

    lines.append("| Table | Rows | Flag Columns | Rows With Any Flag |")
    lines.append("|-------|------|-------------|--------------------|")
    for table_name in sorted(report_data.keys()):
        stats = report_data[table_name]
        total = stats["total_rows"]
        n_flags = stats["flag_columns_added"]
        flagged_rows = stats.get("rows_with_any_flag", 0)
        lines.append(f"| {table_name} | {total:,} | {n_flags} | {flag_small_cell(flagged_rows)} |")
    lines.append("")
    return "\n".join(lines)


def _section_valueset(report_data: dict) -> str:
    """Generate Section 2: Value Set Conformance for values_validation.md report.

    Creates markdown section showing coded field validation results per table. For each coded
    field (RACE, SEX, DX_TYPE, etc.), shows count of flagged rows (invalid codes not in PCORnet
    value sets), total rows, and invalid code rate. Highlights fields with >5% invalid codes
    with ⚠ symbol.

    Small-cell suppression applied via flag_small_cell for flagged counts per REQ-05.

    Coded field validation helps identify data collection errors, vendor-specific codes, or
    PCORnet compliance issues (e.g., unexpected RACE codes, missing DX_TYPE).

    Args:
        report_data: Dict mapping table_name to stats dict (keys: total_rows, flags with *_val_code keys)

    Returns:
        Markdown string for Section 2 (value set conformance) including per-table subsections
        with field validation tables
    """
    lines: list[str] = []
    lines.append("## 2. Value Set Conformance\n")

    any_found = False
    for table_name in sorted(report_data.keys()):
        stats = report_data[table_name]
        code_flags = {k: v for k, v in stats["flags"].items() if k.endswith("_val_code")}
        if not code_flags:
            continue
        any_found = True
        lines.append(f"### {table_name}\n")
        lines.append("| Field | Flagged | Total | Rate |")
        lines.append("|-------|---------|-------|------|")
        total = stats["total_rows"]
        for flag_col, count in sorted(code_flags.items()):
            field = flag_col.replace("_val_code", "")
            rate = count / max(total, 1) * 100
            highlight = " ⚠ >5%" if rate > 5 else ""
            lines.append(f"| {field} | {flag_small_cell(count)} | {total:,} | {rate:.2f}%{highlight} |")
        lines.append("")

    if not any_found:
        lines.append("No value set flags generated.\n")

    return "\n".join(lines)


def _section_plausibility(report_data: dict) -> str:
    """Generate Section 3: Plausibility Checks for values_validation.md report.

    Creates markdown section showing vital signs and lab result plausibility validation. For vitals
    (HT, WT, SYSTOLIC, DIASTOLIC), shows out-of-range counts and clinical ranges checked. For lab
    results (WBC, ANC, HGB, PLT, CRCL), shows out-of-range and missing RESULT_UNIT counts, plus
    table of HL-specific lab ranges checked (name, LOINC, range, unit).

    Small-cell suppression applied via flag_small_cell for flagged counts per REQ-05.

    Plausibility checks help identify data entry errors (impossible vital signs like 999 weight),
    unit conversion errors (cm vs inches for height), and missing metadata (RESULT_UNIT required
    for correct interpretation of RESULT_NUM).

    Args:
        report_data: Dict mapping table_name to stats dict (keys: total_rows, flags with *_val_range
            and RESULT_UNIT_val_missing keys)

    Returns:
        Markdown string for Section 3 (plausibility checks) including vital signs subsection, lab
        results subsection, and lab ranges reference table
    """
    lines: list[str] = []
    lines.append("## 3. Plausibility Checks\n")

    # Vital signs
    lines.append("### Vital Signs\n")
    vital_table = None
    for tbl, stats in report_data.items():
        range_flags = {k: v for k, v in stats["flags"].items() if k.endswith("_val_range") and any(k.startswith(m) for m in VITAL_RANGES)}
        if range_flags:
            vital_table = tbl
            lines.append("| Measure | Range | Flagged | % |")
            lines.append("|---------|-------|---------|---|")
            total = stats["total_rows"]
            for flag_col, count in sorted(range_flags.items()):
                measure = flag_col.replace("_val_range", "")
                lo, hi = VITAL_RANGES.get(measure, (0, 0))
                rate = count / max(total, 1) * 100
                lines.append(f"| {measure} | {lo}–{hi} | {flag_small_cell(count)} | {rate:.2f}% |")
            lines.append("")
            break

    if not vital_table:
        lines.append("No VITAL table found in validation results.\n")

    # Lab results
    lines.append("### Lab Results\n")
    lab_table = None
    for tbl, stats in report_data.items():
        if "RESULT_NUM_val_range" in stats["flags"]:
            lab_table = tbl
            total = stats["total_rows"]
            range_count = stats["flags"]["RESULT_NUM_val_range"]
            rate = range_count / max(total, 1) * 100
            lines.append(f"- **RESULT_NUM out-of-range:** {flag_small_cell(range_count)} ({rate:.2f}%)")
            if "RESULT_UNIT_val_missing" in stats["flags"]:
                unit_count = stats["flags"]["RESULT_UNIT_val_missing"]
                unit_rate = unit_count / max(total, 1) * 100
                lines.append(f"- **RESULT_UNIT missing:** {flag_small_cell(unit_count)} ({unit_rate:.2f}%)")
            lines.append("")

            lines.append("#### Lab Ranges Checked\n")
            lines.append("| Lab | LOINC | Range | Unit |")
            lines.append("|-----|-------|-------|------|")
            for loinc, info in sorted(HL_LAB_RANGES.items(), key=lambda x: x[1]["name"]):
                lines.append(f"| {info['name']} | {loinc} | {info['min']}–{info['max']} | {info['unit']} |")
            lines.append("")
            break

    if not lab_table:
        lines.append("No LAB_RESULT_CM table found in validation results.\n")

    return "\n".join(lines)


def _section_icd_concordance(concordance_data: dict) -> str:
    """Generate Section 4: ICD Version-Date Concordance for values_validation.md report.

    Creates markdown section validating that ICD-9 codes only appear before October 2015 and ICD-10
    codes only appear after July 2015 (with grace period Jul-Jan 2016). Shows total DX records,
    flagged concordance violations, and per-partner breakdown (total DX, ICD-9 count, ICD-10 count,
    pre-Oct-2015 ICD-10 count, flagged count, mapped status).

    Small-cell suppression applied via flag_small_cell for counts per REQ-05.

    ICD version-date concordance helps identify: (1) Data collection errors (ICD-10 codes before
    transition date); (2) Mapped partners (AMS, UMI) who retrospectively converted ICD-9 → ICD-10;
    (3) Grace period compliance (both versions allowed Jul 2015 - Jan 2016).

    Args:
        concordance_data: Dict with keys: total_dx (int), total_flagged (int), partner_breakdown
            (list of dicts with keys: partner, total, icd9, icd10, pre_transition_icd10, flagged, mapped)

    Returns:
        Markdown string for Section 4 (ICD concordance) including summary stats, per-partner breakdown
        table, and grace period note
    """
    lines: list[str] = []
    lines.append("## 4. ICD Version-Date Concordance\n")

    if not concordance_data:
        lines.append("No DIAGNOSIS table available for ICD concordance.\n")
        return "\n".join(lines)

    total_dx = concordance_data.get("total_dx", 0)
    total_flagged = concordance_data.get("total_flagged", 0)
    flag_rate = total_flagged / max(total_dx, 1) * 100

    lines.append(f"- **Total DX records:** {total_dx:,}")
    lines.append(f"- **Flagged:** {flag_small_cell(total_flagged)} ({flag_rate:.2f}%)")
    lines.append("- **Grace period:** Jul 2015 – Jan 2016\n")

    if "partner_breakdown" in concordance_data:
        lines.append("### Per-Partner Breakdown\n")
        lines.append("| Partner | Total DX | ICD-9 | ICD-10 | Pre-Oct-2015 ICD-10 | Flagged | Mapped? |")
        lines.append("|---------|----------|-------|--------|---------------------|---------|---------|")
        for row in concordance_data["partner_breakdown"]:
            pre_icd10 = row.get("pre_transition_icd10", 0)
            lines.append(
                f"| {row['partner']} | {row['total']:,} "
                f"| {flag_small_cell(row['icd9'])} "
                f"| {flag_small_cell(row['icd10'])} "
                f"| {flag_small_cell(pre_icd10)} "
                f"| {flag_small_cell(row['flagged'])} "
                f"| {'Yes' if row['mapped'] else 'No'} |"
            )
        lines.append("")

    lines.append(
        "> **Note:** Grace period (Jul 2015 – Jan 2016) allows both ICD-9 and ICD-10 codes. AMS and UMI auto-detected as mapped partners.\n"
    )

    return "\n".join(lines)


def _section_temporal(report_data: dict, hl_timeline: dict) -> str:
    """Generate Section 5: Temporal Consistency for values_validation.md report.

    Creates comprehensive markdown section showing temporal validation results: (1) Encounter checks
    (admit > discharge, same-day encounters); (2) Future dates table showing all date columns with
    future values; (3) Before-birth / after-death flags table; (4) Enrollment date ordering (ENR_START
    > ENR_END); (5) HL disease timeline cross-table summary (DX→treatment median days, treatment before
    DX flags, >365 day gap flags, distribution buckets).

    Small-cell suppression applied via flag_small_cell for all counts per REQ-05.

    Temporal consistency checks help identify: data entry errors (admit > discharge), future dates
    (suggesting system clock issues), biological impossibilities (events before birth or after death),
    and clinically significant delays (>365 day DX-to-treatment gap).

    Args:
        report_data: Dict mapping table_name to stats dict (keys: total_rows, flags with temporal
            validation keys like _val_admit_discharge, *_val_future, *_val_before_birth, *_val_after_death)
        hl_timeline: Dict with keys: total_patients, with_treatment, median_dx_to_tx, flagged_before_dx,
            flagged_over_365, distribution_buckets (from _compute_hl_timeline)

    Returns:
        Markdown string for Section 5 (temporal consistency) including encounter checks, future dates
        table, before-birth/after-death table, enrollment checks, and HL timeline summary with distribution
    """
    lines: list[str] = []
    lines.append("## 5. Temporal Consistency\n")

    # Encounter
    lines.append("### Encounter Temporal Checks\n")
    for tbl, stats in report_data.items():
        if "_val_admit_discharge" in stats["flags"]:
            ad = stats["flags"]["_val_admit_discharge"]
            sd = stats["flags"].get("_val_same_day", 0)
            total = stats["total_rows"]
            lines.append(f"- **Admit > Discharge:** {flag_small_cell(ad)} ({ad / max(total, 1) * 100:.2f}%)")
            lines.append(f"- **Same-day encounters:** {flag_small_cell(sd)} ({sd / max(total, 1) * 100:.2f}%)")
            lines.append("  - *Note: Same-day encounters are expected for outpatient visits*")
            lines.append("")
            break

    # Future dates
    lines.append("### Future Dates\n")
    lines.append("| Table | Flag Column | Flagged |")
    lines.append("|-------|------------|---------|")
    any_future = False
    for tbl in sorted(report_data.keys()):
        stats = report_data[tbl]
        future_flags = {k: v for k, v in stats["flags"].items() if k.endswith("_val_future") and v > 0}
        for fc, count in sorted(future_flags.items()):
            lines.append(f"| {tbl} | {fc} | {flag_small_cell(count)} |")
            any_future = True
    if not any_future:
        lines.append("| — | — | No future dates found |")
    lines.append("")

    # Before-birth / after-death
    lines.append("### Before-Birth / After-Death Flags\n")
    lines.append("| Table | Check | Flagged |")
    lines.append("|-------|-------|---------|")
    any_bd = False
    for tbl in sorted(report_data.keys()):
        stats = report_data[tbl]
        for fc, count in sorted(stats["flags"].items()):
            if ("_val_before_birth" in fc or "_val_after_death" in fc) and count > 0:
                check = "Before birth" if "before_birth" in fc else "After death"
                col_name = fc.split("_val_")[0]
                lines.append(f"| {tbl} | {check} ({col_name}) | {flag_small_cell(count)} |")
                any_bd = True
    if not any_bd:
        lines.append("| — | — | No violations found |")
    lines.append("")

    # Enrollment dates
    lines.append("### Enrollment Date Ordering\n")
    for tbl, stats in report_data.items():
        if "_val_enr_dates" in stats["flags"]:
            enr = stats["flags"]["_val_enr_dates"]
            total = stats["total_rows"]
            lines.append(f"- **ENR_START > ENR_END:** {flag_small_cell(enr)} ({enr / max(total, 1) * 100:.2f}%)")
            break
    lines.append("")

    # HL Disease Timeline
    lines.append("### HL Disease Timeline (Cross-Table Summary)\n")
    if hl_timeline["total_patients"] == 0:
        lines.append("No HL diagnosis data available for timeline analysis.\n")
    else:
        lines.append(f"- **HL patients with DX date:** {hl_timeline['total_patients']:,}")
        lines.append(f"- **Patients with any treatment record:** {flag_small_cell(hl_timeline['with_treatment'])}")
        if hl_timeline["median_dx_to_tx"] is not None:
            lines.append(f"- **Median DX→TX days:** {hl_timeline['median_dx_to_tx']}")
        lines.append(f"- **Treatment before DX (flagged):** {flag_small_cell(hl_timeline['flagged_before_dx'])}")
        lines.append(f"- **DX→TX gap > 365 days (flagged):** {flag_small_cell(hl_timeline['flagged_over_365'])}")
        lines.append("")

        if hl_timeline["distribution_buckets"]:
            lines.append("#### DX-to-Treatment Distribution\n")
            lines.append("| Bucket | Patients |")
            lines.append("|--------|----------|")
            for bucket, count in hl_timeline["distribution_buckets"].items():
                lines.append(f"| {bucket} days | {flag_small_cell(count)} |")
            lines.append("")

        lines.append("> *Expected window: 0–365 days from first HL diagnosis to first treatment.*\n")

    return "\n".join(lines)


def _section_tumor_registry(report_data: dict) -> str:
    """Generate Section 6: Tumor Registry Validation for values_validation.md report.

    Creates markdown section showing tumor registry-specific validation results for TUMOR_REGISTRY1/2/3
    tables. Per-table subsections show validation checks: (1) HISTOLOGY (HL codes 9650-9667); (2) STAGE_GROUP
    format (Ann Arbor staging I-IV); (3) B_SYMPTOMS (B symptoms present/absent codes); (4) CS_SSF1 (B symptoms
    site-specific factor); (5) AGE_AT_DIAGNOSIS range (0-120); (6) PRIMARY_SITE (HL primary sites C77.x);
    (7) Treatment timing (DT_SURG, DT_RAD, DT_CHEMO before DATE_OF_DIAGNOSIS).

    Small-cell suppression applied via flag_small_cell for flagged counts per REQ-05.

    Notes that only ORL, TMH, UFH partners contribute tumor registry data (other partners don't collect
    cancer registry variables).

    Args:
        report_data: Dict mapping table_name to stats dict (keys: total_rows, flags with tumor registry
            validation keys like HISTOLOGY_val_hl, STAGE_GROUP_val_format, *_val_before_dx)

    Returns:
        Markdown string for Section 6 (tumor registry validation) including per-table subsections with
        validation check tables
    """
    lines: list[str] = []
    lines.append("## 6. Tumor Registry Validation\n")

    tr_tables = {tbl: stats for tbl, stats in report_data.items() if tbl in TUMOR_REGISTRY_TABLES}

    if not tr_tables:
        lines.append("No TUMOR_REGISTRY tables found in validated data.\n")
        return "\n".join(lines)

    lines.append("> Only ORL, TMH, UFH partners have TUMOR_REGISTRY data.\n")

    # Map flag columns to check descriptions
    check_map = {
        "HISTOLOGY_val_hl": ("histology", "HISTOLOGY"),
        "STAGE_GROUP_val_format": ("stage", "STAGE_GROUP"),
        "B_SYMPTOMS_val_code": ("b_symptoms", "B_SYMPTOMS"),
        "CS_SSF1_val_code": ("b_symptoms", "CS_SSF1"),
        "AGE_AT_DIAGNOSIS_val_range": ("age", "AGE_AT_DIAGNOSIS"),
        "PRIMARY_SITE_val_hl": ("primary_site", "PRIMARY_SITE"),
    }
    tx_prefix = "_val_before_dx"

    for tbl in sorted(tr_tables.keys()):
        stats = tr_tables[tbl]
        total = stats["total_rows"]
        lines.append(f"### {tbl} ({total:,} rows)\n")
        lines.append("| Check | Field | Flagged | % |")
        lines.append("|-------|-------|---------|---|")

        for flag_col, (check, field) in check_map.items():
            if flag_col in stats["flags"]:
                count = stats["flags"][flag_col]
                rate = count / max(total, 1) * 100
                lines.append(f"| {check} | {field} | {flag_small_cell(count)} | {rate:.2f}% |")

        # Treatment timing flags
        for fc, count in sorted(stats["flags"].items()):
            if fc.endswith(tx_prefix) and count > 0:
                field = fc.replace(tx_prefix, "")
                rate = count / max(total, 1) * 100
                lines.append(f"| treatment_timing | {field} | {flag_small_cell(count)} | {rate:.2f}% |")

        lines.append("")

    return "\n".join(lines)


def _write_temporal_issues_csv(
    report_data: dict,
    hl_timeline: dict,
    reports_dir: Path,
) -> None:
    """Write reports/temporal_issues.csv with detailed temporal validation findings.

    Creates CSV with one row per temporal check failure type per table: admit/discharge order,
    same-day encounters, future dates, before-birth dates, after-death dates, enrollment date
    order (ENR_START > ENR_END). Also includes HL timeline cross-table summary rows (treatment
    before DX, DX-to-treatment gap >365 days).

    Small-cell suppression applied via _suppress (replaces 1-10 with dash) per REQ-05 for CSV output.

    CSV columns: table, check_type, flagged_count (suppressed), total_rows, flag_rate (percentage string).

    Args:
        report_data: Dict mapping table_name to stats dict (keys: total_rows, flags with temporal
            validation keys)
        hl_timeline: Dict with keys: total_patients, flagged_before_dx, flagged_over_365 (from
            _compute_hl_timeline)
        reports_dir: Output directory for reports
    """
    rows: list[dict] = []

    for tbl in sorted(report_data.keys()):
        stats = report_data[tbl]
        total = stats["total_rows"]

        # Admit/discharge
        if "_val_admit_discharge" in stats["flags"]:
            count = stats["flags"]["_val_admit_discharge"]
            rows.append(
                {
                    "table": tbl,
                    "check_type": "admit_discharge",
                    "flagged_count": _suppress(count),
                    "total_rows": total,
                    "flag_rate": f"{count / max(total, 1) * 100:.2f}%",
                }
            )
        if "_val_same_day" in stats["flags"]:
            count = stats["flags"]["_val_same_day"]
            rows.append(
                {
                    "table": tbl,
                    "check_type": "same_day",
                    "flagged_count": _suppress(count),
                    "total_rows": total,
                    "flag_rate": f"{count / max(total, 1) * 100:.2f}%",
                }
            )

        # Future dates
        for fc, count in stats["flags"].items():
            if fc.endswith("_val_future") and count > 0:
                rows.append(
                    {
                        "table": tbl,
                        "check_type": "future_date",
                        "flagged_count": _suppress(count),
                        "total_rows": total,
                        "flag_rate": f"{count / max(total, 1) * 100:.2f}%",
                    }
                )

        # Before-birth / after-death
        for fc, count in stats["flags"].items():
            if "_val_before_birth" in fc and count > 0:
                rows.append(
                    {
                        "table": tbl,
                        "check_type": "before_birth",
                        "flagged_count": _suppress(count),
                        "total_rows": total,
                        "flag_rate": f"{count / max(total, 1) * 100:.2f}%",
                    }
                )
            if "_val_after_death" in fc and count > 0:
                rows.append(
                    {
                        "table": tbl,
                        "check_type": "after_death",
                        "flagged_count": _suppress(count),
                        "total_rows": total,
                        "flag_rate": f"{count / max(total, 1) * 100:.2f}%",
                    }
                )

        # Enrollment
        if "_val_enr_dates" in stats["flags"]:
            count = stats["flags"]["_val_enr_dates"]
            rows.append(
                {
                    "table": tbl,
                    "check_type": "enr_dates",
                    "flagged_count": _suppress(count),
                    "total_rows": total,
                    "flag_rate": f"{count / max(total, 1) * 100:.2f}%",
                }
            )

    # HL timeline summary rows
    if hl_timeline["total_patients"] > 0:
        tp = hl_timeline["total_patients"]
        rows.append(
            {
                "table": "CROSS_TABLE",
                "check_type": "hl_timeline_before_dx",
                "flagged_count": _suppress(hl_timeline["flagged_before_dx"]),
                "total_rows": tp,
                "flag_rate": f"{hl_timeline['flagged_before_dx'] / max(tp, 1) * 100:.2f}%",
            }
        )
        rows.append(
            {
                "table": "CROSS_TABLE",
                "check_type": "hl_timeline_over_365",
                "flagged_count": _suppress(hl_timeline["flagged_over_365"]),
                "total_rows": tp,
                "flag_rate": f"{hl_timeline['flagged_over_365'] / max(tp, 1) * 100:.2f}%",
            }
        )

    if rows:
        df = pl.DataFrame(rows)
        df.write_csv(reports_dir / "temporal_issues.csv")


def _write_tumor_registry_csv(
    report_data: dict,
    reports_dir: Path,
) -> None:
    """Write reports/tumor_registry_validation.csv with detailed tumor registry validation findings.

    Creates CSV with one row per validation check per tumor registry table: histology (HL codes
    9650-9667), stage format (Ann Arbor I-IV), B symptoms codes, AGE_AT_DIAGNOSIS range, PRIMARY_SITE
    (HL primary sites), and treatment timing (treatment dates before diagnosis date).

    Small-cell suppression applied via _suppress (replaces 1-10 with dash) per REQ-05 for CSV output.

    CSV columns: table, check (check type), field (column name), valid_count (suppressed), invalid_count
    (suppressed), invalid_pct (percentage string).

    Args:
        report_data: Dict mapping table_name to stats dict (keys: total_rows, flags with tumor registry
            validation keys like HISTOLOGY_val_hl, *_val_before_dx)
        reports_dir: Output directory for reports
    """
    rows: list[dict] = []

    check_map = {
        "HISTOLOGY_val_hl": ("histology", "HISTOLOGY"),
        "STAGE_GROUP_val_format": ("stage", "STAGE_GROUP"),
        "B_SYMPTOMS_val_code": ("b_symptoms", "B_SYMPTOMS"),
        "CS_SSF1_val_code": ("b_symptoms", "CS_SSF1"),
        "AGE_AT_DIAGNOSIS_val_range": ("age", "AGE_AT_DIAGNOSIS"),
        "PRIMARY_SITE_val_hl": ("primary_site", "PRIMARY_SITE"),
    }

    for tbl in sorted(report_data.keys()):
        if tbl not in TUMOR_REGISTRY_TABLES:
            continue
        stats = report_data[tbl]
        total = stats["total_rows"]

        for flag_col, (check, field) in check_map.items():
            if flag_col not in stats["flags"]:
                continue
            flagged = stats["flags"][flag_col]
            valid = total - flagged
            pct = flagged / max(total, 1) * 100
            rows.append(
                {
                    "table": tbl,
                    "check": check,
                    "field": field,
                    "valid_count": _suppress(valid),
                    "invalid_count": _suppress(flagged),
                    "invalid_pct": f"{pct:.2f}%",
                }
            )

        # Treatment timing flags
        for fc, count in sorted(stats["flags"].items()):
            if fc.endswith("_val_before_dx"):
                field = fc.replace("_val_before_dx", "")
                valid = total - count
                pct = count / max(total, 1) * 100
                rows.append(
                    {
                        "table": tbl,
                        "check": "treatment_timing",
                        "field": field,
                        "valid_count": _suppress(valid),
                        "invalid_count": _suppress(count),
                        "invalid_pct": f"{pct:.2f}%",
                    }
                )

    if rows:
        df = pl.DataFrame(rows)
        df.write_csv(reports_dir / "tumor_registry_validation.csv")


def _suppress(value: int) -> str:
    """Replace small-cell counts (1-10) with dash for CSV output per HIPAA de-identification.

    Used in CSV reports where values must be truly suppressed (not just flagged). Markdown
    reports use flag_small_cell() which adds ⚠ warning but keeps value visible for debugging.

    Args:
        value: Count to potentially suppress

    Returns:
        "-" if 1 <= value <= 10, otherwise string representation of value
    """
    if 1 <= value <= SMALL_CELL_THRESHOLD:
        return "-"
    return str(value)


# ---------------------------------------------------------------------------
# ICD concordance CSV helper
# ---------------------------------------------------------------------------


def _build_concordance_data(
    table_map: dict[str, Path],
    mapped_partners: set[str],
    report_data: dict,
    partner_col: str = "SOURCE",
) -> dict:
    """Build ICD version-date concordance summary data for Section 4 report and CSV output.

    Aggregates DIAGNOSIS table to compute: (1) Total DX records; (2) Total flagged concordance
    violations (ICD-10 before Oct 2015 transition, excluding grace period Jul 2015 - Jan 2016);
    (3) Per-partner breakdown (total DX, ICD-9 count, ICD-10 count, pre-transition ICD-10 count,
    flagged count, mapped partner indicator).

    Auto-detects ICD version using uppercase letter regex (ICD-10 starts with letter, ICD-9 is
    all digits). Identifies mapped partners (AMS, UMI who retrospectively converted ICD-9 → ICD-10)
    using detect_mapped_partners() from src/validate/values.py.

    Args:
        table_map: Dict mapping table names to parquet paths (must include DIAGNOSIS)
        mapped_partners: Set of partner codes known to have ICD-9 → ICD-10 mapping (AMS, UMI)
        report_data: Dict mapping table_name to stats dict (used to extract total flagged count
            from DIAGNOSIS.DX_val_icd_concordance if available)
        partner_col: Column name for partner/site grouping (default "SOURCE")

    Returns:
        Dict with keys: total_dx (int), total_flagged (int), partner_breakdown (list of dicts
        with keys: partner, total, icd9, icd10, pre_transition_icd10, flagged, mapped)
        Returns empty dict if DIAGNOSIS table not found or missing required columns
    """
    diag_path = table_map.get("DIAGNOSIS")
    if not diag_path or not diag_path.exists():
        return {}

    diag = pl.read_parquet(diag_path)
    if "DX" not in diag.columns or "DX_DATE" not in diag.columns:
        return {}

    total_dx = diag.height
    total_flagged = 0
    if "DIAGNOSIS" in report_data:
        total_flagged = report_data["DIAGNOSIS"]["flags"].get("DX_val_icd_concordance", 0)

    result: dict = {
        "total_dx": total_dx,
        "total_flagged": total_flagged,
    }

    is_icd10 = pl.col("DX").str.to_uppercase().str.contains(r"^[A-Z]")

    if partner_col in diag.columns:
        is_pre_trans_icd10 = is_icd10 & pl.col("DX_DATE").is_not_null() & (pl.col("DX_DATE") < ICD10_TRANSITION)
        partner_stats = (
            diag.with_columns(
                is_icd10.alias("_is_icd10"),
                is_pre_trans_icd10.alias("_pre_icd10"),
            )
            .group_by(partner_col)
            .agg(
                pl.len().alias("total"),
                pl.col("_is_icd10").sum().alias("icd10"),
                (pl.len() - pl.col("_is_icd10").sum()).alias("icd9"),
                pl.col("_pre_icd10").sum().alias("pre_transition_icd10"),
            )
            .sort(partner_col)
        )

        # Get per-partner flagged counts
        flagged_col = "DX_val_icd_concordance"
        if flagged_col in diag.columns:
            partner_flagged = diag.filter(pl.col(flagged_col) == 1).group_by(partner_col).agg(pl.len().alias("flagged"))
        else:
            # Re-read after validation — flags written to parquet
            try:
                diag_updated = pl.read_parquet(diag_path)
                if flagged_col in diag_updated.columns:
                    partner_flagged = diag_updated.filter(pl.col(flagged_col) == 1).group_by(partner_col).agg(pl.len().alias("flagged"))
                else:
                    partner_flagged = pl.DataFrame(schema={partner_col: pl.String, "flagged": pl.UInt32})
            except Exception:
                partner_flagged = pl.DataFrame(schema={partner_col: pl.String, "flagged": pl.UInt32})

        merged = partner_stats.join(partner_flagged, on=partner_col, how="left")
        merged = merged.with_columns(pl.col("flagged").fill_null(0))

        breakdown = []
        for row in merged.iter_rows(named=True):
            p = row[partner_col] if row[partner_col] is not None else "NULL"
            breakdown.append(
                {
                    "partner": p,
                    "total": row["total"],
                    "icd9": row["icd9"],
                    "icd10": row["icd10"],
                    "pre_transition_icd10": row["pre_transition_icd10"],
                    "flagged": row["flagged"],
                    "mapped": p in mapped_partners,
                }
            )
        result["partner_breakdown"] = breakdown

    return result


def _write_icd_concordance_csv(
    concordance_data: dict,
    reports_dir: Path,
) -> None:
    """Write reports/icd_concordance.csv with detailed per-partner ICD version concordance data.

    Creates CSV with one row per partner showing: total DX records, ICD-9 count, ICD-10 count,
    pre-transition ICD-10 count (before Oct 2015), flagged concordance violations, and mapped
    partner indicator (True for AMS/UMI who retrospectively converted ICD-9 → ICD-10).

    Small-cell suppression applied via _suppress (replaces 1-10 with dash) per REQ-05 for CSV output.

    CSV columns: partner, total_dx, icd9_count (suppressed), icd10_count (suppressed),
    pre_transition_icd10 (suppressed), flagged_count (suppressed), is_mapped (bool).

    Args:
        concordance_data: Dict with key "partner_breakdown" (list of dicts from _build_concordance_data)
        reports_dir: Output directory for reports
    """
    if "partner_breakdown" not in concordance_data:
        return

    rows = []
    for row in concordance_data["partner_breakdown"]:
        pre_icd10 = row.get("pre_transition_icd10", 0)
        rows.append(
            {
                "partner": row["partner"],
                "total_dx": row["total"],
                "icd9_count": _suppress(row["icd9"]),
                "icd10_count": _suppress(row["icd10"]),
                "pre_transition_icd10": _suppress(pre_icd10),
                "flagged_count": _suppress(row["flagged"]),
                "is_mapped": row["mapped"],
            }
        )

    if rows:
        df = pl.DataFrame(rows)
        df.write_csv(reports_dir / "icd_concordance.csv")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(config_path: Path | None = None) -> None:
    """Phase 4: Value and temporal validation for OneFlorida+ PCORnet CDM with HL-specific checks.

    Entry point for deep value validation pipeline. Performs six validation categories:
    (1) Coded field validation against PCORnet value sets (RACE, SEX, DX_TYPE, etc.);
    (2) Vital/lab plausibility (HT, WT, vitals ranges; HL-specific lab LOINC ranges for WBC, ANC, HGB, PLT, CRCL);
    (3) ICD version-date concordance (ICD-10 transition Oct 2015 with grace period Jul 2015 - Jan 2016);
    (4) Temporal consistency (future dates, before-birth dates, after-death dates, admit/discharge order,
        enrollment date order, encounter temporal relationships);
    (5) HL disease timeline (cross-table DX→treatment gap analysis from DIAGNOSIS, PROCEDURES, PRESCRIBING,
        TUMOR_REGISTRY);
    (6) Tumor registry validation (HISTOLOGY HL codes 9650-9667, STAGE_GROUP Ann Arbor I-IV, B_SYMPTOMS codes,
        AGE_AT_DIAGNOSIS 0-120, PRIMARY_SITE HL C77.x, treatment timing before DX).

    Adds binary validation flag columns (Int8, 0/1) to each table and writes flagged Parquet back to
    parquet_dir in-place. Generates four outputs: reports/values_validation.md (main report with 6 sections),
    reports/temporal_issues.csv (detailed temporal findings), reports/tumor_registry_validation.csv (tumor
    registry findings), reports/icd_concordance.csv (per-partner ICD concordance).

    Small-cell suppression: Markdown report uses flag_small_cell (adds ⚠ for 1-10), CSV files use
    _suppress (replaces 1-10 with dash) per REQ-05.

    Designed for HPC interactive sessions (srun --pty bash). Typical run time: 10-15 minutes depending
    on table count and row counts. Uses lazy evaluation for memory efficiency on large tables. Sequential
    table processing.

    Creates reports/ directory if it doesn't exist. Prints progress for each validation category (tables
    checked, flags added, rows flagged) to stdout. Final summary shows total tables validated, total flag
    columns added, total rows flagged, elapsed time, and report paths.

    Args:
        config_path: Optional path to config/paths.toml (uses default if None)

    Raises:
        SystemExit: If critical error occurs (missing config, parquet read/write failures, etc.)
    """
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

    # ----- Build value set lookup -----
    print(f"\n{'─' * 60}")
    print("  Building value set lookup...")
    print(f"{'─' * 60}")
    lookup = build_valueset_lookup(paths.valuesets_path)
    print(f"  Value sets loaded: {len(lookup)} (table, field) pairs")

    # ----- Load birth/death lookup -----
    print("\n  Loading birth/death lookup for cross-table temporal checks...")
    birth_df, death_df = _load_birth_death_lookup(table_map)
    print(f"  Birth records: {birth_df.height:,}")
    print(f"  Death records: {death_df.height:,}")

    # ----- Detect mapped partners -----
    diag_path = table_map.get("DIAGNOSIS")
    mapped_partners: set[str] = {"AMS", "UMI"}
    if diag_path and diag_path.exists():
        diag_for_detect = pl.read_parquet(diag_path)
        mapped_partners = detect_mapped_partners(diag_for_detect)
        print(f"  Mapped partners: {sorted(mapped_partners)}")
        del diag_for_detect

    # ----- Main validation loop -----
    print(f"\n{'─' * 60}")
    print("  VALIDATION LOOP")
    print(f"{'─' * 60}")

    report_data: dict = {}
    tables_sorted = sorted(table_map.items())
    total_tables = len(tables_sorted)
    skip_tables = {"DEMOGRAPHIC", "DEATH"}

    for idx, (table_name, pq_path) in enumerate(tables_sorted, 1):
        print(f"\n  [{idx}/{total_tables}] {table_name}", end="")

        if not pq_path.exists():
            print(" — SKIP (parquet not found)")
            continue

        df = pl.read_parquet(pq_path)
        df = drop_existing_flags(df)
        initial_cols = len(df.columns)

        # Value set validation (skip TUMOR_REGISTRY — NAACCR, not CDM value sets)
        if table_name not in TUMOR_REGISTRY_TABLES:
            df = validate_coded_fields(df, table_name, lookup)

        # Table-specific checks
        if table_name == "VITAL":
            df = validate_vital_plausibility(df)
        elif table_name == "LAB_RESULT_CM":
            df = validate_lab_plausibility(df)
        elif table_name == "DIAGNOSIS":
            df = validate_icd_concordance(df, mapped_partners)
        elif table_name == "ENCOUNTER":
            df = validate_temporal_encounter(df)
        elif table_name == "ENROLLMENT":
            df = validate_enrollment_dates(df)
        elif table_name in TUMOR_REGISTRY_TABLES:
            df = validate_tumor_registry(df)

        # Universal temporal checks
        df = validate_future_dates(df)

        # Cross-table birth/death checks (skip DEMOGRAPHIC and DEATH themselves)
        if table_name not in skip_tables:
            date_cols = _get_date_columns(df)
            if date_cols and PATID_COL in df.columns:
                df = df.with_columns(pl.col(PATID_COL).cast(pl.String))
                df = _validate_against_birth(df, birth_df, date_cols)
                df = _validate_against_death(df, death_df, date_cols)

        # Write back
        stats = write_validated(df, pq_path)

        # Count rows with any flag
        flag_cols = [c for c in df.columns if "_val_" in c]
        if flag_cols:
            any_flag_expr = pl.lit(False)
            for fc in flag_cols:
                any_flag_expr = any_flag_expr | (pl.col(fc) == 1)
            rows_with_flag = df.filter(any_flag_expr).height
        else:
            rows_with_flag = 0
        stats["rows_with_any_flag"] = rows_with_flag

        report_data[table_name] = stats
        new_flags = len(df.columns) - initial_cols
        print(f" — {new_flags} flags added, {rows_with_flag:,} rows flagged")

    # ----- Cross-table HL timeline -----
    print(f"\n{'─' * 60}")
    print("  CROSS-TABLE: HL Disease Timeline")
    print(f"{'─' * 60}")
    hl_timeline = _compute_hl_timeline(table_map, reports_dir)
    if hl_timeline["total_patients"] > 0:
        print(f"  HL patients with DX: {hl_timeline['total_patients']:,}")
        print(f"  With treatment:      {hl_timeline['with_treatment']:,}")
        if hl_timeline["median_dx_to_tx"] is not None:
            print(f"  Median DX→TX days:   {hl_timeline['median_dx_to_tx']}")
        print(f"  TX before DX:        {hl_timeline['flagged_before_dx']}")
        print(f"  Gap > 365 days:      {hl_timeline['flagged_over_365']}")
    else:
        print("  No HL diagnosis data for timeline analysis")

    # ----- ICD concordance CSV -----
    print(f"\n{'─' * 60}")
    print("  ICD Concordance CSV")
    print(f"{'─' * 60}")
    concordance_data = _build_concordance_data(table_map, mapped_partners, report_data)
    _write_icd_concordance_csv(concordance_data, reports_dir)
    if concordance_data:
        print("  Written: reports/icd_concordance.csv")
    else:
        print("  Skipped — no DIAGNOSIS data")

    # ----- Generate reports -----
    print(f"\n{'─' * 60}")
    print("  Assembling reports...")
    print(f"{'─' * 60}")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report_parts: list[str] = []
    report_parts.append("# Value & Temporal Validation Report\n")
    report_parts.append(f"**Generated:** {timestamp}")
    report_parts.append(f"**Data source:** {paths.data_root}")
    report_parts.append(f"**Parquet directory:** {paths.parquet_dir}")
    report_parts.append(f"**Tables validated:** {len(report_data)}\n")

    report_parts.append("## Table of Contents\n")
    report_parts.append("1. [Validation Overview](#1-validation-overview)")
    report_parts.append("2. [Value Set Conformance](#2-value-set-conformance)")
    report_parts.append("3. [Plausibility Checks](#3-plausibility-checks)")
    report_parts.append("4. [ICD Version-Date Concordance](#4-icd-version-date-concordance)")
    report_parts.append("5. [Temporal Consistency](#5-temporal-consistency)")
    report_parts.append("6. [Tumor Registry Validation](#6-tumor-registry-validation)\n")
    report_parts.append("---\n")

    report_parts.append(_section_overview(report_data))
    report_parts.append(_section_valueset(report_data))
    report_parts.append(_section_plausibility(report_data))
    report_parts.append(_section_icd_concordance(concordance_data))
    report_parts.append(_section_temporal(report_data, hl_timeline))
    report_parts.append(_section_tumor_registry(report_data))

    report_path = reports_dir / "value_validation.md"
    report_path.write_text("\n".join(report_parts), encoding="utf-8")

    _write_temporal_issues_csv(report_data, hl_timeline, reports_dir)
    _write_tumor_registry_csv(report_data, reports_dir)

    overall_elapsed = time.time() - overall_start

    # ----- Compute totals -----
    total_flag_cols = sum(s["flag_columns_added"] for s in report_data.values())
    total_flagged_rows = sum(s.get("rows_with_any_flag", 0) for s in report_data.values())
    icd_flagged = concordance_data.get("total_flagged", 0)
    icd_total = concordance_data.get("total_dx", 0)

    # ----- Console summary -----
    print(f"\n{'=' * 60}")
    print("  VALUE & TEMPORAL VALIDATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Tables validated:      {len(report_data)}")
    print(f"  Total flag columns:    {total_flag_cols}")
    print(f"  Total flagged rows:    {total_flagged_rows:,}")
    print(f"  ICD concordance:       {icd_flagged:,}/{icd_total:,} flagged")
    if hl_timeline["median_dx_to_tx"] is not None:
        print(f"  HL timeline median:    {hl_timeline['median_dx_to_tx']} days DX→TX")
    print(f"  Elapsed:               {overall_elapsed:.1f}s")
    print("  Reports:")
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
