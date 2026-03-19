"""Build combined insurance summary tables per treatment cohort.

Merges Phase 5 (insurance at treatment) and Phase 6 (post-treatment insurance)
into unified 4-column HTML tables for each treatment type.

Reads derived/encounter_payer_summary.parquet and clean/ENCOUNTER.parquet, produces:
- reports/combined_insurance/chemotherapy_insurance_table.html
- reports/combined_insurance/radiation_insurance_table.html
- reports/combined_insurance/sct_insurance_table.html

Each table has 9 payer category rows and 4 columns:
  Primary Insurance | First {Treatment} | Last {Treatment} | Post-Treatment

No HIPAA suppression applied — internal working tables.

Usage:
    python scripts/build_combined_insurance_tables.py [config/paths.toml]
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

# Optional matplotlib imports for color palette
try:
    import matplotlib
    matplotlib.use("Agg")
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

# Color palette for HTML rendering
if MATPLOTLIB_AVAILABLE:
    _palette = sns.color_palette("Pastel1", n_colors=9)
    PAYER_COLORS = {
        category: matplotlib.colors.to_hex(color)
        for category, color in zip(PAYER_CATEGORY_ORDER, _palette)
    }
else:
    # Fallback hex values (seaborn Pastel1)
    PAYER_COLORS = {
        "Medicare": "#FBB4AE",
        "Medicaid": "#B3CDE3",
        "Dual eligible": "#CCEBC5",
        "Private": "#DECBE4",
        "Other government": "#FED9A6",
        "Self-pay": "#FFFFCC",
        "Other": "#E5D8BD",
        "Unavailable": "#FDDAEC",
        "Unknown": "#F2F2F2",
    }

HEADER_COLOR = "#2C5AA0"

# Required columns per treatment type
REQUIRED_COLUMNS = {
    "chemotherapy": {
        "flag": "HAD_CHEMO",
        "primary": "PAYER_CATEGORY_PRIMARY",
        "first": "PAYER_CATEGORY_AT_FIRST_CHEMO",
        "last": "PAYER_CATEGORY_AT_LAST_CHEMO",
        "first_label": "First Chemo",
        "last_label": "Last Chemo",
        "date_col": "LAST_CHEMO_DATE",
    },
    "radiation": {
        "flag": "HAD_RADIATION",
        "primary": "PAYER_CATEGORY_PRIMARY",
        "first": "PAYER_CATEGORY_AT_FIRST_RADIATION",
        "last": "PAYER_CATEGORY_AT_LAST_RADIATION",
        "first_label": "First Radiation",
        "last_label": "Last Radiation",
        "date_col": "LAST_RADIATION_DATE",
    },
    "sct": {
        "flag": "HAD_SCT",
        "primary": "PAYER_CATEGORY_PRIMARY",
        "first": "PAYER_CATEGORY_AT_FIRST_SCT",
        "last": "PAYER_CATEGORY_AT_LAST_SCT",
        "first_label": "First SCT",
        "last_label": "Last SCT",
        "date_col": "LAST_SCT_DATE",
    },
}


def _normalize_payer(s: pl.Series) -> pl.Series:
    """Replace null and empty string payer values with 'Unknown'."""
    return pl.Series(
        [("Unknown" if (v is None or v == "") else v) for v in s],
        dtype=pl.String,
    )


def _compute_post_treatment_payer(
    enc_payer_summary: pl.DataFrame,
    enc_path: Path,
) -> pl.DataFrame:
    """Compute post-treatment payer as mode category from encounters after last treatment date.

    Returns DataFrame with PATID, POST_TREATMENT_PAYER, HAD_CHEMO, HAD_RADIATION,
    HAD_SCT, HAD_ANY_TREATMENT, LAST_TREATMENT_DATE.
    """
    date_cols = ["LAST_CHEMO_DATE", "LAST_RADIATION_DATE", "LAST_SCT_DATE"]
    for col in date_cols:
        if col not in enc_payer_summary.columns:
            enc_payer_summary = enc_payer_summary.with_columns(
                pl.lit(None).cast(pl.Date).alias(col)
            )

    flag_cols = ["HAD_CHEMO", "HAD_RADIATION", "HAD_SCT"]
    for col in flag_cols:
        if col not in enc_payer_summary.columns:
            enc_payer_summary = enc_payer_summary.with_columns(
                pl.lit(0).cast(pl.Int8).alias(col)
            )

    patients = enc_payer_summary.with_columns(
        pl.max_horizontal("LAST_CHEMO_DATE", "LAST_RADIATION_DATE", "LAST_SCT_DATE")
        .alias("LAST_TREATMENT_DATE")
    )
    patients = patients.with_columns(
        (
            (pl.col("HAD_CHEMO") == 1)
            | (pl.col("HAD_RADIATION") == 1)
            | (pl.col("HAD_SCT") == 1)
        )
        .cast(pl.Int8)
        .alias("HAD_ANY_TREATMENT")
    )

    base_cols = [
        PATID_COL, "HAD_CHEMO", "HAD_RADIATION", "HAD_SCT",
        "HAD_ANY_TREATMENT", "LAST_TREATMENT_DATE",
    ]

    if not enc_path.exists():
        print(f"  [WARNING] {enc_path.name} not found; all patients get Unknown post-treatment payer")
        return patients.select(base_cols).with_columns(
            pl.lit("Unknown").alias("POST_TREATMENT_PAYER")
        )

    enc_schema = pl.read_parquet_schema(enc_path)
    if "PAYER_TYPE_PRIMARY" not in enc_schema.names():
        print("  [WARNING] PAYER_TYPE_PRIMARY column missing; all patients get Unknown post-treatment payer")
        return patients.select(base_cols).with_columns(
            pl.lit("Unknown").alias("POST_TREATMENT_PAYER")
        )

    has_secondary = "PAYER_TYPE_SECONDARY" in enc_schema.names()
    eff_expr, valid_expr, dual_expr = _effective_payer_and_dual_exprs(has_secondary)

    enc_cols = [PATID_COL, "ADMIT_DATE", "PAYER_TYPE_PRIMARY"]
    if has_secondary:
        enc_cols.append("PAYER_TYPE_SECONDARY")

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
        print("  [WARNING] No encounters found; all patients get Unknown post-treatment payer")
        return patients.select(base_cols).with_columns(
            pl.lit("Unknown").alias("POST_TREATMENT_PAYER")
        )

    patients_with_tx = patients.filter(pl.col("LAST_TREATMENT_DATE").is_not_null())
    if patients_with_tx.is_empty():
        return patients.select(base_cols).with_columns(
            pl.when(pl.col("HAD_ANY_TREATMENT") == 1)
            .then(pl.lit("Unknown"))
            .otherwise(pl.lit("Unknown"))
            .alias("POST_TREATMENT_PAYER")
        )

    joined = patients_with_tx.select(
        PATID_COL, "LAST_TREATMENT_DATE"
    ).join(enc, on=PATID_COL, how="inner")

    post_treatment = joined.filter(
        (pl.col("ADMIT_DATE") > pl.col("LAST_TREATMENT_DATE")) & pl.col("_valid")
    )

    print(f"  Post-treatment encounters: {post_treatment.height:,} (from {enc.height:,} total)")

    if post_treatment.is_empty():
        return patients.select(base_cols).with_columns(
            pl.lit("Unknown").alias("POST_TREATMENT_PAYER")
        )

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
    post_treatment = post_treatment.with_columns(
        pl.when(pl.col("PAYER_CATEGORY") == "No payment / Self-pay")
        .then(pl.lit("Self-pay"))
        .otherwise(pl.col("PAYER_CATEGORY"))
        .alias("PAYER_CATEGORY")
    )

    mode_df = (
        post_treatment.group_by(PATID_COL, "PAYER_CATEGORY")
        .agg(pl.len().alias("_n"))
        .sort("_n", descending=True)
        .group_by(PATID_COL)
        .first()
        .select(PATID_COL, pl.col("PAYER_CATEGORY").alias("POST_TREATMENT_PAYER"))
    )

    result = patients.select(base_cols).join(mode_df, on=PATID_COL, how="left")
    result = result.with_columns(
        pl.col("POST_TREATMENT_PAYER").fill_null("Unknown").alias("POST_TREATMENT_PAYER")
    )
    return result


def _build_combined_table(
    df: pl.DataFrame,
    primary_col: str,
    first_col: str,
    last_col: str,
    post_treatment_col: str,
    first_label: str,
    last_label: str,
) -> tuple[list[dict], int]:
    """Build 4-column table: Primary, First Treatment, Last Treatment, Post-Treatment.

    Returns (list of row dicts, cohort size).
    """
    cohort_size = df.height
    if cohort_size == 0:
        rows = []
        for cat in PAYER_CATEGORY_ORDER:
            rows.append({
                "Payer Category": cat,
                "Primary Insurance": "0 (0.0%)",
                first_label: "0 (0.0%)",
                last_label: "0 (0.0%)",
                "Post-Treatment": "0 (0.0%)",
            })
        return rows, cohort_size

    df_norm = df.with_columns([
        _normalize_payer(df[primary_col]).alias("_primary"),
        _normalize_payer(df[first_col]).alias("_first"),
        _normalize_payer(df[last_col]).alias("_last"),
        _normalize_payer(df[post_treatment_col]).alias("_post"),
    ])

    primary_map = {
        row["Category"]: row["N"]
        for row in df_norm.group_by("_primary").agg(pl.len().alias("N")).rename({"_primary": "Category"}).iter_rows(named=True)
    }
    first_map = {
        row["Category"]: row["N"]
        for row in df_norm.group_by("_first").agg(pl.len().alias("N")).rename({"_first": "Category"}).iter_rows(named=True)
    }
    last_map = {
        row["Category"]: row["N"]
        for row in df_norm.group_by("_last").agg(pl.len().alias("N")).rename({"_last": "Category"}).iter_rows(named=True)
    }
    post_map = {
        row["Category"]: row["N"]
        for row in df_norm.group_by("_post").agg(pl.len().alias("N")).rename({"_post": "Category"}).iter_rows(named=True)
    }

    rows = []
    for cat in PAYER_CATEGORY_ORDER:
        n_p = primary_map.get(cat, 0)
        n_f = first_map.get(cat, 0)
        n_l = last_map.get(cat, 0)
        n_pt = post_map.get(cat, 0)

        pct_p = 100.0 * n_p / cohort_size
        pct_f = 100.0 * n_f / cohort_size
        pct_l = 100.0 * n_l / cohort_size
        pct_pt = 100.0 * n_pt / cohort_size

        rows.append({
            "Payer Category": cat,
            "Primary Insurance": f"{n_p} ({pct_p:.1f}%)",
            first_label: f"{n_f} ({pct_f:.1f}%)",
            last_label: f"{n_l} ({pct_l:.1f}%)",
            "Post-Treatment": f"{n_pt} ({pct_pt:.1f}%)",
        })

    return rows, cohort_size


def _render_html(
    table_data: list[dict],
    title: str,
    output_path: Path,
    first_label: str,
    last_label: str,
) -> None:
    """Render combined 4-column table as styled HTML file with inline CSS."""
    css_classes = []
    for category in PAYER_CATEGORY_ORDER:
        class_name = category.lower().replace(" ", "-")
        color = PAYER_COLORS.get(category, "#FFFFFF")
        css_classes.append(f"    .payer-{class_name} {{ background-color: {color}; }}")

    css_block = "\n".join(css_classes)

    html_lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        '  <meta charset="UTF-8">',
        f"  <title>{html.escape(title)}</title>",
        "  <style>",
        "    body {",
        "      font-family: Arial, sans-serif;",
        "      padding: 20px;",
        "      background-color: #f9f9f9;",
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
        f"      background-color: {HEADER_COLOR};",
        "      color: white;",
        "      padding: 12px 16px;",
        "      text-align: center;",
        f"      border: 1px solid {HEADER_COLOR};",
        "      font-weight: bold;",
        "    }",
        "    th:first-child {",
        "      text-align: left;",
        "    }",
        "    td {",
        "      padding: 10px 16px;",
        "      border: 1px solid #ddd;",
        "      text-align: center;",
        "    }",
        "    td:first-child {",
        "      text-align: left;",
        "      font-weight: 500;",
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
        "        <th>Post-Treatment</th>",
        "      </tr>",
        "    </thead>",
        "    <tbody>",
    ]

    for row in table_data:
        payer_cat = row["Payer Category"]
        class_name = payer_cat.lower().replace(" ", "-")

        html_lines.append(f'      <tr class="payer-{class_name}">')
        html_lines.append(f"        <td>{html.escape(payer_cat)}</td>")
        html_lines.append(f"        <td>{html.escape(row['Primary Insurance'])}</td>")
        html_lines.append(f"        <td>{html.escape(row[first_label])}</td>")
        html_lines.append(f"        <td>{html.escape(row[last_label])}</td>")
        html_lines.append(f"        <td>{html.escape(row['Post-Treatment'])}</td>")
        html_lines.append("      </tr>")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_lines.extend([
        "    </tbody>",
        "  </table>",
        '  <div class="footer">',
        f"    Source: encounter_payer_summary.parquet, ENCOUNTER.parquet | Generated: {timestamp}",
        "  </div>",
        "</body>",
        "</html>",
    ])

    output_path.write_text("\n".join(html_lines), encoding="utf-8")


def main(config_path: Path | None = None) -> None:
    """Build combined insurance tables (Phase 5 + Phase 6 merged) per treatment cohort.

    Outputs three HTML files:
      - chemotherapy_insurance_table.html
      - radiation_insurance_table.html
      - sct_insurance_table.html

    Each table shows 9 payer categories across 4 columns:
      Primary Insurance | First {Treatment} | Last {Treatment} | Post-Treatment
    """
    print("=" * 60)
    print("COMBINED INSURANCE TABLES — Per Treatment Cohort")
    print("=" * 60)

    paths = load_and_validate_config(config_path)
    derived_dir = paths.derived_dir
    clean_dir = paths.parquet_dir
    reports_dir = PROJECT_ROOT / "reports" / "combined_insurance"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # --- Load encounter payer summary ---
    enc_payer_path = derived_dir / "encounter_payer_summary.parquet"
    if not enc_payer_path.exists():
        print("encounter_payer_summary.parquet missing; skipping.")
        sys.exit(0)

    df = pl.read_parquet(enc_payer_path)
    if df.is_empty():
        print("encounter_payer_summary.parquet is empty; skipping.")
        sys.exit(0)

    print(f"\n  derived_dir: {derived_dir}")
    print(f"  clean_dir:   {clean_dir}")
    print(f"  Patients:    {df.height:,}")

    # --- Validate required columns ---
    missing_all = True
    for treatment, spec in REQUIRED_COLUMNS.items():
        needed = [spec["flag"], spec["primary"], spec["first"], spec["last"]]
        absent = [c for c in needed if c not in df.columns]
        if absent:
            print(f"\n  [WARNING] Missing columns for {treatment}: {absent}")
            print(f"            Re-run: python scripts/assemble_clean.py")
        else:
            missing_all = False

    if missing_all:
        print("\n  [FATAL] All treatment column sets are missing. Cannot generate any tables.")
        sys.exit(1)

    # --- Compute post-treatment payer ---
    enc_candidates = sorted(clean_dir.glob("ENCOUNTER*.parquet"))
    enc_path = enc_candidates[0] if enc_candidates else clean_dir / "ENCOUNTER.parquet"
    print(f"\n  ENCOUNTER parquet: {enc_path.name}")
    print("  Computing post-treatment payer...")
    post_tx = _compute_post_treatment_payer(df, enc_path)

    # --- Build and write tables per treatment ---
    output_specs = {
        "chemotherapy": {
            "filename": "chemotherapy_insurance_table.html",
            "title_label": "Chemotherapy",
        },
        "radiation": {
            "filename": "radiation_insurance_table.html",
            "title_label": "Radiation",
        },
        "sct": {
            "filename": "sct_insurance_table.html",
            "title_label": "Stem Cell Transplant (SCT)",
        },
    }

    print("\n  Building tables...")
    for treatment, spec in REQUIRED_COLUMNS.items():
        needed = [spec["flag"], spec["primary"], spec["first"], spec["last"]]
        if any(c not in df.columns for c in needed):
            print(f"    [SKIPPED] {treatment} — missing columns")
            continue

        # Filter to treatment cohort
        df_cohort = df.filter(pl.col(spec["flag"]) == 1)
        cohort_size = df_cohort.height
        if cohort_size == 0:
            print(f"    [SKIPPED] {treatment} — 0 patients in cohort")
            continue

        # Join post-treatment payer
        df_cohort = df_cohort.join(
            post_tx.select(PATID_COL, "POST_TREATMENT_PAYER"),
            on=PATID_COL,
            how="left",
        )
        df_cohort = df_cohort.with_columns(
            pl.col("POST_TREATMENT_PAYER").fill_null("Unknown")
        )

        # Build 4-column table
        table_data, size = _build_combined_table(
            df_cohort,
            primary_col=spec["primary"],
            first_col=spec["first"],
            last_col=spec["last"],
            post_treatment_col="POST_TREATMENT_PAYER",
            first_label=spec["first_label"],
            last_label=spec["last_label"],
        )

        # Render HTML
        out_spec = output_specs[treatment]
        title = f"{out_spec['title_label']} Cohort (N={size:,})"
        html_path = reports_dir / out_spec["filename"]
        _render_html(
            table_data, title, html_path,
            first_label=spec["first_label"],
            last_label=spec["last_label"],
        )

        print(f"    {out_spec['filename']}  (N={size:,})")

    print(f"\n  Output directory: {reports_dir}")
    print("Done.")


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(config_path)
