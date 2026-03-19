# Phase 6: Post-Treatment Insurance - Research

**Researched:** 2026-03-19
**Domain:** Clinical data analysis - post-treatment payer derivation and presentation table generation
**Confidence:** HIGH

## Summary

Phase 6 derives the most prevalent (mode) payer category from encounters occurring after a patient's last treatment date (max of last chemo, last radiation, and last SCT dates, nulls ignored), and produces standalone summary tables showing post-treatment insurance distributions. The phase builds directly on Phase 5's infrastructure for treatment-stratified payer tables.

The implementation requires: (1) computing a single "last treatment date" per patient as the maximum across all three treatment modalities (LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE), (2) filtering encounters where ADMIT_DATE > last_treatment_date, (3) deriving the mode payer category across those post-treatment encounters, and (4) generating 4 standalone tables (combined post-treatment, and per-cohort breakdowns for chemo, radiation, SCT) matching Phase 5's visual style.

The codebase already has all necessary infrastructure: `src/report/encounter_payer_summary.py` computes LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE columns and treatment flags (HAD_CHEMO, HAD_RADIATION, HAD_SCT), Phase 5's `build_insurance_by_treatment.py` provides proven table rendering patterns (PNG with seaborn Pastel1 palette, CSV, HTML), and the `_payer_mode_in_window()` function demonstrates mode payer derivation logic that can be adapted for post-treatment encounters.

**Primary recommendation:** Extend `build_insurance_by_treatment.py` or create a companion script `build_post_treatment_insurance.py` that reuses Phase 5's table rendering infrastructure. Compute last treatment date using Polars `pl.max_horizontal()` for LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE (ignoring nulls), join encounters on ADMIT_DATE > last_treatment_date, and apply existing mode payer derivation patterns. Output to `reports/post_treatment_insurance/` directory with identical visual styling.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Post-treatment date logic:**
  - Last treatment date = max(LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE), nulls ignored
  - Single date per patient across all treatment types (not per-treatment-type windows)
  - Post-treatment period starts immediately after last treatment date (no buffer/gap)
  - Any encounter with ADMIT_DATE > last_treatment_date counts as post-treatment
- **Output destination:**
  - Separate standalone table(s) — NOT added as a column to existing Phase 5 tables
  - One combined table for all patients who had any treatment, PLUS per-cohort breakdowns (chemo, radiation, SCT)
  - So 4 tables total: combined post-treatment, post-treatment for chemo cohort, radiation cohort, SCT cohort
  - Same 3 output formats as Phase 5: PNG (color-coded), CSV + markdown, HTML (styled)
  - Same visual style, colors, and layout as Phase 5 tables
- **Edge cases:**
  - Patients with no encounters after last treatment: count under "Unknown" payer category
  - Patients with no treatment at all (HAD_CHEMO=0, HAD_RADIATION=0, HAD_SCT=0): include in combined table with payer marked as N/A
  - One post-treatment encounter is sufficient — no minimum threshold
- **Payer selection rule:**
  - Mode (most frequent) payer category across all post-treatment encounters — same approach as Phase 5
  - No time cap — all encounters after last treatment count, even years later
  - No HIPAA small-cell suppression — show all counts as-is (internal working tables)
- **Table structure:**
  - Same structure as Phase 5 tables: 9 payer category rows (+ N/A row for no-treatment patients in combined table)
  - Single column per table: "Post-Treatment Insurance" showing N (%) format
  - Cohort size in table header, e.g., "Post-Treatment: Chemotherapy Cohort (N=XXX)"

### Claude's Discretion
- Whether to compute post-treatment payer in the existing encounter_payer_summary.py or inline in the script
- Script organization (extend build_insurance_by_treatment.py or new script)
- Exact table column header wording
- How to handle the N/A row visually (color, placement)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.38.1 | Data manipulation and max() across columns | Already project standard; has `pl.max_horizontal()` for row-wise max across nullable columns |
| matplotlib | 3.10.8 | PNG table rendering | Already installed; Phase 5 proven pattern with `matplotlib.pyplot.table()` |
| Python stdlib (pathlib, datetime, html) | 3.14 | File I/O, timestamps, HTML escaping | Built-in; no dependencies |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| seaborn | 0.13.2 | Color palette (reuse Phase 5 Pastel1 palette) | Already installed; ensures visual consistency with Phase 5 tables |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Inline post-treatment payer computation | Add column to encounter_payer_summary.py | Would bloat that module and slow pipeline for a single-use analysis; computing inline in script is cleaner |
| New script | Extend build_insurance_by_treatment.py | Either approach works; new script keeps concerns separated and output directories distinct |

**Installation:**
No new packages required - all necessary libraries already installed in project environment.

## Architecture Patterns

### Recommended Project Structure
```
scripts/
├── build_insurance_by_treatment.py       # Phase 5 (existing)
└── build_post_treatment_insurance.py     # Phase 6 (new, recommended)

reports/
├── insurance_by_treatment/               # Phase 5 outputs
│   └── (existing files)
└── post_treatment_insurance/             # Phase 6 outputs (new directory)
    ├── combined_post_treatment.png
    ├── chemo_post_treatment.png
    ├── radiation_post_treatment.png
    ├── sct_post_treatment.png
    ├── combined_post_treatment.csv
    ├── chemo_post_treatment.csv
    ├── radiation_post_treatment.csv
    ├── sct_post_treatment.csv
    ├── combined_post_treatment.html
    ├── chemo_post_treatment.html
    ├── radiation_post_treatment.html
    ├── sct_post_treatment.html
    └── README.md
```

**Alternative:** If extending `build_insurance_by_treatment.py`, place outputs in `reports/insurance_by_treatment/post_treatment/` subdirectory. User constraint allows Claude's discretion on script organization.

### Pattern 1: Row-wise Maximum Across Nullable Date Columns
**What:** Compute max(LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE) handling nulls correctly
**When to use:** For deriving last_treatment_date per patient
**Example:**
```python
# Source: Polars 1.38.1 max_horizontal() documentation
import polars as pl

# Assume encounter_payer_summary.parquet has these columns
df = pl.read_parquet("derived/encounter_payer_summary.parquet")

# max_horizontal ignores nulls automatically (like SQL GREATEST with COALESCE behavior)
df = df.with_columns(
    pl.max_horizontal(
        "LAST_CHEMO_DATE",
        "LAST_RADIATION_DATE",
        "LAST_SCT_DATE"
    ).alias("LAST_TREATMENT_DATE")
)

# Result: LAST_TREATMENT_DATE is null only if ALL three are null
# Otherwise it's the latest non-null date across the three modalities
```

### Pattern 2: Mode Payer Derivation from Filtered Encounters
**What:** Find most frequent payer category among encounters matching a filter (ADMIT_DATE > last_treatment_date)
**When to use:** For computing post-treatment payer mode per patient
**Example:**
```python
# Source: Adapted from src/report/encounter_payer_summary.py _payer_mode_in_window() (lines 478-534)
import polars as pl
from pathlib import Path

# Read encounters and patients with last_treatment_date
enc_path = Path("clean/ENCOUNTER.parquet")
patients = df.select("PATID", "LAST_TREATMENT_DATE").filter(
    pl.col("LAST_TREATMENT_DATE").is_not_null()
)

# Join encounters, filter to post-treatment only
enc = pl.scan_parquet(enc_path).select("PATID", "ADMIT_DATE", "PAYER_TYPE_PRIMARY").collect()
joined = patients.join(enc, on="PATID", how="inner")

# Filter: ADMIT_DATE > LAST_TREATMENT_DATE
post_treatment = joined.filter(pl.col("ADMIT_DATE") > pl.col("LAST_TREATMENT_DATE"))

# Derive payer category from PAYER_TYPE_PRIMARY (reuse _collapse_payer_category logic)
post_treatment = post_treatment.with_columns(
    pl.col("PAYER_TYPE_PRIMARY").map_elements(
        lambda code: _collapse_payer_category(code),  # Reuse existing function
        return_dtype=pl.String
    ).alias("PAYER_CATEGORY")
)

# Mode (most frequent) payer per patient
mode_df = (
    post_treatment
    .group_by("PATID", "PAYER_CATEGORY")
    .agg(pl.len().alias("_n"))
    .sort("_n", descending=True)
    .group_by("PATID")
    .first()
    .select("PATID", pl.col("PAYER_CATEGORY").alias("POST_TREATMENT_PAYER"))
)
```

### Pattern 3: Handling No-Treatment Patients with N/A Row
**What:** Include patients with HAD_CHEMO=0, HAD_RADIATION=0, HAD_SCT=0 in combined table with N/A payer
**When to use:** For combined post-treatment table only
**Example:**
```python
# Source: User constraint requirement + table generation patterns
import polars as pl

# Patients with any treatment
had_any = df.filter(
    (pl.col("HAD_CHEMO") == 1) |
    (pl.col("HAD_RADIATION") == 1) |
    (pl.col("HAD_SCT") == 1)
)

# Patients with no treatment
no_treatment = df.filter(
    (pl.col("HAD_CHEMO") == 0) &
    (pl.col("HAD_RADIATION") == 0) &
    (pl.col("HAD_SCT") == 0)
)

# For combined table: count no-treatment patients separately
# Add "N/A" row to table (10 rows total: 9 payer categories + N/A)
n_no_treatment = no_treatment.height
pct_no_treatment = 100.0 * n_no_treatment / df.height

table_rows = [...existing 9 payer rows...]
table_rows.append({
    "Payer Category": "N/A (No Treatment)",
    "Post-Treatment Insurance (N)": n_no_treatment,
    "Post-Treatment Insurance (%)": pct_no_treatment,
    "Post-Treatment Insurance (N_Pct)": f"{n_no_treatment} ({pct_no_treatment:.1f}%)"
})
```

### Pattern 4: Reusing Phase 5 Table Rendering Infrastructure
**What:** Copy PNG, HTML, CSV generation functions from build_insurance_by_treatment.py with minimal modifications
**When to use:** For all output generation in Phase 6
**Example:**
```python
# Source: scripts/build_insurance_by_treatment.py _render_png() (lines 92-162), _render_html() (lines 164-272)
# Adaptation: Single column table instead of 3-column

# FROM PHASE 5:
def _render_png(table_data, title, output_path, first_label, last_label):
    # ... existing 3-column logic ...

# FOR PHASE 6 (simplified to 1 column):
def _render_png_post_treatment(table_data, title, output_path):
    """Render post-treatment payer table as PNG (single column)."""
    cellText = []
    cellColours = []

    for row in table_data:
        payer_cat = row["Payer Category"]
        post_tx = row["Post-Treatment Insurance (N_Pct)"]

        cellText.append([payer_cat, post_tx])
        row_color = PAYER_COLORS.get(payer_cat, "#FFFFFF")
        cellColours.append([row_color, row_color])

    fig, ax = plt.subplots(figsize=(8, 7))  # Narrower than 3-column tables
    ax.axis('off')

    table = ax.table(
        cellText=cellText,
        colLabels=["Payer Category", "Post-Treatment Insurance"],
        cellColours=cellColours,
        loc='center',
        cellLoc='center'
    )
    # ... rest of styling identical to Phase 5 ...
```

### Anti-Patterns to Avoid
- **Computing last_treatment_date with pl.when().then() chains:** Don't manually chain conditionals. Use `pl.max_horizontal()` which handles nulls correctly and is more readable.
- **Adding post-treatment column to encounter_payer_summary.parquet:** User explicitly wants standalone tables, not new columns in existing outputs. Keep phases separated.
- **Different color palette from Phase 5:** User wants "same visual style, colors, and layout". Must reuse exact PAYER_COLORS dict from Phase 5 (seaborn Pastel1).
- **Separate post-treatment encounter filtering in each cohort loop:** Compute once, reuse for all 4 tables to avoid redundant I/O.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Row-wise max across nullable columns | Manual comparison with null checks | `pl.max_horizontal()` | Polars native function handles null propagation correctly; avoids off-by-one bugs with when/then chains |
| Mode (most frequent) computation | Custom dict counting logic | Polars group_by + agg + sort pattern from _payer_mode_in_window | Already proven in Phase 5 pipeline; handles ties consistently (alphabetical tiebreaker) |
| Payer category mapping | New PCORnet code→category logic | Reuse `_collapse_payer_category()` from encounter_payer_summary.py | Maintains consistency with existing pipeline; already tested in test_payer_logic.py |
| Table rendering (PNG, HTML, CSV) | New rendering functions | Copy/adapt Phase 5's _render_png(), _render_html() | User explicitly requires "same visual style"; reuse ensures exact match |

**Key insight:** Phase 5 already solved table rendering, payer categorization, and mode derivation. Phase 6 is primarily about (1) computing last_treatment_date, (2) filtering encounters, and (3) applying existing patterns to new data slice. Don't reinvent; adapt proven code.

## Common Pitfalls

### Pitfall 1: Incorrect Null Handling in max() Across Treatment Dates
**What goes wrong:** Using Python max() or naive pl.max() on [LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE] returns None if ANY value is null, when logic requires max of non-null values.
**Why it happens:** Python's max() and some max implementations treat None as "propagating" (one None → result is None). User requirement is "nulls ignored" (SQL GREATEST behavior).
**How to avoid:** Use `pl.max_horizontal()` which ignores nulls by default. Returns null only if ALL inputs are null. Test with patient having only chemo (radiation/SCT nulls) → last_treatment_date should equal LAST_CHEMO_DATE.
**Warning signs:** Patients with partial treatment (e.g., chemo only) have null last_treatment_date despite having LAST_CHEMO_DATE populated.

### Pitfall 2: Forgetting "No Encounters Post-Treatment" Edge Case
**What goes wrong:** Patients who had treatment but no encounters after last_treatment_date are silently dropped from output, creating incomplete tables.
**Why it happens:** Left join after mode computation loses patients with null mode. User constraint says "Patients with no encounters after last treatment: count under 'Unknown' payer category".
**How to avoid:** After computing mode payer, do left join from all patients with non-null last_treatment_date to mode results. Fill null mode with "Unknown" category. Verify row count matches (patients with treatment) before aggregating to table.
**Warning signs:** Cohort table N is smaller than HAD_CHEMO=1 count; some patients mysteriously missing from output.

### Pitfall 3: N/A Row Color Mismatch
**What goes wrong:** N/A row in combined table gets arbitrary color or crashes PNG rendering because "N/A (No Treatment)" not in PAYER_COLORS dict.
**Why it happens:** Phase 5's PAYER_COLORS only maps 9 standard payer categories. N/A is new category for Phase 6.
**How to avoid:** Add PAYER_COLORS["N/A (No Treatment)"] = "#D3D3D3" (gray, distinct from other categories). Or handle N/A specially in cell color assignment with fallback. User discretion on exact color/placement.
**Warning signs:** KeyError when rendering combined table PNG; or N/A row renders with white/transparent background.

### Pitfall 4: Including Pre-Treatment Encounters in Mode Calculation
**What goes wrong:** Mode computation uses all encounters instead of filtering ADMIT_DATE > LAST_TREATMENT_DATE, resulting in wrong post-treatment payer.
**Why it happens:** Easy to forget filter step when adapting _payer_mode_in_window pattern (which filters by date window).
**How to avoid:** Explicitly filter joined encounters with `pl.col("ADMIT_DATE") > pl.col("LAST_TREATMENT_DATE")` BEFORE group_by for mode. Add assertion that filtered encounter count ≤ total encounter count as sanity check.
**Warning signs:** Post-treatment payer matches primary payer exactly for most patients (suspicious — should differ if payer changed post-treatment).

### Pitfall 5: Inconsistent Cohort Definitions Between Phase 5 and Phase 6
**What goes wrong:** Phase 6 chemo cohort uses HAD_CHEMO=1 & LAST_CHEMO_DATE is not null, while Phase 5 used HAD_CHEMO=1 only. Cohort sizes differ between reports.
**Why it happens:** Phase 6 requires last_treatment_date for filtering, tempting to add extra null check. But user constraint says cohorts should match Phase 5.
**How to avoid:** Use identical cohort filters as Phase 5: HAD_CHEMO=1, HAD_RADIATION=1, HAD_SCT=1 (no additional date null checks). Patients in cohort but with null last_treatment_date get post-treatment payer = "Unknown" (no encounters after treatment).
**Warning signs:** Cohort N in Phase 6 tables is smaller than Phase 5 tables for same treatment type.

## Code Examples

Verified patterns from project code and Polars documentation:

### Computing Last Treatment Date with max_horizontal
```python
# Source: Polars 1.38.1 max_horizontal() docs
# https://docs.pola.rs/api/python/stable/reference/expressions/api/polars.max_horizontal.html
import polars as pl

df = pl.read_parquet("derived/encounter_payer_summary.parquet")

# Compute last treatment date (nulls ignored automatically)
df = df.with_columns(
    pl.max_horizontal(
        "LAST_CHEMO_DATE",
        "LAST_RADIATION_DATE",
        "LAST_SCT_DATE"
    ).alias("LAST_TREATMENT_DATE")
)

# Add flag for "had any treatment"
df = df.with_columns(
    ((pl.col("HAD_CHEMO") == 1) |
     (pl.col("HAD_RADIATION") == 1) |
     (pl.col("HAD_SCT") == 1)
    ).cast(pl.Int8).alias("HAD_ANY_TREATMENT")
)
```

### Post-Treatment Payer Mode Derivation
```python
# Source: Adapted from src/report/encounter_payer_summary.py _payer_mode_in_window
import polars as pl
from pathlib import Path
from src.report.encounter_payer_summary import (
    _collapse_payer_category,
    _payer_category_from_effective_and_dual,
    _effective_payer_and_dual_exprs,
)

def compute_post_treatment_payer(
    enc_path: Path,
    patients: pl.DataFrame,  # Must have PATID and LAST_TREATMENT_DATE columns
) -> pl.DataFrame:
    """Compute mode payer category from encounters after LAST_TREATMENT_DATE.

    Returns DataFrame with PATID and POST_TREATMENT_PAYER columns.
    Patients with no post-treatment encounters get POST_TREATMENT_PAYER = "Unknown".
    """
    enc_schema = pl.read_parquet_schema(enc_path)
    has_secondary = "PAYER_TYPE_SECONDARY" in enc_schema.names()

    enc_cols = ["PATID", "ADMIT_DATE", "PAYER_TYPE_PRIMARY"]
    if has_secondary:
        enc_cols.append("PAYER_TYPE_SECONDARY")

    # Load encounters with effective payer logic
    eff_expr, valid_expr, dual_expr = _effective_payer_and_dual_exprs(has_secondary)
    enc = (
        pl.scan_parquet(enc_path)
        .with_columns(pl.col("PATID").cast(pl.String))
        .filter(pl.col("PATID").is_in(patients["PATID"].implode()))
        .select(enc_cols)
        .with_columns([eff_expr, valid_expr, dual_expr])
        .select("PATID", "ADMIT_DATE", "effective_payer", "dual_eligible", "_valid")
        .collect()
    )

    # Join with patients, filter to post-treatment encounters
    joined = patients.select("PATID", "LAST_TREATMENT_DATE").join(enc, on="PATID", how="inner")
    post_treatment = joined.filter(
        (pl.col("ADMIT_DATE") > pl.col("LAST_TREATMENT_DATE")) &
        pl.col("_valid")  # Only valid payers count
    )

    if post_treatment.is_empty():
        # No post-treatment encounters for anyone → all get "Unknown"
        return patients.select("PATID").with_columns(
            pl.lit("Unknown").alias("POST_TREATMENT_PAYER")
        )

    # Derive payer category from effective_payer and dual_eligible
    post_treatment = post_treatment.with_columns(
        pl.struct(["effective_payer", "dual_eligible"])
        .map_elements(
            lambda row: _payer_category_from_effective_and_dual(
                row["effective_payer"],
                row.get("dual_eligible", 0) or 0
            ),
            return_dtype=pl.String
        )
        .alias("PAYER_CATEGORY")
    )

    # Mode: most frequent payer category per patient
    mode_df = (
        post_treatment
        .group_by("PATID", "PAYER_CATEGORY")
        .agg(pl.len().alias("_n"))
        .sort("_n", descending=True)
        .group_by("PATID")
        .first()
        .select("PATID", pl.col("PAYER_CATEGORY").alias("POST_TREATMENT_PAYER"))
    )

    # Left join to preserve patients with no post-treatment encounters
    return (
        patients.select("PATID")
        .join(mode_df, on="PATID", how="left")
        .with_columns(
            pl.col("POST_TREATMENT_PAYER").fill_null("Unknown")
        )
    )
```

### Building Single-Column Table with N/A Row
```python
# Source: Adapted from scripts/build_insurance_by_treatment.py _build_table() (lines 289-373)
import polars as pl

def build_post_treatment_table(
    df: pl.DataFrame,
    post_treatment_col: str,
    cohort_label: str,
    include_no_treatment: bool = False,  # True for combined table only
) -> tuple[list[dict], int]:
    """Build post-treatment summary table with 9 (or 10 if N/A) payer rows and 1 column.

    Args:
        df: Filtered cohort DataFrame (e.g., HAD_CHEMO==1 or all patients)
        post_treatment_col: Column name for post-treatment payer (e.g., "POST_TREATMENT_PAYER")
        cohort_label: Label for cohort (e.g., "Post-Treatment: Chemotherapy")
        include_no_treatment: If True, add N/A row for patients with no treatment

    Returns:
        Tuple of (list of row dicts, cohort size)
    """
    cohort_size = df.height
    if cohort_size == 0:
        # Return empty rows
        rows = []
        for cat in PAYER_CATEGORY_ORDER:
            rows.append({
                "Payer Category": cat,
                "Post-Treatment Insurance (N)": 0,
                "Post-Treatment Insurance (%)": 0.0,
                "Post-Treatment Insurance (N_Pct)": "0 (0.0%)",
            })
        return rows, cohort_size

    # Normalize nulls to "Unknown"
    df = df.with_columns(
        pl.col(post_treatment_col).fill_null("Unknown").alias("_payer_norm")
    )

    # Count by category
    counts = (
        df.group_by("_payer_norm")
        .agg(pl.len().alias("N"))
        .rename({"_payer_norm": "Category"})
    )
    count_map = {row["Category"]: row["N"] for row in counts.iter_rows(named=True)}

    # Build rows in standard order
    rows = []
    for cat in PAYER_CATEGORY_ORDER:
        n = count_map.get(cat, 0)
        pct = 100.0 * n / cohort_size if cohort_size > 0 else 0.0
        rows.append({
            "Payer Category": cat,
            "Post-Treatment Insurance (N)": n,
            "Post-Treatment Insurance (%)": pct,
            "Post-Treatment Insurance (N_Pct)": f"{n} ({pct:.1f}%)",
        })

    # Add N/A row if requested (combined table only)
    if include_no_treatment:
        n_no_tx = count_map.get("N/A (No Treatment)", 0)
        pct_no_tx = 100.0 * n_no_tx / cohort_size if cohort_size > 0 else 0.0
        rows.append({
            "Payer Category": "N/A (No Treatment)",
            "Post-Treatment Insurance (N)": n_no_tx,
            "Post-Treatment Insurance (%)": pct_no_tx,
            "Post-Treatment Insurance (N_Pct)": f"{n_no_tx} ({pct_no_tx:.1f}%)",
        })

    return rows, cohort_size
```

### Reusing Phase 5 PNG Rendering with Single Column
```python
# Source: scripts/build_insurance_by_treatment.py _render_png() adapted for 1 column
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors
import seaborn as sns
from pathlib import Path

# Reuse Phase 5 color palette
PAYER_CATEGORY_ORDER = [
    "Medicare", "Medicaid", "Dual eligible", "Private",
    "Other government", "Self-pay", "Other", "Unavailable", "Unknown"
]
_palette = sns.color_palette("Pastel1", n_colors=9)
PAYER_COLORS = {
    category: matplotlib.colors.to_hex(color)
    for category, color in zip(PAYER_CATEGORY_ORDER, _palette)
}
PAYER_COLORS["N/A (No Treatment)"] = "#D3D3D3"  # Gray for N/A row
HEADER_COLOR = "#2C5AA0"

def render_post_treatment_png(
    table_data: list[dict],
    title: str,
    output_path: Path,
) -> None:
    """Render post-treatment payer table as PNG (single column)."""
    cellText = []
    cellColours = []

    for row in table_data:
        payer_cat = row["Payer Category"]
        post_tx = row["Post-Treatment Insurance (N_Pct)"]

        cellText.append([payer_cat, post_tx])
        row_color = PAYER_COLORS.get(payer_cat, "#FFFFFF")
        cellColours.append([row_color, row_color])

    # Single-column table: narrower figure
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.axis('off')

    table = ax.table(
        cellText=cellText,
        colLabels=["Payer Category", "Post-Treatment Insurance"],
        cellColours=cellColours,
        loc='center',
        cellLoc='center'
    )

    # Style header cells
    for col_idx in range(2):
        cell = table[(0, col_idx)]
        cell.set_facecolor(HEADER_COLOR)
        cell.set_text_props(weight='bold', color='white')

    # Left-align first column
    for row_idx in range(len(table_data)):
        cell = table[(row_idx + 1, 0)]
        cell.set_text_props(ha='left')

    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.2, 2.0)

    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.95)
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual max() with null handling | `pl.max_horizontal()` for row-wise max | Polars 0.19+ (2024) | Built-in null handling; simpler code, fewer bugs |
| Separate post-treatment analysis in SAS/R | Integrated Polars pipeline with treatment dates | 2024-2025 | Reproducible Python workflow; leverages existing infrastructure |
| Time-windowed post-treatment (±30 days) | Unbounded post-treatment (all encounters after last treatment) | Phase 6 design | Captures long-term survivorship care patterns, not just immediate post-treatment |

**Deprecated/outdated:**
- **Computing last_treatment_date with pl.when().then() chains:** Verbose and error-prone. Replaced by `pl.max_horizontal()`.
- **Adding post-treatment column to patient_level.parquet:** Would bloat the main summary table. Phase 6 keeps post-treatment analysis in separate reports.

## Open Questions

1. **Should overview table include patients with no treatment at all?**
   - What we know: User constraint says "Patients with no treatment at all (HAD_CHEMO=0, HAD_RADIATION=0, HAD_SCT=0): include in combined table with payer marked as N/A"
   - What's unclear: Does "combined table" mean the combined post-treatment table (all treatment types) or a separate all-patients overview?
   - Recommendation: Interpret "combined table" as the post-treatment table for all patients who had ANY treatment (HAD_ANY_TREATMENT=1), PLUS a separate N/A row counting patients with NO treatment. This matches "4 tables total" constraint (combined post-treatment, chemo, radiation, SCT).

2. **How to compute post-treatment payer: inline in script or add column to encounter_payer_summary.parquet?**
   - What we know: Claude's discretion per user constraints. Adding to encounter_payer_summary.py would make it available for future analyses. Computing inline keeps Phase 6 script self-contained.
   - What's unclear: Is post-treatment payer a one-off analysis or will it be reused in future phases?
   - Recommendation: Compute inline in Phase 6 script. Rationale: (1) Single-use analysis per current requirements, (2) Avoids slowing pipeline for all runs, (3) encounter_payer_summary.py already complex (894 lines) — adding more would reduce maintainability. If future phases need it, refactor then.

3. **What exact color and placement for N/A row in combined table?**
   - What we know: User says Claude's discretion on "How to handle the N/A row visually (color, placement)"
   - What's unclear: Should N/A row be at top (before payer categories), bottom (after Unknown), or separate section?
   - Recommendation: Place N/A row at bottom (after Unknown) with gray color (#D3D3D3). Rationale: N/A is conceptually separate from payer categories (represents absence of treatment, not insurance type). Bottom placement keeps 9 payer rows together, visually distinct from N/A.

4. **Should per-cohort tables (chemo, radiation, SCT) include patients from that cohort who had no post-treatment encounters?**
   - What we know: User constraint says "Patients with no encounters after last treatment: count under 'Unknown' payer category"
   - What's unclear: Does this apply to per-cohort tables or only combined table?
   - Recommendation: Apply to ALL tables. Per-cohort chemo table = all HAD_CHEMO=1 patients; those with no post-treatment encounters get POST_TREATMENT_PAYER="Unknown". This ensures cohort N matches Phase 5 tables for consistency.

## Sources

### Primary (HIGH confidence)
- Polars max_horizontal() documentation: https://docs.pola.rs/api/python/stable/reference/expressions/api/polars.max_horizontal.html
- Project source code: `scripts/build_insurance_by_treatment.py`, `src/report/encounter_payer_summary.py` (lines 268-355 for treatment date logic, 478-534 for mode payer derivation)
- Phase 5 RESEARCH.md and CONTEXT.md: `.planning/phases/05-insurance-by-treatment-analysis/`
- Phase 6 CONTEXT.md: User decisions from `/gsd:discuss-phase`

### Secondary (MEDIUM confidence)
- Polars conditional expressions guide: https://docs.pola.rs/user-guide/expressions/conditionals/
- Matplotlib table styling gallery: https://matplotlib.org/stable/gallery/misc/table_demo.html

### Tertiary (LOW confidence)
None — research based entirely on verified project code and official Polars documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already installed and proven in Phase 5
- Architecture: HIGH - Direct adaptation of Phase 5 patterns; max_horizontal() is well-documented Polars feature
- Pitfalls: HIGH - Derived from Phase 5 implementation experience and Polars null handling edge cases
- Edge case handling (N/A row, no encounters): MEDIUM - User constraint provides requirements but visual implementation details left to discretion

**Research date:** 2026-03-19
**Valid until:** 60 days (stable domain - table rendering and Polars date operations are mature)
