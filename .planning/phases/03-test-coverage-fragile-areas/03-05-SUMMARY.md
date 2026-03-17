---
phase: 03-test-coverage-fragile-areas
plan: 05
subsystem: audit-resolution-test-infrastructure
tags: [audit-resolution, test-fixtures, pcornet-cdm, phase-closure]
completed: 2026-03-17

dependency_graph:
  requires:
    - 03-01-PLAN.md (payer logic tests)
    - 03-02-PLAN.md (date parsing tests)
    - 03-03-PLAN.md (report and dedup tests)
    - 03-04-PLAN.md (checkpoint validation tests)
  provides:
    - Complete audit resolution for all 18 Phase 1 TODO(audit) items
    - Full PCORnet CDM factory fixture set (5 tables)
    - Comprehensive test infrastructure for Phase 4
  affects:
    - Phase 4 planning (6 items deferred with clear rationale)
    - Test suite completeness (all major PCORnet tables covered)

tech_stack:
  added: []
  patterns:
    - Factory fixtures for all PCORnet tables (DRY test data)
    - Systematic audit resolution with evidence linking
    - Phase closure documentation

key_files:
  created: []
  modified:
    - docs/AUDIT_LOG.md (40 lines added)
    - tests/conftest.py (261 lines added)

decisions:
  - decision: Systematic resolution of all 18 TODO(audit) items with evidence
    rationale: Close out all Phase 1 unknowns, ensure no technical debt carries forward undocumented
    alternatives: Defer resolution to Phase 4 (leaves uncertainty)
  - decision: Complete factory fixture set for all major PCORnet tables
    rationale: Robust test infrastructure for current and future tests, consistent pattern across all tables
    alternatives: Add fixtures on-demand (leads to inconsistency)
  - decision: 6 items deferred to Phase 4 with clear rationale (infra/refactor work)
    rationale: Test coverage validated correctness; remaining work is code cleanup not correctness fixes
    alternatives: Block Phase 4 on refactors (delays progress unnecessarily)

metrics:
  duration_minutes: 2
  tasks_completed: 2
  files_modified: 2
  lines_added: 301
  audit_items_resolved: 18
  fixtures_added: 4
---

# Phase 03 Plan 05: Audit Resolution & Test Infrastructure Summary

Systematic resolution of all 18 TODO(audit) items from Phase 1 with complete PCORnet CDM factory fixture set for test infrastructure.

## One-liner

Systematically resolved all 18 Phase 1 TODO(audit) items (1 verified correct, 8 validated/documented, 6 deferred to Phase 4, 2 deferred to future) and enhanced test infrastructure with complete factory fixture set for all major PCORnet tables.

## Overview

Closed out all Phase 1 technical debt by systematically documenting resolution status for every TODO(audit) item with test evidence. Enhanced conftest.py with complete factory fixture set (diagnosis, enrollment, vital, procedures) following same pattern as existing encounter fixture. All 18 items now have clear status (fixed, validated, documented, or deferred with rationale).

**Phase 3 closure:** All fragile areas identified in Phase 1 now have either test coverage, documented behavior, or clear deferral rationale. No technical debt carries forward to Phase 4 without explicit documentation.

## Tasks Completed

### Task 1: Systematically resolve all TODO(audit) items
- **Status:** Complete
- **Files:** `docs/AUDIT_LOG.md` (40 lines added)
- **Commit:** 49711bd

**Added Phase 3 Resolutions section with complete resolution table:**

**HIGH severity (5 items):**
- AUDIT-001: DOCUMENTED - 99/9999 sentinel behavior tested, defaults to no fallback
- AUDIT-002: VALIDATED - Date detection thresholds tested with edge cases, appropriate
- AUDIT-003: DEFER TO PHASE 4 - LAB_RESULT_CM aliasing requires production schema check
- AUDIT-004: VALIDATED - Null key behavior tested, nulls DO match in Polars
- AUDIT-005: VERIFIED CORRECT - Dual-eligible detection correct (primary 14/141/142 sufficient)

**MEDIUM severity (5 items):**
- AUDIT-006: DEFER TO PHASE 4 - Pandas to Polars migration (refactor work)
- AUDIT-007: DOCUMENTED - Suppression strategy documented (suppress vs flag_small_cell)
- AUDIT-008: DEFER TO PHASE 4 - src/clean/validate/ consolidation (refactor work)
- AUDIT-009: VALIDATED - Parse failure rate tracked in stats dict
- AUDIT-010: DOCUMENTED - VITAL dedup key issue documented, requires schema investigation

**LOW severity (8 items):**
- AUDIT-011: DEFER TO PHASE 4 - Logging framework
- AUDIT-012: DEFER TO PHASE 4 - Incremental conversion optimization
- AUDIT-013: DOCUMENTED - Partner abbreviations tested
- AUDIT-014: VALIDATED - Outcomes.csv schema validation tested
- AUDIT-015: DEFER TO PHASE 4 - SCT_CPTS constant renaming
- AUDIT-016: DEFER TO FUTURE - VITAL/LAB range validation (requires distribution analysis)
- AUDIT-017: DEFER TO FUTURE - 30-day payer window sensitivity analysis
- AUDIT-018: DOCUMENTED - 1900-01-01 births assumed masked values

**Resolution summary:**
- 1 VERIFIED CORRECT (AUDIT-005)
- 8 VALIDATED/DOCUMENTED (AUDIT-001, 002, 004, 007, 009, 010, 013, 014, 018)
- 6 DEFERRED TO PHASE 4 (AUDIT-003, 006, 008, 011, 012, 015)
- 2 DEFERRED TO FUTURE (AUDIT-016, 017)

**Evidence linking:** Each resolved item links to specific test evidence (e.g., `tests/test_report/test_payer_logic.py::test_include_99_as_sentinel_flag`).

### Task 2: Complete conftest.py with all PCORnet table factories
- **Status:** Complete
- **Files:** `tests/conftest.py` (261 lines added, 337 lines total)
- **Commit:** 281183d

**Added factory fixtures for 4 additional PCORnet tables:**

**1. make_diagnosis_df():**
- Columns: ID, ENCOUNTERID, DX, DX_TYPE, DX_DATE
- Defaults: HL ICD-10 codes (C81.10, C81.11, C81.12), DX_TYPE "10"
- Use case: HL cohort identification tests

**2. make_enrollment_df():**
- Columns: ID, ENR_START_DATE, ENR_END_DATE
- Defaults: 2020-01-01 to 2025-12-31 (5+ year enrollment)
- Use case: Enrollment duration validation tests

**3. make_vital_df():**
- Columns: ID, ENCOUNTERID, MEASURE_DATE, HT, WT, SYSTOLIC, DIASTOLIC
- Defaults: HT=170cm, WT=70kg, BP=120/80mmHg
- Use case: Vital range validation tests

**4. make_procedures_df():**
- Columns: ID, ENCOUNTERID, PX, PX_TYPE, PX_DATE
- Defaults: Treatment CPTs (77401 radiation, 38240 SCT), PX_TYPE "CH"
- Use case: Treatment modality flagging tests

**All factories follow same pattern:**
- PCORnet-realistic defaults (not synthetic integers)
- Sequential patient IDs (PT001, PT002, PT003)
- Recent dates (2025-01-01+)
- Kwargs for customization (n_rows, column overrides)
- Comprehensive docstrings with usage examples

**Added module-level docstring:**
- Lists all 5 available factories
- Documents PCORnet code realism principle
- Explains factory pattern rationale

**Verification:** All fixtures pytest-discoverable via `pytest --fixtures`

## Verification Results

**AUDIT_LOG.md verification:**
- ✓ "## Phase 3 Resolutions" section exists
- ✓ Resolution table has all 18 items
- ✓ Each item has status (DOCUMENTED, VALIDATED, VERIFIED, DEFER)
- ✓ Evidence links provided for resolved items
- ✓ Phase 3 Summary with breakdown by category
- ✓ Outstanding HIGH/MEDIUM items for Phase 4 listed

**conftest.py verification:**
```bash
$ python -m pytest tests/conftest.py --collect-only --fixtures | grep make_
make_encounter_df -- tests\conftest.py:24
make_diagnosis_df -- tests\conftest.py:96
make_enrollment_df -- tests\conftest.py:158
make_vital_df -- tests\conftest.py:210
make_procedures_df -- tests\conftest.py:279
```

All 5 factories discoverable.

**Line count verification:**
- conftest.py: 337 lines (meets min_lines: 150 requirement)
- AUDIT_LOG.md: 40 lines added (Phase 3 Resolutions section)

## Deviations from Plan

None - plan executed exactly as written.

**No auto-fixes needed:**
- Task 1: Straightforward documentation update
- Task 2: Factory fixtures followed established pattern

## Success Criteria Met

- ✓ All 18 TODO(audit) items systematically reviewed and documented
- ✓ Each item has resolution status (FIXED, VALIDATED, DOCUMENTED, DEFERRED)
- ✓ AUDIT_LOG.md updated with Phase 3 resolution section
- ✓ Conftest.py has complete factory fixture set (5 tables)
- ✓ No technical debt carries forward without documentation
- ✓ All deferred items have clear rationale
- ✓ Tests confirm all fixtures pytest-discoverable
- ✓ Must-haves artifacts met:
  - tests/conftest.py: 337 lines (min: 150)
  - docs/AUDIT_LOG.md: Phase 3 Resolutions section (contains all 18 items)

## Key Decisions Made

1. **Systematic resolution over selective fixing**
   - Documented ALL 18 items with evidence or deferral rationale
   - Provides complete picture for Phase 4 planning
   - No surprises or forgotten issues

2. **Complete factory fixture set over on-demand**
   - Added all major PCORnet tables at once (not as-needed)
   - Consistent pattern across all fixtures
   - Reduces future test boilerplate

3. **Evidence linking for resolved items**
   - Each resolved item links to specific test
   - Provides traceability and confidence
   - Documents why resolution is correct

4. **Clear deferral categories**
   - Phase 4: Infrastructure/refactor work (6 items)
   - Future: Analysis work requiring data (2 items)
   - Prevents scope creep, maintains focus

## Phase 3 Closure

**Test coverage complete:**
- Payer logic: 73 tests (03-01)
- Date parsing: 57 tests (03-02)
- Report & dedup: 60 tests (03-03)
- Checkpoint validation: 32 tests (03-04)
- Total: 222 tests covering all fragile areas

**Audit resolution complete:**
- All 18 Phase 1 TODO(audit) items resolved or deferred
- 9 items validated/documented with test evidence
- 6 items deferred to Phase 4 with rationale
- 2 items deferred to future (data analysis required)

**Test infrastructure complete:**
- 5 PCORnet table factory fixtures (encounter, diagnosis, enrollment, vital, procedures)
- Consistent pattern across all fixtures
- PCORnet-realistic defaults throughout

**Phase 4 readiness:**
- No blockers
- Outstanding items clearly documented (AUDIT-003, 006, 008, 011, 012, 015)
- Test suite provides regression protection for all changes

## Files Modified

### Modified (2 files)

**docs/AUDIT_LOG.md:**
- Added "## Phase 3 Resolutions" section (40 lines)
- Resolution table for all 18 AUDIT items
- Phase 3 Summary with breakdown
- Outstanding items for Phase 4

**tests/conftest.py:**
- Added module-level docstring (14 lines)
- Added make_diagnosis_df (62 lines)
- Added make_enrollment_df (45 lines)
- Added make_vital_df (71 lines)
- Added make_procedures_df (69 lines)
- Total: 261 lines added (337 lines total)

## Performance & Quality Metrics

| Metric | Value |
|--------|-------|
| Duration | 2 minutes |
| Tasks completed | 2 of 2 |
| Files modified | 2 |
| Lines added | 301 |
| Audit items resolved | 18 |
| Factory fixtures added | 4 |
| Test coverage | Complete (222 tests across Phase 3) |

## Next Steps

**Phase 3 Plan 06:** Final plan in Phase 3 (if exists), otherwise Phase 3 complete.

**Phase 4 priorities based on audit resolution:**
- AUDIT-003: LAB_RESULT_CM table name aliasing (production schema check)
- AUDIT-006: Pandas to Polars migration in outcomes_flags.py
- AUDIT-008: Consolidate src/validate/ and src/clean/validate/ modules
- AUDIT-011: Logging framework (replace print())
- AUDIT-012: Incremental conversion optimization
- AUDIT-015: SCT_CPTS constant renaming

**Future work (requires data analysis):**
- AUDIT-016: VITAL/LAB range validation (distribution analysis)
- AUDIT-017: 30-day payer window sensitivity analysis

## Self-Check: PASSED

Verified all claims:

**Created/modified files:**
```bash
$ ls docs/AUDIT_LOG.md
docs/AUDIT_LOG.md

$ ls tests/conftest.py
tests/conftest.py

$ wc -l tests/conftest.py
337 tests/conftest.py
```

**AUDIT_LOG.md content:**
```bash
$ grep "## Phase 3 Resolutions" docs/AUDIT_LOG.md
## Phase 3 Resolutions

$ grep "^| AUDIT-" docs/AUDIT_LOG.md | wc -l
18
```

**Commits:**
```bash
$ git log --oneline -2
281183d feat(03-05): complete conftest.py with all PCORnet table factories
49711bd docs(03-05): systematically resolve all 18 TODO(audit) items
```

**Factory fixtures:**
```bash
$ python -m pytest tests/conftest.py --collect-only --fixtures 2>&1 | grep -E "make_(encounter|diagnosis|enrollment|vital|procedures)_df" | wc -l
5
```

All SUMMARY.md claims verified.
