"""Phase 5: Cleaning — partner provenance flags and enrollment coverage checks.

Identifies partner-specific data characteristics and validates encounter-enrollment
temporal consistency. Partner flags distinguish data sources with known quirks
(retrospective coding, claims-only data, death registries). Enrollment checks flag
encounters without insurance coverage.

**Pipeline position:** Phase 5 (Cleaning)
**Input:** Raw Parquet tables from Phase 4 (Loading)
**Output:** DataFrames with ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY, _con_* flag columns
**Orchestrated by:** scripts/clean_all.py

**Key functions:**
- add_partner_flags: Partner provenance indicators
- flag_encounters_outside_enrollment: Enrollment coverage validation
- flag_no_enrollment: Missing enrollment detection
"""

import polars as pl

from src.validate.structural import PATID_COL

# ---------------------------------------------------------------------------
# Constants — partner provenance flags
# ---------------------------------------------------------------------------

# Partner flags identify data sources with known characteristics that affect interpretation.
# Clinical rationale: Data provenance affects data quality and usability — retrospective
# coding differs from prospective EHR, claims lack clinical detail, death registries have
# limited scope.
#
# ICD_MAPPED (AMS, UMI): Partners performing retrospective ICD code mapping from clinical
# notes or legacy systems. Mapped codes may have lower specificity or completeness than
# prospectively coded data.
#
# CLAIMS_ONLY (FLM): Claims data lacks clinical detail (lab values, vital signs, clinical
# notes) but has complete billing codes. Useful for utilization/cost but limited for
# clinical outcomes.
#
# DEATH_ONLY (VRT): Death registry data — provides mortality dates but no longitudinal
# clinical data. Used for vital status ascertainment.
#
# TODO(audit): Verify partner abbreviations (AMS, UMI, FLM, VRT) match current data sources.
# Partner lists may change over time — maintain in sync with data acquisition.
PARTNER_FLAGS: dict[str, set[str]] = {
    "ICD_MAPPED": {"AMS", "UMI"},
    "CLAIMS_ONLY": {"FLM"},
    "DEATH_ONLY": {"VRT"},
}


# ---------------------------------------------------------------------------
# 1. Add partner provenance flags
# ---------------------------------------------------------------------------


def add_partner_flags(
    df: pl.DataFrame,
    partner_col: str = "SOURCE",
) -> pl.DataFrame:
    """Add partner provenance flags to DataFrame based on SOURCE column.

    Creates binary Int8 flags (ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY) identifying partner-
    specific data characteristics. Each flag is 1 when partner_col matches the partner
    set defined in PARTNER_FLAGS.

    Clinical rationale: Data source affects interpretation — ICD_MAPPED data has
    retrospective coding limitations, CLAIMS_ONLY lacks clinical detail, DEATH_ONLY
    provides only vital status.

    Args:
        df: Input DataFrame with partner identifier column.
        partner_col: Name of column containing partner codes (default: "SOURCE").

    Returns:
        DataFrame with ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY columns added (Int8).
        Returns df unchanged if partner_col absent.
    """
    if partner_col not in df.columns:
        return df
    for flag_name, partners in PARTNER_FLAGS.items():
        df = df.with_columns(pl.col(partner_col).is_in(partners).cast(pl.Int8).alias(flag_name))
    return df


# ---------------------------------------------------------------------------
# 2. Encounters outside enrollment periods
# ---------------------------------------------------------------------------


def flag_encounters_outside_enrollment(
    encounter_df: pl.DataFrame,
    enrollment_df: pl.DataFrame,
) -> pl.DataFrame:
    """Flag encounters whose ADMIT_DATE falls outside all enrollment periods.

    Encounters should occur during active insurance enrollment. Encounters outside
    enrollment windows indicate data quality issues (missing enrollment records,
    incorrect dates, or uninsured care not captured in enrollment table).

    **Join strategy:** Many-to-many join (patient can have multiple enrollment periods,
    multiple encounters). Uses lazy evaluation to manage memory during Cartesian product
    expansion. Groups by encounter columns after join to check if ANY enrollment period
    covers the encounter date.

    Clinical rationale: Enrollment coverage is essential for payer analysis and
    understanding insurance continuity during treatment.

    Args:
        encounter_df: ENCOUNTER DataFrame with ADMIT_DATE and patient ID.
        enrollment_df: ENROLLMENT DataFrame with ENR_START_DATE, ENR_END_DATE.

    Returns:
        encounter_df with _con_outside_enrollment column added (Int8: 1 if outside all
        periods, 0 if covered by at least one period). Returns encounter_df unchanged
        if ADMIT_DATE absent.
    """
    if "ADMIT_DATE" not in encounter_df.columns:
        return encounter_df

    enr = enrollment_df.select(
        pl.col(PATID_COL).cast(pl.String).alias(PATID_COL),
        "ENR_START_DATE",
        "ENR_END_DATE",
    )

    enc_cols = encounter_df.columns

    result = (
        encounter_df.lazy()
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .join(enr.lazy(), on=PATID_COL, how="left")
        .with_columns(
            pl.when(
                pl.col("ENR_START_DATE").is_not_null()
                & pl.col("ENR_END_DATE").is_not_null()
                & (pl.col("ADMIT_DATE") >= pl.col("ENR_START_DATE"))
                & (pl.col("ADMIT_DATE") <= pl.col("ENR_END_DATE"))
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .alias("_covered")
        )
        .group_by(enc_cols)
        .agg(pl.col("_covered").max().alias("_any_covered"))
        .with_columns(
            pl.when((pl.col("_any_covered") == 0) & pl.col("ADMIT_DATE").is_not_null())
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias("_con_outside_enrollment")
        )
        .drop("_any_covered")
        .collect()
    )
    return result


# ---------------------------------------------------------------------------
# 3. Patients with no enrollment records
# ---------------------------------------------------------------------------


def flag_no_enrollment(
    encounter_df: pl.DataFrame,
    enrollment_df: pl.DataFrame,
) -> pl.DataFrame:
    """Flag patients who appear in ENCOUNTER but have zero ENROLLMENT records.

    Patients with encounters but no enrollment records represent data quality issues
    (incomplete enrollment data, system integration gaps) or uninsured care not
    captured in enrollment table. Flags ALL encounters for affected patients.

    Clinical rationale: Patients without enrollment records cannot have payer analysis
    performed and represent potential coverage gaps in the dataset.

    Args:
        encounter_df: ENCOUNTER DataFrame with patient ID.
        enrollment_df: ENROLLMENT DataFrame with patient ID.

    Returns:
        encounter_df with _con_no_enrollment column added (Int8: 1 if patient has no
        enrollment records, 0 otherwise).
    """
    enr_ids = enrollment_df.select(pl.col(PATID_COL).cast(pl.String)).unique()

    no_enr = encounter_df.select(pl.col(PATID_COL).cast(pl.String)).unique().join(enr_ids, on=PATID_COL, how="anti")

    no_enr_list = no_enr[PATID_COL].to_list()

    encounter_df = encounter_df.with_columns(pl.col(PATID_COL).cast(pl.String).is_in(no_enr_list).cast(pl.Int8).alias("_con_no_enrollment"))
    return encounter_df
