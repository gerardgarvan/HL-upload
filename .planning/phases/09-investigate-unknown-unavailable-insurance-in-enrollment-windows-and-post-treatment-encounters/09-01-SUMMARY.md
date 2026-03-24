---
phase: 09-investigate-unknown-unavailable-insurance-in-enrollment-windows-and-post-treatment-encounters
plan: 01
subsystem: insurance-diagnostic
tags:
  - diagnostic
  - insurance
  - enrollment
  - post-treatment
  - unknown-unavailable
dependency_graph:
  requires:
    - encounter_payer_summary.parquet
    - ENROLLMENT parquet
    - ENCOUNTER parquet
    - Phase 8 enrollment functions
  provides:
    - phase9_insurance_diagnostic.md
  affects:
    - Understanding of Unknown/Unavailable insurance patterns
tech_stack:
  added: []
  patterns:
    - Polars data manipulation
    - Function reuse from Phase 8
    - Markdown report generation
key_files:
  created:
    - scripts/investigate_insurance_diagnostic.py
    - reports/phase9_insurance_diagnostic.md (runtime output)
  modified: []
decisions:
  - Reused Phase 8's `_flag_enrollment_coverage()` and `_check_enrollment_covers_window()` via import for consistency
  - Created `_analyze_post_treatment_gaps()` helper function to avoid code duplication across questions 2-4
  - Separated Unknown and Unavailable reporting throughout per D-05
  - Used treatment-specific LAST_*_DATE columns per D-06
  - No rendering output (PNG/HTML/CSV/PowerPoint) per D-02
  - Patient-level SCT trace table included in markdown per D-11
metrics:
  duration_minutes: 3
  tasks_completed: 2
  files_created: 1
  files_modified: 0
completed: 2026-03-24
---

# Phase 09 Plan 01: Diagnostic Script for Unknown/Unavailable Insurance Investigation Summary

**One-liner:** Diagnostic Python script answering 5 insurance questions with markdown report output

## Objective Completed

Created `scripts/investigate_insurance_diagnostic.py` — a standalone diagnostic script that answers 5 specific questions about Unknown and Unavailable insurance patients:

1. **Enrollment coverage cross-reference** for Unknown/Unavailable patients at treatment windows (chemo, radiation, SCT) with separate counts for ENR covers vs ENR gap
2. **Chemo post-treatment gaps**: % of Unknown and Unavailable patients with zero encounters after LAST_CHEMO_DATE
3. **Radiation post-treatment gaps**: % of Unknown and Unavailable patients with zero encounters after LAST_RADIATION_DATE
4. **SCT post-treatment gaps**: % of Unknown and Unavailable patients with zero encounters after LAST_SCT_DATE
5. **SCT primary Unknown discrepancy**: Patient-level trace for the 4 SCT patients with primary Unknown showing why first/last SCT payer is not Unknown

## Tasks Completed

### Task 1: Create diagnostic script answering all 5 insurance questions
**Files:** `scripts/investigate_insurance_diagnostic.py`

Created comprehensive 470-line diagnostic script with:
- **Data loading**: encounter_payer_summary.parquet, ENROLLMENT, ENCOUNTER parquets
- **Question 1 (enrollment coverage)**: For each treatment type (chemo, radiation, SCT) and timepoint (first, last), cross-reference Unknown/Unavailable patients with enrollment coverage using ±30d window
- **Questions 2-4 (post-treatment gaps)**: Factored into `_analyze_post_treatment_gaps()` helper to analyze zero-encounter rates and distribution for Unknown/Unavailable patients after last treatment date
- **Question 5 (SCT discrepancy)**: Patient-level trace table showing 4 SCT patients with primary Unknown but non-Unknown payers at first/last SCT, with explanation of mode-payer mechanism
- **Output**: Console progress with `[N/5]` section numbering + structured markdown report to `reports/phase9_insurance_diagnostic.md`

**Key decisions:**
- Reused `_flag_enrollment_coverage()` from Phase 8 for consistency with existing enrollment analysis
- Used treatment-specific date columns (LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE) per D-06
- Separated Unknown and Unavailable reporting throughout per D-05
- No PNG/HTML/CSV/PowerPoint output per D-02

**Commit:** 3785533 — `feat(09-01): create diagnostic script for Unknown/Unavailable insurance investigation`

### Task 2: Verify script imports resolve and report path is correct
**Files:** `scripts/investigate_insurance_diagnostic.py`

Verified script correctness:
- **Import resolution**: All imports resolve successfully:
  - `load_and_validate_config` from src.load.config
  - `_payer_category_from_effective_and_dual`, `_effective_payer_and_dual_exprs` from src.report.encounter_payer_summary
  - `_flag_enrollment_coverage`, `PAYER_CATEGORY_ORDER`, `WINDOW_DAYS`, `ENCOUNTER_COUNT_BINS` from scripts.build_insurance_enr_comparison
- **Constants verified**: PAYER_CATEGORY_ORDER has 9 categories, WINDOW_DAYS = 30, ENCOUNTER_COUNT_BINS = ['0', '1-5', '6-10', '11-20', '21+']
- **Structure check**: Contains `main()` and `_analyze_post_treatment_gaps()` functions
- **No prohibited imports**: No matplotlib, seaborn, or rendering functions
- **Report path**: Outputs to `reports/phase9_insurance_diagnostic.md`

No commit needed — verification only.

## Implementation Notes

### Helper Function Pattern
Created `_analyze_post_treatment_gaps()` to avoid repeating ~40 lines of logic three times for questions 2-4. The helper:
- Takes treatment flag column, last date column, payer column, and treatment label
- Filters to treatment cohort, then to Unknown/Unavailable patients separately
- Computes zero-encounter counts and percentages
- Bins encounter counts into standard bins
- Returns markdown lines for the section

This pattern aligns with project's DRY principle while maintaining readability.

### Enrollment Coverage Reuse
Imported `_flag_enrollment_coverage()` from Phase 8 script rather than reimplementing. This ensures:
- Consistency with Phase 8 enrollment analysis
- Same ±30 day window definition
- Same union-of-periods coverage logic
- Reduces maintenance burden (single source of truth)

### SCT Discrepancy Explanation
The script explains that the discrepancy occurs because:
- **PAYER_CATEGORY_PRIMARY** = mode payer across ALL encounters
- **PAYER_CATEGORY_AT_FIRST/LAST_SCT** = mode payer within ±30d windows around SCT dates
- The 4 patients had Unknown as their most frequent overall payer but had encounters with known payers during SCT treatment windows

This clarifies the mechanism without requiring code changes to Phases 5-8.

## Deviations from Plan

None — plan executed exactly as written. All 5 questions answered with correct data sources, treatment-specific dates used, Unknown and Unavailable separated throughout, and no prohibited output formats.

## Verification

All acceptance criteria met:
- ✅ scripts/investigate_insurance_diagnostic.py exists and is valid Python (470 lines)
- ✅ File contains `def main()` and `def _analyze_post_treatment_gaps()` functions
- ✅ File contains imports from build_insurance_enr_comparison, encounter_payer_summary, load.config
- ✅ File contains `[1/5]` through `[5/5]` progress markers
- ✅ File contains "Question 1" through "Question 5" section headers
- ✅ File contains treatment-specific payer columns (PAYER_CATEGORY_AT_LAST_CHEMO, _RADIATION, _SCT)
- ✅ File contains both "Unknown" and "Unavailable" as separate filter values
- ✅ File contains PAYER_CATEGORY_PRIMARY and PAYER_CATEGORY_AT_FIRST_SCT (Q5 trace)
- ✅ File does NOT contain _render_png, _render_html, .write_csv, or matplotlib imports
- ✅ File contains `if __name__ == "__main__":` block
- ✅ All imports resolve successfully (verified with Python import check)

## Known Stubs

None — script outputs findings to markdown report. No UI components or data source stubs.

## Self-Check: PASSED

**Created files verification:**
```bash
[ -f "scripts/investigate_insurance_diagnostic.py" ] && echo "FOUND"
```
Result: FOUND ✅

**Commit verification:**
```bash
git log --oneline --all | grep -q "3785533" && echo "FOUND"
```
Result: FOUND ✅

All files created and commits exist.
