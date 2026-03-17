"""Phase 5: Cleaning — deduplication and cross-table consistency checks.

Flags exact-match duplicates using composite keys and validates consistency across
related tables (demographics, temporal windows, death dates). All flags are binary
Int8 columns (0/1) added to DataFrames.

**Pipeline position:** Phase 5 (Cleaning)
**Input:** Raw Parquet tables from Phase 4 (Loading)
**Output:** DataFrames with IS_DUPLICATE and _con_* flag columns
**Orchestrated by:** scripts/clean_all.py

**Key functions:**
- flag_duplicates: Composite-key duplicate detection
- check_demographic_consistency: Multi-birth-date and multi-sex detection
- flag_events_outside_encounters: Temporal window validation
- check_death_consistency: Cross-table death date comparison
- write_cleaned: Parquet write with flag statistics
"""

from pathlib import Path

import polars as pl

from src.validate.structural import PATID_COL, TUMOR_REGISTRY_TABLES

# ---------------------------------------------------------------------------
# Constants — composite dedup keys per table
# ---------------------------------------------------------------------------

# Composite keys for duplicate detection: columns that together uniquely identify a record.
# Rationale: Clinical events are identified by patient + date + clinical code/type. Using
# composite keys (rather than single IDs) detects true semantic duplicates where the same
# event appears multiple times.
#
# Key selection logic:
# - DIAGNOSIS: Patient + date + code (DX_DATE + DX) — same diagnosis on same date is duplicate
# - PROCEDURES: Patient + date + code (PX_DATE + PX) — same procedure on same date is duplicate
# - LAB_RESULT_CM: Patient + date + test (SPECIMEN_DATE + LAB_LOINC) — same lab on same date
# - ENCOUNTER: Patient + date + type + facility (ADMIT_DATE + ENC_TYPE + FACILITYID) — encounter uniqueness
# - VITAL: Patient + date only (MEASURE_DATE) — multiple vitals same day considered duplicates
# - PRESCRIBING: Patient + date + drug (RX_ORDER_DATE + RXNORM_CUI) — same prescription on same date
#
# TODO(audit): VITAL uses only MEASURE_DATE without vital type (HT/WT/BP/etc) — may flag
# legitimate multiple measurements on same day as duplicates. Consider adding VITAL_SOURCE or
# measurement type if available.
DEDUP_KEYS: dict[str, list[str]] = {
    "DIAGNOSIS": ["ID", "DX_DATE", "DX"],
    "PROCEDURES": ["ID", "PX_DATE", "PX"],
    "LAB_RESULT_CM": ["ID", "SPECIMEN_DATE", "LAB_LOINC"],
    "ENCOUNTER": ["ID", "ADMIT_DATE", "ENC_TYPE", "FACILITYID"],
    "VITAL": ["ID", "MEASURE_DATE"],
    "PRESCRIBING": ["ID", "RX_ORDER_DATE", "RXNORM_CUI"],
}

# ---------------------------------------------------------------------------
# Constants — event date columns per table
# ---------------------------------------------------------------------------

EVENT_DATE_COLS: dict[str, str] = {
    "DIAGNOSIS": "DX_DATE",
    "PROCEDURES": "PX_DATE",
    "LAB_RESULT_CM": "SPECIMEN_DATE",
    "VITAL": "MEASURE_DATE",
    "PRESCRIBING": "RX_ORDER_DATE",
    "CONDITION": "ONSET_DATE",
    "MED_ADMIN": "MEDADMIN_START_DATE",
    "IMMUNIZATION": "VX_ADMIN_DATE",
    "OBS_CLIN": "OBSCLIN_START_DATE",
    "OBS_GEN": "OBSGEN_START_DATE",
}

# ---------------------------------------------------------------------------
# Constants — Phase 5 clean-flag identifiers
# ---------------------------------------------------------------------------

CLEAN_FLAG_COLS: set[str] = {
    "IS_DUPLICATE",
    "ICD_MAPPED",
    "CLAIMS_ONLY",
    "DEATH_ONLY",
    "FLAG_HL_DX",
    "FLAG_SURVIVORSHIP_DX",
    "FLAG_CANCER_PROVIDER",
}

CLEAN_FLAG_PREFIX: str = "_con_"


# ---------------------------------------------------------------------------
# 1. Drop existing Phase 5 flags (idempotent re-runs)
# ---------------------------------------------------------------------------


def drop_existing_clean_flags(df: pl.DataFrame) -> pl.DataFrame:
    """Remove Phase 5 flag columns from DataFrame for idempotent re-runs.

    Scans column names and drops any matching CLEAN_FLAG_COLS (IS_DUPLICATE, ICD_MAPPED,
    FLAG_HL_DX, etc.) or starting with CLEAN_FLAG_PREFIX ("_con_"). This allows cleaning
    scripts to be re-run without accumulating duplicate flag columns.

    Clinical rationale: Pipeline re-runs require clean state — old flags must be removed
    before reapplying logic to ensure correctness.

    Args:
        df: Input DataFrame potentially containing old flag columns.

    Returns:
        DataFrame with all Phase 5 flag columns removed.
    """
    to_drop = [c for c in df.columns if c in CLEAN_FLAG_COLS or c.startswith(CLEAN_FLAG_PREFIX)]
    if to_drop:
        df = df.drop(to_drop)
    return df


# ---------------------------------------------------------------------------
# 2. Composite-key duplicate flagging
# ---------------------------------------------------------------------------


def flag_duplicates(df: pl.DataFrame, table_name: str) -> pl.DataFrame:
    """Mark ALL rows sharing composite key values as IS_DUPLICATE=1.

    Detects exact-match duplicates using table-specific composite keys from DEDUP_KEYS.
    Marks ALL occurrences (both first and subsequent rows) as IS_DUPLICATE=1. Uses Polars
    is_duplicated() on key column subset.

    **Null behavior:** Rows with null key columns are NOT flagged as duplicates of each
    other (Polars treats null != null). This is correct behavior — null date/code values
    represent unknowns, not semantic matches.

    Clinical rationale: Duplicate clinical events (same patient, date, code) indicate
    data quality issues or multi-system redundancy that must be identified before analysis.

    Args:
        df: Input DataFrame for a PCORnet table.
        table_name: PCORnet table name (e.g., "DIAGNOSIS", "PROCEDURES").

    Returns:
        DataFrame with IS_DUPLICATE column added (Int8: 1 if duplicate, 0 otherwise).
        Returns df unchanged if table_name not in DEDUP_KEYS or < 2 keys available.
    """
    keys = DEDUP_KEYS.get(table_name)
    if not keys:
        return df
    available_keys = [k for k in keys if k in df.columns]
    if len(available_keys) < 2:
        return df
    mask = df.select(available_keys).is_duplicated()
    df = df.with_columns(mask.cast(pl.Int8).alias("IS_DUPLICATE"))
    return df


# ---------------------------------------------------------------------------
# 3. Demographic consistency (multi-birth-date / multi-sex)
# ---------------------------------------------------------------------------


def check_demographic_consistency(table_map: dict[str, Path]) -> dict:
    """Check for patients with multiple BIRTH_DATE or SEX values across DEMOGRAPHIC rows.

    Scans DEMOGRAPHIC table and identifies patients with inconsistent demographics. In
    well-formed data, each patient should have a single birth date and sex value. Multiple
    values indicate data quality issues (system integration problems, data entry errors).

    Clinical rationale: Demographics are foundational attributes — inconsistency undermines
    all downstream analysis (age calculations, sex-specific cohorts).

    Args:
        table_map: Dict mapping table names to Parquet file paths.

    Returns:
        Dict with keys:
        - "multi_birth_date": List of patient IDs with >1 BIRTH_DATE value
        - "multi_sex": List of patient IDs with >1 SEX value
        - "total_patients": Total unique patients in DEMOGRAPHIC
        Returns empty dict if DEMOGRAPHIC table unavailable or missing.
    """
    if "DEMOGRAPHIC" not in table_map:
        return {}
    demo_path = table_map["DEMOGRAPHIC"]
    if not demo_path.exists():
        return {}

    demo = pl.read_parquet(demo_path)
    id_col = PATID_COL
    demo = demo.with_columns(pl.col(id_col).cast(pl.String))

    total_patients = demo[id_col].n_unique()

    multi_birth = demo.group_by(id_col).agg(pl.col("BIRTH_DATE").n_unique().alias("n")).filter(pl.col("n") > 1)

    multi_sex = demo.group_by(id_col).agg(pl.col("SEX").n_unique().alias("n")).filter(pl.col("n") > 1)

    return {
        "multi_birth_date": multi_birth[id_col].to_list(),
        "multi_sex": multi_sex[id_col].to_list(),
        "total_patients": total_patients,
    }


# ---------------------------------------------------------------------------
# 4. Events outside encounter windows (±1 day tolerance)
# ---------------------------------------------------------------------------


def flag_events_outside_encounters(
    event_df: pl.DataFrame,
    encounter_df: pl.DataFrame,
    event_date_col: str,
) -> pl.DataFrame:
    """Flag event rows whose date falls outside the linked encounter window.

    Clinical events (diagnoses, procedures, labs) should occur within their linked
    encounter's temporal window. Events outside the window indicate data quality issues
    (incorrect ENCOUNTERID linkage, date entry errors, or encounter record gaps).

    **Validation window:** [ADMIT_DATE - 1 day, DISCHARGE_DATE + 1 day]. The ±1 day
    tolerance accommodates timestamp rounding and pre-admission/post-discharge services.

    **Null handling:**
    - If ENCOUNTERID, ADMIT_DATE, or event_date_col is null: flag = 0 (cannot assess)
    - If DISCHARGE_DATE is null: window is open-ended (only lower bound checked)

    Clinical rationale: Temporal consistency between events and encounters is essential
    for accurate clinical timelines and encounter-level aggregation.

    Uses lazy evaluation to manage memory during the many-to-many join.

    Args:
        event_df: Event DataFrame (DIAGNOSIS, PROCEDURES, etc.) with ENCOUNTERID.
        encounter_df: ENCOUNTER DataFrame with ADMIT_DATE, DISCHARGE_DATE.
        event_date_col: Name of date column in event_df (e.g., "DX_DATE", "PX_DATE").

    Returns:
        event_df with _con_outside_encounter column added (Int8: 1 if outside, 0 otherwise).
        Returns event_df unchanged if ENCOUNTERID column absent.
    """
    if "ENCOUNTERID" not in event_df.columns:
        return event_df

    enc = encounter_df.select(
        pl.col("ENCOUNTERID").cast(pl.String),
        "ADMIT_DATE",
        "DISCHARGE_DATE",
    )

    result = (
        event_df.lazy()
        .with_columns(pl.col("ENCOUNTERID").cast(pl.String))
        .join(enc.lazy(), on="ENCOUNTERID", how="left")
        .with_columns(
            pl.when(pl.col("ENCOUNTERID").is_null() | pl.col("ADMIT_DATE").is_null() | pl.col(event_date_col).is_null())
            .then(pl.lit(0))
            .when(
                (pl.col(event_date_col) >= (pl.col("ADMIT_DATE") - pl.duration(days=1)))
                & (pl.col("DISCHARGE_DATE").is_null() | (pl.col(event_date_col) <= (pl.col("DISCHARGE_DATE") + pl.duration(days=1))))
            )
            .then(pl.lit(0))
            .otherwise(pl.lit(1))
            .cast(pl.Int8)
            .alias("_con_outside_encounter")
        )
        .drop(["ADMIT_DATE", "DISCHARGE_DATE"])
        .collect()
    )
    return result


# ---------------------------------------------------------------------------
# 5. Death date consistency across DEATH and TUMOR_REGISTRY tables
# ---------------------------------------------------------------------------


def check_death_consistency(table_map: dict[str, Path]) -> dict:
    """Compare DEATH_DATE between DEATH table and TUMOR_REGISTRY tables.

    Death dates should be consistent across tables. Mismatches indicate data quality issues
    (source system discrepancies, date format errors, incomplete updates). TUMOR_REGISTRY
    tables may contain DATE_OF_DEATH, DATE_OF_LAST_CONTACT, or DEATH_DATE columns.

    **Date parsing:** TUMOR_REGISTRY date columns may be strings in multiple formats.
    Applies fallback chain: MM/DD/YYYY → DD-Mon-YYYY (DATE9) → YYYYMMDD. This handles
    mixed-format columns common in cancer registry data.

    Clinical rationale: Death date accuracy is critical for survival analysis and ensures
    post-death events are properly identified.

    Args:
        table_map: Dict mapping table names to Parquet file paths.

    Returns:
        Dict with keys:
        - "patients_checked": Total patients with death dates compared
        - "patients_mismatched": Patients with inconsistent death dates
        - "details": List of per-table comparison results (dict per TUMOR_REGISTRY table)
        Returns empty dict if DEATH table unavailable.
    """
    if "DEATH" not in table_map or not table_map["DEATH"].exists():
        return {}

    death = pl.read_parquet(
        table_map["DEATH"],
        columns=[PATID_COL, "DEATH_DATE"],
    )
    death = death.with_columns(pl.col(PATID_COL).cast(pl.String))

    tr_date_candidates = [
        "DATE_OF_LAST_CONTACT",
        "DEATH_DATE",
        "DATE_OF_DEATH",
    ]

    details: list[dict] = []
    total_checked = 0
    total_mismatched = 0

    for tr_name in TUMOR_REGISTRY_TABLES:
        if tr_name not in table_map or not table_map[tr_name].exists():
            continue

        tr = pl.read_parquet(table_map[tr_name])
        tr = tr.with_columns(pl.col(PATID_COL).cast(pl.String))

        tr_date_col = None
        for candidate in tr_date_candidates:
            if candidate in tr.columns:
                tr_date_col = candidate
                break
        if tr_date_col is None:
            continue

        # Parse TR date column — may be String in various formats
        if tr.schema[tr_date_col] in (pl.String, pl.Utf8):
            tr = tr.with_columns(
                pl.col(tr_date_col)
                .str.to_date("%m/%d/%Y", strict=False)
                .fill_null(pl.col(tr_date_col).str.to_date("%d%b%Y", strict=False))
                .fill_null(pl.col(tr_date_col).str.to_date("%Y%m%d", strict=False))
                .alias(tr_date_col)
            )

        tr_subset = tr.select(
            pl.col(PATID_COL),
            pl.col(tr_date_col).alias("_tr_death_date"),
        )

        merged = death.join(tr_subset, on=PATID_COL, how="inner")
        if merged.is_empty():
            continue

        merged = merged.filter(pl.col("DEATH_DATE").is_not_null() & pl.col("_tr_death_date").is_not_null())

        # Cast both sides to Date for comparison
        for c in ("DEATH_DATE", "_tr_death_date"):
            if merged.schema[c] != pl.Date:
                merged = merged.with_columns(pl.col(c).cast(pl.Date, strict=False))

        mismatched = merged.filter(pl.col("DEATH_DATE") != pl.col("_tr_death_date"))

        total_checked += merged.height
        total_mismatched += mismatched.height
        details.append(
            {
                "tr_table": tr_name,
                "tr_date_col": tr_date_col,
                "patients_checked": merged.height,
                "patients_mismatched": mismatched.height,
            }
        )

    return {
        "patients_checked": total_checked,
        "patients_mismatched": total_mismatched,
        "details": details,
    }


# ---------------------------------------------------------------------------
# 6. Write cleaned DataFrame to Parquet with flag stats
# ---------------------------------------------------------------------------


def write_cleaned(df: pl.DataFrame, parquet_path: Path) -> dict:
    """Write DataFrame to Parquet with snappy compression and return flag statistics.

    Writes cleaned DataFrame to disk and calculates summary statistics for all Phase 5
    flag columns (IS_DUPLICATE, _con_*, FLAG_*, ICD_MAPPED, etc.). Statistics support
    data quality reporting and validation.

    Clinical rationale: Flag statistics document data quality issues discovered during
    cleaning and provide audit trail for downstream analysis decisions.

    Args:
        df: Cleaned DataFrame with flag columns added.
        parquet_path: Output path for Parquet file.

    Returns:
        Dict with keys:
        - "path": Output file path (string)
        - "total_rows": Total rows in DataFrame
        - "flag_columns_added": Count of flag columns
        - "flags": Dict mapping flag column name to count of flagged rows (1s)
    """
    flag_cols = [c for c in df.columns if c in CLEAN_FLAG_COLS or c.startswith(CLEAN_FLAG_PREFIX)]

    stats: dict = {
        "path": str(parquet_path),
        "total_rows": df.height,
        "flag_columns_added": len(flag_cols),
        "flags": {},
    }
    for fc in flag_cols:
        flagged = df[fc].sum()
        stats["flags"][fc] = int(flagged) if flagged is not None else 0

    df.write_parquet(parquet_path, compression="snappy")
    return stats
