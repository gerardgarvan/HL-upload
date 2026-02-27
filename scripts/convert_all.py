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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.load.config import load_config
from src.load.convert import convert_table, write_inventory
from src.load.schema import parse_datastructure


def main(config_path: Path | None = None) -> None:
    print("=" * 60)
    print("HL DATA LOADING & CLEANING — CSV TO PARQUET CONVERSION")
    print("=" * 60)

    paths = load_config(config_path)
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
        table_name = filename.split("_Mailhot_V1")[0]

        print(f"\n{'=' * 60}")
        print(f"  [{i}/{len(table_filenames)}] {table_name}")
        print(f"  File: {filename}")
        print(f"{'=' * 60}")

        try:
            record = convert_table(csv_path, paths.parquet_dir)
        except Exception as exc:
            print(f"\n  [FATAL] {table_name} failed: {exc}")
            import traceback
            traceback.print_exc()
            print(f"\n  Stopping — cannot continue after table failure.")
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
        print(f"  CONVERSION FAILED")
        print(f"{'=' * 60}")
        print(f"  Error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
