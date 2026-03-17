---
phase: 03-test-coverage-fragile-areas
plan: 04
subsystem: validation-checkpoints-harmonization
tags: [testing, validation, checkpoints, partner-flags, audit-resolution]
dependency_graph:
  requires: [TEST-04, Phase-02-validation-infrastructure]
  provides: [checkpoint-validation-tests, partner-flag-tests, outcomes-schema-validation]
  affects: [validation-module, clean-module, audit-log]
tech_stack:
  added: []
  patterns: [pytest-fixtures, polars-testing, schema-validation-tests]
key_files:
  created:
    - tests/test_validate/test_checkpoint.py
    - tests/test_clean/test_harmonize.py
    - tests/test_clean/test_outcomes_flags.py
  modified: []
decisions:
  - Use Polars Series with explicit dtype for test expectations (Int8 matching actual output)
  - Document schema validation behavior rather than adding explicit checks (pandas raises KeyError)
  - Reorganize outcomes tests to align with source module location (src/clean/outcomes_flags.py)
metrics:
  duration_minutes: 3
  completed_date: 2026-03-17
  tasks_completed: 2
  files_created: 3
  tests_added: 32
  lines_added: 685
---

# Phase 03 Plan 04: Checkpoint Validation & Partner Flag Tests Summary

Comprehensive test coverage for checkpoint validation, partner flags, and outcomes code lookup with schema validation.

## What Was Built

**Test coverage for Phase 2 checkpoint infrastructure and data cleaning logic:**
- 16 checkpoint validation tests covering row-count (strict/tolerance modes), schema validation (missing columns, wrong dtypes, dtype flexibility), and no-vanish detection
- 7 partner flag tests covering ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY assignment based on SOURCE column values
- 9 outcomes code lookup tests with schema validation for Outcomes.csv parsing

**Audit resolution:**
- AUDIT-013: Partner abbreviations (AMS, UMI, FLM, VRT) documented and tested
- AUDIT-014: Outcomes.csv schema validation documented and tested (KeyError on missing columns)

## Tasks Completed

### Task 1: Create Checkpoint Validation Tests
**Commit:** 28463c1

Created comprehensive tests for `src/validate/checkpoint.py` validation functions:

**Row-count validation (strict mode):**
- Exact match pass/fail scenarios
- Tests ensure tolerance=0.0 catches any deviation

**Row-count validation (tolerance mode):**
- Within-tolerance pass (98 vs 100, 2% tolerance)
- Exceeds-tolerance fail (95 vs 100, 2% tolerance)
- Gain detection (105 vs 100, 2% tolerance)

**No-vanish validation:**
- Catastrophic data loss detection (10 rows vs 50 minimum)
- Boundary condition (exactly 50 rows vs 50 minimum)

**Schema validation:**
- All columns present with correct dtypes
- Missing column detection (single and multiple)
- Wrong dtype detection (single and multiple)
- Dtype flexibility (tuple of allowed types)
- Extra columns allowed (non-strict mode)

**Files:**
- Created `tests/test_validate/test_checkpoint.py` (317 lines, 16 tests)

### Task 2: Create Partner Flag and Outcomes Tests
**Commit:** f4072da

Created tests for partner flag assignment and outcomes code lookup:

**Partner flag tests (`test_harmonize.py`):**
- ICD_MAPPED flag for AMS, UMI partners
- CLAIMS_ONLY flag for FLM partner
- DEATH_ONLY flag for VRT partner
- Unrecognized SOURCE values get no flags (all 0)
- Custom column name support
- PARTNER_FLAGS constant validation
- AUDIT-013 resolution: Documents partner abbreviations and adds TODO for production validation

**Outcomes code lookup tests (`test_outcomes_flags.py`):**
- Valid schema loading (Modality, Code system, Code columns)
- Forward-fill parsing (hierarchical CSV structure)
- Code normalization (uppercase, whitespace stripped)
- Empty file handling (returns empty dict)
- Multiple code systems per modality (CPT + LOINC + ICD-10)
- Unrecognized modality handling (skipped)
- Missing column behavior (raises KeyError)
- AUDIT-014 resolution: Documents expected schema and tests failure mode

**Files:**
- Created `tests/test_clean/test_harmonize.py` (138 lines, 7 tests)
- Created `tests/test_clean/test_outcomes_flags.py` (230 lines, 9 tests)
- Reorganized from `tests/test_load_outcomes_code_lookup.py` to align with source module location

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test dtype mismatch in assert_frame_equal**
- **Found during:** Task 2, test execution
- **Issue:** Expected DataFrame used default Int64 dtypes, but add_partner_flags() returns Int8
- **Fix:** Used pl.Series with explicit dtype=pl.Int8 for test expectations
- **Files modified:** tests/test_clean/test_harmonize.py
- **Commit:** f4072da (included in Task 2 commit)

## Verification Results

All tests pass:

```bash
$ python -m pytest tests/test_validate/ tests/test_clean/ -v
============================= 32 passed in 0.61s ==============================
```

**Coverage breakdown:**
- Checkpoint validation: 16 tests (row-count strict/tolerance, schema, no-vanish)
- Partner flags: 7 tests (ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY assignment)
- Outcomes code lookup: 9 tests (schema validation, forward-fill, normalization)

## Success Criteria Met

- [x] Checkpoint validation has comprehensive coverage
- [x] Row-count validation tested in strict and tolerance modes
- [x] Schema validation tested for missing columns and wrong dtypes
- [x] validate_no_vanish tested for catastrophic data loss
- [x] Partner flag logic tested with known abbreviations
- [x] Outcomes code lookup tested with schema validation
- [x] All tests pass
- [x] AUDIT-013 and AUDIT-014 resolved

## Key Decisions

1. **Polars Series with explicit dtype:** Used pl.Series(..., dtype=pl.Int8) in test expectations to match actual Int8 output from add_partner_flags()

2. **Document schema validation behavior:** Rather than adding explicit schema validation to load_outcomes_code_lookup(), documented that pandas raises KeyError on missing columns (fail-fast behavior)

3. **Reorganize outcomes tests:** Moved from tests/test_load_outcomes_code_lookup.py to tests/test_clean/test_outcomes_flags.py to align with source module location (src/clean/outcomes_flags.py)

## Audit Resolution

**AUDIT-013 (Partner abbreviations):**
- Documented partner abbreviations (AMS, UMI, FLM, VRT) in test_harmonize.py
- Tested partner flag assignment for known abbreviations
- Added test for unrecognized SOURCE values (all flags = 0)
- Added TODO for production validation step to detect unrecognized SOURCE values

**AUDIT-014 (Outcomes.csv schema):**
- Documented expected schema: Modality, Code system, Code columns
- Tested missing column behavior (raises KeyError)
- Added schema documentation test as reference for future maintainers

## Impact

**Testing:**
- 32 new tests covering Phase 2 checkpoint infrastructure
- Locks in correctness of checkpoint validation (row-count, schema, no-vanish)
- Validates partner flag assignment logic for all known partners
- Ensures Outcomes.csv schema changes are caught early

**Audit:**
- Resolves 2 TODO(audit) items (AUDIT-013, AUDIT-014)
- Documents partner abbreviations for future data source changes
- Documents Outcomes.csv schema requirements

## Self-Check

Verifying created files exist:

```bash
$ ls tests/test_validate/test_checkpoint.py
tests/test_validate/test_checkpoint.py

$ ls tests/test_clean/test_harmonize.py
tests/test_clean/test_harmonize.py

$ ls tests/test_clean/test_outcomes_flags.py
tests/test_clean/test_outcomes_flags.py
```

Verifying commits exist:

```bash
$ git log --oneline --all | grep 28463c1
28463c1 test(03-04): add comprehensive checkpoint validation tests

$ git log --oneline --all | grep f4072da
f4072da test(03-04): add partner flag and outcomes schema validation tests
```

## Self-Check: PASSED

All files created and commits verified.
