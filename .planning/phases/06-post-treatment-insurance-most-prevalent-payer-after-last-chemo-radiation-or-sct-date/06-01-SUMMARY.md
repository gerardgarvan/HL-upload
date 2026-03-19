---
phase: 06-post-treatment-insurance-most-prevalent-payer-after-last-chemo-radiation-or-sct-date
plan: 01
subsystem: reporting
tags: [insurance, post-treatment, payer-analysis, treatment-outcomes]
dependency_graph:
  requires:
    - encounter_payer_summary.parquet (treatment dates + flags)
    - clean/ENCOUNTER.parquet (raw encounters with payer columns)
  provides:
    - reports/post_treatment_insurance/*.csv (4 tables)
    - reports/post_treatment_insurance/README.md
  affects:
    - Phase 6 post-treatment analysis workflows
tech_stack:
  added: []
  patterns:
    - Polars max_horizontal for row-wise max across nullable date columns
    - Mode payer derivation from filtered encounter set
    - Effective payer logic with primary->secondary fallback
    - Graceful degradation for missing treatment date columns
key_files:
  created:
    - scripts/build_post_treatment_insurance.py (598 lines)
  modified: []
decisions:
  - Post-treatment payer computed inline in script (not added to encounter_payer_summary.py) for single-use analysis
  - Self-pay label (not "No payment / Self-pay") for consistency with Phase 5 tables
  - N/A row placed at bottom of combined table (after Unknown) with conceptual separation
  - All 4 tables include patients with no post-treatment encounters as "Unknown"
metrics:
  duration_minutes: 3.3
  tasks_completed: 2
  files_created: 1
  lines_added: 598
  completed_at: "2026-03-19T13:55:00Z"
---

# Phase 06 Plan 01: Post-Treatment Insurance Script Summary

**One-liner:** Create standalone post-treatment insurance analysis script deriving mode payer from encounters after max(last chemo, radiation, SCT dates) with 4 CSV tables + markdown README

## What Was Built

Created `scripts/build_post_treatment_insurance.py` (598 lines) that:
1. Reads encounter_payer_summary.parquet for treatment dates (LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE) and flags (HAD_CHEMO, HAD_RADIATION, HAD_SCT)
2. Computes LAST_TREATMENT_DATE per patient using `pl.max_horizontal()` (nulls ignored automatically)
3. Reads clean/ENCOUNTER.parquet for raw encounters with payer columns
4. Filters encounters to ADMIT_DATE > LAST_TREATMENT_DATE (strict greater-than, no buffer)
5. Applies effective payer logic (primary->secondary fallback) and dual-eligible detection from src/report/encounter_payer_summary.py
6. Computes mode (most frequent) payer category per patient across post-treatment encounters
7. Handles edge cases: Unknown for no post-treatment encounters, N/A for no treatment
8. Generates 4 CSV tables: combined (10 rows: 9 payer + N/A), chemo cohort (9 rows), radiation cohort (9 rows), SCT cohort (9 rows)
9. Writes combined markdown README with all 4 tables and comprehensive methodology section

**Output location:** `reports/post_treatment_insurance/` (separate from Phase 5 tables)

**Table structure:** Single column per table ("Post-Treatment Insurance") with N (%) format. Cohort size in header. 9 payer categories in standard order (Medicare through Unknown).

**Edge case handling:**
- Patients with treatment but no post-treatment encounters -> POST_TREATMENT_PAYER = "Unknown"
- Patients with no treatment at all (HAD_CHEMO=0, HAD_RADIATION=0, HAD_SCT=0) -> POST_TREATMENT_PAYER = "N/A (No Treatment)" in combined table only
- One post-treatment encounter sufficient (no minimum threshold)
- No time cap (all encounters after last treatment count)

**Cohort definitions:** Match Phase 5 exactly (HAD_CHEMO=1, HAD_RADIATION=1, HAD_SCT=1, no additional date null checks). Post-treatment payer for chemo cohort patient based on encounters after max(ALL treatment dates), not just last chemo date.

## Tasks Completed

### Task 1: Create build_post_treatment_insurance.py with data loading and post-treatment payer computation
**Status:** ✅ Complete
**Commit:** 6113506

Created script with:
- Module docstring explaining Phase 6 purpose and output structure
- sys.path setup for PROJECT_ROOT (same pattern as Phase 5)
- Imports: polars, pathlib, datetime, html, src.load.config, src.report.encounter_payer_summary functions, src.validate.structural
- PAYER_CATEGORY_ORDER with 9 categories using "Self-pay" label (not "No payment / Self-pay")
- `_compute_post_treatment_payer()` function:
  - Computes LAST_TREATMENT_DATE with `pl.max_horizontal()` across 3 date columns
  - Computes HAD_ANY_TREATMENT flag
  - Reads clean/ENCOUNTER.parquet with effective payer logic (reuses _effective_payer_and_dual_exprs)
  - Joins encounters to patients, filters ADMIT_DATE > LAST_TREATMENT_DATE with _valid flag
  - Applies _payer_category_from_effective_and_dual for category derivation
  - Maps "No payment / Self-pay" -> "Self-pay" for label consistency
  - Computes mode via group_by PATID+PAYER_CATEGORY, count, sort descending, group_by PATID, first
  - Left joins mode results to all patients, fills nulls with "Unknown" for HAD_ANY_TREATMENT=1, "N/A (No Treatment)" for HAD_ANY_TREATMENT=0
- `_build_post_treatment_table()` function:
  - Takes df, col_name, cohort_label, include_na_row bool
  - Normalizes nulls to "Unknown"
  - Counts by payer category
  - Builds 9 rows in PAYER_CATEGORY_ORDER with N, %, N_Pct columns
  - Appends N/A row if include_na_row=True (combined table only)
- `main()` function:
  - Loads config, reads encounter_payer_summary.parquet
  - Checks for required date columns (LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE) with graceful degradation (warns but continues with available columns)
  - Checks for required flag columns (HAD_CHEMO, HAD_RADIATION, HAD_SCT), adds as 0 if missing
  - Calls _compute_post_treatment_payer()
  - Builds 4 tables: combined (include_na_row=True), chemo cohort (HAD_CHEMO=1), radiation cohort (HAD_RADIATION=1), SCT cohort (HAD_SCT=1)
  - Writes CSV for each table
  - Writes combined markdown README with 4 tables and methodology section
  - Prints summary stats: total patients, patients with treatment, patients without treatment, cohort sizes, post-treatment encounter counts

**Verification:**
- ✅ Syntax check passed
- ✅ Imports resolve correctly
- ✅ PAYER_CATEGORY_ORDER has 9 categories with "Self-pay" label
- ✅ N/A row logic only in combined table (include_na_row=True for combined, False for cohorts)

### Task 2: Verify table structure and edge case handling via code review
**Status:** ✅ Complete (No changes needed)

Code review against 6 CONTEXT.md locked decisions:

**1. Post-treatment date logic:**
- ✅ Confirmed `pl.max_horizontal()` used for LAST_TREATMENT_DATE (lines 74-78)
- ✅ Confirmed single date per patient (not per-treatment-type windows)
- ✅ Confirmed ADMIT_DATE > LAST_TREATMENT_DATE (strict greater-than, no buffer)

**2. Output destination:**
- ✅ Confirmed outputs go to reports/post_treatment_insurance/ (separate from Phase 5)
- ✅ Confirmed 4 tables: combined, chemo, radiation, SCT
- ✅ Confirmed NOT modifying Phase 5 tables or adding columns to them

**3. Edge cases:**
- ✅ Confirmed no post-treatment encounters -> "Unknown" (multiple fallback paths in code)
- ✅ Confirmed no treatment at all -> "N/A (No Treatment)" in combined table ONLY (include_na_row logic)
- ✅ Confirmed one post-treatment encounter is sufficient (no minimum threshold check)

**4. Payer selection rule:**
- ✅ Confirmed mode (most frequent) used via group_by + agg + sort pattern
- ✅ Confirmed no time cap on post-treatment encounters (filter only checks > last_treatment_date)
- ✅ Confirmed no HIPAA small-cell suppression

**5. Table structure:**
- ✅ Confirmed 9 payer category rows (+ N/A for combined = 10 rows)
- ✅ Confirmed single column: "Post-Treatment Insurance" with N (%) format
- ✅ Confirmed cohort size in table header

**6. Specific ideas:**
- ✅ Confirmed per-cohort breakdowns use Phase 5 cohort definitions (HAD_CHEMO=1, HAD_RADIATION=1, HAD_SCT=1, no additional date checks)
- ✅ Confirmed chemo cohort patient's post-treatment payer is based on encounters after max(ALL treatment dates) — verified by checking that the join uses LAST_TREATMENT_DATE (computed from max_horizontal of all 3 dates), not LAST_CHEMO_DATE

**Re-verification:**
- ✅ Syntax check passed
- ✅ Key patterns confirmed:
  - `max_horizontal` found
  - `ADMIT_DATE > LAST_TREATMENT_DATE` found (strict greater-than)
  - "N/A" handling for no-treatment patients found
  - "Unknown" handling for no post-treatment encounters found
  - "Self-pay" label found (with mapping from "No payment / Self-pay")

**Conclusion:** All 6 locked decisions and 3 specific ideas correctly implemented. No issues found.

## Deviations from Plan

None — plan executed exactly as written.

## Decisions Made

1. **Post-treatment payer computation location:** Computed inline in script rather than adding column to encounter_payer_summary.py. Rationale: Single-use analysis per current requirements; avoids slowing pipeline for all runs; encounter_payer_summary.py already complex (894 lines).

2. **Self-pay label mapping:** Map "No payment / Self-pay" (from encounter_payer_summary categorization) to "Self-pay" for consistency with Phase 5 insurance_by_treatment tables. Implemented in _compute_post_treatment_payer after category derivation.

3. **N/A row placement and color:** Place N/A row at bottom (after Unknown) as 10th row in combined table. N/A conceptually separate from payer categories (represents absence of treatment, not insurance type). Bottom placement keeps 9 payer rows together.

4. **Unknown payer for all patients with no post-treatment encounters:** Applied to ALL tables (combined + per-cohort), not just combined. Ensures cohort N matches Phase 5 tables for consistency. Per-cohort chemo table = all HAD_CHEMO=1 patients; those with no post-treatment encounters get POST_TREATMENT_PAYER="Unknown".

## Known Issues

None identified during execution or verification.

## Next Steps

1. Run script on HPC with real data to verify 4 CSV files + README.md created in reports/post_treatment_insurance/
2. Validate cohort sizes match Phase 5 tables (chemo N, radiation N, SCT N)
3. Spot-check post-treatment payer distributions for clinical plausibility
4. If encounter_payer_summary.parquet is missing LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE columns, re-run `python scripts/assemble_clean.py` to rebuild with treatment date columns

## Self-Check

Verifying SUMMARY.md claims:

**Created files:**
```bash
[ -f "scripts/build_post_treatment_insurance.py" ] && echo "FOUND: scripts/build_post_treatment_insurance.py" || echo "MISSING: scripts/build_post_treatment_insurance.py"
```

**Commits:**
```bash
git log --oneline --all | grep -q "6113506" && echo "FOUND: 6113506" || echo "MISSING: 6113506"
```

**Results:**
```
FOUND: scripts/build_post_treatment_insurance.py
FOUND: 6113506
```

## Self-Check: PASSED

All claims verified. Created files exist, commits recorded in git history.
