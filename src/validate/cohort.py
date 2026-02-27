# HL data loading & cleaning — cohort verification module
"""HL cohort verification with exact ICD code matching, dual-date methods,
ICD version flagging, DX_TYPE mismatch detection, and enrollment cross-check.

Uses exact set of 149 ICD codes (77 ICD-10 C81.xx + 72 ICD-9 201.xx) with
both dotted and normalized (dot-stripped) forms for format-adaptive matching.
"""

from pathlib import Path

import polars as pl

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PATID_COL = "ID"

ICD10_HL_CODES: set[str] = {
    f"C81.{sub}{site}"
    for sub in ("0", "1", "2", "3", "4", "7", "9")
    for site in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "A")
}  # 77 codes: C81.00 through C81.9A (no C81.5x or C81.6x)

ICD9_HL_CODES: set[str] = {
    f"201.{sub}{site}"
    for sub in ("0", "1", "2", "4", "5", "6", "7", "9")
    for site in ("0", "1", "2", "3", "4", "5", "6", "7", "8")
}  # 72 codes: 201.00 through 201.98 (no 201.3x)

ALL_HL_CODES: set[str] = ICD10_HL_CODES | ICD9_HL_CODES  # 149 codes


def normalize_dx(code: str) -> str:
    """Normalize diagnosis code: uppercase + remove dots."""
    return code.upper().replace(".", "")


ICD10_HL_NORMALIZED: set[str] = {normalize_dx(c) for c in ICD10_HL_CODES}
ICD9_HL_NORMALIZED: set[str] = {normalize_dx(c) for c in ICD9_HL_CODES}
ALL_HL_NORMALIZED: set[str] = ICD10_HL_NORMALIZED | ICD9_HL_NORMALIZED

# Expected ICD-10 DX_TYPE values (valid or missing)
_VALID_ICD10_DX_TYPES = {"10", None, "", "NI"}
_VALID_ICD9_DX_TYPES = {"09", None, "", "NI"}


# ---------------------------------------------------------------------------
# 1. DX format detection
# ---------------------------------------------------------------------------


def detect_dx_format(diagnosis_path: Path) -> str:
    """Detect whether DX values use dotted (C81.10) or undotted (C8110) format.

    Samples up to 1000 non-null DX values and checks dot frequency.
    Returns 'dotted' or 'undotted'.
    """
    sample = (
        pl.scan_parquet(diagnosis_path)
        .filter(pl.col("DX").is_not_null())
        .select("DX")
        .head(1000)
        .collect()
    )
    if sample.is_empty():
        return "dotted"

    dotted_count = sample.filter(pl.col("DX").str.contains(r"\.")).height
    return "dotted" if dotted_count > sample.height / 2 else "undotted"


# ---------------------------------------------------------------------------
# 2. DX_TYPE mismatch detection
# ---------------------------------------------------------------------------


def check_dx_type_mismatches(hl_dx: pl.DataFrame) -> pl.DataFrame:
    """Find HL DX records where code prefix disagrees with DX_TYPE.

    C81.xx with DX_TYPE not in ('10', None, '', 'NI') → mismatch.
    201.xx with DX_TYPE not in ('09', None, '', 'NI') → mismatch.
    Reports mismatches but does NOT exclude records (per locked decision).
    """
    if "DX_TYPE" not in hl_dx.columns:
        return pl.DataFrame(
            schema={"ID": pl.String, "DX": pl.String, "DX_TYPE": pl.String,
                    "expected_type": pl.String, "SOURCE": pl.String}
        )

    has_dx_type = hl_dx.filter(pl.col("DX_TYPE").is_not_null() & (pl.col("DX_TYPE") != ""))

    if has_dx_type.is_empty():
        return pl.DataFrame(
            schema={"ID": pl.String, "DX": pl.String, "DX_TYPE": pl.String,
                    "expected_type": pl.String, "SOURCE": pl.String}
        )

    dx_col = "DX"
    result = has_dx_type.with_columns(
        pl.when(
            pl.col(dx_col).str.to_uppercase().str.starts_with("C81")
        ).then(pl.lit("10"))
        .when(
            pl.col(dx_col).str.starts_with("201")
        ).then(pl.lit("09"))
        .otherwise(pl.lit("unknown"))
        .alias("expected_type")
    )

    mismatches = result.filter(
        (pl.col("expected_type") != "unknown")
        & (pl.col("DX_TYPE") != pl.col("expected_type"))
        & (~pl.col("DX_TYPE").is_in(["NI", ""]))
    )

    select_cols = [PATID_COL, "DX", "DX_TYPE", "expected_type"]
    if "SOURCE" in mismatches.columns:
        select_cols.append("SOURCE")
    else:
        mismatches = mismatches.with_columns(pl.lit("ALL").alias("SOURCE"))
        select_cols.append("SOURCE")

    return mismatches.select(select_cols)


# ---------------------------------------------------------------------------
# 3. Main cohort verification (5 stages)
# ---------------------------------------------------------------------------


def verify_hl_cohort(
    diagnosis_path: Path,
    encounter_path: Path,
    partner_col: str = "SOURCE",
) -> dict:
    """Five-stage HL cohort verification algorithm.

    Stage 1: Extract HL diagnosis records with format-adaptive matching
    Stage 2: Method A — 2+ distinct DX_DATEs
    Stage 3: Method B — 2+ distinct ADMIT_DATEs via ENCOUNTER join
    Stage 4: Compare methods with per-partner breakdown
    Stage 5: ICD version flag per patient with AMS/UMI caveat

    All IDs and ENCOUNTERIDs cast to String. Uses lazy evaluation where possible.
    """
    # --- Stage 1: Extract HL DX records ---
    dx_format = detect_dx_format(diagnosis_path)
    code_set = ALL_HL_CODES if dx_format == "dotted" else ALL_HL_NORMALIZED
    icd10_set = ICD10_HL_CODES if dx_format == "dotted" else ICD10_HL_NORMALIZED
    icd9_set = ICD9_HL_CODES if dx_format == "dotted" else ICD9_HL_NORMALIZED

    dx_schema = pl.read_parquet_schema(diagnosis_path)
    select_cols = [PATID_COL, "DX", "DX_DATE"]
    if "DX_TYPE" in dx_schema:
        select_cols.append("DX_TYPE")
    if "ENCOUNTERID" in dx_schema:
        select_cols.append("ENCOUNTERID")
    if partner_col in dx_schema:
        select_cols.append(partner_col)

    dx_match_col = pl.col("DX") if dx_format == "dotted" else pl.col("DX").str.to_uppercase().str.replace_all(r"\.", "")

    hl_lf = (
        pl.scan_parquet(diagnosis_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .with_columns(dx_match_col.alias("_DX_MATCH"))
        .filter(pl.col("_DX_MATCH").is_in(code_set))
        .select(select_cols + ["_DX_MATCH"])
    )

    if "ENCOUNTERID" in select_cols:
        hl_lf = hl_lf.with_columns(pl.col("ENCOUNTERID").cast(pl.String))

    hl_dx = hl_lf.collect()

    total_hl_records = hl_dx.height
    unique_patients = hl_dx[PATID_COL].n_unique()

    null_dx_date_records = hl_dx.filter(pl.col("DX_DATE").is_null()).height
    null_dx_date_patients = (
        hl_dx.filter(pl.col("DX_DATE").is_null())[PATID_COL].n_unique()
        if null_dx_date_records > 0 else 0
    )

    # --- Stage 2: Method A — 2+ distinct DX_DATEs ---
    method_a_df = (
        hl_dx
        .filter(pl.col("DX_DATE").is_not_null())
        .group_by(PATID_COL)
        .agg(pl.col("DX_DATE").n_unique().alias("distinct_dx_dates"))
        .filter(pl.col("distinct_dx_dates") >= 2)
    )
    method_a_ids = set(method_a_df[PATID_COL].to_list())

    # --- Stage 3: Method B — 2+ distinct ADMIT_DATEs ---
    method_b_ids: set[str] = set()
    no_encounterid_match = 0

    if "ENCOUNTERID" in hl_dx.columns:
        hl_with_enc = hl_dx.filter(pl.col("ENCOUNTERID").is_not_null())
        no_encounterid_match = hl_dx.filter(pl.col("ENCOUNTERID").is_null()).height

        enc_lf = (
            pl.scan_parquet(encounter_path)
            .select(
                pl.col("ENCOUNTERID").cast(pl.String),
                "ADMIT_DATE",
            )
        )

        joined = (
            hl_with_enc.lazy()
            .join(enc_lf, on="ENCOUNTERID", how="inner")
            .collect()
        )

        method_b_df = (
            joined
            .filter(pl.col("ADMIT_DATE").is_not_null())
            .group_by(PATID_COL)
            .agg(pl.col("ADMIT_DATE").n_unique().alias("distinct_admit_dates"))
            .filter(pl.col("distinct_admit_dates") >= 2)
        )
        method_b_ids = set(method_b_df[PATID_COL].to_list())
    else:
        joined = pl.DataFrame()

    # --- Stage 4: Compare methods ---
    a_only = method_a_ids - method_b_ids
    b_only = method_b_ids - method_a_ids
    both = method_a_ids & method_b_ids
    union = method_a_ids | method_b_ids

    # Per-partner breakdown of union cohort
    union_df = pl.DataFrame({PATID_COL: list(union)})
    per_partner: dict[str, int] = {}
    if partner_col in hl_dx.columns:
        partner_df = (
            hl_dx
            .join(union_df, on=PATID_COL, how="inner")
            .group_by(partner_col)
            .agg(pl.col(PATID_COL).n_unique().alias("n_patients"))
        )
        for row in partner_df.iter_rows(named=True):
            per_partner[row[partner_col] if row[partner_col] is not None else "NULL"] = row["n_patients"]

    # Per-year breakdown of earliest DX_DATE
    year_breakdown: dict[str, int] = {}
    if total_hl_records > 0:
        patient_dates = (
            hl_dx
            .filter(pl.col("DX_DATE").is_not_null())
            .join(union_df, on=PATID_COL, how="inner")
            .group_by(PATID_COL)
            .agg(
                pl.col("DX_DATE").min().alias("earliest_dx"),
                pl.col("DX_DATE").max().alias("latest_dx"),
            )
        )
        if patient_dates.height > 0:
            yearly = (
                patient_dates
                .with_columns(pl.col("earliest_dx").dt.year().alias("year"))
                .group_by("year")
                .agg(pl.len().alias("n"))
                .sort("year")
            )
            for row in yearly.iter_rows(named=True):
                yr = row["year"]
                year_breakdown[str(yr) if yr is not None else "NULL"] = row["n"]

    # --- Stage 5: ICD version flag ---
    icd10_prefix = "C81" if dx_format == "dotted" else "C81"
    icd9_prefix = "201"

    icd_version_col = (
        pl.when(pl.col("_DX_MATCH").str.to_uppercase().str.starts_with(icd10_prefix))
        .then(pl.lit("ICD10"))
        .when(pl.col("_DX_MATCH").str.starts_with(icd9_prefix))
        .then(pl.lit("ICD9"))
        .otherwise(pl.lit("UNKNOWN"))
    )

    per_record = hl_dx.with_columns(icd_version_col.alias("icd_version"))

    icd_flags = (
        per_record
        .group_by(PATID_COL)
        .agg(
            pl.col("icd_version").n_unique().alias("version_count"),
            pl.col("icd_version").unique().alias("versions"),
        )
        .with_columns(
            pl.when(pl.col("version_count") > 1)
            .then(pl.lit("BOTH"))
            .when(pl.col("versions").list.first() == "ICD10")
            .then(pl.lit("ICD10_ONLY"))
            .when(pl.col("versions").list.first() == "ICD9")
            .then(pl.lit("ICD9_ONLY"))
            .otherwise(pl.lit("UNKNOWN"))
            .alias("icd_flag")
        )
        .select(PATID_COL, "icd_flag")
    )

    # ICD flags per partner
    icd_by_partner: dict[str, dict[str, int]] = {}
    if partner_col in hl_dx.columns:
        patient_partner = (
            hl_dx.select(PATID_COL, partner_col).unique()
        )
        flagged = icd_flags.join(patient_partner, on=PATID_COL, how="left")
        for row in (
            flagged
            .group_by(partner_col, "icd_flag")
            .agg(pl.len().alias("n"))
            .iter_rows(named=True)
        ):
            p = row[partner_col] if row[partner_col] is not None else "NULL"
            icd_by_partner.setdefault(p, {})[row["icd_flag"]] = row["n"]

    # DX_TYPE mismatches
    dx_type_mismatches = check_dx_type_mismatches(hl_dx)

    return {
        "dx_format": dx_format,
        "total_hl_records": total_hl_records,
        "unique_patients": unique_patients,
        "null_dx_date_records": null_dx_date_records,
        "null_dx_date_patients": null_dx_date_patients,
        "method_a_count": len(method_a_ids),
        "method_b_count": len(method_b_ids),
        "a_only": len(a_only),
        "b_only": len(b_only),
        "intersection": len(both),
        "union": len(union),
        "per_partner": per_partner,
        "year_breakdown": year_breakdown,
        "no_encounterid_match": no_encounterid_match,
        "icd_flags": icd_flags,
        "icd_by_partner": icd_by_partner,
        "dx_type_mismatches": dx_type_mismatches,
        "method_a_ids_df": method_a_df.select(PATID_COL),
        "method_b_ids_df": pl.DataFrame({PATID_COL: list(method_b_ids)}),
        "union_ids_df": union_df,
        "hl_dx": hl_dx,
        "ams_umi_caveat": (
            "AMS and UMI mapped ICD-9→ICD-10 for all diagnoses; "
            "their ICD10_ONLY counts may include originally ICD-9 patients"
        ),
    }


# ---------------------------------------------------------------------------
# 4. Enrollment cross-check
# ---------------------------------------------------------------------------


def enrollment_crosscheck(
    cohort_ids: pl.DataFrame,
    enrollment_path: Path,
    demographic_path: Path,
    partner_col: str = "SOURCE",
) -> dict:
    """Cross-check HL cohort IDs against ENROLLMENT and DEMOGRAPHIC.

    Reports coverage rates, uncovered patients by partner, and
    coverage period summary (ENR_START_DATE → ENR_END_DATE).
    All IDs cast to String.
    """
    cohort = cohort_ids.select(pl.col(PATID_COL).cast(pl.String))

    enr_lf = pl.scan_parquet(enrollment_path).with_columns(
        pl.col(PATID_COL).cast(pl.String)
    )

    with_enr = (
        cohort.lazy()
        .join(enr_lf.select(PATID_COL).unique(), on=PATID_COL, how="inner")
        .collect()
    )

    without_enr = (
        cohort.lazy()
        .join(enr_lf.select(PATID_COL).unique(), on=PATID_COL, how="anti")
        .collect()
    )

    total_hl = cohort.height
    coverage_pct = round(with_enr.height / max(total_hl, 1) * 100, 2)

    # Uncovered patients by partner (join with DEMOGRAPHIC for SOURCE)
    uncovered_by_partner: dict[str, int] = {}
    demo_schema = pl.read_parquet_schema(demographic_path)
    demo_partner_col = partner_col if partner_col in demo_schema else (
        "SITE" if "SITE" in demo_schema else None
    )

    if demo_partner_col and without_enr.height > 0:
        demo_lf = (
            pl.scan_parquet(demographic_path)
            .select(pl.col(PATID_COL).cast(pl.String), demo_partner_col)
        )
        uncov_with_partner = (
            without_enr.lazy()
            .join(demo_lf, on=PATID_COL, how="left")
            .collect()
        )
        for row in (
            uncov_with_partner
            .group_by(demo_partner_col)
            .agg(pl.len().alias("n"))
            .iter_rows(named=True)
        ):
            p = row[demo_partner_col] if row[demo_partner_col] is not None else "NULL"
            uncovered_by_partner[p] = row["n"]

    # Coverage period summary by partner
    coverage_summary_by_partner: dict[str, dict] = {}
    enr_schema = pl.read_parquet_schema(enrollment_path)
    has_dates = "ENR_START_DATE" in enr_schema and "ENR_END_DATE" in enr_schema

    if has_dates and with_enr.height > 0:
        enr_select = [
            pl.col(PATID_COL).cast(pl.String),
            "ENR_START_DATE",
            "ENR_END_DATE",
        ]
        if partner_col in enr_schema:
            enr_select.append(partner_col)
            enr_partner = partner_col
        elif "SITE" in enr_schema:
            enr_select.append("SITE")
            enr_partner = "SITE"
        else:
            enr_partner = None

        enr_data = (
            pl.scan_parquet(enrollment_path)
            .select(enr_select)
            .collect()
        )

        hl_enr = (
            with_enr.lazy()
            .join(enr_data.lazy(), on=PATID_COL, how="inner")
            .collect()
        )

        if enr_partner and enr_partner in hl_enr.columns:
            valid_enr = hl_enr.filter(
                pl.col("ENR_START_DATE").is_not_null()
                & pl.col("ENR_END_DATE").is_not_null()
            )

            if valid_enr.height > 0:
                valid_enr = valid_enr.with_columns(
                    (pl.col("ENR_END_DATE") - pl.col("ENR_START_DATE"))
                    .dt.total_days()
                    .alias("duration_days")
                )
                summary = (
                    valid_enr
                    .group_by(enr_partner)
                    .agg(
                        pl.col("ENR_START_DATE").min().alias("earliest_start"),
                        pl.col("ENR_END_DATE").max().alias("latest_end"),
                        pl.col("duration_days").median().alias("median_duration"),
                    )
                )
                for row in summary.iter_rows(named=True):
                    p = row[enr_partner] if row[enr_partner] is not None else "NULL"
                    coverage_summary_by_partner[p] = {
                        "earliest_start": str(row["earliest_start"]) if row["earliest_start"] else "N/A",
                        "latest_end": str(row["latest_end"]) if row["latest_end"] else "N/A",
                        "median_duration_days": row["median_duration"],
                    }

    return {
        "total_hl": total_hl,
        "with_enrollment": with_enr.height,
        "without_enrollment": without_enr.height,
        "coverage_pct": coverage_pct,
        "uncovered_by_partner": uncovered_by_partner,
        "coverage_summary_by_partner": coverage_summary_by_partner,
    }


# ---------------------------------------------------------------------------
# 5. Cohort summary DataFrame
# ---------------------------------------------------------------------------


def build_cohort_summary_df(
    cohort_result: dict,
    enrollment_result: dict | None = None,
    partner_col: str = "SOURCE",
) -> pl.DataFrame:
    """Assemble per-patient summary DataFrame for CSV output.

    Columns: ID, in_method_a, in_method_b, icd_flag, has_enrollment,
    partner, earliest_dx_date, latest_dx_date, n_hl_dx_records.
    """
    union_df = cohort_result["union_ids_df"]
    method_a_df = cohort_result["method_a_ids_df"]
    method_b_df = cohort_result["method_b_ids_df"]
    icd_flags = cohort_result["icd_flags"]
    hl_dx = cohort_result["hl_dx"]

    base = union_df.clone()

    base = base.join(
        method_a_df.with_columns(pl.lit(True).alias("in_method_a")),
        on=PATID_COL, how="left",
    ).with_columns(pl.col("in_method_a").fill_null(False))

    base = base.join(
        method_b_df.with_columns(pl.lit(True).alias("in_method_b")),
        on=PATID_COL, how="left",
    ).with_columns(pl.col("in_method_b").fill_null(False))

    base = base.join(icd_flags, on=PATID_COL, how="left")

    # Per-patient DX aggregates
    patient_agg = (
        hl_dx
        .group_by(PATID_COL)
        .agg(
            pl.col("DX_DATE").min().alias("earliest_dx_date"),
            pl.col("DX_DATE").max().alias("latest_dx_date"),
            pl.len().alias("n_hl_dx_records"),
        )
    )

    select_partner = []
    if partner_col in hl_dx.columns:
        partner_per_patient = (
            hl_dx
            .group_by(PATID_COL)
            .agg(pl.col(partner_col).first().alias("partner"))
        )
        base = base.join(partner_per_patient, on=PATID_COL, how="left")
        select_partner = ["partner"]

    base = base.join(patient_agg, on=PATID_COL, how="left")

    if enrollment_result is not None:
        enr_ids = set()
        covered_count = enrollment_result.get("with_enrollment", 0)
        total_hl = enrollment_result.get("total_hl", 0)
        base = base.with_columns(pl.lit(False).alias("has_enrollment"))
    else:
        base = base.with_columns(pl.lit(None).cast(pl.Boolean).alias("has_enrollment"))

    out_cols = [
        PATID_COL, "in_method_a", "in_method_b", "icd_flag",
        "has_enrollment",
    ] + select_partner + ["earliest_dx_date", "latest_dx_date", "n_hl_dx_records"]

    available = [c for c in out_cols if c in base.columns]
    return base.select(available)
