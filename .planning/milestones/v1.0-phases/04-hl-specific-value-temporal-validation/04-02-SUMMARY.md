---
phase: 04-hl-specific-value-temporal-validation
plan: 02
subsystem: validation
tags: [polars, pcornet-cdm, icd-concordance, temporal, parquet, hipaa, small-cell-suppression]

requires:
  - phase: 04-hl-specific-value-temporal-validation
    plan: 01
    provides: 12 validation functions in src/validate/values.py
  - phase: 03-structural-cohort-validation
    provides: PATID_COL, SMALL_CELL_THRESHOLD, TUMOR_REGISTRY_TABLES, flag_small_cell
  - phase: 02-sas-to-parquet-conversion
    provides: Parquet files with all CDM table data
provides:
  - Phase 4 entry point script (scripts/validate_values.py) orchestrating all validation
  - Per-table validation loop applying value set, plausibility, ICD concordance, temporal checks
  - Cross-table birth/death temporal checks with masked birth date recovery from TUMOR_REGISTRY
  - HL disease timeline summary (DX-to-treatment timing via PROCEDURES CPTs and TR dates)
  - Four report files in reports/ directory (markdown + 3 CSVs)
  - ICD concordance CSV with per-partner pre-transition ICD-10 breakdown
  - Small-cell suppression on all aggregate counts (HIPAA compliance)
affects: [phase-5, downstream-analysis]

tech-stack:
  added: []
  patterns: [entry-point-orchestration, cross-table-temporal-joins, masked-date-recovery, small-cell-csv-suppression]

key-files:
  created: [scripts/validate_values.py]
  modified: []

key-decisions:
  - "HL treatment CPTs: stem cell transplant (38240-38242), bone marrow harvest (38230/38232), radiation (77385-77412)"
  - "PRESCRIBING included in HL timeline for completeness; filtered to HL patients only"
  - "Masked birth date recovery: approximate birth year = DATE_OF_DIAGNOSIS year - AGE_AT_DIAGNOSIS"
  - "Pre-transition ICD-10 count added to concordance CSV for mapped partner analysis"
  - "Small-cell suppression in CSVs replaces counts 1-10 with dash; markdown uses warning marker"
  - "Birth/death temporal checks skip DEMOGRAPHIC and DEATH but include TUMOR_REGISTRY tables"

patterns-established:
  - "Entry-point orchestration: load config → build lookups → validation loop → cross-table analysis → reports"
  - "Cross-table temporal joins: rename lookup columns (_LOOKUP_BD/_LOOKUP_DD) to avoid column collisions"
  - "Report data dict: write_validated stats + rows_with_any_flag for report assembly"
  - "CSV suppression: _suppress() replaces 1-10 with dash for HIPAA; separate from flag_small_cell warning marker"

requirements-completed: [REQ-02, REQ-03, REQ-04, REQ-05]

duration: ~10min
completed: 2026-02-27
---

# Phase 4 Plan 02: Entry Point Script and Report Generation Summary

**Phase 4 entry point orchestrating all 12 validation functions across 22 tables with cross-table birth/death temporal checks, HL disease timeline, ICD concordance CSV, and 4 report files with HIPAA small-cell suppression**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-02-27T18:45:36Z
- **Completed:** 2026-02-27T18:55:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Created 1263-line entry point script that processes all 22 CDM tables through the validation pipeline
- Per-table loop applies value set validation, table-specific checks (vital/lab plausibility, ICD concordance, encounter temporal, enrollment dates, tumor registry), universal future-date checks, and cross-table birth/death temporal checks
- Masked birth date recovery from TUMOR_REGISTRY: computes approximate birth year from AGE_AT_DIAGNOSIS + DATE_OF_DIAGNOSIS for patients with BIRTH_DATE = 1900-01-01
- HL disease timeline computes first-DX-to-first-treatment days across PROCEDURES (stem cell/radiation CPTs) and TUMOR_REGISTRY treatment dates
- Four report outputs: value_validation.md (6-section markdown), icd_concordance.csv (per-partner with pre-transition ICD-10), temporal_issues.csv, tumor_registry_validation.csv
- HIPAA-compliant small-cell suppression: counts 1-10 replaced with dash in CSVs, warning marker in markdown

## Task Commits

Each task was committed atomically:

1. **Task 1: Entry point script with per-table validation loop and cross-table temporal analysis** - `511f7b9` (feat)
2. **Task 2: Report generation — pre-transition ICD-10 concordance and CSV outputs** - `d5d259d` (feat)

## Files Created/Modified

- `scripts/validate_values.py` — Phase 4 entry point: validation loop, 7 helpers, 6 report section builders, 3 CSV writers, main()

## Decisions Made

- HL treatment CPTs defined as constant set covering stem cell transplant, bone marrow harvest, and radiation delivery codes
- PRESCRIBING dates included in HL timeline analysis (filtered to HL patients); noise acknowledged but provides completeness
- Birth/death lookup columns renamed to _LOOKUP_BD/_LOOKUP_DD to prevent column name collisions during left joins
- Pre-transition ICD-10 counts (ICD-10 codes before Oct 2015) added to concordance breakdown for identifying mapped partners
- CSV small-cell suppression uses _suppress() (returns dash string) vs markdown's flag_small_cell (returns count with warning marker)

## Deviations from Plan

None — plan executed as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 4 is complete: all validation functions (Plan 01) and entry point script with reports (Plan 02) are ready
- Script is runnable via `python scripts/validate_values.py [config/paths.toml]` on HPC
- Four report files will be generated in reports/ directory when run against real data
- All Parquet files will have binary flag columns (_val_ infix) added in-place

---
*Phase: 04-hl-specific-value-temporal-validation*
*Completed: 2026-02-27*
