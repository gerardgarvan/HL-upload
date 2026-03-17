# Phase 3: Test Coverage for Fragile Areas - Context

**Gathered:** 2026-03-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Lock in correctness of complex, fragile pipeline logic with comprehensive test coverage. Covers payer logic (derivation, dual-eligible, fallback chains, sentinels), date parsing (3 formats + edge cases), report generation (structure, suppression, aggregation), and checkpoint validation (row-count, schema). Also systematically resolves all TODO(audit) items from Phase 1.

</domain>

<decisions>
## Implementation Decisions

### Edge case depth
- Exhaustive enumeration for ALL test areas (payer logic, date parsing, reports, checkpoints)
- Every combination of sentinel values, missing fields, conflicting records for payer logic
- Every format x edge case combination for dates (nulls, mixed in same column, invalid strings, boundary dates)
- Use pytest.mark.parametrize for all edge case tests (one function, table of inputs/expected outputs)

### Behavior codification
- Tests assert EXPECTED behavior, not current behavior
- If current code is wrong, FIX the code in this phase (not xfail)
- For ambiguous cases: conservative defaults (preserve data, flag for review, don't silently drop)
- Systematically resolve ALL TODO(audit) items from Phase 1 — not just ones that surface through test writing

### Test data strategy
- Synthetic minimal fixtures: hand-crafted Polars DataFrames in each test, minimal rows, no files on disk
- Use actual PCORnet CDM value sets for realistic column names and value ranges (real DX_TYPE values like '09', '10', real ENC_TYPE values)
- Shared conftest.py with builder functions (make_diagnosis_df(), make_encounter_df(), etc.) that return valid DataFrames with sensible defaults — tests call with overrides

### Test organization
- Mirror src/ structure: tests/test_load/, tests/test_validate/, tests/test_clean/, tests/test_report/
- Reorganize existing tests (test_suppress.py, test_flag_small_cell.py) into the mirror structure
- Existing test behavior preserved, only import paths and file locations change

### Claude's Discretion
- Report test assertion style: Claude picks structural + spot-check vs exact values per report type
- Checkpoint file I/O tests: Claude decides whether to include Parquet round-trip tests or stay in-memory only
- Test granularity: Claude determines unit vs light-integration per area
- Coverage targets: Claude determines what "comprehensive" means per area

</decisions>

<specifics>
## Specific Ideas

- PCORnet CDM value sets should be the source of truth for test data values
- Conservative defaults principle: when behavior is ambiguous, tests should assert that data is preserved and flagged rather than silently dropped
- Every TODO(audit) from Phase 1 docstrings and AUDIT_LOG.md should be addressed with a test + fix

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-test-coverage-fragile-areas*
*Context gathered: 2026-03-17*
