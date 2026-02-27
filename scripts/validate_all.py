"""Structural validation and HL cohort verification for OneFlorida+ PCORnet CDM.

Compares schemas against DatasetCoverPage, checks PATID/ENCOUNTERID
referential integrity, profiles per-partner completeness, verifies the
HL cohort (149 ICD codes, dual-date methods, enrollment cross-check),
and generates reports/structural_validation.md, completeness_by_partner.csv,
and cohort_summary.csv.

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
from src.validate.cohort import (
    ALL_HL_CODES,
    verify_hl_cohort,
    enrollment_crosscheck,
    build_cohort_summary_df,
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
# Section 5: HL Cohort Verification
# ---------------------------------------------------------------------------


def _section_cohort(
    cohort_result: dict,
    enrollment_result: dict | None = None,
) -> str:
    """Generate Section 5: HL Cohort Verification."""
    lines: list[str] = []
    lines.append("## 5. HL Cohort Verification\n")

    # --- Cohort Definition ---
    lines.append("### Cohort Definition")
    lines.append(
        "Hodgkin Lymphoma patients identified by ICD-10 C81.xx or ICD-9 201.xx "
        "diagnosis codes at 2+ encounters on different dates. Expected cohort "
        "size: ~9,331 patients."
    )
    lines.append(
        "Matching: exact set of 149 ICD codes (77 ICD-10 + 72 ICD-9), not "
        "prefix matching. DX_TYPE not required for matching (per study decision).\n"
    )

    # --- Code Matching Summary ---
    lines.append("### Code Matching Summary\n")
    lines.append("- ICD-10 codes used: 77 (C81.00\u2013C81.9A, subtypes 0/1/2/3/4/7/9, sites 0-9+A)")
    lines.append("- ICD-9 codes used: 72 (201.00\u2013201.98, subtypes 0/1/2/4/5/6/7/9, sites 0-8)")
    lines.append(f"- DX format detected: {cohort_result['dx_format']}")
    lines.append(f"- Total HL diagnosis records: {flag_small_cell(cohort_result['total_hl_records'])}")
    lines.append(f"- Unique patients with any HL code: {flag_small_cell(cohort_result['unique_patients'])}\n")

    # --- Cohort Counts ---
    lines.append("### Cohort Counts\n")
    lines.append("| Method | Patients | Description |")
    lines.append("|--------|----------|-------------|")
    lines.append(f"| A: DX_DATE | {flag_small_cell(cohort_result['method_a_count'])} | 2+ distinct DX_DATEs with HL codes |")
    lines.append(f"| B: ADMIT_DATE | {flag_small_cell(cohort_result['method_b_count'])} | 2+ distinct ADMIT_DATEs from linked encounters |")
    lines.append(f"| A only | {flag_small_cell(cohort_result['a_only'])} | In Method A but not B |")
    lines.append(f"| B only | {flag_small_cell(cohort_result['b_only'])} | In Method B but not A |")
    lines.append(f"| Intersection | {flag_small_cell(cohort_result['intersection'])} | In both methods |")
    lines.append(f"| Union | {flag_small_cell(cohort_result['union'])} | In either method |")
    lines.append("| Expected | ~9,331 | From cohort specification |\n")

    # --- Count Mismatch Investigation ---
    union_count = cohort_result["union"]
    if union_count != 9331:
        lines.append("### Count Mismatch Investigation\n")
        lines.append(f"Union count ({union_count:,}) differs from expected (~9,331).\n")

        if cohort_result["per_partner"]:
            lines.append("#### Per-Partner Breakdown\n")
            lines.append("| Partner | HL Patients |")
            lines.append("|---------|------------|")
            for partner in sorted(cohort_result["per_partner"].keys()):
                n = cohort_result["per_partner"][partner]
                lines.append(f"| {partner} | {flag_small_cell(n)} |")
            lines.append("")

        if cohort_result["year_breakdown"]:
            lines.append("#### By Earliest DX Year\n")
            lines.append("| Year | Patients |")
            lines.append("|------|----------|")
            for year in sorted(cohort_result["year_breakdown"].keys()):
                n = cohort_result["year_breakdown"][year]
                lines.append(f"| {year} | {flag_small_cell(n)} |")
            lines.append("")

    # --- Null DX_DATE Impact ---
    null_records = cohort_result["null_dx_date_records"]
    null_patients = cohort_result["null_dx_date_patients"]
    total_records = cohort_result["total_hl_records"]
    null_pct = round(null_records / max(total_records, 1) * 100, 1)
    lines.append("### Null DX_DATE Impact\n")
    lines.append(f"- HL records with null DX_DATE: {flag_small_cell(null_records)} ({null_pct}%)")
    lines.append(f"- Patients affected: {flag_small_cell(null_patients)}")
    if null_pct > 5:
        lines.append(
            "\nNull DX_DATEs reduce Method A count. Method B may be more "
            "reliable for these patients."
        )
    lines.append("")

    # --- DX_TYPE Mismatches ---
    dx_mismatches = cohort_result["dx_type_mismatches"]
    lines.append("### DX_TYPE Mismatches\n")
    if dx_mismatches.height == 0:
        lines.append("No DX_TYPE mismatches found.\n")
    else:
        lines.append(f"Total mismatches: {dx_mismatches.height}\n")
        lines.append("| DX | DX_TYPE | Expected Type | Count | Partners |")
        lines.append("|-----|---------|---------------|-------|----------|")

        summary = (
            dx_mismatches
            .group_by("DX", "DX_TYPE", "expected_type")
            .agg(
                pl.len().alias("count"),
                pl.col("SOURCE").unique().alias("partners"),
            )
            .sort("count", descending=True)
            .head(20)
        )
        for row in summary.iter_rows(named=True):
            partners_str = ", ".join(str(p) for p in row["partners"]) if row["partners"] else "—"
            lines.append(
                f"| {row['DX']} | {row['DX_TYPE']} | {row['expected_type']} "
                f"| {flag_small_cell(row['count'])} | {partners_str} |"
            )
        lines.append("")

    lines.append("> Per locked decision: DX_TYPE mismatches reported but not used for exclusion.\n")

    # --- ICD Version Distribution ---
    icd_flags_df = cohort_result["icd_flags"]
    lines.append("### ICD Version Distribution\n")

    if not icd_flags_df.is_empty():
        flag_counts = (
            icd_flags_df
            .group_by("icd_flag")
            .agg(pl.len().alias("n"))
            .sort("icd_flag")
        )
        total_flagged = flag_counts["n"].sum()
        lines.append("| Flag | Patients | % of Cohort |")
        lines.append("|------|----------|-------------|")
        for row in flag_counts.iter_rows(named=True):
            pct = round(row["n"] / max(total_flagged, 1) * 100, 1)
            lines.append(f"| {row['icd_flag']} | {flag_small_cell(row['n'])} | {pct}% |")
        lines.append("")

        lines.append(
            "> **Note:** AMS and UMI mapped ICD-9\u2192ICD-10 for all diagnoses. "
            "Their ICD10_ONLY counts may include patients whose original codes "
            "were ICD-9.\n"
        )

        if cohort_result["icd_by_partner"]:
            lines.append("#### ICD Version by Partner\n")
            all_flags = sorted({f for d in cohort_result["icd_by_partner"].values() for f in d})
            header = "| Partner | " + " | ".join(all_flags) + " | Total |"
            sep = "|---------|" + "|".join(["------" for _ in all_flags]) + "|-------|"
            lines.append(header)
            lines.append(sep)
            for partner in sorted(cohort_result["icd_by_partner"].keys()):
                counts = cohort_result["icd_by_partner"][partner]
                row = f"| {partner} "
                total = 0
                for flag in all_flags:
                    n = counts.get(flag, 0)
                    total += n
                    row += f"| {flag_small_cell(n)} "
                row += f"| {flag_small_cell(total)} |"
                lines.append(row)
            lines.append("")

    # --- Enrollment Cross-Check ---
    if enrollment_result:
        lines.append("### Enrollment Cross-Check\n")
        with_enr = enrollment_result["with_enrollment"]
        without_enr = enrollment_result["without_enrollment"]
        total_hl = enrollment_result["total_hl"]
        cov_pct = enrollment_result["coverage_pct"]
        uncov_pct = round(100 - cov_pct, 2)

        lines.append(f"- HL patients with enrollment records: {flag_small_cell(with_enr)} ({cov_pct}%)")
        lines.append(f"- HL patients without enrollment: {flag_small_cell(without_enr)} ({uncov_pct}%)\n")

        if enrollment_result.get("uncovered_by_partner"):
            lines.append("#### Uncovered Patients by Partner\n")
            lines.append("| Partner | Without Enrollment |")
            lines.append("|---------|-------------------|")
            for partner in sorted(enrollment_result["uncovered_by_partner"].keys()):
                n = enrollment_result["uncovered_by_partner"][partner]
                lines.append(f"| {partner} | {flag_small_cell(n)} |")
            lines.append("")

        if enrollment_result.get("coverage_summary_by_partner"):
            lines.append("#### Coverage Period Summary\n")
            lines.append("| Partner | Earliest ENR_START | Latest ENR_END | Median Duration (days) |")
            lines.append("|---------|-------------------|----------------|----------------------|")
            for partner in sorted(enrollment_result["coverage_summary_by_partner"].keys()):
                s = enrollment_result["coverage_summary_by_partner"][partner]
                med = s.get("median_duration_days")
                med_str = f"{med:.0f}" if med is not None else "N/A"
                lines.append(
                    f"| {partner} | {s.get('earliest_start', 'N/A')} "
                    f"| {s.get('latest_end', 'N/A')} | {med_str} |"
                )
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

    # ----- 5. HL Cohort Verification -----
    print(f"\n{'─' * 60}")
    print("  SECTION 5: HL Cohort Verification")
    print(f"{'─' * 60}")

    cohort_result: dict | None = None
    enrollment_result: dict | None = None
    diag_path = table_map.get("DIAGNOSIS")
    enr_path = table_map.get("ENROLLMENT")

    if diag_path and diag_path.exists() and enc_path and enc_path.exists():
        print(f"  DIAGNOSIS: {diag_path}")
        print(f"  ENCOUNTER: {enc_path}")

        cohort_result = verify_hl_cohort(diag_path, enc_path)

        print(f"\n  DX format:           {cohort_result['dx_format']}")
        print(f"  Total HL DX records: {cohort_result['total_hl_records']:,}")
        print(f"  Unique HL patients:  {cohort_result['unique_patients']:,}")
        print(f"  Method A (DX_DATE):  {cohort_result['method_a_count']:,}")
        print(f"  Method B (ADMIT_DATE): {cohort_result['method_b_count']:,}")
        print(f"  Union cohort:        {cohort_result['union']:,}  (expected ~9,331)")
        print(f"  A only / B only:     {cohort_result['a_only']:,} / {cohort_result['b_only']:,}")

        icd_flags = cohort_result["icd_flags"]
        if not icd_flags.is_empty():
            flag_counts = (
                icd_flags
                .group_by("icd_flag")
                .agg(pl.len().alias("n"))
                .sort("icd_flag")
            )
            for row in flag_counts.iter_rows(named=True):
                print(f"  {row['icd_flag']}: {row['n']:,}")

        dx_mm = cohort_result["dx_type_mismatches"]
        print(f"  DX_TYPE mismatches:  {dx_mm.height}")

        if enr_path and enr_path.exists() and demo_path and demo_path.exists():
            print(f"\n  Enrollment cross-check...")
            enrollment_result = enrollment_crosscheck(
                cohort_result["union_ids_df"], enr_path, demo_path
            )
            print(f"  With enrollment:     {enrollment_result['with_enrollment']:,} ({enrollment_result['coverage_pct']}%)")
            print(f"  Without enrollment:  {enrollment_result['without_enrollment']:,}")
        else:
            print("  [SKIP] Enrollment cross-check — ENROLLMENT or DEMOGRAPHIC not found")

        cohort_summary_df = build_cohort_summary_df(cohort_result, enrollment_result)
        cohort_csv_path = reports_dir / "cohort_summary.csv"
        cohort_summary_df.write_csv(cohort_csv_path)
        print(f"\n  Cohort CSV: {cohort_csv_path}")
    else:
        print("  [SKIP] DIAGNOSIS or ENCOUNTER not found — cohort verification skipped")

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
    report_parts.append("4. [Missing Value Classification](#4-missing-value-classification)")
    report_parts.append("5. [HL Cohort Verification](#5-hl-cohort-verification)\n")
    report_parts.append("---\n")

    report_parts.append(_section_schema(schema_results))
    report_parts.append(_section_integrity(patid_unique, patid_results, enc_results))
    report_parts.append(_section_completeness(comp_df, table_map))
    report_parts.append(_section_missing(missing_df))

    if cohort_result is not None:
        report_parts.append(_section_cohort(cohort_result, enrollment_result))

    report_path = reports_dir / "structural_validation.md"
    report_path.write_text("\n".join(report_parts), encoding="utf-8")

    overall_elapsed = time.time() - overall_start

    # ----- Console summary -----
    schema_warn_count = sum(1 for r in schema_results if r["status"] == "warn")
    total_orphan_patids = sum(r["orphan_ids"] for r in patid_results)
    total_orphan_encs = sum(
        r["orphan_encounterids"] for r in enc_results if not r.get("skipped")
    )

    hl_union = cohort_result["union"] if cohort_result else 0
    enr_cov = f"{enrollment_result['coverage_pct']}%" if enrollment_result else "N/A"

    print(f"\n{'=' * 60}")
    print("  STRUCTURAL VALIDATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Tables validated:     {len(schema_results)}")
    print(f"  Schema issues:        {schema_warn_count} tables with missing/extra columns")
    print(f"  PATID orphans:        {total_orphan_patids} tables with orphan IDs")
    print(f"  ENCOUNTERID orphans:  {total_orphan_encs} tables with orphan ENCOUNTERIDs")
    print(f"  HL cohort (union):    {hl_union:,} patients (expected ~9,331)")
    print(f"  Enrollment coverage:  {enr_cov}")
    print(f"  Elapsed:              {overall_elapsed:.1f}s")
    print(f"  Reports:")
    print(f"    - {report_path}")
    print(f"    - {reports_dir / 'completeness_by_partner.csv'}")
    if cohort_result:
        print(f"    - {reports_dir / 'cohort_summary.csv'}")
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
