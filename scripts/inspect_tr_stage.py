"""Inspect TUMOR_REGISTRY stage columns and values (run on HPC where parquet exists).

Usage:
    python scripts/inspect_tr_stage.py [config/paths.toml]
"""

import sys
from pathlib import Path

import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.load.config import load_config
from src.load.schema import parse_datastructure

TUMOR_REGISTRY_TABLES = {"TUMOR_REGISTRY1", "TUMOR_REGISTRY2", "TUMOR_REGISTRY3"}
PATID_COL = "ID"
HL_HISTOLOGY = set(range(9650, 9668))


def main(config_path: Path | None = None):
    """Inspect TUMOR_REGISTRY table schemas and stage-related columns.

    Debugging utility to explore TUMOR_REGISTRY1/2/3 Parquet files. Prints row counts,
    stage-related column names, unique values for stage columns (first 20), HISTOLOGY counts
    (including HL-specific codes 9650-9667), and unique patient IDs.

    Run on HPC where parquet files are available. Helps understand what stage variables
    exist in tumor registry data before designing validation logic.

    Prints output to stdout showing table name, row count, stage columns, and sample values.

    Args:
        config_path: Optional path to config/paths.toml (uses default if None)
    """
    paths = load_config(config_path)
    _, filenames = parse_datastructure(paths.datastructure_path)
    parquet_dir = paths.parquet_dir

    for name in sorted(TUMOR_REGISTRY_TABLES):
        stem = next((f.replace(".csv", "") for f in filenames if name in f and "Mailhot" in f), None)
        if not stem:
            continue
        pq = parquet_dir / (stem + ".parquet")
        if not pq.exists():
            print(f"\n{name}: NOT FOUND ({pq})")
            continue
        df = pl.scan_parquet(pq)
        schema = df.collect_schema()
        cols = schema.names()
        stage_cols = [c for c in cols if "STAGE" in c.upper()]
        print(f"\n{name}: {pq.name}")
        print(f"  Rows: {df.collect().height}")
        print(f"  Stage-related columns: {stage_cols or '(none)'}")

        for sc in stage_cols[:3]:  # inspect first 3
            vals = df.select(sc).drop_nulls().filter(pl.col(sc).cast(pl.String).str.strip_chars() != "").collect()
            if vals.height > 0:
                uniq = vals[sc].unique().head(20).to_list()
                print(f"  {sc} unique (max 20): {uniq}")

        if "HISTOLOGY" in cols:
            h = df.select("HISTOLOGY").drop_nulls().collect()
            print(f"  HISTOLOGY non-null: {h.height}")
            hl_hist = pl.col("HISTOLOGY").cast(pl.Float64, strict=False).cast(pl.Int64, strict=False)
            hl_count = df.filter(hl_hist.is_in(list(HL_HISTOLOGY))).collect().height
            print(f"  HISTOLOGY in 9650-9667 (HL): {hl_count}")

        if PATID_COL in cols:
            n_ids = df.select(PATID_COL).unique().collect().height
            print(f"  Unique {PATID_COL}: {n_ids}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
