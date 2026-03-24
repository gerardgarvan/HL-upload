# Phase 09: Investigate Unknown/Unavailable Insurance in Enrollment Windows and Post-Treatment Encounters - Research

**Researched:** 2026-03-24
**Domain:** Diagnostic data quality investigation — insurance coverage gap analysis
**Confidence:** HIGH

## Summary

Phase 9 is a diagnostic/investigative phase answering 5 specific questions about Unknown and Unavailable insurance patients:
1. Cross-reference enrollment coverage with treatment windows to determine if Unknown/Unavailable patients should be counted
2-4. For each treatment type (chemo, radiation, SCT), measure % of Unknown/Unavailable post-treatment patients with zero encounters after last treatment
5. Explain SCT discrepancy where primary Unknown=4 but first/last Unknown both=0

This is NOT a table generation phase. It produces a diagnostic Python script that prints findings to console AND writes a structured markdown report.

**Primary recommendation:** Reuse Phase 8's enrollment coverage logic (`_check_enrollment_covers_window`, `_flag_enrollment_coverage`) via import. Combine with Phase 6's post-treatment payer logic. Use patient-level trace for SCT discrepancy investigation. Output as structured markdown with numbered sections matching the 5 questions.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Diagnostic Python script (not a full table pipeline) — prints findings to console AND writes a structured markdown report to `reports/phase9_insurance_diagnostic.md`

**D-02:** No PNG, HTML, CSV, or PowerPoint output — this is exploratory analysis, not presentation tables

**D-03:** Report format: structured markdown with numbered sections matching the 5 questions, tables where appropriate

**D-04:** Report findings only — do NOT recommend exclusions or change existing Phase 5-8 tables

**D-05:** Unknown and Unavailable are reported as separate groups (not combined), since they may have different underlying patterns

**D-06:** For "no encounters after last treatment" questions, use treatment-specific dates (LAST_CHEMO_DATE for chemo, LAST_RADIATION_DATE for radiation, LAST_SCT_DATE for SCT) — matches the questions as asked

**D-07:** Cross-reference Phase 8's enrollment coverage for Unknown/Unavailable post-treatment patients

**D-08:** Use ±30 day treatment window enrollment check (reuse Phase 8's `_check_enrollment_covers_window` logic) for direct comparability with Phase 8 tables

**D-09:** For each treatment type, report: of the Unknown/Unavailable patients, how many had ENR coverage vs not around the treatment-specific window

**D-10:** Full patient-level trace for the 4 SCT patients with primary Unknown — identify them, show their primary payer source encounters, first/last SCT dates, and derived payer at first/last SCT

**D-11:** Include per-patient trace table in the markdown report (patient IDs are already de-identified in PCORnet CDM)

**D-12:** Explain the mechanism causing the discrepancy (e.g., different encounter payer in the ±30d SCT window vs primary/mode payer)

### Claude's Discretion

- Script naming and organization within `scripts/`
- Exact markdown report structure and section headings
- Whether to reuse Phase 8's enrollment functions via import or recompute inline
- How to present the enrollment cross-reference findings (table vs narrative)
- Bin sizes for encounter count distributions

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 1.17.1+ | DataFrame manipulation | Project standard; used in Phases 5-8 for insurance analysis |
| pathlib | stdlib | Path handling | Python standard library; project convention |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| datetime | stdlib | Date calculations | Treatment date comparisons, window calculations |
| sys | stdlib | Exit codes, args | Script orchestration patterns |

**Installation:**
```bash
# All dependencies already installed for Phases 5-8
# No new packages required
```

**Version verification:** Polars version confirmed from existing insurance scripts.

## Architecture Patterns

### Recommended Project Structure
```
scripts/
├── investigate_insurance_diagnostic.py  # Phase 9 diagnostic script
└── build_insurance_*.py                 # Phase 5-8 scripts (existing)

reports/
└── phase9_insurance_diagnostic.md       # Output report
```

### Pattern 1: Reuse Phase 8 Enrollment Functions
**What:** Import enrollment coverage logic from `scripts/build_insurance_enr_comparison.py`
**When to use:** Question 1 (enrollment window cross-reference) for all three treatment types
**Example:**
```python
# Source: build_insurance_enr_comparison.py lines 95-201
from scripts.build_insurance_enr_comparison import (
    _check_enrollment_covers_window,
    _flag_enrollment_coverage,
)

# Use directly for ±30 day enrollment coverage checks
chemo_enr_coverage = _flag_enrollment_coverage(
    chemo_cohort.select("ID", "FIRST_CHEMO_DATE"),
    enrollment_df,
    "FIRST_CHEMO_DATE",
    window_days=30
)
```

### Pattern 2: Treatment-Specific Date Usage
**What:** Use treatment-specific LAST_*_DATE columns, not combined LAST_TREATMENT_DATE
**When to use:** Questions 2-4 (post-treatment encounter gaps)
**Example:**
```python
# For chemo: filter encounters to ADMIT_DATE > LAST_CHEMO_DATE
post_chemo = enc.filter(
    pl.col("ADMIT_DATE") > pl.col("LAST_CHEMO_DATE")
)

# For radiation: filter encounters to ADMIT_DATE > LAST_RADIATION_DATE
post_radiation = enc.filter(
    pl.col("ADMIT_DATE") > pl.col("LAST_RADIATION_DATE")
)

# For SCT: filter encounters to ADMIT_DATE > LAST_SCT_DATE
post_sct = enc.filter(
    pl.col("ADMIT_DATE") > pl.col("LAST_SCT_DATE")
)
```

### Pattern 3: Patient-Level Trace for Discrepancy Investigation
**What:** Extract per-patient details (ID, dates, payer sources) into trace table
**When to use:** Question 5 (SCT discrepancy investigation)
**Example:**
```python
# Identify the 4 SCT patients with primary Unknown
unknown_primary_sct = enc_payer_summary.filter(
    (pl.col("HAD_SCT") == 1) &
    (pl.col("PAYER_CATEGORY_PRIMARY") == "Unknown")
)

# Join with encounter data to show payer sources
trace = unknown_primary_sct.select("ID", "FIRST_SCT_DATE", "LAST_SCT_DATE").join(
    enc.select("ID", "ADMIT_DATE", "PAYER_TYPE_PRIMARY", "effective_payer"),
    on="ID"
)

# Show encounters in ±30d SCT windows
first_sct_window = trace.filter(
    (pl.col("ADMIT_DATE") >= pl.col("FIRST_SCT_DATE") - timedelta(days=30)) &
    (pl.col("ADMIT_DATE") <= pl.col("FIRST_SCT_DATE") + timedelta(days=30))
)
```

### Pattern 4: Markdown Report Structure
**What:** Structured markdown with numbered sections, tables rendered as markdown tables
**When to use:** All output (console progress + final report file)
**Example:**
```python
# Console output with progress markers
print("[1/5] Analyzing enrollment coverage for Unknown/Unavailable patients...")

# Markdown report sections
md_lines = [
    "# Phase 9: Insurance Diagnostic Report",
    "",
    "## Question 1: Enrollment Coverage for Unknown/Unavailable Patients",
    "",
    "### Chemotherapy",
    "",
    "| Category | N Patients | ENR Covers ±30d | ENR Gap |",
    "|----------|------------|-----------------|---------|",
    f"| Unknown | {n_unknown} | {n_enr_covers} ({pct_covers:.1f}%) | {n_enr_gap} ({pct_gap:.1f}%) |",
]
```

### Anti-Patterns to Avoid
- **Combining Unknown and Unavailable:** User specified separate reporting (D-05) — do NOT merge into single category
- **Using combined LAST_TREATMENT_DATE:** Questions 2-4 are treatment-specific — use LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE respectively
- **Generating PNG/HTML/CSV:** D-02 explicitly disallows — markdown-only output
- **Making recommendations:** D-04 explicitly disallows — report findings neutrally without suggesting exclusions

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Enrollment coverage check | Custom date overlap logic | `_check_enrollment_covers_window()` from Phase 8 | Handles adjacent/overlapping periods, gap detection, already validated in Phase 8 |
| Post-treatment payer | Custom encounter filtering | Pattern from `_compute_post_treatment_payer()` in Phase 6 | Handles effective payer logic, mode computation, null handling |
| ±30 day window filtering | Manual date arithmetic | `_flag_enrollment_coverage()` from Phase 8 | Batch processing, consistent with Phase 8 definitions |
| Payer category mapping | Custom code prefix logic | `_payer_category_from_effective_and_dual()` from encounter_payer_summary.py | Handles dual-eligible, sentinel values, PCORnet typology |

**Key insight:** Phases 5-8 built reusable functions for enrollment coverage, post-treatment payer, and payer categorization. Phase 9 is orchestration — combine existing functions to answer 5 specific questions. Custom logic only needed for: (1) treatment-specific date filtering, (2) encounter count binning, (3) patient-level trace formatting.

## Common Pitfalls

### Pitfall 1: Using Wrong Date Column for Post-Treatment Analysis
**What goes wrong:** Using `LAST_TREATMENT_DATE` (max of all treatment dates) instead of treatment-specific dates for questions 2-4
**Why it happens:** Phase 6 used `LAST_TREATMENT_DATE` for combined post-treatment analysis; easy to assume same pattern
**How to avoid:** D-06 explicitly requires treatment-specific dates — use `LAST_CHEMO_DATE` for chemo, `LAST_RADIATION_DATE` for radiation, `LAST_SCT_DATE` for SCT
**Warning signs:** If chemo patients with Unknown post-treatment payer have encounters after chemo but those encounters are after radiation/SCT, they'd be misclassified as having encounters

### Pitfall 2: Combining Unknown and Unavailable Categories
**What goes wrong:** Treating "Unknown" and "Unavailable" as a single group for analysis
**Why it happens:** Both represent missing/unclear payer information; semantically similar
**How to avoid:** D-05 explicitly requires separate reporting — user hypothesis is they may have different patterns
**Warning signs:** If markdown report has rows like "Unknown/Unavailable (N=X)" instead of separate "Unknown (N=X)" and "Unavailable (N=Y)"

### Pitfall 3: Forgetting to Filter to Treatment Cohorts
**What goes wrong:** Analyzing all patients instead of treatment-specific cohorts (HAD_CHEMO=1, etc.)
**Why it happens:** Phase 6 had combined analysis; easy to forget cohort filtering
**How to avoid:** Questions 2-4 are treatment-specific — filter to `HAD_CHEMO=1`, `HAD_RADIATION=1`, `HAD_SCT=1` before computing post-treatment metrics
**Warning signs:** If denominator for "% with no encounters" includes patients who never had that treatment

### Pitfall 4: Not Handling Null Treatment Dates
**What goes wrong:** Crash or incorrect filtering when treatment date is null
**Why it happens:** Not all patients have all treatment types; null dates are valid
**How to avoid:** Filter to non-null treatment dates before computing windows or post-treatment encounters
**Warning signs:** Polars errors like "cannot compare date and null" or empty cohorts when they shouldn't be

### Pitfall 5: Misinterpreting Primary vs Window-Based Payer
**What goes wrong:** Expecting PAYER_CATEGORY_PRIMARY (mode across all encounters) to match PAYER_CATEGORY_AT_FIRST_SCT (mode in ±30d window)
**Why it happens:** Column names are similar; different time scopes not obvious
**How to avoid:** D-12 explains the mechanism — primary is all-time mode, first/last are window-based modes; patient can have Unknown primary but known payer in specific windows
**Warning signs:** If explanation says "payer changed" when actually different aggregation scopes

## Code Examples

Verified patterns from official sources:

### Enrollment Coverage Check (Question 1)
```python
# Source: build_insurance_enr_comparison.py lines 152-201
from scripts.build_insurance_enr_comparison import _flag_enrollment_coverage

# Flag enrollment coverage for Unknown chemo patients
unknown_chemo = enc_payer_summary.filter(
    (pl.col("HAD_CHEMO") == 1) &
    (pl.col("PAYER_CATEGORY_AT_FIRST_CHEMO") == "Unknown")
)

enr_coverage = _flag_enrollment_coverage(
    unknown_chemo.select("ID", "FIRST_CHEMO_DATE"),
    enrollment_df,
    "FIRST_CHEMO_DATE",
    window_days=30
)

# Merge and count
merged = unknown_chemo.join(enr_coverage.select("ID", "ENR_COVERS_WINDOW"), on="ID", how="left")
n_covered = merged.filter(pl.col("ENR_COVERS_WINDOW") == 1).height
n_gap = merged.filter(pl.col("ENR_COVERS_WINDOW") == 0).height
```

### Post-Treatment Encounter Count (Questions 2-4)
```python
# Source: Pattern from build_post_treatment_insurance.py lines 371-379
# Filter to patients with Unknown post-treatment payer (treatment-specific)
unknown_post_chemo = enc_payer_summary.filter(
    (pl.col("HAD_CHEMO") == 1) &
    (pl.col("LAST_CHEMO_DATE").is_not_null())
)

# Join with encounters, filter to post-chemo only
post_chemo_enc = unknown_post_chemo.select("ID", "LAST_CHEMO_DATE").join(
    enc.select("ID", "ADMIT_DATE"), on="ID", how="left"
).filter(
    pl.col("ADMIT_DATE") > pl.col("LAST_CHEMO_DATE")
)

# Count encounters per patient
enc_counts = post_chemo_enc.group_by("ID").agg(
    pl.len().alias("N_POST_CHEMO_ENC")
)

# Merge back, fill nulls with 0 (no encounters)
with_counts = unknown_post_chemo.join(enc_counts, on="ID", how="left").with_columns(
    pl.col("N_POST_CHEMO_ENC").fill_null(0)
)

# Compute % with zero encounters
n_zero_enc = with_counts.filter(pl.col("N_POST_CHEMO_ENC") == 0).height
pct_zero = 100.0 * n_zero_enc / with_counts.height if with_counts.height > 0 else 0.0
```

### Patient-Level Trace for SCT Discrepancy (Question 5)
```python
# Source: Pattern from build_insurance_enr_comparison.py patient iteration logic
# Identify the 4 patients with primary Unknown but first/last=0
unknown_primary_sct = enc_payer_summary.filter(
    (pl.col("HAD_SCT") == 1) &
    (pl.col("PAYER_CATEGORY_PRIMARY") == "Unknown")
)

# For each patient, trace encounters and payer sources
trace_rows = []
for patient_id in unknown_primary_sct["ID"]:
    patient_info = unknown_primary_sct.filter(pl.col("ID") == patient_id)
    first_sct = patient_info["FIRST_SCT_DATE"][0]
    last_sct = patient_info["LAST_SCT_DATE"][0]

    # Get all encounters for this patient
    patient_enc = enc.filter(pl.col("ID") == patient_id)

    # Count encounters in ±30d windows around first/last SCT
    first_window_enc = patient_enc.filter(
        (pl.col("ADMIT_DATE") >= first_sct - timedelta(days=30)) &
        (pl.col("ADMIT_DATE") <= first_sct + timedelta(days=30))
    )
    last_window_enc = patient_enc.filter(
        (pl.col("ADMIT_DATE") >= last_sct - timedelta(days=30)) &
        (pl.col("ADMIT_DATE") <= last_sct + timedelta(days=30))
    )

    trace_rows.append({
        "Patient ID": patient_id,
        "First SCT Date": first_sct,
        "Last SCT Date": last_sct,
        "N Total Encounters": patient_enc.height,
        "N First SCT Window": first_window_enc.height,
        "N Last SCT Window": last_window_enc.height,
        "Primary Payer": patient_info["PAYER_CATEGORY_PRIMARY"][0],
        "First SCT Payer": patient_info["PAYER_CATEGORY_AT_FIRST_SCT"][0],
        "Last SCT Payer": patient_info["PAYER_CATEGORY_AT_LAST_SCT"][0],
    })

trace_df = pl.DataFrame(trace_rows)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 5-7: Generate presentation tables | Phase 9: Diagnostic report-only | Phase 9 (2026-03-24) | No PNG/HTML/CSV output; markdown-only for diagnostic questions |
| Phase 6: Combined LAST_TREATMENT_DATE | Phase 9: Treatment-specific dates | Phase 9 (2026-03-24) | Questions 2-4 use LAST_CHEMO/RADIATION/SCT_DATE respectively |
| Phase 8: Enrollment comparison tables | Phase 9: Reuse enrollment functions | Phase 9 (2026-03-24) | Import `_check_enrollment_covers_window` instead of reimplementing |

**Deprecated/outdated:**
- None — Phase 9 builds on current Phases 5-8 patterns

## Open Questions

1. **Should Unknown and Unavailable be combined in final interpretation?**
   - What we know: D-05 requires separate reporting during analysis
   - What's unclear: Whether findings will show similar patterns that justify future merging
   - Recommendation: Report separately as specified; if patterns are nearly identical, note in report's interpretation section but don't combine data

2. **What bin sizes for encounter count distributions?**
   - What we know: Phase 8 used `["0", "1-5", "6-10", "11-20", "21+"]` for Unknown post-treatment breakdown
   - What's unclear: Whether same bins work for treatment-specific analysis (chemo vs radiation vs SCT may have different distributions)
   - Recommendation: Reuse Phase 8 bins for consistency; if distributions cluster differently, note in report

3. **Should enrollment coverage be checked for first AND last treatment dates?**
   - What we know: D-09 says "around the treatment-specific window" but doesn't specify first vs last
   - What's unclear: Whether to check first treatment window only, last only, or both
   - Recommendation: Check both for completeness — patient may have enrollment coverage at first chemo but gap at last chemo

## Validation Architecture

**Note:** Validation section omitted per `.planning/config.json` — `workflow.nyquist_validation` key not present, but Phase 9 is diagnostic/investigative (not a pipeline component requiring test coverage).

## Sources

### Primary (HIGH confidence)
- `scripts/build_insurance_enr_comparison.py` — Phase 8 enrollment coverage logic (lines 95-201: `_check_enrollment_covers_window`, `_flag_enrollment_coverage`)
- `scripts/build_post_treatment_insurance.py` — Phase 6 post-treatment payer computation (lines 256-453: `_compute_post_treatment_payer`)
- `scripts/build_insurance_by_treatment.py` — Phase 5 payer category constants (lines 43-54: `PAYER_CATEGORY_ORDER`)
- `src/report/encounter_payer_summary.py` — Core payer derivation logic (lines 156-177: `_payer_category_from_effective_and_dual`)
- `.planning/phases/09-investigate-unknown-unavailable-insurance-in-enrollment-windows-and-post-treatment-encounters/09-CONTEXT.md` — User decisions D-01 through D-12

### Secondary (MEDIUM confidence)
- Project patterns: Phases 5-8 established Polars-based analysis, config-driven paths, console progress output, standalone scripts in `scripts/`
- PCORnet CDM: Patient IDs are de-identified per CDM standard (supports D-11: patient-level trace OK for markdown report)

### Tertiary (LOW confidence)
- None — all findings verified against existing codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in use for Phases 5-8, no new dependencies
- Architecture: HIGH - Reusing validated Phase 8 enrollment logic, Phase 6 post-treatment patterns, established project conventions
- Pitfalls: HIGH - Specific pitfalls identified from user decisions (wrong date column, combining categories, cohort filtering)

**Research date:** 2026-03-24
**Valid until:** 2026-04-24 (30 days — stable domain, existing codebase patterns unlikely to change)
