---
phase: 06-data-quality-report-clean-dataset-assembly
plan: 02
subsystem: report
tags: [polars, assemble-clean, parquet, DQ-report, HIPAA]

# Dependency graph
requires:
  - phase: 06-data-quality-report-clean-dataset-assembly
    plan: 01
    provides: build_patient_level_derived, aggregate_dq_metrics, generate_cleaning_decisions_content
provides:
  - scripts/assemble_clean.py as Phase 6 entry point
  - parquet_clean/ with snappy-compressed Parquet copies
  - derived/patient_level.parquet
  - reports/DATA_QUALITY_REPORT.md (completeness, conformance, plausibility, persistence)
  - reports/CLEANING_DECISIONS.md
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: flag_small_cell for all aggregate counts, derive output paths from parquet_dir.parent

key-files:
  created: [hpc-upload/scripts/assemble_clean.py, hpc-upload/reports/DATA_QUALITY_REPORT.md, hpc-upload/reports/CLEANING_DECISIONS.md, hpc-upload/reports/figures/]
  modified: []

key-decisions:
  - "parquet_clean_dir and derived_dir derived from paths.parquet_dir.parent (do not modify config)"
  - "Snappy compression throughout per HPC learnings"

patterns-established:
  - "Mirror clean_all.py/validate_values.py: load_config, parse_datastructure, _build_table_map"

requirements-completed: [REQ-03, REQ-04, REQ-05, REQ-06]

# Metrics
duration: ~8min
completed: 2026-03-02
---

# Phase 6 Plan 02: Assemble Clean & Reports Summary

**Phase 6 entry-point script assembling validated Parquet to parquet_clean/, building patient_level.parquet, and generating DATA_QUALITY_REPORT.md and CLEANING_DECISIONS.md with HIPAA-compliant small cell suppression**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-02T20:01:05Z
- **Completed:** 2026-03-02T20:09:00Z
- **Tasks:** 2
- **Files modified:** 4 created

## Accomplishments

- `scripts/assemble_clean.py` orchestrates: copy Parquet to parquet_clean with snappy compression, build patient_level.parquet, generate DQ and cleaning-decision reports
- DATA_QUALITY_REPORT.md with 5 sections: Overview, Completeness (stratified by SOURCE), Conformance, Plausibility, Persistence
- CLEANING_DECISIONS.md documents valuesets, plausibility ranges, temporal rules, DEDUP_KEYS, partner flags, masked values, INSURANCE_CONTINUITY, SMALL_CELL_THRESHOLD
- flag_small_cell applied to all aggregate counts in reports
- reports/figures/ directory for optional completeness heatmaps

## Task Commits

Each task was committed atomically:

1. **Task 1: Create assemble_clean entry point and Parquet assembly** - `8b51b00` (feat)
2. **Task 2: Generate DATA_QUALITY_REPORT and CLEANING_DECISIONS** - `b8659d7` (feat)

## Files Created/Modified

- `hpc-upload/scripts/assemble_clean.py` - Phase 6 entry point: copy to parquet_clean, build patient_level, generate reports
- `hpc-upload/reports/DATA_QUALITY_REPORT.md` - DQ report with 4 dimensions stratified by partner
- `hpc-upload/reports/CLEANING_DECISIONS.md` - Cleaning rules documentation
- `hpc-upload/reports/figures/` - Directory for optional completeness heatmap figures

## Decisions Made

None - followed plan as specified. PATID_COL="ID" used throughout via quality_report; output paths derived from parquet_dir.parent.

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED
