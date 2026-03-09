# HL data loading & cleaning — partner harmonization & insurance consistency
"""Partner-level provenance flags and insurance enrollment coverage checks.

Adds binary flag columns (0/1, Int8) to DataFrames.  Partner flags use
direct names (ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY); insurance consistency
flags use the ``_con_`` infix naming convention.
"""

import polars as pl

from src.validate.structural import PATID_COL

# ---------------------------------------------------------------------------
# Constants — partner provenance flags
# ---------------------------------------------------------------------------

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
    """Add ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY Int8 flags based on SOURCE.

    Each flag is 1 when the partner_col value belongs to the corresponding
    partner set.  Returns *df* unchanged if *partner_col* is absent.
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
    """Flag encounters whose ADMIT_DATE is not covered by any enrollment period.

    Adds ``_con_outside_enrollment`` (Int8): 1 when ADMIT_DATE is not null
    but falls outside every enrollment [ENR_START_DATE, ENR_END_DATE] window
    for the same patient.  Uses lazy evaluation to manage the many-to-many
    join explosion (patients × enrollment periods).

    Returns *encounter_df* unchanged if ADMIT_DATE is absent.
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

    Adds ``_con_no_enrollment`` (Int8): 1 for encounter rows belonging to
    patients entirely absent from the enrollment table.
    """
    enr_ids = enrollment_df.select(pl.col(PATID_COL).cast(pl.String)).unique()

    no_enr = encounter_df.select(pl.col(PATID_COL).cast(pl.String)).unique().join(enr_ids, on=PATID_COL, how="anti")

    no_enr_list = no_enr[PATID_COL].to_list()

    encounter_df = encounter_df.with_columns(pl.col(PATID_COL).cast(pl.String).is_in(no_enr_list).cast(pl.Int8).alias("_con_no_enrollment"))
    return encounter_df
