import polars as pl

df = pl.read_parquet("derived/encounter_payer_summary.parquet")
chemo = df.filter(pl.col("HAD_CHEMO") == 1)
print(f"Total rows: {df.height}")
print(f"Unique IDs: {df['ID'].n_unique()}")
print(f"HAD_CHEMO rows: {chemo.height}")
print(f"HAD_CHEMO unique IDs: {chemo['ID'].n_unique()}")
