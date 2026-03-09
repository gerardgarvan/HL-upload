"""Unit tests for load_outcomes_code_lookup (Outcomes.csv parsing)."""

from pathlib import Path

import pandas as pd

from src.clean.outcomes_flags import load_outcomes_code_lookup


def test_load_outcomes_code_lookup_mock(tmp_path: Path) -> None:
    """Test with minimal mock CSV (no dependency on project Outcomes.csv)."""
    csv_path = tmp_path / "outcomes_mock.csv"
    df = pd.DataFrame(
        {
            "Modality": ["Stem cell transplant", None],
            "Code system": ["CPT", "LOINC"],
            "Code": ["38205", "38206-3"],
            "Description": ["desc1", "desc2"],
        }
    )
    df.to_csv(csv_path, index=False)

    result = load_outcomes_code_lookup(csv_path)
    assert "SCT" in result
    sct = result["SCT"]
    assert "38205" in sct["cpt_hcpcs"]
    assert "38206-3" in sct["loinc"]
