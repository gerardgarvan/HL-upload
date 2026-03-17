---
phase: 03-structural-validation-hl-cohort-verification
plan: 02
subsystem: data-validation
tags: [polars, parquet, icd-codes, hl-cohort, enrollment, dual-date-method, dx-type]

requires:
  - phase: 03-structural-validation-hl-cohort-verification
    plan: 01
    provides: "structural.py (validation functions, PATID_COL, flag_small_cell), validate_all.py (pipeline entry point)"
  - phase: 02-csv-to-parquet-conversion
    provides: "Parquet files for DIAGNOSIS, ENCOUNTER, ENROLLMENT, DEMOGRAPHIC"
  - phase: 01-environment-extension-data-staging
    provides: "config.py (Paths dataclass with parquet_dir)"
provides:
  - "cohort.py module with 149 ICD codes, verify_hl_cohort (5-stage algorithm), enrollment_crosscheck, build_cohort_summary_df"
  - "validate_all.py updated with Section 5 cohort verification and cohort_summary.csv output"
  - "reports/structural_validation.md Section 5: HL Cohort Verification"
  - "reports/cohort_summary.csv (per-patient cohort data)"
affects: [04-data-cleaning, 05-analysis]

tech-stack:
  added: []
  patterns:
    - "Exact ICD code matching via set membership (is_in) — not prefix matching"
    - "Format-adaptive DX matching: detect dotted vs undotted at runtime, use appropriate code set"
    - "Dual-date cohort verification: Method A (DX_DATE) and Method B (ADMIT_DATE) with set comparison"
    - "ICD version flagging per patient: ICD9_ONLY / ICD10_ONLY / BOTH with AMS/UMI caveat"
    - "DX_TYPE mismatch detection reported but not used for exclusion"
    - "Enrollment cross-check via anti-join with per-partner coverage period analysis"

key-files:
  created:
    - src/validate/cohort.py
  modified:
    - scripts/validate_all.py

key-decisions:
  - "Cohort section added as Section 5 (not 4) since existing report already had 4 sections from Plan 01"
  - "DX format auto-detection samples 1000 records to choose dotted vs normalized code set"
  - "All IDs and ENCOUNTERIDs cast to pl.String before joins to prevent type mismatch errors"
  - "build_cohort_summary_df produces per-patient CSV with method membership, ICD flag, and DX date range"
  - "ICD version classification uses _DX_MATCH (normalized) column for consistent prefix detection"

patterns-established:
  - "cohort verification module: src/validate/cohort.py with constants + functions pattern"
  - "Report section builder pattern: _section_cohort() follows same design as _section_schema, _section_integrity"
  - "Enrollment cross-check joins cohort IDs against ENROLLMENT and DEMOGRAPHIC for per-partner analysis"

requirements-completed: [REQ-01, REQ-03, REQ-04, REQ-05]

duration: 8min
completed: 2026-02-27
---

# Phase 3 Plan 02: HL Cohort Verification Summary

**Exact 149-code ICD matching with dual-date verification (DX_DATE vs ADMIT_DATE), ICD version flagging, DX_TYPE mismatch detection, and enrollment cross-check producing cohort_summary.csv and Section 5 of structural_validation.md**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-02-27T17:41:39Z
- **Completed:** 2026-02-27T17:50:00Z
- **Tasks:** 2
- **Files created:** 1
- **Files modified:** 1

## Accomplishments
- Created `cohort.py` module (~560 lines) with 149 exact ICD codes (77 ICD-10 C81.00–C81.9A + 72 ICD-9 201.00–201.98), both dotted and normalized forms, and 5 exported functions
- Five-stage cohort verification: extract HL DX records with format-adaptive matching, Method A (2+ distinct DX_DATEs), Method B (2+ distinct ADMIT_DATEs via ENCOUNTER join), set comparison with per-partner breakdown, ICD version flags with AMS/UMI mapping caveat
- DX_TYPE mismatches detected but not used for exclusion (per locked decision); enrollment cross-check identifies uncovered patients by partner with coverage period analysis
- Updated `validate_all.py` with `_section_cohort()` generating Section 5 of the report, console cohort stats, and `cohort_summary.csv` output

## Task Commits

Each task was committed atomically:

1. **Task 1: Create HL cohort verification module** — `644120a` (feat)
2. **Task 2: Integrate cohort verification into pipeline** — `c4d0955` (feat)

## Files Created/Modified
- `src/validate/cohort.py` — 149 ICD codes (dotted + normalized), detect_dx_format, verify_hl_cohort (5 stages), check_dx_type_mismatches, enrollment_crosscheck, build_cohort_summary_df
- `scripts/validate_all.py` — Added cohort imports, _section_cohort() for report Section 5, cohort verification in main(), updated console summary with HL cohort union count and enrollment coverage

## Decisions Made
- Cohort verification added as Section 5 (not Section 4 as plan assumed) because Plan 01 already created 4 sections in the structural validation report — renumbering would break existing section references
- DX format detection samples first 1000 non-null DX values to determine dotted vs undotted format, then selects appropriate code set for matching
- All join keys (ID, ENCOUNTERID) cast to pl.String to prevent type mismatch errors across tables
- ICD version classification uses the normalized _DX_MATCH column internally for consistent prefix matching regardless of original DX format

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Section numbering adjusted from 4 to 5**
- **Found during:** Task 2 (report integration)
- **Issue:** Plan specified "Section 4: HL Cohort Verification" but Plan 01 already created 4 report sections (Schema, Integrity, Completeness, Missing Values)
- **Fix:** Added cohort as Section 5 instead of Section 4 to avoid renumbering existing sections
- **Files modified:** scripts/validate_all.py
- **Verification:** ToC updated with all 5 sections
- **Committed in:** c4d0955 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minor numbering change. No scope creep. All planned content delivered.

## Issues Encountered
None.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Full structural validation and cohort verification pipeline complete
- User needs to run `python scripts/validate_all.py` in an HPC interactive session to execute against real data
- Three output files generated: `reports/structural_validation.md` (5 sections), `reports/completeness_by_partner.csv`, `reports/cohort_summary.csv`
- Phase 3 delivers all diagnostic outputs needed before Phase 4 (data cleaning)

## Self-Check: PASSED

- FOUND: src/validate/cohort.py
- FOUND: scripts/validate_all.py
- FOUND: commit 644120a (Task 1)
- FOUND: commit c4d0955 (Task 2)

---
*Phase: 03-structural-validation-hl-cohort-verification*
*Completed: 2026-02-27*
