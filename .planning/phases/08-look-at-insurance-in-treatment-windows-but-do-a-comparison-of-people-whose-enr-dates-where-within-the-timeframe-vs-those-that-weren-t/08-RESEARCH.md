# Phase 8: Insurance in Treatment Windows — ENR Date Comparison - Research

**Researched:** 2026-03-24
**Domain:** Enrollment coverage validation and insurance stratification analysis
**Confidence:** HIGH

## Summary

Phase 8 compares insurance coverage patterns between patients whose ENROLLMENT periods fully cover the ±30 day treatment window vs those whose enrollment doesn't. This addresses a data quality question: are payer classifications at treatment reliable (enrollment covers window) or potentially missing data (enrollment gaps)?

The phase produces side-by-side comparison tables for each treatment type (DX, Chemo First/Last, Radiation First/Last, SCT First/Last) and a diagnostic breakdown of "Unknown" post-treatment payer patients from Phase 6. All outputs in PNG, CSV/markdown, HTML, and PowerPoint.

**Primary recommendation:** Reuse existing ±30 day window logic and enrollment overlap checking patterns from `encounter_payer_summary.py` and `harmonize.py`. The key technical challenge is checking if union of multiple enrollment periods spans the full ±60 day window (treatment_date - 30 to treatment_date + 30). Phase 5/6/7 patterns provide all rendering and presentation infrastructure.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Treatment window definition:**
- **D-01:** Reuse existing ±30 day windows from the pipeline (PAYER_AT_TREATMENT_WINDOW_DAYS=30)
- **D-02:** 7 windows total: FIRST_HL_DX_DATE, FIRST_CHEMO_DATE, LAST_CHEMO_DATE, FIRST_RADIATION_DATE, LAST_RADIATION_DATE, FIRST_SCT_DATE, LAST_SCT_DATE
- **D-03:** Window = [treatment_date - 30 days, treatment_date + 30 days]

**ENR overlap logic:**
- **D-04:** Full coverage required — the union of a patient's ENROLLMENT periods must span the entire ±30 day window for the patient to count as "enrolled covers window"
- **D-05:** Multiple enrollment periods: combined coverage OK (adjacent/overlapping ENR records can together cover the window)
- **D-06:** Patients with no ENROLLMENT records at all count as "ENR does not cover window"

**Comparison table structure:**
- **D-07:** Side-by-side columns: "ENR Covers Window N (%)" | "ENR Does Not Cover Window N (%)" per table
- **D-08:** 4 tables total: DX table (2 columns), Chemo table (4 columns: first covers/doesn't + last covers/doesn't), Radiation table (4 columns), SCT table (4 columns)
- **D-09:** N per column in header (each column shows its own group size)
- **D-10:** Payer values from existing pipeline: PAYER_CATEGORY_AT_FIRST_* and PAYER_CATEGORY_AT_LAST_* columns from encounter_payer_summary.parquet
- **D-11:** Patients with null PAYER_CATEGORY_AT_* shown as "N/A" row (not under Unknown)
- **D-12:** Same 9 payer categories + N/A row where applicable

**Cohort scoping:**
- **D-13:** DX table: all HL patients with non-null FIRST_HL_DX_DATE
- **D-14:** Treatment tables: treatment-specific cohorts (HAD_CHEMO=1 for chemo, HAD_RADIATION=1 for radiation, HAD_SCT=1 for SCT) — same as Phase 5
- **D-15:** Exclude patients with null treatment dates from that treatment type's table (e.g., HAD_CHEMO=1 but FIRST_CHEMO_DATE is null = excluded from chemo table)

**Unknown post-treatment encounter analysis:**
- **D-16:** Additional diagnostic analysis: for patients with "Unknown" post-treatment payer from Phase 6 logic, show a count breakdown of encounters after last treatment
- **D-17:** Breakdown table: how many Unknown-payer patients have 0 encounters, 1-5, 6+, etc. after last treatment date — reveals whether Unknown = no data vs Unknown = encounters with no payer info
- **D-18:** Same 3-format output (PNG, CSV/markdown, HTML) and included in PowerPoint

**Output and presentation:**
- **D-19:** All tables output in 3 formats: PNG (color-coded, seaborn Pastel1 palette), CSV + markdown, styled HTML
- **D-20:** Same visual style as Phases 5/6 (same colors, fonts, layout)
- **D-21:** No HIPAA small-cell suppression (internal working tables)
- **D-22:** Add all tables as slides to the existing PowerPoint presentation (extend Phase 7 script or rebuild)
- **D-23:** Report directory: reports/insurance_enr_comparison/

### Claude's Discretion

- Column header wording for enrolled/not-enrolled groups
- How to organize the 4+1 tables in the PowerPoint (section dividers, slide order)
- Exact encounter count bins for the Unknown breakdown table (0, 1-5, 6+ or finer)
- Whether to extend build_insurance_presentation.py or create new script for PowerPoint additions
- Script naming (new standalone script or extension of existing Phase 5/6 scripts)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 0.20+ | DataFrame operations and date interval logic | Already used across pipeline, lazy evaluation for enrollment joins |
| python-pptx | 0.6.21 | PowerPoint generation with native tables | Phase 7 standard, UF branding already implemented |
| matplotlib | 3.7+ | PNG table rendering | Phase 5/6 standard for color-coded tables |
| seaborn | 0.12+ | Pastel1 color palette for payer categories | Phase 5/6 standard, consistent visual style |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib | stdlib | Path handling for HPC environments | Already used in all scripts |

**Installation:**
No new dependencies — all libraries already installed per Phase 5/6/7 requirements.

**Version verification:**
All packages verified in existing environment from Phases 5-7. No version changes needed.

## Architecture Patterns

### Recommended Project Structure
```
scripts/
├── build_insurance_enr_comparison.py    # Main Phase 8 script
reports/
└── insurance_enr_comparison/            # Phase 8 outputs
    ├── dx_enr_comparison.csv
    ├── dx_enr_comparison.png
    ├── dx_enr_comparison.html
    ├── chemo_first_enr_comparison.csv
    ├── chemo_last_enr_comparison.csv
    ├── radiation_first_enr_comparison.csv
    ├── radiation_last_enr_comparison.csv
    ├── sct_first_enr_comparison.csv
    ├── sct_last_enr_comparison.csv
    ├── unknown_post_tx_encounter_breakdown.csv
    ├── unknown_post_tx_encounter_breakdown.png
    ├── unknown_post_tx_encounter_breakdown.html
    └── README.md
```

### Pattern 1: Enrollment Coverage Checking (Union of Periods)

**What:** Check if union of a patient's ENROLLMENT periods fully covers a date window

**When to use:** For D-04 requirement — determine if patient's enrollment gaps leave any part of the ±30 day window uncovered

**Example:**
```python
# Source: Adapted from src/clean/harmonize.py flag_encounters_outside_enrollment pattern
def _check_enrollment_covers_window(
    patient_id: str,
    window_start: date,
    window_end: date,
    enrollment_df: pl.DataFrame,
) -> bool:
    """Check if union of enrollment periods fully covers [window_start, window_end].

    Returns True if every day in [window_start, window_end] is covered by at least
    one enrollment period. Adjacent/overlapping periods combine to cover gaps.

    Algorithm:
    1. Filter to patient's enrollment periods
    2. Sort by ENR_START_DATE
    3. Walk through sorted periods, tracking latest covered date
    4. If any gap exists before window_end, return False
    5. If latest covered date >= window_end, return True
    """
    patient_enr = enrollment_df.filter(pl.col("ID") == patient_id).sort("ENR_START_DATE")

    if patient_enr.is_empty():
        return False  # No enrollment records

    covered_until = window_start - timedelta(days=1)  # Start before window

    for row in patient_enr.iter_rows(named=True):
        start = row["ENR_START_DATE"]
        end = row["ENR_END_DATE"]

        if start is None or end is None:
            continue

        # If this period starts after our coverage gap, window has uncovered days
        if start > covered_until + timedelta(days=1):
            return False

        # Extend coverage to this period's end date
        covered_until = max(covered_until, end)

        # If we've covered past window_end, we're done
        if covered_until >= window_end:
            return True

    # After all periods, check if we covered the full window
    return covered_until >= window_end
```

**Optimization for Polars:**
```python
# Vectorized approach for all patients at once
def _flag_enrollment_covers_window(
    patients_with_dates: pl.DataFrame,  # Columns: ID, treatment_date
    enrollment_df: pl.DataFrame,        # Columns: ID, ENR_START_DATE, ENR_END_DATE
    window_days: int = 30,
) -> pl.DataFrame:
    """Add column ENR_COVERS_WINDOW (1/0) for each patient-treatment pair.

    Returns DataFrame with ID, treatment_date, ENR_COVERS_WINDOW columns.
    """
    # Compute window bounds
    patients = patients_with_dates.with_columns([
        (pl.col("treatment_date") - pl.duration(days=window_days)).alias("window_start"),
        (pl.col("treatment_date") + pl.duration(days=window_days)).alias("window_end"),
    ])

    # Join to enrollment, check each enrollment period vs window
    joined = patients.join(enrollment_df, on="ID", how="left")

    # Flag periods that overlap with window
    joined = joined.with_columns(
        (
            (pl.col("ENR_START_DATE") <= pl.col("window_end")) &
            (pl.col("ENR_END_DATE") >= pl.col("window_start"))
        ).alias("_period_overlaps")
    )

    # NOTE: This flags OVERLAP but not FULL COVERAGE. Need gap detection logic
    # for true "union covers window" check. Consider using Python loop for
    # correctness at cost of performance, or implement interval merging in Polars.

    # For production: use per-patient Python function with apply() or iter_rows()
    # to ensure correct union logic per D-04/D-05 requirements.
```

### Pattern 2: Side-by-Side Comparison Tables

**What:** Build table with paired columns showing same payer categories for two patient groups

**When to use:** D-07 requirement — show "ENR Covers" vs "ENR Does Not Cover" side-by-side

**Example:**
```python
# Source: Adapted from scripts/build_insurance_by_treatment.py _build_table pattern
def _build_comparison_table(
    df: pl.DataFrame,
    payer_col: str,              # e.g., "PAYER_CATEGORY_AT_FIRST_CHEMO"
    enr_flag_col: str,           # "ENR_COVERS_FIRST_CHEMO_WINDOW"
    first_label: str,            # "First Chemo"
) -> tuple[list[dict], int, int]:
    """Build side-by-side comparison table with ENR coverage split.

    Returns:
        Tuple of (list of row dicts, n_covered, n_not_covered)
    """
    df_covered = df.filter(pl.col(enr_flag_col) == 1)
    df_not_covered = df.filter(pl.col(enr_flag_col) == 0)

    n_covered = df_covered.height
    n_not_covered = df_not_covered.height

    # Count payer categories in each group
    def _count_payers(subset_df, label_suffix):
        # Normalize nulls to "N/A"
        normalized = subset_df.with_columns(
            pl.when(pl.col(payer_col).is_null())
            .then(pl.lit("N/A"))
            .when(pl.col(payer_col) == "No payment / Self-pay")
            .then(pl.lit("Self-pay"))
            .otherwise(pl.col(payer_col))
            .alias("_payer_norm")
        )
        counts = normalized.group_by("_payer_norm").agg(pl.len().alias("N"))
        return {row["_payer_norm"]: row["N"] for row in counts.iter_rows(named=True)}

    covered_map = _count_payers(df_covered, "covered")
    not_covered_map = _count_payers(df_not_covered, "not_covered")

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
            f"ENR Covers Window (N={n_covered}) (N)": n_cov,
            f"ENR Covers Window (N={n_covered}) (%)": pct_cov,
            f"ENR Covers Window (N={n_covered}) (N_Pct)": f"{n_cov} ({pct_cov:.1f}%)",
            f"ENR Does Not Cover (N={n_not_covered}) (N)": n_not,
            f"ENR Does Not Cover (N={n_not_covered}) (%)": pct_not,
            f"ENR Does Not Cover (N={n_not_covered}) (N_Pct)": f"{n_not} ({pct_not:.1f}%)",
        })

    return rows, n_covered, n_not_covered
```

### Pattern 3: Unknown Post-Treatment Encounter Breakdown

**What:** Count how many post-treatment encounters Unknown-payer patients have (diagnostic table)

**When to use:** D-16/D-17 requirement — diagnose whether "Unknown" means no encounters or encounters without payer info

**Example:**
```python
# Source: New pattern combining Phase 6 post-treatment logic with encounter counting
def _build_unknown_encounter_breakdown(
    enc_payer_summary: pl.DataFrame,
    enc_path: Path,
) -> list[dict]:
    """Build diagnostic table: Unknown post-tx payer patients grouped by encounter count.

    Returns list of row dicts:
        {"Encounter Count Bin": "0", "N Patients": 50, "% of Unknown": 25.0}
        {"Encounter Count Bin": "1-5", "N Patients": 100, "% of Unknown": 50.0}
        {"Encounter Count Bin": "6+", "N Patients": 50, "% of Unknown": 25.0}
    """
    # Step 1: Identify patients with Unknown post-treatment payer (from Phase 6 logic)
    # Recompute post-treatment payer or read from Phase 6 output
    # Assume we have column POST_TREATMENT_PAYER

    unknown_patients = enc_payer_summary.filter(
        pl.col("POST_TREATMENT_PAYER") == "Unknown"
    )

    n_unknown = unknown_patients.height

    if n_unknown == 0:
        return [{"Encounter Count Bin": "N/A", "N Patients": 0, "% of Unknown": 0.0}]

    # Step 2: Compute LAST_TREATMENT_DATE (max of LAST_CHEMO/RADIATION/SCT)
    unknown_patients = unknown_patients.with_columns(
        pl.max_horizontal("LAST_CHEMO_DATE", "LAST_RADIATION_DATE", "LAST_SCT_DATE")
        .alias("LAST_TREATMENT_DATE")
    )

    # Step 3: Count post-treatment encounters per patient
    enc = pl.read_parquet(enc_path).filter(
        pl.col("ID").is_in(unknown_patients["ID"].implode())
    )

    joined = unknown_patients.select("ID", "LAST_TREATMENT_DATE").join(
        enc.select("ID", "ADMIT_DATE"), on="ID", how="left"
    )

    post_tx_enc = joined.filter(
        pl.col("ADMIT_DATE") > pl.col("LAST_TREATMENT_DATE")
    )

    enc_counts = post_tx_enc.group_by("ID").agg(
        pl.len().alias("N_POST_TX_ENCOUNTERS")
    )

    # Step 4: Merge back to unknown_patients, fill nulls with 0 (no encounters)
    unknown_with_counts = unknown_patients.join(
        enc_counts, on="ID", how="left"
    ).with_columns(
        pl.col("N_POST_TX_ENCOUNTERS").fill_null(0)
    )

    # Step 5: Bin encounter counts (0, 1-5, 6-10, 11-20, 21+)
    unknown_with_counts = unknown_with_counts.with_columns(
        pl.when(pl.col("N_POST_TX_ENCOUNTERS") == 0).then(pl.lit("0"))
        .when(pl.col("N_POST_TX_ENCOUNTERS") <= 5).then(pl.lit("1-5"))
        .when(pl.col("N_POST_TX_ENCOUNTERS") <= 10).then(pl.lit("6-10"))
        .when(pl.col("N_POST_TX_ENCOUNTERS") <= 20).then(pl.lit("11-20"))
        .otherwise(pl.lit("21+"))
        .alias("_bin")
    )

    # Step 6: Count patients per bin
    bin_counts = unknown_with_counts.group_by("_bin").agg(
        pl.len().alias("N_Patients")
    )

    # Step 7: Build rows with percentages
    rows = []
    bin_order = ["0", "1-5", "6-10", "11-20", "21+"]
    bin_map = {row["_bin"]: row["N_Patients"] for row in bin_counts.iter_rows(named=True)}

    for bin_label in bin_order:
        n = bin_map.get(bin_label, 0)
        pct = 100.0 * n / n_unknown
        rows.append({
            "Encounter Count Bin": bin_label,
            "N Patients": n,
            "% of Unknown": pct,
            "N_Pct": f"{n} ({pct:.1f}%)",
        })

    return rows
```

### Anti-Patterns to Avoid

- **Anti-pattern: Checking single enrollment period instead of union:** Phase 8 requires checking if union of ALL enrollment periods covers window (D-04/D-05), not just checking if ANY single period covers it. A patient with two adjacent periods that together cover the window should count as "covered".

- **Anti-pattern: Including patients with null treatment dates:** D-15 requires excluding HAD_CHEMO=1 patients with null FIRST_CHEMO_DATE from the chemo table. Don't show them as "N/A" — exclude them entirely to avoid confusion.

- **Anti-pattern: Recomputing payer categories from scratch:** D-10 requires using existing PAYER_CATEGORY_AT_* columns from encounter_payer_summary.parquet, not recalculating payer mode in ±30 day windows. Reuse Phase 5/6 outputs.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Date interval overlap checking | Custom date range intersection logic | Polars duration and comparison operators with sorting | Date arithmetic has edge cases (DST, leap years, null handling). Polars handles these correctly. |
| Enrollment period union | Recursive merge algorithm | Sort by start date, walk through with "covered_until" tracker | Union of intervals is well-studied problem. Sort-and-sweep algorithm is O(n log n) and handles all cases. |
| PNG table rendering | Custom matplotlib table layout | Reuse Phase 5 `_render_png()` function | Color palette, fonts, sizing already tuned. Phase 8 needs side-by-side columns but same visual style. |
| PowerPoint table creation | Manual shape/cell formatting | Reuse Phase 7 `_add_table_slide()` function | UF branding, alternating row colors, native tables already implemented. Extend for wider tables. |

**Key insight:** Phase 8 is primarily a data stratification problem (split patients by enrollment coverage) + table rendering problem (side-by-side columns). All rendering infrastructure exists from Phases 5-7. The new logic is enrollment union checking, which requires careful date interval handling but follows established Polars patterns.

## Runtime State Inventory

> Phase 8 is a greenfield analysis phase — no rename/refactor/migration involved. Omit Runtime State Inventory section entirely per instructions.

## Common Pitfalls

### Pitfall 1: Incorrect Enrollment Union Logic

**What goes wrong:** Checking if ANY enrollment period overlaps the window instead of checking if UNION of periods fully COVERS the window. This incorrectly flags patients with enrollment gaps as "covered".

**Why it happens:** Naive approach: join patients to enrollment, check if `(ENR_START <= window_end) AND (ENR_END >= window_start)`, aggregate with `max()`. This detects overlap but not full coverage. A patient with two 20-day periods separated by a 30-day gap would be flagged as "covered" even though they have a gap.

**How to avoid:**
1. Sort enrollment periods by start date per patient
2. Walk through periods, tracking "covered_until" date
3. If next period starts after `covered_until + 1 day`, there's a gap → return False
4. Extend `covered_until` to max of current end date
5. After all periods, check if `covered_until >= window_end`

**Warning signs:**
- High proportion of patients flagged as "ENR covers window" (>90%) when manual spot-checks show enrollment gaps
- Validation query: For random sample of "ENR covers" patients, manually verify all days in [treatment_date - 30, treatment_date + 30] have at least one enrollment period

### Pitfall 2: Off-by-One Errors in Window Bounds

**What goes wrong:** Window defined as [treatment_date - 30, treatment_date + 29] instead of [treatment_date - 30, treatment_date + 30]. Results in 60-day window instead of 61-day window (treatment date itself + 30 days before + 30 days after).

**Why it happens:** Confusion about whether "±30 days" means 30 days on each side (total 61 days including center) or 30 days total (15 on each side).

**How to avoid:**
- Document in code comments: "±30 days = 61-day window: [treatment_date - 30, treatment_date + 30]"
- Use Polars duration: `pl.col("treatment_date") - pl.duration(days=30)` (unambiguous)
- Test case: Treatment date 2020-01-31, window should be 2020-01-01 to 2020-03-01 (61 days)

**Warning signs:**
- Window sizes don't match Phase 5's ±30 day payer-at-treatment windows
- Test with single-day enrollment period at treatment date — should count as "not covered" because it doesn't span full ±30 days

### Pitfall 3: Null Treatment Dates Breaking Cohort Filters

**What goes wrong:** Including patients with `HAD_CHEMO=1` but `FIRST_CHEMO_DATE=null` in the chemo table, leading to null window bounds and downstream errors.

**Why it happens:** Treatment flags (HAD_CHEMO) derived from multiple sources (tumor registry, procedures, prescribing). If flag is set but date columns are null, patient gets included in cohort but has no valid treatment date.

**How to avoid:**
- Filter: `df.filter((pl.col("HAD_CHEMO") == 1) & pl.col("FIRST_CHEMO_DATE").is_not_null())`
- Apply to ALL treatment tables (chemo first/last, radiation first/last, SCT first/last)
- Document in RESEARCH.md: D-15 requires null date exclusion

**Warning signs:**
- Polars errors about null dates in date arithmetic (window bounds computation)
- Cohort size drops significantly after adding `.is_not_null()` filter (indicates data quality issue in treatment date derivation)

### Pitfall 4: Confusing "Unknown" Payer with "N/A" (Null Payer)

**What goes wrong:** Treating null PAYER_CATEGORY_AT_* values as "Unknown" category instead of "N/A" category. D-11 requires separate "N/A" row for null payer values.

**Why it happens:** Phase 5/6 scripts normalize null payers to "Unknown". Phase 8 needs to distinguish null (patient never had a payer recorded at that treatment) from "Unknown" (patient had encounters but payer was Unknown category).

**How to avoid:**
```python
# Normalize nulls to "N/A", not "Unknown"
df = df.with_columns(
    pl.when(pl.col(payer_col).is_null())
    .then(pl.lit("N/A"))
    .when(pl.col(payer_col) == "No payment / Self-pay")
    .then(pl.lit("Self-pay"))
    .otherwise(pl.col(payer_col))
    .alias("_payer_norm")
)
```
- Use PAYER_CATEGORY_ORDER + ["N/A"] for row ordering
- Document: "N/A" means no payer recorded at treatment date (no encounters in ±30 day window), "Unknown" means encounters exist but payer category is Unknown

**Warning signs:**
- No "N/A" row appears in tables even though some patients have null PAYER_CATEGORY_AT_* values
- "Unknown" row has unexpectedly high counts (combining true Unknown + null values)

## Code Examples

Verified patterns from official sources:

### Enrollment Period Union Coverage Check
```python
# Source: Adapted from src/clean/harmonize.py flag_encounters_outside_enrollment
# Official pattern: many-to-many join with lazy evaluation, group_by aggregation
def _check_enrollment_covers_full_window(
    patients_with_dates: pl.DataFrame,  # Columns: ID, treatment_date
    enrollment_df: pl.DataFrame,        # Columns: ID, ENR_START_DATE, ENR_END_DATE
    window_days: int = 30,
) -> pl.DataFrame:
    """Check if union of enrollment periods fully covers ±window_days around treatment_date.

    Returns DataFrame with ID, treatment_date, ENR_COVERS_WINDOW (Int8: 1/0).

    Algorithm: Per-patient Python loop for correctness. Polars vectorization would
    require complex interval merging; use Python for maintainability.
    """
    # Compute window bounds
    patients = patients_with_dates.with_columns([
        (pl.col("treatment_date") - pl.duration(days=window_days)).alias("window_start"),
        (pl.col("treatment_date") + pl.duration(days=window_days)).alias("window_end"),
    ])

    # Extract patient enrollment periods
    enr = enrollment_df.select(
        pl.col("ID").cast(pl.String),
        "ENR_START_DATE",
        "ENR_END_DATE",
    )

    # Per-patient coverage check (Python loop for correctness)
    results = []
    for patient_row in patients.iter_rows(named=True):
        patient_id = patient_row["ID"]
        window_start = patient_row["window_start"]
        window_end = patient_row["window_end"]

        # Get patient's enrollment periods, sorted by start date
        patient_enr = enr.filter(pl.col("ID") == patient_id).sort("ENR_START_DATE")

        if patient_enr.is_empty():
            # No enrollment records -> does not cover
            results.append({"ID": patient_id, "treatment_date": patient_row["treatment_date"], "ENR_COVERS_WINDOW": 0})
            continue

        # Walk through sorted periods, tracking coverage
        covered_until = window_start - timedelta(days=1)  # Start before window
        fully_covered = False

        for enr_row in patient_enr.iter_rows(named=True):
            start = enr_row["ENR_START_DATE"]
            end = enr_row["ENR_END_DATE"]

            if start is None or end is None:
                continue  # Skip periods with null dates

            # If this period starts after coverage gap, window has uncovered days
            if start > covered_until + timedelta(days=1):
                break  # Gap detected, stop checking

            # Extend coverage to this period's end date
            covered_until = max(covered_until, end)

            # If we've covered past window_end, we're done
            if covered_until >= window_end:
                fully_covered = True
                break

        # Final check: did we cover the full window?
        if not fully_covered and covered_until >= window_end:
            fully_covered = True

        results.append({
            "ID": patient_id,
            "treatment_date": patient_row["treatment_date"],
            "ENR_COVERS_WINDOW": 1 if fully_covered else 0,
        })

    return pl.DataFrame(results)
```

### Side-by-Side Comparison PNG Rendering
```python
# Source: scripts/build_insurance_by_treatment.py _render_png function
# Extend for 2-column comparison (ENR Covers | ENR Does Not Cover)
def _render_comparison_png(
    table_data: list[dict], title: str, output_path: Path,
    n_covered: int, n_not_covered: int,
) -> None:
    """Render side-by-side comparison table as PNG with 4 columns.

    Columns: Payer Category | ENR Covers (N=X) | ENR Does Not Cover (N=Y)
    """
    if not MATPLOTLIB_AVAILABLE:
        print(f"    [SKIPPED] {output_path.name} (matplotlib not available)")
        return

    # Extract data for table rendering (4 columns: category, covered N_Pct, not-covered N_Pct)
    cellText = []
    cellColours = []

    for row in table_data:
        payer_cat = row["Payer Category"]
        covered = row[f"ENR Covers Window (N={n_covered}) (N_Pct)"]
        not_covered = row[f"ENR Does Not Cover (N={n_not_covered}) (N_Pct)"]

        cellText.append([payer_cat, covered, not_covered])

        # All cells in this row get the same payer category color (from Phase 5 palette)
        row_color = PAYER_COLORS.get(payer_cat, "#FFFFFF")
        cellColours.append([row_color, row_color, row_color])

    # Create figure and table (wider figsize for 3 columns)
    fig, ax = plt.subplots(figsize=(14, 7))  # Phase 5 used (12, 7) for 4 columns
    ax.axis('off')

    col_labels = [
        "Payer Category",
        f"ENR Covers Window\n(N={n_covered})",
        f"ENR Does Not Cover\n(N={n_not_covered})"
    ]

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
        cell.set_facecolor(HEADER_COLOR)  # Phase 5: #2C5AA0
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
```

### Treatment Date + Window Columns
```python
# Source: src/report/encounter_payer_summary.py PAYER_AT_TREATMENT_WINDOW_DAYS
# Official pattern: treatment dates stored in encounter_payer_summary.parquet
def _prepare_treatment_windows(enc_payer_summary: pl.DataFrame) -> pl.DataFrame:
    """Add window start/end columns for each treatment date.

    Columns added: FIRST_CHEMO_WINDOW_START, FIRST_CHEMO_WINDOW_END, etc.
    """
    window_days = 30  # PAYER_AT_TREATMENT_WINDOW_DAYS from encounter_payer_summary.py

    treatment_dates = [
        ("FIRST_HL_DX_DATE", "FIRST_DX"),
        ("FIRST_CHEMO_DATE", "FIRST_CHEMO"),
        ("LAST_CHEMO_DATE", "LAST_CHEMO"),
        ("FIRST_RADIATION_DATE", "FIRST_RADIATION"),
        ("LAST_RADIATION_DATE", "LAST_RADIATION"),
        ("FIRST_SCT_DATE", "FIRST_SCT"),
        ("LAST_SCT_DATE", "LAST_SCT"),
    ]

    for date_col, label in treatment_dates:
        if date_col not in enc_payer_summary.columns:
            continue

        enc_payer_summary = enc_payer_summary.with_columns([
            (pl.col(date_col) - pl.duration(days=window_days))
            .alias(f"{label}_WINDOW_START"),
            (pl.col(date_col) + pl.duration(days=window_days))
            .alias(f"{label}_WINDOW_END"),
        ])

    return enc_payer_summary
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single enrollment period check | Union of multiple enrollment periods | Phase 8 (2026-03-24) | D-04/D-05: Patients with adjacent/overlapping enrollment periods now correctly count as "covered" if union spans window |
| Payer-at-treatment without enrollment validation | Stratified analysis: payer reliability depends on enrollment coverage | Phase 8 (2026-03-24) | Reveals which payer classifications are backed by enrollment records vs potentially missing data |
| "Unknown" post-treatment payer with no diagnostic breakdown | Encounter count breakdown reveals data quality issues | Phase 8 (2026-03-24) | D-16/D-17: Distinguishes "no encounters after treatment" from "encounters with missing payer info" |

**Deprecated/outdated:**
- Simple enrollment overlap check (harmonize.py `flag_encounters_outside_enrollment`) checks if ANY enrollment period overlaps encounter date. Phase 8 requires checking if UNION of periods fully COVERS a window. The existing function is correct for its purpose (single-date checking) but insufficient for Phase 8 (window coverage).

## Open Questions

1. **Encounter count bins for Unknown breakdown (D-17)**
   - What we know: Need bins like "0", "1-5", "6+" to show distribution
   - What's unclear: Optimal bin boundaries (1-5 vs 1-3 and 4-10, should there be 11-20 and 21+)
   - Recommendation: Start with [0, 1-5, 6-10, 11-20, 21+] bins. User can refine after seeing distribution in initial results.

2. **PowerPoint slide organization (Claude's discretion)**
   - What we know: 4 comparison tables + 1 Unknown breakdown table = 5 new slides
   - What's unclear: Insert before Phase 6 post-treatment tables, after them, or in separate section?
   - Recommendation: Group by treatment type: Overview (DX comparison), then Chemo section (Phase 5 + Phase 8 first/last + Phase 6), then Radiation section, then SCT section. Unknown breakdown as final slide.

3. **Column header wording (Claude's discretion)**
   - What we know: Need concise headers for "ENR Covers Window" and "ENR Does Not Cover"
   - What's unclear: Exact wording that's clear but fits in table column
   - Recommendation: "ENR Covers\n±30d Window (N=X)" and "ENR Gap\nin Window (N=Y)" — uses newline for two-line header, "Gap" is shorter than "Does Not Cover"

## Validation Architecture

> Validation architecture section included per .planning/config.json (workflow.nyquist_validation not explicitly disabled)

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.4+ |
| Config file | pytest.ini |
| Quick run command | `pytest tests/ -x --tb=short` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

**Note:** Phase 8 has no formally defined requirements in REQUIREMENTS.md (requirement IDs were "null (TBD)" in research input). Tests below map to user decisions from CONTEXT.md.

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-04 | Enrollment union coverage check returns True when multiple periods together cover ±30 day window | unit | `pytest tests/test_enr_coverage.py::test_union_coverage_multiple_periods -x` | ❌ Wave 0 |
| D-04 | Enrollment union coverage check returns False when periods have gaps in ±30 day window | unit | `pytest tests/test_enr_coverage.py::test_union_coverage_with_gaps -x` | ❌ Wave 0 |
| D-06 | Patients with no enrollment records flagged as "does not cover" | unit | `pytest tests/test_enr_coverage.py::test_no_enrollment_records -x` | ❌ Wave 0 |
| D-11 | Null payer values shown as "N/A" row, separate from "Unknown" | unit | `pytest tests/test_enr_comparison_tables.py::test_na_vs_unknown_rows -x` | ❌ Wave 0 |
| D-15 | Patients with null treatment dates excluded from cohort tables | unit | `pytest tests/test_enr_comparison_tables.py::test_null_date_exclusion -x` | ❌ Wave 0 |
| D-17 | Unknown post-treatment patients binned by encounter count correctly | unit | `pytest tests/test_unknown_breakdown.py::test_encounter_count_bins -x` | ❌ Wave 0 |
| D-19 | PNG/CSV/HTML outputs all created with correct filenames | integration | `pytest tests/test_enr_comparison_outputs.py::test_all_outputs_created -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_enr_coverage.py tests/test_enr_comparison_tables.py -x` (critical enrollment logic + table structure)
- **Per wave merge:** `pytest tests/ -x` (full suite)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_enr_coverage.py` — covers D-04, D-06 (enrollment union logic)
- [ ] `tests/test_enr_comparison_tables.py` — covers D-11, D-15 (N/A row, null date exclusion)
- [ ] `tests/test_unknown_breakdown.py` — covers D-17 (encounter count binning)
- [ ] `tests/test_enr_comparison_outputs.py` — covers D-19 (output file creation)
- [ ] `tests/conftest.py` — add enrollment fixture factory (ENR_START_DATE, ENR_END_DATE per patient)

## Sources

### Primary (HIGH confidence)
- src/report/encounter_payer_summary.py — PAYER_AT_TREATMENT_WINDOW_DAYS constant (line 83), treatment date derivation (_get_chemo_dates, _get_radiation_dates, _get_sct_dates), PAYER_CATEGORY_AT_* column names
- src/clean/harmonize.py — flag_encounters_outside_enrollment function (lines 91-156), many-to-many join pattern for enrollment overlap checking
- src/validate/schemas.py — ENROLLMENT_EXPECTED schema (lines 63-67): ENR_START_DATE, ENR_END_DATE columns confirmed
- scripts/build_insurance_by_treatment.py — Phase 5 table rendering patterns (_render_png, _render_html, _build_table), PAYER_CATEGORY_ORDER (lines 44-54), PAYER_COLORS palette (lines 57-67), N_Pct formatting
- scripts/build_post_treatment_insurance.py — Phase 6 post-treatment payer logic (_compute_post_treatment_payer), Unknown payer handling, encounter counting patterns
- scripts/build_insurance_presentation.py — Phase 7 PowerPoint generation (_add_table_slide), UF branding colors (lines 40-45), native table creation with python-pptx

### Secondary (MEDIUM confidence)
- .planning/phases/08-*/08-CONTEXT.md — All user decisions (D-01 through D-23), canonical references, integration points

### Tertiary (LOW confidence)
- None — all research findings verified against codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in use from Phases 5-7, no new dependencies
- Architecture: HIGH - Enrollment checking pattern exists in harmonize.py, table rendering patterns exist in Phase 5/6/7 scripts
- Pitfalls: HIGH - Union coverage vs overlap checking documented in harmonize.py code, off-by-one errors common in date interval logic (standard software engineering pitfall)

**Research date:** 2026-03-24
**Valid until:** 30 days (stable domain — existing pipeline patterns, no fast-moving dependencies)
