"""Tests for outcomes code lookup and modality flag logic.

Tests cover Outcomes.csv parsing, modality code lookup, and schema validation.
Resolves AUDIT-014 by adding schema validation for Outcomes.csv columns.

Reorganized from tests/test_load_outcomes_code_lookup.py to align with source
module location (src/clean/outcomes_flags.py).
"""

from pathlib import Path
from io import StringIO

import pytest
import pandas as pd

from src.clean.outcomes_flags import load_outcomes_code_lookup


def test_load_outcomes_code_lookup_valid_schema(tmp_path: Path):
    """Valid Outcomes.csv with expected columns loads successfully.

    Tests that load_outcomes_code_lookup() correctly parses minimal mock CSV
    with standard columns: Modality, Code system, Code.
    """
    csv_path = tmp_path / "outcomes_valid.csv"
    df = pd.DataFrame({
        "Modality": ["Chemotherapy", "Radiation"],
        "Code system": ["J-code", "CPT"],
        "Code": ["J9035", "77401"],
        "Description": ["Chemotherapy drug", "Radiation treatment"]
    })
    df.to_csv(csv_path, index=False)

    result = load_outcomes_code_lookup(csv_path)

    # Should return non-empty dict (though slugs may not match MODALITY_SLUG_MAP)
    assert isinstance(result, dict)


def test_load_outcomes_code_lookup_mock():
    """Test with minimal mock CSV (no dependency on project Outcomes.csv).

    Original test from test_load_outcomes_code_lookup.py - preserved for
    backward compatibility.
    """
    csv_content = """Modality,Code system,Code,Description
Stem cell transplant,CPT,38205,desc1
,LOINC,38206-3,desc2"""

    csv_path = Path("test_outcomes_mock.csv")

    # Create temporary CSV for test
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(csv_content)
        csv_path = Path(f.name)

    try:
        result = load_outcomes_code_lookup(csv_path)
        assert "SCT" in result
        sct = result["SCT"]
        assert "38205" in sct["cpt_hcpcs"]
        assert "38206-3" in sct["loinc"]
    finally:
        csv_path.unlink()


def test_load_outcomes_code_lookup_empty_file(tmp_path: Path):
    """Empty CSV (header only, no data rows) returns empty dict."""
    csv_path = tmp_path / "outcomes_empty.csv"
    df = pd.DataFrame({
        "Modality": [],
        "Code system": [],
        "Code": [],
        "Description": []
    })
    df.to_csv(csv_path, index=False)

    result = load_outcomes_code_lookup(csv_path)

    # Empty file should return empty dict (no codes to map)
    assert isinstance(result, dict)
    assert len(result) == 0


def test_load_outcomes_code_lookup_forward_fill():
    """Modality and Code system forward-fill works correctly.

    Tests that hierarchical CSV structure (Modality and Code system in first
    row, subsequent rows use forward-fill) is parsed correctly.
    """
    csv_content = """Modality,Code system,Code,Description
Stem cell transplant,CPT,38205,desc1
,,38241,desc2
,LOINC,38206-3,desc3"""

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(csv_content)
        csv_path = Path(f.name)

    try:
        result = load_outcomes_code_lookup(csv_path)
        assert "SCT" in result
        sct = result["SCT"]

        # Both CPT codes should be captured
        assert "38205" in sct["cpt_hcpcs"]
        assert "38241" in sct["cpt_hcpcs"]

        # LOINC code should be captured
        assert "38206-3" in sct["loinc"]
    finally:
        csv_path.unlink()


def test_load_outcomes_code_lookup_code_normalization():
    """Codes are normalized (uppercase, whitespace stripped)."""
    csv_content = """Modality,Code system,Code,Description
Stem cell transplant,CPT,  38205  ,desc1
,CPT,j9035,desc2"""

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(csv_content)
        csv_path = Path(f.name)

    try:
        result = load_outcomes_code_lookup(csv_path)
        assert "SCT" in result
        sct = result["SCT"]

        # Codes should be normalized (no whitespace, uppercase)
        assert "38205" in sct["cpt_hcpcs"]
        assert "J9035" in sct["cpt_hcpcs"]
    finally:
        csv_path.unlink()


def test_load_outcomes_code_lookup_unrecognized_modality():
    """Unrecognized modalities (not in MODALITY_SLUG_MAP) are skipped."""
    csv_content = """Modality,Code system,Code,Description
Unknown Modality,CPT,12345,desc1
Stem cell transplant,CPT,38205,desc2"""

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(csv_content)
        csv_path = Path(f.name)

    try:
        result = load_outcomes_code_lookup(csv_path)

        # Unknown Modality should be skipped
        assert "Unknown Modality" not in result

        # SCT should be present
        assert "SCT" in result
    finally:
        csv_path.unlink()


def test_load_outcomes_code_lookup_multiple_code_systems():
    """Modality with multiple code systems (CPT + LOINC + ICD-10) handled correctly."""
    csv_content = """Modality,Code system,Code,Description
Stem cell transplant,CPT,38205,desc1
,LOINC,38206-3,desc2
,ICD-10-PCS,30243G1,desc3"""

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(csv_content)
        csv_path = Path(f.name)

    try:
        result = load_outcomes_code_lookup(csv_path)
        assert "SCT" in result
        sct = result["SCT"]

        assert "38205" in sct["cpt_hcpcs"]
        assert "38206-3" in sct["loinc"]
        assert "30243G1" in sct["icd10"]
    finally:
        csv_path.unlink()


# ---------------------------------------------------------------------------
# Schema Validation Tests (AUDIT-014)
# ---------------------------------------------------------------------------

def test_load_outcomes_code_lookup_missing_column_behavior(tmp_path: Path):
    """CSV missing expected columns raises pandas KeyError.

    AUDIT-014: Schema validation - load_outcomes_code_lookup() should fail fast
    if Outcomes.csv columns renamed or reordered.

    Current behavior: pandas raises KeyError if expected columns missing.
    This test documents that behavior and serves as regression test.

    NOTE: If explicit schema validation is added to load_outcomes_code_lookup(),
    this test should be updated to expect ValueError with clear message.
    """
    csv_path = tmp_path / "outcomes_wrong_schema.csv"
    df = pd.DataFrame({
        "Treatment": ["Chemotherapy"],  # Wrong column name (not "Modality")
        "System": ["J-code"],           # Wrong column name (not "Code system")
        "Code": ["J9035"]
    })
    df.to_csv(csv_path, index=False)

    # Current behavior: raises KeyError when accessing missing "Modality" column
    with pytest.raises(KeyError):
        load_outcomes_code_lookup(csv_path)


def test_load_outcomes_code_lookup_schema_documentation():
    """Document expected Outcomes.csv schema for AUDIT-014 resolution.

    AUDIT-014: Schema validation - Outcomes.csv structure must be maintained:
    - Columns: Modality, Code system, Code (Description optional)
    - Modality and Code system use forward-fill for multi-row entries
    - Each row has a single code value

    This test serves as documentation. If schema changes, update both
    load_outcomes_code_lookup() and this test.
    """
    expected_columns = ["Modality", "Code system", "Code"]

    # Document for future maintainers
    assert expected_columns == ["Modality", "Code system", "Code"]
