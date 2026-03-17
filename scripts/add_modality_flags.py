"""Add modality flags to existing patient_level.parquet from Outcomes.csv.

Usage:
    python scripts/add_modality_flags.py [config/paths.toml]

Reads patient_level.parquet, PROCEDURES, LAB_RESULT_CM, DIAGNOSIS from parquet_dir,
adds MODALITY_* columns using Outcomes.csv (project root), writes back to derived/.
Outcomes path: OUTCOMES_PATH env or project root / Outcomes.csv.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.clean.outcomes_flags import add_modality_flags
from src.load.config import load_config
from src.load.schema import parse_datastructure, resolve_table_name


def _build_table_map(table_filenames: list[str], parquet_dir: Path) -> dict[str, Path]:
    """Build mapping from CDM table name to parquet file path.

    Resolves table names using schema.py naming rules (e.g., "DEMOGRAPHIC_Mailhot_V1" → "DEMOGRAPHIC").
    Used to locate source tables (PROCEDURES, LAB_RESULT_CM, DIAGNOSIS) for modality flag lookups.

    Args:
        table_filenames: List of CSV filenames from datastructure.txt
        parquet_dir: Directory containing parquet files

    Returns:
        Dict mapping table name to parquet path (e.g., {"DEMOGRAPHIC": Path("parquet/DEMOGRAPHIC_Mailhot_V1.parquet")})
    """
    table_map: dict[str, Path] = {}
    for filename in table_filenames:
        stem = Path(filename).stem
        table_name = resolve_table_name(stem)
        table_map[table_name] = parquet_dir / (stem + ".parquet")
    return table_map


def main(config_path: Path | None = None) -> None:
    """Add modality treatment flags to existing patient_level.parquet.

    Reads patient_level.parquet from derived/, looks up treatment codes from Outcomes.csv
    (MODALITY columns: Chemotherapy, Radiation, Stem Cell Transplant), adds binary flag columns
    (HAD_CHEMO, HAD_RADIATION, HAD_SCT, etc.), and writes back to derived/patient_level.parquet.

    This is a standalone utility script for re-adding modality flags without re-running
    the full assemble_clean.py pipeline. Typically used when Outcomes.csv is updated.

    Outputs patient_level.parquet with added modality columns to derived/ directory.

    Args:
        config_path: Optional path to config/paths.toml (uses default if None)

    Raises:
        SystemExit: If patient_level.parquet or Outcomes.csv not found
    """
    paths = load_config(config_path)
    _, table_filenames = parse_datastructure(paths.datastructure_path)
    table_map = _build_table_map(table_filenames, paths.parquet_dir)

    derived_dir = paths.derived_dir
    patient_path = derived_dir / "patient_level.parquet"
    outcomes_path = Path(os.environ.get("OUTCOMES_PATH", str(PROJECT_ROOT / "Outcomes.csv")))

    if not patient_path.exists():
        print(f"Error: {patient_path} not found. Run assemble_clean.py first.")
        sys.exit(1)
    if not outcomes_path.exists():
        print(f"Error: {outcomes_path} not found.")
        sys.exit(1)

    import polars as pl

    patient_df = pl.read_parquet(patient_path)
    patient_df = add_modality_flags(patient_df, table_map, outcomes_path)
    patient_df.write_parquet(patient_path, compression="snappy")
    print(f"Modality flags added. Written: {patient_path}")


if __name__ == "__main__":
    try:
        cfg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
        main(cfg)
    except Exception as exc:
        print(f"Error: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
