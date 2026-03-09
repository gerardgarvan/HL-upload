"""Integration test for add_modality_flags."""

from pathlib import Path

import pandas as pd
import polars as pl

from src.clean.outcomes_flags import add_modality_flags


def test_add_modality_flags_integration(tmp_path: Path) -> None:
    """add_modality_flags sets MODALITY_SCT=1 when patient has matching PX code."""
    # Outcomes.csv with SCT code 38205 (CPT)
    outcomes_path = tmp_path / "outcomes.csv"
    pd.DataFrame(
        {
            "Modality": ["Stem cell transplant"],
            "Code system": ["CPT"],
            "Code": ["38205"],
            "Description": ["SCT procedure"],
        }
    ).to_csv(outcomes_path, index=False)

    # Patient-level
    patient_df = pl.DataFrame({"ID": ["P1", "P2"]})

    # PROCEDURES: P1 has PX 38205
    proc_path = tmp_path / "PROCEDURES.parquet"
    pl.DataFrame(
        {
            "ID": ["P1"],
            "PX": ["38205"],
            "PX_DATE": [None],
        }
    ).write_parquet(proc_path)

    # LAB_RESULT_CM and DIAGNOSIS minimal (no SCT-matching codes)
    lab_path = tmp_path / "LAB_RESULT_CM.parquet"
    pl.DataFrame({"ID": ["P2"], "LAB_LOINC": ["xxx"]}).write_parquet(lab_path)
    diag_path = tmp_path / "DIAGNOSIS.parquet"
    pl.DataFrame({"ID": ["P2"], "DX": ["Z99"]}).write_parquet(diag_path)

    table_map = {
        "PROCEDURES": proc_path,
        "LAB_RESULT_CM": lab_path,
        "DIAGNOSIS": diag_path,
    }

    result = add_modality_flags(patient_df, table_map, outcomes_path)
    assert "MODALITY_SCT" in result.columns
    p1_row = result.filter(pl.col("ID") == "P1").row(0, named=True)
    p2_row = result.filter(pl.col("ID") == "P2").row(0, named=True)
    assert p1_row["MODALITY_SCT"] == 1
    assert p2_row["MODALITY_SCT"] == 0
