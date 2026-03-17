"""CSV-to-Parquet conversion for all OneFlorida+ PCORnet CDM tables.

Reads all 22 CSVs listed in datastructure.txt, auto-detects and converts date
columns, writes Parquet files with snappy compression, and produces
file_inventory.csv with per-table metadata.

Usage:
    python scripts/convert_all.py [config/paths.toml]

Designed for HPC interactive sessions (srun --pty bash), not batch SLURM jobs.
Always reconverts all tables (no skip-existing logic).
"""

import sys
import time
from pathlib import Path

import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.load.config import load_and_validate_config
from src.load.convert import convert_table, write_inventory
from src.load.schema import parse_datastructure, resolve_table_name
from src.validate.checkpoint import validate_row_count, CheckpointError


def main(config_path: Path | None = None) -> None:
    """Phase 2: Convert all OneFlorida+ PCORnet CDM CSV files to typed Parquet with snappy compression.

    Entry point for the conversion pipeline. Reads 22 CSV tables listed in datastructure.txt,
    auto-detects and converts date columns (using 4-format fallback: DATETIME, DATE9, YYYYMMDD, MM/DD/YYYY),
    writes Parquet files with snappy compression, and produces file_inventory.csv with per-table
    metadata (row counts, file sizes, date columns detected/converted).

    Re-converts all tables on every run (no skip-existing logic; see CONCERNS.md for incremental
    conversion discussion). Uses mtime check to skip tables where CSV hasn't changed since last run.

    Designed for HPC interactive sessions (srun --pty bash), not batch SLURM jobs. Typical run
    time: 5-10 minutes for full dataset depending on CSV sizes. Exits with code 1 if any table
    conversion fails (fail-fast behavior to avoid cascading errors).

    Creates parquet_dir if it doesn't exist. Writes file_inventory.csv to parquet_dir parent directory.
    Prints progress for each table (row counts, date columns found, elapsed time) and final summary
    (total rows, total Parquet size, overall elapsed time) to stdout.

    Args:
        config_path: Optional path to config/paths.toml (uses default if None)

    Raises:
        SystemExit: If any table conversion fails or unrecoverable error occurs
    """
    print("=" * 60)
    print("HL DATA LOADING & CLEANING — CSV TO PARQUET CONVERSION")
    print("=" * 60)

    paths = load_and_validate_config(config_path)
    print(f"\n  data_root:    {paths.data_root}")
    print(f"  scratch_root: {paths.scratch_root}")
    print(f"  parquet_dir:  {paths.parquet_dir}")

    _, table_filenames = parse_datastructure(paths.datastructure_path)
    print(f"\n  Tables to convert: {len(table_filenames)}")
    for t in table_filenames:
        print(f"    - {t}")

    paths.parquet_dir.mkdir(parents=True, exist_ok=True)

    overall_start = time.time()
    inventory_records: list[dict] = []
    total_csv_rows = 0
    total_parquet_bytes = 0
    empty_count = 0

    for i, filename in enumerate(table_filenames, 1):
        csv_path = paths.data_root / filename
        stem = Path(filename).stem
        table_name = resolve_table_name(stem)
        parquet_path = paths.parquet_dir / (stem + ".parquet")

        print(f"\n{'=' * 60}")
        print(f"  [{i}/{len(table_filenames)}] {table_name}")
        print(f"  File: {filename}")
        print(f"{'=' * 60}")

        if parquet_path.exists() and csv_path.exists() and csv_path.stat().st_mtime <= parquet_path.stat().st_mtime:
            parquet_df = pl.read_parquet(parquet_path)
            record = {
                "table_name": table_name,
                "csv_file": filename,
                "parquet_file": parquet_path.name,
                "csv_rows": parquet_df.height,
                "parquet_rows": parquet_df.height,
                "csv_bytes": csv_path.stat().st_size,
                "parquet_bytes": parquet_path.stat().st_size,
                "date_columns_found": 0,
                "date_columns_converted": 0,
                "date_columns_kept_string": 0,
                "elapsed_seconds": 0,
                "status": "skipped (up-to-date)",
            }
            print(f"  [SKIP] {table_name} — Parquet up-to-date (CSV mtime <= Parquet mtime)")
        else:
            try:
                record = convert_table(csv_path, paths.parquet_dir)

                # Row count checkpoint: strict validation (Parquet rows must equal CSV rows)
                if record["status"] not in ("empty", "skipped (up-to-date)"):
                    validate_row_count(
                        pl.read_parquet(parquet_path),
                        phase="convert",
                        table=table_name,
                        expected=record["csv_rows"],
                        tolerance=0.0,  # Strict: Parquet must have same rows as CSV
                    )
            except CheckpointError:
                print(f"\n  [FATAL] {table_name} checkpoint failed — row count mismatch")
                print("\n  Stopping — cannot continue after checkpoint failure.")
                sys.exit(1)
            except Exception as exc:
                print(f"\n  [FATAL] {table_name} failed: {exc}")
                import traceback

                traceback.print_exc()
                print("\n  Stopping — cannot continue after table failure.")
                sys.exit(1)

        inventory_records.append(record)
        total_csv_rows += record["csv_rows"]
        total_parquet_bytes += record["parquet_bytes"]
        if record["status"] == "empty":
            empty_count += 1

    inventory_path = paths.parquet_dir.parent / "file_inventory.csv"
    write_inventory(inventory_records, inventory_path)

    overall_elapsed = time.time() - overall_start

    print(f"\n{'=' * 60}")
    print("  CONVERSION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Tables processed:  {len(table_filenames)}")
    print(f"  Tables skipped:    {empty_count} (empty)")
    print(f"  Total CSV rows:    {total_csv_rows:,}")
    print(f"  Total Parquet:     {total_parquet_bytes / 1024 / 1024:.1f} MB")
    print(f"  Total elapsed:     {overall_elapsed:.1f}s")
    print(f"  Inventory:         {inventory_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    try:
        cfg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
        main(cfg)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"\n{'=' * 60}")
        print("  CONVERSION FAILED")
        print(f"{'=' * 60}")
        print(f"  Error: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
