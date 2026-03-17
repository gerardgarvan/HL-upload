"""Checkpoint validation for HL pipeline phase boundaries.

This module provides row-count and schema validation at critical pipeline phase
transitions to catch data loss, schema drift, and transformation errors before
they propagate downstream.

**Pipeline Position:** Cross-phase validation layer (used at all phase boundaries)

**Key Design Principles:**
1. Fail fast with structured logging - all failures print machine-parseable logs
2. Strict vs tolerance modes - row-count can be exact or allow controlled loss
3. Plain Polars dtypes - no external validation frameworks needed
4. Exception-based control flow - CheckpointError signals validation failures

**Typical Usage:**

    from src.validate.checkpoint import (
        CheckpointError,
        validate_row_count,
        validate_no_vanish,
        validate_schema
    )
    from src.validate.schemas import CRITICAL_SCHEMAS

    # After loading phase
    result = validate_row_count(df, "load", "DIAGNOSIS", expected=150000)

    # After dedup phase (allow up to 2% loss for legitimate duplicates)
    result = validate_row_count(df, "dedup", "DIAGNOSIS", expected=150000, tolerance=0.02)

    # Schema validation at type conversion
    result = validate_schema(df, "typing", "DIAGNOSIS", CRITICAL_SCHEMAS["DIAGNOSIS"])

**Structured Log Format:**
- Success: `[CHECKPOINT PASS] phase={phase} table={table} rows={actual}`
- Failure: `[CHECKPOINT FAIL] phase={phase} table={table} expected={expected} got={actual} delta={delta}`
- Schema: `[SCHEMA OK] phase={phase} table={table} columns={N} validated`
"""

from dataclasses import dataclass
from typing import Union

import polars as pl


class CheckpointError(Exception):
    """Raised when checkpoint validation fails (row count, schema, or vanish check).

    This exception signals that data has deviated from expected state at a phase
    boundary. Catching this exception allows pipeline orchestrators to log the
    failure and halt processing before bad data propagates downstream.
    """
    pass


@dataclass
class CheckpointResult:
    """Result of a checkpoint validation operation.

    Captures validation metadata for logging and downstream decision-making.
    Even passing validations return a CheckpointResult for audit trail purposes.

    Attributes:
        phase: Pipeline phase where validation occurred (e.g., "load", "dedup", "typing")
        table: Table name being validated (e.g., "DIAGNOSIS", "ENCOUNTER")
        passed: True if validation succeeded, False if it failed
        expected: Expected value (row count or None for schema-only checks)
        actual: Actual value observed (row count or None)
        message: Human-readable validation message (includes structured log output)
    """
    phase: str
    table: str
    passed: bool
    expected: int | None
    actual: int | None
    message: str


def validate_row_count(
    df: pl.DataFrame,
    phase: str,
    table: str,
    expected: int,
    tolerance: float = 0.0
) -> CheckpointResult:
    """Validate DataFrame row count against expected value with optional tolerance.

    This is the primary checkpoint for detecting data loss or unexpected row count
    changes between pipeline phases. Supports both strict mode (no loss allowed)
    and tolerance mode (for phases like dedup where some row reduction is expected).

    **Strict Mode (tolerance=0.0):**
    Any difference between expected and actual row count raises CheckpointError.
    Use for phases where row count should be preserved exactly (load, typing).

    **Tolerance Mode (tolerance>0.0):**
    Allows row count to deviate by up to (tolerance * expected) rows.
    Raises CheckpointError only if deviation exceeds tolerance.
    Use for dedup phases where legitimate duplicate removal is expected.

    Args:
        df: DataFrame to validate
        phase: Pipeline phase name (for logging)
        table: Table name (for logging)
        expected: Expected row count
        tolerance: Allowed deviation as fraction of expected (0.0 = strict, 0.02 = 2%)

    Returns:
        CheckpointResult with passed=True if validation succeeded

    Raises:
        CheckpointError: If row count deviates beyond tolerance

    Example:
        # Strict validation after load
        result = validate_row_count(df, "load", "DIAGNOSIS", 150000)

        # Allow up to 2% loss during dedup
        result = validate_row_count(df, "dedup", "DIAGNOSIS", 150000, tolerance=0.02)
    """
    actual = df.height
    delta = actual - expected

    if tolerance == 0.0:
        # Strict mode: any difference is an error
        if delta != 0:
            msg = f"[CHECKPOINT FAIL] phase={phase} table={table} expected={expected} got={actual} delta={delta}"
            print(msg)
            raise CheckpointError(msg)
    else:
        # Tolerance mode: allow deviation within tolerance
        max_deviation = abs(tolerance * expected)
        if abs(delta) > max_deviation:
            msg = f"[CHECKPOINT FAIL] phase={phase} table={table} expected={expected} got={actual} delta={delta} tolerance={tolerance} max_allowed={max_deviation}"
            print(msg)
            raise CheckpointError(msg)

    # Success
    msg = f"[CHECKPOINT PASS] phase={phase} table={table} rows={actual}"
    print(msg)
    return CheckpointResult(
        phase=phase,
        table=table,
        passed=True,
        expected=expected,
        actual=actual,
        message=msg
    )


def validate_no_vanish(
    df: pl.DataFrame,
    phase: str,
    table: str,
    min_rows: int
) -> CheckpointResult:
    """Validate that DataFrame has at least min_rows (detect catastrophic data loss).

    This is a sanity-check validation for detecting complete table loss or
    catastrophic filtering errors. Unlike validate_row_count which checks exact
    counts, this ensures output has a reasonable minimum number of rows.

    Use when expected row count is unknown but there should be a baseline minimum
    (e.g., "we should have at least 100K patients after any filtering").

    Args:
        df: DataFrame to validate
        phase: Pipeline phase name (for logging)
        table: Table name (for logging)
        min_rows: Minimum acceptable row count

    Returns:
        CheckpointResult with passed=True if df.height >= min_rows

    Raises:
        CheckpointError: If df.height < min_rows (output lost rows vs input)

    Example:
        # Ensure we have at least 100K records after aggressive filtering
        result = validate_no_vanish(df, "filter", "DIAGNOSIS", 100000)
    """
    actual = df.height

    if actual < min_rows:
        delta = actual - min_rows  # Will be negative
        msg = f"[CHECKPOINT FAIL] phase={phase} table={table} expected_min={min_rows} got={actual} delta={delta}"
        print(msg)
        raise CheckpointError(msg)

    # Success
    msg = f"[CHECKPOINT PASS] phase={phase} table={table} rows={actual} (>= {min_rows})"
    print(msg)
    return CheckpointResult(
        phase=phase,
        table=table,
        passed=True,
        expected=min_rows,
        actual=actual,
        message=msg
    )


def validate_schema(
    df: pl.DataFrame,
    phase: str,
    table: str,
    expected_columns: dict[str, Union[type, tuple]]
) -> CheckpointResult:
    """Validate DataFrame schema against expected column names and dtypes.

    Checks that all expected columns exist in the DataFrame and have the correct
    Polars dtype. This is a non-strict check: extra columns in the DataFrame are
    allowed (for derived flags, intermediate columns, etc.).

    **Dtype Flexibility:**
    Column dtypes can be specified as:
    - Single type: pl.Utf8 (exact match required)
    - Tuple of types: (pl.Date, pl.Utf8) (any type in tuple accepted)

    Tuple mode is useful for columns where dtype may vary by source or date
    detection success (e.g., date columns may be pl.Date or pl.Utf8).

    Args:
        df: DataFrame to validate
        phase: Pipeline phase name (for logging)
        table: Table name (for logging)
        expected_columns: Dict mapping column name to expected dtype(s)
            - Single dtype: {"ID": pl.Utf8}
            - Multiple allowed: {"DX_DATE": (pl.Date, pl.Utf8)}

    Returns:
        CheckpointResult with passed=True if all expected columns exist with correct dtypes

    Raises:
        CheckpointError: If any expected column is missing or has wrong dtype

    Example:
        from src.validate.schemas import CRITICAL_SCHEMAS
        result = validate_schema(df, "typing", "DIAGNOSIS", CRITICAL_SCHEMAS["DIAGNOSIS"])
    """
    actual_schema = {col: dtype for col, dtype in zip(df.columns, df.dtypes)}

    # Check for missing columns
    missing_cols = [col for col in expected_columns if col not in actual_schema]
    if missing_cols:
        msg = f"[CHECKPOINT FAIL] phase={phase} table={table} missing_columns={missing_cols}"
        print(msg)
        raise CheckpointError(msg)

    # Check for dtype mismatches
    dtype_errors = {}
    for col, expected_dtype in expected_columns.items():
        actual_dtype = actual_schema[col]

        # Handle tuple of allowed dtypes
        if isinstance(expected_dtype, tuple):
            if actual_dtype not in expected_dtype:
                dtype_errors[col] = f"expected_one_of={expected_dtype} got={actual_dtype}"
        else:
            # Single dtype - exact match required
            if actual_dtype != expected_dtype:
                dtype_errors[col] = f"expected={expected_dtype} got={actual_dtype}"

    if dtype_errors:
        msg = f"[CHECKPOINT FAIL] phase={phase} table={table} dtype_mismatch={dtype_errors}"
        print(msg)
        raise CheckpointError(msg)

    # Success
    num_validated = len(expected_columns)
    msg = f"[SCHEMA OK] phase={phase} table={table} columns={num_validated} validated"
    print(msg)
    return CheckpointResult(
        phase=phase,
        table=table,
        passed=True,
        expected=None,
        actual=None,
        message=msg
    )
