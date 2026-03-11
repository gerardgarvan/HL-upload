"""Phase 6: Assemble clean Parquet, derived patient-level, and reports.

Small-cell: all report counts use flag_small_cell per REQ-05.

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

from src.clean.outcomes_flags import add_modality_flags
from src.load.config import load_config
from src.load.schema import parse_datastructure, resolve_table_name
from src.report.encounter_payer_summary import build_encounter_payer_summary
from src.report.quality_report import (
    aggregate_dq_metrics,
    build_patient_level_derived,
    generate_cleaning_decisions_content,
)
from src.validate.structural import flag_small_cell

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_table_map(table_filenames: list[str], parquet_dir: Path) -> dict[str, Path]:
    """Build mapping from table_name -> parquet_path."""
    table_map: dict[str, Path] = {}
    for filename in table_filenames:
        stem = Path(filename).stem
        table_name = resolve_table_name(stem)
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
    derived_dir = paths.derived_dir
    reports_dir = PROJECT_ROOT / "reports"

    parquet_clean_dir.mkdir(parents=True, exist_ok=True)
    derived_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

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
    print("\n--- Build patient_level.parquet ---")
    patient_df = build_patient_level_derived(table_map)

    # Add modality flags from Outcomes.csv (Phase 7)
    outcomes_path = PROJECT_ROOT / "Outcomes.csv"
    if outcomes_path.exists():
        patient_df = add_modality_flags(patient_df, table_map, outcomes_path)
        print(f"  Modality flags added from {outcomes_path.name}")
    else:
        print("  SKIP modality flags (Outcomes.csv not found)")

    patient_path = derived_dir / "patient_level.parquet"
    patient_df.write_parquet(patient_path, compression="snappy")
    print(f"  Rows: {patient_df.height:,}")
    print(f"  Written: {patient_path}")

    # Encounter-payer summary (Phase 14)
    enc_summary = build_encounter_payer_summary(table_map)
    if not enc_summary.is_empty():
        enc_path = derived_dir / "encounter_payer_summary.parquet"
        enc_summary.write_parquet(enc_path, compression="snappy")
        print(f"  encounter_payer_summary.parquet -> {enc_path} ({enc_summary.height:,} rows)")
    else:
        print("  encounter_payer_summary: SKIP (no ENCOUNTER data)")

    # Generate reports
    print("\n--- Generate reports ---")
    dq = aggregate_dq_metrics(table_map, reports_dir)

    # DATA_QUALITY_REPORT.md
    dq_lines: list[str] = []
    dq_lines.append("# Data Quality Report\n")
    dq_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    dq_lines.append(f"**Parquet directory:** {paths.parquet_dir}")
    dq_lines.append(f"**Tables:** {len([p for p in table_map.values() if p.exists()])}\n")

    dq_lines.append("## 1. Overview\n")
    dq_lines.append(f"- Tables processed: {len(table_map)}")
    dq_lines.append(f"- Patient-level derived: {patient_path}")
    dq_lines.append("")

    # 2. Completeness (stratified by SOURCE/partner)
    dq_lines.append("## 2. Completeness (per-field non-null by partner)\n")
    comp = dq.get("completeness", {})
    if comp.get("source") == "csv" and "df" in comp:
        cdf = comp["df"]
        for row in cdf.iter_rows(named=True):
            partner = row.get("SOURCE", row.get("SITE", "ALL"))
            tbl = row.get("table", "")
            col = row.get("column", "")
            comp_val = row.get("completeness")
            rc = int(row.get("row_count", 0))
            pct = f"{comp_val * 100:.1f}%" if comp_val is not None else "N/A"
            dq_lines.append(f"- **{tbl}.{col}** | {partner} | {flag_small_cell(rc)} rows | {pct}")
    elif comp.get("source") == "parquet" and "tables" in comp:
        for item in comp["tables"]:
            tbl = item["table"]
            cdf = item["df"]
            for row in cdf.iter_rows(named=True):
                partner = row.get("SOURCE", row.get("SITE", "ALL"))
                col = row.get("column", "")
                comp_val = row.get("completeness")
                rc = int(row.get("row_count", 0))
                pct = f"{comp_val * 100:.1f}%" if comp_val is not None else "N/A"
                dq_lines.append(f"- **{tbl}.{col}** | {partner} | {flag_small_cell(rc)} rows | {pct}")
    else:
        dq_lines.append("No completeness data available.")
    dq_lines.append("")

    # 3. Conformance (invalid code summaries)
    dq_lines.append("## 3. Conformance (invalid code counts)\n")
    conf = dq.get("conformance", {}).get("invalid_counts", [])
    for r in conf:
        dq_lines.append(f"- **{r['table']}.{r['check']}**: {flag_small_cell(r['count'])}")
    if not conf:
        dq_lines.append("No conformance flags.")
    dq_lines.append("")

    # 4. Plausibility (out-of-range, temporal)
    dq_lines.append("## 4. Plausibility (range, temporal violations)\n")
    plaus = dq.get("plausibility", {}).get("flagged_counts", [])
    for r in plaus:
        dq_lines.append(f"- **{r['table']}.{r['check']}**: {flag_small_cell(r['count'])}")
    if not plaus:
        dq_lines.append("No plausibility flags.")
    dq_lines.append("")

    # 5. Persistence (volume over time by partner)
    dq_lines.append("## 5. Persistence (volume over time by partner)\n")
    pers = dq.get("persistence", {})
    by_year = pers.get("by_year", [])
    if by_year:
        for row in by_year:
            src = row.get("SOURCE", "ALL")
            yr = row.get("year", "")
            n = row.get("n", 0)
            dq_lines.append(f"- {src} | {yr} | {flag_small_cell(n)} encounters")
    else:
        dq_lines.append("No persistence data (ENCOUNTER.ADMIT_DATE).")
    dq_lines.append("")

    dq_path = reports_dir / "DATA_QUALITY_REPORT.md"
    dq_path.write_text("\n".join(dq_lines), encoding="utf-8")
    print(f"  Written: {dq_path}")

    # CLEANING_DECISIONS.md
    cd_lines = generate_cleaning_decisions_content()
    cd_lines.insert(1, f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    cd_lines.insert(2, "Reference: Phase 3–5 reports (structural, values, cohort, dedup, harmonization).\n")
    cd_path = reports_dir / "CLEANING_DECISIONS.md"
    cd_path.write_text("\n".join(cd_lines), encoding="utf-8")
    print(f"  Written: {cd_path}")

    # figures/ directory
    figures_dir = reports_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    print(f"  figures/: {figures_dir}")

    print(f"\n{'=' * 60}")
    print("  ASSEMBLE CLEAN COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Tables copied:     {copied}")
    print(f"  patient_level:     {patient_df.height:,} rows")
    print(f"  parquet_clean:     {parquet_clean_dir}")
    print(f"  derived:           {patient_path}")
    print(f"  Reports:           {dq_path}, {cd_path}")
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
