---
phase: 03-test-coverage-fragile-areas
plan: 06
subsystem: test-infrastructure
tags: [testing, test-organization, pytest-configuration, ci-cd-ready]
completed: 2026-03-17

dependency_graph:
  requires: [03-01, 03-02, 03-03, 03-04]
  provides:
    - Fully organized test suite mirroring src/ structure
    - pytest.ini configuration with markers and discovery settings
    - Selective test execution by requirement (TEST-01 through TEST-04)
  affects:
    - CI/CD pipeline integration (pytest configuration ready)
    - Test maintenance (mirrored structure improves discoverability)

tech_stack:
  added:
    - pytest.ini configuration with markers and discovery rules
    - Test markers for requirement-based test organization
  patterns:
    - Mirrored directory structure (tests/test_X mirrors src/X)
    - pytest.mark decorators for selective test execution
    - git mv for history-preserving file reorganization

key_files:
  created:
    - pytest.ini (33 lines): Test discovery, markers, output settings
    - test_summary.txt (244 lines): Full test suite execution log
  modified:
    - tests/test_validate/test_cohort.py: Moved from tests/ root
    - tests/test_validate/test_structural.py: Moved from tests/ root
    - tests/test_clean/test_add_modality_flags.py: Moved from tests/ root
    - tests/test_clean/test_flags_diagnosis_provider.py: Moved from tests/ root
    - tests/test_report/test_payer_logic.py: Added @pytest.mark.payer (73 tests)
    - tests/test_load/test_date_parsing.py: Added @pytest.mark.dates (57 tests)
    - tests/test_report/test_quality_report.py: Added @pytest.mark.reports (14 tests)
    - tests/test_report/test_suppression.py: Added @pytest.mark.reports (27 tests)
    - tests/test_validate/test_checkpoint.py: Added @pytest.mark.checkpoint (16 tests)
  deleted:
    - tests/test_suppress.py: Merged into test_report/test_suppression.py in 03-03
    - tests/test_flag_small_cell.py: Merged into test_report/test_suppression.py in 03-03
    - tests/test_load_outcomes_code_lookup.py: Merged into test_clean/test_outcomes_flags.py in 03-04

decisions:
  - decision: Mirror src/ directory structure in tests/
    rationale: Best practice for test discoverability and maintenance; clear 1:1 mapping between source and test files
    alternatives: Flat structure (harder to navigate), feature-based grouping (breaks source mapping)
  - decision: Use pytest.ini instead of pyproject.toml for test configuration
    rationale: Dedicated test configuration file, explicit and discoverable, no dependency on pyproject.toml structure
    alternatives: pyproject.toml [tool.pytest] (couples test config to project config)
  - decision: Marker-based test organization (payer, dates, reports, checkpoint)
    rationale: Enables selective execution by requirement (TEST-01 through TEST-04), supports CI/CD stage separation
    alternatives: Directory-based organization (less flexible), filename prefixes (verbose)
  - decision: git mv for file reorganization
    rationale: Preserves git history for moved files, maintains blame/log continuity
    alternatives: cp + rm (loses history), manual file moves (same issue)

metrics:
  duration_minutes: 6
  tasks_completed: 3
  test_files_moved: 4
  test_files_deleted: 3
  test_markers_added: 187
  total_tests: 234
  lines_of_code: 277 (pytest.ini + test_summary.txt)
  files_created: 2
  files_modified: 9
  files_deleted: 3
---

# Phase 03 Plan 06: Test Suite Organization & pytest Configuration

**One-liner:** Reorganized test suite to mirror src/ directory structure, configured pytest.ini with requirement-based markers (payer, dates, reports, checkpoint), enabling selective test execution for 234 tests across 4 requirements.

## Overview

Completed final test suite organization for Phase 3, establishing production-ready test infrastructure. Reorganized existing tests into mirrored src/ structure (tests/test_load/, test_validate/, test_clean/, test_report/), configured pytest.ini with discovery settings and requirement-based markers, and verified full test suite passes with selective execution capability. All 234 tests pass in 1.01 seconds with clear requirement-to-test mapping.

## Tasks Completed

### Task 1: Reorganize existing tests to mirror src/ structure
- **Status:** Complete
- **Files:** tests/test_validate/test_cohort.py, tests/test_validate/test_structural.py, tests/test_clean/test_add_modality_flags.py, tests/test_clean/test_flags_diagnosis_provider.py (4 files moved)
- **Commit:** 99c9a9d
- **Implementation:**
  - Moved tests/test_cohort.py → tests/test_validate/test_cohort.py (git mv)
  - Moved tests/test_structural.py → tests/test_validate/test_structural.py (git mv)
  - Moved tests/test_add_modality_flags.py → tests/test_clean/test_add_modality_flags.py (git mv)
  - Moved tests/test_flags_diagnosis_provider.py → tests/test_clean/test_flags_diagnosis_provider.py (git mv)
  - Deleted merged files: test_suppress.py, test_flag_small_cell.py, test_load_outcomes_code_lookup.py (git rm)
  - Preserved git history for all moved files (git mv, not cp+rm)
  - All 234 tests passing after reorganization (no behavior changes)
  - Final structure mirrors src/ exactly:
    - tests/test_load/ mirrors src/load/
    - tests/test_validate/ mirrors src/validate/
    - tests/test_clean/ mirrors src/clean/
    - tests/test_report/ mirrors src/report/

### Task 2: Create pytest.ini configuration
- **Status:** Complete
- **Files:** pytest.ini, tests/test_report/test_payer_logic.py, tests/test_load/test_date_parsing.py, tests/test_report/test_quality_report.py, tests/test_report/test_suppression.py, tests/test_validate/test_checkpoint.py
- **Commit:** c1b9a4d
- **Implementation:**
  - Created pytest.ini with test discovery settings (testpaths=tests, python_files=test_*.py)
  - Configured verbose output (-v), strict markers (--strict-markers), short tracebacks (--tb=short)
  - Defined 6 markers: payer (TEST-01), dates (TEST-02), reports (TEST-03), checkpoint (TEST-04), audit, slow
  - Added @pytest.mark.payer to all 10 test functions in test_payer_logic.py (73 parametrized tests)
  - Added @pytest.mark.dates to all 12 test functions in test_date_parsing.py (57 parametrized tests)
  - Added @pytest.mark.reports to all 9 test classes in test_quality_report.py and test_suppression.py (41 tests)
  - Added @pytest.mark.checkpoint to all 16 test functions in test_checkpoint.py
  - Verified markers registered: pytest --markers shows all 6 custom markers
  - Verified selective execution: pytest -m payer (73 tests), pytest -m dates (57 tests), pytest -m reports (41 tests), pytest -m checkpoint (16 tests)
  - All 234 tests passing with pytest.ini settings applied

### Task 3: Run full test suite and verify coverage
- **Status:** Complete
- **Files:** test_summary.txt
- **Commit:** 8956417
- **Implementation:**
  - Ran pytest tests/ -v --tb=short (234 tests, all PASSED in 1.01 seconds)
  - Saved full test output to test_summary.txt (244 lines)
  - Verified coverage by requirement:
    - TEST-01 (Payer Logic): 73 tests passing (pytest -m payer)
    - TEST-02 (Date Parsing): 57 tests passing (pytest -m dates)
    - TEST-03 (Reports): 41 tests passing (pytest -m reports)
    - TEST-04 (Checkpoints): 16 tests passing (pytest -m checkpoint)
    - Total requirement coverage: 187 tests (234 total includes non-requirement tests)
  - Verified test organization: 12 test files across 4 mirrored subdirectories
  - Verified selective execution: pytest -m payer, pytest -m dates, pytest -m reports, pytest -m checkpoint all working
  - No test failures, no skipped tests, no warnings

## Verification Results

All verification criteria met:

**pytest.ini configuration:**
- pytest --markers lists payer, dates, reports, checkpoint markers ✓
- pytest -v uses configured settings (verbose, strict-markers, tb=short) ✓
- pytest.ini exists in repository root ✓

**Test organization:**
- All tests reorganized into tests/test_load/, test_validate/, test_clean/, test_report/ ✓
- No test files remain in tests/ root (except conftest.py) ✓
- All __init__.py files exist in subdirectories ✓

**Full test suite:**
- pytest tests/ -v shows all 234 tests passing ✓
- test_summary.txt shows 234 passed, 0 failed, 0 skipped ✓
- All requirements (TEST-01 through TEST-04) have test coverage ✓

**Selective execution:**
- pytest -m payer runs 73 payer logic tests ✓
- pytest -m dates runs 57 date parsing tests ✓
- pytest -m reports runs 41 report generation tests ✓
- pytest -m checkpoint runs 16 checkpoint validation tests ✓

**Must-haves verification:**
- All existing tests reorganized to mirror src/ structure ✓
- No test behavior changed during reorganization (234 tests passing) ✓
- pytest.ini configured with discovery, reporting, and marker settings ✓
- tests/test_validate/test_cohort.py provides reorganized cohort validation tests (30+ lines) ✓
- tests/test_validate/test_structural.py provides reorganized structural validation tests (40+ lines) ✓
- pytest.ini provides pytest configuration for test discovery and reporting (33 lines, min_lines: 10) ✓
- Key link from tests/ to src/ via mirrored directory structure exists ✓
  - Pattern: tests/test_load/ mirrors src/load/
  - Pattern: tests/test_validate/ mirrors src/validate/
  - Pattern: tests/test_clean/ mirrors src/clean/
  - Pattern: tests/test_report/ mirrors src/report/

## Deviations from Plan

**None** - plan executed exactly as written.

All tasks completed as specified. No blocking issues encountered. No code fixes needed (only test organization and configuration).

## Key Decisions Made

1. **Mirror src/ directory structure in tests/**
   - Follows pytest best practice for test discoverability
   - Clear 1:1 mapping between source and test files improves maintainability
   - Easier for new contributors to find relevant tests

2. **Use pytest.ini instead of pyproject.toml**
   - Dedicated test configuration file is more discoverable
   - Explicit pytest configuration, not coupled to project packaging config
   - Standard pytest convention, widely recognized

3. **Marker-based test organization**
   - Enables selective execution by requirement (TEST-01 through TEST-04)
   - Supports CI/CD pipeline stage separation (e.g., run payer tests first)
   - More flexible than directory-based organization for cross-cutting concerns

4. **git mv for file reorganization**
   - Preserves git history for moved files
   - Maintains git blame and log continuity
   - Critical for understanding test evolution over time

## Performance & Quality Metrics

| Metric | Value |
|--------|-------|
| Duration | 6 minutes |
| Tasks completed | 3 of 3 |
| Test files moved | 4 |
| Test files deleted | 3 (previously merged) |
| Test markers added | 187 (across 234 tests) |
| Total tests | 234 (all passing) |
| Test execution time | 1.01 seconds (full suite) |
| Lines of code | 277 (pytest.ini + test_summary.txt) |
| Files created | 2 (pytest.ini, test_summary.txt) |
| Files modified | 9 (4 moved + 5 marker additions) |
| Files deleted | 3 (merged in prior plans) |

## Files Modified

### Created
- `pytest.ini` (33 lines)
  - Test discovery settings (testpaths, python_files, python_classes, python_functions)
  - Output settings (verbose, strict-markers, short tracebacks, color)
  - 6 markers: payer, dates, reports, checkpoint, audit, slow
  - Warnings configuration (error on warnings, ignore deprecations)
  - Coverage settings (commented, requires pytest-cov)
- `test_summary.txt` (244 lines)
  - Full pytest -v output for 234 tests
  - Verification log for test suite completeness

### Modified
- `tests/test_validate/test_cohort.py`: Moved from tests/ root (git mv)
- `tests/test_validate/test_structural.py`: Moved from tests/ root (git mv)
- `tests/test_clean/test_add_modality_flags.py`: Moved from tests/ root (git mv)
- `tests/test_clean/test_flags_diagnosis_provider.py`: Moved from tests/ root (git mv)
- `tests/test_report/test_payer_logic.py`: Added @pytest.mark.payer to 10 test functions
- `tests/test_load/test_date_parsing.py`: Added @pytest.mark.dates to 12 test functions
- `tests/test_report/test_quality_report.py`: Added @pytest.mark.reports to 5 test classes
- `tests/test_report/test_suppression.py`: Added @pytest.mark.reports to 4 test classes
- `tests/test_validate/test_checkpoint.py`: Added @pytest.mark.checkpoint to 16 test functions

### Deleted
- `tests/test_suppress.py`: Merged into test_report/test_suppression.py in 03-03
- `tests/test_flag_small_cell.py`: Merged into test_report/test_suppression.py in 03-03
- `tests/test_load_outcomes_code_lookup.py`: Merged into test_clean/test_outcomes_flags.py in 03-04

## Next Steps

1. **CI/CD Integration:**
   - Add pytest to CI/CD pipeline (e.g., GitHub Actions, GitLab CI)
   - Use requirement markers for staged testing: pytest -m payer (fast), pytest -m checkpoint (slower)
   - Configure pytest-cov for coverage reporting if needed

2. **Test Suite Maintenance:**
   - When adding new source files, create corresponding test files in mirrored structure
   - When adding new test requirements, create new markers in pytest.ini
   - Keep test_summary.txt updated for regression tracking

3. **Phase 3 Completion:**
   - All 6 Phase 3 plans complete (03-01 through 03-06)
   - Test coverage spans all 4 requirements (TEST-01 through TEST-04)
   - Ready for Phase 4: Execution hardening or next milestone

## Lessons Learned

1. **Mirrored directory structure improves test discoverability**
   - Clear 1:1 mapping between src/ and tests/ reduces cognitive load
   - New contributors can find relevant tests immediately
   - Maintains consistency with pytest best practices

2. **Marker-based organization enables flexible test execution**
   - Requirement-based markers (payer, dates, reports, checkpoint) support selective CI/CD stages
   - More flexible than directory-based organization for cross-cutting concerns
   - Easy to add new markers as requirements evolve

3. **git mv preserves history during reorganization**
   - Critical for understanding test evolution over time
   - Maintains git blame and log continuity
   - Should always be used for file moves (never cp+rm)

4. **pytest.ini provides clear test configuration**
   - Dedicated test configuration file is more discoverable than pyproject.toml
   - Explicit settings reduce pytest invocation friction
   - Standard pytest convention, widely recognized

## Success Criteria Met

- ✓ All tasks executed (3 of 3)
- ✓ Each task committed individually (99c9a9d, c1b9a4d, 8956417)
- ✓ All deviations documented (none occurred)
- ✓ All existing tests reorganized to mirror src/ structure
- ✓ No test behavior changed during reorganization (234 tests passing)
- ✓ pytest.ini configured with discovery, reporting, and marker settings
- ✓ Full test suite passes (234 tests, 1.01s execution time)
- ✓ Markers enable selective execution by requirement (TEST-01 through TEST-04)
- ✓ Test coverage spans all requirements (187 requirement tests + 47 supporting tests)
- ✓ CI/CD ready test configuration

---

**Summary statement:** Completed test suite organization with mirrored src/ structure, pytest.ini configuration with requirement-based markers (payer, dates, reports, checkpoint), and verification of 234 passing tests with selective execution capability. Test infrastructure is CI/CD ready with clear requirement-to-test mapping for TEST-01 through TEST-04.

## Self-Check: PASSED

Verified all claims before proceeding to state updates:

1. **Created files exist:**
   - ✓ pytest.ini (33 lines)
   - ✓ test_summary.txt (244 lines)

2. **Moved files exist in new locations:**
   - ✓ tests/test_validate/test_cohort.py
   - ✓ tests/test_validate/test_structural.py
   - ✓ tests/test_clean/test_add_modality_flags.py
   - ✓ tests/test_clean/test_flags_diagnosis_provider.py

3. **Commits exist:**
   - ✓ 99c9a9d: refactor(03-06): reorganize tests to mirror src/ directory structure
   - ✓ c1b9a4d: feat(03-06): create pytest.ini with markers and test organization
   - ✓ 8956417: test(03-06): run full test suite and verify coverage

4. **Test execution:**
   - ✓ 234 tests collected and passed in 1.01s
   - ✓ pytest -m payer: 73 tests passed
   - ✓ pytest -m dates: 57 tests passed
   - ✓ pytest -m reports: 41 tests passed
   - ✓ pytest -m checkpoint: 16 tests passed

5. **Mirrored structure verification:**
   - ✓ tests/test_load/ mirrors src/load/
   - ✓ tests/test_validate/ mirrors src/validate/
   - ✓ tests/test_clean/ mirrors src/clean/
   - ✓ tests/test_report/ mirrors src/report/

All SUMMARY.md claims verified before state updates.
