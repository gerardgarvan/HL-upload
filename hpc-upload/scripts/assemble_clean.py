"""Phase 6: Assemble clean Parquet, derived patient-level, and reports.

Entry point for assembling validated+flagged Parquet into parquet_clean/,
building patient_level.parquet, and generating DATA_QUALITY_REPORT.md and
CLEANING_DECISIONS.md.

Usage:
    python scripts/assemble_clean.py [config/paths.toml]

Designed for HPC interactive sessions (srun --pty bash).
"""

import sys
from datetime import datetime
from pathlib import Path

import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.load.config import load_config
from src.load.schema import parse_datastructure
from src.report.quality_report import build_patient_level_derived


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_table_map(
    table_filenames: list[str], parquet_dir: Path
) -> dict[str, Path]:
    """Build mapping from table_name -> parquet_path."""
    table_map: dict[str, Path] = {}
    for filename in table_filenames:
        stem = Path(filename).stem
        table_name = stem.split("_Mailhot_V1")[0]
        parquet_path = parquet_dir / (stem + ".parquet")
        table_map[table_name] = parquet_path
    return table_map


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(config_path: Path | None = None) -> None:
    print("=" * 60)
    print("HL ASSEMBLE CLEAN — Parquet Copy, Derived, Reports")
    print("=" * 60)

    paths = load_config(config_path)
    print(f"\n  parquet_dir: {paths.parquet_dir}")

    _, table_filenames = parse_datastructure(paths.datastructure_path)
    table_map = _build_table_map(table_filenames, paths.parquet_dir)

    parquet_clean_dir = paths.parquet_dir.parent / "parquet_clean"
    derived_dir = paths.parquet_dir.parent / "derived"

    parquet_clean_dir.mkdir(parents=True, exist_ok=True)
    derived_dir.mkdir(parents=True, exist_ok=True)

    # Copy Parquet to parquet_clean (snappy compression)
    print(f"\n--- Copy Parquet to {parquet_clean_dir} ---")
    copied = 0
    for table_name, src_path in sorted(table_map.items()):
        if not src_path.exists():
            print(f"  SKIP {table_name} (not found)")
            continue
        dst_path = parquet_clean_dir / src_path.name
        df = pl.read_parquet(src_path)
        df.write_parquet(dst_path, compression="snappy")
        copied += 1
        print(f"  {table_name} -> {dst_path.name}")
    print(f"  Copied {copied} tables")

    # Build patient_level.parquet
    print(f"\n--- Build patient_level.parquet ---")
    patient_df = build_patient_level_derived(table_map)
    patient_path = derived_dir / "patient_level.parquet"
    patient_df.write_parquet(patient_path, compression="snappy")
    print(f"  Rows: {patient_df.height:,}")
    print(f"  Written: {patient_path}")

    print(f"\n{'=' * 60}")
    print("  ASSEMBLE CLEAN COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Tables copied:     {copied}")
    print(f"  patient_level:     {patient_df.height:,} rows")
    print(f"  parquet_clean:     {parquet_clean_dir}")
    print(f"  derived:           {patient_path}")
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
        print("  ASSEMBLE CLEAN FAILED")
        print(f"{'=' * 60}")
        print(f"  Error: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
