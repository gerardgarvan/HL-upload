# HL data loading & cleaning — encounter patient-level summary (payer focus)
"""Build one row per patient with encounter-derived, payer-focused variables.

Scope: Only patients with ENROLLMENT records.
Output: N_ENCOUNTERS, N_ENCOUNTERS_WITH_PAYER, N_DISTINCT_PAYER_CATEGORIES,
PAYER_CATEGORY_PRIMARY (most frequent payer category), PAYER_TRANSITION (1 if >1 category).

Payer categories: Medicare, Medicaid, Private, Other government,
No payment / Self-pay, Other, Unavailable, Unknown (PCORnet typology prefix mapping).
Any future CSV or report export must use _suppress for counts 1–10 (HIPAA).
"""

from pathlib import Path

import polars as pl

from src.validate.structural import PATID_COL

INVALID_PAYER: set[str] = {"NI", "UN", "OT"}

# Payer code → category (PCORnet typology: 1=Medicare, 2=Medicaid, 5/6=Private, etc.)
def _collapse_payer_category(code: str) -> str:
    """Map PAYER_TYPE_PRIMARY to collapsed category for analysis."""
    c = str(code).strip() if code is not None else ""
    if not c or c.upper() in ("UNKNOWN", "NI", "UN", "OT"):
        return "Unknown"
    if c in ("99", "9999"):
        return "Unavailable"
    if c.startswith("1"):
        return "Medicare"
    if c.startswith("2"):
        return "Medicaid"
    if c.startswith("5") or c.startswith("6"):
        return "Private"
    if c.startswith("3") or c.startswith("4"):
        return "Other government"
    if c.startswith("8"):
        return "No payment / Self-pay"
    if c.startswith("7") or c.startswith("9"):
        return "Other"
    return "Other"


def _valid_payer_expr() -> pl.Expr:
    """True when PAYER_TYPE_PRIMARY is usable (not null, not empty, not NI/UN/OT)."""
    return (
        pl.col("PAYER_TYPE_PRIMARY").is_not_null()
        & (pl.col("PAYER_TYPE_PRIMARY") != "")
        & ~pl.col("PAYER_TYPE_PRIMARY").is_in(INVALID_PAYER)
    )


def build_encounter_payer_summary(table_map: dict[str, Path]) -> pl.DataFrame:
    """Summarize ENCOUNTER at patient level with payer-focused variables.

    Only includes patients with at least one ENROLLMENT record.
    Payer is classified into categories: Medicare, Medicaid, Private, etc.

    Returns one row per patient with:
    - N_ENCOUNTERS: total encounter count
    - N_ENCOUNTERS_WITH_PAYER: encounters with valid PAYER_TYPE_PRIMARY
    - N_DISTINCT_PAYER_CATEGORIES: distinct payer categories per patient
    - PAYER_CATEGORY_PRIMARY: most frequent payer category; null if none
    - PAYER_TRANSITION: 1 if N_DISTINCT_PAYER_CATEGORIES > 1, else 0

    Returns empty DataFrame with schema if ENCOUNTER not found.
    """
    empty_schema = {
        PATID_COL: pl.String,
        "N_ENCOUNTERS": pl.Int64,
        "N_ENCOUNTERS_WITH_PAYER": pl.Int64,
        "N_DISTINCT_PAYER_CATEGORIES": pl.Int64,
        "PAYER_CATEGORY_PRIMARY": pl.String,
        "PAYER_TRANSITION": pl.Int8,
    }

    enc_path = table_map.get("ENCOUNTER")
    if not enc_path or not enc_path.exists():
        return pl.DataFrame(schema=empty_schema)

    schema = pl.read_parquet_schema(enc_path)
    if "PAYER_TYPE_PRIMARY" not in schema or PATID_COL not in schema:
        return pl.DataFrame(schema=empty_schema)

    # Enrolled IDs only
    enr_path = table_map.get("ENROLLMENT")
    if enr_path and enr_path.exists():
        enr_schema = pl.read_parquet_schema(enr_path)
        if PATID_COL in enr_schema:
            enrolled_ids = (
                pl.scan_parquet(enr_path)
                .select(pl.col(PATID_COL).cast(pl.String).unique())
                .collect()
            )
            filter_ids = enrolled_ids.to_series()
        else:
            filter_ids = None
    else:
        filter_ids = None

    enc = (
        pl.scan_parquet(enc_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .with_columns(_valid_payer_expr().alias("_valid"))
    )
    if filter_ids is not None:
        enc = enc.filter(pl.col(PATID_COL).is_in(filter_ids))

    # Base counts
    base = (
        enc.group_by(PATID_COL)
        .agg(
            pl.len().alias("N_ENCOUNTERS"),
            pl.col("_valid").sum().cast(pl.Int64).alias("N_ENCOUNTERS_WITH_PAYER"),
        )
        .collect()
    )

    # Add PAYER_CATEGORY from PAYER_TYPE_PRIMARY (valid rows only)
    valid_enc = (
        enc.filter(pl.col("_valid"))
        .select(PATID_COL, "PAYER_TYPE_PRIMARY")
        .collect()
    )

    if valid_enc.is_empty():
        base = base.with_columns(
            pl.lit(0).cast(pl.Int64).alias("N_DISTINCT_PAYER_CATEGORIES"),
            pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_PRIMARY"),
        )
    else:
        valid_enc = valid_enc.with_columns(
            pl.col("PAYER_TYPE_PRIMARY")
            .map_batches(
                lambda s: pl.Series(
                    [_collapse_payer_category(v) for v in s], dtype=pl.String
                )
            )
            .alias("PAYER_CATEGORY")
        )

        distinct = (
            valid_enc.group_by(PATID_COL)
            .agg(
                pl.col("PAYER_CATEGORY")
                .n_unique()
                .alias("N_DISTINCT_PAYER_CATEGORIES")
            )
        )

        payer_counts = (
            valid_enc.group_by(PATID_COL, "PAYER_CATEGORY")
            .agg(pl.len().alias("_n"))
            .sort("_n", descending=True)
            .group_by(PATID_COL)
            .first()
        )
        payer_primary = payer_counts.select(
            PATID_COL,
            pl.col("PAYER_CATEGORY").alias("PAYER_CATEGORY_PRIMARY"),
        )

        base = (
            base.join(distinct, on=PATID_COL, how="left")
            .with_columns(pl.col("N_DISTINCT_PAYER_CATEGORIES").fill_null(0))
            .join(payer_primary, on=PATID_COL, how="left")
        )

    base = base.with_columns(
        (pl.col("N_DISTINCT_PAYER_CATEGORIES") > 1)
        .cast(pl.Int8)
        .alias("PAYER_TRANSITION")
    )
    return base.select(
        PATID_COL,
        "N_ENCOUNTERS",
        "N_ENCOUNTERS_WITH_PAYER",
        "N_DISTINCT_PAYER_CATEGORIES",
        "PAYER_CATEGORY_PRIMARY",
        "PAYER_TRANSITION",
    )
