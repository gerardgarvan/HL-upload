# HL data loading & cleaning — deduplication & cross-table consistency module
"""Exact-match duplicate flagging with composite keys, cross-table
demographic and temporal consistency checks, and Parquet write-back helper.

Adds binary flag columns (0/1, Int8) to DataFrames.  Dedup uses the
``IS_DUPLICATE`` column; cross-table consistency flags use the ``_con_``
infix naming convention.
"""

from pathlib import Path

import polars as pl

from src.validate.structural import PATID_COL, TUMOR_REGISTRY_TABLES

# ---------------------------------------------------------------------------
# Constants — composite dedup keys per table
# ---------------------------------------------------------------------------

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
    """Remove columns in CLEAN_FLAG_COLS or starting with CLEAN_FLAG_PREFIX."""
    to_drop = [c for c in df.columns if c in CLEAN_FLAG_COLS or c.startswith(CLEAN_FLAG_PREFIX)]
    if to_drop:
        df = df.drop(to_drop)
    return df


# ---------------------------------------------------------------------------
# 2. Composite-key duplicate flagging
# ---------------------------------------------------------------------------


def flag_duplicates(df: pl.DataFrame, table_name: str) -> pl.DataFrame:
    """Mark ALL rows sharing composite key values as IS_DUPLICATE=1.

    Uses ``DataFrame.is_duplicated()`` on a column subset — marks both
    first and subsequent occurrences.  Null keys do NOT match each other
    (null != null), so rows with null key columns are not flagged as
    duplicates of one another.
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
    """Check for patients with multiple BIRTH_DATE or SEX values.

    Returns dict with ``multi_birth_date``, ``multi_sex``, and
    ``total_patients`` keys.  Returns empty dict if DEMOGRAPHIC table
    is unavailable.
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

    Adds ``_con_outside_encounter`` (Int8): 1 when *event_date_col* is
    outside [ADMIT_DATE − 1 day, DISCHARGE_DATE + 1 day].

    Null handling: if ENCOUNTERID, ADMIT_DATE, or *event_date_col* is
    null the flag is 0 (cannot assess).  If DISCHARGE_DATE is null the
    window is treated as open-ended (only the lower bound is checked).
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

    TUMOR_REGISTRY date columns may be strings — parsed using a
    multi-format fallback chain (MM/DD/YYYY, DATE9, YYYYMMDD).

    Returns dict with ``patients_checked``, ``patients_mismatched``,
    ``details``.  Returns empty dict if DEATH table is unavailable.
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
    """Write *df* to Parquet (snappy) and return Phase 5 flag statistics.

    Counts columns matching CLEAN_FLAG_COLS or the CLEAN_FLAG_PREFIX and
    sums flagged rows for each.
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
