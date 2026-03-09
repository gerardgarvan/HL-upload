"""Phase 5: Deduplication, cross-table consistency, partner harmonization.

Small-cell: all report counts use flag_small_cell/_suppress per REQ-05.

Usage: python scripts/clean_all.py [config/paths.toml]

Designed for HPC interactive sessions (srun --pty bash).
"""

import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl

from src.clean.dedup import (
    CLEAN_FLAG_COLS,
    CLEAN_FLAG_PREFIX,
    DEDUP_KEYS,
    EVENT_DATE_COLS,
    check_death_consistency,
    check_demographic_consistency,
    drop_existing_clean_flags,
    flag_duplicates,
    flag_events_outside_encounters,
    write_cleaned,
)
from src.clean.harmonize import (
    PARTNER_FLAGS,
    add_partner_flags,
    flag_encounters_outside_enrollment,
    flag_no_enrollment,
)
from src.load.config import load_config
from src.load.schema import parse_datastructure, resolve_table_name
from src.validate.structural import (
    PATID_COL,
    SMALL_CELL_THRESHOLD,
    flag_small_cell,
)

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


def _suppress(value: int) -> str:
    """Small-cell suppression: replace counts 1-10 with dash."""
    if 1 <= value <= SMALL_CELL_THRESHOLD:
        return "-"
    return str(value)


# ---------------------------------------------------------------------------
# Report generation (Step 5)
# ---------------------------------------------------------------------------


def _generate_dedup_report(
    report_data: dict,
    reports_dir: Path,
    paths,
) -> Path:
    """Generate reports/dedup_report.md with duplicate detection findings."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    # ── Header ───────────────────────────────────────────────────────────
    lines.append("# Deduplication Report\n")
    lines.append(f"**Generated:** {timestamp}")
    lines.append(f"**Data source:** {paths.data_root}")
    lines.append(f"**Parquet directory:** {paths.parquet_dir}")
    lines.append(f"**Tables processed:** {len(report_data)}\n")

    lines.append("## Table of Contents\n")
    lines.append("1. [Overview](#1-overview)")
    lines.append("2. [Per-Partner Duplicate Rates](#2-per-partner-duplicate-rates)")
    lines.append("3. [Methodology](#3-methodology)\n")
    lines.append("---\n")

    # ── Section 1: Overview ──────────────────────────────────────────────
    lines.append("## 1. Overview\n")
    lines.append("| Table | Total Rows | Duplicates | Dup Rate | Keys Used |")
    lines.append("|-------|-----------|------------|----------|-----------|")

    for table_name in sorted(report_data.keys()):
        stats = report_data[table_name]
        total = stats["total_rows"]
        dup_count = stats["flags"].get("IS_DUPLICATE", 0)

        if table_name in DEDUP_KEYS:
            keys_str = ", ".join(DEDUP_KEYS[table_name])
            rate = dup_count / max(total, 1) * 100
            lines.append(f"| {table_name} | {total:,} | {flag_small_cell(dup_count)} | {rate:.2f}% | {keys_str} |")
        else:
            lines.append(f"| {table_name} | {total:,} | — | — | — |")

    lines.append("")

    # ── Section 2: Per-Partner Duplicate Rates ───────────────────────────
    lines.append("## 2. Per-Partner Duplicate Rates\n")

    partner_rows_found = False
    lines.append("| Partner | Table | Total | Duplicates | Rate |")
    lines.append("|---------|-------|-------|------------|------|")

    for table_name in sorted(report_data.keys()):
        stats = report_data[table_name]
        pd_df = stats.get("partner_dedup")
        if pd_df is None:
            continue
        partner_rows_found = True
        for row in pd_df.sort("SOURCE").iter_rows(named=True):
            partner = row["SOURCE"] if row["SOURCE"] is not None else "NULL"
            total = row["total"]
            dup_c = int(row["dup_count"]) if row["dup_count"] is not None else 0
            rate = dup_c / max(total, 1) * 100
            lines.append(f"| {partner} | {table_name} | {total:,} | {flag_small_cell(dup_c)} | {rate:.2f}% |")

    if not partner_rows_found:
        lines.append("| — | — | — | — | No partner dedup data available |")
    lines.append("")

    # ── Section 3: Methodology ───────────────────────────────────────────
    lines.append("## 3. Methodology\n")
    lines.append("### Composite Keys\n")
    for table_name, keys in sorted(DEDUP_KEYS.items()):
        lines.append(f"- **{table_name}:** {', '.join(keys)}")
    lines.append("")
    lines.append("### Flagging Behavior\n")
    lines.append("- **ALL** occurrences sharing the same composite key are flagged (`IS_DUPLICATE = 1`), not just subsequent rows.")
    lines.append("- Null key values do **not** match each other (`null != null`), so rows with null keys are not flagged as duplicates.")
    lines.append("- No records are deleted; flags are additive Int8 columns.")
    lines.append("")

    out_path = reports_dir / "dedup_report.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def _generate_consistency_report(
    report_data: dict,
    demo_consistency: dict,
    death_consistency: dict,
    reports_dir: Path,
    paths,
) -> Path:
    """Generate reports/consistency_report.md with cross-table findings."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    # ── Header ───────────────────────────────────────────────────────────
    lines.append("# Cross-Table Consistency Report\n")
    lines.append(f"**Generated:** {timestamp}")
    lines.append(f"**Data source:** {paths.data_root}")
    lines.append(f"**Parquet directory:** {paths.parquet_dir}")
    lines.append(f"**Tables processed:** {len(report_data)}\n")

    lines.append("## Table of Contents\n")
    lines.append("1. [Demographics Consistency](#1-demographics-consistency)")
    lines.append("2. [Events Outside Encounter Windows](#2-events-outside-encounter-windows)")
    lines.append("3. [Death Date Consistency](#3-death-date-consistency)")
    lines.append("4. [Insurance Enrollment Coverage](#4-insurance-enrollment-coverage)")
    lines.append("\n---\n")

    # ── Section 1: Demographics Consistency ──────────────────────────────
    lines.append("## 1. Demographics Consistency\n")

    if not demo_consistency:
        lines.append("DEMOGRAPHIC table not available for consistency checks.\n")
    else:
        total_pts = demo_consistency.get("total_patients", 0)
        multi_bd = demo_consistency.get("multi_birth_date", [])
        multi_sx = demo_consistency.get("multi_sex", [])

        lines.append(f"- **Total patients:** {total_pts:,}")

        n_bd = len(multi_bd)
        if n_bd == 0:
            lines.append("- **Multiple BIRTH_DATE values:** 0 inconsistencies")
        else:
            lines.append(f"- **Multiple BIRTH_DATE values:** {flag_small_cell(n_bd)} patients")
            if n_bd <= SMALL_CELL_THRESHOLD:
                lines.append(f"  - Patient IDs: {', '.join(str(x) for x in multi_bd)}")

        n_sx = len(multi_sx)
        if n_sx == 0:
            lines.append("- **Multiple SEX values:** 0 inconsistencies")
        else:
            lines.append(f"- **Multiple SEX values:** {flag_small_cell(n_sx)} patients")
            if n_sx <= SMALL_CELL_THRESHOLD:
                lines.append(f"  - Patient IDs: {', '.join(str(x) for x in multi_sx)}")

    lines.append("")

    # ── Section 2: Events Outside Encounter Windows ──────────────────────
    lines.append("## 2. Events Outside Encounter Windows\n")
    lines.append("| Table | Total Rows | Outside Window | Rate |")
    lines.append("|-------|-----------|----------------|------|")

    any_event_flag = False
    for table_name in sorted(report_data.keys()):
        stats = report_data[table_name]
        flag_count = stats["flags"].get("_con_outside_encounter", 0)
        if flag_count > 0 or "_con_outside_encounter" in stats["flags"]:
            total = stats["total_rows"]
            rate = flag_count / max(total, 1) * 100
            lines.append(f"| {table_name} | {total:,} | {flag_small_cell(flag_count)} | {rate:.2f}% |")
            any_event_flag = True

    if not any_event_flag:
        lines.append("| — | — | — | No event-encounter flags generated |")

    lines.append("")
    lines.append("> **Note:** ±1 day tolerance applied. Rows with null ENCOUNTERID are not assessed (flag = 0).\n")

    # ── Section 3: Death Date Consistency ────────────────────────────────
    lines.append("## 3. Death Date Consistency\n")

    if not death_consistency:
        lines.append("DEATH table not available for consistency checks.\n")
    else:
        checked = death_consistency.get("patients_checked", 0)
        mismatched = death_consistency.get("patients_mismatched", 0)
        lines.append(f"- **Patients checked:** {checked:,}")
        lines.append(f"- **Patients with mismatched death dates:** {flag_small_cell(mismatched)}")

        details = death_consistency.get("details", [])
        if details:
            lines.append("")
            lines.append("| TR Table | Date Column | Checked | Mismatched |")
            lines.append("|----------|------------|---------|------------|")
            for d in details:
                lines.append(
                    f"| {d['tr_table']} | {d['tr_date_col']} | {d['patients_checked']:,} | {flag_small_cell(d['patients_mismatched'])} |"
                )

    lines.append("")

    # ── Section 4: Insurance Enrollment Coverage ─────────────────────────
    lines.append("## 4. Insurance Enrollment Coverage\n")

    enc_stats = report_data.get("ENCOUNTER", {})
    enc_flags = enc_stats.get("flags", {})

    outside_enr = enc_flags.get("_con_outside_enrollment", 0)
    no_enr = enc_flags.get("_con_no_enrollment", 0)

    if outside_enr == 0 and no_enr == 0 and "ENCOUNTER" not in report_data:
        lines.append("ENCOUNTER table not processed or no enrollment data.\n")
    else:
        enc_total = enc_stats.get("total_rows", 0)
        lines.append(f"- **ENCOUNTER rows outside any enrollment period:** {flag_small_cell(outside_enr)}")
        if enc_total > 0:
            rate_out = outside_enr / enc_total * 100
            lines.append(f"  - Rate: {rate_out:.2f}% of {enc_total:,} encounters")
        lines.append(f"- **Patients with no enrollment record:** {flag_small_cell(no_enr)}")
    lines.append("")

    out_path = reports_dir / "consistency_report.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def _generate_partner_report(
    report_data: dict,
    reports_dir: Path,
    paths,
) -> Path:
    """Generate reports/partner_harmonization.md with partner flag findings."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    # ── Header ───────────────────────────────────────────────────────────
    lines.append("# Partner Harmonization Report\n")
    lines.append(f"**Generated:** {timestamp}")
    lines.append(f"**Data source:** {paths.data_root}")
    lines.append(f"**Parquet directory:** {paths.parquet_dir}")
    lines.append(f"**Tables processed:** {len(report_data)}\n")

    lines.append("## Table of Contents\n")
    lines.append("1. [Partner Flag Summary](#1-partner-flag-summary)")
    lines.append("2. [ICD_MAPPED Partners (AMS, UMI)](#2-icd_mapped-partners-ams-umi)")
    lines.append("3. [CLAIMS_ONLY Partner (FLM)](#3-claims_only-partner-flm)")
    lines.append("4. [DEATH_ONLY Partner (VRT)](#4-death_only-partner-vrt)")
    lines.append("\n---\n")

    # ── Section 1: Partner Flag Summary ──────────────────────────────────
    lines.append("## 1. Partner Flag Summary\n")
    lines.append("| Flag | Partners | Tables Flagged | Total Rows Flagged |")
    lines.append("|------|----------|---------------|-------------------|")

    for flag_name, partner_set in sorted(PARTNER_FLAGS.items()):
        tables_with_flag = 0
        total_flagged = 0
        for table_name in sorted(report_data.keys()):
            stats = report_data[table_name]
            fc = stats["flags"].get(flag_name, 0)
            if fc > 0:
                tables_with_flag += 1
                total_flagged += fc

        partners_str = ", ".join(sorted(partner_set))
        lines.append(f"| {flag_name} | {partners_str} | {tables_with_flag} | {flag_small_cell(total_flagged)} |")
    lines.append("")

    # ── Section 2: ICD_MAPPED Partners ───────────────────────────────────
    lines.append("## 2. ICD_MAPPED Partners (AMS, UMI)\n")

    icd_total = 0
    for stats in report_data.values():
        icd_total += stats["flags"].get("ICD_MAPPED", 0)

    lines.append(f"- **Total records flagged:** {flag_small_cell(icd_total)}")
    lines.append("- These partners retrospectively mapped ICD-9 → ICD-10, so pre-October-2015 ICD-10 codes are expected for their records.")

    concordance_csv = reports_dir / "icd_concordance.csv"
    if concordance_csv.exists():
        lines.append("- Cross-reference: see `reports/icd_concordance.csv` from Phase 4 validation for per-partner ICD breakdown.")
    lines.append("")

    # ── Section 3: CLAIMS_ONLY Partner ───────────────────────────────────
    lines.append("## 3. CLAIMS_ONLY Partner (FLM)\n")

    flm_total = 0
    flm_tables: list[str] = []
    all_tables = sorted(report_data.keys())
    for table_name in all_tables:
        stats = report_data[table_name]
        fc = stats["flags"].get("CLAIMS_ONLY", 0)
        if fc > 0:
            flm_tables.append(table_name)
            flm_total += fc

    lines.append(f"- **Total records flagged:** {flag_small_cell(flm_total)}")

    if flm_tables:
        lines.append(f"- **Tables with FLM data:** {', '.join(flm_tables)}")
        absent = [t for t in all_tables if t not in flm_tables]
        if absent:
            lines.append(f"- **Tables without FLM data:** {', '.join(absent)}")

    lines.append("- FLM provides claims-only data: no labs, vitals, or prescribing.")
    lines.append("")

    # ── Section 4: DEATH_ONLY Partner ────────────────────────────────────
    lines.append("## 4. DEATH_ONLY Partner (VRT)\n")

    vrt_total = 0
    for stats in report_data.values():
        vrt_total += stats["flags"].get("DEATH_ONLY", 0)

    lines.append(f"- **Total records flagged:** {flag_small_cell(vrt_total)}")
    lines.append("- VRT contributes death records only.")
    lines.append("")

    out_path = reports_dir / "partner_harmonization.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(config_path: Path | None = None) -> None:
    print("=" * 60)
    print("HL DATA LOADING & CLEANING — DEDUPLICATION & HARMONIZATION")
    print("=" * 60)

    overall_start = time.time()

    # ── Step 1: Load config ──────────────────────────────────────────────
    paths = load_config(config_path)
    print(f"\n  data_root:    {paths.data_root}")
    print(f"  parquet_dir:  {paths.parquet_dir}")

    _, table_filenames = parse_datastructure(paths.datastructure_path)
    table_map = _build_table_map(table_filenames, paths.parquet_dir)
    print(f"\n  Tables found: {len(table_map)}")

    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 2: Load reference tables ────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("  Loading reference tables...")
    print(f"{'─' * 60}")

    encounter_ref = None
    enc_path = table_map.get("ENCOUNTER")
    if enc_path and enc_path.exists():
        enc_df = pl.read_parquet(enc_path)
        needed = ("ENCOUNTERID", "ADMIT_DATE", "DISCHARGE_DATE")
        if all(c in enc_df.columns for c in needed):
            encounter_ref = enc_df.select(
                pl.col("ENCOUNTERID").cast(pl.String),
                "ADMIT_DATE",
                "DISCHARGE_DATE",
            )
            print(f"  ENCOUNTER reference: {encounter_ref.height:,} rows")
        del enc_df
    if encounter_ref is None:
        print("  ENCOUNTER — not available, event-window checks disabled")

    enrollment_ref = None
    enr_path = table_map.get("ENROLLMENT")
    if enr_path and enr_path.exists():
        enr_df = pl.read_parquet(enr_path)
        needed_enr = (PATID_COL, "ENR_START_DATE", "ENR_END_DATE")
        if all(c in enr_df.columns for c in needed_enr):
            enrollment_ref = enr_df.select(
                pl.col(PATID_COL).cast(pl.String),
                "ENR_START_DATE",
                "ENR_END_DATE",
            )
            print(f"  ENROLLMENT reference: {enrollment_ref.height:,} rows")
        del enr_df
    if enrollment_ref is None:
        print("  ENROLLMENT — not available, insurance checks disabled")

    # ── Step 3: Main cleaning loop ───────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("  CLEANING LOOP")
    print(f"{'─' * 60}")

    report_data: dict = {}
    tables_sorted = sorted(table_map.items())
    total_tables = len(tables_sorted)

    for idx, (table_name, pq_path) in enumerate(tables_sorted, 1):
        print(f"\n  [{idx}/{total_tables}] {table_name}", end="")

        if not pq_path.exists():
            print(" — SKIP (parquet not found)")
            continue

        df = pl.read_parquet(pq_path)
        df = drop_existing_clean_flags(df)
        initial_cols = len(df.columns)

        # (e) Dedup flagging
        df = flag_duplicates(df, table_name)

        # (f) Partner provenance flags
        df = add_partner_flags(df)

        # (g) Event-encounter window check
        if table_name in EVENT_DATE_COLS and encounter_ref is not None and "ENCOUNTERID" in df.columns:
            event_date_col = EVENT_DATE_COLS[table_name]
            if event_date_col in df.columns:
                df = flag_events_outside_encounters(df, encounter_ref, event_date_col)

        # (h) ENCOUNTER-specific: enrollment coverage
        if table_name == "ENCOUNTER" and enrollment_ref is not None:
            df = flag_encounters_outside_enrollment(df, enrollment_ref)
            df = flag_no_enrollment(df, enrollment_ref)

        # (i) Write flagged Parquet back
        stats = write_cleaned(df, pq_path)

        # (j) Count rows with any Phase 5 flag
        flag_cols = [c for c in df.columns if c in CLEAN_FLAG_COLS or c.startswith(CLEAN_FLAG_PREFIX)]
        if flag_cols:
            any_flag_expr = pl.lit(False)
            for fc in flag_cols:
                any_flag_expr = any_flag_expr | (pl.col(fc) == 1)
            rows_with_flag = df.filter(any_flag_expr).height
        else:
            rows_with_flag = 0
        stats["rows_with_any_flag"] = rows_with_flag

        # (k) Per-partner dedup summary
        if "SOURCE" in df.columns and "IS_DUPLICATE" in df.columns:
            partner_dedup = df.group_by("SOURCE").agg(
                pl.len().alias("total"),
                pl.col("IS_DUPLICATE").sum().alias("dup_count"),
            )
            stats["partner_dedup"] = partner_dedup

        report_data[table_name] = stats

        new_flags = len(df.columns) - initial_cols
        print(f" — {new_flags} flags added, {rows_with_flag:,} rows flagged")

    # ── Step 4: Cross-table summary checks ───────────────────────────────
    print(f"\n{'─' * 60}")
    print("  CROSS-TABLE SUMMARY CHECKS")
    print(f"{'─' * 60}")

    demo_consistency = check_demographic_consistency(table_map)
    if demo_consistency:
        n_birth = len(demo_consistency.get("multi_birth_date", []))
        n_sex = len(demo_consistency.get("multi_sex", []))
        print(f"  Demographics: {n_birth} multi-BIRTH_DATE, {n_sex} multi-SEX patients")
    else:
        print("  Demographics: DEMOGRAPHIC table not available")

    death_consistency = check_death_consistency(table_map)
    if death_consistency:
        print(f"  Death dates: {death_consistency['patients_checked']} checked, {death_consistency['patients_mismatched']} mismatched")
    else:
        print("  Death dates: DEATH table not available")

    # ── Step 5: Report generation ────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("  Generating reports...")
    print(f"{'─' * 60}")

    rpt_dedup = _generate_dedup_report(report_data, reports_dir, paths)
    print(f"  Written: {rpt_dedup}")

    rpt_consistency = _generate_consistency_report(report_data, demo_consistency, death_consistency, reports_dir, paths)
    print(f"  Written: {rpt_consistency}")

    rpt_partner = _generate_partner_report(report_data, reports_dir, paths)
    print(f"  Written: {rpt_partner}")

    # ── Step 6: Console summary ──────────────────────────────────────────
    overall_elapsed = time.time() - overall_start
    total_flag_cols = sum(s["flag_columns_added"] for s in report_data.values())
    total_flagged_rows = sum(s.get("rows_with_any_flag", 0) for s in report_data.values())

    print(f"\n{'=' * 60}")
    print("  DEDUPLICATION & HARMONIZATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Tables processed:      {len(report_data)}")
    print(f"  Total flag columns:    {total_flag_cols}")
    print(f"  Total flagged rows:    {total_flagged_rows:,}")
    print(f"  Elapsed:               {overall_elapsed:.1f}s")
    print("  Reports:")
    print(f"    - {rpt_dedup}")
    print(f"    - {rpt_consistency}")
    print(f"    - {rpt_partner}")
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
        print("  DEDUPLICATION & HARMONIZATION FAILED")
        print(f"{'=' * 60}")
        print(f"  Error: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
