"""Comprehensive tests for checkpoint validation functions.

Tests cover row-count validation (strict and tolerance modes), schema validation
(missing columns, wrong dtypes, dtype flexibility), and no-vanish validation
(catastrophic data loss detection).
"""

import pytest
import polars as pl
from src.validate.checkpoint import (
    CheckpointError,
    CheckpointResult,
    validate_row_count,
    validate_no_vanish,
    validate_schema
)


# ---------------------------------------------------------------------------
# Test validate_row_count: Strict mode (tolerance=0.0)
# ---------------------------------------------------------------------------

@pytest.mark.checkpoint
def test_validate_row_count_exact_match_pass():
    """Row count matches expected exactly - validation should pass."""
    df = pl.DataFrame({"ID": ["PT001", "PT002", "PT003"]})
    result = validate_row_count(df, "load", "DIAGNOSIS", expected=3, tolerance=0.0)

    assert result.passed is True
    assert result.actual == 3
    assert result.expected == 3
    assert result.phase == "load"
    assert result.table == "DIAGNOSIS"
    assert "[CHECKPOINT PASS]" in result.message


@pytest.mark.checkpoint
def test_validate_row_count_exact_match_fail():
    """Row count differs from expected - strict mode should fail."""
    df = pl.DataFrame({"ID": ["PT001", "PT002"]})

    with pytest.raises(CheckpointError) as excinfo:
        validate_row_count(df, "load", "DIAGNOSIS", expected=3, tolerance=0.0)

    error_msg = str(excinfo.value)
    assert "expected=3" in error_msg
    assert "got=2" in error_msg
    assert "delta=-1" in error_msg
    assert "[CHECKPOINT FAIL]" in error_msg


# ---------------------------------------------------------------------------
# Test validate_row_count: Tolerance mode (tolerance>0.0)
# ---------------------------------------------------------------------------

@pytest.mark.checkpoint
def test_validate_row_count_tolerance_pass():
    """Row count within tolerance - validation should pass.

    Test case: 98 rows vs 100 expected with 2% tolerance.
    Loss = 2 rows = 2% (exactly at threshold, should pass).
    """
    df = pl.DataFrame({"ID": [f"PT{i:03d}" for i in range(98)]})
    result = validate_row_count(df, "dedup", "DIAGNOSIS", expected=100, tolerance=0.02)

    assert result.passed is True
    assert result.actual == 98
    assert result.expected == 100
    assert "[CHECKPOINT PASS]" in result.message


@pytest.mark.checkpoint
def test_validate_row_count_tolerance_fail():
    """Row count exceeds tolerance - validation should fail.

    Test case: 95 rows vs 100 expected with 2% tolerance.
    Loss = 5 rows = 5% (exceeds 2% tolerance, should fail).
    """
    df = pl.DataFrame({"ID": [f"PT{i:03d}" for i in range(95)]})

    with pytest.raises(CheckpointError) as excinfo:
        validate_row_count(df, "dedup", "DIAGNOSIS", expected=100, tolerance=0.02)

    error_msg = str(excinfo.value)
    assert "expected=100" in error_msg
    assert "got=95" in error_msg
    assert "delta=-5" in error_msg
    assert "tolerance=0.02" in error_msg
    assert "[CHECKPOINT FAIL]" in error_msg


@pytest.mark.checkpoint
def test_validate_row_count_tolerance_gain():
    """Row count increases are also checked against tolerance.

    Test case: 105 rows vs 100 expected with 2% tolerance.
    Gain = 5 rows = 5% (exceeds 2% tolerance, should fail).
    """
    df = pl.DataFrame({"ID": [f"PT{i:03d}" for i in range(105)]})

    with pytest.raises(CheckpointError) as excinfo:
        validate_row_count(df, "typing", "DIAGNOSIS", expected=100, tolerance=0.02)

    error_msg = str(excinfo.value)
    assert "expected=100" in error_msg
    assert "got=105" in error_msg
    assert "delta=5" in error_msg


# ---------------------------------------------------------------------------
# Test validate_no_vanish: Catastrophic data loss detection
# ---------------------------------------------------------------------------

@pytest.mark.checkpoint
def test_validate_no_vanish_pass():
    """DataFrame has sufficient rows - validation should pass."""
    df = pl.DataFrame({"ID": [f"PT{i:03d}" for i in range(100)]})
    result = validate_no_vanish(df, "filter", "DIAGNOSIS", min_rows=50)

    assert result.passed is True
    assert result.actual == 100
    assert result.expected == 50
    assert "[CHECKPOINT PASS]" in result.message
    assert ">= 50" in result.message


@pytest.mark.checkpoint
def test_validate_no_vanish_fail():
    """DataFrame has too few rows - catastrophic loss detected."""
    df = pl.DataFrame({"ID": [f"PT{i:03d}" for i in range(10)]})

    with pytest.raises(CheckpointError) as excinfo:
        validate_no_vanish(df, "filter", "DIAGNOSIS", min_rows=50)

    error_msg = str(excinfo.value)
    assert "expected_min=50" in error_msg
    assert "got=10" in error_msg
    assert "delta=-40" in error_msg
    assert "[CHECKPOINT FAIL]" in error_msg


@pytest.mark.checkpoint
def test_validate_no_vanish_exact_boundary():
    """DataFrame exactly at minimum threshold - should pass."""
    df = pl.DataFrame({"ID": [f"PT{i:03d}" for i in range(50)]})
    result = validate_no_vanish(df, "filter", "DIAGNOSIS", min_rows=50)

    assert result.passed is True
    assert result.actual == 50


# ---------------------------------------------------------------------------
# Test validate_schema: Column presence and dtype matching
# ---------------------------------------------------------------------------

@pytest.mark.checkpoint
def test_validate_schema_all_columns_present_pass():
    """All expected columns present with correct dtypes - validation should pass."""
    df = pl.DataFrame({
        "ID": ["PT001"],
        "DX": ["C81.10"],
        "DX_TYPE": ["10"]
    })
    expected_schema = {
        "ID": pl.Utf8,
        "DX": pl.Utf8,
        "DX_TYPE": pl.Utf8
    }

    result = validate_schema(df, "typing", "DIAGNOSIS", expected_schema)

    assert result.passed is True
    assert result.phase == "typing"
    assert result.table == "DIAGNOSIS"
    assert "[SCHEMA OK]" in result.message
    assert "columns=3" in result.message


@pytest.mark.checkpoint
def test_validate_schema_missing_column_fail():
    """Expected column missing from DataFrame - validation should fail."""
    df = pl.DataFrame({
        "ID": ["PT001"],
        "DX": ["C81.10"]
        # Missing DX_TYPE
    })
    expected_schema = {
        "ID": pl.Utf8,
        "DX": pl.Utf8,
        "DX_TYPE": pl.Utf8
    }

    with pytest.raises(CheckpointError) as excinfo:
        validate_schema(df, "typing", "DIAGNOSIS", expected_schema)

    error_msg = str(excinfo.value)
    assert "missing_columns" in error_msg
    assert "DX_TYPE" in error_msg
    assert "[CHECKPOINT FAIL]" in error_msg


@pytest.mark.checkpoint
def test_validate_schema_wrong_dtype_fail():
    """Column has wrong dtype - validation should fail."""
    df = pl.DataFrame({
        "ID": ["PT001"],
        "DX_DATE": ["2025-01-01"]  # String, not Date
    })
    expected_schema = {
        "ID": pl.Utf8,
        "DX_DATE": pl.Date
    }

    with pytest.raises(CheckpointError) as excinfo:
        validate_schema(df, "typing", "DIAGNOSIS", expected_schema)

    error_msg = str(excinfo.value)
    assert "dtype_mismatch" in error_msg
    assert "DX_DATE" in error_msg


@pytest.mark.checkpoint
def test_validate_schema_dtype_flexibility():
    """Column dtype is one of allowed tuple options - validation should pass.

    Tests tuple dtype mode: allows either pl.Date or pl.Utf8 for date columns
    where parsing may fail and fall back to string representation.
    """
    df = pl.DataFrame({
        "ID": ["PT001"],
        "DX_DATE": ["2025-01-01"]  # String (date parsing failed)
    })
    expected_schema = {
        "ID": pl.Utf8,
        "DX_DATE": (pl.Date, pl.Utf8)  # Accept either Date or String
    }

    result = validate_schema(df, "typing", "DIAGNOSIS", expected_schema)

    assert result.passed is True
    assert "[SCHEMA OK]" in result.message


@pytest.mark.checkpoint
def test_validate_schema_dtype_flexibility_fail():
    """Column dtype not in allowed tuple options - validation should fail."""
    df = pl.DataFrame({
        "ID": ["PT001"],
        "COUNT": [42]  # Int64
    })
    expected_schema = {
        "ID": pl.Utf8,
        "COUNT": (pl.Utf8, pl.Float64)  # Accept String or Float, not Int
    }

    with pytest.raises(CheckpointError) as excinfo:
        validate_schema(df, "typing", "DIAGNOSIS", expected_schema)

    error_msg = str(excinfo.value)
    assert "dtype_mismatch" in error_msg
    assert "COUNT" in error_msg


@pytest.mark.checkpoint
def test_validate_schema_extra_columns_allowed():
    """DataFrame has extra columns beyond expected - should pass (non-strict).

    Extra columns are allowed for derived flags, intermediate columns, etc.
    """
    df = pl.DataFrame({
        "ID": ["PT001"],
        "DX": ["C81.10"],
        "DX_TYPE": ["10"],
        "ICD_MAPPED": [1],  # Extra flag column
        "_temp_col": ["foo"]  # Extra intermediate column
    })
    expected_schema = {
        "ID": pl.Utf8,
        "DX": pl.Utf8,
        "DX_TYPE": pl.Utf8
    }

    result = validate_schema(df, "typing", "DIAGNOSIS", expected_schema)

    assert result.passed is True
    assert "columns=3" in result.message  # Only 3 validated, not all 5


@pytest.mark.checkpoint
def test_validate_schema_multiple_missing_columns():
    """Multiple expected columns missing - all should be reported."""
    df = pl.DataFrame({
        "ID": ["PT001"]
        # Missing DX, DX_TYPE, DX_DATE
    })
    expected_schema = {
        "ID": pl.Utf8,
        "DX": pl.Utf8,
        "DX_TYPE": pl.Utf8,
        "DX_DATE": pl.Date
    }

    with pytest.raises(CheckpointError) as excinfo:
        validate_schema(df, "load", "DIAGNOSIS", expected_schema)

    error_msg = str(excinfo.value)
    assert "missing_columns" in error_msg
    assert "DX" in error_msg
    assert "DX_TYPE" in error_msg
    assert "DX_DATE" in error_msg


@pytest.mark.checkpoint
def test_validate_schema_multiple_dtype_mismatches():
    """Multiple columns have wrong dtypes - all should be reported."""
    df = pl.DataFrame({
        "ID": [123],  # Int64, should be Utf8
        "DX": ["C81.10"],
        "COUNT": ["42"]  # Utf8, should be Int64
    })
    expected_schema = {
        "ID": pl.Utf8,
        "DX": pl.Utf8,
        "COUNT": pl.Int64
    }

    with pytest.raises(CheckpointError) as excinfo:
        validate_schema(df, "typing", "DIAGNOSIS", expected_schema)

    error_msg = str(excinfo.value)
    assert "dtype_mismatch" in error_msg
    assert "ID" in error_msg
    assert "COUNT" in error_msg
