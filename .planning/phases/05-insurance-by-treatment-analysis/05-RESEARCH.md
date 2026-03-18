# Phase 5: Insurance by Treatment Analysis - Research

**Researched:** 2026-03-18
**Domain:** Python data table visualization and presentation-ready output generation
**Confidence:** HIGH

## Summary

Phase 5 replaces the existing `scripts/build_insurance_summary.py` with a new implementation that generates presentation-ready summary tables of insurance coverage patterns stratified by treatment type (chemotherapy, radiation, SCT). The phase requires outputting tables in three formats: PNG images (color-coded), CSV + markdown, and styled HTML.

The codebase uses **Polars** for data manipulation and already has matplotlib/seaborn installed. The upstream data source (`encounter_payer_summary.parquet`) exists but currently lacks several treatment-specific columns mentioned in CONTEXT.md requirements (PAYER_CATEGORY_AT_FIRST_RADIATION, PAYER_CATEGORY_AT_LAST_RADIATION, PAYER_CATEGORY_AT_FIRST_SCT, PAYER_CATEGORY_AT_LAST_SCT). The pipeline logic for building this parquet is in `src/report/encounter_payer_summary.py` and is already designed to produce these columns - the existing parquet may simply be from an older pipeline run.

**Primary recommendation:** Use matplotlib for PNG table generation (already installed, no new dependencies), Polars native operations for CSV generation, and simple HTML templating with inline CSS for styled HTML output. Avoid introducing new heavy dependencies (plotly, great-tables) that require additional setup (Selenium, Kaleido).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Replace `scripts/build_insurance_summary.py` entirely with a new implementation
- The current output (CSVs, markdown, charts) has wrong structure, missing analyses, and wrong format
- New script reads from `encounter_payer_summary.parquet` (same data source, pending audit of column sufficiency)
- **Table structure:**
  - Rows: One row per payer category (Medicare, Medicaid, Dual eligible, Private, Other government, Self-pay, Other, Unavailable, Unknown)
  - Columns per table: Primary insurance (mode), Insurance at first treatment, Insurance at last treatment
  - Cell values: N (%) format, e.g. "45 (23.4%)"
  - No total row, no total column
  - Cohort size in table header, e.g. "Chemotherapy Cohort (N=192)"
  - Three separate treatment-specific tables (chemo, radiation, SCT) PLUS a combined overview table
  - No payer transition analysis — just snapshots at each timepoint
- **Output formats (all three required):**
  - PNG images: Color-coded tables (by payer category or treatment type) for easy paste into presentation slides
  - CSV + markdown: CSV for data, markdown for readable preview
  - HTML: Styled HTML tables for screenshot or paste
- **Visual style:**
  - Colorful, presentation-appropriate — color-coded by payer category or treatment type for visual impact
  - No bar charts or other visualizations — tables only
- **HIPAA suppression:**
  - No small-cell suppression — show all counts as-is (internal/working tables, not for publication)
- **Statistical detail:**
  - N (%) only — no confidence intervals, no statistical tests

### Claude's Discretion
- Specific color palette for payer categories
- PNG rendering approach (matplotlib table, plotly, or other)
- HTML styling details
- Whether to audit/modify upstream encounter_payer_summary.parquet or just use existing columns
- Script naming and module organization

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.38.1 | Data manipulation and aggregation | Already project standard; zero-copy operations, efficient groupby/pivot |
| matplotlib | 3.10.8 | PNG table rendering | Already installed; proven table rendering with `matplotlib.pyplot.table()` |
| Python stdlib (pathlib, csv) | 3.14 | File I/O and path handling | Built-in; no dependencies |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | 2.4.1 | Array operations for matplotlib | Already installed; matplotlib backend for color arrays |
| seaborn | 0.13.2 | Color palette selection | Already installed; professional categorical color palettes |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| matplotlib | plotly + kaleido | Plotly requires kaleido package for static PNG export; adds dependency complexity for minimal gain |
| matplotlib | great-tables + selenium | Requires Selenium + Chrome/Firefox webdriver; significant setup overhead for screenshot-based PNG generation |
| HTML templating | pandas.DataFrame.to_html() | Requires pandas (not installed); Polars native + Jinja2 or simple string templating simpler |

**Installation:**
No new packages required - all necessary libraries already installed in project environment.

## Architecture Patterns

### Recommended Project Structure
```
scripts/
├── build_insurance_by_treatment.py    # New script (replaces build_insurance_summary.py)
└── (existing scripts remain)

reports/
├── insurance_by_treatment/            # New output directory
│   ├── overview_table.png             # Combined overview table
│   ├── chemotherapy_table.png         # Chemo-specific table
│   ├── radiation_table.png            # Radiation-specific table
│   ├── sct_table.png                  # SCT-specific table
│   ├── overview_table.csv             # CSV versions
│   ├── chemotherapy_table.csv
│   ├── radiation_table.csv
│   ├── sct_table.csv
│   ├── overview_table.html            # HTML versions
│   ├── chemotherapy_table.html
│   ├── radiation_table.html
│   ├── sct_table.html
│   └── README.md                      # Markdown preview with all tables
```

### Pattern 1: Polars Data Aggregation
**What:** Build N (%) format cells with Polars expressions, avoiding iterrows()
**When to use:** For all data aggregation before visualization
**Example:**
```python
# Source: Project pattern from build_insurance_summary.py
import polars as pl

# Group by payer category and calculate N and percentage
summary = (
    df.filter(pl.col("HAD_CHEMO") == 1)
    .group_by("PAYER_CATEGORY_AT_FIRST_CHEMO")
    .agg(pl.len().alias("N"))
    .with_columns(
        (100.0 * pl.col("N") / df.filter(pl.col("HAD_CHEMO") == 1).height).alias("Pct")
    )
    .with_columns(
        pl.format("{}  ({:.1f}%)", pl.col("N"), pl.col("Pct")).alias("N_Pct")
    )
)
```

### Pattern 2: Matplotlib Table Rendering with Color
**What:** Create presentation-ready PNG tables with cell background colors
**When to use:** For PNG output generation
**Example:**
```python
# Source: https://matplotlib.org/stable/gallery/misc/table_demo.html
# Modified for cell colors
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

fig, ax = plt.subplots(figsize=(8, 6))
ax.axis('off')

# Cell colors: 2D array matching table shape (rows x cols)
cell_colors = [
    ['#E8F4F8', '#E8F4F8', '#E8F4F8'],  # Header row (light blue)
    ['#FFE6E6', '#FFE6E6', '#FFE6E6'],  # Medicare row (light red)
    ['#E6F3E6', '#E6F3E6', '#E6F3E6'],  # Medicaid row (light green)
    # ... one color array per row
]

table = ax.table(
    cellText=cell_data,
    colLabels=["Primary Insurance", "First Treatment", "Last Treatment"],
    cellColours=cell_colors,
    loc='center',
    cellLoc='left'
)
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1.2, 1.8)  # Scale for readability

plt.savefig('output.png', dpi=150, bbox_inches='tight')
plt.close()
```

### Pattern 3: HTML Table Generation with Inline CSS
**What:** Generate styled HTML tables with embedded CSS (no external dependencies)
**When to use:** For HTML output generation
**Example:**
```python
# Source: Project pattern adapted from existing HTML generation needs
html_template = """
<html>
<head>
<style>
table {{
    border-collapse: collapse;
    font-family: Arial, sans-serif;
    margin: 20px;
}}
th {{
    background-color: {header_color};
    color: white;
    padding: 12px;
    text-align: left;
    border: 1px solid #ddd;
}}
td {{
    padding: 10px;
    border: 1px solid #ddd;
}}
.payer-medicare {{ background-color: {medicare_color}; }}
.payer-medicaid {{ background-color: {medicaid_color}; }}
/* ... CSS class per payer category */
</style>
</head>
<body>
<h2>{title}</h2>
<table>
<thead>
<tr>{header_row}</tr>
</thead>
<tbody>
{data_rows}
</tbody>
</table>
</body>
</html>
"""

# Generate HTML by string formatting (no templating engine needed)
html = html_template.format(
    header_color='#2C5AA0',
    medicare_color='#FFE6E6',
    # ... fill in all placeholders
)
Path('output.html').write_text(html, encoding='utf-8')
```

### Pattern 4: Categorical Color Palette Selection
**What:** Use seaborn's categorical palettes for professional, colorblind-friendly colors
**When to use:** For assigning colors to payer categories
**Example:**
```python
# Source: https://seaborn.pydata.org/tutorial/color_palettes.html
import seaborn as sns

# For 9 payer categories, use Set2 or Pastel1 (designed for 8-12 categories)
palette = sns.color_palette("Pastel1", n_colors=9)  # Returns list of RGB tuples

# Convert to hex for matplotlib
payer_colors = {
    "Medicare": mcolors.to_hex(palette[0]),
    "Medicaid": mcolors.to_hex(palette[1]),
    "Dual eligible": mcolors.to_hex(palette[2]),
    # ... map all 9 categories
}
```

### Anti-Patterns to Avoid
- **Pandas dependency:** Don't convert Polars → Pandas → visualization. Keep Polars native and convert directly to lists/numpy for matplotlib.
- **External templating engines:** Don't add Jinja2/Mako for simple HTML generation. String formatting sufficient for this phase.
- **Plotly for static tables:** Plotly is overkill for static PNG tables; requires kaleido package and is designed for interactive visualizations.
- **Selenium-based screenshot tools:** Don't use great-tables, dataframe-image, or other screenshot-based PNG generation. Direct matplotlib rendering is faster and has no browser dependency.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Color palette generation | Manual RGB tuples or hex codes | seaborn.color_palette() | Seaborn provides 20+ perceptually uniform, colorblind-safe palettes designed by color experts (ColorBrewer, etc.) |
| N (%) formatting | String concatenation with f-strings | polars.format() expression | Polars format() handles nulls, type casting, and vectorized formatting in-expression |
| Payer category ordering | Manual sort by category name | Predefined order mapping | Project already has PAYER_CATEGORY_ORDER constant in build_insurance_summary.py (line 25-35) |
| HTML escaping | Manual .replace() for <, >, & | html.escape() | Prevents XSS if data contains HTML-like characters; stdlib solution |

**Key insight:** Table rendering is deceptively complex (alignment, padding, colors, fonts, image scaling). Matplotlib has battle-tested table rendering code handling all edge cases. Don't build custom PIL/Pillow-based table drawing.

## Common Pitfalls

### Pitfall 1: Mismatched Cell Colors Array Shape
**What goes wrong:** matplotlib table requires cellColours to match shape (rows x cols) exactly, including header row. Providing wrong shape causes silent rendering bugs (colors don't apply) or IndexError.
**Why it happens:** Easy to forget header row when building color array programmatically.
**How to avoid:** Build color array with explicit row count = data rows + 1 (header). Validate shape before passing to table().
**Warning signs:** Table renders but colors don't appear; or "IndexError: list index out of range" in table drawing code.

### Pitfall 2: Matplotlib Figure Size vs Table Content Size
**What goes wrong:** Table content overflows figure or has too much whitespace. Text becomes unreadable at default DPI.
**Why it happens:** matplotlib figure size is in inches, table scaling is separate. Need to coordinate figsize, table.scale(), and savefig DPI.
**How to avoid:** Use `table.auto_set_font_size(False)` and manually set font size. Iterate on figsize + scale + DPI combination with test data. Rule of thumb: figsize=(cols*2, rows*1.5), scale=(1.2, 1.8), dpi=150.
**Warning signs:** Text overlaps, cells too narrow, excessive whitespace around table.

### Pitfall 3: Parquet Column Availability Assumption
**What goes wrong:** Script crashes with KeyError because parquet is missing expected columns (e.g., PAYER_CATEGORY_AT_FIRST_RADIATION).
**Why it happens:** CONTEXT.md lists columns that SHOULD exist, but current parquet might be from older pipeline run. Pipeline code in encounter_payer_summary.py (line 788-813) shows radiation/SCT payer logic exists but may not have executed.
**How to avoid:** Add column presence check at script start. If treatment columns missing, either error with helpful message ("Re-run assemble_clean.py to generate full parquet") or compute missing columns inline (less preferred - duplicates pipeline logic).
**Warning signs:** KeyError on PAYER_CATEGORY_AT_FIRST_RADIATION or HAD_RADIATION when trying to filter cohorts.

### Pitfall 4: Forgetting "No Small-Cell Suppression" Requirement
**What goes wrong:** Script applies suppress() or flag_small_cell() to counts, masking 1-10 values per existing pipeline pattern.
**Why it happens:** Existing build_insurance_summary.py (line 182-183, 236-237) uses _suppress() and flag_small_cell() extensively. Easy to copy-paste pattern.
**How to avoid:** CONTEXT.md explicitly states "No small-cell suppression — show all counts as-is (internal/working tables, not for publication)". Do NOT import or use suppress()/flag_small_cell() in new script.
**Warning signs:** CSV/HTML showing "-" instead of actual counts; PNG table cells showing "5 ⚠" instead of "5".

### Pitfall 5: Missing Cohort Size in Table Headers
**What goes wrong:** Tables lack cohort size notation (e.g., "Chemotherapy Cohort (N=192)"), making it unclear how many patients are in each treatment group.
**Why it happens:** Easy to forget when focusing on cell data; requirement is in CONTEXT.md but not emphasized.
**How to avoid:** Build table title as f"{treatment_name} Cohort (N={cohort_size:,})" for all treatment-specific tables. For overview table, include total enrolled patient count.
**Warning signs:** User feedback that tables lack context; no way to assess sample size adequacy from table alone.

## Code Examples

Verified patterns from official sources and project code:

### Polars: N (%) Formatting
```python
# Source: Project pattern (build_insurance_summary.py) + Polars format() docs
import polars as pl

df_chemo = df.filter(pl.col("HAD_CHEMO") == 1)
n_chemo = df_chemo.height

summary = (
    df_chemo
    .group_by("PAYER_CATEGORY_AT_FIRST_CHEMO")
    .agg(pl.len().alias("N"))
    .with_columns([
        (100.0 * pl.col("N") / n_chemo).alias("Pct"),
        pl.format("{}  ({:.1f}%)", pl.col("N"), pl.col("Pct")).alias("N_Pct")
    ])
)
```

### Matplotlib: Color-Coded Table PNG
```python
# Source: https://matplotlib.org/stable/gallery/misc/table_demo.html
# Modified for payer category coloring
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import seaborn as sns

# Get pastel palette for 9 payer categories
palette = sns.color_palette("Pastel1", n_colors=9)
payer_colors = {
    "Medicare": mcolors.to_hex(palette[0]),
    "Medicaid": mcolors.to_hex(palette[1]),
    "Dual eligible": mcolors.to_hex(palette[2]),
    "Private": mcolors.to_hex(palette[3]),
    "Other government": mcolors.to_hex(palette[4]),
    "Self-pay": mcolors.to_hex(palette[5]),
    "Other": mcolors.to_hex(palette[6]),
    "Unavailable": mcolors.to_hex(palette[7]),
    "Unknown": mcolors.to_hex(palette[8]),
}

# Build cell_colors array: header row + data rows
header_color = '#2C5AA0'  # Dark blue
cell_colors = [[header_color] * 3]  # 3 columns
for payer in payer_order:
    row_color = payer_colors[payer]
    cell_colors.append([row_color] * 3)

# Render table
fig, ax = plt.subplots(figsize=(10, 6))
ax.axis('off')
table = ax.table(
    cellText=cell_data,
    colLabels=["Primary Insurance", "First Treatment", "Last Treatment"],
    cellColours=cell_colors,
    loc='center',
    cellLoc='left'
)
table.auto_set_font_size(False)
table.set_fontsize(11)
table.scale(1.2, 2.0)

# Add title above table
fig.suptitle("Chemotherapy Cohort (N=192)", fontsize=14, fontweight='bold', y=0.95)

plt.savefig('chemo_table.png', dpi=150, bbox_inches='tight')
plt.close()
```

### CSV + Markdown Generation
```python
# Source: Project pattern (build_insurance_summary.py line 208-209, 633-634)
from pathlib import Path

# CSV (Polars native)
summary_df.select(["Payer", "Primary", "First_Treatment", "Last_Treatment"]).write_csv(
    output_dir / "chemotherapy_table.csv"
)

# Markdown (simple string building)
md_lines = [
    "# Insurance by Treatment Analysis",
    "",
    "## Chemotherapy Cohort (N=192)",
    "",
    "| Payer Category | Primary Insurance | First Treatment | Last Treatment |",
    "|----------------|-------------------|-----------------|----------------|",
]
for row in summary_df.iter_rows(named=True):
    md_lines.append(
        f"| {row['Payer']} | {row['Primary']} | {row['First_Treatment']} | {row['Last_Treatment']} |"
    )
md_lines.append("")

Path(output_dir / "README.md").write_text("\n".join(md_lines), encoding='utf-8')
```

### HTML: Styled Table with Inline CSS
```python
# Source: Web search results + HTML best practices
from html import escape

html_rows = []
for i, row in enumerate(summary_df.iter_rows(named=True)):
    payer = escape(row['Payer'])
    css_class = payer.lower().replace(' ', '-').replace('/', '-')
    html_rows.append(
        f'<tr class="payer-{css_class}">'
        f'<td>{payer}</td>'
        f'<td>{escape(row["Primary"])}</td>'
        f'<td>{escape(row["First_Treatment"])}</td>'
        f'<td>{escape(row["Last_Treatment"])}</td>'
        f'</tr>'
    )

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
table {{
    border-collapse: collapse;
    font-family: Arial, sans-serif;
    margin: 20px auto;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}}
th {{
    background-color: #2C5AA0;
    color: white;
    padding: 12px 16px;
    text-align: left;
    border: 1px solid #ddd;
    font-weight: bold;
}}
td {{
    padding: 10px 16px;
    border: 1px solid #ddd;
}}
tbody tr:hover {{
    background-color: #f5f5f5;
}}
.payer-medicare {{ background-color: {payer_colors['Medicare']}; }}
.payer-medicaid {{ background-color: {payer_colors['Medicaid']}; }}
/* ... Add CSS class for each payer category */
</style>
</head>
<body>
<h2 style="text-align:center; font-family:Arial,sans-serif;">Chemotherapy Cohort (N=192)</h2>
<table>
<thead>
<tr>
<th>Payer Category</th>
<th>Primary Insurance</th>
<th>First Treatment</th>
<th>Last Treatment</th>
</tr>
</thead>
<tbody>
{''.join(html_rows)}
</tbody>
</table>
</body>
</html>"""

Path(output_dir / "chemotherapy_table.html").write_text(html, encoding='utf-8')
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pandas DataFrame → matplotlib | Polars DataFrame → matplotlib via to_numpy() | Polars 0.15+ (2023) | Zero-copy conversion for numeric data; ~2x faster for large tables |
| Manual color selection | seaborn categorical palettes | Seaborn 0.11+ (2021) | Colorblind-safe palettes; professional quality with 1 line of code |
| plotly.figure_factory.create_table | matplotlib.pyplot.table for static images | Ongoing | Matplotlib simpler for static PNG; no kaleido dependency |
| great-tables for PNG export | Direct matplotlib rendering | 2024-2025 | great-tables requires Selenium + browser driver; matplotlib is self-contained |

**Deprecated/outdated:**
- **pandas.DataFrame.to_html():** Still valid but requires pandas dependency. For Polars-native projects, direct HTML generation with html.escape() is cleaner.
- **PIL ImageDraw for table rendering:** Superseded by matplotlib table API. Manual pixel-level table drawing was error-prone and required complex layout logic.

## Open Questions

1. **Are radiation/SCT payer columns present in current parquet?**
   - What we know: encounter_payer_summary.parquet (12 rows, 10 cols) is missing PAYER_CATEGORY_AT_FIRST_RADIATION, PAYER_CATEGORY_AT_LAST_RADIATION, PAYER_CATEGORY_AT_FIRST_SCT, PAYER_CATEGORY_AT_LAST_SCT per inspection. Pipeline code in src/report/encounter_payer_summary.py lines 788-840 has logic to compute these columns.
   - What's unclear: Is parquet outdated (needs re-run of assemble_clean.py) or do radiation/SCT procedures not exist in source data (PROCEDURES table)?
   - Recommendation: Script should check column presence at startup. If missing, print clear message: "Required columns missing. Re-run: python scripts/assemble_clean.py". Exit with code 1. Don't try to compute inline (complex logic, duplicates pipeline).

2. **What is the intended color-coding scheme?**
   - What we know: CONTEXT.md says "color-coded by payer category or treatment type for visual impact" but leaves specific palette to Claude's discretion.
   - What's unclear: Should colors be consistent across all 4 tables (same payer → same color) or different per treatment type (e.g., chemo=blue theme, radiation=green theme)?
   - Recommendation: Use consistent payer category colors across all tables for recognizability. Use seaborn "Pastel1" palette (soft colors appropriate for presentations). Document color mapping in script comments.

3. **Should overview table aggregate across treatments or show separate columns?**
   - What we know: CONTEXT.md requires "combined overview table" in addition to 3 treatment-specific tables. Table structure has 3 columns: "Primary insurance (mode), Insurance at first treatment, Insurance at last treatment".
   - What's unclear: For overview table, what does "first treatment" mean when patient has multiple treatment types? First of ANY treatment (min date across chemo/rad/SCT)?
   - Recommendation: Overview table = aggregated across all enrolled patients (not filtered by treatment). Columns: (1) Primary insurance (mode), (2) Insurance at first HL diagnosis (PAYER_CATEGORY_AT_FIRST_DX), (3) "N/A" for last treatment (no single "last treatment" definition across modalities). Alternative: make overview table show treatment-agnostic payer distribution only (1 column: Primary insurance).

## Sources

### Primary (HIGH confidence)
- Matplotlib table API documentation: https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.table.html
- Matplotlib table gallery example: https://matplotlib.org/stable/gallery/misc/table_demo.html
- Seaborn color palettes tutorial: https://seaborn.pydata.org/tutorial/color_palettes.html
- Polars format() expression docs: https://docs.pola.rs/api/python/dev/reference/expressions/api/polars.format.html
- Project source code: `scripts/build_insurance_summary.py`, `src/report/encounter_payer_summary.py`, `src/report/suppression.py`

### Secondary (MEDIUM confidence)
- Practical Guide to Professional Table Rendering in Python: https://medium.com/data-science-collective/designing-stylish-table-visualizations-in-python-2f43cfc82912
- Polars visualization guide: https://docs.pola.rs/user-guide/misc/visualization/
- HTML table styling (W3Schools): https://www.w3schools.com/html/html_table_styling.asp

### Tertiary (LOW confidence)
- great-tables PNG export (requires Selenium): https://posit-dev.github.io/great-tables/reference/GT.save.html
- Plotly static image export (requires kaleido): https://plotly.com/python/static-image-export/

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already installed; matplotlib table rendering is well-documented
- Architecture: HIGH - Patterns directly from project code + official matplotlib docs; tested approach
- Pitfalls: HIGH - Derived from direct parquet inspection + matplotlib API quirks documented in gallery examples
- Color palette selection: MEDIUM - Seaborn categorical palettes are standard but specific palette choice ("Pastel1") is subjective

**Research date:** 2026-03-18
**Valid until:** 60 days (stable domain - table rendering patterns don't change rapidly)
