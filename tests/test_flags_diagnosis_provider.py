"""Unit tests for flags_diagnosis_provider: FLAG_HL_DX, FLAG_SURVIVORSHIP_DX, FLAG_CANCER_PROVIDER."""

import polars as pl

from src.clean.flags_diagnosis_provider import add_diagnosis_flags, add_provider_flags
from src.validate.cohort import ICD9_HL_CODES, ICD10_HL_CODES


def test_flag_hl_dx_matches_cohort_codes() -> None:
    """Cohort HL codes (from ICD9/ICD10_HL_CODES) all yield FLAG_HL_DX=1."""
    icd9_sample = list(ICD9_HL_CODES)[:3]
    icd10_sample = list(ICD10_HL_CODES)[:3]
    df = pl.DataFrame(
        {
            "ID": ["P"] * 6,
            "DX": icd9_sample + icd10_sample,
            "DX_TYPE": ["09"] * 3 + ["10"] * 3,
            "DX_DATE": [None] * 6,
        }
    )
    result = add_diagnosis_flags(df)
    assert result["FLAG_HL_DX"].sum() == 6


def test_flag_hl_dx_excluded_codes_not_flagged() -> None:
    """Excluded codes (201.3x, C81.5x, C81.6x) yield FLAG_HL_DX=0."""
    df = pl.DataFrame(
        {
            "ID": ["P", "P", "P", "P"],
            "DX": ["201.30", "201.35", "C81.50", "C81.60"],
            "DX_TYPE": ["09", "09", "10", "10"],
            "DX_DATE": [None, None, None, None],
        }
    )
    result = add_diagnosis_flags(df)
    assert result["FLAG_HL_DX"].sum() == 0


def test_add_diagnosis_flags_hl() -> None:
    """FLAG_HL_DX = 1 for cohort HL codes (201.00, C81.10), 0 for non-HL (Z85.3)."""
    df = pl.DataFrame(
        {
            "ID": ["P1", "P2", "P3"],
            "DX": ["201.00", "C81.10", "Z85.3"],
            "DX_TYPE": ["09", "10", "10"],
            "DX_DATE": [None, None, None],
        }
    )
    result = add_diagnosis_flags(df)
    assert "FLAG_HL_DX" in result.columns
    assert result["FLAG_HL_DX"].to_list() == [1, 1, 0]


def test_add_diagnosis_flags_survivorship() -> None:
    """FLAG_SURVIVORSHIP_DX = 1 for survivorship codes (exact and prefix)."""
    df = pl.DataFrame(
        {
            "ID": ["P1", "P2", "P3", "P4"],
            "DX": ["V87.41", "V15.3", "Z08.0", "Z85.3"],
            "DX_TYPE": ["10", "09", "10", "10"],
            "DX_DATE": [None, None, None, None],
        }
    )
    result = add_diagnosis_flags(df)
    assert "FLAG_SURVIVORSHIP_DX" in result.columns
    assert result["FLAG_SURVIVORSHIP_DX"].to_list() == [1, 1, 1, 1]


def test_add_diagnosis_flags_dx_type_variants() -> None:
    """DX_TYPE 'ICD-9-CM' and 'ICD-10-CM' produce same results as '09' and '10'."""
    df = pl.DataFrame(
        {
            "ID": ["P1", "P2"],
            "DX": ["201.00", "C81.10"],
            "DX_TYPE": ["ICD-9-CM", "ICD-10-CM"],
            "DX_DATE": [None, None],
        }
    )
    result = add_diagnosis_flags(df)
    assert result["FLAG_HL_DX"].to_list() == [1, 1]


def test_add_provider_flags() -> None:
    """FLAG_CANCER_PROVIDER = 1 for oncology specialties."""
    df = pl.DataFrame(
        {
            "PROVIDERID": ["PR1", "PR2", "PR3"],
            "PROVIDER_SPECIALTY_PRIMARY": ["Medical Oncology", "Cardiology", "Hematology-Oncology"],
        }
    )
    result = add_provider_flags(df)
    assert "FLAG_CANCER_PROVIDER" in result.columns
    assert result["FLAG_CANCER_PROVIDER"].to_list() == [1, 0, 1]


def test_add_provider_flags_null() -> None:
    """PROVIDER_SPECIALTY_PRIMARY null → FLAG_CANCER_PROVIDER = 0."""
    df = pl.DataFrame(
        {
            "PROVIDERID": ["PR1"],
            "PROVIDER_SPECIALTY_PRIMARY": [None],
        }
    )
    result = add_provider_flags(df)
    assert result["FLAG_CANCER_PROVIDER"].to_list() == [0]
