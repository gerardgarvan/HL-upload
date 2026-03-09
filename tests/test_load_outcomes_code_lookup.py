"""Unit tests for load_outcomes_code_lookup (Outcomes.xlsx parsing)."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.clean.outcomes_flags import load_outcomes_code_lookup


def test_load_outcomes_code_lookup_mock(tmp_path: Path) -> None:
    """Test with minimal mock Excel (no dependency on project Outcomes.xlsx)."""
    excel_path = tmp_path / "outcomes_mock.xlsx"
    df = pd.DataFrame({
        "Modality": ["Stem cell transplant", None],
        "Code system": ["CPT", "LOINC"],
        "Code": ["38205", "38206-3"],
        "Description": ["desc1", "desc2"],
    })
    df.to_excel(excel_path, sheet_name="Outcomes", index=False)

    result = load_outcomes_code_lookup(excel_path)
    assert "SCT" in result
    sct = result["SCT"]
    assert "38205" in sct["cpt_hcpcs"]
    assert "38206-3" in sct["loinc"]
