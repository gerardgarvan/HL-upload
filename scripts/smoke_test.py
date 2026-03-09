"""Smoke test: CSV load -> SAS date parse -> Parquet write -> read-back verify -> DuckDB verify.

Validates the end-to-end pipeline using the DEMOGRAPHIC table.
Run: python scripts/smoke_test.py [config/paths.toml]
"""

import sys
from pathlib import Path

# Allow running from project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.load.config import load_config
from src.load.schema import parse_datastructure


def main(config_path: Path | None = None) -> None:
    print("=" * 60)
    print("HL DATA LOADING & CLEANING — SMOKE TEST")
    print("=" * 60)

    # Step 1: Load config, verify data_root
    print("\n--- Step 1: Load configuration ---")
    paths = load_config(config_path)
    print(f"  data_root:    {paths.data_root}")
    print(f"  scratch_root: {paths.scratch_root}")
    print(f"  parquet_dir:  {paths.parquet_dir}")

    if not paths.data_root.is_dir():
        raise RuntimeError(f"data_root is not a directory: {paths.data_root}")
    print("  [OK] data_root exists and is a directory")

    # Step 2: Parse datastructure.txt
    print("\n--- Step 2: Parse datastructure.txt ---")
    data_root_from_file, tables = parse_datastructure(paths.datastructure_path)
    print(f"  Data root in file: {data_root_from_file}")
    print(f"  Table count: {len(tables)}")
    for t in tables:
        print(f"    - {t}")

    # Step 3: Verify at least one CSV exists
    print("\n--- Step 3: Verify source CSV exists ---")
    demo_csv = "DEMOGRAPHIC_Mailhot_V1.csv"
    csv_path = paths.data_root / demo_csv
    if not csv_path.exists():
        raise FileNotFoundError(f"Expected CSV not found: {csv_path}")
    csv_size_mb = csv_path.stat().st_size / (1024 * 1024)
    print(f"  [OK] {demo_csv} exists ({csv_size_mb:.1f} MB)")

    # Step 4: Load DEMOGRAPHIC CSV with Polars
    print("\n--- Step 4: Load CSV with Polars ---")
    import polars as pl

    df = pl.read_csv(csv_path)
    print(f"  Rows: {df.shape[0]:,}")
    print(f"  Columns: {df.shape[1]}")
    original_shape = df.shape

    # Step 5: Parse BIRTH_DATE (SAS DATE9. format)
    print("\n--- Step 5: Parse SAS DATE9. dates ---")
    date_col = "BIRTH_DATE"
    if date_col not in df.columns:
        raise RuntimeError(f"{date_col} column not found in DEMOGRAPHIC")

    dtype_before = df[date_col].dtype
    nulls_before = df[date_col].null_count()
    print(f"  Before: dtype={dtype_before}, nulls={nulls_before}")

    df = df.with_columns(pl.col(date_col).str.to_date("%d%b%Y", strict=False))

    dtype_after = df[date_col].dtype
    nulls_after = df[date_col].null_count()
    print(f"  After:  dtype={dtype_after}, nulls={nulls_after}")
    print(f"  New nulls from parsing: {nulls_after - nulls_before}")

    # Step 6: Write Parquet
    print("\n--- Step 6: Write Parquet ---")
    paths.parquet_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = paths.parquet_dir / "DEMOGRAPHIC.parquet"
    df.write_parquet(parquet_path)
    parquet_size_mb = parquet_path.stat().st_size / (1024 * 1024)
    print(f"  [OK] Wrote {parquet_path}")
    print(f"  Parquet size: {parquet_size_mb:.1f} MB")

    # Step 7: Read back and verify
    print("\n--- Step 7: Parquet read-back verify ---")
    df2 = pl.read_parquet(parquet_path)
    assert df2.shape == original_shape, f"Shape mismatch: wrote {original_shape}, read {df2.shape}"
    assert df2[date_col].dtype == pl.Date, f"Date type lost: expected pl.Date, got {df2[date_col].dtype}"
    print(f"  [OK] Shape matches: {df2.shape[0]:,} rows x {df2.shape[1]} cols")
    print(f"  [OK] {date_col} dtype preserved: {df2[date_col].dtype}")

    # Step 8: DuckDB verification
    print("\n--- Step 8: DuckDB Parquet verification ---")
    import duckdb

    con = duckdb.connect()
    parquet_str = str(parquet_path).replace("\\", "/")
    result = con.sql(f"SELECT COUNT(*) FROM read_parquet('{parquet_str}')").fetchone()
    duckdb_count = result[0]
    assert duckdb_count == original_shape[0], f"DuckDB count mismatch: expected {original_shape[0]}, got {duckdb_count}"
    print(f"  [OK] DuckDB reads {duckdb_count:,} rows from Parquet")
    con.close()

    # Step 9: Summary
    print("\n--- Step 9: Summary ---")
    compression = csv_size_mb / parquet_size_mb if parquet_size_mb > 0 else float("inf")
    print(f"  CSV size:         {csv_size_mb:.1f} MB")
    print(f"  Parquet size:     {parquet_size_mb:.1f} MB")
    print(f"  Compression:      {compression:.1f}x")
    print(f"  Rows:             {original_shape[0]:,}")
    print(f"  Columns:          {original_shape[1]}")
    print(f"  Date column:      {date_col} -> {dtype_after}")

    print("\n" + "=" * 60)
    print("=== SMOKE TEST PASSED ===")
    print("=" * 60)


if __name__ == "__main__":
    try:
        cfg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
        main(cfg)
        sys.exit(0)
    except Exception as exc:
        print(f"\n{'=' * 60}")
        print("=== SMOKE TEST FAILED ===")
        print(f"{'=' * 60}")
        print(f"Error: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
