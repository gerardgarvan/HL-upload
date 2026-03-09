"""Build site-stratified demographic table (Age, Race, Ethnicity, Stage, Insurance).

Small-cell: site_table.build_site_summary_table applies flag_small_cell per REQ-05.

Each patient is assigned to their predominant SOURCE (site). TMA and TMC are
combined into TM. Output: CSV and Markdown table.

Usage:
    python scripts/build_site_table.py [config/paths.toml]
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.load.config import load_config
from src.load.schema import parse_datastructure, resolve_table_name
from src.report.site_table import build_site_table, build_site_summary_table, build_site_summary_html


def _build_table_map(
    table_filenames: list[str], parquet_dir: Path
) -> dict[str, Path]:
    """Build mapping from table_name -> parquet_path."""
    table_map: dict[str, Path] = {}
    for filename in table_filenames:
        stem = Path(filename).stem
        table_name = resolve_table_name(stem)
        parquet_path = parquet_dir / (stem + ".parquet")
        table_map[table_name] = parquet_path
    return table_map


def main(config_path: Path | None = None) -> None:
    print("=" * 60)
    print("HL SITE STRATIFIED TABLE — Age, Race, Ethnicity, Stage, Insurance")
    print("=" * 60)

    paths = load_config(config_path)
    print(f"\n  parquet_dir: {paths.parquet_dir}")

    _, table_filenames = parse_datastructure(paths.datastructure_path)
    table_map = _build_table_map(table_filenames, paths.parquet_dir)

    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    print("\n--- Build patient-level site table ---")
    patient_df = build_site_table(table_map)
    if patient_df.is_empty():
        print("  No patients with predominant site. Exiting.")
        return
    print(f"  Rows: {patient_df.height:,}")
    print(f"  Sites: {patient_df['SITE'].unique().sort().to_list()}")

    print("\n--- Build site summary table ---")
    summary = build_site_summary_table(patient_df)
    if summary.is_empty():
        print("  Summary table is empty.")
        return

    csv_path = reports_dir / "site_stratified_table.csv"
    md_path = reports_dir / "site_stratified_table.md"
    html_path = reports_dir / "site_stratified_table.html"
    summary.write_csv(csv_path)
    print(f"  CSV:  {csv_path}")

    html_path.write_text(build_site_summary_html(summary), encoding="utf-8")
    print(f"  HTML: {html_path}")

    # Markdown table
    cols = summary.columns
    md_lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in summary.iter_rows(named=True):
        md_lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"  MD:  {md_path}")

    print("\nDone.")


if __name__ == "__main__":
    cfg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(cfg)
