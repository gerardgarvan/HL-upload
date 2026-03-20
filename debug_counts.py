"""Trace through _compute_post_treatment_payer to find where patients are lost."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl
from src.load.config import load_and_validate_config
from src.report.encounter_payer_summary import (
    _payer_category_from_effective_and_dual,
    _effective_payer_and_dual_exprs,
)
from src.validate.structural import PATID_COL

paths = load_and_validate_config()
df = pl.read_parquet(paths.derived_dir / "encounter_payer_summary.parquet")
print(f"1. Input parquet: {df.height} rows, {df.filter(pl.col('HAD_CHEMO')==1).height} chemo")

# Step: add LAST_TREATMENT_DATE
patients = df.with_columns(
    pl.max_horizontal("LAST_CHEMO_DATE", "LAST_RADIATION_DATE", "LAST_SCT_DATE")
    .alias("LAST_TREATMENT_DATE")
)
patients = patients.with_columns(
    ((pl.col("HAD_CHEMO") == 1) | (pl.col("HAD_RADIATION") == 1) | (pl.col("HAD_SCT") == 1))
    .cast(pl.Int8).alias("HAD_ANY_TREATMENT")
)
print(f"2. After with_columns: {patients.height} rows, {patients.filter(pl.col('HAD_CHEMO')==1).height} chemo")

# Step: select columns (before join)
selected = patients.select(
    PATID_COL, "HAD_CHEMO", "HAD_RADIATION", "HAD_SCT",
    "HAD_ANY_TREATMENT", "LAST_TREATMENT_DATE",
)
print(f"3. After select: {selected.height} rows, {selected.filter(pl.col('HAD_CHEMO')==1).height} chemo")

# Step: read ENCOUNTER and build mode_df (reproduce Phase 6 logic)
clean_dir = paths.parquet_dir
enc_candidates = sorted(clean_dir.glob("ENCOUNTER*.parquet"))
enc_path = enc_candidates[0] if enc_candidates else clean_dir / "ENCOUNTER.parquet"
print(f"4. ENCOUNTER path: {enc_path}")

enc_schema = pl.read_parquet_schema(enc_path)
has_secondary = "PAYER_TYPE_SECONDARY" in enc_schema.names()
enc_cols = [PATID_COL, "ADMIT_DATE", "PAYER_TYPE_PRIMARY"]
if has_secondary:
    enc_cols.append("PAYER_TYPE_SECONDARY")

eff_expr, valid_expr, dual_expr = _effective_payer_and_dual_exprs(has_secondary)
enc = (
    pl.scan_parquet(enc_path)
    .with_columns(pl.col(PATID_COL).cast(pl.String))
    .filter(pl.col(PATID_COL).is_in(patients[PATID_COL].implode()))
    .select(enc_cols)
    .with_columns([eff_expr, valid_expr, dual_expr])
    .select(PATID_COL, "ADMIT_DATE", "effective_payer", "dual_eligible", "_valid")
    .collect()
)
print(f"5. Encounters loaded: {enc.height} rows, {enc[PATID_COL].n_unique()} unique patients")

# Mode computation
patients_with_last_tx = patients.filter(pl.col("LAST_TREATMENT_DATE").is_not_null())
print(f"6. Patients with treatment: {patients_with_last_tx.height}, chemo: {patients_with_last_tx.filter(pl.col('HAD_CHEMO')==1).height}")

joined = patients_with_last_tx.select(PATID_COL, "LAST_TREATMENT_DATE").join(enc, on=PATID_COL, how="inner")
print(f"7. After inner join (encounters x treated patients): {joined.height} rows, {joined[PATID_COL].n_unique()} unique patients")

post_treatment = joined.filter(
    (pl.col("ADMIT_DATE") > pl.col("LAST_TREATMENT_DATE")) & pl.col("_valid")
)
print(f"8. Post-treatment encounters: {post_treatment.height} rows, {post_treatment[PATID_COL].n_unique()} unique patients")

# Derive payer category
post_treatment = post_treatment.with_columns(
    pl.Series("PAYER_CATEGORY", [
        _payer_category_from_effective_and_dual(r["effective_payer"], r.get("dual_eligible", 0) or 0)
        for r in post_treatment.iter_rows(named=True)
    ], dtype=pl.String)
)
post_treatment = post_treatment.with_columns(
    pl.when(pl.col("PAYER_CATEGORY") == "No payment / Self-pay")
    .then(pl.lit("Self-pay"))
    .otherwise(pl.col("PAYER_CATEGORY"))
    .alias("PAYER_CATEGORY")
)

mode_df = (
    post_treatment.group_by(PATID_COL, "PAYER_CATEGORY")
    .agg(pl.len().alias("_n"))
    .sort("_n", descending=True)
    .group_by(PATID_COL)
    .first()
    .select(PATID_COL, pl.col("PAYER_CATEGORY").alias("POST_TREATMENT_PAYER"))
)
print(f"9. mode_df: {mode_df.height} patients with post-treatment payer")

# The critical left join
result = selected.join(mode_df, on=PATID_COL, how="left")
print(f"10. After LEFT join: {result.height} rows, {result.filter(pl.col('HAD_CHEMO')==1).height} chemo")

# Fill nulls
result = result.with_columns(
    pl.when(pl.col("POST_TREATMENT_PAYER").is_not_null())
    .then(pl.col("POST_TREATMENT_PAYER"))
    .when(pl.col("HAD_ANY_TREATMENT") == 1)
    .then(pl.lit("Unknown"))
    .otherwise(pl.lit("N/A (No Treatment)"))
    .alias("POST_TREATMENT_PAYER")
)
print(f"11. Final result: {result.height} rows, {result.filter(pl.col('HAD_CHEMO')==1).height} chemo")
print(f"\nExpected chemo: 6296, Got: {result.filter(pl.col('HAD_CHEMO')==1).height}")
