# HL data loading & cleaning — diagnosis and provider flags
"""Add FLAG_HL_DX, FLAG_SURVIVORSHIP_DX (DIAGNOSIS) and FLAG_CANCER_PROVIDER (PROVIDER).

Survivorship codes: user-provided list per study protocol (V87.41/42/43/46, V15.3,
Z92.21-25, Z92.3, Z08*, Z85*). For ENCOUNTER–PROVIDER linkage: join ENCOUNTER.PROVIDERID
to PROVIDER and filter FLAG_CANCER_PROVIDER=1 for "encounter with cancer provider."
"""

import polars as pl

# DX_TYPE supports PCORnet numeric (09/10) and full labels (ICD-9-CM/ICD-10-CM)
ICD9_DX_TYPES: set[str] = {"09", "ICD-9-CM", "9"}
ICD10_DX_TYPES: set[str] = {"10", "ICD-10-CM", "10-CM"}

# Survivorship: exact-match codes (normalized: uppercase, no dots)
SURVIVORSHIP_EXACT_ICD10: set[str] = {"V8741", "V8742", "V8743", "V8746", "Z9221", "Z9222", "Z9223", "Z9225", "Z923"}
SURVIVORSHIP_EXACT_ICD9: set[str] = {"V153"}
# Prefix-match (Z08.x, Z85.xx = history of malignancy, follow-up)
SURVIVORSHIP_PREFIX_ICD10: tuple[str, ...] = ("Z08", "Z85")

# Oncology keywords for PROVIDER_SPECIALTY_PRIMARY (case-insensitive)
ONCOLOGY_KEYWORDS: list[str] = [
    r"oncology",
    r"medical oncology",
    r"radiation oncology",
    r"hematology[\-\s]*oncology",
    r"hematology/oncology",
    r"pediatric oncology",
]


def _dx_type_upper() -> pl.Expr:
    """Coalesce DX_TYPE to string, strip, uppercase."""
    return pl.coalesce(pl.col("DX_TYPE").cast(pl.Utf8).str.strip_chars(), pl.lit("")).str.to_uppercase()


def _is_icd9_type() -> pl.Expr:
    return _dx_type_upper().is_in({t.upper() for t in ICD9_DX_TYPES})


def _is_icd10_type() -> pl.Expr:
    return _dx_type_upper().is_in({t.upper() for t in ICD10_DX_TYPES})


def add_diagnosis_flags(df: pl.DataFrame) -> pl.DataFrame:
    """Add FLAG_HL_DX and FLAG_SURVIVORSHIP_DX to DIAGNOSIS.

    FLAG_HL_DX: 1 when (DX_TYPE in ICD9 and DX starts with 201) or (DX_TYPE in ICD10 and DX starts with C81).
    FLAG_SURVIVORSHIP_DX: 1 when DX is in survivorship set (V87.41/42/43/46, V15.3, Z92.21-25, Z92.3, Z08*, Z85*).
    """
    if "DX" not in df.columns:
        return df
    dx_norm = pl.col("DX").fill_null("").str.to_uppercase().str.replace_all(r"\.", "")
    has_dx_type = "DX_TYPE" in df.columns

    # FLAG_HL_DX
    if has_dx_type:
        flag_hl = (
            pl.when(_is_icd9_type() & pl.col("DX").str.starts_with("201"))
            .then(pl.lit(1, dtype=pl.Int8))
            .when(_is_icd10_type() & dx_norm.str.starts_with("C81"))
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
    else:
        flag_hl = (
            pl.when(pl.col("DX").str.starts_with("201"))
            .then(pl.lit(1, dtype=pl.Int8))
            .when(dx_norm.str.starts_with("C81"))
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
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
    """Add FLAG_CANCER_PROVIDER to PROVIDER.

    FLAG_CANCER_PROVIDER: 1 when PROVIDER_SPECIALTY_PRIMARY matches oncology keywords.
    """
    if "PROVIDER_SPECIALTY_PRIMARY" not in df.columns:
        return df
    specialty = pl.col("PROVIDER_SPECIALTY_PRIMARY").fill_null("").str.to_lowercase()
    pattern = "|".join(ONCOLOGY_KEYWORDS)
    is_cancer = specialty.str.contains(pattern).fill_null(False)
    df = df.with_columns(is_cancer.cast(pl.Int8).alias("FLAG_CANCER_PROVIDER"))
    return df
