---
phase: 04-hl-specific-value-temporal-validation
plan: 01
subsystem: validation
tags: [polars, pcornet-cdm, icd-concordance, plausibility, tumor-registry, parquet]

requires:
  - phase: 02-sas-to-parquet-conversion
    provides: Parquet files with all CDM table data
  - phase: 03-structural-cohort-validation
    provides: PATID_COL, SMALL_CELL_THRESHOLD constants; validated table schemas
provides:
  - 12 validation functions in src/validate/values.py
  - Value set lookup from valuesets.csv
  - Vital sign and lab plausibility checks with wide biological ranges
  - ICD version-date concordance with grace period and partner auto-detection
  - Per-table temporal consistency checks
  - HL-specific tumor registry validation (histology, staging, B-symptoms)
  - Idempotent flag drop/re-add via drop_existing_flags
  - Write-back helper preserving snappy compression
affects: [04-02, phase-4-entry-point, reports]

tech-stack:
  added: []
  patterns: [binary-flag-columns, _val_-infix-naming, chained-when-then-otherwise, _ensure_float-casting]

key-files:
  created: [src/validate/values.py]
  modified: []

key-decisions:
  - "Wide vital ranges (HT 50-272cm, WT 1-500kg) to minimize false positives"
  - "20 LOINC codes covering CBC, liver function, TSH, ESR, CRP with wide biological ranges"
  - "ICD grace period Jul 2015 - Jan 2016; AMS/UMI always treated as mapped partners"
  - "Value set validation skips fields with >200 valid values (loosely-coded fields)"
  - "B-symptom probing: check B_SYMPTOMS first, fall back to CS_SSF1"
  - "Primary site check is informational (non-lymph-node sites possible in some HL)"

patterns-established:
  - "_val_ infix naming: all flag columns contain _val_ for programmatic detection"
  - "Binary Int8 flags: 0=pass/null, 1=flagged — never deletes or corrects data"
  - "_ensure_float: always cast potentially-String numeric columns before range checks"
  - "Guard clauses: each function returns df unchanged if required columns are absent"

requirements-completed: [REQ-02, REQ-03, REQ-04, REQ-05]

duration: ~8min
completed: 2026-02-27
---

# Phase 4 Plan 01: Value & Temporal Validation Functions Summary

**12 validation functions covering PCORnet value sets, vital/lab plausibility (20 LOINC codes), ICD concordance with grace period, temporal encounter checks, and HL-specific tumor registry validation**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-02-27T18:36:57Z
- **Completed:** 2026-02-27T18:45:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Created complete validation function library (585 lines) with 12 exported functions and 5+ constant dictionaries
- Value set validation reads valuesets.csv and checks all coded fields, skipping loosely-coded columns (>200 values)
- Lab plausibility covers 20 HL-relevant LOINC codes with wide biological ranges; missing RESULT_UNIT flagged separately
- ICD concordance handles Oct 2015 transition with 3-month grace period and auto-detects mapped partners beyond known AMS/UMI
- Tumor registry checks validate HL histology (9650-9667), AJCC staging, B-symptoms, age range, treatment timing, and primary site

## Task Commits

Each task was committed atomically:

1. **Task 1: Value set validation, plausibility checks, and utility functions** - `26b0acb` (feat)
2. **Task 2: ICD concordance, temporal, tumor registry, and write-back functions** - `18e1a6f` (feat)

## Files Created/Modified
- `src/validate/values.py` — All 12 validation functions, constants, and utility helpers

## Decisions Made
- Wide vital sign ranges chosen to minimize false positives on real clinical data (e.g., HT 50-272cm covers premature infants to tallest recorded)
- Value set validation skips fields with >200 valid values to avoid false-flagging loosely-coded columns per Pitfall 2
- B-symptom column probing handles NAACCR naming variation (B_SYMPTOMS vs CS_SSF1)
- PRIMARY_SITE lymph node check is informational — non-C77x sites occur in some HL presentations
- Snappy compression used for write-back to match Phase 2 convention

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
- Polars not installed on local Windows Python; installed for verification (HPC conda env has it)
- Git 2.28 on Windows has `--trailer` flag injected by tooling; worked around via commit message files

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness
- All validation functions ready for Phase 4 Plan 02 (entry-point script and report generation)
- Entry-point script will iterate tables, call relevant functions, and produce validation reports
- drop_existing_flags enables safe re-runs without duplicate flag columns

---
*Phase: 04-hl-specific-value-temporal-validation*
*Completed: 2026-02-27*
