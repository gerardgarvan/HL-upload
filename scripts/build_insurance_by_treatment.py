"""Build treatment-stratified insurance summary tables (Phase 5).

Reads derived/encounter_payer_summary.parquet, produces:
- reports/insurance_by_treatment/chemotherapy_table.csv
- reports/insurance_by_treatment/radiation_table.csv
- reports/insurance_by_treatment/sct_table.csv
- reports/insurance_by_treatment/overview_table.csv
- reports/insurance_by_treatment/README.md (combined markdown preview)

Each table has 9 payer category rows (Medicare through Unknown), 3 columns
(Primary Insurance, First Treatment, Last Treatment), and N (%) cell values.
No HIPAA suppression applied - shows all counts as-is for internal use.

Usage:
    python scripts/build_insurance_by_treatment.py [config/paths.toml]
"""

import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl

from src.load.config import load_and_validate_config

# Standard payer category order (9 categories)
PAYER_CATEGORY_ORDER = [
    "Medicare",
    "Medicaid",
    "Dual eligible",
    "Private",
    "Other government",
    "Self-pay",
    "Other",
    "Unavailable",
    "Unknown",
]

# Required columns per treatment type
REQUIRED_COLUMNS = {
    "chemo": [
        "HAD_CHEMO",
        "PAYER_CATEGORY_PRIMARY",
        "PAYER_CATEGORY_AT_FIRST_CHEMO",
        "PAYER_CATEGORY_AT_LAST_CHEMO",
    ],
    "radiation": [
        "HAD_RADIATION",
        "PAYER_CATEGORY_PRIMARY",
        "PAYER_CATEGORY_AT_FIRST_RADIATION",
        "PAYER_CATEGORY_AT_LAST_RADIATION",
    ],
    "sct": [
        "HAD_SCT",
        "PAYER_CATEGORY_PRIMARY",
        "PAYER_CATEGORY_AT_FIRST_SCT",
        "PAYER_CATEGORY_AT_LAST_SCT",
    ],
}


def _normalize_payer(s: pl.Series) -> pl.Series:
    """Replace null and empty string payer values with 'Unknown' for consistent reporting.

    Args:
        s: Polars Series of payer category strings (may contain nulls or empty strings)

    Returns:
        Series with nulls and empty strings replaced by "Unknown", dtype pl.String
    """
    return pl.Series(
        [("Unknown" if (v is None or v == "") else v) for v in s],
        dtype=pl.String,
    )


def _build_table(
    df: pl.DataFrame,
    primary_col: str,
    first_col: str,
    last_col: str,
    cohort_label: str,
) -> tuple[list[dict], int]:
    """Build treatment-stratified summary table with 9 payer rows and 3 columns.

    Args:
        df: Filtered cohort DataFrame (e.g., HAD_CHEMO==1)
        primary_col: Column name for primary insurance (mode across encounters)
        first_col: Column name for insurance at first treatment
        last_col: Column name for insurance at last treatment
        cohort_label: Label for cohort (e.g., "Chemotherapy")

    Returns:
        Tuple of (list of row dicts, cohort size)
    """
    cohort_size = df.height
    if cohort_size == 0:
        # Return empty rows with 0 counts for all categories
        rows = []
        for cat in PAYER_CATEGORY_ORDER:
            rows.append({
                "Payer Category": cat,
                "Primary Insurance (N)": 0,
                "Primary Insurance (%)": 0.0,
                "First Treatment (N)": 0,
                "First Treatment (%)": 0.0,
                "Last Treatment (N)": 0,
                "Last Treatment (%)": 0.0,
                "Primary Insurance (N_Pct)": "0 (0.0%)",
                "First Treatment (N_Pct)": "0 (0.0%)",
                "Last Treatment (N_Pct)": "0 (0.0%)",
            })
        return rows, cohort_size

    # Normalize payer columns (null -> "Unknown")
    df_norm = df.with_columns([
        _normalize_payer(df[primary_col]).alias("_primary"),
        _normalize_payer(df[first_col]).alias("_first"),
        _normalize_payer(df[last_col]).alias("_last"),
    ])

    # Count by category for each column
    primary_counts = df_norm.group_by("_primary").agg(pl.len().alias("N")).rename({"_primary": "Category"})
    first_counts = df_norm.group_by("_first").agg(pl.len().alias("N")).rename({"_first": "Category"})
    last_counts = df_norm.group_by("_last").agg(pl.len().alias("N")).rename({"_last": "Category"})

    # Convert to lookup dicts
    primary_map = {row["Category"]: row["N"] for row in primary_counts.iter_rows(named=True)}
    first_map = {row["Category"]: row["N"] for row in first_counts.iter_rows(named=True)}
    last_map = {row["Category"]: row["N"] for row in last_counts.iter_rows(named=True)}

    # Build rows in standard order
    rows = []
    for cat in PAYER_CATEGORY_ORDER:
        n_primary = primary_map.get(cat, 0)
        n_first = first_map.get(cat, 0)
        n_last = last_map.get(cat, 0)

        pct_primary = 100.0 * n_primary / cohort_size if cohort_size > 0 else 0.0
        pct_first = 100.0 * n_first / cohort_size if cohort_size > 0 else 0.0
        pct_last = 100.0 * n_last / cohort_size if cohort_size > 0 else 0.0

        rows.append({
            "Payer Category": cat,
            "Primary Insurance (N)": n_primary,
            "Primary Insurance (%)": pct_primary,
            "First Treatment (N)": n_first,
            "First Treatment (%)": pct_first,
            "Last Treatment (N)": n_last,
            "Last Treatment (%)": pct_last,
            "Primary Insurance (N_Pct)": f"{n_primary} ({pct_primary:.1f}%)",
            "First Treatment (N_Pct)": f"{n_first} ({pct_first:.1f}%)",
            "Last Treatment (N_Pct)": f"{n_last} ({pct_last:.1f}%)",
        })

    return rows, cohort_size


def main(config_path: Path | None = None) -> None:
    """Phase 5: Build treatment-stratified insurance summary tables.

    Generates 4 summary tables (chemo, radiation, SCT, overview) with insurance
    coverage patterns at different timepoints (primary, first treatment, last treatment).
    Each table has 9 payer category rows and 3 columns. No small-cell suppression.

    Creates reports/insurance_by_treatment/ directory with CSV and markdown outputs.

    Args:
        config_path: Optional path to config/paths.toml (uses default if None)

    Raises:
        SystemExit: Exits with code 0 if parquet missing (not an error)
        SystemExit: Exits with code 1 if ALL treatment columns are missing
    """
    print("=" * 60)
    print("INSURANCE BY TREATMENT ANALYSIS — Summary Tables")
    print("=" * 60)

    paths = load_and_validate_config(config_path)
    derived_dir = paths.derived_dir
    reports_dir = PROJECT_ROOT / "reports" / "insurance_by_treatment"
    reports_dir.mkdir(parents=True, exist_ok=True)

    enc_path = derived_dir / "encounter_payer_summary.parquet"
    if not enc_path.exists():
        print("encounter_payer_summary.parquet missing; skipping.")
        sys.exit(0)

    df = pl.read_parquet(enc_path)
    if df.is_empty():
        print("encounter_payer_summary.parquet is empty; skipping.")
        sys.exit(0)

    print(f"\n  derived_dir: {derived_dir}")
    print(f"  Rows: {df.height:,}")

    # Validate which treatment column sets are present
    available_treatments = []
    missing_treatments = []

    for treatment, required_cols in REQUIRED_COLUMNS.items():
        if all(col in df.columns for col in required_cols):
            available_treatments.append(treatment)
        else:
            missing_cols = [col for col in required_cols if col not in df.columns]
            missing_treatments.append((treatment, missing_cols))
            print(f"\n  [WARNING] Required columns missing for {treatment}: {missing_cols}")
            print(f"            Re-run: python scripts/assemble_clean.py")

    if not available_treatments:
        print("\n  [FATAL] ALL treatment columns are missing. Cannot generate any tables.")
        print("          Re-run: python scripts/assemble_clean.py")
        sys.exit(1)

    print(f"\n  Available treatments: {', '.join(available_treatments)}")

    # Build tables for available treatments
    tables = {}

    # Chemotherapy table
    if "chemo" in available_treatments:
        df_chemo = df.filter(pl.col("HAD_CHEMO") == 1)
        chemo_rows, chemo_size = _build_table(
            df_chemo,
            "PAYER_CATEGORY_PRIMARY",
            "PAYER_CATEGORY_AT_FIRST_CHEMO",
            "PAYER_CATEGORY_AT_LAST_CHEMO",
            "Chemotherapy",
        )
        tables["chemotherapy"] = (chemo_rows, chemo_size)
        print(f"\n  Chemotherapy cohort: N={chemo_size:,}")

    # Radiation table
    if "radiation" in available_treatments:
        df_radiation = df.filter(pl.col("HAD_RADIATION") == 1)
        radiation_rows, radiation_size = _build_table(
            df_radiation,
            "PAYER_CATEGORY_PRIMARY",
            "PAYER_CATEGORY_AT_FIRST_RADIATION",
            "PAYER_CATEGORY_AT_LAST_RADIATION",
            "Radiation",
        )
        tables["radiation"] = (radiation_rows, radiation_size)
        print(f"  Radiation cohort: N={radiation_size:,}")

    # SCT table
    if "sct" in available_treatments:
        df_sct = df.filter(pl.col("HAD_SCT") == 1)
        sct_rows, sct_size = _build_table(
            df_sct,
            "PAYER_CATEGORY_PRIMARY",
            "PAYER_CATEGORY_AT_FIRST_SCT",
            "PAYER_CATEGORY_AT_LAST_SCT",
            "SCT",
        )
        tables["sct"] = (sct_rows, sct_size)
        print(f"  SCT cohort: N={sct_size:,}")

    # Overview table (all enrolled patients)
    # Use PAYER_CATEGORY_PRIMARY for all 3 columns
    # If PAYER_CATEGORY_AT_FIRST_DX exists, use it for first column instead
    first_dx_col = "PAYER_CATEGORY_AT_FIRST_DX" if "PAYER_CATEGORY_AT_FIRST_DX" in df.columns else "PAYER_CATEGORY_PRIMARY"
    overview_rows, overview_size = _build_table(
        df,
        "PAYER_CATEGORY_PRIMARY",
        first_dx_col,
        "PAYER_CATEGORY_PRIMARY",
        "Overview",
    )
    tables["overview"] = (overview_rows, overview_size)
    print(f"  Overview cohort (all enrolled): N={overview_size:,}")

    # Write CSV files
    print("\n  Writing CSV files...")
    for name, (rows, size) in tables.items():
        df_table = pl.DataFrame(rows)
        csv_path = reports_dir / f"{name}_table.csv"
        df_table.write_csv(csv_path)
        print(f"    {name}_table.csv")

    # Write combined markdown README
    print("\n  Writing markdown README...")
    md_lines = []
    md_lines.append("# Insurance by Treatment Analysis")
    md_lines.append("")
    md_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md_lines.append("")
    md_lines.append("Summary tables of insurance coverage patterns stratified by treatment type.")
    md_lines.append("Each table shows payer category distributions at three timepoints:")
    md_lines.append("- Primary Insurance: Mode payer category across all encounters")
    md_lines.append("- First Treatment: Payer category at first occurrence of treatment")
    md_lines.append("- Last Treatment: Payer category at last occurrence of treatment")
    md_lines.append("")

    # Add each table
    table_order = ["chemotherapy", "radiation", "sct", "overview"]
    table_labels = {
        "chemotherapy": "Chemotherapy",
        "radiation": "Radiation",
        "sct": "Stem Cell Transplant (SCT)",
        "overview": "Overview (All Enrolled Patients)",
    }

    for name in table_order:
        if name not in tables:
            continue
        rows, size = tables[name]
        label = table_labels[name]

        md_lines.append(f"## {label} Cohort (N={size:,})")
        md_lines.append("")
        md_lines.append("| Payer Category | Primary Insurance | First Treatment | Last Treatment |")
        md_lines.append("|----------------|-------------------|-----------------|----------------|")
        for row in rows:
            md_lines.append(
                f"| {row['Payer Category']} | "
                f"{row['Primary Insurance (N_Pct)']} | "
                f"{row['First Treatment (N_Pct)']} | "
                f"{row['Last Treatment (N_Pct)']} |"
            )
        md_lines.append("")

    md_lines.append("---")
    md_lines.append("")
    md_lines.append("**Source:** encounter_payer_summary.parquet")
    md_lines.append("")
    md_lines.append("**Note:** No HIPAA suppression applied. These are internal working tables.")

    readme_path = reports_dir / "README.md"
    readme_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"    README.md")

    print("\nDone.")


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(config_path)
