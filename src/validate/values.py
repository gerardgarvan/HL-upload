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
    vs = pl.read_csv(valuesets_path)
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
