"""Build treatment-stratified insurance summary tables (Phase 5).

Reads derived/encounter_payer_summary.parquet, produces:
- reports/insurance_by_treatment/*.csv (4 tables: chemo, radiation, SCT, overview)
- reports/insurance_by_treatment/*.png (4 color-coded table images)
- reports/insurance_by_treatment/*.html (4 styled HTML tables)
- reports/insurance_by_treatment/README.md (combined markdown preview)

Each table has 9 payer category rows (Medicare through Unknown), 3 columns
(Primary Insurance, First Treatment, Last Treatment), and N (%) cell values.
No HIPAA suppression applied - shows all counts as-is for internal use.

PNG images use seaborn Pastel1 palette for color-coded payer categories.
HTML files are self-contained with inline CSS matching PNG colors.

Usage:
    python scripts/build_insurance_by_treatment.py [config/paths.toml]
"""

import sys
from pathlib import Path
from datetime import datetime
import html

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl

from src.load.config import load_and_validate_config

# Optional matplotlib imports for PNG rendering
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.colors
    import seaborn as sns
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

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

# Color palette for PNG and HTML rendering
if MATPLOTLIB_AVAILABLE:
    # Use seaborn Pastel1 palette for payer categories
    _palette = sns.color_palette("Pastel1", n_colors=9)
    PAYER_COLORS = {
        category: matplotlib.colors.to_hex(color)
        for category, color in zip(PAYER_CATEGORY_ORDER, _palette)
    }
    HEADER_COLOR = "#2C5AA0"  # Dark blue for headers
else:
    PAYER_COLORS = {}
    HEADER_COLOR = "#2C5AA0"

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


def _render_png(
    table_data: list[dict], title: str, output_path: Path,
    first_label: str = "First Treatment", last_label: str = "Last Treatment",
) -> None:
    """Render summary table as PNG image with color-coded payer category rows.

    Args:
        table_data: List of row dicts from _build_table()
        title: Title text with cohort name and size, e.g., "Chemotherapy Cohort (N=192)"
        output_path: Path to save PNG file
        first_label: Column header for first-treatment column (e.g., "First Chemo")
        last_label: Column header for last-treatment column (e.g., "Last Chemo")
    """
    if not MATPLOTLIB_AVAILABLE:
        print(f"    [SKIPPED] {output_path.name} (matplotlib not available)")
        return

    # Extract data for table rendering
    cellText = []
    cellColours = []

    for row in table_data:
        payer_cat = row["Payer Category"]
        # Use N_Pct formatted strings for display
        primary = row["Primary Insurance (N_Pct)"]
        first = row[f"{first_label} (N_Pct)"]
        last = row[f"{last_label} (N_Pct)"]

        cellText.append([payer_cat, primary, first, last])

        # All cells in this row get the same payer category color
        row_color = PAYER_COLORS.get(payer_cat, "#FFFFFF")
        cellColours.append([row_color, row_color, row_color, row_color])

    # Create figure and table
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.axis('off')

    col_labels = ["Payer Category", "Primary Insurance", first_label, last_label]

    table = ax.table(
        cellText=cellText,
        colLabels=col_labels,
        cellColours=cellColours,
        loc='center',
        cellLoc='center'
    )

    # Style header cells (row 0)
    for col_idx in range(len(col_labels)):
        cell = table[(0, col_idx)]
        cell.set_facecolor(HEADER_COLOR)
        cell.set_text_props(weight='bold', color='white')

    # Left-align first column (Payer Category)
    for row_idx in range(len(table_data)):
        cell = table[(row_idx + 1, 0)]  # +1 because row 0 is header
        cell.set_text_props(ha='left')

    # Font and scaling
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.2, 2.0)

    # Title
    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.95)

    # Save
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def _render_html(
    table_data: list[dict], title: str, output_path: Path,
    first_label: str = "First Treatment", last_label: str = "Last Treatment",
) -> None:
    """Render summary table as styled HTML file with inline CSS.

    Args:
        table_data: List of row dicts from _build_table()
        title: Title text with cohort name and size
        output_path: Path to save HTML file
        first_label: Column header for first-treatment column (e.g., "First Chemo")
        last_label: Column header for last-treatment column (e.g., "Last Chemo")
    """
    # Generate CSS classes for payer categories
    css_classes = []
    for category in PAYER_CATEGORY_ORDER:
        class_name = category.lower().replace(" ", "-")
        color = PAYER_COLORS.get(category, "#FFFFFF")
        css_classes.append(f"  .payer-{class_name} {{ background-color: {color}; }}")

    css_block = "\n".join(css_classes)

    # Build HTML
    html_lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        '  <meta charset="UTF-8">',
        "  <style>",
        "    body {",
        "      font-family: Arial, sans-serif;",
        "      padding: 20px;",
        "    }",
        "    h2 {",
        "      text-align: center;",
        "      color: #333;",
        "    }",
        "    table {",
        "      border-collapse: collapse;",
        "      margin: 20px auto;",
        "      box-shadow: 0 2px 4px rgba(0,0,0,0.1);",
        "    }",
        "    th {",
        "      background-color: #2C5AA0;",
        "      color: white;",
        "      padding: 12px 16px;",
        "      text-align: left;",
        "      border: 1px solid #2C5AA0;",
        "      font-weight: bold;",
        "    }",
        "    td {",
        "      padding: 10px 16px;",
        "      border: 1px solid #ddd;",
        "    }",
        "    tbody tr:hover {",
        "      filter: brightness(0.95);",
        "    }",
        css_block,
        "    .footer {",
        "      text-align: center;",
        "      margin-top: 20px;",
        "      font-size: 12px;",
        "      color: #666;",
        "    }",
        "  </style>",
        "</head>",
        "<body>",
        f"  <h2>{html.escape(title)}</h2>",
        "  <table>",
        "    <thead>",
        "      <tr>",
        "        <th>Payer Category</th>",
        "        <th>Primary Insurance</th>",
        f"        <th>{html.escape(first_label)}</th>",
        f"        <th>{html.escape(last_label)}</th>",
        "      </tr>",
        "    </thead>",
        "    <tbody>",
    ]

    # Add data rows
    for row in table_data:
        payer_cat = row["Payer Category"]
        class_name = payer_cat.lower().replace(" ", "-")
        primary = html.escape(row["Primary Insurance (N_Pct)"])
        first = html.escape(row[f"{first_label} (N_Pct)"])
        last = html.escape(row[f"{last_label} (N_Pct)"])

        html_lines.append(f'      <tr class="payer-{class_name}">')
        html_lines.append(f"        <td>{html.escape(payer_cat)}</td>")
        html_lines.append(f"        <td>{primary}</td>")
        html_lines.append(f"        <td>{first}</td>")
        html_lines.append(f"        <td>{last}</td>")
        html_lines.append("      </tr>")

    # Footer
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html_lines.extend([
        "    </tbody>",
        "  </table>",
        '  <div class="footer">',
        f"    Source: encounter_payer_summary.parquet | Generated: {timestamp}",
        "  </div>",
        "</body>",
        "</html>",
    ])

    output_path.write_text("\n".join(html_lines), encoding="utf-8")


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
    first_label: str = "First Treatment",
    last_label: str = "Last Treatment",
) -> tuple[list[dict], int]:
    """Build treatment-stratified summary table with 9 payer rows and 3 columns.

    Args:
        df: Filtered cohort DataFrame (e.g., HAD_CHEMO==1)
        primary_col: Column name for primary insurance (mode across encounters)
        first_col: Column name for insurance at first treatment
        last_col: Column name for insurance at last treatment
        cohort_label: Label for cohort (e.g., "Chemotherapy")
        first_label: Column header for the first-treatment column (e.g., "First Chemo")
        last_label: Column header for the last-treatment column (e.g., "Last Chemo")

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
                f"{first_label} (N)": 0,
                f"{first_label} (%)": 0.0,
                f"{last_label} (N)": 0,
                f"{last_label} (%)": 0.0,
                "Primary Insurance (N_Pct)": "0 (0.0%)",
                f"{first_label} (N_Pct)": "0 (0.0%)",
                f"{last_label} (N_Pct)": "0 (0.0%)",
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
            f"{first_label} (N)": n_first,
            f"{first_label} (%)": pct_first,
            f"{last_label} (N)": n_last,
            f"{last_label} (%)": pct_last,
            "Primary Insurance (N_Pct)": f"{n_primary} ({pct_primary:.1f}%)",
            f"{first_label} (N_Pct)": f"{n_first} ({pct_first:.1f}%)",
            f"{last_label} (N_Pct)": f"{n_last} ({pct_last:.1f}%)",
        })

    return rows, cohort_size


def main(config_path: Path | None = None) -> None:
    """Phase 5: Build treatment-stratified insurance summary tables.

    Generates 4 summary tables (chemo, radiation, SCT, overview) with insurance
    coverage patterns at different timepoints (primary, first treatment, last treatment).
    Each table has 9 payer category rows and 3 columns. No small-cell suppression.

    Creates reports/insurance_by_treatment/ directory with CSV, PNG, HTML, and markdown outputs.

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
    # Each entry: (rows, cohort_size, first_label, last_label)
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
            first_label="First Chemo",
            last_label="Last Chemo",
        )
        tables["chemotherapy"] = (chemo_rows, chemo_size, "First Chemo", "Last Chemo")
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
            first_label="First Radiation",
            last_label="Last Radiation",
        )
        tables["radiation"] = (radiation_rows, radiation_size, "First Radiation", "Last Radiation")
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
            first_label="First SCT",
            last_label="Last SCT",
        )
        tables["sct"] = (sct_rows, sct_size, "First SCT", "Last SCT")
        print(f"  SCT cohort: N={sct_size:,}")

    # Overview table (all enrolled patients)
    # If PAYER_CATEGORY_AT_FIRST_DX exists, use it for first column
    first_dx_col = "PAYER_CATEGORY_AT_FIRST_DX" if "PAYER_CATEGORY_AT_FIRST_DX" in df.columns else "PAYER_CATEGORY_PRIMARY"
    overview_first_label = "First Diagnosis" if "PAYER_CATEGORY_AT_FIRST_DX" in df.columns else "Primary Insurance"
    overview_rows, overview_size = _build_table(
        df,
        "PAYER_CATEGORY_PRIMARY",
        first_dx_col,
        "PAYER_CATEGORY_PRIMARY",
        "Overview",
        first_label=overview_first_label,
        last_label="Primary Insurance",
    )
    tables["overview"] = (overview_rows, overview_size, overview_first_label, "Primary Insurance")
    print(f"  Overview cohort (all enrolled): N={overview_size:,}")

    # Write CSV files and render PNG/HTML
    print("\n  Writing output files...")
    for name, (rows, size, first_lbl, last_lbl) in tables.items():
        # CSV
        df_table = pl.DataFrame(rows)
        csv_path = reports_dir / f"{name}_table.csv"
        df_table.write_csv(csv_path)
        print(f"    {name}_table.csv")

        # PNG
        title_label = name.replace("_", " ").title()
        if name == "sct":
            title_label = "SCT"
        elif name == "chemotherapy":
            title_label = "Chemotherapy"
        elif name == "radiation":
            title_label = "Radiation"
        elif name == "overview":
            title_label = "Overview (All Enrolled Patients)"

        png_title = f"{title_label} Cohort (N={size:,})"
        png_path = reports_dir / f"{name}_table.png"
        _render_png(rows, png_title, png_path, first_label=first_lbl, last_label=last_lbl)
        if MATPLOTLIB_AVAILABLE:
            print(f"    {name}_table.png")

        # HTML
        html_path = reports_dir / f"{name}_table.html"
        _render_html(rows, png_title, html_path, first_label=first_lbl, last_label=last_lbl)
        print(f"    {name}_table.html")

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
    md_lines.append("- First {Treatment}: Payer category at first occurrence of that treatment")
    md_lines.append("- Last {Treatment}: Payer category at last occurrence of that treatment")
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
        rows, size, first_lbl, last_lbl = tables[name]
        label = table_labels[name]

        md_lines.append(f"## {label} Cohort (N={size:,})")
        md_lines.append("")
        md_lines.append(f"| Payer Category | Primary Insurance | {first_lbl} | {last_lbl} |")
        md_lines.append("|----------------|-------------------|" + "-" * (len(first_lbl) + 2) + "|" + "-" * (len(last_lbl) + 2) + "|")
        for row in rows:
            md_lines.append(
                f"| {row['Payer Category']} | "
                f"{row['Primary Insurance (N_Pct)']} | "
                f"{row[f'{first_lbl} (N_Pct)']} | "
                f"{row[f'{last_lbl} (N_Pct)']} |"
            )
        md_lines.append("")

    # Methodology section
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## Methodology")
    md_lines.append("")
    md_lines.append("### Treatment Identification")
    md_lines.append("")
    md_lines.append("Treatment flags are derived from procedure codes and clinical records:")
    md_lines.append("")
    md_lines.append("**Chemotherapy (HAD_CHEMO)**")
    md_lines.append("- Tumor registry tables: DT_CHEMO and CHEMO_START_DATE_SUMMARY columns")
    md_lines.append("- PRESCRIBING table: RX_ORDER_DATE for enrolled patients")
    md_lines.append("- First/last chemo date = min/max date across all sources")
    md_lines.append("")
    md_lines.append("**Radiation (HAD_RADIATION)**")
    md_lines.append("- Tumor registry tables: DT_RAD column")
    md_lines.append("- PROCEDURES table filtered to CPT codes: 77401, 77402, 77407, 77412, 77427")
    md_lines.append("- First/last radiation date = min/max date across all sources")
    md_lines.append("")
    md_lines.append("**Stem Cell Transplant (HAD_SCT)**")
    md_lines.append("- PROCEDURES table filtered to CPT codes: 38230, 38232, 38240, 38241, 38242")
    md_lines.append("- Plus ICD-10-PCS codes for transfusion/infusion (30230xx\u201330243xx, XW0xxxxx)")
    md_lines.append("- First/last SCT date = min/max date across all sources")
    md_lines.append("")
    md_lines.append("### Insurance (Payer) Derivation")
    md_lines.append("")
    md_lines.append("**Effective payer per encounter:**")
    md_lines.append("1. Use PAYER_TYPE_PRIMARY if valid (non-null, non-empty, not a sentinel)")
    md_lines.append("2. Fall back to PAYER_TYPE_SECONDARY if primary is invalid")
    md_lines.append("3. Sentinel values triggering fallback: NI, UN, OT")
    md_lines.append("")
    md_lines.append("**Payer category mapping** (PCORnet codes \u2192 9 categories):")
    md_lines.append("")
    md_lines.append("| PCORnet Code Prefix | Payer Category |")
    md_lines.append("|---------------------|----------------|")
    md_lines.append("| 1xx (11, 12, 121\u2026) | Medicare |")
    md_lines.append("| 2xx (21, 22, 221\u2026) | Medicaid |")
    md_lines.append("| 14, 141, 142 or Medicare+Medicaid combo | Dual eligible |")
    md_lines.append("| 5xx, 6xx | Private |")
    md_lines.append("| 3xx, 4xx (VA, TriCare, IHS, Corrections) | Other government |")
    md_lines.append("| 8xx | Self-pay |")
    md_lines.append("| 7xx, 9xx (except 99/9999) | Other |")
    md_lines.append("| 99, 9999 | Unavailable |")
    md_lines.append("| null, empty, NI, UN, OT | Unknown |")
    md_lines.append("")
    md_lines.append("**Dual-eligible override:** If primary is Medicare and secondary is Medicaid")
    md_lines.append("(or vice versa), or if either payer code is 14/141/142, the encounter is")
    md_lines.append("classified as Dual eligible regardless of the effective payer code.")
    md_lines.append("")
    md_lines.append("### Column Definitions")
    md_lines.append("")
    md_lines.append("**Primary Insurance:** Mode (most frequent) payer category across all of a")
    md_lines.append("patient's encounters with valid effective payer.")
    md_lines.append("")
    md_lines.append("**First/Last {Treatment}:** Mode payer category among encounters within")
    md_lines.append("\u00b130 days of the first/last treatment date. Uses ADMIT_DATE from the")
    md_lines.append("ENCOUNTER table. If multiple encounters fall in the window, the most")
    md_lines.append("frequent payer category is selected.")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("**Source:** encounter_payer_summary.parquet")
    md_lines.append("(built by `src/report/encounter_payer_summary.py`)")
    md_lines.append("")
    md_lines.append("**Note:** No HIPAA suppression applied. These are internal working tables.")

    readme_path = reports_dir / "README.md"
    readme_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"    README.md")

    print("\nDone.")


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(config_path)
