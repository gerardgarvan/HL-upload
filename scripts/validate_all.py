"""Structural validation for all OneFlorida+ PCORnet CDM Parquet tables.

Compares schemas against DatasetCoverPage, checks PATID/ENCOUNTERID
referential integrity, profiles per-partner completeness, and generates
reports/structural_validation.md + reports/completeness_by_partner.csv.

Usage:
    python scripts/validate_all.py [config/paths.toml]

Designed for HPC interactive sessions (srun --pty bash).
"""

import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.load.config import load_config
from src.load.schema import parse_datastructure
from src.validate.structural import (
    ENCOUNTER_LINKED_TABLES,
    PATID_COL,
    PATID_LINKED_TABLES,
    TUMOR_REGISTRY_EXPECTED_COUNTS,
    TUMOR_REGISTRY_TABLES,
    check_encounterid_integrity,
    check_patid_integrity,
    check_patid_uniqueness,
    classify_missing_values,
    completeness_by_partner,
    completeness_heatmap_symbol,
    flag_small_cell,
    parse_cover_page,
    validate_table_schema,
)

import polars as pl


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
# Report sections
# ---------------------------------------------------------------------------


def _section_schema(
    schema_results: list[dict],
) -> str:
    """Generate Section 1: Schema Validation."""
    lines: list[str] = []
    lines.append("## 1. Schema Validation\n")

    cdm_results = [r for r in schema_results if r["table"] not in TUMOR_REGISTRY_TABLES]
    tr_results = [r for r in schema_results if r["table"] in TUMOR_REGISTRY_TABLES]

    lines.append("### Summary\n")
    lines.append("| Table | Expected Cols | Actual Cols | Matched | Extra | Missing | Status |")
    lines.append("|-------|--------------|-------------|---------|-------|---------|--------|")
    for r in cdm_results:
        exp = r["expected_col_count"] if r["expected_col_count"] is not None else "N/A"
        lines.append(
            f"| {r['table']} | {exp} | {r['actual_col_count']} "
            f"| {r['matched']} | {len(r['extra'])} | {len(r['missing'])} | {r['status']} |"
        )

    details = [r for r in cdm_results if r["extra"] or r["missing"]]
    if details:
        lines.append("\n### Details\n")
        for r in details:
            lines.append(f"**{r['table']}**\n")
            if r["extra"]:
                lines.append(f"- Extra columns: {', '.join(r['extra'])}")
            if r["missing"]:
                lines.append(f"- Missing columns: {', '.join(r['missing'])}")
            lines.append("")

    if tr_results:
        lines.append("### TUMOR_REGISTRY Tables\n")
        lines.append("| Table | Expected Cols | Actual Cols | Key Vars Present | Status | Details |")
        lines.append("|-------|--------------|-------------|-----------------|--------|---------|")
        for r in tr_results:
            exp = r["expected_col_count"] if r["expected_col_count"] is not None else "N/A"
            detail_str = "; ".join(r["details"]) if r["details"] else "—"
            lines.append(
                f"| {r['table']} | {exp} | {r['actual_col_count']} "
                f"| {r['matched']} | {r['status']} | {detail_str} |"
            )
        lines.append("")

    return "\n".join(lines)


def _section_integrity(
    patid_unique: dict,
    patid_results: list[dict],
    enc_results: list[dict],
) -> str:
    """Generate Section 2: Key Integrity."""
    lines: list[str] = []
    lines.append("## 2. Key Integrity\n")

    lines.append("### PATID Uniqueness (DEMOGRAPHIC)\n")
    lines.append(f"- Total rows: {patid_unique['total_rows']:,}")
    lines.append(f"- Unique IDs: {patid_unique['unique_ids']:,}")
    lines.append(f"- Duplicates: {flag_small_cell(patid_unique['duplicate_ids'])}")
    lines.append(f"- Is unique: {'Yes' if patid_unique['is_unique'] else 'No'}")
    lines.append("")

    lines.append("### PATID Referential Integrity\n")
    lines.append("| Table | Unique IDs | Orphan IDs | Orphan % |")
    lines.append("|-------|-----------|------------|----------|")
    for r in patid_results:
        lines.append(
            f"| {r['table']} | {r['unique_ids']:,} "
            f"| {flag_small_cell(r['orphan_ids'])} | {r['orphan_pct']:.2f}% |"
        )
    lines.append("")

    lines.append("### ENCOUNTERID Referential Integrity\n")
    lines.append("| Table | Unique ENCOUNTERIDs | Orphan ENCOUNTERIDs | Orphan % | Notes |")
    lines.append("|-------|--------------------|--------------------|----------|-------|")
    for r in enc_results:
        if r.get("skipped"):
            lines.append(
                f"| {r['table']} | — | — | — | {r.get('reason', 'skipped')} |"
            )
        else:
            notes = ""
            if r.get("skip_partner"):
                notes = f"{r['skip_partner']} records excluded"
            lines.append(
                f"| {r['table']} | {r['unique_encounterids']:,} "
                f"| {flag_small_cell(r['orphan_encounterids'])} "
                f"| {r['orphan_pct']:.2f}% | {notes} |"
            )

    lines.append("")
    lines.append("> **Note:** CHP LAB_RESULT_CM skipped per DatasetCoverPage known limitation\n")

    return "\n".join(lines)


def _section_completeness(
    comp_df: pl.DataFrame,
    table_map: dict[str, Path],
) -> str:
    """Generate Section 3: Completeness by Partner."""
    lines: list[str] = []
    lines.append("## 3. Completeness by Partner\n")

    if comp_df.is_empty():
        lines.append("No completeness data available.\n")
        return "\n".join(lines)

    partner_col = "SOURCE"
    if partner_col not in comp_df.columns:
        for c in comp_df.columns:
            if c not in ("row_count", "column", "completeness", "table"):
                partner_col = c
                break

    lines.append("### Overview Heatmap\n")
    lines.append("Symbols: █ ≥95% | ▓ ≥75% | ▒ ≥50% | ░ ≥25% | · >0% | ○ 0%\n")

    tables_in_data = comp_df["table"].unique().sort().to_list()
    partners = comp_df[partner_col].unique().sort().to_list()

    overview_cols = [PATID_COL, "ENCOUNTERID", "BIRTH_DATE", "SEX", "RACE", "HISPANIC"]
    available_overview = [c for c in overview_cols if c in comp_df["column"].unique().to_list()]

    if available_overview:
        header = "| Partner | " + " | ".join(available_overview) + " |"
        sep = "|---------|" + "|".join(["------" for _ in available_overview]) + "|"
        lines.append(header)
        lines.append(sep)

        for partner in partners:
            row = f"| {partner} "
            for col in available_overview:
                match = comp_df.filter(
                    (pl.col(partner_col) == partner) & (pl.col("column") == col)
                )
                if match.is_empty():
                    row += "| — "
                else:
                    tables_with_col = match["table"].unique().to_list()
                    avg_pct = match["completeness"].mean()
                    if avg_pct is not None:
                        sym = completeness_heatmap_symbol(avg_pct)
                        row += f"| {sym} {avg_pct:.0%} "
                    else:
                        row += "| — "
                row += ""
            row += "|"
            lines.append(row)
        lines.append("")

    lines.append("### Key Insurance Variables\n")
    ins_cols = ["PAYER_TYPE_PRIMARY", "PAYER_TYPE_SECONDARY", "RAW_PAYER_TYPE_PRIMARY"]
    available_ins = [c for c in ins_cols if c in comp_df["column"].unique().to_list()]

    if available_ins:
        header = "| Partner | " + " | ".join(available_ins) + " |"
        sep = "|---------|" + "|".join(["------" for _ in available_ins]) + "|"
        lines.append(header)
        lines.append(sep)

        for partner in partners:
            row = f"| {partner} "
            for col in available_ins:
                match = comp_df.filter(
                    (pl.col(partner_col) == partner) & (pl.col("column") == col)
                )
                if match.is_empty():
                    row += "| — "
                else:
                    pct = match["completeness"].mean()
                    if pct is not None:
                        sym = completeness_heatmap_symbol(pct)
                        row += f"| {sym} {pct:.0%} "
                    else:
                        row += "| — "
            row += "|"
            lines.append(row)
        lines.append("")
    else:
        lines.append("No insurance variables found in completeness data.\n")

    lines.append("### Per-Table Detail\n")

    for table in tables_in_data:
        tbl_data = comp_df.filter(pl.col("table") == table)
        cols_in_table = tbl_data["column"].unique().sort().to_list()

        if len(cols_in_table) > 20:
            display_cols = cols_in_table[:20]
            truncated = True
        else:
            display_cols = cols_in_table
            truncated = False

        lines.append(f"#### {table}\n")

        tbl_partners = tbl_data[partner_col].unique().sort().to_list()

        header = "| Partner | " + " | ".join(display_cols) + " |"
        sep = "|---------|" + "|".join(["------" for _ in display_cols]) + "|"
        lines.append(header)
        lines.append(sep)

        for partner in tbl_partners:
            row = f"| {partner} "
            for col in display_cols:
                match = tbl_data.filter(
                    (pl.col(partner_col) == partner) & (pl.col("column") == col)
                )
                if match.is_empty():
                    row += "| — "
                else:
                    pct = match["completeness"][0]
                    if pct is not None:
                        sym = completeness_heatmap_symbol(pct)
                        row += f"| {sym} {pct:.0%} "
                    else:
                        row += "| — "
            row += "|"
            lines.append(row)

        if truncated:
            lines.append(f"\n*Showing first 20 of {len(cols_in_table)} columns*\n")
        lines.append("")

    return "\n".join(lines)


def _section_missing(missing_df: pl.DataFrame) -> str:
    """Generate Section 4: Missing Value Classification."""
    lines: list[str] = []
    lines.append("## 4. Missing Value Classification\n")

    lines.append("### PCORnet Coded Values\n")

    if missing_df.is_empty():
        lines.append("No string columns found for missing value classification.\n")
        return "\n".join(lines)

    has_coded = missing_df.filter(
        (pl.col("ni_count") > 0)
        | (pl.col("un_count") > 0)
        | (pl.col("ot_count") > 0)
        | (pl.col("empty_count") > 0)
    )

    if has_coded.is_empty():
        lines.append("No PCORnet coded missing values (NI/UN/OT/empty) found.\n")
    else:
        display = has_coded.head(100)

        lines.append("| Table | Column | NI | UN | OT | Empty | Null | Total |")
        lines.append("|-------|--------|-----|-----|-----|-------|------|-------|")
        for row in display.iter_rows(named=True):
            lines.append(
                f"| {row['table']} | {row['column']} "
                f"| {flag_small_cell(row['ni_count'])} "
                f"| {flag_small_cell(row['un_count'])} "
                f"| {flag_small_cell(row['ot_count'])} "
                f"| {row['empty_count']:,} "
                f"| {row['null_count']:,} "
                f"| {row['total_rows']:,} |"
            )

        if has_coded.height > 100:
            lines.append(f"\n*Showing first 100 of {has_coded.height} columns with coded values*\n")

    lines.append("")
    lines.append("### Handling Rules\n")
    lines.append("- **NI** (No Information): Treat as missing, include in completeness denominator")
    lines.append("- **UN** (Unknown): Treat as missing, include in completeness denominator")
    lines.append("- **OT** (Other): Valid response — value exists but outside defined categories")
    lines.append("- **Empty string**: Treat as null")
    lines.append("- **NULL**: Standard missing")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(config_path: Path | None = None) -> None:
    print("=" * 60)
    print("HL DATA LOADING & CLEANING — STRUCTURAL VALIDATION")
    print("=" * 60)

    paths = load_config(config_path)
    print(f"\n  data_root:    {paths.data_root}")
    print(f"  parquet_dir:  {paths.parquet_dir}")

    _, table_filenames = parse_datastructure(paths.datastructure_path)
    table_map = _build_table_map(table_filenames, paths.parquet_dir)
    print(f"\n  Tables found: {len(table_map)}")

    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    overall_start = time.time()

    # ----- DatasetCoverPage -----
    cover_page_path = None
    cover_page_cols: dict[str, list[str]] = {}

    for candidate in sorted(paths.data_root.glob("DatasetCoverPage*.txt")):
        cover_page_path = candidate
        break

    if cover_page_path:
        print(f"\n  DatasetCoverPage: {cover_page_path}")
        cover_page_cols = parse_cover_page(cover_page_path)
        print(f"  Tables parsed: {len(cover_page_cols)}")
    else:
        print("\n  [WARN] DatasetCoverPage not found — schema comparison skipped")

    # ----- 1. Schema validation -----
    print(f"\n{'─' * 60}")
    print("  SECTION 1: Schema Validation")
    print(f"{'─' * 60}")

    schema_results: list[dict] = []
    for table_name, pq_path in sorted(table_map.items()):
        if not pq_path.exists():
            print(f"  [SKIP] {table_name} — parquet not found")
            continue

        expected = cover_page_cols.get(table_name)
        is_tr = table_name in TUMOR_REGISTRY_TABLES
        exp_count = TUMOR_REGISTRY_EXPECTED_COUNTS.get(table_name)

        result = validate_table_schema(
            pq_path, expected, table_name,
            is_tumor_registry=is_tr,
            expected_col_count=exp_count,
        )
        schema_results.append(result)

        status_icon = "OK" if result["status"] == "ok" else "WARN"
        print(f"  [{status_icon}] {table_name}: {result['actual_col_count']} cols", end="")
        if result["details"]:
            print(f" — {'; '.join(result['details'])}")
        else:
            print()

    # ----- 2. Key integrity -----
    print(f"\n{'─' * 60}")
    print("  SECTION 2: Key Integrity")
    print(f"{'─' * 60}")

    demo_path = table_map.get("DEMOGRAPHIC")
    enc_path = table_map.get("ENCOUNTER")

    patid_unique = {"total_rows": 0, "unique_ids": 0, "duplicate_ids": 0, "is_unique": False}
    if demo_path and demo_path.exists():
        patid_unique = check_patid_uniqueness(demo_path)
        print(f"  DEMOGRAPHIC: {patid_unique['total_rows']:,} rows, "
              f"{patid_unique['unique_ids']:,} unique IDs, "
              f"{patid_unique['duplicate_ids']} duplicates")
    else:
        print("  [SKIP] DEMOGRAPHIC not found")

    patid_results: list[dict] = []
    if demo_path and demo_path.exists():
        for table_name in PATID_LINKED_TABLES:
            child_path = table_map.get(table_name)
            if not child_path or not child_path.exists():
                print(f"  [SKIP] {table_name} — not found")
                continue
            result = check_patid_integrity(child_path, demo_path, table_name)
            patid_results.append(result)
            print(f"  {table_name}: {result['unique_ids']:,} unique IDs, "
                  f"{result['orphan_ids']} orphans ({result['orphan_pct']:.2f}%)")

    enc_results: list[dict] = []
    if enc_path and enc_path.exists():
        for table_name in ENCOUNTER_LINKED_TABLES:
            child_path = table_map.get(table_name)
            if not child_path or not child_path.exists():
                print(f"  [SKIP] {table_name} — not found")
                continue

            skip = "CHP" if table_name == "LAB_RESULT_CM" else None
            result = check_encounterid_integrity(
                child_path, enc_path, table_name, skip_partner=skip
            )
            enc_results.append(result)

            if result.get("skipped"):
                print(f"  {table_name}: skipped ({result.get('reason')})")
            else:
                note = f" [{result['skip_partner']} excluded]" if result.get("skip_partner") else ""
                print(f"  {table_name}: {result['unique_encounterids']:,} unique ENCOUNTERIDs, "
                      f"{result['orphan_encounterids']} orphans ({result['orphan_pct']:.2f}%){note}")
    else:
        print("  [SKIP] ENCOUNTER not found — ENCOUNTERID checks skipped")

    # ----- 3. Completeness -----
    print(f"\n{'─' * 60}")
    print("  SECTION 3: Completeness by Partner")
    print(f"{'─' * 60}")

    comp_frames: list[pl.DataFrame] = []
    for table_name, pq_path in sorted(table_map.items()):
        if not pq_path.exists():
            continue
        frame = completeness_by_partner(pq_path, table_name)
        if not frame.is_empty():
            comp_frames.append(frame)
            partners = frame["SOURCE"].n_unique() if "SOURCE" in frame.columns else 0
            print(f"  {table_name}: {partners} partners profiled")

    comp_df = pl.concat(comp_frames) if comp_frames else pl.DataFrame()

    # ----- 4. Missing value classification -----
    print(f"\n{'─' * 60}")
    print("  SECTION 4: Missing Value Classification")
    print(f"{'─' * 60}")

    missing_frames: list[pl.DataFrame] = []
    for table_name, pq_path in sorted(table_map.items()):
        if not pq_path.exists():
            continue
        frame = classify_missing_values(pq_path, table_name)
        if not frame.is_empty():
            missing_frames.append(frame)
            coded = frame.filter(
                (pl.col("ni_count") > 0)
                | (pl.col("un_count") > 0)
                | (pl.col("ot_count") > 0)
            )
            print(f"  {table_name}: {frame.height} string cols, {coded.height} with coded values")

    missing_df = pl.concat(missing_frames) if missing_frames else pl.DataFrame()

    # ----- Write CSV -----
    if not comp_df.is_empty():
        csv_path = reports_dir / "completeness_by_partner.csv"
        comp_df.write_csv(csv_path)
        print(f"\n  Completeness CSV: {csv_path}")

    # ----- Assemble report -----
    print(f"\n{'─' * 60}")
    print("  Assembling report...")
    print(f"{'─' * 60}")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report_parts: list[str] = []
    report_parts.append(f"# Structural Validation Report\n")
    report_parts.append(f"**Generated:** {timestamp}")
    report_parts.append(f"**Data source:** {paths.data_root}")
    report_parts.append(f"**Parquet directory:** {paths.parquet_dir}")
    report_parts.append(f"**Tables validated:** {len(schema_results)}\n")

    report_parts.append("## Table of Contents\n")
    report_parts.append("1. [Schema Validation](#1-schema-validation)")
    report_parts.append("2. [Key Integrity](#2-key-integrity)")
    report_parts.append("3. [Completeness by Partner](#3-completeness-by-partner)")
    report_parts.append("4. [Missing Value Classification](#4-missing-value-classification)\n")
    report_parts.append("---\n")

    report_parts.append(_section_schema(schema_results))
    report_parts.append(_section_integrity(patid_unique, patid_results, enc_results))
    report_parts.append(_section_completeness(comp_df, table_map))
    report_parts.append(_section_missing(missing_df))

    report_path = reports_dir / "structural_validation.md"
    report_path.write_text("\n".join(report_parts), encoding="utf-8")

    overall_elapsed = time.time() - overall_start

    # ----- Console summary -----
    total_orphan_patids = sum(r["orphan_ids"] for r in patid_results)
    total_orphan_encs = sum(
        r["orphan_encounterids"] for r in enc_results if not r.get("skipped")
    )

    avg_completeness = comp_df["completeness"].mean() if not comp_df.is_empty() else 0.0

    print(f"\n{'=' * 60}")
    print("  STRUCTURAL VALIDATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Tables validated:     {len(schema_results)}")
    print(f"  Schema warnings:      {sum(1 for r in schema_results if r['status'] == 'warn')}")
    print(f"  PATID unique:         {'Yes' if patid_unique['is_unique'] else 'No'}")
    print(f"  Total orphan PATIDs:  {total_orphan_patids}")
    print(f"  Total orphan ENCIDs:  {total_orphan_encs}")
    print(f"  Avg completeness:     {avg_completeness:.1%}" if avg_completeness else "  Avg completeness:     N/A")
    print(f"  Elapsed:              {overall_elapsed:.1f}s")
    print(f"  Report:               {report_path}")
    print(f"  Completeness CSV:     {reports_dir / 'completeness_by_partner.csv'}")
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
        print(f"  STRUCTURAL VALIDATION FAILED")
        print(f"{'=' * 60}")
        print(f"  Error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
