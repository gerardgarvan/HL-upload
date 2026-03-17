"""Tests for partner flag assignment logic.

Tests cover partner provenance flags (ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY)
based on SOURCE column values. Resolves AUDIT-013 by documenting and testing
hardcoded partner abbreviations.
"""

import pytest
import polars as pl
from polars.testing import assert_frame_equal
from src.clean.harmonize import add_partner_flags, PARTNER_FLAGS


def test_add_partner_flags_ams():
    """Partner flags correctly assigned for known abbreviations.

    Tests that AMS and UMI get ICD_MAPPED=1, FLM gets CLAIMS_ONLY=1.
    AUDIT-013: Documents partner abbreviations used in PARTNER_FLAGS constant.
    """
    df = pl.DataFrame({
        "ID": ["PT001", "PT002", "PT003"],
        "SOURCE": ["AMS", "FLM", "UMI"]
    })

    result = add_partner_flags(df, partner_col="SOURCE")

    expected = pl.DataFrame({
        "ID": ["PT001", "PT002", "PT003"],
        "SOURCE": ["AMS", "FLM", "UMI"],
        "ICD_MAPPED": pl.Series([1, 0, 1], dtype=pl.Int8),  # AMS and UMI have ICD_MAPPED
        "CLAIMS_ONLY": pl.Series([0, 1, 0], dtype=pl.Int8),  # FLM has CLAIMS_ONLY
        "DEATH_ONLY": pl.Series([0, 0, 0], dtype=pl.Int8)   # None are DEATH_ONLY
    })

    assert_frame_equal(result, expected, check_dtypes=True, check_column_order=False)


def test_add_partner_flags_vrt():
    """DEATH_ONLY flag assigned correctly for VRT partner."""
    df = pl.DataFrame({
        "ID": ["PT001", "PT002"],
        "SOURCE": ["VRT", "AMS"]
    })

    result = add_partner_flags(df, partner_col="SOURCE")

    assert result.filter(pl.col("SOURCE") == "VRT")["DEATH_ONLY"][0] == 1
    assert result.filter(pl.col("SOURCE") == "AMS")["DEATH_ONLY"][0] == 0
    assert result.filter(pl.col("SOURCE") == "AMS")["ICD_MAPPED"][0] == 1


def test_add_partner_flags_unrecognized_source():
    """Unrecognized SOURCE values get all flags set to 0.

    AUDIT-013: Verify partner abbreviations (AMS, UMI, FLM, VRT) match current
    data sources. Unrecognized SOURCE values get no flags set - this test
    documents that behavior.

    TODO: Add data validation step to detect and warn about unrecognized SOURCE
    values in production data.
    """
    df = pl.DataFrame({
        "ID": ["PT001", "PT002"],
        "SOURCE": ["AMC", "XYZ"]  # Unrecognized abbreviations
    })

    result = add_partner_flags(df, partner_col="SOURCE")

    # All flags should be 0 for unrecognized sources
    assert result["ICD_MAPPED"].sum() == 0
    assert result["CLAIMS_ONLY"].sum() == 0
    assert result["DEATH_ONLY"].sum() == 0


def test_add_partner_flags_missing_source_column():
    """If SOURCE column absent, return DataFrame unchanged."""
    df = pl.DataFrame({
        "ID": ["PT001", "PT002"],
        "DX": ["C81.10", "C81.11"]
    })

    result = add_partner_flags(df, partner_col="SOURCE")

    # DataFrame should be unchanged (no flag columns added)
    assert result.columns == ["ID", "DX"]
    assert_frame_equal(result, df)


def test_add_partner_flags_custom_column_name():
    """Partner flags work with custom column name (not 'SOURCE')."""
    df = pl.DataFrame({
        "ID": ["PT001", "PT002"],
        "PARTNER": ["AMS", "FLM"]
    })

    result = add_partner_flags(df, partner_col="PARTNER")

    assert result.filter(pl.col("PARTNER") == "AMS")["ICD_MAPPED"][0] == 1
    assert result.filter(pl.col("PARTNER") == "FLM")["CLAIMS_ONLY"][0] == 1


def test_partner_flags_constants():
    """PARTNER_FLAGS constant has expected structure.

    AUDIT-013: Partner abbreviations hardcoded - validate against actual SOURCE
    column values in production data.

    Expected partners:
    - ICD_MAPPED: AMS, UMI (retrospective coding)
    - CLAIMS_ONLY: FLM (claims data without clinical detail)
    - DEATH_ONLY: VRT (death registry)
    """
    assert "ICD_MAPPED" in PARTNER_FLAGS
    assert "CLAIMS_ONLY" in PARTNER_FLAGS
    assert "DEATH_ONLY" in PARTNER_FLAGS

    assert PARTNER_FLAGS["ICD_MAPPED"] == {"AMS", "UMI"}
    assert PARTNER_FLAGS["CLAIMS_ONLY"] == {"FLM"}
    assert PARTNER_FLAGS["DEATH_ONLY"] == {"VRT"}


def test_add_partner_flags_multiple_rows_same_source():
    """Multiple rows with same SOURCE get same flags."""
    df = pl.DataFrame({
        "ID": ["PT001", "PT002", "PT003"],
        "SOURCE": ["AMS", "AMS", "FLM"]
    })

    result = add_partner_flags(df, partner_col="SOURCE")

    # Both AMS rows should have ICD_MAPPED=1
    ams_rows = result.filter(pl.col("SOURCE") == "AMS")
    assert ams_rows["ICD_MAPPED"].to_list() == [1, 1]
    assert ams_rows["CLAIMS_ONLY"].to_list() == [0, 0]

    # FLM row should have CLAIMS_ONLY=1
    flm_rows = result.filter(pl.col("SOURCE") == "FLM")
    assert flm_rows["CLAIMS_ONLY"][0] == 1
