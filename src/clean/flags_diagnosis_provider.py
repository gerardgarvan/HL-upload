"""Phase 5: Cleaning — diagnosis and provider flags for cohort identification.

Adds binary Int8 flags to DIAGNOSIS (FLAG_HL_DX, FLAG_SURVIVORSHIP_DX) and PROVIDER
(FLAG_CANCER_PROVIDER) tables. These flags support cohort selection, survivorship
analysis, and cancer provider identification.

**Pipeline position:** Phase 5 (Cleaning)
**Input:** Raw DIAGNOSIS and PROVIDER Parquet tables
**Output:** Tables with FLAG_HL_DX, FLAG_SURVIVORSHIP_DX, FLAG_CANCER_PROVIDER columns
**Orchestrated by:** scripts/clean_all.py

**Key functions:**
- add_diagnosis_flags: HL and survivorship diagnosis flags
- add_provider_flags: Cancer provider specialty flags

**Clinical usage:**
- FLAG_HL_DX: Cohort inclusion (Hodgkin lymphoma diagnoses)
- FLAG_SURVIVORSHIP_DX: Survivorship care identification
- FLAG_CANCER_PROVIDER: Cancer care setting identification (ENCOUNTER-PROVIDER linkage)
"""

import polars as pl

from src.validate.cohort import (
    ICD9_HL_CODES,
    ICD9_HL_NORMALIZED,
    ICD10_HL_CODES,
    ICD10_HL_NORMALIZED,
)

# DX_TYPE value sets: PCORnet supports numeric codes (09/10) and full labels.
# Multiple representations needed for compatibility across data sources.
ICD9_DX_TYPES: set[str] = {"09", "ICD-9-CM", "9"}
ICD10_DX_TYPES: set[str] = {"10", "ICD-10-CM", "10-CM"}

# Survivorship codes: Personal history of cancer treatment and follow-up encounters.
# Clinical rationale: Identifies patients in survivorship phase (post-treatment monitoring,
# late effects surveillance). Survivorship care differs from active treatment.
#
# Exact-match codes (normalized: uppercase, no dots):
# - V87.41-43, V87.46: Personal history of chemotherapy, immunotherapy, radiation, etc.
# - Z92.21-25, Z92.3: Personal history of antineoplastic chemotherapy, immunosuppression, etc.
# - V15.3: ICD-9 personal history code (semantics vary by implementation — verify against
#   study protocol if used for cohort selection)
#
# Prefix-match codes:
# - Z08.x: Encounter for follow-up examination after completed treatment for malignancy
# - Z85.xx: Personal history of malignant neoplasm (broad category)
SURVIVORSHIP_EXACT_ICD10: set[str] = {"V8741", "V8742", "V8743", "V8746", "Z9221", "Z9222", "Z9223", "Z9225", "Z923"}
SURVIVORSHIP_EXACT_ICD9: set[str] = {"V153"}
SURVIVORSHIP_PREFIX_ICD10: tuple[str, ...] = ("Z08", "Z85")

# Oncology provider keywords: Case-insensitive regex patterns for PROVIDER_SPECIALTY_PRIMARY.
# Clinical rationale: Cancer providers deliver specialized oncology care. Used to identify
# cancer-care encounters via ENCOUNTER.PROVIDERID linkage.
#
# Patterns support common specialty naming variations (hyphen, slash, spacing) and pediatric
# oncology sub-specialty.
ONCOLOGY_KEYWORDS: list[str] = [
    r"oncology",
    r"medical oncology",
    r"radiation oncology",
    r"hematology[\-\s]*oncology",
    r"hematology/oncology",
    r"pediatric oncology",
]


def _dx_type_upper() -> pl.Expr:
    """Normalize DX_TYPE column to uppercase string for matching.

    Handles null values, strips whitespace, and uppercases for consistent comparison
    against ICD9_DX_TYPES and ICD10_DX_TYPES sets.

    Returns:
        Polars expression yielding normalized DX_TYPE string (empty string if null).
    """
    return pl.coalesce(pl.col("DX_TYPE").cast(pl.Utf8).str.strip_chars(), pl.lit("")).str.to_uppercase()


def _is_icd9_type() -> pl.Expr:
    """Check if DX_TYPE indicates ICD-9-CM code system.

    Returns:
        Polars expression evaluating to True if DX_TYPE in ICD9_DX_TYPES.
    """
    return _dx_type_upper().is_in({t.upper() for t in ICD9_DX_TYPES})


def _is_icd10_type() -> pl.Expr:
    """Check if DX_TYPE indicates ICD-10-CM code system.

    Returns:
        Polars expression evaluating to True if DX_TYPE in ICD10_DX_TYPES.
    """
    return _dx_type_upper().is_in({t.upper() for t in ICD10_DX_TYPES})


def add_diagnosis_flags(df: pl.DataFrame) -> pl.DataFrame:
    """Add FLAG_HL_DX and FLAG_SURVIVORSHIP_DX to DIAGNOSIS table.

    Creates binary Int8 flags for Hodgkin lymphoma cohort inclusion and survivorship care
    identification. Uses normalized code matching (uppercase, dots removed) and DX_TYPE-
    aware logic when DX_TYPE column available.

    **FLAG_HL_DX:** 1 when DX matches cohort HL code set (149 codes). Uses same code set
    as cohort validation (src/validate/cohort.py). Excludes 201.3x (ICD-9) and C81.5x/C81.6x
    (ICD-10) per study protocol.

    **FLAG_SURVIVORSHIP_DX:** 1 when DX matches survivorship code set (personal history
    of treatment, follow-up encounters). Includes exact-match and prefix-match codes.

    Clinical rationale: FLAG_HL_DX identifies cohort-eligible diagnoses for inclusion.
    FLAG_SURVIVORSHIP_DX identifies post-treatment care patterns and survivorship phase.

    Args:
        df: DIAGNOSIS DataFrame with DX column (and optionally DX_TYPE).

    Returns:
        DataFrame with FLAG_HL_DX and FLAG_SURVIVORSHIP_DX columns added (Int8).
        Returns df unchanged if DX column absent.
    """
    if "DX" not in df.columns:
        return df
    dx_norm = pl.col("DX").fill_null("").str.to_uppercase().str.replace_all(r"\.", "")
    has_dx_type = "DX_TYPE" in df.columns

    # FLAG_HL_DX — use cohort's exact 149-code set (no prefix match)
    icd9_codes = list(ICD9_HL_CODES)
    icd9_norm = list(ICD9_HL_NORMALIZED)
    icd10_codes = list(ICD10_HL_CODES)
    icd10_norm = list(ICD10_HL_NORMALIZED)

    in_icd9_hl = pl.col("DX").is_in(icd9_codes) | dx_norm.is_in(icd9_norm)
    in_icd10_hl = pl.col("DX").is_in(icd10_codes) | dx_norm.is_in(icd10_norm)

    if has_dx_type:
        flag_hl = (
            pl.when(_is_icd9_type() & in_icd9_hl)
            .then(pl.lit(1, dtype=pl.Int8))
            .when(_is_icd10_type() & in_icd10_hl)
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
    else:
        flag_hl = pl.when(in_icd9_hl | in_icd10_hl).then(pl.lit(1, dtype=pl.Int8)).otherwise(pl.lit(0, dtype=pl.Int8))
    df = df.with_columns(flag_hl.alias("FLAG_HL_DX"))

    # FLAG_SURVIVORSHIP_DX
    exact_icd9 = dx_norm.is_in(SURVIVORSHIP_EXACT_ICD9)
    exact_icd10 = dx_norm.is_in(SURVIVORSHIP_EXACT_ICD10)
    prefix_match = dx_norm.str.starts_with(SURVIVORSHIP_PREFIX_ICD10[0]) | dx_norm.str.starts_with(SURVIVORSHIP_PREFIX_ICD10[1])
    if has_dx_type:
        flag_surv = (
            pl.when(_is_icd9_type() & exact_icd9)
            .then(pl.lit(1, dtype=pl.Int8))
            .when(_is_icd10_type() & (exact_icd10 | prefix_match))
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
    else:
        flag_surv = pl.when(exact_icd9 | exact_icd10 | prefix_match).then(pl.lit(1, dtype=pl.Int8)).otherwise(pl.lit(0, dtype=pl.Int8))
    df = df.with_columns(flag_surv.alias("FLAG_SURVIVORSHIP_DX"))

    return df


def add_provider_flags(df: pl.DataFrame) -> pl.DataFrame:
    """Add FLAG_CANCER_PROVIDER to PROVIDER table.

    Creates binary Int8 flag identifying oncology providers based on specialty keywords.
    Uses case-insensitive regex matching on PROVIDER_SPECIALTY_PRIMARY.

    Clinical rationale: Cancer providers deliver specialized oncology care. Used to
    identify cancer-care encounters via ENCOUNTER.PROVIDERID linkage (join ENCOUNTER
    to PROVIDER and filter FLAG_CANCER_PROVIDER=1).

    Args:
        df: PROVIDER DataFrame with PROVIDER_SPECIALTY_PRIMARY column.

    Returns:
        DataFrame with FLAG_CANCER_PROVIDER column added (Int8: 1 if oncology, 0 otherwise).
        Returns df unchanged if PROVIDER_SPECIALTY_PRIMARY absent.
    """
    if "PROVIDER_SPECIALTY_PRIMARY" not in df.columns:
        return df
    specialty = pl.col("PROVIDER_SPECIALTY_PRIMARY").fill_null("").str.to_lowercase()
    pattern = "|".join(ONCOLOGY_KEYWORDS)
    is_cancer = specialty.str.contains(pattern).fill_null(False)
    df = df.with_columns(is_cancer.cast(pl.Int8).alias("FLAG_CANCER_PROVIDER"))
    return df
