# Testing Patterns

**Analysis Date:** 2026-03-17

## Test Framework

**Runner:**
- pytest (no specific version pinned in `pyproject.toml`, uses system install)
- Config: no `pytest.ini` or `setup.cfg` — uses default discovery from project root
- Cache directory: `.pytest_cache/` (auto-generated)

**Assertion Library:**
- Built-in `assert` statements (no `pytest.approx()`, `pytest.raises()`, or third-party library)
- Simple comparisons: `assert result == expected`, `assert result["status"] == "ok"`
- Collection membership: `assert "KEY" in result`
- Numeric comparisons: `assert result["total"] >= 0`, `assert flagged_count == 6`

**Run Commands:**
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_cohort.py -v

# Run specific test
python -m pytest tests/test_cohort.py::test_verify_hl_cohort_minimal -v

# Run in watch mode (via CI)
# Not configured; use manual re-run

# View coverage
# Not configured; coverage measurement not enabled
```

## Test File Organization

**Location:**
- Co-located in separate `tests/` directory at project root
- One test module per source module (mapping: `src/module.py` → `tests/test_module.py`)
- Test directory structure mirrors some source structure but is flat (no subdirectories)

**Naming:**
- Test modules: `test_<source_module>.py`
- Test functions: `test_<function_name>_<scenario>` or `test_<feature_<behavior>`
- Examples:
  - `test_verify_hl_cohort_minimal` — minimal case of `verify_hl_cohort()`
  - `test_validate_table_schema_ok` — schema validation success path
  - `test_validate_table_schema_missing_col` — missing column scenario
  - `test_check_patid_integrity_orphans` — orphan record detection

**Current test files:**
- `tests/conftest.py` — fixtures (currently minimal/empty)
- `tests/test_cohort.py` — tests for `src/validate/cohort.py`
- `tests/test_structural.py` — tests for `src/validate/structural.py`
- `tests/test_flags_diagnosis_provider.py` — tests for `src/clean/flags_diagnosis_provider.py`
- `tests/test_flag_small_cell.py` — tests for small-cell suppression utility
- `tests/test_suppress.py` — tests for CSV suppression utility
- `tests/test_add_modality_flags.py` — integration test for `src/clean/outcomes_flags.py`
- `tests/test_load_outcomes_code_lookup.py` — tests for outcomes code loading

## Test Structure

**Suite Organization:**

```python
"""Tests for <function/module> — one-line description."""

from pathlib import Path
import polars as pl
from src.<module> import <function_to_test>

def test_<function>_<scenario>() -> None:
    """Brief description of what is tested."""
    # Setup: Create test data
    # Action: Call function
    # Assert: Verify result
```

**Setup-Action-Assert Pattern (AAA):**
- **Setup**: Create minimal test fixtures (temp files, DataFrames)
- **Action**: Call the function under test with test data
- **Assert**: Verify one or more assertions about the result

**Example from `test_cohort.py`:**
```python
def test_verify_hl_cohort_minimal(tmp_path: Path) -> None:
    """verify_hl_cohort returns dict with expected keys."""
    # SETUP: Create minimal parquet files
    diag_path = tmp_path / "diagnosis.parquet"
    enc_path = tmp_path / "encounter.parquet"

    pl.DataFrame({
        "ID": ["P1", "P1", "P2"],
        "DX": ["C81.00", "C81.01", "201.00"],
        "DX_DATE": [date(2020, 1, 1), date(2020, 1, 15), date(2020, 2, 1)],
        "DX_TYPE": ["10", "10", "09"],
        "SOURCE": ["UFH", "UFH", "UFH"],
    }).write_parquet(diag_path)

    # ACTION: Call function
    result = verify_hl_cohort(diag_path, enc_path)

    # ASSERT: Check result structure and values
    assert "total_hl_records" in result
    assert "unique_patients" in result
    assert result["total_hl_records"] >= 0
```

**Patterns:**
- **Fixtures (fixtures):** `tmp_path: Path` fixture from pytest — provides temporary directory
- **Teardown:** Not explicitly used; pytest automatically cleans up `tmp_path`
- **Assertion patterns:** See "Assertion Library" section above

## Mocking

**Framework:** Not used in current tests

**Current approach:**
- No mocking library imported (no `unittest.mock`, `pytest-mock`, `monkeypatch`)
- All dependencies are either:
  - External (Polars dataframes, file I/O) — use real objects
  - Internal (functions from `src/`) — call directly
  - Configuration — passed as parameters or loaded from fixtures

**What to Mock:**
- File system access: Use `tmp_path` fixture instead (creates real temp dirs)
- External APIs: Not tested (no integrations in current codebase)
- Database connections: Not tested (file-based only)

**What NOT to Mock:**
- Polars DataFrames — use real `pl.DataFrame()` with test data
- Internal function calls — call them directly to test integration
- Constants — import and use directly

**Pattern for file operations:**
```python
def test_example(tmp_path: Path) -> None:
    # Create file in temp directory
    path = tmp_path / "test.parquet"
    df = pl.DataFrame({"col": [1, 2, 3]})
    df.write_parquet(path)

    # Function under test reads from actual file
    result = function_that_reads(path)
    assert result is not None
```

## Fixtures and Factories

**Test Data:**
- Inline DataFrame creation via `pl.DataFrame({"col": [vals]})`
- Minimal schema: only columns required by function under test
- Sample sizes: 2-3 rows typically (enough to test logic, not performance)
- Real values when testing parsing/validation (e.g., ICD codes, dates)

**Example from `test_flags_diagnosis_provider.py`:**
```python
df = pl.DataFrame({
    "ID": ["P1", "P2", "P3"],
    "DX": ["201.00", "C81.10", "Z85.3"],
    "DX_TYPE": ["09", "10", "10"],
    "DX_DATE": [None, None, None],
})
result = add_diagnosis_flags(df)
assert result["FLAG_HL_DX"].to_list() == [1, 1, 0]
```

**Location:**
- No separate fixture factories — `conftest.py` is empty/minimal
- Fixtures defined inline in test functions (typical for small datasets)
- Constants from source modules imported directly (e.g., `ICD9_HL_CODES`)

**Fixture pattern (if using conftest):**
```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def demo_dataframe():
    """Basic demographic DataFrame."""
    return pl.DataFrame({
        "ID": ["P1", "P2"],
        "BIRTH_DATE": [date(1990, 1, 1), date(1995, 6, 15)],
    })
```

## Coverage

**Requirements:** Not enforced

**View Coverage:**
```bash
# Install pytest-cov
pip install pytest-cov

# Run tests with coverage
python -m pytest tests/ --cov=src --cov-report=html
```

**Coverage status:**
- No `.coveragerc` or coverage configuration in repository
- No CI check for minimum coverage percentage
- Some untested scenarios exist (see CONCERNS.md)

## Test Types

**Unit Tests:**
- **Scope:** Individual functions and their behavior with various inputs
- **Approach:** Test with minimal DataFrame fixtures; verify output structure and values
- **Examples:**
  - `test_flag_hl_dx_matches_cohort_codes()` — tests that cohort codes produce FLAG_HL_DX=1
  - `test_flag_small_cell_one()` — tests suppression logic for single-cell counts
  - `test_suppress_ten()` — tests CSV value suppression for small counts

**Integration Tests:**
- **Scope:** Multiple functions working together, file I/O, data transformation pipeline
- **Approach:** Create temp Parquet files, call high-level functions, verify result files
- **Examples:**
  - `test_add_modality_flags_integration()` — reads outcomes CSV, checks procedure matches, verifies flags set
  - `test_check_patid_integrity_orphans()` — creates demographic and child tables, validates referential integrity

**E2E Tests:**
- Not present in codebase
- Full pipeline testing happens via scripts (e.g., `scripts/smoke_test.py`, `scripts/validate_all.py`)

## Common Patterns

**Async Testing:**
Not applicable (no async code in codebase)

**Error Testing:**
- **No explicit error assertions** — functions return empty dicts/DataFrames on error (see defensive patterns)
- Test expected behavior when data is missing:
  ```python
  def test_check_death_consistency_missing_table(tmp_path: Path) -> None:
      """Returns empty dict if DEATH table missing."""
      table_map = {"DIAGNOSIS": tmp_path / "diagnosis.parquet"}
      result = check_death_consistency(table_map)
      assert result == {}
  ```

**Multi-condition Testing:**
- Test multiple code types in one DataFrame:
  ```python
  df = pl.DataFrame({
      "DX": ["201.00", "C81.10", "Z85.3"],  # ICD-9, ICD-10, other
      "DX_TYPE": ["09", "10", "10"],
  })
  result = add_diagnosis_flags(df)
  assert result["FLAG_HL_DX"].to_list() == [1, 1, 0]
  ```

**Null/Empty Handling:**
- Test with None values:
  ```python
  df = pl.DataFrame({
      "PROVIDER_SPECIALTY_PRIMARY": [None],
  })
  result = add_provider_flags(df)
  assert result["FLAG_CANCER_PROVIDER"].to_list() == [0]
  ```

**Date/Type Handling:**
- Test format parsing (from `src/validate/cohort.py`):
  ```python
  # Multi-format date parsing with fallback
  tr.with_columns(
      pl.col(tr_date_col)
      .str.to_date("%m/%d/%Y", strict=False)
      .fill_null(pl.col(tr_date_col).str.to_date("%d%b%Y", strict=False))
      .fill_null(pl.col(tr_date_col).str.to_date("%Y%m%d", strict=False))
  )
  ```

## Testing Workflow

**Pre-commit Hook:**
- Tests run automatically via pre-commit hook before each commit
- Config: `.pre-commit-config.yaml` (entry: `python -m pytest tests/ -v`)
- Hook stops commit if any test fails
- All tests must pass before code can be committed

**CI Target:**
- Makefile `ci` target runs: `ruff check . && ruff format --check . && python -m pytest tests/ -v`
- Tests must pass alongside linting checks

**Test Discovery:**
- pytest auto-discovers files matching `test_*.py` in `tests/` directory
- No explicit test configuration needed (uses defaults)

---

*Testing analysis: 2026-03-17*
