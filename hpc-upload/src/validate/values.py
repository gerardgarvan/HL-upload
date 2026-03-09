# HL data loading & cleaning — value & temporal validation module
"""Value set conformance, vital/lab plausibility, ICD concordance,
temporal consistency, tumor registry validation, and write-back helpers.

Adds binary flag columns (0/1, Int8) to DataFrames. Flag columns use
the ``_val_`` infix naming convention for downstream identification.
"""

from datetime import date
from pathlib import Path

import polars as pl

from src.validate.structural import PATID_COL, SMALL_CELL_THRESHOLD

# ---------------------------------------------------------------------------
# Constants — vital sign plausibility ranges
# ---------------------------------------------------------------------------

VITAL_RANGES: dict[str, tuple[float, float]] = {
    "HT": (50.0, 272.0),
    "WT": (1.0, 500.0),
    "SYSTOLIC": (40.0, 300.0),
    "DIASTOLIC": (20.0, 200.0),
    "ORIGINAL_BMI": (8.0, 100.0),
}

# ---------------------------------------------------------------------------
# Constants — HL-relevant lab plausibility ranges (wide biological)
# ---------------------------------------------------------------------------

HL_LAB_RANGES: dict[str, dict] = {
    "6690-2":  {"name": "WBC",              "min": 0, "max": 500,   "unit": "10*3/uL"},
    "26464-8": {"name": "WBC alt",          "min": 0, "max": 500,   "unit": "10*3/uL"},
    "718-7":   {"name": "Hemoglobin",       "min": 0, "max": 30,    "unit": "g/dL"},
    "30313-1": {"name": "Hgb alt",          "min": 0, "max": 30,    "unit": "g/dL"},
    "777-3":   {"name": "Platelets",        "min": 0, "max": 5000,  "unit": "10*3/uL"},
    "26515-7": {"name": "Plt alt",          "min": 0, "max": 5000,  "unit": "10*3/uL"},
    "4544-3":  {"name": "Hematocrit",       "min": 0, "max": 75,    "unit": "%"},
    "787-2":   {"name": "MCV",              "min": 0, "max": 200,   "unit": "fL"},
    "30428-7": {"name": "MCV alt",          "min": 0, "max": 200,   "unit": "fL"},
    "1742-6":  {"name": "ALT",              "min": 0, "max": 50000, "unit": "U/L"},
    "1920-8":  {"name": "AST",              "min": 0, "max": 50000, "unit": "U/L"},
    "6768-6":  {"name": "ALP",              "min": 0, "max": 10000, "unit": "U/L"},
    "1975-2":  {"name": "Bilirubin total",  "min": 0, "max": 100,   "unit": "mg/dL"},
    "1751-7":  {"name": "Albumin",          "min": 0, "max": 15,    "unit": "g/dL"},
    "1968-7":  {"name": "Direct bilirubin", "min": 0, "max": 100,   "unit": "mg/dL"},
    "2324-2":  {"name": "GGT",              "min": 0, "max": 10000, "unit": "U/L"},
    "11580-8": {"name": "TSH",              "min": 0, "max": 500,   "unit": "mIU/L"},
    "3016-3":  {"name": "TSH alt",          "min": 0, "max": 500,   "unit": "mIU/L"},
    "4537-7":  {"name": "ESR",              "min": 0, "max": 200,   "unit": "mm/hr"},
    "1988-5":  {"name": "CRP",              "min": 0, "max": 500,   "unit": "mg/L"},
}

# ---------------------------------------------------------------------------
# Constants — temporal / ICD / PCORnet
# ---------------------------------------------------------------------------

FUTURE_DATE_CUTOFF = date(2025, 12, 31)

MASKED_BIRTH_DATE = date(1900, 1, 1)

ICD10_TRANSITION = date(2015, 10, 1)
GRACE_START = date(2015, 7, 1)
GRACE_END = date(2016, 1, 1)

ALWAYS_VALID_CODES: set[str] = {"NI", "UN", "OT"}

# ---------------------------------------------------------------------------
# Constants — tumor registry / HL-specific
# ---------------------------------------------------------------------------

HL_HISTOLOGY_CODES: set[int] = set(range(9650, 9668))

VALID_AJCC_STAGES: set[str] = {
    "I", "IA", "IB",
    "II", "IIA", "IIB",
    "III", "IIIA", "IIIB",
    "IV", "IVA", "IVB",
    "UNK", "88", "99",
}

_B_SYMPTOM_VALID: set[str] = {"A", "B", "1", "2", "9", "8", ""}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _ensure_float(df: pl.DataFrame, col: str) -> pl.DataFrame:
    """Cast *col* to Float64 if it is stored as String (Pitfall 1)."""
    if col in df.columns and df.schema[col] in (pl.String, pl.Utf8):
        df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))
    return df


# ---------------------------------------------------------------------------
# 1. Value-set lookup builder
# ---------------------------------------------------------------------------


def build_valueset_lookup(
    valuesets_path: Path,
) -> dict[tuple[str, str], set[str]]:
    """Build {(TABLE_NAME, FIELD_NAME): {valid_values}} from valuesets.csv."""
    vs = pl.read_csv(valuesets_path, encoding="utf8-lossy")
    lookup: dict[tuple[str, str], set[str]] = {}
    for row in vs.iter_rows(named=True):
        key = (row["TABLE_NAME"], row["FIELD_NAME"])
        lookup.setdefault(key, set()).add(row["VALUESET_ITEM"])
    return lookup


# ---------------------------------------------------------------------------
# 2. Coded-field validation against value sets
# ---------------------------------------------------------------------------


def validate_coded_fields(
    df: pl.DataFrame,
    table_name: str,
    lookup: dict[tuple[str, str], set[str]],
) -> pl.DataFrame:
    """Add ``{COL}_val_code`` flag for each coded field with invalid values.

    Flag = 1 when value is non-null, non-empty, and not in value set.
    NI/UN/OT are always valid (PCORnet missing-value codes).
    Skips fields with >200 valid values to avoid false positives on
    loosely-coded columns.
    """
    for col in df.columns:
        key = (table_name, col)
        if key not in lookup:
            continue
        valid_set = lookup[key]
        if len(valid_set) > 200:
            continue
        valid = valid_set | ALWAYS_VALID_CODES
        flag_col = f"{col}_val_code"
        df = df.with_columns(
            pl.when(
                pl.col(col).is_null()
                | (pl.col(col) == "")
                | pl.col(col).is_in(valid)
            )
            .then(pl.lit(0))
            .otherwise(pl.lit(1))
            .cast(pl.Int8)
            .alias(flag_col)
        )
    return df


# ---------------------------------------------------------------------------
# 3. Vital-sign plausibility
# ---------------------------------------------------------------------------


def validate_vital_plausibility(df: pl.DataFrame) -> pl.DataFrame:
    """Add ``{COL}_val_range`` flag for implausible vital-sign values."""
    for col, (lo, hi) in VITAL_RANGES.items():
        if col not in df.columns:
            continue
        df = _ensure_float(df, col)
        flag_col = f"{col}_val_range"
        df = df.with_columns(
            pl.when(
                pl.col(col).is_null()
                | (pl.col(col).ge(lo) & pl.col(col).le(hi))
            )
            .then(pl.lit(0))
            .otherwise(pl.lit(1))
            .cast(pl.Int8)
            .alias(flag_col)
        )
    return df


# ---------------------------------------------------------------------------
# 4. Lab-result plausibility (wide biological ranges)
# ---------------------------------------------------------------------------


def validate_lab_plausibility(df: pl.DataFrame) -> pl.DataFrame:
    """Add ``RESULT_NUM_val_range`` and ``RESULT_UNIT_val_missing`` flags.

    Range checks fire only when LAB_LOINC matches a known code.
    Missing RESULT_UNIT is flagged separately per locked decision.
    """
    if "LAB_LOINC" not in df.columns or "RESULT_NUM" not in df.columns:
        return df

    df = _ensure_float(df, "RESULT_NUM")

    # Flag missing RESULT_UNIT on rows with a numeric result
    if "RESULT_UNIT" in df.columns:
        df = df.with_columns(
            pl.when(
                pl.col("RESULT_NUM").is_not_null()
                & (
                    pl.col("RESULT_UNIT").is_null()
                    | (pl.col("RESULT_UNIT") == "")
                )
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias("RESULT_UNIT_val_missing")
        )

    # Chained range check across all LOINC codes
    range_flag: pl.Expr = pl.lit(0).cast(pl.Int8)
    for loinc, info in HL_LAB_RANGES.items():
        range_flag = (
            pl.when(
                pl.col("LAB_LOINC").eq(loinc)
                & pl.col("RESULT_NUM").is_not_null()
                & (
                    pl.col("RESULT_NUM").lt(info["min"])
                    | pl.col("RESULT_NUM").gt(info["max"])
                )
            )
            .then(pl.lit(1).cast(pl.Int8))
            .otherwise(range_flag)
        )

    df = df.with_columns(range_flag.alias("RESULT_NUM_val_range"))
    return df


# ---------------------------------------------------------------------------
# 5. Mapped-partner auto-detection (ICD-9 → ICD-10)
# ---------------------------------------------------------------------------


def detect_mapped_partners(
    df: pl.DataFrame,
    partner_col: str = "SOURCE",
) -> set[str]:
    """Auto-detect partners that retrospectively mapped ICD-9 to ICD-10.

    Partners with >95 % ICD-10 codes in pre-Oct-2015 data are flagged as
    mappers.  AMS and UMI are always included (known mappers).
    """
    known: set[str] = {"AMS", "UMI"}
    if partner_col not in df.columns or "DX_DATE" not in df.columns:
        return known

    pre = df.filter(
        pl.col("DX_DATE").is_not_null() & (pl.col("DX_DATE") < ICD10_TRANSITION)
    )
    if pre.is_empty():
        return known

    is_icd10 = pl.col("DX").str.to_uppercase().str.contains(r"^[A-Z]")

    partner_stats = (
        pre
        .with_columns(is_icd10.alias("_is_icd10"))
        .group_by(partner_col)
        .agg(
            pl.len().alias("total"),
            pl.col("_is_icd10").sum().alias("icd10_count"),
        )
        .with_columns(
            (pl.col("icd10_count") / pl.col("total")).alias("icd10_pct")
        )
        .filter(pl.col("icd10_pct") > 0.95)
    )

    detected = set(partner_stats[partner_col].to_list())
    return detected | known


# ---------------------------------------------------------------------------
# 6. ICD version-date concordance
# ---------------------------------------------------------------------------


def validate_icd_concordance(
    df: pl.DataFrame,
    mapped_partners: set[str],
    partner_col: str = "SOURCE",
) -> pl.DataFrame:
    """Add ``DX_val_icd_concordance`` flag for ICD version-date mismatches.

    Rules:
    - Null DX_DATE → 0  (cannot assess)
    - Grace period (Jul 2015 – Jan 2016) → 0
    - ICD-9 after grace period → 1
    - ICD-10 before grace period AND not a mapped partner → 1
    - Otherwise → 0
    """
    if "DX" not in df.columns or "DX_DATE" not in df.columns:
        return df

    is_icd10 = pl.col("DX").str.to_uppercase().str.contains(r"^[A-Z]")

    in_grace = pl.col("DX_DATE").ge(GRACE_START) & pl.col("DX_DATE").lt(GRACE_END)

    is_mapped = (
        pl.col(partner_col).is_in(mapped_partners)
        if partner_col in df.columns and mapped_partners
        else pl.lit(False)
    )

    flag = (
        pl.when(pl.col("DX_DATE").is_null()).then(pl.lit(0))
        .when(in_grace).then(pl.lit(0))
        .when(~is_icd10 & pl.col("DX_DATE").ge(GRACE_END)).then(pl.lit(1))
        .when(is_icd10 & pl.col("DX_DATE").lt(GRACE_START) & ~is_mapped).then(pl.lit(1))
        .otherwise(pl.lit(0))
    )

    df = df.with_columns(flag.cast(pl.Int8).alias("DX_val_icd_concordance"))
    return df


# ---------------------------------------------------------------------------
# 7. Encounter temporal validation (admit / discharge)
# ---------------------------------------------------------------------------


def validate_temporal_encounter(df: pl.DataFrame) -> pl.DataFrame:
    """Add admit/discharge ordering and same-day flags.

    ``_val_admit_discharge`` = 1 when DISCHARGE_DATE < ADMIT_DATE.
    ``_val_same_day``        = 1 when both dates equal.
    """
    if "ADMIT_DATE" not in df.columns or "DISCHARGE_DATE" not in df.columns:
        return df

    df = df.with_columns(
        pl.when(
            pl.col("ADMIT_DATE").is_not_null()
            & pl.col("DISCHARGE_DATE").is_not_null()
            & (pl.col("DISCHARGE_DATE") < pl.col("ADMIT_DATE"))
        )
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .cast(pl.Int8)
        .alias("_val_admit_discharge")
    )

    df = df.with_columns(
        pl.when(
            pl.col("ADMIT_DATE").is_not_null()
            & pl.col("DISCHARGE_DATE").is_not_null()
            & (pl.col("ADMIT_DATE") == pl.col("DISCHARGE_DATE"))
        )
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .cast(pl.Int8)
        .alias("_val_same_day")
    )
    return df


# ---------------------------------------------------------------------------
# 8. Future-date validation (all tables)
# ---------------------------------------------------------------------------


def validate_future_dates(
    df: pl.DataFrame,
    cutoff: date | None = None,
) -> pl.DataFrame:
    """Add ``{COL}_val_future`` flag for dates beyond the cutoff.

    Checks every Date / Datetime column in *df*.
    """
    cutoff = cutoff or FUTURE_DATE_CUTOFF
    for col in df.columns:
        dtype = df.schema[col]
        if dtype == pl.Date:
            df = df.with_columns(
                pl.when(
                    pl.col(col).is_not_null() & (pl.col(col) > cutoff)
                )
                .then(pl.lit(1))
                .otherwise(pl.lit(0))
                .cast(pl.Int8)
                .alias(f"{col}_val_future")
            )
        elif dtype == pl.Datetime or (isinstance(dtype, pl.Datetime)):
            df = df.with_columns(
                pl.when(
                    pl.col(col).is_not_null()
                    & (pl.col(col).cast(pl.Date) > cutoff)
                )
                .then(pl.lit(1))
                .otherwise(pl.lit(0))
                .cast(pl.Int8)
                .alias(f"{col}_val_future")
            )
    return df


# ---------------------------------------------------------------------------
# 9. Enrollment date ordering
# ---------------------------------------------------------------------------


def validate_enrollment_dates(df: pl.DataFrame) -> pl.DataFrame:
    """Add ``_val_enr_dates`` flag when ENR_START_DATE > ENR_END_DATE."""
    if "ENR_START_DATE" not in df.columns or "ENR_END_DATE" not in df.columns:
        return df

    df = df.with_columns(
        pl.when(
            pl.col("ENR_START_DATE").is_not_null()
            & pl.col("ENR_END_DATE").is_not_null()
            & (pl.col("ENR_START_DATE") > pl.col("ENR_END_DATE"))
        )
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .cast(pl.Int8)
        .alias("_val_enr_dates")
    )
    return df


# ---------------------------------------------------------------------------
# 10. Tumor registry HL-specific validation
# ---------------------------------------------------------------------------


def validate_tumor_registry(df: pl.DataFrame) -> pl.DataFrame:
    """Add HL-specific tumor registry flags.

    Checks histology codes, AJCC staging format, B-symptom coding,
    age at diagnosis range, treatment-before-diagnosis timing, and
    primary site lymph-node concordance.
    """
    # --- Histology ---
    if "HISTOLOGY" in df.columns:
        df = _ensure_float(df, "HISTOLOGY")
        df = df.with_columns(
            pl.col("HISTOLOGY").cast(pl.Int64, strict=False).alias("_hist_int")
        )
        df = df.with_columns(
            pl.when(
                pl.col("_hist_int").is_not_null()
                & ~pl.col("_hist_int").is_in(HL_HISTOLOGY_CODES)
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias("HISTOLOGY_val_hl")
        )
        df = df.drop("_hist_int")

    # --- AJCC staging ---
    if "STAGE_GROUP" in df.columns:
        df = df.with_columns(
            pl.when(
                pl.col("STAGE_GROUP").is_not_null()
                & (pl.col("STAGE_GROUP") != "")
                & ~pl.col("STAGE_GROUP").str.to_uppercase().is_in(VALID_AJCC_STAGES)
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias("STAGE_GROUP_val_format")
        )

    # --- B-symptoms (probe B_SYMPTOMS first, then CS_SSF1) ---
    b_col = None
    if "B_SYMPTOMS" in df.columns:
        b_col = "B_SYMPTOMS"
    elif "CS_SSF1" in df.columns:
        b_col = "CS_SSF1"

    if b_col is not None:
        df = df.with_columns(
            pl.when(
                pl.col(b_col).is_not_null()
                & (pl.col(b_col) != "")
                & ~pl.col(b_col).str.to_uppercase().is_in(
                    {v.upper() for v in _B_SYMPTOM_VALID}
                )
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias(f"{b_col}_val_code")
        )

    # --- Age at diagnosis ---
    if "AGE_AT_DIAGNOSIS" in df.columns:
        df = _ensure_float(df, "AGE_AT_DIAGNOSIS")
        df = df.with_columns(
            pl.when(
                pl.col("AGE_AT_DIAGNOSIS").is_not_null()
                & (
                    (pl.col("AGE_AT_DIAGNOSIS") < 0)
                    | (
                        (pl.col("AGE_AT_DIAGNOSIS") > 120)
                        & (pl.col("AGE_AT_DIAGNOSIS") != 200)
                    )
                )
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias("AGE_AT_DIAGNOSIS_val_range")
        )

    # --- Treatment timing vs DATE_OF_DIAGNOSIS ---
    if "DATE_OF_DIAGNOSIS" in df.columns:
        tx_cols = [
            "DT_SURG", "DT_RAD", "DT_CHEMO",
            "CHEMO_START_DATE_SUMMARY",
            "MOST_DEFINITIVE_SURGERY_DATE",
            "IMMUNO_START_DATE",
            "HORMONE_START_DATE",
        ]
        for tx_col in tx_cols:
            if tx_col not in df.columns:
                continue
            df = df.with_columns(
                pl.when(
                    pl.col("DATE_OF_DIAGNOSIS").is_not_null()
                    & pl.col(tx_col).is_not_null()
                    & (pl.col(tx_col) < pl.col("DATE_OF_DIAGNOSIS"))
                )
                .then(pl.lit(1))
                .otherwise(pl.lit(0))
                .cast(pl.Int8)
                .alias(f"{tx_col}_val_before_dx")
            )

    # --- Primary site (lymph node check) ---
    if "PRIMARY_SITE" in df.columns:
        df = df.with_columns(
            pl.when(
                pl.col("PRIMARY_SITE").is_not_null()
                & ~pl.col("PRIMARY_SITE").str.to_uppercase().str.contains(r"^C77[0-9]$")
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias("PRIMARY_SITE_val_hl")
        )

    return df


# ---------------------------------------------------------------------------
# 11. Drop existing flag columns (idempotent re-runs)
# ---------------------------------------------------------------------------


def drop_existing_flags(df: pl.DataFrame) -> pl.DataFrame:
    """Remove any existing ``_val_`` flag columns for idempotent re-runs."""
    flag_cols = [c for c in df.columns if "_val_" in c]
    if flag_cols:
        df = df.drop(flag_cols)
    return df


# ---------------------------------------------------------------------------
# 12. Write validated DataFrame back to Parquet
# ---------------------------------------------------------------------------


def write_validated(df: pl.DataFrame, parquet_path: Path) -> dict:
    """Write *df* (with flag columns) back to Parquet and return flag stats.

    Uses snappy compression for consistency with Phase 2.
    """
    flag_cols = [c for c in df.columns if "_val_" in c]
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
