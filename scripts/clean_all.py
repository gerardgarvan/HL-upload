"""Phase 5: Deduplication, cross-table consistency, partner harmonization.

Usage: python scripts/clean_all.py [config/paths.toml]

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
    PATID_COL,
    SMALL_CELL_THRESHOLD,
    TUMOR_REGISTRY_TABLES,
    ENCOUNTER_LINKED_TABLES,
    flag_small_cell,
)
from src.clean.dedup import (
    flag_duplicates,
    DEDUP_KEYS,
    EVENT_DATE_COLS,
    CLEAN_FLAG_COLS,
    CLEAN_FLAG_PREFIX,
    check_demographic_consistency,
    flag_events_outside_encounters,
    check_death_consistency,
    drop_existing_clean_flags,
    write_cleaned,
)
from src.clean.harmonize import (
    add_partner_flags,
    PARTNER_FLAGS,
    flag_encounters_outside_enrollment,
    flag_no_enrollment,
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


def _suppress(value: int) -> str:
    """Small-cell suppression: replace counts 1-10 with dash."""
    if 1 <= value <= SMALL_CELL_THRESHOLD:
        return "-"
    return str(value)


# ---------------------------------------------------------------------------
# Report generation (Step 5)
# ---------------------------------------------------------------------------


# Report functions will be added in Task 2.


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
        if (
            table_name in EVENT_DATE_COLS
            and encounter_ref is not None
            and "ENCOUNTERID" in df.columns
        ):
            event_date_col = EVENT_DATE_COLS[table_name]
            if event_date_col in df.columns:
                df = flag_events_outside_encounters(
                    df, encounter_ref, event_date_col
                )

        # (h) ENCOUNTER-specific: enrollment coverage
        if table_name == "ENCOUNTER" and enrollment_ref is not None:
            df = flag_encounters_outside_enrollment(df, enrollment_ref)
            df = flag_no_enrollment(df, enrollment_ref)

        # (i) Write flagged Parquet back
        stats = write_cleaned(df, pq_path)

        # (j) Count rows with any Phase 5 flag
        flag_cols = [
            c for c in df.columns
            if c in CLEAN_FLAG_COLS or c.startswith(CLEAN_FLAG_PREFIX)
        ]
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
        print(
            f"  Demographics: {n_birth} multi-BIRTH_DATE, "
            f"{n_sex} multi-SEX patients"
        )
    else:
        print("  Demographics: DEMOGRAPHIC table not available")

    death_consistency = check_death_consistency(table_map)
    if death_consistency:
        print(
            f"  Death dates: {death_consistency['patients_checked']} checked, "
            f"{death_consistency['patients_mismatched']} mismatched"
        )
    else:
        print("  Death dates: DEATH table not available")

    # ── Step 5: Report generation ────────────────────────────────────────
    # Report functions wired here after Task 2.

    # ── Step 6: Console summary ──────────────────────────────────────────
    overall_elapsed = time.time() - overall_start
    total_flag_cols = sum(s["flag_columns_added"] for s in report_data.values())
    total_flagged_rows = sum(
        s.get("rows_with_any_flag", 0) for s in report_data.values()
    )

    print(f"\n{'=' * 60}")
    print("  DEDUPLICATION & HARMONIZATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Tables processed:      {len(report_data)}")
    print(f"  Total flag columns:    {total_flag_cols}")
    print(f"  Total flagged rows:    {total_flagged_rows:,}")
    print(f"  Elapsed:               {overall_elapsed:.1f}s")
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
        print(f"  DEDUPLICATION & HARMONIZATION FAILED")
        print(f"{'=' * 60}")
        print(f"  Error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
