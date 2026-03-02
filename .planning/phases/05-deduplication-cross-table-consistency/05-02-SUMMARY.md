---
phase: 05-deduplication-cross-table-consistency
plan: 02
subsystem: data-quality
tags: [polars, dedup, cross-table, partner-harmonization, enrollment, reports, hipaa]

requires:
  - phase: 05-deduplication-cross-table-consistency
    plan: 01
    provides: src/clean/dedup.py (flag_duplicates, DEDUP_KEYS, EVENT_DATE_COLS, check_demographic_consistency, flag_events_outside_encounters, check_death_consistency, write_cleaned), src/clean/harmonize.py (add_partner_flags, PARTNER_FLAGS, flag_encounters_outside_enrollment, flag_no_enrollment)
  - phase: 04-value-temporal-validation
    provides: validated Parquet files with _val_ flags, icd_concordance.csv
provides:
  - scripts/clean_all.py orchestrating Phase 5 dedup + consistency + partner flags across all 22 tables
  - reports/dedup_report.md with per-table and per-partner duplicate rates
  - reports/consistency_report.md with demographics, event-encounter, death, enrollment findings
  - reports/partner_harmonization.md with ICD_MAPPED/CLAIMS_ONLY/DEATH_ONLY partner summaries
affects: [reports, parquet files]

tech-stack:
  added: []
  patterns: [Phase 5 entry-point script following Phase 4 validate_values.py pattern, three-report markdown generation with HIPAA small-cell suppression]

key-files:
  created:
    - scripts/clean_all.py
  modified: []

key-decisions:
  - "Report generation functions defined in the entry-point script (not a separate module) for simplicity"
  - "flag_small_cell() used for all markdown report counts (warning marker for 1-10)"
  - "_suppress() used for CSV counts (dash for 1-10) — identical to Phase 4 pattern"
  - "partner_dedup stored as DataFrame in stats dict for lazy per-partner iteration"
  - "Reference tables (ENCOUNTER, ENROLLMENT) loaded once and reused across loop iterations"
  - "Reports include table of contents, metadata header, and methodology notes"

patterns-established:
  - "Phase 5 entry point: scripts/clean_all.py (mirrors scripts/validate_values.py)"
  - "Three-report pattern: dedup_report.md + consistency_report.md + partner_harmonization.md"
  - "Report metadata header: title, generated timestamp, data source, parquet dir, tables processed"

requirements-completed: [REQ-03, REQ-04, REQ-05]

duration: 6min
completed: 2026-03-02
---

# Phase 5 Plan 02: Entry Point & Reports Summary

**Phase 5 entry-point script orchestrating dedup/consistency/partner flagging across all 22 tables with three HIPAA-compliant markdown reports for duplicate rates, cross-table consistency, and partner harmonization**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-03-02T10:04:17Z
- **Completed:** 2026-03-02T10:11:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Entry-point script (640 lines) orchestrating Phase 5 pipeline: load config → build table map → load reference tables → iterate 22 tables applying dedup/partner/consistency flags → write flagged Parquet → cross-table summary checks → generate 3 reports
- Dedup report with per-table overview (total rows, duplicates, rate, keys used), per-partner duplicate rates, and methodology documentation
- Consistency report covering demographics (multi-birth-date/multi-sex), events outside encounter windows (±1 day tolerance), death date consistency, and insurance enrollment coverage
- Partner harmonization report with flag summary across tables, ICD_MAPPED/CLAIMS_ONLY/DEATH_ONLY partner-specific sections, and Phase 4 icd_concordance.csv cross-reference

## Task Commits

Each task was committed atomically:

1. **Task 1: Create entry point with main loop and Parquet write-back** - `a5e9016` (feat)
2. **Task 2: Add report generation for three markdown reports** - `f6fc71b` (feat)

## Files Created/Modified
- `scripts/clean_all.py` - Phase 5 entry point: main cleaning loop + three report generation functions (_generate_dedup_report, _generate_consistency_report, _generate_partner_report)

## Decisions Made
- Report generation functions defined in the entry-point script rather than a separate module, matching the Phase 4 pattern
- flag_small_cell() from structural.py used for all markdown report counts (HIPAA compliance)
- Reference tables (ENCOUNTER, ENROLLMENT) loaded once before the main loop for efficiency
- partner_dedup stored as a Polars DataFrame in the stats dict for flexible per-partner iteration in reports

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Phase 5 complete: all dedup, cross-table consistency, partner harmonization, and insurance coverage checks implemented
- Running `python scripts/clean_all.py config/paths.toml` on HPC will produce flagged Parquet files and three reports
- All Phase 5 flag columns (IS_DUPLICATE, ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY, _con_*) are additive Int8 — no records deleted

## Self-Check: PASSED

- [x] scripts/clean_all.py — FOUND
- [x] Commit a5e9016 — FOUND (Task 1)
- [x] Commit f6fc71b — FOUND (Task 2)

---
*Phase: 05-deduplication-cross-table-consistency*
*Completed: 2026-03-02*
