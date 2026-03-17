---
phase: 03-structural-validation-hl-cohort-verification
plan: 01
subsystem: data-validation
tags: [polars, parquet, schema-comparison, referential-integrity, completeness, pcornet-cdm, heatmap, unicode]

requires:
  - phase: 02-csv-to-parquet-conversion
    provides: "convert.py (Parquet files with typed dates), convert_all.py (batch pipeline), file_inventory.csv"
  - phase: 01-environment-extension-data-staging
    provides: "config.py (Paths dataclass with parquet_dir), schema.py (parse_datastructure)"
provides:
  - "structural.py module with 9 validation functions and 7 constants"
  - "validate_all.py entry point orchestrating schema, integrity, completeness, and missing value checks"
  - "reports/structural_validation.md (sections 1-4: schema, integrity, completeness, missing values)"
  - "reports/completeness_by_partner.csv (one row per table+column+partner)"
affects: [03-02-hl-cohort-verification, 04-data-cleaning, 05-analysis]

tech-stack:
  added: []
  patterns:
    - "pl.read_parquet_schema() for schema-only reads without loading data"
    - "pl.scan_parquet() lazy evaluation for all integrity and completeness checks"
    - "Anti-join (how='anti') for orphan detection in PATID and ENCOUNTERID"
    - "String-cast join keys (cast(pl.String)) to prevent type mismatch errors"
    - "group_by + unpivot for long-form per-partner completeness"
    - "Unicode block characters (█▓▒░·○) for markdown completeness heatmap"
    - "PCORnet missing value classification (NI/UN/OT/empty/null)"

key-files:
  created:
    - src/validate/__init__.py
    - src/validate/structural.py
    - scripts/validate_all.py
  modified: []

key-decisions:
  - "DatasetCoverPage parser is format-adaptive with BOM handling — probes for table name section markers and tab-delimited variable names at runtime"
  - "TUMOR_REGISTRY tables get column-count validation only (not CDM schema comparison) — they follow NAACCR not PCORnet"
  - "CHP LAB_RESULT_CM ENCOUNTERID exception implemented via skip_partner parameter — documents known data limitation"
  - "Partner column fallback chain: SOURCE → SITE → overall (no stratification) — handles column name variability across tables"
  - "Missing value classifier counts per string column rather than per group_by partner — simpler and sufficient for QC"
  - "Per-table completeness heatmap truncated to 20 columns in report for readability — full data in CSV"

patterns-established:
  - "validate module structure: src/validate/ package with function-per-check design"
  - "Report generation: section builder functions (_section_schema, _section_integrity, etc.) assembled into single markdown"
  - "Flag-but-show pattern for small cells: actual counts displayed with ⚠ marker for internal QC"

requirements-completed: [REQ-01, REQ-03, REQ-04, REQ-05]

duration: 8min
completed: 2026-02-27
---

# Phase 3 Plan 01: Structural Validation Summary

**Schema comparison, PATID/ENCOUNTERID integrity anti-joins, per-partner completeness heatmaps, and PCORnet missing value classification across 22 Parquet tables using Polars lazy evaluation**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-02-27T17:32:29Z
- **Completed:** 2026-02-27T17:45:00Z
- **Tasks:** 2
- **Files created:** 3

## Accomplishments
- Created `structural.py` module (320 lines) with 9 exported functions and 7 constants covering schema comparison, referential integrity, completeness profiling, and missing value classification
- Created `validate_all.py` entry point (330 lines) that orchestrates all validation checks and generates two output files: `reports/structural_validation.md` (4 sections) and `reports/completeness_by_partner.csv`
- Format-adaptive DatasetCoverPage parser handles BOM and probes tab-delimited sections at runtime
- All integrity checks use Polars lazy evaluation with String-cast join keys to prevent type mismatches

## Task Commits

Each task was committed atomically:

1. **Task 1: Create structural validation module** - `d91dfb4` (feat)
2. **Task 2: Create entry point and report generation** - `133c20e` (feat)

## Files Created/Modified
- `src/validate/__init__.py` — Package marker for validate module
- `src/validate/structural.py` — 9 validation functions (parse_cover_page, validate_table_schema, check_patid_uniqueness, check_patid_integrity, check_encounterid_integrity, completeness_by_partner, classify_missing_values, completeness_heatmap_symbol, flag_small_cell) + 7 constants
- `scripts/validate_all.py` — Entry point orchestrating all checks, generating reports/structural_validation.md and reports/completeness_by_partner.csv

## Decisions Made
- DatasetCoverPage parser is format-adaptive — probes for known table names as section markers, tries tab-delimited parsing, collects variable names matching identifier patterns
- TUMOR_REGISTRY tables validated by column count and key variable presence only (NAACCR schema, not PCORnet CDM)
- CHP LAB_RESULT_CM ENCOUNTERID exception via `skip_partner` parameter on `check_encounterid_integrity()`
- Partner column fallback: SOURCE → SITE → overall completeness (handles column name variability)
- Per-table heatmap capped at 20 columns in markdown report for readability; full granularity preserved in CSV
- Missing value classifier operates per-column (not per-partner) for simplicity — partner-stratified completeness already captured separately

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Validation infrastructure ready for Phase 3 Plan 02 (HL cohort verification)
- `src/validate/structural.py` constants (PATID_COL, ENCOUNTER_LINKED_TABLES, etc.) available for reuse
- User needs to run `python scripts/validate_all.py` in an HPC interactive session to execute validation against real data
- Report will be generated at `reports/structural_validation.md` with companion `reports/completeness_by_partner.csv`

## Self-Check: PASSED

- FOUND: src/validate/__init__.py
- FOUND: src/validate/structural.py
- FOUND: scripts/validate_all.py
- FOUND: commit d91dfb4 (Task 1)
- FOUND: commit 133c20e (Task 2)

---
*Phase: 03-structural-validation-hl-cohort-verification*
*Completed: 2026-02-27*
