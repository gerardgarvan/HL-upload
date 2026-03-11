# HL data loading & cleaning — encounter patient-level summary (payer focus)
"""Build one row per patient with encounter-derived, payer-focused variables.

Output: N_ENCOUNTERS, N_ENCOUNTERS_WITH_PAYER, N_DISTINCT_PAYERS,
PAYER_PRIMARY (most frequent valid payer), PAYER_TRANSITION (1 if >1 payer).

Valid payer: PAYER_TYPE_PRIMARY not null, not empty, not in {NI, UN, OT}.
Any future CSV or report export must use _suppress for counts 1–10 (HIPAA).
"""

from pathlib import Path

import polars as pl

from src.validate.structural import PATID_COL

INVALID_PAYER: set[str] = {"NI", "UN", "OT"}


def _valid_payer_expr() -> pl.Expr:
    """True when PAYER_TYPE_PRIMARY is usable (not null, not empty, not NI/UN/OT)."""
    return (
        pl.col("PAYER_TYPE_PRIMARY").is_not_null()
        & (pl.col("PAYER_TYPE_PRIMARY") != "")
        & ~pl.col("PAYER_TYPE_PRIMARY").is_in(INVALID_PAYER)
    )


def build_encounter_payer_summary(table_map: dict[str, Path]) -> pl.DataFrame:
    """Summarize ENCOUNTER at patient level with payer-focused variables.

    Returns one row per patient with:
    - N_ENCOUNTERS: total encounter count
    - N_ENCOUNTERS_WITH_PAYER: encounters with valid PAYER_TYPE_PRIMARY
    - N_DISTINCT_PAYERS: distinct valid payers per patient
    - PAYER_PRIMARY: most frequent valid payer; null if none
    - PAYER_TRANSITION: 1 if N_DISTINCT_PAYERS > 1, else 0

    Returns empty DataFrame with schema if ENCOUNTER not found.
    """
    enc_path = table_map.get("ENCOUNTER")
    if not enc_path or not enc_path.exists():
        return pl.DataFrame(
            schema={
                PATID_COL: pl.String,
                "N_ENCOUNTERS": pl.Int64,
                "N_ENCOUNTERS_WITH_PAYER": pl.Int64,
                "N_DISTINCT_PAYERS": pl.Int64,
                "PAYER_PRIMARY": pl.String,
                "PAYER_TRANSITION": pl.Int8,
            }
        )

    schema = pl.read_parquet_schema(enc_path)
    if "PAYER_TYPE_PRIMARY" not in schema or PATID_COL not in schema:
        return pl.DataFrame(
            schema={
                PATID_COL: pl.String,
                "N_ENCOUNTERS": pl.Int64,
                "N_ENCOUNTERS_WITH_PAYER": pl.Int64,
                "N_DISTINCT_PAYERS": pl.Int64,
                "PAYER_PRIMARY": pl.String,
                "PAYER_TRANSITION": pl.Int8,
            }
        )

    enc = (
        pl.scan_parquet(enc_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .with_columns(_valid_payer_expr().alias("_valid"))
    )

    # Base counts
    base = (
        enc.group_by(PATID_COL)
        .agg(
            pl.len().alias("N_ENCOUNTERS"),
            pl.col("_valid").sum().cast(pl.Int64).alias("N_ENCOUNTERS_WITH_PAYER"),
        )
        .collect()
    )

    # N_DISTINCT_PAYERS and PAYER_PRIMARY from valid rows only
    valid_enc = (
        enc.filter(pl.col("_valid"))
        .select(PATID_COL, "PAYER_TYPE_PRIMARY")
        .collect()
    )

    if valid_enc.is_empty():
        base = base.with_columns(
            pl.lit(0).cast(pl.Int64).alias("N_DISTINCT_PAYERS"),
            pl.lit(None).cast(pl.String).alias("PAYER_PRIMARY"),
        )
    else:
        # Per patient: n_unique payers
        distinct = (
            valid_enc.group_by(PATID_COL)
            .agg(pl.col("PAYER_TYPE_PRIMARY").n_unique().alias("N_DISTINCT_PAYERS"))
        )

        # PAYER_PRIMARY: most frequent payer per patient (mode)
        payer_counts = (
            valid_enc.group_by(PATID_COL, "PAYER_TYPE_PRIMARY")
            .agg(pl.len().alias("_n"))
            .sort("_n", descending=True)
            .group_by(PATID_COL)
            .first()
        )
        payer_primary = payer_counts.select(
            PATID_COL, pl.col("PAYER_TYPE_PRIMARY").alias("PAYER_PRIMARY")
        )

        base = (
            base.join(distinct, on=PATID_COL, how="left")
            .with_columns(pl.col("N_DISTINCT_PAYERS").fill_null(0))
            .join(payer_primary, on=PATID_COL, how="left")
        )

    base = base.with_columns(
        (pl.col("N_DISTINCT_PAYERS") > 1).cast(pl.Int8).alias("PAYER_TRANSITION")
    )
    return base.select(
        PATID_COL,
        "N_ENCOUNTERS",
        "N_ENCOUNTERS_WITH_PAYER",
        "N_DISTINCT_PAYERS",
        "PAYER_PRIMARY",
        "PAYER_TRANSITION",
    )
