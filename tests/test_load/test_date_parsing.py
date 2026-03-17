"""Comprehensive test coverage for date parsing logic in src/load/convert.py.

Tests all 3 SAS date formats (DATE9, DATETIME, YYYYMMDD), edge cases for
nulls/mixed formats/invalid dates, boundary date handling, and parse failure
thresholds.

Resolves AUDIT-002 (thresholds), AUDIT-009 (parse failure reporting), and
AUDIT-018 (1900-01-01 births) through systematic edge case testing.
"""

import pytest
import polars as pl
from datetime import date

from src.load.convert import (
    detect_date_columns,
    convert_date_column,
    validate_date_range,
    DATE9_RE,
    DATETIME_RE,
    YYYYMMDD_RE,
    MIN_DATE,
    MAX_DATE,
)


# ---------------------------------------------------------------------------
# Test 1: Regex Pattern Matching
# ---------------------------------------------------------------------------


@pytest.mark.dates
@pytest.mark.parametrize(
    "pattern,test_string,expected_match",
    [
        # DATE9_RE tests
        (DATE9_RE, "01JAN2020", True),
        (DATE9_RE, "1JAN2020", False),  # needs 2-digit day
        (DATE9_RE, "01Jan2020", True),  # case insensitive
        (DATE9_RE, "31DEC2025", True),
        (DATE9_RE, "15FEB1999", True),
        (DATE9_RE, "01JAN20", False),  # needs 4-digit year
        (DATE9_RE, "01-JAN-2020", False),  # no separators
        # DATETIME_RE tests
        (DATETIME_RE, "01JAN2020:00:00:00", True),
        (DATETIME_RE, "01JAN2020", False),  # needs time component
        (DATETIME_RE, "01JAN2020:14:30:00", True),
        (DATETIME_RE, "01Jan2020:23:59:59", True),  # case insensitive
        (DATETIME_RE, "31DEC2025:12:00:00", True),
        (DATETIME_RE, "01JAN2020:0:0:0", False),  # needs 2-digit time parts
        # YYYYMMDD_RE tests
        (YYYYMMDD_RE, "20200101", True),
        (YYYYMMDD_RE, "2020010", False),  # needs 8 digits exactly
        (YYYYMMDD_RE, "202001011", False),  # too many digits
        (YYYYMMDD_RE, "19991231", True),
        (YYYYMMDD_RE, "20260915", True),
        (YYYYMMDD_RE, "2020-01-01", False),  # no separators
    ],
    ids=[
        "date9_valid",
        "date9_short_day",
        "date9_case_insensitive",
        "date9_dec",
        "date9_feb",
        "date9_short_year",
        "date9_with_separators",
        "datetime_valid",
        "datetime_no_time",
        "datetime_with_time",
        "datetime_case_insensitive",
        "datetime_dec",
        "datetime_short_time",
        "yyyymmdd_valid",
        "yyyymmdd_7_digits",
        "yyyymmdd_9_digits",
        "yyyymmdd_1999",
        "yyyymmdd_2026",
        "yyyymmdd_with_separators",
    ],
)
def test_date_format_regex_matching(pattern, test_string, expected_match):
    """Test regex patterns match expected formats correctly."""
    match = pattern.match(test_string) is not None
    assert match == expected_match, f"Pattern {pattern.pattern} {'should' if expected_match else 'should not'} match '{test_string}'"


# ---------------------------------------------------------------------------
# Test 2: Null Handling in Detection
# ---------------------------------------------------------------------------


@pytest.mark.dates
@pytest.mark.parametrize(
    "column_data,expected_detected",
    [
        ([None, None, None, None], False),  # all null
        (["", "", "", ""], False),  # all empty string
        ([None, "", None, ""], False),  # mix of null and empty
        ([None, None, "01JAN2020", "15FEB2020"], True),  # 50% null, 50% valid dates
        ([None, "01JAN2020", None, "15FEB2020", None, "31DEC2020"], True),  # 50% null, 50% valid dates
    ],
    ids=[
        "all_null",
        "all_empty_string",
        "null_and_empty_mix",
        "half_null_half_dates",
        "majority_null_some_dates",
    ],
)
def test_detect_date_columns_null_handling(column_data, expected_detected):
    """Test detection skips all-null columns but handles mixed null/valid correctly.

    Only non-null, non-empty values are counted toward format detection threshold.
    """
    df = pl.DataFrame({"test_date": column_data})
    detected = detect_date_columns(df)

    if expected_detected:
        assert "test_date" in detected, "Column with valid dates should be detected"
    else:
        assert "test_date" not in detected, "Column without valid values should not be detected"


# ---------------------------------------------------------------------------
# Test 3: Format Detection
# ---------------------------------------------------------------------------


@pytest.mark.dates
@pytest.mark.parametrize(
    "date_strings,expected_format",
    [
        # DATE9 format
        (["01JAN2020", "15FEB2020", "31DEC2020"], "%d%b%Y"),
        (["01Jan2020", "15Feb2020", "31Dec2020"], "%d%b%Y"),  # case variation
        # DATETIME format
        (["01JAN2020:00:00:00", "15FEB2020:14:30:00"], "%d%b%Y:%H:%M:%S"),
        (["01Jan2020:12:00:00", "15Feb2020:23:59:59"], "%d%b%Y:%H:%M:%S"),
        # YYYYMMDD format (requires name match, so use known date column)
        (["20200101", "20200215", "20201231"], "%Y%m%d"),
    ],
    ids=[
        "date9_standard",
        "date9_mixed_case",
        "datetime_standard",
        "datetime_mixed_case",
        "yyyymmdd_standard",
    ],
)
def test_detect_date_columns_format_detection(date_strings, expected_format):
    """Test detection identifies correct SAS format from value sampling.

    Uses known date column name to ensure YYYYMMDD is tested (requires name match).
    """
    # Use a known PCORnet date column name for detection
    df = pl.DataFrame({"BIRTH_DATE": date_strings})
    detected = detect_date_columns(df)

    assert "BIRTH_DATE" in detected, f"Should detect date column with {expected_format}"
    assert detected["BIRTH_DATE"] == expected_format, f"Should detect format as {expected_format}"


# ---------------------------------------------------------------------------
# Test 4: Mixed Format Detection (AUDIT-002)
# ---------------------------------------------------------------------------


@pytest.mark.dates
@pytest.mark.parametrize(
    "date_mix,expected_detected,expected_format",
    [
        # 70% DATE9 + 30% YYYYMMDD → should detect DATE9 (dominant format)
        (
            ["01JAN2020", "15FEB2020", "31DEC2020", "01APR2021", "15MAY2021", "30JUN2021", "15JUL2021",
             "20200101", "20200215", "20201231"],
            True,
            "%d%b%Y"
        ),
        # 50% DATE9 + 50% YYYYMMDD → should detect DATE9 (first format tested wins at tie)
        (
            ["01JAN2020", "15FEB2020", "31DEC2020", "01APR2021", "15MAY2021",
             "20200101", "20200215", "20201231", "20210401", "20210515"],
            True,
            "%d%b%Y"
        ),
        # 60% invalid + 40% DATE9 → should NOT detect (below 50% value-only threshold)
        # Note: Using non-known column name to trigger 50% threshold instead of 30%
        (
            ["invalid1", "invalid2", "invalid3", "invalid4", "invalid5", "invalid6",
             "01JAN2020", "15FEB2020", "31DEC2020", "01APR2021"],
            False,
            None
        ),
    ],
    ids=[
        "70pct_date9_30pct_yyyymmdd",
        "50pct_date9_50pct_yyyymmdd",
        "60pct_invalid_40pct_date9",
    ],
)
def test_detect_date_columns_mixed_formats(date_mix, expected_detected, expected_format):
    """Test detection with mixed formats validates threshold logic.

    AUDIT-002: Validate thresholds (30% name+value, 50% value-only) against
    mixed-format scenarios.

    Threshold logic:
    - 30% match required when column name matches date pattern (high confidence)
    - 50% match required for value-only detection (avoid false positives)
    - Dominant format wins when multiple formats present above threshold
    """
    # Test 1 & 2: Use known date column (30% threshold)
    if expected_detected:
        df = pl.DataFrame({"BIRTH_DATE": date_mix})
        detected = detect_date_columns(df)
        assert "BIRTH_DATE" in detected, "Should detect dominant format"
        assert detected["BIRTH_DATE"] == expected_format, f"Should detect {expected_format} as dominant"
    else:
        # Test 3: Use non-date column name (50% threshold)
        df = pl.DataFrame({"patient_id": date_mix})
        detected = detect_date_columns(df)
        assert "patient_id" not in detected, "Should NOT detect when invalid > 60% with 50% threshold"


# ---------------------------------------------------------------------------
# Test 5: Boundary Date Conversion (AUDIT-018)
# ---------------------------------------------------------------------------


@pytest.mark.dates
@pytest.mark.parametrize(
    "date_string,expected_date,description",
    [
        # PCORnet minimum (masked births)
        ("01JAN1900", date(1900, 1, 1), "PCORnet minimum - masked birth dates"),
        # Leap year
        ("29FEB2020", date(2020, 2, 29), "Leap year Feb 29"),
        # Near MAX_DATE boundary
        ("31DEC2026", date(2026, 12, 31), "Near MAX_DATE boundary"),
        # Beyond MAX_DATE (should still parse, validation is informational)
        ("01JAN2100", date(2100, 1, 1), "Beyond MAX_DATE - should parse but flag"),
    ],
    ids=[
        "1900_masked_birth",
        "leap_year_2020",
        "max_date_boundary",
        "beyond_max_date",
    ],
)
def test_convert_date_column_boundary_dates(date_string, expected_date, description):
    """Test conversion handles boundary dates correctly.

    AUDIT-018: 1900-01-01 births may be masked values (HIPAA de-identification),
    not legitimate birth dates. Patients born on this exact date would be 126
    years old in 2026 (extremely unlikely in HL cohort).

    Validation is informational only - values are converted even if out of range.
    """
    df = pl.DataFrame({"BIRTH_DATE": [date_string]})
    result_df, stats = convert_date_column(df, "BIRTH_DATE", "%d%b%Y")

    assert stats["action"] == "converted", f"Should convert boundary date: {description}"
    assert result_df["BIRTH_DATE"][0] == expected_date, f"Should parse to {expected_date}"


# ---------------------------------------------------------------------------
# Test 6: Parse Failure Threshold
# ---------------------------------------------------------------------------


@pytest.mark.dates
@pytest.mark.parametrize(
    "valid_count,invalid_count,should_convert",
    [
        (90, 10, True),   # 90% valid, 10% invalid → at threshold, should convert
        (89, 11, False),  # 89% valid, 11% invalid → exceeds threshold, keep as string
        (100, 0, True),   # 100% valid → should convert
        (0, 100, False),  # 100% invalid → keep as string
        (95, 5, True),    # 95% valid, 5% invalid → well below threshold
    ],
    ids=[
        "at_threshold_90pct",
        "exceeds_threshold_89pct",
        "all_valid",
        "all_invalid",
        "well_below_threshold",
    ],
)
def test_convert_date_column_invalid_handling(valid_count, invalid_count, should_convert):
    """Test conversion applies 10% parse failure threshold correctly.

    If >10% of non-null, non-empty values fail to parse, column is kept as
    string (safety over convenience). Otherwise converted.
    """
    # Create mix of valid and invalid dates
    valid_dates = ["01JAN2020"] * valid_count
    invalid_dates = ["invalid"] * invalid_count
    all_dates = valid_dates + invalid_dates

    df = pl.DataFrame({"test_date": all_dates})
    result_df, stats = convert_date_column(df, "test_date", "%d%b%Y")

    if should_convert:
        assert stats["action"] == "converted", f"Should convert with {valid_count}/{valid_count+invalid_count} valid"
        # Verify invalid values became null
        assert stats["new_nulls"] == invalid_count, f"Should have {invalid_count} new nulls"
    else:
        assert stats["action"] == "kept_as_string", f"Should keep as string with {valid_count}/{valid_count+invalid_count} valid"
        assert "failures" in stats, "Should report failure count"
        assert stats["failures"] == invalid_count, f"Should report {invalid_count} failures"


# ---------------------------------------------------------------------------
# Test 7: Null Preservation
# ---------------------------------------------------------------------------


@pytest.mark.dates
@pytest.mark.parametrize(
    "values,should_convert,expected_new_nulls",
    [
        # Existing nulls preserved, don't count as parse failures
        (["01JAN2020", None, "15FEB2020", "01MAR2020", "01APR2020"], True, 0),
        # Parse failures: 1/5 = 20% > 10% threshold, kept as string
        (["01JAN2020", "invalid", "15FEB2020", "01MAR2020", "01APR2020"], False, 1),
        # Mix of existing nulls and parse failures: 1/4 = 25% > 10%, kept as string
        (["01JAN2020", None, "invalid", "15FEB2020", "01MAR2020"], False, 1),
        # Empty strings become null but are excluded from denominator, then counted as failures
        # Denominator=4 (excludes empty string), new_nulls=1 (empty string), 1/4=25% > 10%
        (["01JAN2020", "", "15FEB2020", "01MAR2020", "01APR2020"], False, 1),
        # Exactly at 10% threshold: 1/10 = 10%, should convert (> not >=)
        (["01JAN2020", "invalid", "15FEB2020", "01MAR2020", "01APR2020",
          "01MAY2020", "01JUN2020", "01JUL2020", "01AUG2020", "01SEP2020"], True, 1),
    ],
    ids=[
        "existing_nulls_preserved",
        "parse_failure_20pct",
        "mix_nulls_and_failures_25pct",
        "empty_string_creates_failure",
        "exactly_10pct_threshold",
    ],
)
def test_convert_date_column_nulls_preserved(values, should_convert, expected_new_nulls):
    """Test conversion threshold calculation with nulls and empty strings.

    Denominator = non-null, non-empty values before conversion.
    New nulls = parse failures (including empty strings that become null).
    Threshold: new_nulls / denominator > 0.10 → kept as string.

    Note: Empty strings are excluded from denominator but DO create new nulls,
    so they count as failures in the percentage calculation.
    """
    df = pl.DataFrame({"test_date": values})
    result_df, stats = convert_date_column(df, "test_date", "%d%b%Y")

    if should_convert:
        assert stats["action"] == "converted", "Should convert when below threshold"
        assert stats["new_nulls"] == expected_new_nulls, f"Should have exactly {expected_new_nulls} new nulls"
    else:
        assert stats["action"] == "kept_as_string", "Should keep as string when exceeds threshold"
        assert stats["failures"] == expected_new_nulls, f"Should report {expected_new_nulls} failures"


# ---------------------------------------------------------------------------
# Test 8: Date Range Validation
# ---------------------------------------------------------------------------


@pytest.mark.dates
@pytest.mark.parametrize(
    "test_date,within_range,description",
    [
        (date(1900, 1, 1), True, "MIN_DATE boundary"),
        (date(1899, 12, 31), False, "Before MIN_DATE"),
        (date(2026, 12, 31), True, "MAX_DATE boundary"),
        (date(2027, 1, 1), False, "After MAX_DATE"),
        (date(2020, 6, 15), True, "Normal date within range"),
    ],
    ids=[
        "min_date_boundary",
        "before_min_date",
        "max_date_boundary",
        "after_max_date",
        "normal_date",
    ],
)
def test_validate_date_range_plausibility(test_date, within_range, description):
    """Test plausibility bounds (MIN_DATE=1900-01-01, MAX_DATE=2026-12-31).

    validate_date_range is informational only - reports out-of-range values
    but doesn't reject them. Out-of-range may be legitimate (e.g., 1900-01-01
    is PCORnet's masked value) or may indicate conversion errors.
    """
    df = pl.DataFrame({"test_date": [test_date]})
    validation = validate_date_range(df, "test_date")

    assert "col" in validation, "Should return validation dict"
    assert validation["col"] == "test_date"

    if within_range:
        assert validation["out_of_range"] == 0, f"{description} should be within range"
    else:
        assert validation["out_of_range"] == 1, f"{description} should be flagged as out of range"


# ---------------------------------------------------------------------------
# Test 9: Format Fallback Order
# ---------------------------------------------------------------------------


@pytest.mark.dates
@pytest.mark.parametrize(
    "date_string,expected_format,description",
    [
        # DATETIME tested first, should match before DATE9
        ("01JAN2020:14:30:00", "%d%b%Y:%H:%M:%S", "DATETIME matched first"),
        # DATETIME fails, DATE9 matched
        ("01JAN2020", "%d%b%Y", "DATE9 matched after DATETIME fails"),
        # Both DATE9/DATETIME fail, YYYYMMDD matched (requires name match)
        ("20200101", "%Y%m%d", "YYYYMMDD matched after others fail"),
    ],
    ids=[
        "datetime_first",
        "date9_second",
        "yyyymmdd_third",
    ],
)
def test_format_fallback_order(date_string, expected_format, description):
    """Test 3-format fallback order: DATETIME → DATE9 → YYYYMMDD.

    Detection tries formats in priority order. First format with >threshold
    match wins.
    """
    # Use known date column for YYYYMMDD detection
    df = pl.DataFrame({"BIRTH_DATE": [date_string]})
    detected = detect_date_columns(df)

    assert "BIRTH_DATE" in detected, f"Should detect date: {description}"
    assert detected["BIRTH_DATE"] == expected_format, f"Should use {expected_format}: {description}"


# ---------------------------------------------------------------------------
# Test 10: All-Null Column Handling
# ---------------------------------------------------------------------------


@pytest.mark.dates
def test_convert_date_column_all_null():
    """Test conversion skips all-null columns with informative status."""
    df = pl.DataFrame({"test_date": [None, None, None]})
    result_df, stats = convert_date_column(df, "test_date", "%d%b%Y")

    assert stats["action"] == "skipped", "Should skip all-null column"
    assert stats["reason"] == "all null/empty", "Should report reason"
    # DataFrame should be unchanged
    assert result_df["test_date"].null_count() == 3


# ---------------------------------------------------------------------------
# Test 11: Edge Case - Single Valid Date
# ---------------------------------------------------------------------------


@pytest.mark.dates
def test_convert_date_column_single_valid_date():
    """Test conversion works with just one valid date value."""
    df = pl.DataFrame({"test_date": ["01JAN2020"]})
    result_df, stats = convert_date_column(df, "test_date", "%d%b%Y")

    assert stats["action"] == "converted", "Should convert single valid date"
    assert result_df["test_date"][0] == date(2020, 1, 1)
    assert stats["new_nulls"] == 0


# ---------------------------------------------------------------------------
# Test 12: DATETIME Format Conversion
# ---------------------------------------------------------------------------


@pytest.mark.dates
def test_convert_date_column_datetime_format():
    """Test DATETIME format converts to datetime dtype (not just date)."""
    df = pl.DataFrame({"test_datetime": ["01JAN2020:14:30:00", "15FEB2020:09:15:30"]})
    result_df, stats = convert_date_column(df, "test_datetime", "%d%b%Y:%H:%M:%S")

    assert stats["action"] == "converted", "Should convert DATETIME format"
    assert result_df["test_datetime"].dtype in [pl.Datetime, pl.Datetime("us"), pl.Datetime("ns"), pl.Datetime("ms")], \
        "Should be datetime dtype, not date"
