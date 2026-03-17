"""Tests for verify_hl_cohort."""

from datetime import date
from pathlib import Path

import polars as pl

from src.validate.cohort import verify_hl_cohort


def test_verify_hl_cohort_minimal(tmp_path: Path) -> None:
    """verify_hl_cohort returns dict with expected keys."""
    diag_path = tmp_path / "diagnosis.parquet"
    enc_path = tmp_path / "encounter.parquet"

    # Minimal HL diagnosis: C81.00, 201.00 with DX_DATE (date type) and SOURCE
    pl.DataFrame(
        {
            "ID": ["P1", "P1", "P2"],
            "DX": ["C81.00", "C81.01", "201.00"],
            "DX_DATE": [date(2020, 1, 1), date(2020, 1, 15), date(2020, 2, 1)],
            "DX_TYPE": ["10", "10", "09"],
            "SOURCE": ["UFH", "UFH", "UFH"],
        }
    ).write_parquet(diag_path)

    # Encounters for Method B
    pl.DataFrame(
        {
            "ENCOUNTERID": ["E1", "E2", "E3"],
            "ID": ["P1", "P1", "P2"],
            "ADMIT_DATE": [date(2020, 1, 1), date(2020, 1, 15), date(2020, 2, 1)],
        }
    ).write_parquet(enc_path)

    result = verify_hl_cohort(diag_path, enc_path)
    assert "total_hl_records" in result
    assert "unique_patients" in result
    assert "method_a_count" in result
    assert "method_b_count" in result
    assert result["total_hl_records"] >= 0
    assert result["unique_patients"] >= 0
