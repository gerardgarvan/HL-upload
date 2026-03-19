"""Build post-treatment insurance summary tables (Phase 6).

Reads derived/encounter_payer_summary.parquet and clean/ENCOUNTER.parquet, produces:
- reports/post_treatment_insurance/combined_post_treatment.csv
- reports/post_treatment_insurance/chemo_post_treatment.csv
- reports/post_treatment_insurance/radiation_post_treatment.csv
- reports/post_treatment_insurance/sct_post_treatment.csv
- reports/post_treatment_insurance/README.md (combined markdown with all tables)

Each table shows post-treatment payer (mode category from encounters after last
treatment date) with N (%) format. Combined table has 10 rows (9 payer + N/A for
no-treatment patients), cohort tables have 9 rows. No HIPAA suppression applied.

Last treatment date = max(LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE),
nulls ignored. Post-treatment encounters: ADMIT_DATE > last_treatment_date.

Usage:
    python scripts/build_post_treatment_insurance.py [config/paths.toml]
"""

import sys
from pathlib import Path
from datetime import datetime
import html

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl

from src.load.config import load_and_validate_config
from src.report.encounter_payer_summary import (
    _payer_category_from_effective_and_dual,
    _effective_payer_and_dual_exprs,
)
from src.validate.structural import PATID_COL

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

# Standard payer category order (9 categories) - using "Self-pay" not "No payment / Self-pay"
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
    # Use seaborn Pastel1 palette for payer categories (same as Phase 5)
    _palette = sns.color_palette("Pastel1", n_colors=9)
    PAYER_COLORS = {
        category: matplotlib.colors.to_hex(color)
        for category, color in zip(PAYER_CATEGORY_ORDER, _palette)
    }
    # Add gray for N/A row in combined table (distinct from 9 payer colors)
    PAYER_COLORS["N/A (No Treatment)"] = "#D3D3D3"
    HEADER_COLOR = "#2C5AA0"  # Dark blue for headers (same as Phase 5)
else:
    PAYER_COLORS = {}
    HEADER_COLOR = "#2C5AA0"


def _render_png(table_data: list[dict], title: str, output_path: Path) -> None:
    """Render post-treatment summary table as PNG image with color-coded payer category rows.

    Single-column layout (2 columns total: Payer Category + Post-Treatment Insurance).
    Uses same matplotlib/seaborn patterns as Phase 5 but with narrower figsize.

    Args:
        table_data: List of row dicts from _build_post_treatment_table()
        title: Title text with cohort name and size, e.g., "Post-Treatment: Combined (N=XXX)"
        output_path: Path to save PNG file
    """
    if not MATPLOTLIB_AVAILABLE:
        print(f"    [SKIPPED] {output_path.name} (matplotlib not available)")
        return

    # Extract data for table rendering
    cellText = []
    cellColours = []

    for row in table_data:
        payer_cat = row["Payer Category"]
        # Use N_Pct formatted string for display
        post_treatment = row["Post-Treatment Insurance (N_Pct)"]

        cellText.append([payer_cat, post_treatment])

        # Both cells in this row get the same payer category color
        row_color = PAYER_COLORS.get(payer_cat, "#FFFFFF")
        cellColours.append([row_color, row_color])

    # Create figure and table
    # Single-column layout: figsize (8, 7) instead of Phase 5's (12, 7)
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.axis('off')

    col_labels = ["Payer Category", "Post-Treatment Insurance"]

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


def _render_html(table_data: list[dict], title: str, output_path: Path) -> None:
    """Render post-treatment summary table as styled HTML file with inline CSS.

    Single-column layout (2 columns total: Payer Category + Post-Treatment Insurance).
    Uses same styling patterns as Phase 5 but adapted for single-column tables.

    Args:
        table_data: List of row dicts from _build_post_treatment_table()
        title: Title text with cohort name and size
        output_path: Path to save HTML file
    """
    # Generate CSS classes for payer categories
    css_classes = []
    for category in PAYER_CATEGORY_ORDER:
        class_name = category.lower().replace(" ", "-")
        color = PAYER_COLORS.get(category, "#FFFFFF")
        css_classes.append(f"  .payer-{class_name} {{ background-color: {color}; }}")

    # Add CSS for N/A row (sanitized class name)
    css_classes.append(f"  .payer-na-no-treatment {{ background-color: #D3D3D3; }}")

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
        "        <th>Post-Treatment Insurance</th>",
        "      </tr>",
        "    </thead>",
        "    <tbody>",
    ]

    # Add data rows
    for row in table_data:
        payer_cat = row["Payer Category"]
        # Sanitize class name for N/A row
        if payer_cat == "N/A (No Treatment)":
            class_name = "payer-na-no-treatment"
        else:
            class_name = payer_cat.lower().replace(" ", "-")
        post_treatment = html.escape(row["Post-Treatment Insurance (N_Pct)"])

        html_lines.append(f'      <tr class="{class_name}">')
        html_lines.append(f"        <td>{html.escape(payer_cat)}</td>")
        html_lines.append(f"        <td>{post_treatment}</td>")
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


def _compute_post_treatment_payer(
    enc_payer_summary: pl.DataFrame,
    enc_path: Path,
) -> pl.DataFrame:
    """Compute post-treatment payer as mode category from encounters after last treatment date.

    Computes LAST_TREATMENT_DATE as max(LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE)
    per patient, filters encounters to ADMIT_DATE > LAST_TREATMENT_DATE, and derives mode
    (most frequent) payer category across post-treatment encounters. Patients with no
    post-treatment encounters get POST_TREATMENT_PAYER = "Unknown". Patients with no
    treatment at all (HAD_ANY_TREATMENT=0) get POST_TREATMENT_PAYER = "N/A (No Treatment)".

    Args:
        enc_payer_summary: Patient-level summary with treatment date columns and flags
        enc_path: Path to clean/ENCOUNTER.parquet

    Returns:
        DataFrame with columns: PATID, POST_TREATMENT_PAYER, HAD_CHEMO, HAD_RADIATION,
        HAD_SCT, HAD_ANY_TREATMENT, LAST_TREATMENT_DATE
    """
    # Compute LAST_TREATMENT_DATE (max across all three modalities, nulls ignored)
    patients = enc_payer_summary.with_columns(
        pl.max_horizontal(
            "LAST_CHEMO_DATE",
            "LAST_RADIATION_DATE",
            "LAST_SCT_DATE",
        ).alias("LAST_TREATMENT_DATE")
    )

    # Compute HAD_ANY_TREATMENT flag
    patients = patients.with_columns(
        (
            (pl.col("HAD_CHEMO") == 1)
            | (pl.col("HAD_RADIATION") == 1)
            | (pl.col("HAD_SCT") == 1)
        )
        .cast(pl.Int8)
        .alias("HAD_ANY_TREATMENT")
    )

    # Read encounters with payer columns
    if not enc_path.exists():
        print(f"  [WARNING] {enc_path.name} not found; all patients get Unknown payer")
        return patients.select(
            PATID_COL,
            "HAD_CHEMO",
            "HAD_RADIATION",
            "HAD_SCT",
            "HAD_ANY_TREATMENT",
            "LAST_TREATMENT_DATE",
        ).with_columns(pl.lit("Unknown").alias("POST_TREATMENT_PAYER"))

    enc_schema = pl.read_parquet_schema(enc_path)
    if "PAYER_TYPE_PRIMARY" not in enc_schema.names():
        print(
            f"  [WARNING] PAYER_TYPE_PRIMARY column missing; all patients get Unknown payer"
        )
        return patients.select(
            PATID_COL,
            "HAD_CHEMO",
            "HAD_RADIATION",
            "HAD_SCT",
            "HAD_ANY_TREATMENT",
            "LAST_TREATMENT_DATE",
        ).with_columns(pl.lit("Unknown").alias("POST_TREATMENT_PAYER"))

    has_secondary = "PAYER_TYPE_SECONDARY" in enc_schema.names()
    enc_cols = [PATID_COL, "ADMIT_DATE", "PAYER_TYPE_PRIMARY"]
    if has_secondary:
        enc_cols.append("PAYER_TYPE_SECONDARY")

    # Load encounters with effective payer logic
    eff_expr, valid_expr, dual_expr = _effective_payer_and_dual_exprs(has_secondary)
    enc = (
        pl.scan_parquet(enc_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(patients[PATID_COL].implode()))
        .select(enc_cols)
        .with_columns([eff_expr, valid_expr, dual_expr])
        .select(PATID_COL, "ADMIT_DATE", "effective_payer", "dual_eligible", "_valid")
        .collect()
    )

    if enc.is_empty():
        print("  [WARNING] No encounters found; all patients get Unknown payer")
        return patients.select(
            PATID_COL,
            "HAD_CHEMO",
            "HAD_RADIATION",
            "HAD_SCT",
            "HAD_ANY_TREATMENT",
            "LAST_TREATMENT_DATE",
        ).with_columns(pl.lit("Unknown").alias("POST_TREATMENT_PAYER"))

    # Join encounters to patients, filter to ADMIT_DATE > LAST_TREATMENT_DATE
    patients_with_last_tx = patients.filter(
        pl.col("LAST_TREATMENT_DATE").is_not_null()
    )
    if patients_with_last_tx.is_empty():
        print(
            "  [WARNING] No patients with treatment dates; all get Unknown or N/A payer"
        )
        return patients.select(
            PATID_COL,
            "HAD_CHEMO",
            "HAD_RADIATION",
            "HAD_SCT",
            "HAD_ANY_TREATMENT",
            "LAST_TREATMENT_DATE",
        ).with_columns(
            pl.when(pl.col("HAD_ANY_TREATMENT") == 1)
            .then(pl.lit("Unknown"))
            .otherwise(pl.lit("N/A (No Treatment)"))
            .alias("POST_TREATMENT_PAYER")
        )

    joined = patients_with_last_tx.select(
        PATID_COL, "LAST_TREATMENT_DATE"
    ).join(enc, on=PATID_COL, how="inner")

    # Filter to post-treatment encounters (strict greater-than)
    post_treatment = joined.filter(
        (pl.col("ADMIT_DATE") > pl.col("LAST_TREATMENT_DATE")) & pl.col("_valid")
    )

    print(
        f"  Post-treatment encounters: {post_treatment.height:,} (from {enc.height:,} total)"
    )

    if post_treatment.is_empty():
        # No post-treatment encounters for anyone -> all with treatment get "Unknown"
        return patients.select(
            PATID_COL,
            "HAD_CHEMO",
            "HAD_RADIATION",
            "HAD_SCT",
            "HAD_ANY_TREATMENT",
            "LAST_TREATMENT_DATE",
        ).with_columns(
            pl.when(pl.col("HAD_ANY_TREATMENT") == 1)
            .then(pl.lit("Unknown"))
            .otherwise(pl.lit("N/A (No Treatment)"))
            .alias("POST_TREATMENT_PAYER")
        )

    # Derive payer category from effective_payer and dual_eligible
    post_treatment = post_treatment.with_columns(
        pl.Series(
            "PAYER_CATEGORY",
            [
                _payer_category_from_effective_and_dual(
                    r["effective_payer"], r.get("dual_eligible", 0) or 0
                )
                for r in post_treatment.iter_rows(named=True)
            ],
            dtype=pl.String,
        )
    )

    # Map "No payment / Self-pay" -> "Self-pay" for consistency with Phase 5 label
    post_treatment = post_treatment.with_columns(
        pl.when(pl.col("PAYER_CATEGORY") == "No payment / Self-pay")
        .then(pl.lit("Self-pay"))
        .otherwise(pl.col("PAYER_CATEGORY"))
        .alias("PAYER_CATEGORY")
    )

    # Mode: most frequent payer category per patient
    mode_df = (
        post_treatment.group_by(PATID_COL, "PAYER_CATEGORY")
        .agg(pl.len().alias("_n"))
        .sort("_n", descending=True)
        .group_by(PATID_COL)
        .first()
        .select(PATID_COL, pl.col("PAYER_CATEGORY").alias("POST_TREATMENT_PAYER"))
    )

    # Left join to preserve all patients, fill nulls based on treatment status
    result = patients.select(
        PATID_COL,
        "HAD_CHEMO",
        "HAD_RADIATION",
        "HAD_SCT",
        "HAD_ANY_TREATMENT",
        "LAST_TREATMENT_DATE",
    ).join(mode_df, on=PATID_COL, how="left")

    # Fill nulls: HAD_ANY_TREATMENT=1 -> "Unknown", else "N/A (No Treatment)"
    result = result.with_columns(
        pl.when(pl.col("POST_TREATMENT_PAYER").is_not_null())
        .then(pl.col("POST_TREATMENT_PAYER"))
        .when(pl.col("HAD_ANY_TREATMENT") == 1)
        .then(pl.lit("Unknown"))
        .otherwise(pl.lit("N/A (No Treatment)"))
        .alias("POST_TREATMENT_PAYER")
    )

    return result


def _build_post_treatment_table(
    df: pl.DataFrame,
    col_name: str,
    cohort_label: str,
    include_na_row: bool = False,
) -> tuple[list[dict], int]:
    """Build post-treatment summary table with 9 (or 10 if N/A) payer rows and 1 column.

    Args:
        df: Filtered cohort DataFrame (e.g., HAD_CHEMO==1 or all patients)
        col_name: Column name for post-treatment payer (POST_TREATMENT_PAYER)
        cohort_label: Label for cohort (e.g., "Chemotherapy")
        include_na_row: If True, add N/A row for no-treatment patients (combined table only)

    Returns:
        Tuple of (list of row dicts, cohort size)
    """
    cohort_size = df.height
    if cohort_size == 0:
        # Return empty rows with 0 counts
        rows = []
        for cat in PAYER_CATEGORY_ORDER:
            rows.append(
                {
                    "Payer Category": cat,
                    "Post-Treatment Insurance (N)": 0,
                    "Post-Treatment Insurance (%)": 0.0,
                    "Post-Treatment Insurance (N_Pct)": "0 (0.0%)",
                }
            )
        return rows, cohort_size

    # Normalize nulls to "Unknown"
    df_norm = df.with_columns(
        pl.col(col_name).fill_null("Unknown").alias("_payer_norm")
    )

    # Count by category
    counts = (
        df_norm.group_by("_payer_norm")
        .agg(pl.len().alias("N"))
        .rename({"_payer_norm": "Category"})
    )
    count_map = {row["Category"]: row["N"] for row in counts.iter_rows(named=True)}

    # Build rows in standard order
    rows = []
    for cat in PAYER_CATEGORY_ORDER:
        n = count_map.get(cat, 0)
        pct = 100.0 * n / cohort_size if cohort_size > 0 else 0.0
        rows.append(
            {
                "Payer Category": cat,
                "Post-Treatment Insurance (N)": n,
                "Post-Treatment Insurance (%)": pct,
                "Post-Treatment Insurance (N_Pct)": f"{n} ({pct:.1f}%)",
            }
        )

    # Add N/A row if requested (combined table only)
    if include_na_row:
        n_no_tx = count_map.get("N/A (No Treatment)", 0)
        pct_no_tx = 100.0 * n_no_tx / cohort_size if cohort_size > 0 else 0.0
        rows.append(
            {
                "Payer Category": "N/A (No Treatment)",
                "Post-Treatment Insurance (N)": n_no_tx,
                "Post-Treatment Insurance (%)": pct_no_tx,
                "Post-Treatment Insurance (N_Pct)": f"{n_no_tx} ({pct_no_tx:.1f}%)",
            }
        )

    return rows, cohort_size


def main(config_path: Path | None = None) -> None:
    """Phase 6: Build post-treatment insurance summary tables.

    Generates 4 summary tables (combined, chemo, radiation, SCT) showing post-treatment
    payer distributions. Post-treatment payer = mode category from encounters after
    last treatment date (max of last chemo, radiation, SCT dates). No small-cell
    suppression applied.

    Creates reports/post_treatment_insurance/ directory with CSV files and markdown README.

    Args:
        config_path: Optional path to config/paths.toml (uses default if None)

    Raises:
        SystemExit: Exits with code 0 if parquet missing (not an error)
        SystemExit: Exits with code 1 if ALL treatment date columns are missing
    """
    print("=" * 60)
    print("POST-TREATMENT INSURANCE ANALYSIS — Summary Tables")
    print("=" * 60)

    paths = load_and_validate_config(config_path)
    derived_dir = paths.derived_dir
    clean_dir = paths.clean_dir
    reports_dir = PROJECT_ROOT / "reports" / "post_treatment_insurance"
    reports_dir.mkdir(parents=True, exist_ok=True)

    enc_payer_path = derived_dir / "encounter_payer_summary.parquet"
    if not enc_payer_path.exists():
        print("encounter_payer_summary.parquet missing; skipping.")
        sys.exit(0)

    df = pl.read_parquet(enc_payer_path)
    if df.is_empty():
        print("encounter_payer_summary.parquet is empty; skipping.")
        sys.exit(0)

    print(f"\n  derived_dir: {derived_dir}")
    print(f"  clean_dir: {clean_dir}")
    print(f"  Patients: {df.height:,}")

    # Check required date columns exist
    required_date_cols = ["LAST_CHEMO_DATE", "LAST_RADIATION_DATE", "LAST_SCT_DATE"]
    missing_date_cols = [col for col in required_date_cols if col not in df.columns]
    available_date_cols = [col for col in required_date_cols if col in df.columns]

    if missing_date_cols:
        print(
            f"\n  [WARNING] Missing treatment date columns: {missing_date_cols}"
        )
        print(
            f"            Script will continue with available columns: {available_date_cols}"
        )
        print(f"            Re-run: python scripts/assemble_clean.py")

        # Add missing columns as nulls to allow graceful continuation
        for col in missing_date_cols:
            df = df.with_columns(pl.lit(None).cast(pl.Date).alias(col))

    if not available_date_cols:
        print(
            "\n  [FATAL] ALL treatment date columns are missing. Cannot compute last treatment date."
        )
        print("          Re-run: python scripts/assemble_clean.py")
        sys.exit(1)

    # Check required treatment flag columns exist
    required_flag_cols = ["HAD_CHEMO", "HAD_RADIATION", "HAD_SCT"]
    missing_flag_cols = [col for col in required_flag_cols if col not in df.columns]

    if missing_flag_cols:
        print(
            f"\n  [WARNING] Missing treatment flag columns: {missing_flag_cols}"
        )
        print(f"            Adding as 0 (no treatment). Re-run assemble_clean.py for real values.")
        for col in missing_flag_cols:
            df = df.with_columns(pl.lit(0).cast(pl.Int8).alias(col))

    # Compute post-treatment payer
    enc_path = clean_dir / "ENCOUNTER.parquet"
    print("\n  Computing post-treatment payer...")
    result = _compute_post_treatment_payer(df, enc_path)

    # Summary stats
    n_total = result.height
    n_had_treatment = result.filter(pl.col("HAD_ANY_TREATMENT") == 1).height
    n_no_treatment = result.filter(pl.col("HAD_ANY_TREATMENT") == 0).height
    n_chemo = result.filter(pl.col("HAD_CHEMO") == 1).height
    n_radiation = result.filter(pl.col("HAD_RADIATION") == 1).height
    n_sct = result.filter(pl.col("HAD_SCT") == 1).height

    print(f"\n  Total patients: {n_total:,}")
    print(f"  Patients with any treatment: {n_had_treatment:,}")
    print(f"  Patients with no treatment: {n_no_treatment:,}")
    print(f"  Chemo cohort: {n_chemo:,}")
    print(f"  Radiation cohort: {n_radiation:,}")
    print(f"  SCT cohort: {n_sct:,}")

    # Build tables
    print("\n  Building tables...")
    tables = {}

    # Combined table (all patients, include N/A row)
    combined_rows, combined_size = _build_post_treatment_table(
        result, "POST_TREATMENT_PAYER", "Combined", include_na_row=True
    )
    tables["combined"] = (combined_rows, combined_size)
    print(f"    Combined: N={combined_size:,} (includes N/A row)")

    # Chemo cohort
    df_chemo = result.filter(pl.col("HAD_CHEMO") == 1)
    chemo_rows, chemo_size = _build_post_treatment_table(
        df_chemo, "POST_TREATMENT_PAYER", "Chemotherapy", include_na_row=False
    )
    tables["chemo"] = (chemo_rows, chemo_size)
    print(f"    Chemo: N={chemo_size:,}")

    # Radiation cohort
    df_radiation = result.filter(pl.col("HAD_RADIATION") == 1)
    radiation_rows, radiation_size = _build_post_treatment_table(
        df_radiation, "POST_TREATMENT_PAYER", "Radiation", include_na_row=False
    )
    tables["radiation"] = (radiation_rows, radiation_size)
    print(f"    Radiation: N={radiation_size:,}")

    # SCT cohort
    df_sct = result.filter(pl.col("HAD_SCT") == 1)
    sct_rows, sct_size = _build_post_treatment_table(
        df_sct, "POST_TREATMENT_PAYER", "SCT", include_na_row=False
    )
    tables["sct"] = (sct_rows, sct_size)
    print(f"    SCT: N={sct_size:,}")

    # Write CSV, PNG, and HTML files
    print("\n  Writing output files...")
    output_specs = {
        "combined": {
            "csv": reports_dir / "combined_post_treatment.csv",
            "png": reports_dir / "combined_post_treatment.png",
            "html": reports_dir / "combined_post_treatment.html",
            "title": "Post-Treatment: Combined",
        },
        "chemo": {
            "csv": reports_dir / "chemo_post_treatment.csv",
            "png": reports_dir / "chemo_post_treatment.png",
            "html": reports_dir / "chemo_post_treatment.html",
            "title": "Post-Treatment: Chemotherapy Cohort",
        },
        "radiation": {
            "csv": reports_dir / "radiation_post_treatment.csv",
            "png": reports_dir / "radiation_post_treatment.png",
            "html": reports_dir / "radiation_post_treatment.html",
            "title": "Post-Treatment: Radiation Cohort",
        },
        "sct": {
            "csv": reports_dir / "sct_post_treatment.csv",
            "png": reports_dir / "sct_post_treatment.png",
            "html": reports_dir / "sct_post_treatment.html",
            "title": "Post-Treatment: Stem Cell Transplant (SCT) Cohort",
        },
    }

    for name, paths_and_title in output_specs.items():
        rows, size = tables[name]

        # CSV
        df_table = pl.DataFrame(rows)
        df_table.write_csv(paths_and_title["csv"])
        print(f"    {paths_and_title['csv'].name}")

        # PNG
        png_title = f"{paths_and_title['title']} (N={size:,})"
        _render_png(rows, png_title, paths_and_title["png"])
        if MATPLOTLIB_AVAILABLE:
            print(f"    {paths_and_title['png'].name}")

        # HTML
        _render_html(rows, png_title, paths_and_title["html"])
        print(f"    {paths_and_title['html'].name}")

    # Write combined markdown README
    print("\n  Writing markdown README...")
    md_lines = []
    md_lines.append("# Post-Treatment Insurance Analysis")
    md_lines.append("")
    md_lines.append(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    md_lines.append("")
    md_lines.append(
        "Post-treatment payer = mode payer category from encounters after last treatment date."
    )
    md_lines.append(
        "Last treatment date = max(LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE), nulls ignored."
    )
    md_lines.append("")

    # Add each table
    table_order = ["combined", "chemo", "radiation", "sct"]
    table_labels = {
        "combined": "Post-Treatment: Combined",
        "chemo": "Post-Treatment: Chemotherapy Cohort",
        "radiation": "Post-Treatment: Radiation Cohort",
        "sct": "Post-Treatment: Stem Cell Transplant (SCT) Cohort",
    }

    for name in table_order:
        if name not in tables:
            continue
        rows, size = tables[name]
        label = table_labels[name]

        md_lines.append(f"## {label} (N={size:,})")
        md_lines.append("")
        md_lines.append("| Payer Category | Post-Treatment Insurance |")
        md_lines.append("|----------------|--------------------------|")
        for row in rows:
            md_lines.append(
                f"| {row['Payer Category']} | {row['Post-Treatment Insurance (N_Pct)']} |"
            )
        md_lines.append("")

    # Methodology section
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## Methodology")
    md_lines.append("")
    md_lines.append("### Last Treatment Date Computation")
    md_lines.append("")
    md_lines.append(
        "Last treatment date per patient = max(LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE)."
    )
    md_lines.append(
        "Nulls are ignored — the max is computed across non-null values only."
    )
    md_lines.append(
        "Returns null only if ALL three treatment dates are null (patient had no treatment)."
    )
    md_lines.append("")
    md_lines.append("### Post-Treatment Encounter Filtering")
    md_lines.append("")
    md_lines.append(
        "Post-treatment encounters: ADMIT_DATE > last_treatment_date (strict greater-than)."
    )
    md_lines.append(
        "No minimum threshold — one post-treatment encounter is sufficient."
    )
    md_lines.append("No time cap — all encounters after last treatment date count.")
    md_lines.append("")
    md_lines.append("### Mode Payer Derivation")
    md_lines.append("")
    md_lines.append(
        "Post-treatment payer = most frequent (mode) payer category across post-treatment encounters."
    )
    md_lines.append(
        "Payer category derived from effective payer logic (primary -> secondary fallback) and dual-eligible detection."
    )
    md_lines.append("See Phase 5 insurance_by_treatment README for payer category details.")
    md_lines.append("")
    md_lines.append("### Edge Case Handling")
    md_lines.append("")
    md_lines.append(
        "**Patients with no post-treatment encounters:** POST_TREATMENT_PAYER = 'Unknown'"
    )
    md_lines.append(
        "**Patients with no treatment at all (HAD_CHEMO=0, HAD_RADIATION=0, HAD_SCT=0):** POST_TREATMENT_PAYER = 'N/A (No Treatment)' in combined table only"
    )
    md_lines.append("")
    md_lines.append("### Cohort Definitions")
    md_lines.append("")
    md_lines.append(
        "**Chemo cohort:** HAD_CHEMO=1 (matches Phase 5 definition)"
    )
    md_lines.append(
        "**Radiation cohort:** HAD_RADIATION=1 (matches Phase 5 definition)"
    )
    md_lines.append("**SCT cohort:** HAD_SCT=1 (matches Phase 5 definition)")
    md_lines.append("")
    md_lines.append(
        "Per-cohort post-treatment payer is based on encounters after max(ALL treatment dates), not just that cohort's treatment date."
    )
    md_lines.append(
        "Example: A patient in the chemo cohort gets their post-treatment payer from encounters after max(LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE)."
    )
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("**Source:** encounter_payer_summary.parquet, ENCOUNTER.parquet")
    md_lines.append("(built by `src/report/encounter_payer_summary.py` and cleaning pipeline)")
    md_lines.append("")
    md_lines.append(
        "**Note:** No HIPAA suppression applied. These are internal working tables."
    )

    readme_path = reports_dir / "README.md"
    readme_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"    README.md")

    print("\nDone.")


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(config_path)
