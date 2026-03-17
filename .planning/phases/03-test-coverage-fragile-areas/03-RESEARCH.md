# Phase 03: Test Coverage for Fragile Areas - Research

**Researched:** 2026-03-17
**Domain:** Pytest testing for data pipeline with Polars DataFrames
**Confidence:** HIGH

## Summary

Phase 3 requires comprehensive test coverage for fragile pipeline logic: payer derivation (primary→secondary fallback, dual-eligible detection, sentinel handling), date parsing (3 SAS formats + edge cases), report generation (suppression, aggregation), and checkpoint validation (row-count, schema). The phase also resolves all 18 TODO(audit) items flagged in Phase 1.

**Testing approach:** Synthetic minimal fixtures using Polars DataFrames built with factory functions in conftest.py, pytest.mark.parametrize for edge case enumeration, tests mirror src/ structure, and existing tests reorganized into the new structure.

**Primary recommendation:** Use pytest 9.0.2 (already installed) with parametrize for exhaustive edge case testing, builder functions in conftest.py for DRY test data creation, polars.testing.assert_frame_equal for DataFrame comparisons, and in-memory testing (no Parquet I/O unless testing checkpoint persistence). Mirror src/ structure in tests/ to maintain code-test alignment as pipeline grows.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Edge case depth:**
- Exhaustive enumeration for ALL test areas (payer logic, date parsing, reports, checkpoints)
- Every combination of sentinel values, missing fields, conflicting records for payer logic
- Every format x edge case combination for dates (nulls, mixed in same column, invalid strings, boundary dates)
- Use pytest.mark.parametrize for all edge case tests (one function, table of inputs/expected outputs)

**Behavior codification:**
- Tests assert EXPECTED behavior, not current behavior
- If current code is wrong, FIX the code in this phase (not xfail)
- For ambiguous cases: conservative defaults (preserve data, flag for review, don't silently drop)
- Systematically resolve ALL TODO(audit) items from Phase 1 — not just ones that surface through test writing

**Test data strategy:**
- Synthetic minimal fixtures: hand-crafted Polars DataFrames in each test, minimal rows, no files on disk
- Use actual PCORnet CDM value sets for realistic column names and value ranges (real DX_TYPE values like '09', '10', real ENC_TYPE values)
- Shared conftest.py with builder functions (make_diagnosis_df(), make_encounter_df(), etc.) that return valid DataFrames with sensible defaults — tests call with overrides

**Test organization:**
- Mirror src/ structure: tests/test_load/, tests/test_validate/, tests/test_clean/, tests/test_report/
- Reorganize existing tests (test_suppress.py, test_flag_small_cell.py) into the mirror structure
- Existing test behavior preserved, only import paths and file locations change

### Claude's Discretion

**Report test assertion style:** Claude picks structural + spot-check vs exact values per report type

**Checkpoint file I/O tests:** Claude determines whether to include Parquet round-trip tests or stay in-memory only

**Test granularity:** Claude determines unit vs light-integration per area

**Coverage targets:** Claude determines what "comprehensive" means per area

### Deferred Ideas (OUT OF SCOPE)

None specified — all test areas are in scope for this phase.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TEST-01 | Comprehensive tests for payer logic (effective payer, dual-eligible detection, fallback chains, sentinel value handling) | Parametrize patterns for sentinel combinations, builder functions for ENCOUNTER DataFrames with PAYER_TYPE_PRIMARY/SECONDARY, test dual-eligible codes (14/141/142), INCLUDE_99_AS_SENTINEL flag testing |
| TEST-02 | Tests for date parsing (all 3 formats, edge cases: nulls, mixed formats, invalid dates, YYYYMMDD for tumor registry) | Parametrize for format x edge case matrix, boundary date testing (1900-01-01, 2026-12-31, leap years, invalid dates), mixed format column testing, detection threshold testing (30%/50%) |
| TEST-03 | Tests for report generation (output structure, suppression applied correctly, aggregation correctness) | Builder functions for report input data, assert_frame_equal for structure checks, spot-check suppression logic on boundary values (0, 1, 10, 11), aggregation correctness via known inputs |
| TEST-04 | Tests for phase checkpoint validation (row counts match expectations, schema checks pass) | Test CheckpointError raising, tolerance mode testing, schema validation with missing/wrong dtype columns, validate_no_vanish edge cases |

</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.0.2 | Testing framework | Industry standard Python testing, parametrize for edge case enumeration, fixture composition, extensive plugin ecosystem |
| polars | 1.38.1 | DataFrame library | Already in use by pipeline, polars.testing module for DataFrame equality assertions |
| polars.testing | 1.38.1 | DataFrame assertions | Official Polars testing utilities: assert_frame_equal, assert_series_equal for DataFrame/Series comparison |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| hypothesis | Latest (optional) | Property-based testing | Optional for parametric DataFrame generation, but user constraints specify hand-crafted fixtures, so not required for Phase 3 |
| pytest-cov | Latest (optional) | Coverage reporting | Optional for measuring test coverage percentage, useful for identifying untested code paths |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pytest parametrize | unittest parameterized | pytest parametrize is more readable and integrates better with fixtures |
| Hand-crafted fixtures | hypothesis strategies | Hypothesis generates random data, but user wants explicit edge case enumeration with predictable inputs |
| polars.testing | pandas.testing | Pipeline uses Polars, not pandas — use native Polars assertions |

**Installation:**

```bash
# Core already installed (pytest 9.0.2, polars 1.38.1)
# Optional coverage reporting:
pip install pytest-cov
```

## Architecture Patterns

### Recommended Project Structure

```
tests/
├── conftest.py              # Shared fixtures and builder functions
├── test_load/               # Mirrors src/load/
│   ├── test_convert.py      # Date detection, conversion, validation
│   └── test_config.py       # Configuration loading
├── test_validate/           # Mirrors src/validate/
│   ├── test_checkpoint.py   # Row-count, schema validation
│   ├── test_cohort.py       # HL cohort identification
│   ├── test_structural.py   # Completeness, structural checks
│   └── test_values.py       # Plausibility, value range checks
├── test_clean/              # Mirrors src/clean/
│   ├── test_dedup.py        # Deduplication logic
│   ├── test_harmonize.py    # Partner flags, enrollment checks
│   └── test_outcomes_flags.py
└── test_report/             # Mirrors src/report/
    ├── test_suppression.py  # HIPAA suppression (RELOCATED)
    ├── test_quality_report.py
    └── test_encounter_payer_summary.py  # Payer logic
```

**Rationale for mirroring:** As application grows, test structure naturally evolves alongside it, making it easier for developers to find tests for a given module. Source: [5 Best Practices For Organizing Tests](https://pytest-with-eric.com/pytest-best-practices/pytest-organize-tests/)

### Pattern 1: Factory Functions in conftest.py

**What:** Fixture that returns a function (factory) for creating test DataFrames with sensible defaults and optional overrides.

**When to use:** When tests need multiple DataFrames with different configurations, avoiding duplication of DataFrame construction.

**Example:**

```python
# conftest.py
import polars as pl
import pytest

@pytest.fixture
def make_encounter_df():
    """Factory for ENCOUNTER DataFrames with sensible PCORnet defaults."""
    def _make(
        n_rows=3,
        patid_col="ID",
        payer_primary=None,
        payer_secondary=None,
        admit_dates=None,
        enc_types=None,
    ):
        ids = [f"PT{i:03d}" for i in range(n_rows)]

        # Defaults to valid payer codes
        payer_pri = payer_primary or ["11"] * n_rows  # Medicare FFS
        payer_sec = payer_secondary or ["21"] * n_rows  # Medicaid FFS

        # Defaults to recent dates
        dates = admit_dates or [pl.date(2025, 1, i+1) for i in range(n_rows)]

        # Defaults to IP (inpatient)
        enc_type = enc_types or ["IP"] * n_rows

        return pl.DataFrame({
            patid_col: ids,
            "ENCOUNTERID": [f"ENC{i:05d}" for i in range(n_rows)],
            "PAYER_TYPE_PRIMARY": payer_pri,
            "PAYER_TYPE_SECONDARY": payer_sec,
            "ADMIT_DATE": dates,
            "ENC_TYPE": enc_type,
        })
    return _make

# Usage in test
def test_payer_fallback_to_secondary(make_encounter_df):
    # Primary is sentinel "NI", secondary is valid "21" (Medicaid)
    df = make_encounter_df(
        n_rows=1,
        payer_primary=["NI"],
        payer_secondary=["21"]
    )
    # Test that effective payer falls back to "21"
    ...
```

**Source:** [Five Advanced Pytest Fixture Patterns](https://www.inspiredpython.com/article/five-advanced-pytest-fixture-patterns)

### Pattern 2: Parametrize for Edge Case Enumeration

**What:** Use @pytest.mark.parametrize to run a single test function with a table of (input, expected_output) pairs.

**When to use:** When testing exhaustive edge cases with predictable inputs/outputs (payer sentinel combinations, date format variations, suppression boundary values).

**Example:**

```python
import pytest
from src.report.suppression import suppress

@pytest.mark.parametrize(
    "value,expected",
    [
        # Boundary values
        (0, "0"),        # Zero is safe to display
        (1, "-"),        # Suppress small cell
        (10, "-"),       # Suppress at threshold
        (11, "11"),      # Above threshold, display
        (100, "100"),    # Large value, display

        # Edge cases
        (-1, "-1"),      # Negative (invalid but shouldn't crash)
    ],
    ids=["zero", "one", "threshold", "above_threshold", "large", "negative"]
)
def test_suppress_boundary_values(value, expected):
    assert suppress(value) == expected
```

**Source:** [How to parametrize fixtures and test functions](https://docs.pytest.org/en/stable/how-to/parametrize.html)

### Pattern 3: Polars DataFrame Assertions

**What:** Use polars.testing.assert_frame_equal for DataFrame comparisons, which provides clear error messages on mismatch.

**When to use:** When verifying DataFrame transformations, report outputs, or checkpoint results.

**Example:**

```python
import polars as pl
from polars.testing import assert_frame_equal
from src.clean.harmonize import add_partner_flags

def test_add_partner_flags_ams(make_encounter_df):
    df = make_encounter_df(n_rows=2).with_columns(
        pl.Series("SOURCE", ["AMS", "FLM"])
    )

    result = add_partner_flags(df, partner_col="SOURCE")

    expected = df.with_columns([
        pl.Series("ICD_MAPPED", [1, 0], dtype=pl.Int8),
        pl.Series("CLAIMS_ONLY", [0, 1], dtype=pl.Int8),
        pl.Series("DEATH_ONLY", [0, 0], dtype=pl.Int8),
    ])

    assert_frame_equal(result, expected)
```

**Note:** polars.testing is not imported by default. Import as:

```python
from polars.testing import assert_frame_equal, assert_series_equal
```

**Source:** [Polars Testing Documentation](https://docs.pola.rs/py-polars/html/reference/testing.html)

### Pattern 4: Test Organization with Fixtures

**What:** Organize tests in subdirectories mirroring source code, use conftest.py at each level for shared fixtures.

**When to use:** For larger projects with multiple modules requiring test organization.

**Example structure:**

```
tests/
├── conftest.py                    # Root fixtures (global builders)
├── test_report/
│   ├── conftest.py                # Report-specific fixtures
│   ├── test_suppression.py
│   └── test_encounter_payer_summary.py
```

**Source:** [Good Integration Practices — pytest documentation](https://docs.pytest.org/en/7.1.x/explanation/goodpractices.html)

### Anti-Patterns to Avoid

- **Don't read from disk unless testing I/O:** Create DataFrames in-memory with pl.DataFrame() instead of reading Parquet files. Disk I/O slows tests and adds flakiness.

- **Don't use xfail for known bugs:** User constraint: "If current code is wrong, FIX the code in this phase (not xfail)". Mark test as passing after fixing the code.

- **Don't test implementation details:** Test the public API (what the function returns) not internal variables or helper functions.

- **Don't use magic values without explanation:** Use constants or parametrize IDs to explain what edge cases represent (e.g., ids=["dual_eligible_code_14", "dual_eligible_code_141"]).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DataFrame equality comparison | Manual column-by-column comparison loops | polars.testing.assert_frame_equal | Handles nulls, dtypes, ordering, provides clear error messages on mismatch |
| Edge case enumeration | Separate test functions per edge case | pytest.mark.parametrize | Single test function, table of cases, automatic test ID generation |
| Test data builders | Copy-paste DataFrame construction | Factory fixtures in conftest.py | DRY principle, sensible defaults, easy overrides |
| Property-based testing | Manual edge case listing | hypothesis + polars.testing.parametric (optional) | Generates thousands of test cases automatically, but user wants explicit enumeration |

**Key insight:** Testing data pipelines involves many similar DataFrame transformations. Builder functions + parametrize + DataFrame assertions eliminate boilerplate while keeping tests readable.

## Common Pitfalls

### Pitfall 1: Forgetting to Import polars.testing

**What goes wrong:** ImportError or AttributeError when trying to use assert_frame_equal.

**Why it happens:** polars.testing is not imported by default to optimize import speed.

**How to avoid:** Explicitly import testing utilities:

```python
from polars.testing import assert_frame_equal, assert_series_equal
```

**Warning signs:** Code tries to use pl.testing.assert_frame_equal without importing.

**Source:** [Polars Testing Documentation](https://docs.pola.rs/py-polars/html/reference/testing.html)

### Pitfall 2: Testing Current Behavior Instead of Expected Behavior

**What goes wrong:** Tests pass but code is wrong because tests codify bugs.

**Why it happens:** Developer writes tests after implementation, copies output as "expected" without validating correctness.

**How to avoid:**
1. Read docstring and understand EXPECTED behavior before writing test
2. For ambiguous cases, check TODO(audit) items for known issues
3. User constraint: "If current code is wrong, FIX the code in this phase"

**Warning signs:** Test expected values match current output exactly but don't match clinical logic or PCORnet standards.

### Pitfall 3: Incomplete Edge Case Coverage

**What goes wrong:** Tests pass but production data hits untested edge case, pipeline crashes or produces wrong results.

**Why it happens:** Edge cases not enumerated exhaustively (nulls, empty strings, sentinel values, boundary dates).

**How to avoid:** User constraint mandates exhaustive enumeration. For each function:
1. List all PCORnet sentinel values (NI, UN, OT, 99, 9999)
2. Test null, empty string, and valid values
3. Test boundary dates (1900-01-01, 2026-12-31, leap years, invalid dates)
4. Test mixed format scenarios for dates

**Warning signs:** Parametrize table has <5 cases for a function that handles sentinel values or date parsing.

### Pitfall 4: Testing with Unrealistic Data

**What goes wrong:** Tests pass with clean synthetic data but fail on real PCORnet data with quirks.

**Why it happens:** Test data uses simple values that don't match PCORnet value sets (e.g., payer codes "1", "2" instead of "11", "21").

**How to avoid:** User constraint: "Use actual PCORnet CDM value sets for realistic column names and value ranges". Reference:
- DX_TYPE values: "09" (ICD-9), "10" (ICD-10)
- ENC_TYPE values: "IP" (inpatient), "ED" (ED), "AV" (ambulatory), "OA" (other ambulatory)
- PAYER_TYPE_PRIMARY: "11" (Medicare FFS), "21" (Medicaid FFS), "14" (dual eligible), "NI" (no information)

**Warning signs:** Test data uses integer codes (1, 2) or generic strings ("payer1", "payer2") instead of PCORnet codes.

**Source:** [PCORnet CDM Data Quality Validation](https://pcornet.org/news/resources-common-data-model-cdm-data-quality-validation/)

### Pitfall 5: Slow Tests Due to Disk I/O

**What goes wrong:** Test suite takes minutes to run because tests write/read Parquet files.

**Why it happens:** Tests unnecessarily persist DataFrames to disk when in-memory testing would work.

**How to avoid:** User constraint: "Synthetic minimal fixtures: hand-crafted Polars DataFrames in each test, minimal rows, no files on disk". Only test Parquet I/O if:
- Testing checkpoint persistence (validate_row_count after Parquet round-trip)
- Testing convert_table() Parquet writing

**Warning signs:** Test writes to tmp files or parquet_dir for testing logic that doesn't need persistence.

### Pitfall 6: Ignoring TODO(audit) Items

**What goes wrong:** Tests don't cover known unknowns, Phase 3 doesn't resolve audit items, technical debt carries forward.

**Why it happens:** Developer writes tests for happy path, doesn't review AUDIT_LOG.md or inline TODO(audit) comments.

**How to avoid:** User constraint: "Systematically resolve ALL TODO(audit) items from Phase 1". Process:
1. Grep for TODO(audit) in src/ (18 items found)
2. Read AUDIT_LOG.md for HIGH/MEDIUM/LOW severity items
3. For each TODO(audit), either:
   - Fix the code if behavior is wrong
   - Add test coverage if behavior is correct but untested
   - Document decision in docstring if ambiguous

**Warning signs:** Phase 3 completes without closing all TODO(audit) items or updating AUDIT_LOG.md.

## Code Examples

Verified patterns from official sources and codebase.

### Creating Test DataFrames with Builder Functions

```python
# conftest.py
import polars as pl
from datetime import date
import pytest

@pytest.fixture
def make_diagnosis_df():
    """Factory for DIAGNOSIS DataFrames with PCORnet defaults."""
    def _make(
        n_rows=3,
        patid_col="ID",
        dx_codes=None,
        dx_types=None,
        dx_dates=None,
    ):
        ids = [f"PT{i:03d}" for i in range(n_rows)]

        # Default to HL ICD-10 codes
        codes = dx_codes or ["C81.10", "C81.11", "C81.12"][:n_rows]

        # Default to ICD-10
        types = dx_types or ["10"] * n_rows

        # Default to recent dates
        dates = dx_dates or [date(2025, 1, i+1) for i in range(n_rows)]

        return pl.DataFrame({
            patid_col: ids,
            "ENCOUNTERID": [f"ENC{i:05d}" for i in range(n_rows)],
            "DX": codes,
            "DX_TYPE": types,
            "DX_DATE": dates,
        })
    return _make

@pytest.fixture
def make_encounter_df():
    """Factory for ENCOUNTER DataFrames with PCORnet defaults."""
    def _make(
        n_rows=3,
        patid_col="ID",
        payer_primary=None,
        payer_secondary=None,
        admit_dates=None,
        enc_types=None,
    ):
        ids = [f"PT{i:03d}" for i in range(n_rows)]

        # Default to Medicare FFS
        payer_pri = payer_primary or ["11"] * n_rows

        # Default to Medicaid FFS (creates dual-eligible scenario)
        payer_sec = payer_secondary or ["21"] * n_rows

        # Default to recent dates
        dates = admit_dates or [date(2025, 1, i+1) for i in range(n_rows)]

        # Default to inpatient
        enc_type = enc_types or ["IP"] * n_rows

        return pl.DataFrame({
            patid_col: ids,
            "ENCOUNTERID": [f"ENC{i:05d}" for i in range(n_rows)],
            "PAYER_TYPE_PRIMARY": payer_pri,
            "PAYER_TYPE_SECONDARY": payer_sec,
            "ADMIT_DATE": dates,
            "ENC_TYPE": enc_type,
        })
    return _make

@pytest.fixture
def make_enrollment_df():
    """Factory for ENROLLMENT DataFrames."""
    def _make(
        n_rows=3,
        patid_col="ID",
        enr_start_dates=None,
        enr_end_dates=None,
    ):
        ids = [f"PT{i:03d}" for i in range(n_rows)]

        # Default to 2020-2025 enrollment
        start_dates = enr_start_dates or [date(2020, 1, 1)] * n_rows
        end_dates = enr_end_dates or [date(2025, 12, 31)] * n_rows

        return pl.DataFrame({
            patid_col: ids,
            "ENR_START_DATE": start_dates,
            "ENR_END_DATE": end_dates,
        })
    return _make
```

### Exhaustive Edge Case Testing with Parametrize

```python
import pytest
from src.report.suppression import suppress, flag_small_cell

# Test suppression boundary values
@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "0"),        # Zero is safe to display
        (1, "-"),        # Small cell (suppress)
        (5, "-"),        # Small cell (suppress)
        (10, "-"),       # At threshold (suppress)
        (11, "11"),      # Above threshold (safe)
        (100, "100"),    # Large value (safe)
    ],
    ids=["zero", "one", "mid_small", "threshold", "above_threshold", "large"]
)
def test_suppress_boundary_values(value, expected):
    """Test HIPAA suppression at boundary values."""
    assert suppress(value) == expected

# Test flagging boundary values
@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "0"),        # Zero (no flag)
        (1, "1 ⚠"),      # Small cell (flag)
        (10, "10 ⚠"),    # At threshold (flag)
        (11, "11"),      # Above threshold (no flag)
    ],
    ids=["zero", "one", "threshold", "above_threshold"]
)
def test_flag_small_cell_boundary_values(value, expected):
    """Test small-cell flagging at boundary values."""
    assert flag_small_cell(value) == expected
```

### Testing Payer Logic Edge Cases

```python
import pytest
import polars as pl
from polars.testing import assert_series_equal

# Assume src/report/encounter_payer_summary.py has extract of payer logic
from src.report.encounter_payer_summary import (
    _collapse_payer_category,
    _payer_category_from_effective_and_dual,
    INVALID_PAYER,
    DUAL_ELIGIBLE_CODES,
)

@pytest.mark.parametrize(
    "payer_code,expected_category",
    [
        # Valid payer categories
        ("11", "Medicare"),          # Medicare FFS
        ("121", "Medicare"),         # Medicare Advantage
        ("21", "Medicaid"),          # Medicaid FFS
        ("221", "Medicaid"),         # Medicaid managed care
        ("51", "Private"),           # Commercial insurance
        ("61", "Private"),           # Self-insured
        ("31", "Other government"),  # VA
        ("41", "Other government"),  # Corrections (NOT dual-eligible)
        ("81", "No payment / Self-pay"),

        # Sentinel values
        ("NI", "Unknown"),           # No information
        ("UN", "Unknown"),           # Unknown
        ("OT", "Unknown"),           # Other
        ("UNKNOWN", "Unknown"),      # Legacy string
        ("99", "Unavailable"),       # Sentinel (when INCLUDE_99_AS_SENTINEL=False)
        ("9999", "Unavailable"),     # Sentinel

        # Edge cases
        (None, "Unknown"),           # Null
        ("", "Unknown"),             # Empty string
        ("   ", "Unknown"),          # Whitespace
        ("ZZ", "Other"),             # Unrecognized code
    ],
    ids=[
        "medicare_ffs", "medicare_advantage", "medicaid_ffs", "medicaid_managed",
        "commercial", "self_insured", "va", "corrections_not_dual", "self_pay",
        "ni_sentinel", "un_sentinel", "ot_sentinel", "unknown_string",
        "sentinel_99", "sentinel_9999",
        "null", "empty", "whitespace", "unrecognized"
    ]
)
def test_collapse_payer_category_edge_cases(payer_code, expected_category):
    """Test payer category mapping for all PCORnet codes and sentinel values."""
    assert _collapse_payer_category(payer_code) == expected_category

@pytest.mark.parametrize(
    "effective_payer,dual_eligible,expected_category",
    [
        # Dual-eligible override
        ("11", 1, "Dual eligible"),   # Medicare + dual flag → dual category
        ("21", 1, "Dual eligible"),   # Medicaid + dual flag → dual category
        ("99", 1, "Dual eligible"),   # Unavailable + dual flag → dual category

        # Not dual-eligible
        ("11", 0, "Medicare"),        # Medicare without dual flag
        ("21", 0, "Medicaid"),        # Medicaid without dual flag
        ("51", 0, "Private"),         # Private without dual flag
    ],
    ids=[
        "dual_medicare", "dual_medicaid", "dual_unavailable",
        "medicare_only", "medicaid_only", "private_only"
    ]
)
def test_payer_category_dual_eligible_override(effective_payer, dual_eligible, expected_category):
    """Test that dual-eligible flag overrides standard payer categorization."""
    assert _payer_category_from_effective_and_dual(effective_payer, dual_eligible) == expected_category
```

### Testing Date Parsing Edge Cases

```python
import pytest
import polars as pl
from datetime import date
from src.load.convert import detect_date_columns, convert_date_column

def test_detect_date_columns_null_column():
    """Date detection should skip all-null columns."""
    df = pl.DataFrame({
        "DX_DATE": [None, None, None],
        "DX": ["C81.10", "C81.11", "C81.12"]
    })
    detected = detect_date_columns(df)
    assert "DX_DATE" not in detected

def test_detect_date_columns_empty_string_column():
    """Date detection should skip all-empty-string columns."""
    df = pl.DataFrame({
        "DX_DATE": ["", "", ""],
        "DX": ["C81.10", "C81.11", "C81.12"]
    })
    detected = detect_date_columns(df)
    assert "DX_DATE" not in detected

@pytest.mark.parametrize(
    "date_strings,expected_format",
    [
        # SAS DATE9 format
        (["01JAN2020", "15FEB2020", "31DEC2020"], "%d%b%Y"),

        # SAS DATETIME format
        (["01JAN2020:00:00:00", "15FEB2020:14:30:00"], "%d%b%Y:%H:%M:%S"),

        # YYYYMMDD tumor registry format
        (["20200101", "20200215", "20201231"], "%Y%m%d"),

        # Mixed formats in same column (should detect dominant format)
        # 70% DATE9, 30% YYYYMMDD → should detect DATE9
        (["01JAN2020"] * 7 + ["20200101"] * 3, "%d%b%Y"),
    ],
    ids=["date9", "datetime", "yyyymmdd", "mixed_dominant_date9"]
)
def test_detect_date_columns_format_detection(date_strings, expected_format):
    """Test detection of different SAS date formats."""
    df = pl.DataFrame({"DX_DATE": date_strings})
    detected = detect_date_columns(df)
    assert detected.get("DX_DATE") == expected_format

def test_convert_date_column_boundary_dates():
    """Test conversion handles boundary dates (1900-01-01, leap years, future dates)."""
    df = pl.DataFrame({
        "TEST_DATE": [
            "01JAN1900",  # PCORnet minimum date (masked birth dates)
            "29FEB2020",  # Leap year
            "31DEC2026",  # Near MAX_DATE boundary
        ]
    })
    converted, stats = convert_date_column(df, "TEST_DATE", "%d%b%Y")

    assert stats["action"] == "converted"
    assert converted["TEST_DATE"].dtype == pl.Date
    assert converted["TEST_DATE"][0] == date(1900, 1, 1)
    assert converted["TEST_DATE"][1] == date(2020, 2, 29)
    assert converted["TEST_DATE"][2] == date(2026, 12, 31)

def test_convert_date_column_invalid_dates():
    """Test conversion keeps column as string when >10% parse failures (mixed formats)."""
    # Mix valid DATE9 with invalid strings
    df = pl.DataFrame({
        "TEST_DATE": [
            "01JAN2020",  # Valid DATE9
            "20200215",   # YYYYMMDD (wrong format for DATE9 parser)
            "invalid",    # Invalid
        ]
    })
    converted, stats = convert_date_column(df, "TEST_DATE", "%d%b%Y")

    # 2/3 fail to parse = 66.7% > 10% threshold
    assert stats["action"] == "kept_as_string"
    assert converted["TEST_DATE"].dtype == pl.Utf8

def test_convert_date_column_nulls_preserved():
    """Test conversion preserves existing nulls (doesn't count as parse failure)."""
    df = pl.DataFrame({
        "TEST_DATE": [
            "01JAN2020",  # Valid
            None,         # Already null (not a parse failure)
            "15FEB2020",  # Valid
        ]
    })
    converted, stats = convert_date_column(df, "TEST_DATE", "%d%b%Y")

    assert stats["action"] == "converted"
    assert converted["TEST_DATE"].dtype == pl.Date
    # Original null count = 1, new null count should still be 1
    assert stats["new_nulls"] == 0
```

### Testing Checkpoint Validation

```python
import pytest
import polars as pl
from src.validate.checkpoint import (
    CheckpointError,
    validate_row_count,
    validate_no_vanish,
    validate_schema,
)

def test_validate_row_count_exact_match_pass():
    """Exact row count validation should pass when counts match."""
    df = pl.DataFrame({"ID": ["PT001", "PT002", "PT003"]})
    result = validate_row_count(df, "load", "DIAGNOSIS", expected=3, tolerance=0.0)

    assert result.passed
    assert result.actual == 3
    assert result.expected == 3

def test_validate_row_count_exact_match_fail():
    """Exact row count validation should raise CheckpointError on mismatch."""
    df = pl.DataFrame({"ID": ["PT001", "PT002"]})

    with pytest.raises(CheckpointError) as exc_info:
        validate_row_count(df, "load", "DIAGNOSIS", expected=3, tolerance=0.0)

    assert "expected=3" in str(exc_info.value)
    assert "got=2" in str(exc_info.value)

def test_validate_row_count_tolerance_pass():
    """Tolerance mode should pass when loss within tolerance."""
    df = pl.DataFrame({"ID": ["PT001", "PT002", "PT003"]})
    # Allow 2% loss: 100 * 0.02 = 2 rows
    # Actual: 98 rows, expected: 100, delta = -2 (within tolerance)
    result = validate_row_count(df, "dedup", "DIAGNOSIS", expected=100, tolerance=0.02)

    # Should fail because we only have 3 rows (97 rows missing)
    # 3 - 100 = -97, abs(-97) = 97 > 2
    with pytest.raises(CheckpointError):
        validate_row_count(df, "dedup", "DIAGNOSIS", expected=100, tolerance=0.02)

def test_validate_schema_missing_column():
    """Schema validation should raise CheckpointError for missing columns."""
    df = pl.DataFrame({
        "ID": ["PT001"],
        "DX": ["C81.10"],
        # Missing DX_TYPE
    })

    expected_schema = {
        "ID": pl.Utf8,
        "DX": pl.Utf8,
        "DX_TYPE": pl.Utf8,
    }

    with pytest.raises(CheckpointError) as exc_info:
        validate_schema(df, "typing", "DIAGNOSIS", expected_schema)

    assert "missing_columns" in str(exc_info.value)
    assert "DX_TYPE" in str(exc_info.value)

def test_validate_schema_wrong_dtype():
    """Schema validation should raise CheckpointError for wrong dtypes."""
    df = pl.DataFrame({
        "ID": ["PT001"],
        "DX_DATE": ["2025-01-01"],  # String, not Date
    })

    expected_schema = {
        "ID": pl.Utf8,
        "DX_DATE": pl.Date,  # Expect Date dtype
    }

    with pytest.raises(CheckpointError) as exc_info:
        validate_schema(df, "typing", "DIAGNOSIS", expected_schema)

    assert "dtype_mismatch" in str(exc_info.value)

def test_validate_schema_dtype_flexibility():
    """Schema validation should accept multiple dtypes when specified as tuple."""
    # Date detection may fail, leaving column as String
    df = pl.DataFrame({
        "ID": ["PT001"],
        "DX_DATE": ["2025-01-01"],  # String (date detection failed)
    })

    expected_schema = {
        "ID": pl.Utf8,
        "DX_DATE": (pl.Date, pl.Utf8),  # Accept either Date or String
    }

    result = validate_schema(df, "typing", "DIAGNOSIS", expected_schema)
    assert result.passed
```

### Testing Report Generation with Suppression

```python
import pytest
import polars as pl
from polars.testing import assert_frame_equal
from src.report.quality_report import aggregate_dq_metrics
from src.report.suppression import suppress

def test_report_suppression_applied(make_diagnosis_df):
    """Test that report generation applies HIPAA suppression correctly."""
    # Create diagnosis data with small cell counts
    df = make_diagnosis_df(n_rows=15).with_columns(
        pl.Series("DX", [
            "C81.10", "C81.10",  # Count = 2 (suppress)
            "C81.11", "C81.11", "C81.11", "C81.11", "C81.11",  # Count = 5 (suppress)
            "C81.12"] * 8  # Count = 8 (suppress)
        )[:15]
    )

    # Group by DX and count
    counts = df.group_by("DX").agg(pl.len().alias("N"))

    # Apply suppression
    counts = counts.with_columns(
        pl.col("N").map_elements(suppress, return_dtype=pl.Utf8).alias("N_SUPPRESSED")
    )

    # Verify suppression applied
    expected = pl.DataFrame({
        "DX": ["C81.10", "C81.11", "C81.12"],
        "N": [2, 5, 8],
        "N_SUPPRESSED": ["-", "-", "-"]  # All suppressed (< 11)
    })

    assert_frame_equal(counts, expected)

def test_report_structure_completeness():
    """Test report output has expected structure (columns present)."""
    # Mock DQ metrics
    metrics = {
        "table": "DIAGNOSIS",
        "completeness_pct": 95.5,
        "conformance_pct": 99.2,
        "plausibility_issues": 3,
    }

    df = pl.DataFrame([metrics])

    # Verify expected columns present
    assert "table" in df.columns
    assert "completeness_pct" in df.columns
    assert "conformance_pct" in df.columns
    assert "plausibility_issues" in df.columns
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| unittest.TestCase | pytest with fixtures/parametrize | ~2015 | More readable, better parametrization, fixture composition |
| pandas.testing.assert_frame_equal | polars.testing.assert_frame_equal | Polars 0.13+ (2022) | Native Polars support, faster execution |
| Hardcoded test DataFrames | Factory fixtures in conftest.py | Pytest 3.0+ (2017) | DRY principle, reusable test data |
| Separate tests per edge case | @pytest.mark.parametrize | Pytest 2.3+ (2012) | One test function, table of cases |

**Deprecated/outdated:**
- unittest.TestCase: Still works but pytest fixtures are more flexible
- nose testing framework: No longer maintained, replaced by pytest
- doctest for complex logic: Better for documentation examples, not comprehensive testing

## Open Questions

### 1. Should checkpoint validation test Parquet round-trip persistence?

**What we know:**
- User constraint: "Synthetic minimal fixtures: hand-crafted Polars DataFrames in each test, minimal rows, no files on disk"
- Claude's discretion: "Checkpoint file I/O tests: Claude determines whether to include Parquet round-trip tests or stay in-memory only"

**What's unclear:** Does checkpoint validation need to test Parquet write/read reliability, or is in-memory validation sufficient?

**Recommendation:** START with in-memory validation only (validate_row_count, validate_schema on DataFrames). ADD Parquet round-trip tests ONLY if:
- Testing convert_table() which explicitly writes Parquet
- Testing checkpoint persistence across phase boundaries
- Keep Parquet tests minimal (1-2 tests) to avoid slow test suite

### 2. How granular should report test assertions be?

**What we know:**
- Claude's discretion: "Report test assertion style: Claude picks structural + spot-check vs exact values per report type"
- Reports include suppression (boundary values), aggregations (counts, percentages), and structure (columns present)

**What's unclear:** Should tests verify exact report content or just structure?

**Recommendation:** TWO-TIER approach:
- **Structural tests:** Verify columns present, dtypes correct, no crashes (always)
- **Spot-check tests:** Verify suppression applied at boundary values (0, 1, 10, 11), aggregation correctness on known inputs (e.g., 3 records → count=3)
- **NOT exact value matching:** Don't test every cell in report output (brittle, hard to maintain)

### 3. Should tests cover all 18 TODO(audit) items or just ones surfaced by testing?

**What we know:**
- User constraint: "Systematically resolve ALL TODO(audit) items from Phase 1 — not just ones that surface through test writing"
- 18 TODO(audit) items found in src/ (grep count)
- AUDIT_LOG.md documents HIGH/MEDIUM/LOW severity items

**What's unclear:** N/A — user constraint is explicit

**Recommendation:** SYSTEMATIC AUDIT RESOLUTION:
1. Grep for all TODO(audit) in src/ (18 items)
2. Read AUDIT_LOG.md for context (HIGH: sentinel 99/9999, date thresholds, LAB_RESULT_CM mismatch; MEDIUM: 30-day windows, dedup keys)
3. For EACH item, either:
   - FIX code if behavior is wrong (e.g., INCLUDE_99_AS_SENTINEL clarification)
   - ADD test coverage if behavior is correct but untested
   - DOCUMENT decision in docstring if ambiguous (e.g., 30-day window rationale)
4. Update AUDIT_LOG.md with resolution status
5. Remove TODO(audit) comments after resolution

## Sources

### Primary (HIGH confidence)

- [Pytest parametrize documentation](https://docs.pytest.org/en/stable/how-to/parametrize.html) - Official pytest parametrization guide
- [Polars Testing Documentation](https://docs.pola.rs/py-polars/html/reference/testing.html) - Official Polars testing utilities
- [Pytest fixtures documentation](https://docs.pytest.org/en/stable/how-to/fixtures.html) - Official pytest fixture guide
- [Pytest good practices](https://docs.pytest.org/en/7.1.x/explanation/goodpractices.html) - Official test organization guidance

### Secondary (MEDIUM confidence)

- [5 Best Practices For Organizing Tests](https://pytest-with-eric.com/pytest-best-practices/pytest-organize-tests/) - Test organization patterns (mirroring src/ structure)
- [Five Advanced Pytest Fixture Patterns](https://www.inspiredpython.com/article/five-advanced-pytest-fixture-patterns) - Factory fixtures pattern
- [PCORnet CDM Data Quality Validation](https://pcornet.org/news/resources-common-data-model-cdm-data-quality-validation/) - PCORnet validation framework (December 2024)
- [Handling Edge Cases In Boundary Testing](https://fastercapital.com/topics/handling-edge-cases-in-boundary-testing.html) - Date edge cases methodology

### Tertiary (LOW confidence)

- Web searches provided general patterns but official docs are authoritative for pytest and Polars

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - pytest 9.0.2 and polars 1.38.1 already installed, well-documented
- Architecture: HIGH - Mirroring pattern, factory fixtures, parametrize are established pytest patterns
- Pitfalls: HIGH - Based on common testing anti-patterns and user constraints

**Research date:** 2026-03-17
**Valid until:** 60 days (stable testing patterns, pytest 9.x, Polars 1.x)

**TODO(audit) Resolution Strategy:**
Phase 3 MUST address all 18 TODO(audit) items systematically:
1. AUDIT-001: INCLUDE_99_AS_SENTINEL flag (HIGH) - Test both behaviors, document decision
2. AUDIT-002: Date detection thresholds 30%/50% (HIGH) - Test edge cases, validate on sample data
3. AUDIT-003: LAB_RESULT_CM vs LAB_RESULT mismatch (HIGH) - Test resolve_table_name() aliasing
4. Remaining 15 items: Review AUDIT_LOG.md, test or document per item

Phase 3 success = ALL TODO(audit) resolved (fixed, tested, or documented).
