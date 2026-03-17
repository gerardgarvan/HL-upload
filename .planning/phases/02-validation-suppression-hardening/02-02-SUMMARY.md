---
phase: 02-validation-suppression-hardening
plan: 02
subsystem: report
tags: [suppression, refactoring, HIPAA, centralization]
dependencies:
  requires: [VAL-04]
  provides: [centralized-suppression-module]
  affects: [quality_report, site_table, build_insurance_summary, assemble_clean, validate_values, test_suppress, test_flag_small_cell]
tech_stack:
  added: [src/report/suppression.py]
  patterns: [single-source-of-truth, backward-compatibility]
key_files:
  created:
    - src/report/suppression.py
  modified:
    - src/report/quality_report.py
    - src/report/site_table.py
    - scripts/build_insurance_summary.py
    - scripts/assemble_clean.py
    - scripts/validate_values.py
    - tests/test_suppress.py
    - tests/test_flag_small_cell.py
    - src/validate/structural.py
    - src/clean/validate/structural.py
decisions:
  - "DEFAULT_THRESHOLD=10 as single source of truth in suppression.py"
  - "Zero counts displayed as-is (not suppressed) per user decision"
  - "Backward compatible _suppress alias for migration safety"
  - "Deprecated original functions in structural.py but did NOT remove (safe migration)"
  - "Used ⚠ marker format for flag_small_cell (matches existing codebase pattern)"
metrics:
  duration_minutes: 4
  tasks_completed: 2
  files_modified: 10
  tests_passing: 22
  commits: 2
completed: 2026-03-17
---

# Phase 02 Plan 02: Centralized Suppression Module Summary

**One-liner:** Single suppression.py module eliminates 4+ duplicate HIPAA small-cell implementations with DEFAULT_THRESHOLD=10, zero-safe logic, and configurable thresholds.

## What Was Built

Created `src/report/suppression.py` as the single source of truth for all HIPAA small-cell suppression logic across the pipeline. Module exports:
- `DEFAULT_THRESHOLD = 10` constant
- `suppress()` function (masks 1-10 with "-", displays zero as-is)
- `flag_small_cell()` function (flags 1-10 with "⚠" marker for internal reports)
- `audit_suppression()` function (metrics tracking for suppression impact)
- `_suppress` backward compatibility alias

Rewired 7 files across the codebase to import from centralized module:
- `src/report/quality_report.py` - removed local `_suppress()` definition
- `src/report/site_table.py` - imports flag_small_cell
- `scripts/build_insurance_summary.py` - imports all suppression functions
- `scripts/assemble_clean.py` - imports flag_small_cell
- `scripts/validate_values.py` - imports suppression functions
- `tests/test_suppress.py` - updated import path
- `tests/test_flag_small_cell.py` - updated import path

Marked original functions in `src/validate/structural.py` and `src/clean/validate/structural.py` as deprecated but did NOT remove them (safe migration pattern).

## Implementation Notes

**Zero-safe logic:** User decision to display zero counts as-is (not suppress) because zero reveals no individual-level information—cannot re-identify from absence.

**Marker format:** Used "⚠" warning symbol for `flag_small_cell()` to match existing codebase pattern from structural.py (verified before implementation).

**Backward compatibility:** Exported `_suppress = suppress` alias so any remaining references to `_suppress` work during migration without breaking.

**Threshold configurability:** All functions accept optional `threshold` parameter (default 10) for per-report override capability while maintaining single source of truth for default.

**Clinical rationale documented:** Module docstring includes HIPAA Safe Harbor method, CMS Cell Suppression Policy, and WA DOH standards references with primary suppression justification.

## Deviations from Plan

None - plan executed exactly as written.

## Testing & Verification

**Unit tests:** All 22 tests pass including 9 suppression-specific tests (test_suppress.py: 4 tests, test_flag_small_cell.py: 5 tests).

**Import verification:** Grep confirms all 7 files import from `src.report.suppression`, no old import paths remain in report/scripts/tests directories.

**Function behavior verified:**
- `suppress(0) == "0"` (zero-safe)
- `suppress(5) == "-"` (suppressed)
- `suppress(11) == "11"` (above threshold)
- `suppress(5, threshold=3) == "5"` (configurable threshold)
- `flag_small_cell(5)` contains "⚠" marker
- `audit_suppression([0, 3, 5, 12, 15])` returns correct metrics

**No duplicate definitions:** Grep confirms only `suppression.py` contains canonical `suppress()` definition (quality_report.py definition removed with comment marker).

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 27d1d87 | feat(02-02): create centralized HIPAA suppression module |
| 2 | a8619f5 | refactor(02-02): rewire all suppression imports to centralized module |

## Impact

**Before:** 4+ duplicate suppression implementations scattered across quality_report.py (local `_suppress`), structural.py (flag_small_cell), and clean/validate/structural.py (flag_small_cell), with inconsistent thresholds and logic.

**After:** Single `src/report/suppression.py` module with DEFAULT_THRESHOLD=10 as single source of truth. All imports centralized, threshold drift eliminated, HIPAA auditing simplified.

**Benefits:**
- Single source of truth for suppression logic prevents threshold drift
- Centralized clinical rationale with HIPAA/CMS/WA DOH references
- Per-report threshold override capability via function parameters
- Backward compatible migration (alias + deprecation comments)
- Simplified auditing for HIPAA compliance
- All existing tests pass without modification (same behavior, new import paths)

**No breaking changes:** All function signatures unchanged, same output format, same threshold value (10), same zero-handling behavior.

## Self-Check: PASSED

Files created:
- FOUND: src/report/suppression.py

Commits exist:
- FOUND: 27d1d87 (Task 1: create suppression module)
- FOUND: a8619f5 (Task 2: rewire imports)

All verification criteria met:
- [x] src/report/suppression.py is single source for suppress(), flag_small_cell(), DEFAULT_THRESHOLD
- [x] All 7 files rewired to import from suppression.py
- [x] Tests pass with new imports (22/22 passed)
- [x] suppress(0) returns "0" (zero-safe)
- [x] suppress(5) returns "-", suppress(11) returns "11"
- [x] suppress(5, threshold=3) returns "5" (configurable threshold)
- [x] audit_suppression() returns correct metrics
- [x] Original functions marked deprecated but not removed
