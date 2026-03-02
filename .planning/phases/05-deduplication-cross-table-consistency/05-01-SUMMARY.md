---
phase: 05-deduplication-cross-table-consistency
plan: 01
subsystem: data-quality
tags: [polars, dedup, composite-key, cross-table, partner-harmonization, enrollment]

requires:
  - phase: 04-value-temporal-validation
    provides: validated Parquet files with _val_ flags, PATID_COL/TUMOR_REGISTRY_TABLES constants
provides:
  - src/clean/dedup.py with flag_duplicates, check_demographic_consistency, flag_events_outside_encounters, check_death_consistency, write_cleaned
  - src/clean/harmonize.py with add_partner_flags, flag_encounters_outside_enrollment, flag_no_enrollment
  - DEDUP_KEYS composite keys for 6 CDM tables
  - EVENT_DATE_COLS mapping for 10 event tables
  - CLEAN_FLAG_COLS and CLEAN_FLAG_PREFIX for Phase 5 flag identification
affects: [05-02, scripts/clean_all.py, reports]

tech-stack:
  added: []
  patterns: [composite-key dedup via DataFrame.is_duplicated(), cross-table join consistency, partner provenance flags via is_in(set), lazy enrollment coverage check]

key-files:
  created:
    - src/clean/__init__.py
    - src/clean/dedup.py
    - src/clean/harmonize.py
  modified: []

key-decisions:
  - "flag_duplicates uses df.select(subset).is_duplicated() not pl.struct — simpler, same semantics"
  - "IS_DUPLICATE marks ALL occurrences (both first and subsequent) for unambiguous flag semantics"
  - "Null keys do not match each other (null != null) — correct dedup behavior"
  - "Events-outside-encounters flag is 0 when ENCOUNTERID/ADMIT_DATE/event_date is null (cannot assess)"
  - "DISCHARGE_DATE null treated as open-ended window (only lower bound checked)"
  - "TR date parsing uses multi-format fallback chain: MM/DD/YYYY, DATE9, YYYYMMDD"
  - "Partner flags added to ALL tables with SOURCE column, not just DIAGNOSIS"
  - "Enrollment coverage uses lazy evaluation + group_by collapse to manage many-to-many join"
  - "flag_no_enrollment uses anti-join with Python list for is_in (avoids deprecated Series path)"

patterns-established:
  - "Phase 5 clean flags: IS_DUPLICATE, ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY + _con_ prefix for consistency flags"
  - "drop_existing_clean_flags() for idempotent Phase 5 re-runs (mirrors Phase 4 drop_existing_flags)"
  - "write_cleaned() for snappy Parquet write-back with Phase 5 flag stats"

requirements-completed: [REQ-03]

duration: 6min
completed: 2026-03-02
---

# Phase 5 Plan 01: Core Modules Summary

**Composite-key dedup flagging for 6 tables, cross-table consistency checks (demographic/temporal/death), partner provenance flags (ICD_MAPPED/CLAIMS_ONLY/DEATH_ONLY), and insurance enrollment coverage validation**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-03-02T09:55:42Z
- **Completed:** 2026-03-02T10:02:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Composite-key dedup flagging for DIAGNOSIS, PROCEDURES, LAB_RESULT_CM, ENCOUNTER, VITAL, PRESCRIBING via DataFrame.is_duplicated() — marks ALL duplicate rows
- Cross-table consistency: demographic multi-birth-date/multi-sex detection, events-outside-encounter-window flagging (±1 day tolerance), death date consistency across DEATH and TUMOR_REGISTRY tables
- Partner provenance flags (ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY) using is_in() with Python sets on SOURCE column
- Insurance enrollment coverage: encounters outside any enrollment window, patients with zero enrollment records
- Idempotent re-run support via drop_existing_clean_flags() and write_cleaned() with snappy Parquet

## Task Commits

Each task was committed atomically:

1. **Task 1: Create dedup flagging and cross-table consistency module** - `1f26f76` (feat)
2. **Task 2: Create partner harmonization and insurance consistency module** - `1026a11` (feat)

## Files Created/Modified
- `src/clean/__init__.py` - Empty package initializer
- `src/clean/dedup.py` - Dedup flagging (DEDUP_KEYS, flag_duplicates), cross-table consistency (check_demographic_consistency, flag_events_outside_encounters, check_death_consistency), idempotent cleanup (drop_existing_clean_flags), write helper (write_cleaned)
- `src/clean/harmonize.py` - Partner provenance flags (add_partner_flags, PARTNER_FLAGS), insurance consistency (flag_encounters_outside_enrollment, flag_no_enrollment)

## Decisions Made
- flag_duplicates uses df.select(subset).is_duplicated() rather than pl.struct — simpler API, identical semantics
- IS_DUPLICATE marks ALL occurrences (first + subsequent) for unambiguous interpretation
- Null keys treated as non-matching (null != null) — correct dedup behavior, documented
- Events-outside-encounters uses ±1 day tolerance with null-safe logic (flag=0 when cannot assess)
- TR date parsing uses multi-format fallback chain matching Phase 4 patterns
- Partner flags applied to ALL tables with SOURCE column (informational for any downstream analysis)
- Enrollment coverage uses lazy evaluation + group_by collapse to handle many-to-many join safely

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Core dedup and consistency functions ready for Plan 02 (entry point script and reports)
- DEDUP_KEYS and EVENT_DATE_COLS constants ready for script-level iteration over tables
- write_cleaned() ready for Parquet write-back after applying all Phase 5 flags

## Self-Check: PASSED

- [x] src/clean/__init__.py — FOUND
- [x] src/clean/dedup.py — FOUND
- [x] src/clean/harmonize.py — FOUND
- [x] Commit 1f26f76 — FOUND (Task 1)
- [x] Commit 1026a11 — FOUND (Task 2)

---
*Phase: 05-deduplication-cross-table-consistency*
*Completed: 2026-03-02*
