---
phase: 06-data-quality-report-clean-dataset-assembly
plan: 01
subsystem: report
tags: [polars, quality-report, derived-vars, DQ-aggregation]

# Dependency graph
requires:
  - phase: 04-hl-specific-value-temporal-validation
    provides: _compute_hl_timeline pattern, _val_* flags
  - phase: 05-dedup-consistency-harmonization
    provides: DEDUP_KEYS, partner flags
provides:
  - build_patient_level_derived() for HL patient-level derived variables
  - aggregate_dq_metrics() for completeness, conformance, plausibility, persistence
  - generate_cleaning_decisions_content() for CLEANING_DECISIONS markdown
affects: 06-02 (entry-point script)

# Tech tracking
tech-stack:
  added: []
  patterns: _compute_hl_timeline reuse, flag_small_cell/_suppress, is_in implode()

key-files:
  created: [hpc-upload/src/report/__init__.py, hpc-upload/src/report/quality_report.py]
  modified: []

key-decisions:
  - "Reused validate_values _compute_hl_timeline logic; did not extract shared fn"
  - "INSURANCE_CONTINUITY=1 when gap >30 days in enrollment; no enrollment → 1"

patterns-established:
  - "Derived vars via cross-table joins: DIAGNOSIS→first_dx, PROCEDURES/PRESCRIBING/TR→first_tx"
  - "DQ metrics return raw counts; Plan 02 applies flag_small_cell when writing"

requirements-completed: [REQ-03, REQ-04, REQ-05, REQ-06]

# Metrics
duration: ~12min
completed: 2026-03-02
---

# Phase 6 Plan 01: Derived Variables & DQ Aggregation Summary

**Derived-variables module and DQ aggregation functions for HL patient-level assembly and data quality reporting, reusing _compute_hl_timeline pattern and structural/cohort/values imports**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-02T19:51:31Z
- **Completed:** 2026-03-02T20:05:00Z
- **Tasks:** 2
- **Files modified:** 2 created

## Accomplishments

- `build_patient_level_derived(table_map)` produces one row per HL patient with 9 derived variables: AGE_AT_HL_DX, AGE_BAND, HL_SUBTYPE, FIRST_HL_DX_DATE, FIRST_HL_TX_DATE, DX_TO_TX_DAYS, PAYER_AT_DX, INSURANCE_CONTINUITY, REGION
- `aggregate_dq_metrics(table_map, reports_dir)` returns dict with completeness, conformance, plausibility, persistence dimensions
- `generate_cleaning_decisions_content()` returns 51 markdown lines documenting valuesets, plausibility ranges, temporal rules, DEDUP_KEYS, partner flags, masked values, TR date formats, INSURANCE_CONTINUITY, SMALL_CELL_THRESHOLD

## Task Commits

Each task was committed atomically:

1. **Task 1: Create derived-variables module** - `a0bb60d` (feat)
2. **Task 2: Add DQ aggregation functions** - `2ad6fb6` (feat)

## Files Created/Modified

- `hpc-upload/src/report/__init__.py` - Package init
- `hpc-upload/src/report/quality_report.py` - build_patient_level_derived, aggregate_dq_metrics, generate_cleaning_decisions_content, _suppress

## Decisions Made

None - followed plan as specified. Used PATID_COL="ID", is_in(implode()) for HL filtering, TR date fallback chain (YYYY.MM.DD, MM/DD/YYYY, %d%b%Y, %Y%m%d).

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- hpc-upload/src/report/__init__.py: FOUND
- hpc-upload/src/report/quality_report.py: FOUND
- Commit a0bb60d: FOUND
- Commit 2ad6fb6: FOUND
