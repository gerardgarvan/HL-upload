"""Build insurance enrollment comparison tables (Phase 8).

Compares insurance coverage patterns between patients whose ENROLLMENT periods
fully cover the ±30 day treatment window vs those whose enrollment doesn't.

Reads:
- derived/encounter_payer_summary.parquet (treatment dates, payer categories)
- cleaned/ENROLLMENT*.parquet (ENR_START_DATE, ENR_END_DATE per patient)
- cleaned/ENCOUNTER*.parquet (for Unknown post-treatment diagnostic breakdown)

Produces:
- reports/insurance_enr_comparison/dx_enr_comparison.csv/.png/.html
- reports/insurance_enr_comparison/chemo_enr_comparison.csv/.png/.html
- reports/insurance_enr_comparison/radiation_enr_comparison.csv/.png/.html
- reports/insurance_enr_comparison/sct_enr_comparison.csv/.png/.html
- reports/insurance_enr_comparison/unknown_post_tx_encounter_breakdown.csv/.png/.html
- reports/insurance_enr_comparison/README.md

Each comparison table shows side-by-side columns for "ENR Covers Window" vs
"ENR Does Not Cover" with N (%) for each payer category. DX table has 2 data
columns, treatment tables (chemo/radiation/SCT) have 4 data columns (first + last).

Unknown breakdown table shows encounter count distribution for patients with
"Unknown" post-treatment payer.

No HIPAA small-cell suppression applied - shows all counts as-is for internal use.

Usage:
    python scripts/build_insurance_enr_comparison.py [config/paths.toml]
"""

import sys
from pathlib import Path
from datetime import date, timedelta, datetime
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

# Standard payer category order (9 categories) - same as Phase 5/6
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
    # Use seaborn Pastel1 palette for payer categories (same as Phase 5/6)
    _palette = sns.color_palette("Pastel1", n_colors=9)
    PAYER_COLORS = {
        category: matplotlib.colors.to_hex(color)
        for category, color in zip(PAYER_CATEGORY_ORDER, _palette)
    }
    # Add gray for N/A row (distinct from 9 payer colors)
    PAYER_COLORS["N/A"] = "#D3D3D3"
    HEADER_COLOR = "#2C5AA0"  # Dark blue for headers (same as Phase 5/6)
else:
    PAYER_COLORS = {}
    HEADER_COLOR = "#2C5AA0"

# Treatment window definition (D-01: ±30 days matching PAYER_AT_TREATMENT_WINDOW_DAYS)
WINDOW_DAYS = 30

# Encounter count bins for Unknown breakdown (D-17)
ENCOUNTER_COUNT_BINS = ["0", "1-5", "6-10", "11-20", "21+"]


def _check_enrollment_covers_window(
    patient_id: str,
    window_start: date,
    window_end: date,
    enrollment_df: pl.DataFrame,
) -> bool:
    """Check if union of enrollment periods fully covers [window_start, window_end].

    Returns True if every day in [window_start, window_end] is covered by at least
    one enrollment period. Adjacent/overlapping periods combine to cover gaps.

    Algorithm (D-04, D-05):
    1. Filter to patient's enrollment periods
    2. Sort by ENR_START_DATE
    3. Walk through sorted periods, tracking latest covered date
    4. If any gap exists before window_end, return False
    5. If latest covered date >= window_end, return True

    Args:
        patient_id: Patient ID to check
        window_start: Start date of window (treatment_date - 30 days)
        window_end: End date of window (treatment_date + 30 days)
        enrollment_df: ENROLLMENT DataFrame with ID, ENR_START_DATE, ENR_END_DATE

    Returns:
        True if union of enrollment periods fully covers window, False otherwise
    """
    patient_enr = enrollment_df.filter(pl.col("ID") == patient_id).sort("ENR_START_DATE")

    if patient_enr.is_empty():
        return False  # D-06: No enrollment records

    # Start tracking coverage from before the window
    covered_until = window_start - timedelta(days=1)

    for row in patient_enr.iter_rows(named=True):
        start = row["ENR_START_DATE"]
        end = row["ENR_END_DATE"]

        if start is None or end is None:
            continue  # Skip periods with null dates

        # If this period starts after our coverage gap, window has uncovered days
        if start > covered_until + timedelta(days=1):
            return False  # Gap detected

        # Extend coverage to this period's end date
        covered_until = max(covered_until, end)

        # If we've covered past window_end, we're done
        if covered_until >= window_end:
            return True

    # After all periods, check if we covered the full window
    return covered_until >= window_end


def _flag_enrollment_coverage(
    patients_df: pl.DataFrame,
    enrollment_df: pl.DataFrame,
    date_col: str,
    window_days: int = 30,
) -> pl.DataFrame:
    """Add ENR_COVERS_WINDOW column (1/0) for each patient.

    For each patient, compute window_start = date_col - 30 days, window_end = date_col + 30 days.
    Call _check_enrollment_covers_window to determine if enrollment covers window.

    Args:
        patients_df: DataFrame with ID and date_col columns
        enrollment_df: ENROLLMENT DataFrame with ID, ENR_START_DATE, ENR_END_DATE
        date_col: Column name with treatment date
        window_days: Window size in days (default: 30)

    Returns:
        DataFrame with ID, date_col, ENR_COVERS_WINDOW (Int8: 1/0) columns
    """
    results = []

    for row in patients_df.iter_rows(named=True):
        patient_id = row["ID"]
        treatment_date = row[date_col]

        if treatment_date is None:
            # Shouldn't happen if caller filtered nulls, but handle gracefully
            results.append({
                "ID": patient_id,
                date_col: treatment_date,
                "ENR_COVERS_WINDOW": 0,
            })
            continue

        window_start = treatment_date - timedelta(days=window_days)
        window_end = treatment_date + timedelta(days=window_days)

        covers = _check_enrollment_covers_window(
            patient_id, window_start, window_end, enrollment_df
        )

        results.append({
            "ID": patient_id,
            date_col: treatment_date,
            "ENR_COVERS_WINDOW": 1 if covers else 0,
        })

    return pl.DataFrame(results)


def _normalize_payer_with_na(col: pl.Expr) -> pl.Expr:
    """Normalize payer values with N/A for nulls (D-11).

    Null -> "N/A" (NOT "Unknown" — distinguishes null payer from Unknown category)
    "No payment / Self-pay" -> "Self-pay"
    Otherwise keep as-is

    Args:
        col: Polars expression with payer category values

    Returns:
        Normalized expression with N/A for nulls
    """
    return (
        pl.when(col.is_null())
        .then(pl.lit("N/A"))
        .when(col == "No payment / Self-pay")
        .then(pl.lit("Self-pay"))
        .otherwise(col)
    )


def _build_comparison_table(
    df: pl.DataFrame,
    payer_col: str,
    enr_flag_col: str,
) -> tuple[list[dict], int, int]:
    """Build side-by-side comparison table with ENR coverage split.

    Split df by enr_flag_col == 1 (covered) vs == 0 (not covered).
    Count payer categories in each group.
    Build rows for each of PAYER_CATEGORY_ORDER + ["N/A"].

    Args:
        df: DataFrame with payer_col and enr_flag_col columns
        payer_col: Column name with payer category (e.g., "PAYER_CATEGORY_AT_FIRST_CHEMO")
        enr_flag_col: Column name with enrollment coverage flag (1/0)

    Returns:
        Tuple of (list of row dicts, n_covered, n_not_covered)
    """
    df_covered = df.filter(pl.col(enr_flag_col) == 1)
    df_not_covered = df.filter(pl.col(enr_flag_col) == 0)

    n_covered = df_covered.height
    n_not_covered = df_not_covered.height

    # Count payer categories in each group
    def _count_payers(subset_df):
        # Normalize payer column
        normalized = subset_df.with_columns(
            _normalize_payer_with_na(pl.col(payer_col)).alias("_payer_norm")
        )
        counts = normalized.group_by("_payer_norm").agg(pl.len().alias("N"))
        return {row["_payer_norm"]: row["N"] for row in counts.iter_rows(named=True)}

    covered_map = _count_payers(df_covered)
    not_covered_map = _count_payers(df_not_covered)

    # Build rows with both columns
    rows = []
    payer_order = PAYER_CATEGORY_ORDER + ["N/A"]  # Add N/A per D-11

    for cat in payer_order:
        n_cov = covered_map.get(cat, 0)
        n_not = not_covered_map.get(cat, 0)

        pct_cov = 100.0 * n_cov / n_covered if n_covered > 0 else 0.0
        pct_not = 100.0 * n_not / n_not_covered if n_not_covered > 0 else 0.0

        rows.append({
            "Payer Category": cat,
            "ENR Covers Window (N)": n_cov,
            "ENR Covers Window (%)": pct_cov,
            "ENR Covers Window (N_Pct)": f"{n_cov} ({pct_cov:.1f}%)",
            "ENR Does Not Cover (N)": n_not,
            "ENR Does Not Cover (%)": pct_not,
            "ENR Does Not Cover (N_Pct)": f"{n_not} ({pct_not:.1f}%)",
        })

    return rows, n_covered, n_not_covered


def _build_unknown_encounter_breakdown(
    enc_payer_summary: pl.DataFrame,
    enc_path: Path,
) -> tuple[list[dict], int]:
    """Build diagnostic table: Unknown post-tx payer patients grouped by encounter count.

    Returns list of row dicts:
        {"Encounter Count Bin": "0", "N Patients (N)": 50, "N Patients (%)": 25.0, ...}

    Args:
        enc_payer_summary: encounter_payer_summary DataFrame with POST_TREATMENT_PAYER column
        enc_path: Path to ENCOUNTER parquet file

    Returns:
        Tuple of (list of row dicts, n_unknown_total)
    """
    # Filter to patients with Unknown post-treatment payer
    if "POST_TREATMENT_PAYER" not in enc_payer_summary.columns:
        # Recompute post-treatment payer (same logic as Phase 6)
        enc_payer_summary = _compute_post_treatment_payer(enc_payer_summary, enc_path)

    unknown_patients = enc_payer_summary.filter(
        pl.col("POST_TREATMENT_PAYER") == "Unknown"
    )

    n_unknown = unknown_patients.height

    if n_unknown == 0:
        return [{
            "Encounter Count Bin": "N/A",
            "N Patients (N)": 0,
            "N Patients (%)": 0.0,
            "N Patients (N_Pct)": "0 (0.0%)",
        }], 0

    # Compute LAST_TREATMENT_DATE (max of LAST_CHEMO/RADIATION/SCT)
    unknown_patients = unknown_patients.with_columns(
        pl.max_horizontal("LAST_CHEMO_DATE", "LAST_RADIATION_DATE", "LAST_SCT_DATE")
        .alias("LAST_TREATMENT_DATE")
    )

    # Read encounters and count post-treatment encounters per patient
    enc = pl.read_parquet(enc_path)

    # Filter encounters to Unknown patients
    enc_filtered = enc.filter(
        pl.col("ID").is_in(unknown_patients["ID"])
    )

    # Join to get LAST_TREATMENT_DATE
    joined = unknown_patients.select("ID", "LAST_TREATMENT_DATE").join(
        enc_filtered.select("ID", "ADMIT_DATE"), on="ID", how="left"
    )

    # Filter to post-treatment encounters
    post_tx_enc = joined.filter(
        pl.col("ADMIT_DATE") > pl.col("LAST_TREATMENT_DATE")
    )

    # Count encounters per patient
    enc_counts = post_tx_enc.group_by("ID").agg(
        pl.len().alias("N_POST_TX_ENCOUNTERS")
    )

    # Merge back to unknown_patients, fill nulls with 0 (no encounters)
    unknown_with_counts = unknown_patients.join(
        enc_counts, on="ID", how="left"
    ).with_columns(
        pl.col("N_POST_TX_ENCOUNTERS").fill_null(0)
    )

    # Bin encounter counts (0, 1-5, 6-10, 11-20, 21+)
    unknown_with_counts = unknown_with_counts.with_columns(
        pl.when(pl.col("N_POST_TX_ENCOUNTERS") == 0).then(pl.lit("0"))
        .when(pl.col("N_POST_TX_ENCOUNTERS") <= 5).then(pl.lit("1-5"))
        .when(pl.col("N_POST_TX_ENCOUNTERS") <= 10).then(pl.lit("6-10"))
        .when(pl.col("N_POST_TX_ENCOUNTERS") <= 20).then(pl.lit("11-20"))
        .otherwise(pl.lit("21+"))
        .alias("_bin")
    )

    # Count patients per bin
    bin_counts = unknown_with_counts.group_by("_bin").agg(
        pl.len().alias("N_Patients")
    )

    # Build rows with percentages
    rows = []
    bin_map = {row["_bin"]: row["N_Patients"] for row in bin_counts.iter_rows(named=True)}

    for bin_label in ENCOUNTER_COUNT_BINS:
        n = bin_map.get(bin_label, 0)
        pct = 100.0 * n / n_unknown if n_unknown > 0 else 0.0
        rows.append({
            "Encounter Count Bin": bin_label,
            "N Patients (N)": n,
            "N Patients (%)": pct,
            "N Patients (N_Pct)": f"{n} ({pct:.1f}%)",
        })

    return rows, n_unknown


def _compute_post_treatment_payer(
    enc_payer_summary: pl.DataFrame,
    enc_path: Path,
) -> pl.DataFrame:
    """Compute post-treatment payer (same logic as Phase 6).

    Adds POST_TREATMENT_PAYER column to enc_payer_summary.

    Args:
        enc_payer_summary: encounter_payer_summary DataFrame
        enc_path: Path to ENCOUNTER parquet file

    Returns:
        DataFrame with POST_TREATMENT_PAYER column added
    """
    # Compute LAST_TREATMENT_DATE (max of LAST_CHEMO/RADIATION/SCT)
    enc_payer_summary = enc_payer_summary.with_columns(
        pl.max_horizontal("LAST_CHEMO_DATE", "LAST_RADIATION_DATE", "LAST_SCT_DATE")
        .alias("LAST_TREATMENT_DATE")
    )

    # Read encounters
    enc = pl.read_parquet(enc_path)

    # Filter to patients in enc_payer_summary
    enc_filtered = enc.filter(
        pl.col("ID").is_in(enc_payer_summary["ID"])
    )

    # Join to get LAST_TREATMENT_DATE
    joined = enc_payer_summary.select("ID", "LAST_TREATMENT_DATE").join(
        enc_filtered.select("ID", "ADMIT_DATE", "PAYER_TYPE_PRIMARY", "PAYER_TYPE_SECONDARY"),
        on="ID",
        how="left"
    )

    # Filter to post-treatment encounters
    post_tx_enc = joined.filter(
        pl.col("ADMIT_DATE") > pl.col("LAST_TREATMENT_DATE")
    )

    # Compute effective payer and category (same as encounter_payer_summary logic)
    effective_payer_expr, dual_eligible_expr = _effective_payer_and_dual_exprs()

    post_tx_enc = post_tx_enc.with_columns([
        effective_payer_expr.alias("_effective_payer"),
        dual_eligible_expr.alias("_dual_eligible"),
    ])

    # Apply payer category mapping
    post_tx_enc = post_tx_enc.with_columns(
        _payer_category_from_effective_and_dual(
            pl.col("_effective_payer"),
            pl.col("_dual_eligible")
        ).alias("_payer_category")
    )

    # Compute mode payer category per patient (most frequent)
    post_tx_mode = post_tx_enc.group_by("ID").agg(
        pl.col("_payer_category").mode().first().alias("POST_TREATMENT_PAYER")
    )

    # Normalize "No payment / Self-pay" to "Self-pay"
    post_tx_mode = post_tx_mode.with_columns(
        pl.when(pl.col("POST_TREATMENT_PAYER") == "No payment / Self-pay")
        .then(pl.lit("Self-pay"))
        .otherwise(pl.col("POST_TREATMENT_PAYER"))
        .alias("POST_TREATMENT_PAYER")
    )

    # Fill nulls with "Unknown" (no post-treatment encounters)
    post_tx_mode = post_tx_mode.with_columns(
        pl.col("POST_TREATMENT_PAYER").fill_null("Unknown")
    )

    # Join back to enc_payer_summary
    enc_payer_summary = enc_payer_summary.join(
        post_tx_mode, on="ID", how="left"
    ).with_columns(
        pl.col("POST_TREATMENT_PAYER").fill_null("Unknown")
    )

    return enc_payer_summary


def _render_comparison_png(
    table_data: list[dict],
    title: str,
    output_path: Path,
    col_headers: list[str],
    n_pct_keys: list[str],
) -> None:
    """Render side-by-side comparison table as PNG with color-coded payer category rows.

    Args:
        table_data: List of row dicts from _build_comparison_table()
        title: Title text with cohort name and size
        output_path: Path to save PNG file
        col_headers: Column headers (e.g., ["ENR Covers (N=X)", "ENR Gap (N=Y)"])
        n_pct_keys: Keys for N_Pct columns to extract from row dicts
    """
    if not MATPLOTLIB_AVAILABLE:
        print(f"    [SKIPPED] {output_path.name} (matplotlib not available)")
        return

    # Extract data for table rendering
    cellText = []
    cellColours = []

    for row in table_data:
        payer_cat = row["Payer Category"]
        # Extract N_Pct values for each column
        values = [row[key] for key in n_pct_keys]

        cellText.append([payer_cat] + values)

        # All cells in this row get the same payer category color
        row_color = PAYER_COLORS.get(payer_cat, "#FFFFFF")
        cellColours.append([row_color] * (1 + len(n_pct_keys)))

    # Create figure and table (wider figsize for multiple columns)
    n_cols = 1 + len(n_pct_keys)
    figsize = (14, 8) if n_cols <= 3 else (18, 8)
    fig, ax = plt.subplots(figsize=figsize)
    ax.axis('off')

    col_labels = ["Payer Category"] + col_headers

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

    # Font and scaling (same as Phase 5)
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.2, 2.0)

    # Title
    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.95)

    # Save
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def _render_comparison_html(
    table_data: list[dict],
    title: str,
    output_path: Path,
    col_headers: list[str],
    n_pct_keys: list[str],
) -> None:
    """Render side-by-side comparison table as styled HTML file with inline CSS.

    Args:
        table_data: List of row dicts from _build_comparison_table()
        title: Title text with cohort name and size
        output_path: Path to save HTML file
        col_headers: Column headers (e.g., ["ENR Covers (N=X)", "ENR Gap (N=Y)"])
        n_pct_keys: Keys for N_Pct columns to extract from row dicts
    """
    # CSS styles (same as Phase 5, with N/A class added)
    css = """
    <style>
        body {
            font-family: Arial, sans-serif;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 15px;
            color: #333;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            max-width: 1000px;
            background-color: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        th {
            background-color: #2C5AA0;
            color: white;
            font-weight: bold;
            padding: 12px;
            text-align: center;
            border: 1px solid #ddd;
        }
        td {
            padding: 10px;
            text-align: center;
            border: 1px solid #ddd;
        }
        td:first-child {
            text-align: left;
            font-weight: 500;
        }
        .payer-medicare { background-color: #FBB4AE; }
        .payer-medicaid { background-color: #B3CDE3; }
        .payer-dual-eligible { background-color: #CCEBC5; }
        .payer-private { background-color: #DECBE4; }
        .payer-other-government { background-color: #FED9A6; }
        .payer-self-pay { background-color: #FFFFCC; }
        .payer-other { background-color: #E5D8BD; }
        .payer-unavailable { background-color: #FDDAEC; }
        .payer-unknown { background-color: #F2F2F2; }
        .payer-na { background-color: #D3D3D3; }
    </style>
    """

    # Build HTML table
    col_labels = ["Payer Category"] + col_headers
    thead = "<tr>" + "".join(f"<th>{html.escape(col)}</th>" for col in col_labels) + "</tr>"

    tbody_rows = []
    for row in table_data:
        payer_cat = row["Payer Category"]
        # Extract N_Pct values for each column
        values = [row[key] for key in n_pct_keys]

        # CSS class for row color
        css_class = f"payer-{payer_cat.lower().replace(' ', '-')}"

        cells = [f'<td class="{css_class}">{html.escape(payer_cat)}</td>']
        cells += [f'<td class="{css_class}">{html.escape(str(val))}</td>' for val in values]

        tbody_rows.append("<tr>" + "".join(cells) + "</tr>")

    tbody = "\n".join(tbody_rows)

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{html.escape(title)}</title>
    {css}
</head>
<body>
    <div class="title">{html.escape(title)}</div>
    <table>
        <thead>{thead}</thead>
        <tbody>{tbody}</tbody>
    </table>
</body>
</html>
"""

    output_path.write_text(html_content, encoding="utf-8")


def _render_breakdown_png(
    table_data: list[dict],
    title: str,
    output_path: Path,
) -> None:
    """Render Unknown encounter breakdown table as PNG.

    Simple 2-column table (Encounter Count Bin | N Patients).

    Args:
        table_data: List of row dicts from _build_unknown_encounter_breakdown()
        title: Title text
        output_path: Path to save PNG file
    """
    if not MATPLOTLIB_AVAILABLE:
        print(f"    [SKIPPED] {output_path.name} (matplotlib not available)")
        return

    # Extract data for table rendering
    cellText = []
    cellColours = []

    for row in table_data:
        bin_label = row["Encounter Count Bin"]
        n_pct = row["N Patients (N_Pct)"]

        cellText.append([bin_label, n_pct])

        # Light gray alternating rows
        row_color = "#F5F5F5" if len(cellText) % 2 == 0 else "#FFFFFF"
        cellColours.append([row_color, row_color])

    # Create figure and table
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.axis('off')

    col_labels = ["Encounter Count Bin", "N Patients"]

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

    # Left-align first column
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


def _render_breakdown_html(
    table_data: list[dict],
    title: str,
    output_path: Path,
) -> None:
    """Render Unknown encounter breakdown table as styled HTML file.

    Args:
        table_data: List of row dicts from _build_unknown_encounter_breakdown()
        title: Title text
        output_path: Path to save HTML file
    """
    # CSS styles (simpler than comparison tables)
    css = """
    <style>
        body {
            font-family: Arial, sans-serif;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 15px;
            color: #333;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            max-width: 600px;
            background-color: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        th {
            background-color: #2C5AA0;
            color: white;
            font-weight: bold;
            padding: 12px;
            text-align: center;
            border: 1px solid #ddd;
        }
        td {
            padding: 10px;
            text-align: center;
            border: 1px solid #ddd;
        }
        td:first-child {
            text-align: left;
            font-weight: 500;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
    </style>
    """

    # Build HTML table
    col_labels = ["Encounter Count Bin", "N Patients"]
    thead = "<tr>" + "".join(f"<th>{html.escape(col)}</th>" for col in col_labels) + "</tr>"

    tbody_rows = []
    for row in table_data:
        bin_label = row["Encounter Count Bin"]
        n_pct = row["N Patients (N_Pct)"]

        tbody_rows.append(
            f"<tr><td>{html.escape(bin_label)}</td><td>{html.escape(n_pct)}</td></tr>"
        )

    tbody = "\n".join(tbody_rows)

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{html.escape(title)}</title>
    {css}
</head>
<body>
    <div class="title">{html.escape(title)}</div>
    <table>
        <thead>{thead}</thead>
        <tbody>{tbody}</tbody>
    </table>
</body>
</html>
"""

    output_path.write_text(html_content, encoding="utf-8")


def main(config_path=None):
    """Main execution function."""
    print("=" * 70)
    print("Phase 8: Insurance Enrollment Comparison Analysis")
    print("=" * 70)

    # Load config
    paths = load_and_validate_config(config_path)
    derived_dir = paths.derived_dir
    clean_dir = paths.parquet_dir
    report_dir = PROJECT_ROOT / "reports"

    # Create output directory
    output_dir = report_dir / "insurance_enr_comparison"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[1/5] Reading encounter_payer_summary.parquet from {derived_dir}")
    enc_payer_summary_path = derived_dir / "encounter_payer_summary.parquet"
    if not enc_payer_summary_path.exists():
        print(f"ERROR: {enc_payer_summary_path} not found")
        sys.exit(1)

    enc_payer_summary = pl.read_parquet(enc_payer_summary_path)
    print(f"  Loaded {enc_payer_summary.height:,} patients")

    print(f"\n[2/5] Reading ENROLLMENT parquet from {clean_dir}")
    enrollment_files = list(clean_dir.glob("ENROLLMENT*.parquet"))
    if not enrollment_files:
        print(f"ERROR: No ENROLLMENT*.parquet files found in {clean_dir}")
        sys.exit(1)

    enrollment_df = pl.read_parquet(enrollment_files[0])
    print(f"  Loaded {enrollment_df.height:,} enrollment records from {enrollment_files[0].name}")

    print(f"\n[3/5] Reading ENCOUNTER parquet from {clean_dir}")
    encounter_files = list(clean_dir.glob("ENCOUNTER*.parquet"))
    if not encounter_files:
        print(f"ERROR: No ENCOUNTER*.parquet files found in {clean_dir}")
        sys.exit(1)

    enc_path = encounter_files[0]
    print(f"  Found {enc_path.name}")

    # Build treatment window comparison tables
    print(f"\n[4/5] Building enrollment comparison tables")

    # DX table (D-13: all patients with non-null FIRST_HL_DX_DATE)
    print("\n  DX comparison table...")
    dx_cohort = enc_payer_summary.filter(
        pl.col("FIRST_HL_DX_DATE").is_not_null()
    )
    print(f"    Cohort: {dx_cohort.height:,} patients with DX date")

    dx_enr_coverage = _flag_enrollment_coverage(
        dx_cohort.select("ID", "FIRST_HL_DX_DATE"),
        enrollment_df,
        "FIRST_HL_DX_DATE",
        WINDOW_DAYS
    )

    dx_merged = dx_cohort.join(dx_enr_coverage.select("ID", "ENR_COVERS_WINDOW"), on="ID", how="left")
    dx_merged = dx_merged.with_columns(pl.col("ENR_COVERS_WINDOW").fill_null(0))

    dx_rows, dx_n_covered, dx_n_not = _build_comparison_table(
        dx_merged, "PAYER_CATEGORY_AT_FIRST_DX", "ENR_COVERS_WINDOW"
    )

    # Write DX outputs
    dx_df = pl.DataFrame(dx_rows)
    dx_df.write_csv(output_dir / "dx_enr_comparison.csv")
    print(f"    Wrote dx_enr_comparison.csv ({dx_n_covered} covered, {dx_n_not} gap)")

    _render_comparison_png(
        dx_rows,
        f"First Diagnosis Insurance by Enrollment Coverage (N={dx_cohort.height})",
        output_dir / "dx_enr_comparison.png",
        [f"ENR Covers\n±30d Window\n(N={dx_n_covered})", f"ENR Gap\nin Window\n(N={dx_n_not})"],
        ["ENR Covers Window (N_Pct)", "ENR Does Not Cover (N_Pct)"]
    )
    print(f"    Wrote dx_enr_comparison.png")

    _render_comparison_html(
        dx_rows,
        f"First Diagnosis Insurance by Enrollment Coverage (N={dx_cohort.height})",
        output_dir / "dx_enr_comparison.html",
        [f"ENR Covers ±30d Window (N={dx_n_covered})", f"ENR Gap in Window (N={dx_n_not})"],
        ["ENR Covers Window (N_Pct)", "ENR Does Not Cover (N_Pct)"]
    )
    print(f"    Wrote dx_enr_comparison.html")

    # Chemo table (D-14: HAD_CHEMO=1 and non-null dates, 4 columns: first covers/gap + last covers/gap)
    print("\n  Chemo comparison table...")
    chemo_cohort = enc_payer_summary.filter(
        (pl.col("HAD_CHEMO") == 1) &
        pl.col("FIRST_CHEMO_DATE").is_not_null() &
        pl.col("LAST_CHEMO_DATE").is_not_null()
    )
    print(f"    Cohort: {chemo_cohort.height:,} patients with chemo dates")

    chemo_first_enr = _flag_enrollment_coverage(
        chemo_cohort.select("ID", "FIRST_CHEMO_DATE"),
        enrollment_df,
        "FIRST_CHEMO_DATE",
        WINDOW_DAYS
    ).rename({"ENR_COVERS_WINDOW": "ENR_COVERS_FIRST"})

    chemo_last_enr = _flag_enrollment_coverage(
        chemo_cohort.select("ID", "LAST_CHEMO_DATE"),
        enrollment_df,
        "LAST_CHEMO_DATE",
        WINDOW_DAYS
    ).rename({"ENR_COVERS_WINDOW": "ENR_COVERS_LAST"})

    chemo_merged = chemo_cohort.join(chemo_first_enr.select("ID", "ENR_COVERS_FIRST"), on="ID", how="left")
    chemo_merged = chemo_merged.join(chemo_last_enr.select("ID", "ENR_COVERS_LAST"), on="ID", how="left")
    chemo_merged = chemo_merged.with_columns([
        pl.col("ENR_COVERS_FIRST").fill_null(0),
        pl.col("ENR_COVERS_LAST").fill_null(0),
    ])

    # Build 4-column table
    chemo_first_rows, chemo_first_cov, chemo_first_gap = _build_comparison_table(
        chemo_merged, "PAYER_CATEGORY_AT_FIRST_CHEMO", "ENR_COVERS_FIRST"
    )
    chemo_last_rows, chemo_last_cov, chemo_last_gap = _build_comparison_table(
        chemo_merged, "PAYER_CATEGORY_AT_LAST_CHEMO", "ENR_COVERS_LAST"
    )

    # Combine into single table with 4 data columns
    chemo_combined_rows = []
    for i, cat in enumerate(PAYER_CATEGORY_ORDER + ["N/A"]):
        first_row = chemo_first_rows[i]
        last_row = chemo_last_rows[i]

        chemo_combined_rows.append({
            "Payer Category": cat,
            "First Chemo ENR Covers (N)": first_row["ENR Covers Window (N)"],
            "First Chemo ENR Covers (%)": first_row["ENR Covers Window (%)"],
            "First Chemo ENR Covers (N_Pct)": first_row["ENR Covers Window (N_Pct)"],
            "First Chemo ENR Gap (N)": first_row["ENR Does Not Cover (N)"],
            "First Chemo ENR Gap (%)": first_row["ENR Does Not Cover (%)"],
            "First Chemo ENR Gap (N_Pct)": first_row["ENR Does Not Cover (N_Pct)"],
            "Last Chemo ENR Covers (N)": last_row["ENR Covers Window (N)"],
            "Last Chemo ENR Covers (%)": last_row["ENR Covers Window (%)"],
            "Last Chemo ENR Covers (N_Pct)": last_row["ENR Covers Window (N_Pct)"],
            "Last Chemo ENR Gap (N)": last_row["ENR Does Not Cover (N)"],
            "Last Chemo ENR Gap (%)": last_row["ENR Does Not Cover (%)"],
            "Last Chemo ENR Gap (N_Pct)": last_row["ENR Does Not Cover (N_Pct)"],
        })

    # Write Chemo outputs
    chemo_df = pl.DataFrame(chemo_combined_rows)
    chemo_df.write_csv(output_dir / "chemo_enr_comparison.csv")
    print(f"    Wrote chemo_enr_comparison.csv")

    _render_comparison_png(
        chemo_combined_rows,
        f"Chemotherapy Insurance by Enrollment Coverage (N={chemo_cohort.height})",
        output_dir / "chemo_enr_comparison.png",
        [
            f"First Chemo\nENR Covers\n(N={chemo_first_cov})",
            f"First Chemo\nENR Gap\n(N={chemo_first_gap})",
            f"Last Chemo\nENR Covers\n(N={chemo_last_cov})",
            f"Last Chemo\nENR Gap\n(N={chemo_last_gap})"
        ],
        [
            "First Chemo ENR Covers (N_Pct)",
            "First Chemo ENR Gap (N_Pct)",
            "Last Chemo ENR Covers (N_Pct)",
            "Last Chemo ENR Gap (N_Pct)"
        ]
    )
    print(f"    Wrote chemo_enr_comparison.png")

    _render_comparison_html(
        chemo_combined_rows,
        f"Chemotherapy Insurance by Enrollment Coverage (N={chemo_cohort.height})",
        output_dir / "chemo_enr_comparison.html",
        [
            f"First Chemo ENR Covers (N={chemo_first_cov})",
            f"First Chemo ENR Gap (N={chemo_first_gap})",
            f"Last Chemo ENR Covers (N={chemo_last_cov})",
            f"Last Chemo ENR Gap (N={chemo_last_gap})"
        ],
        [
            "First Chemo ENR Covers (N_Pct)",
            "First Chemo ENR Gap (N_Pct)",
            "Last Chemo ENR Covers (N_Pct)",
            "Last Chemo ENR Gap (N_Pct)"
        ]
    )
    print(f"    Wrote chemo_enr_comparison.html")

    # Radiation table (same pattern as chemo)
    print("\n  Radiation comparison table...")
    radiation_cohort = enc_payer_summary.filter(
        (pl.col("HAD_RADIATION") == 1) &
        pl.col("FIRST_RADIATION_DATE").is_not_null() &
        pl.col("LAST_RADIATION_DATE").is_not_null()
    )
    print(f"    Cohort: {radiation_cohort.height:,} patients with radiation dates")

    radiation_first_enr = _flag_enrollment_coverage(
        radiation_cohort.select("ID", "FIRST_RADIATION_DATE"),
        enrollment_df,
        "FIRST_RADIATION_DATE",
        WINDOW_DAYS
    ).rename({"ENR_COVERS_WINDOW": "ENR_COVERS_FIRST"})

    radiation_last_enr = _flag_enrollment_coverage(
        radiation_cohort.select("ID", "LAST_RADIATION_DATE"),
        enrollment_df,
        "LAST_RADIATION_DATE",
        WINDOW_DAYS
    ).rename({"ENR_COVERS_WINDOW": "ENR_COVERS_LAST"})

    radiation_merged = radiation_cohort.join(radiation_first_enr.select("ID", "ENR_COVERS_FIRST"), on="ID", how="left")
    radiation_merged = radiation_merged.join(radiation_last_enr.select("ID", "ENR_COVERS_LAST"), on="ID", how="left")
    radiation_merged = radiation_merged.with_columns([
        pl.col("ENR_COVERS_FIRST").fill_null(0),
        pl.col("ENR_COVERS_LAST").fill_null(0),
    ])

    radiation_first_rows, radiation_first_cov, radiation_first_gap = _build_comparison_table(
        radiation_merged, "PAYER_CATEGORY_AT_FIRST_RADIATION", "ENR_COVERS_FIRST"
    )
    radiation_last_rows, radiation_last_cov, radiation_last_gap = _build_comparison_table(
        radiation_merged, "PAYER_CATEGORY_AT_LAST_RADIATION", "ENR_COVERS_LAST"
    )

    radiation_combined_rows = []
    for i, cat in enumerate(PAYER_CATEGORY_ORDER + ["N/A"]):
        first_row = radiation_first_rows[i]
        last_row = radiation_last_rows[i]

        radiation_combined_rows.append({
            "Payer Category": cat,
            "First Radiation ENR Covers (N)": first_row["ENR Covers Window (N)"],
            "First Radiation ENR Covers (%)": first_row["ENR Covers Window (%)"],
            "First Radiation ENR Covers (N_Pct)": first_row["ENR Covers Window (N_Pct)"],
            "First Radiation ENR Gap (N)": first_row["ENR Does Not Cover (N)"],
            "First Radiation ENR Gap (%)": first_row["ENR Does Not Cover (%)"],
            "First Radiation ENR Gap (N_Pct)": first_row["ENR Does Not Cover (N_Pct)"],
            "Last Radiation ENR Covers (N)": last_row["ENR Covers Window (N)"],
            "Last Radiation ENR Covers (%)": last_row["ENR Covers Window (%)"],
            "Last Radiation ENR Covers (N_Pct)": last_row["ENR Covers Window (N_Pct)"],
            "Last Radiation ENR Gap (N)": last_row["ENR Does Not Cover (N)"],
            "Last Radiation ENR Gap (%)": last_row["ENR Does Not Cover (%)"],
            "Last Radiation ENR Gap (N_Pct)": last_row["ENR Does Not Cover (N_Pct)"],
        })

    radiation_df = pl.DataFrame(radiation_combined_rows)
    radiation_df.write_csv(output_dir / "radiation_enr_comparison.csv")
    print(f"    Wrote radiation_enr_comparison.csv")

    _render_comparison_png(
        radiation_combined_rows,
        f"Radiation Insurance by Enrollment Coverage (N={radiation_cohort.height})",
        output_dir / "radiation_enr_comparison.png",
        [
            f"First Radiation\nENR Covers\n(N={radiation_first_cov})",
            f"First Radiation\nENR Gap\n(N={radiation_first_gap})",
            f"Last Radiation\nENR Covers\n(N={radiation_last_cov})",
            f"Last Radiation\nENR Gap\n(N={radiation_last_gap})"
        ],
        [
            "First Radiation ENR Covers (N_Pct)",
            "First Radiation ENR Gap (N_Pct)",
            "Last Radiation ENR Covers (N_Pct)",
            "Last Radiation ENR Gap (N_Pct)"
        ]
    )
    print(f"    Wrote radiation_enr_comparison.png")

    _render_comparison_html(
        radiation_combined_rows,
        f"Radiation Insurance by Enrollment Coverage (N={radiation_cohort.height})",
        output_dir / "radiation_enr_comparison.html",
        [
            f"First Radiation ENR Covers (N={radiation_first_cov})",
            f"First Radiation ENR Gap (N={radiation_first_gap})",
            f"Last Radiation ENR Covers (N={radiation_last_cov})",
            f"Last Radiation ENR Gap (N={radiation_last_gap})"
        ],
        [
            "First Radiation ENR Covers (N_Pct)",
            "First Radiation ENR Gap (N_Pct)",
            "Last Radiation ENR Covers (N_Pct)",
            "Last Radiation ENR Gap (N_Pct)"
        ]
    )
    print(f"    Wrote radiation_enr_comparison.html")

    # SCT table (same pattern)
    print("\n  SCT comparison table...")
    sct_cohort = enc_payer_summary.filter(
        (pl.col("HAD_SCT") == 1) &
        pl.col("FIRST_SCT_DATE").is_not_null() &
        pl.col("LAST_SCT_DATE").is_not_null()
    )
    print(f"    Cohort: {sct_cohort.height:,} patients with SCT dates")

    sct_first_enr = _flag_enrollment_coverage(
        sct_cohort.select("ID", "FIRST_SCT_DATE"),
        enrollment_df,
        "FIRST_SCT_DATE",
        WINDOW_DAYS
    ).rename({"ENR_COVERS_WINDOW": "ENR_COVERS_FIRST"})

    sct_last_enr = _flag_enrollment_coverage(
        sct_cohort.select("ID", "LAST_SCT_DATE"),
        enrollment_df,
        "LAST_SCT_DATE",
        WINDOW_DAYS
    ).rename({"ENR_COVERS_WINDOW": "ENR_COVERS_LAST"})

    sct_merged = sct_cohort.join(sct_first_enr.select("ID", "ENR_COVERS_FIRST"), on="ID", how="left")
    sct_merged = sct_merged.join(sct_last_enr.select("ID", "ENR_COVERS_LAST"), on="ID", how="left")
    sct_merged = sct_merged.with_columns([
        pl.col("ENR_COVERS_FIRST").fill_null(0),
        pl.col("ENR_COVERS_LAST").fill_null(0),
    ])

    sct_first_rows, sct_first_cov, sct_first_gap = _build_comparison_table(
        sct_merged, "PAYER_CATEGORY_AT_FIRST_SCT", "ENR_COVERS_FIRST"
    )
    sct_last_rows, sct_last_cov, sct_last_gap = _build_comparison_table(
        sct_merged, "PAYER_CATEGORY_AT_LAST_SCT", "ENR_COVERS_LAST"
    )

    sct_combined_rows = []
    for i, cat in enumerate(PAYER_CATEGORY_ORDER + ["N/A"]):
        first_row = sct_first_rows[i]
        last_row = sct_last_rows[i]

        sct_combined_rows.append({
            "Payer Category": cat,
            "First SCT ENR Covers (N)": first_row["ENR Covers Window (N)"],
            "First SCT ENR Covers (%)": first_row["ENR Covers Window (%)"],
            "First SCT ENR Covers (N_Pct)": first_row["ENR Covers Window (N_Pct)"],
            "First SCT ENR Gap (N)": first_row["ENR Does Not Cover (N)"],
            "First SCT ENR Gap (%)": first_row["ENR Does Not Cover (%)"],
            "First SCT ENR Gap (N_Pct)": first_row["ENR Does Not Cover (N_Pct)"],
            "Last SCT ENR Covers (N)": last_row["ENR Covers Window (N)"],
            "Last SCT ENR Covers (%)": last_row["ENR Covers Window (%)"],
            "Last SCT ENR Covers (N_Pct)": last_row["ENR Covers Window (N_Pct)"],
            "Last SCT ENR Gap (N)": last_row["ENR Does Not Cover (N)"],
            "Last SCT ENR Gap (%)": last_row["ENR Does Not Cover (%)"],
            "Last SCT ENR Gap (N_Pct)": last_row["ENR Does Not Cover (N_Pct)"],
        })

    sct_df = pl.DataFrame(sct_combined_rows)
    sct_df.write_csv(output_dir / "sct_enr_comparison.csv")
    print(f"    Wrote sct_enr_comparison.csv")

    _render_comparison_png(
        sct_combined_rows,
        f"SCT Insurance by Enrollment Coverage (N={sct_cohort.height})",
        output_dir / "sct_enr_comparison.png",
        [
            f"First SCT\nENR Covers\n(N={sct_first_cov})",
            f"First SCT\nENR Gap\n(N={sct_first_gap})",
            f"Last SCT\nENR Covers\n(N={sct_last_cov})",
            f"Last SCT\nENR Gap\n(N={sct_last_gap})"
        ],
        [
            "First SCT ENR Covers (N_Pct)",
            "First SCT ENR Gap (N_Pct)",
            "Last SCT ENR Covers (N_Pct)",
            "Last SCT ENR Gap (N_Pct)"
        ]
    )
    print(f"    Wrote sct_enr_comparison.png")

    _render_comparison_html(
        sct_combined_rows,
        f"SCT Insurance by Enrollment Coverage (N={sct_cohort.height})",
        output_dir / "sct_enr_comparison.html",
        [
            f"First SCT ENR Covers (N={sct_first_cov})",
            f"First SCT ENR Gap (N={sct_first_gap})",
            f"Last SCT ENR Covers (N={sct_last_cov})",
            f"Last SCT ENR Gap (N={sct_last_gap})"
        ],
        [
            "First SCT ENR Covers (N_Pct)",
            "First SCT ENR Gap (N_Pct)",
            "Last SCT ENR Covers (N_Pct)",
            "Last SCT ENR Gap (N_Pct)"
        ]
    )
    print(f"    Wrote sct_enr_comparison.html")

    # Unknown post-treatment encounter breakdown
    print("\n  Unknown post-treatment encounter breakdown...")
    unknown_rows, n_unknown = _build_unknown_encounter_breakdown(enc_payer_summary, enc_path)

    unknown_df = pl.DataFrame(unknown_rows)
    unknown_df.write_csv(output_dir / "unknown_post_tx_encounter_breakdown.csv")
    print(f"    Wrote unknown_post_tx_encounter_breakdown.csv ({n_unknown} Unknown patients)")

    _render_breakdown_png(
        unknown_rows,
        f"Unknown Post-Treatment Payer: Encounter Count Breakdown (N={n_unknown})",
        output_dir / "unknown_post_tx_encounter_breakdown.png"
    )
    print(f"    Wrote unknown_post_tx_encounter_breakdown.png")

    _render_breakdown_html(
        unknown_rows,
        f"Unknown Post-Treatment Payer: Encounter Count Breakdown (N={n_unknown})",
        output_dir / "unknown_post_tx_encounter_breakdown.html"
    )
    print(f"    Wrote unknown_post_tx_encounter_breakdown.html")

    # Write combined markdown README
    print(f"\n[5/5] Writing combined README.md")
    readme_content = f"""# Insurance Coverage by Enrollment — Phase 8 Analysis

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

This analysis compares insurance coverage patterns between patients whose ENROLLMENT periods fully cover the ±30 day treatment window vs those whose enrollment doesn't.

## Tables

### 1. First Diagnosis (N={dx_cohort.height})

| Payer Category | ENR Covers ±30d Window (N={dx_n_covered}) | ENR Gap in Window (N={dx_n_not}) |
|----------------|-------------------------------------------|----------------------------------|
"""
    for row in dx_rows:
        cat = row["Payer Category"]
        cov = row["ENR Covers Window (N_Pct)"]
        gap = row["ENR Does Not Cover (N_Pct)"]
        readme_content += f"| {cat} | {cov} | {gap} |\n"

    readme_content += f"""
### 2. Chemotherapy (N={chemo_cohort.height})

| Payer Category | First Chemo ENR Covers (N={chemo_first_cov}) | First Chemo ENR Gap (N={chemo_first_gap}) | Last Chemo ENR Covers (N={chemo_last_cov}) | Last Chemo ENR Gap (N={chemo_last_gap}) |
|----------------|---------------------------------------------|-------------------------------------------|-------------------------------------------|----------------------------------------|
"""
    for row in chemo_combined_rows:
        cat = row["Payer Category"]
        readme_content += f"| {cat} | {row['First Chemo ENR Covers (N_Pct)']} | {row['First Chemo ENR Gap (N_Pct)']} | {row['Last Chemo ENR Covers (N_Pct)']} | {row['Last Chemo ENR Gap (N_Pct)']} |\n"

    readme_content += f"""
### 3. Radiation (N={radiation_cohort.height})

| Payer Category | First Radiation ENR Covers (N={radiation_first_cov}) | First Radiation ENR Gap (N={radiation_first_gap}) | Last Radiation ENR Covers (N={radiation_last_cov}) | Last Radiation ENR Gap (N={radiation_last_gap}) |
|----------------|-----------------------------------------------------|--------------------------------------------------|--------------------------------------------------|------------------------------------------------|
"""
    for row in radiation_combined_rows:
        cat = row["Payer Category"]
        readme_content += f"| {cat} | {row['First Radiation ENR Covers (N_Pct)']} | {row['First Radiation ENR Gap (N_Pct)']} | {row['Last Radiation ENR Covers (N_Pct)']} | {row['Last Radiation ENR Gap (N_Pct)']} |\n"

    readme_content += f"""
### 4. SCT (N={sct_cohort.height})

| Payer Category | First SCT ENR Covers (N={sct_first_cov}) | First SCT ENR Gap (N={sct_first_gap}) | Last SCT ENR Covers (N={sct_last_cov}) | Last SCT ENR Gap (N={sct_last_gap}) |
|----------------|------------------------------------------|---------------------------------------|----------------------------------------|-------------------------------------|
"""
    for row in sct_combined_rows:
        cat = row["Payer Category"]
        readme_content += f"| {cat} | {row['First SCT ENR Covers (N_Pct)']} | {row['First SCT ENR Gap (N_Pct)']} | {row['Last SCT ENR Covers (N_Pct)']} | {row['Last SCT ENR Gap (N_Pct)']} |\n"

    readme_content += f"""
### 5. Unknown Post-Treatment Payer Diagnostic Breakdown (N={n_unknown})

| Encounter Count Bin | N Patients |
|---------------------|------------|
"""
    for row in unknown_rows:
        readme_content += f"| {row['Encounter Count Bin']} | {row['N Patients (N_Pct)']} |\n"

    readme_content += """
## Interpretation

- **ENR Covers Window**: Patient's union of enrollment periods fully covers [treatment_date - 30 days, treatment_date + 30 days]
- **ENR Gap in Window**: Patient has enrollment gaps within the ±30 day window
- **N/A**: Patient had no payer recorded at treatment date (no encounters in ±30 day window)
- **Unknown**: Patient had encounters but payer category is Unknown

The Unknown breakdown table shows how many post-treatment encounters Unknown-payer patients have, revealing whether Unknown = no data vs encounters with missing payer info.

## Files

- `dx_enr_comparison.csv/.png/.html` - First diagnosis comparison
- `chemo_enr_comparison.csv/.png/.html` - Chemotherapy comparison
- `radiation_enr_comparison.csv/.png/.html` - Radiation comparison
- `sct_enr_comparison.csv/.png/.html` - SCT comparison
- `unknown_post_tx_encounter_breakdown.csv/.png/.html` - Unknown diagnostic breakdown
"""

    (output_dir / "README.md").write_text(readme_content, encoding="utf-8")
    print(f"  Wrote README.md")

    print("\n" + "=" * 70)
    print("Phase 8 Analysis Complete!")
    print("=" * 70)
    print(f"\nOutputs written to: {output_dir}")
    print(f"\n  - 4 comparison tables (DX, Chemo, Radiation, SCT)")
    print(f"  - 1 diagnostic breakdown (Unknown post-treatment)")
    print(f"  - Each table in CSV, PNG, HTML formats")
    print(f"  - Combined README.md with all tables")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    main(config_path)
