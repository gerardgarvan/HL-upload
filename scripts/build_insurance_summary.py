"""Build insurance summary tables and figures from encounter-payer summary (Phase 15).

Reads derived/encounter_payer_summary.parquet, produces:
- reports/encounter_payer_summary.csv (counts and percentages per category for each insurance variable; _suppress)
- reports/insurance_summary.md (four tables with flag_small_cell)
- reports/payer_at_first_dx.csv, payer_at_first_chemo.csv, payer_at_first_radiation.csv, payer_at_last_radiation.csv, payer_at_first_sct.csv, payer_at_last_sct.csv, payer_crosstab_*.csv, payer_transition_prevalence.csv (_suppress)
- reports/figures/insurance_payer_at_first_dx.png, insurance_payer_at_first_chemo.png (bars; 1–10 excluded)

Usage:
    python scripts/build_insurance_summary.py [config/paths.toml]
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl

from src.load.config import load_config
from src.report.quality_report import _suppress
from src.validate.structural import SMALL_CELL_THRESHOLD, flag_small_cell

PAYER_CATEGORY_ORDER = [
    "Medicare",
    "Medicaid",
    "Dual eligible",
    "Private",
    "Other government",
    "No payment / Self-pay",
    "Other",
    "Unavailable",
    "Unknown",
]


def _normalize_payer(s: pl.Series) -> pl.Series:
    """Replace null and empty string payer values with 'Unknown' for consistent reporting.

    Used to normalize payer category columns before grouping/aggregation. Ensures all patients
    have a category (even if "Unknown") to avoid null values in summary tables.

    Args:
        s: Polars Series of payer category strings (may contain nulls or empty strings)

    Returns:
        Series with nulls and empty strings replaced by "Unknown", dtype pl.String
    """
    return pl.Series(
        [("Unknown" if (v is None or v == "") else v) for v in s],
        dtype=pl.String,
    )


def _order_categories(df: pl.DataFrame, col: str) -> pl.DataFrame:
    """Sort DataFrame rows by standard payer category order for consistent table presentation.

    Uses PAYER_CATEGORY_ORDER (Medicare, Medicaid, Dual eligible, Private, Other government,
    No payment / Self-pay, Other, Unavailable, Unknown) to sort rows. Categories not in the
    standard order are sorted last (by their natural order).

    Args:
        df: DataFrame containing a payer category column
        col: Name of the payer category column to sort by

    Returns:
        DataFrame sorted by standard payer category order (in-place sort via temporary _ord column)
    """
    order = {c: i for i, c in enumerate(PAYER_CATEGORY_ORDER)}
    ord_series = pl.Series(
        [order.get(v, len(order)) for v in df[col].to_list()],
        dtype=pl.Int64,
    )
    return df.with_columns(ord_series.alias("_ord")).sort("_ord").drop("_ord")


def main(config_path: Path | None = None) -> None:
    """Phase 15: Build insurance summary tables and figures from derived/encounter_payer_summary.parquet.

    Generates comprehensive insurance equity reporting outputs: (1) encounter_payer_summary.csv with
    counts/percentages for all insurance variables; (2) insurance_summary.md with markdown tables for
    payer at first DX, first chemo, first/last radiation, first/last SCT, cross-tab first DX vs first
    chemo, payer transition prevalence, dual-eligible prevalence; (3) Treatment-specific cohort CSVs
    (insurance_summary_chemo.csv, insurance_summary_radiation.csv, insurance_summary_sct.csv) with
    payer distributions among patients who had that treatment; (4) Per-variable CSVs for each payer
    timepoint (payer_at_first_dx.csv, payer_at_first_chemo.csv, etc.); (5) Cross-tab CSV; (6) Bar
    chart PNGs for payer at first DX and first chemo (categories 1-10 excluded from figures per HIPAA).

    Small-cell suppression: Markdown tables use flag_small_cell (adds ⚠ for 1-10), CSV files use
    _suppress (replaces 1-10 with dash) per REQ-05.

    Adds DUAL_ELIGIBLE column as 0 if missing (for parquet built pre-Phase 16); prints note to
    re-run assemble_clean.py for real values. Adds HAD_CHEMO, HAD_RADIATION, HAD_SCT as 0 if missing.

    Designed for HPC or local runs. Typical run time: <1 minute. Requires encounter_payer_summary.parquet
    from assemble_clean.py (Phase 6). Exits early if parquet missing or empty.

    Creates reports/ and reports/figures/ directories if they don't exist. Prints progress for each
    output file to stdout. Skips figures if matplotlib not available.

    Args:
        config_path: Optional path to config/paths.toml (uses default if None)

    Raises:
        SystemExit: Exits with code 0 if encounter_payer_summary.parquet missing or empty (not an error)
    """
    print("=" * 60)
    print("HL INSURANCE SUMMARY — Tables and Figures")
    print("=" * 60)

    paths = load_config(config_path)
    derived_dir = paths.derived_dir
    reports_dir = PROJECT_ROOT / "reports"
    figures_dir = reports_dir / "figures"
    reports_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    enc_path = derived_dir / "encounter_payer_summary.parquet"
    if not enc_path.exists():
        print("encounter_payer_summary.parquet missing or empty; skipping.")
        sys.exit(0)
    df = pl.read_parquet(enc_path)
    if df.is_empty():
        print("encounter_payer_summary.parquet missing or empty; skipping.")
        sys.exit(0)

    print(f"\n  derived_dir: {derived_dir}")
    print(f"  Rows: {df.height:,}")
    # Ensure DUAL_ELIGIBLE exists so it always appears in reports (add 0 if parquet was built pre-Phase 16)
    if "DUAL_ELIGIBLE" not in df.columns:
        df = df.with_columns(pl.lit(0).cast(pl.Int8).alias("DUAL_ELIGIBLE"))
        print("  Note: DUAL_ELIGIBLE was missing in parquet; added as 0. Re-run assemble_clean.py for real values.")
    # Treatment flags for cohort-specific summaries (add 0 if missing)
    for col in ("HAD_CHEMO", "HAD_RADIATION", "HAD_SCT"):
        if col not in df.columns:
            df = df.with_columns(pl.lit(0).cast(pl.Int8).alias(col))

    n_total = df.height
    # Cohorts for treatment-specific tables (only people who had that treatment)
    df_chemo = df.filter(pl.col("HAD_CHEMO") == 1) if "HAD_CHEMO" in df.columns else pl.DataFrame()
    df_radiation = df.filter(pl.col("HAD_RADIATION") == 1) if "HAD_RADIATION" in df.columns else pl.DataFrame()
    df_sct = df.filter(pl.col("HAD_SCT") == 1) if "HAD_SCT" in df.columns else pl.DataFrame()

    # -------------------------------------------------------------------------
    # encounter_payer_summary.csv: counts and percentages for each insurance variable
    # -------------------------------------------------------------------------
    INSURANCE_VARS = [
        "PAYER_CATEGORY_PRIMARY",
        "PAYER_CATEGORY_AT_FIRST_DX",
        "PAYER_CATEGORY_AT_FIRST_CHEMO",
        "PAYER_CATEGORY_AT_LAST_CHEMO",
        "PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO",
        "PAYER_CATEGORY_AT_FIRST_RADIATION",
        "PAYER_CATEGORY_AT_LAST_RADIATION",
        "PAYER_CATEGORY_AT_FIRST_SCT",
        "PAYER_CATEGORY_AT_LAST_SCT",
    ]
    summary_rows: list[dict] = []
    for var in INSURANCE_VARS:
        if var not in df.columns:
            continue
        normalized = df.with_columns(_normalize_payer(df[var]).alias("_cat"))
        grp = normalized.group_by("_cat").agg(pl.len().alias("N"))
        grp = grp.with_columns((100.0 * pl.col("N") / n_total).alias("Pct"))
        grp = _order_categories(grp.rename({"_cat": "Category"}), "Category")
        for row in grp.iter_rows(named=True):
            n = row["N"]
            pct = row["Pct"]
            summary_rows.append({
                "Variable": var,
                "Category": row["Category"],
                "N": _suppress(n),
                "Pct": _suppress(int(round(pct))) if 1 <= n <= SMALL_CELL_THRESHOLD else f"{pct:.1f}",
            })
    # PAYER_TRANSITION (0/1)
    if "PAYER_TRANSITION" in df.columns:
        for val in (0, 1):
            n = df.filter(pl.col("PAYER_TRANSITION") == val).height
            pct = 100.0 * n / n_total if n_total else 0
            summary_rows.append({
                "Variable": "PAYER_TRANSITION",
                "Category": str(val),
                "N": _suppress(n),
                "Pct": _suppress(int(round(pct))) if 1 <= n <= SMALL_CELL_THRESHOLD else f"{pct:.1f}",
            })
    # DUAL_ELIGIBLE (0/1)
    if "DUAL_ELIGIBLE" in df.columns:
        for val in (0, 1):
            n = df.filter(pl.col("DUAL_ELIGIBLE") == val).height
            pct = 100.0 * n / n_total if n_total else 0
            summary_rows.append({
                "Variable": "DUAL_ELIGIBLE",
                "Category": str(val),
                "N": _suppress(n),
                "Pct": _suppress(int(round(pct))) if 1 <= n <= SMALL_CELL_THRESHOLD else f"{pct:.1f}",
            })
    if summary_rows:
        pl.DataFrame(summary_rows).write_csv(reports_dir / "encounter_payer_summary.csv")
        print(f"  encounter_payer_summary.csv")

    # -------------------------------------------------------------------------
    # Treatment-specific summary tables (enrollment + had that treatment)
    # -------------------------------------------------------------------------
    def _build_cohort_summary_rows(
        cohort_df: pl.DataFrame,
        vars_list: list[str],
    ) -> list[dict]:
        """Build Variable/Category/N/Pct rows for a cohort, same format as main summary."""
        rows: list[dict] = []
        n_cohort = cohort_df.height
        if n_cohort == 0:
            return rows
        for var in vars_list:
            if var not in cohort_df.columns:
                continue
            normalized = cohort_df.with_columns(_normalize_payer(cohort_df[var]).alias("_cat"))
            grp = normalized.group_by("_cat").agg(pl.len().alias("N"))
            grp = grp.with_columns((100.0 * pl.col("N") / n_cohort).alias("Pct"))
            grp = _order_categories(grp.rename({"_cat": "Category"}), "Category")
            for row in grp.iter_rows(named=True):
                n = row["N"]
                pct = row["Pct"]
                rows.append({
                    "Variable": var,
                    "Category": row["Category"],
                    "N": _suppress(n),
                    "Pct": _suppress(int(round(pct))) if 1 <= n <= SMALL_CELL_THRESHOLD else f"{pct:.1f}",
                })
        if "PAYER_TRANSITION" in cohort_df.columns:
            for val in (0, 1):
                n = cohort_df.filter(pl.col("PAYER_TRANSITION") == val).height
                pct = 100.0 * n / n_cohort if n_cohort else 0
                rows.append({
                    "Variable": "PAYER_TRANSITION",
                    "Category": str(val),
                    "N": _suppress(n),
                    "Pct": _suppress(int(round(pct))) if 1 <= n <= SMALL_CELL_THRESHOLD else f"{pct:.1f}",
                })
        if "DUAL_ELIGIBLE" in cohort_df.columns:
            for val in (0, 1):
                n = cohort_df.filter(pl.col("DUAL_ELIGIBLE") == val).height
                pct = 100.0 * n / n_cohort if n_cohort else 0
                rows.append({
                    "Variable": "DUAL_ELIGIBLE",
                    "Category": str(val),
                    "N": _suppress(n),
                    "Pct": _suppress(int(round(pct))) if 1 <= n <= SMALL_CELL_THRESHOLD else f"{pct:.1f}",
                })
        return rows

    # Chemo cohort: enrollment + had any chemo; general insurance + chemo-specific vars
    CHEMO_COHORT_VARS = [
        "PAYER_CATEGORY_PRIMARY",
        "PAYER_CATEGORY_AT_FIRST_DX",
        "PAYER_CATEGORY_AT_FIRST_CHEMO",
        "PAYER_CATEGORY_AT_LAST_CHEMO",
        "PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO",
    ]
    df_chemo = df.filter(pl.col("HAD_CHEMO") == 1)
    chemo_summary_rows = _build_cohort_summary_rows(df_chemo, CHEMO_COHORT_VARS)
    if chemo_summary_rows:
        pl.DataFrame(chemo_summary_rows).write_csv(reports_dir / "insurance_summary_chemo.csv")
        print(f"  insurance_summary_chemo.csv (N={df_chemo.height:,})")

    # Radiation cohort: enrollment + had any radiation; general insurance + radiation vars
    RADIATION_COHORT_VARS = [
        "PAYER_CATEGORY_PRIMARY",
        "PAYER_CATEGORY_AT_FIRST_DX",
        "PAYER_CATEGORY_AT_FIRST_RADIATION",
        "PAYER_CATEGORY_AT_LAST_RADIATION",
    ]
    df_radiation = df.filter(pl.col("HAD_RADIATION") == 1)
    radiation_summary_rows = _build_cohort_summary_rows(df_radiation, RADIATION_COHORT_VARS)
    if radiation_summary_rows:
        pl.DataFrame(radiation_summary_rows).write_csv(reports_dir / "insurance_summary_radiation.csv")
        print(f"  insurance_summary_radiation.csv (N={df_radiation.height:,})")

    # SCT cohort: enrollment + had any stem cell transplant; general insurance + SCT vars
    SCT_COHORT_VARS = [
        "PAYER_CATEGORY_PRIMARY",
        "PAYER_CATEGORY_AT_FIRST_DX",
        "PAYER_CATEGORY_AT_FIRST_SCT",
        "PAYER_CATEGORY_AT_LAST_SCT",
    ]
    df_sct = df.filter(pl.col("HAD_SCT") == 1)
    sct_summary_rows = _build_cohort_summary_rows(df_sct, SCT_COHORT_VARS)
    if sct_summary_rows:
        pl.DataFrame(sct_summary_rows).write_csv(reports_dir / "insurance_summary_sct.csv")
        print(f"  insurance_summary_sct.csv (N={df_sct.height:,})")

    # Normalize payer columns for tables
    for col in ["PAYER_CATEGORY_AT_FIRST_DX", "PAYER_CATEGORY_AT_FIRST_CHEMO"]:
        if col in df.columns:
            df = df.with_columns(_normalize_payer(df[col]).alias(col))

    md_lines: list[str] = []
    md_lines.append("# Insurance Summary (Phase 15)")
    md_lines.append("")
    md_lines.append("Summary tables from encounter-payer summary. Counts 1–10 flagged (⚠) for HIPAA.")
    md_lines.append("")

    # -------------------------------------------------------------------------
    # Table 1: Counts by payer at first DX
    # -------------------------------------------------------------------------
    col_dx = "PAYER_CATEGORY_AT_FIRST_DX"
    if col_dx in df.columns:
        t1 = (
            df.with_columns(pl.col(col_dx).fill_null("Unknown").alias(col_dx))
            .group_by(col_dx)
            .agg(pl.len().alias("N"))
        )
        t1 = _order_categories(t1, col_dx)
        md_lines.append("## Counts by payer at first HL diagnosis")
        md_lines.append("")
        md_lines.append("| Payer category | N |")
        md_lines.append("|----------------|---|")
        for row in t1.iter_rows(named=True):
            n = row["N"]
            md_lines.append(f"| {row[col_dx]} | {flag_small_cell(n)} |")
        md_lines.append("")
        # CSV
        t1_csv = t1.with_columns(
            pl.col("N").map_batches(lambda s: pl.Series([_suppress(int(v)) for v in s], dtype=pl.String))
        )
        t1_csv.write_csv(reports_dir / "payer_at_first_dx.csv")
        print(f"  payer_at_first_dx.csv")
    else:
        md_lines.append("## Counts by payer at first HL diagnosis")
        md_lines.append("")
        md_lines.append("(Column not present.)")
        md_lines.append("")

    # -------------------------------------------------------------------------
    # Table 2: Counts by payer at first chemo (chemo cohort only)
    # -------------------------------------------------------------------------
    col_chemo = "PAYER_CATEGORY_AT_FIRST_CHEMO"
    if col_chemo in df.columns and not df_chemo.is_empty():
        t2 = (
            df_chemo.with_columns(pl.col(col_chemo).fill_null("Unknown").alias(col_chemo))
            .group_by(col_chemo)
            .agg(pl.len().alias("N"))
        )
        t2 = _order_categories(t2, col_chemo)
        md_lines.append("## Counts by payer at first chemotherapy")
        md_lines.append("")
        md_lines.append(f"*Among patients who had chemotherapy only (N = {flag_small_cell(df_chemo.height)}).*")
        md_lines.append("")
        md_lines.append("| Payer category | N |")
        md_lines.append("|----------------|---|")
        for row in t2.iter_rows(named=True):
            n = row["N"]
            md_lines.append(f"| {row[col_chemo]} | {flag_small_cell(n)} |")
        md_lines.append("")
        t2_csv = t2.with_columns(
            pl.col("N").map_batches(lambda s: pl.Series([_suppress(int(v)) for v in s], dtype=pl.String))
        )
        t2_csv.write_csv(reports_dir / "payer_at_first_chemo.csv")
        print(f"  payer_at_first_chemo.csv (N={df_chemo.height})")
    else:
        md_lines.append("## Counts by payer at first chemotherapy")
        md_lines.append("")
        md_lines.append("(Column not present or no patients had chemotherapy.)")
        md_lines.append("")

    # -------------------------------------------------------------------------
    # Table: Counts by payer at first radiation (radiation cohort only)
    # -------------------------------------------------------------------------
    col_rad_first = "PAYER_CATEGORY_AT_FIRST_RADIATION"
    if col_rad_first in df.columns and not df_radiation.is_empty():
        t_rad_first = (
            df_radiation.with_columns(pl.col(col_rad_first).fill_null("Unknown").alias(col_rad_first))
            .group_by(col_rad_first)
            .agg(pl.len().alias("N"))
        )
        t_rad_first = _order_categories(t_rad_first, col_rad_first)
        md_lines.append("## Counts by payer at first radiation")
        md_lines.append("")
        md_lines.append(f"*Among patients who had radiation only (N = {flag_small_cell(df_radiation.height)}).*")
        md_lines.append("")
        md_lines.append("| Payer category | N |")
        md_lines.append("|----------------|---|")
        for row in t_rad_first.iter_rows(named=True):
            n = row["N"]
            md_lines.append(f"| {row[col_rad_first]} | {flag_small_cell(n)} |")
        md_lines.append("")
        t_rad_first_csv = t_rad_first.with_columns(
            pl.col("N").map_batches(lambda s: pl.Series([_suppress(int(v)) for v in s], dtype=pl.String))
        )
        t_rad_first_csv.write_csv(reports_dir / "payer_at_first_radiation.csv")
        print(f"  payer_at_first_radiation.csv (N={df_radiation.height})")
    else:
        md_lines.append("## Counts by payer at first radiation")
        md_lines.append("")
        md_lines.append("(Column not present or no patients had radiation.)")
        md_lines.append("")

    # -------------------------------------------------------------------------
    # Table: Counts by payer at last radiation (radiation cohort only)
    # -------------------------------------------------------------------------
    col_rad_last = "PAYER_CATEGORY_AT_LAST_RADIATION"
    if col_rad_last in df.columns and not df_radiation.is_empty():
        t_rad_last = (
            df_radiation.with_columns(pl.col(col_rad_last).fill_null("Unknown").alias(col_rad_last))
            .group_by(col_rad_last)
            .agg(pl.len().alias("N"))
        )
        t_rad_last = _order_categories(t_rad_last, col_rad_last)
        md_lines.append("## Counts by payer at last radiation")
        md_lines.append("")
        md_lines.append(f"*Among patients who had radiation only (N = {flag_small_cell(df_radiation.height)}).*")
        md_lines.append("")
        md_lines.append("| Payer category | N |")
        md_lines.append("|----------------|---|")
        for row in t_rad_last.iter_rows(named=True):
            n = row["N"]
            md_lines.append(f"| {row[col_rad_last]} | {flag_small_cell(n)} |")
        md_lines.append("")
        t_rad_last_csv = t_rad_last.with_columns(
            pl.col("N").map_batches(lambda s: pl.Series([_suppress(int(v)) for v in s], dtype=pl.String))
        )
        t_rad_last_csv.write_csv(reports_dir / "payer_at_last_radiation.csv")
        print(f"  payer_at_last_radiation.csv (N={df_radiation.height})")
    else:
        md_lines.append("## Counts by payer at last radiation")
        md_lines.append("")
        md_lines.append("(Column not present or no patients had radiation.)")
        md_lines.append("")

    # -------------------------------------------------------------------------
    # Table: Counts by payer at first SCT (SCT cohort only)
    # -------------------------------------------------------------------------
    col_sct_first = "PAYER_CATEGORY_AT_FIRST_SCT"
    if col_sct_first in df.columns and not df_sct.is_empty():
        t_sct_first = (
            df_sct.with_columns(pl.col(col_sct_first).fill_null("Unknown").alias(col_sct_first))
            .group_by(col_sct_first)
            .agg(pl.len().alias("N"))
        )
        t_sct_first = _order_categories(t_sct_first, col_sct_first)
        md_lines.append("## Counts by payer at first stem cell transplant")
        md_lines.append("")
        md_lines.append(f"*Among patients who had stem cell transplant only (N = {flag_small_cell(df_sct.height)}).*")
        md_lines.append("")
        md_lines.append("| Payer category | N |")
        md_lines.append("|----------------|---|")
        for row in t_sct_first.iter_rows(named=True):
            n = row["N"]
            md_lines.append(f"| {row[col_sct_first]} | {flag_small_cell(n)} |")
        md_lines.append("")
        t_sct_first_csv = t_sct_first.with_columns(
            pl.col("N").map_batches(lambda s: pl.Series([_suppress(int(v)) for v in s], dtype=pl.String))
        )
        t_sct_first_csv.write_csv(reports_dir / "payer_at_first_sct.csv")
        print(f"  payer_at_first_sct.csv (N={df_sct.height})")
    else:
        md_lines.append("## Counts by payer at first stem cell transplant")
        md_lines.append("")
        md_lines.append("(Column not present or no patients had stem cell transplant.)")
        md_lines.append("")

    # -------------------------------------------------------------------------
    # Table: Counts by payer at last SCT (SCT cohort only)
    # -------------------------------------------------------------------------
    col_sct_last = "PAYER_CATEGORY_AT_LAST_SCT"
    if col_sct_last in df.columns and not df_sct.is_empty():
        t_sct_last = (
            df_sct.with_columns(pl.col(col_sct_last).fill_null("Unknown").alias(col_sct_last))
            .group_by(col_sct_last)
            .agg(pl.len().alias("N"))
        )
        t_sct_last = _order_categories(t_sct_last, col_sct_last)
        md_lines.append("## Counts by payer at last stem cell transplant")
        md_lines.append("")
        md_lines.append(f"*Among patients who had stem cell transplant only (N = {flag_small_cell(df_sct.height)}).*")
        md_lines.append("")
        md_lines.append("| Payer category | N |")
        md_lines.append("|----------------|---|")
        for row in t_sct_last.iter_rows(named=True):
            n = row["N"]
            md_lines.append(f"| {row[col_sct_last]} | {flag_small_cell(n)} |")
        md_lines.append("")
        t_sct_last_csv = t_sct_last.with_columns(
            pl.col("N").map_batches(lambda s: pl.Series([_suppress(int(v)) for v in s], dtype=pl.String))
        )
        t_sct_last_csv.write_csv(reports_dir / "payer_at_last_sct.csv")
        print(f"  payer_at_last_sct.csv (N={df_sct.height})")
    else:
        md_lines.append("## Counts by payer at last stem cell transplant")
        md_lines.append("")
        md_lines.append("(Column not present or no patients had stem cell transplant.)")
        md_lines.append("")

    # -------------------------------------------------------------------------
    # Table 3: Cross-tab first DX vs first chemo
    # -------------------------------------------------------------------------
    if col_dx in df.columns and col_chemo in df.columns:
        ct = (
            df.select(pl.col(col_dx).fill_null("Unknown"), pl.col(col_chemo).fill_null("Unknown"))
            .group_by(col_dx, col_chemo)
            .agg(pl.len().alias("N"))
        )
        rows_ord = {c: i for i, c in enumerate(PAYER_CATEGORY_ORDER)}
        cols_ord = rows_ord
        row_cats = sorted(ct[col_dx].unique().to_list(), key=lambda c: rows_ord.get(c, 99))
        col_cats = sorted(ct[col_chemo].unique().to_list(), key=lambda c: cols_ord.get(c, 99))
        # Build markdown table with row/column totals
        md_lines.append("## Cross-tab: Payer at first diagnosis vs payer at first chemotherapy")
        md_lines.append("")
        header = "| Payer (first DX) | " + " | ".join(col_cats) + " | Total |"
        md_lines.append(header)
        md_lines.append("|" + "---|" * (len(col_cats) + 2))
        ct_map = {(r, c): n for r, c, n in ct.iter_rows()}
        for r in row_cats:
            cells = [r]
            row_total = 0
            for c in col_cats:
                n = ct_map.get((r, c), 0)
                row_total += n
                cells.append(flag_small_cell(n))
            cells.append(flag_small_cell(row_total))
            md_lines.append("| " + " | ".join(cells) + " |")
        col_totals = [sum(ct_map.get((r, c), 0) for r in row_cats) for c in col_cats]
        total_total = sum(col_totals)
        total_row = ["Total"] + [flag_small_cell(n) for n in col_totals] + [flag_small_cell(total_total)]
        md_lines.append("| " + " | ".join(total_row) + " |")
        md_lines.append("")
        # CSV: rows = first DX, columns = first chemo
        # Write CSV with proper headers
        with open(reports_dir / "payer_crosstab_first_dx_first_chemo.csv", "w", encoding="utf-8") as f:
            f.write(",".join(["PAYER_AT_FIRST_DX"] + col_cats + ["Total"]) + "\n")
            for r in row_cats:
                row_total = 0
                cells = [r]
                for c in col_cats:
                    n = ct_map.get((r, c), 0)
                    row_total += n
                    cells.append(_suppress(n))
                cells.append(_suppress(row_total))
                f.write(",".join(cells) + "\n")
            f.write(",".join(["Total"] + [_suppress(n) for n in col_totals] + [_suppress(total_total)]) + "\n")
        print(f"  payer_crosstab_first_dx_first_chemo.csv")
    else:
        md_lines.append("## Cross-tab: Payer at first diagnosis vs payer at first chemotherapy")
        md_lines.append("")
        md_lines.append("(Columns not present.)")
        md_lines.append("")

    # -------------------------------------------------------------------------
    # Table 4: PAYER_TRANSITION prevalence
    # -------------------------------------------------------------------------
    if "PAYER_TRANSITION" in df.columns:
        n_total = df.height
        n_transition = df.filter(pl.col("PAYER_TRANSITION") == 1).height
        pct = (100.0 * n_transition / n_total) if n_total else 0.0
        md_lines.append("## Payer transition prevalence")
        md_lines.append("")
        md_lines.append("| Metric | Value |")
        md_lines.append("|--------|-------|")
        md_lines.append(f"| Patients with payer transition (1+ category change) | {flag_small_cell(n_transition)} |")
        md_lines.append(f"| Total N | {flag_small_cell(n_total)} |")
        md_lines.append(f"| % with transition | {flag_small_cell(int(round(pct)))} |")
        md_lines.append("")
        trans_df = pl.DataFrame({
            "Metric": ["N_with_transition", "N_total", "Pct_transition"],
            "Value": [_suppress(n_transition), _suppress(n_total), _suppress(int(round(pct)))],
        })
        trans_df.write_csv(reports_dir / "payer_transition_prevalence.csv")
        print(f"  payer_transition_prevalence.csv")
    else:
        md_lines.append("## Payer transition prevalence")
        md_lines.append("")
        md_lines.append("(Column not present.)")
        md_lines.append("")

    # -------------------------------------------------------------------------
    # Table 5: DUAL_ELIGIBLE prevalence
    # -------------------------------------------------------------------------
    if "DUAL_ELIGIBLE" in df.columns:
        n_dual = df.filter(pl.col("DUAL_ELIGIBLE") == 1).height
        n_not_dual = df.filter(pl.col("DUAL_ELIGIBLE") == 0).height
        pct_dual = (100.0 * n_dual / n_total) if n_total else 0.0
        md_lines.append("## Dual-eligible prevalence")
        md_lines.append("")
        md_lines.append("| Metric | Value |")
        md_lines.append("|--------|-------|")
        md_lines.append(f"| Patients dual-eligible (Medicare+Medicaid or code 14/141/142) | {flag_small_cell(n_dual)} |")
        md_lines.append(f"| Patients not dual-eligible | {flag_small_cell(n_not_dual)} |")
        md_lines.append(f"| Total N | {flag_small_cell(n_total)} |")
        md_lines.append(f"| % dual-eligible | {flag_small_cell(int(round(pct_dual)))} |")
        md_lines.append("")
        dual_df = pl.DataFrame({
            "Metric": ["N_dual_eligible", "N_not_dual_eligible", "N_total", "Pct_dual_eligible"],
            "Value": [_suppress(n_dual), _suppress(n_not_dual), _suppress(n_total), _suppress(int(round(pct_dual)))],
        })
        dual_df.write_csv(reports_dir / "dual_eligible_prevalence.csv")
        print(f"  dual_eligible_prevalence.csv")
    else:
        md_lines.append("## Dual-eligible prevalence")
        md_lines.append("")
        md_lines.append("(Column not present.)")
        md_lines.append("")

    # -------------------------------------------------------------------------
    # Treatment-specific cohorts (enrollment + had that treatment)
    # -------------------------------------------------------------------------
    md_lines.append("## Summary by treatment type")
    md_lines.append("")
    md_lines.append("Cohorts: enrolled patients who had at least one occurrence of the treatment. Full counts by variable are in the CSV files below.")
    md_lines.append("")
    n_chemo = df.filter(pl.col("HAD_CHEMO") == 1).height if "HAD_CHEMO" in df.columns else 0
    n_rad = df.filter(pl.col("HAD_RADIATION") == 1).height if "HAD_RADIATION" in df.columns else 0
    n_sct = df.filter(pl.col("HAD_SCT") == 1).height if "HAD_SCT" in df.columns else 0
    md_lines.append("| Cohort | N | Summary file |")
    md_lines.append("|--------|---|--------------|")
    md_lines.append(f"| Chemo (any chemo) | {flag_small_cell(n_chemo)} | insurance_summary_chemo.csv |")
    md_lines.append(f"| Radiation (any radiation) | {flag_small_cell(n_rad)} | insurance_summary_radiation.csv |")
    md_lines.append(f"| Stem cell transplant (any SCT) | {flag_small_cell(n_sct)} | insurance_summary_sct.csv |")
    md_lines.append("")
    md_lines.append("Each CSV has: Variable, Category, N, Pct (general insurance + treatment-specific payer variables; PAYER_TRANSITION and DUAL_ELIGIBLE included).")
    md_lines.append("")

    # Write markdown report
    (reports_dir / "insurance_summary.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"  insurance_summary.md")

    # -------------------------------------------------------------------------
    # Figures: bar charts (exclude categories with count 1–10)
    # -------------------------------------------------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available; skipping figures.")
    else:
        def _plot_payer_bars(counts_df: pl.DataFrame, category_col: str, title: str, out_path: Path) -> None:
            # Exclude categories with 1 <= N <= 10 for HIPAA
            safe = counts_df.filter(
                (pl.col("N") > SMALL_CELL_THRESHOLD) | (pl.col("N") == 0)
            )
            if safe.is_empty():
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.text(0.5, 0.5, "All categories suppressed (1–10); no bars shown.", ha="center", va="center")
                ax.set_title(title)
                fig.savefig(out_path, dpi=150, bbox_inches="tight")
                plt.close(fig)
                return
            safe = _order_categories(safe, category_col)
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.bar(safe[category_col].to_list(), safe["N"].to_list(), color="steelblue", edgecolor="black")
            ax.set_title(title)
            ax.set_ylabel("N (categories with 1–10 excluded)")
            plt.xticks(rotation=45, ha="right")
            fig.tight_layout()
            fig.savefig(out_path, dpi=150, bbox_inches="tight")
            plt.close(fig)

        if col_dx in df.columns:
            t1 = (
                df.with_columns(pl.col(col_dx).fill_null("Unknown").alias(col_dx))
                .group_by(col_dx)
                .agg(pl.len().alias("N"))
            )
            _plot_payer_bars(
                t1,
                col_dx,
                "Payer at first HL diagnosis",
                figures_dir / "insurance_payer_at_first_dx.png",
            )
            print(f"  figures/insurance_payer_at_first_dx.png")
        if col_chemo in df.columns:
            t2 = (
                df.with_columns(pl.col(col_chemo).fill_null("Unknown").alias(col_chemo))
                .group_by(col_chemo)
                .agg(pl.len().alias("N"))
            )
            _plot_payer_bars(
                t2,
                col_chemo,
                "Payer at first chemotherapy",
                figures_dir / "insurance_payer_at_first_chemo.png",
            )
            print(f"  figures/insurance_payer_at_first_chemo.png")

    print("\nDone.")


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(config_path)
