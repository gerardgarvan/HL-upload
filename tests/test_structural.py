"""Tests for validate_table_schema and check_patid_integrity."""

from pathlib import Path

import polars as pl
import pytest

from src.validate.structural import (
    check_patid_integrity,
    validate_table_schema,
)


def test_validate_table_schema_ok(tmp_path: Path) -> None:
    """Schema matches expected columns."""
    parquet_path = tmp_path / "demo.parquet"
    df = pl.DataFrame({"ID": ["A", "B"], "BIRTH_DATE": [None, None]})
    df.write_parquet(parquet_path)

    result = validate_table_schema(
        parquet_path,
        expected_cols=["ID", "BIRTH_DATE"],
        table_name="DEMOGRAPHIC",
    )
    assert result["status"] == "ok"
    assert result["matched"] == 2


def test_validate_table_schema_missing_col(tmp_path: Path) -> None:
    """Schema missing expected column → status warn."""
    parquet_path = tmp_path / "demo.parquet"
    df = pl.DataFrame({"ID": ["A"]})  # no BIRTH_DATE
    df.write_parquet(parquet_path)

    result = validate_table_schema(
        parquet_path,
        expected_cols=["ID", "BIRTH_DATE"],
        table_name="DEMOGRAPHIC",
    )
    assert result["status"] == "warn"
    assert result["missing"]
    assert "BIRTH_DATE" in str(result["missing"]).upper()


def test_check_patid_integrity_orphans(tmp_path: Path) -> None:
    """Child has IDs not in demographic → orphan_ids > 0."""
    demo_path = tmp_path / "demographic.parquet"
    child_path = tmp_path / "child.parquet"
    pl.DataFrame({"ID": ["A"]}).write_parquet(demo_path)
    pl.DataFrame({"ID": ["A", "B"]}).write_parquet(child_path)

    result = check_patid_integrity(
        child_path,
        demo_path,
        child_table="PROCEDURES",
    )
    assert result["orphan_ids"] == 1
    assert result["unique_ids"] == 2
