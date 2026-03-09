# Testing Patterns

**Analysis Date:** 2026-03-09

## Test Framework

**Runner:**
- None — No pytest, unittest, or other test framework

**Assertion Library:**
- Plain `assert` in smoke test

**Run Commands:**
```bash
python scripts/smoke_test.py [config/paths.toml]   # Manual smoke test
```

## Test File Organization

**Location:**
- Single smoke test: `scripts/smoke_test.py`
- No `tests/` directory; no `*_test.py` or `test_*.py` in src

**Naming:**
- `smoke_test.py` — descriptive, not pytest-discoverable

**Structure:**
- Smoke test: 9 steps (config load, datastructure parse, CSV exists, Polars load, SAS date parse, Parquet write, read-back, DuckDB verify, summary)

## Test Structure

**Smoke Test Pattern:**
```python
def main(config_path: Path | None = None) -> None:
    # Step 1: Load config
    paths = load_config(config_path)
    # Step 2: Parse datastructure
    # Step 3: Verify CSV exists
    # Step 4: Load CSV with Polars
    # Step 5: Parse SAS DATE9. dates
    # Step 6: Write Parquet
    # Step 7: Read back and assert shape, dtype
    # Step 8: DuckDB count assert
    # Step 9: Summary
```

**Patterns:**
- Assert on shape and dtype after round-trip
- Raises `RuntimeError` or `FileNotFoundError` on precondition failure
- Exit 0 on success, 1 on exception

## Mocking

**Not used** — Smoke test operates on real files (requires data_root with DEMOGRAPHIC CSV)

## Fixtures and Factories

**Test Data:**
- Smoke test uses real DEMOGRAPHIC CSV from `paths.data_root`
- No synthetic fixtures or factories

**Location:**
- N/A

## Coverage

**Requirements:** None enforced

**View Coverage:** N/A — no coverage tooling

## Test Types

**Unit Tests:** None

**Integration Tests:** Smoke test serves as integration check (config → load → convert → Parquet → DuckDB)

**E2E Tests:** None

## Verification Approach

**Current:**
- Manual run of `smoke_test.py` after deployment
- Per-phase verification via `.planning/phases/*/VERIFICATION.md` (documentation, not automated)
- `submit_job.sh` runs smoke test on HPC

## Gaps

- No unit tests for `convert_table`, `validate_table_schema`, `verify_hl_cohort`, etc.
- No tests for `flag_small_cell`, `_suppress` edge cases
- No tests for Outcomes.xlsx parsing or modality flag logic
- No CI pipeline to run tests

---

*Testing analysis: 2026-03-09*
