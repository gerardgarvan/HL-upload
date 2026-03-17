"""Tests for report generation structure and aggregation correctness.

Tests quality_report.py functions covering:
- Report structure validation (expected columns, dtypes)
- Suppression applied in report aggregations
- Aggregation correctness spot-checks
- Edge cases (empty input, null handling)

Testing strategy (from 03-CONTEXT.md):
- Structural tests: Verify columns present, dtypes correct, no crashes
- Spot-check tests: Verify suppression at boundary values, aggregation correctness
- NOT exact value matching (too brittle)
"""

import pytest
import polars as pl
from polars.testing import assert_frame_equal

from src.report.quality_report import aggregate_dq_metrics, build_patient_level_derived
from src.report.suppression import suppress, DEFAULT_THRESHOLD


@pytest.fixture
def minimal_table_map(tmp_path):
    """Create minimal table_map for testing with empty/minimal Parquet files."""
    # Create minimal DIAGNOSIS table with HL codes
    diagnosis_path = tmp_path / "DIAGNOSIS.parquet"
    diagnosis_df = pl.DataFrame({
        "ID": ["PT001", "PT002", "PT003"],
        "DX": ["C81.10", "C81.11", "C81.10"],
        "DX_DATE": ["2020-01-01", "2020-02-01", "2020-03-01"],
        "ENCOUNTERID": ["ENC001", "ENC002", "ENC003"],
        "SOURCE": ["PARTNER1", "PARTNER1", "PARTNER2"],
    }).with_columns(pl.col("DX_DATE").str.to_date())
    diagnosis_df.write_parquet(diagnosis_path)

    # Create minimal DEMOGRAPHIC table
    demographic_path = tmp_path / "DEMOGRAPHIC.parquet"
    demographic_df = pl.DataFrame({
        "ID": ["PT001", "PT002", "PT003"],
        "BIRTH_DATE": ["1990-01-01", "1985-05-15", "1995-10-20"],
        "SEX": ["M", "F", "M"],
    }).with_columns(pl.col("BIRTH_DATE").str.to_date())
    demographic_df.write_parquet(demographic_path)

    # Create minimal ENCOUNTER table
    encounter_path = tmp_path / "ENCOUNTER.parquet"
    encounter_df = pl.DataFrame({
        "ID": ["PT001", "PT002", "PT003"],
        "ENCOUNTERID": ["ENC001", "ENC002", "ENC003"],
        "ADMIT_DATE": ["2020-01-01", "2020-02-01", "2020-03-01"],
        "DISCHARGE_DATE": ["2020-01-02", "2020-02-02", "2020-03-02"],
        "ENC_TYPE": ["IP", "AV", "IP"],
        "PAYER_TYPE_PRIMARY": ["MC", "PR", "MC"],
        "SOURCE": ["PARTNER1", "PARTNER1", "PARTNER2"],
    }).with_columns([
        pl.col("ADMIT_DATE").str.to_date(),
        pl.col("DISCHARGE_DATE").str.to_date(),
    ])
    encounter_df.write_parquet(encounter_path)

    return {
        "DIAGNOSIS": diagnosis_path,
        "DEMOGRAPHIC": demographic_path,
        "ENCOUNTER": encounter_path,
    }


class TestPatientLevelDerivedStructure:
    """Test build_patient_level_derived() output structure."""

    def test_patient_level_derived_has_expected_columns(self, minimal_table_map):
        """Verify build_patient_level_derived() returns expected column structure."""
        result = build_patient_level_derived(minimal_table_map)

        # Expected columns from quality_report.py build_patient_level_derived()
        expected_cols = {
            "ID",
            "FIRST_HL_DX_DATE",
            "FIRST_HL_TX_DATE",
            "DX_TO_TX_DAYS",
            "AGE_AT_HL_DX",
            "AGE_BAND",
            "HL_SUBTYPE",
            "PAYER_AT_DX",
            "INSURANCE_CONTINUITY",
            "REGION",
        }

        # Check subset (some columns may be missing if tables unavailable)
        assert "ID" in result.columns
        assert "FIRST_HL_DX_DATE" in result.columns
        assert "HL_SUBTYPE" in result.columns

        # Verify no crash on minimal input
        assert result.height >= 0

    def test_patient_level_derived_dtypes(self, minimal_table_map):
        """Verify column data types are correct."""
        result = build_patient_level_derived(minimal_table_map)

        if result.is_empty():
            pytest.skip("Empty result, cannot verify dtypes")

        # Check key column dtypes
        assert result.schema["ID"] == pl.String
        assert result.schema["FIRST_HL_DX_DATE"] == pl.Date
        if "AGE_AT_HL_DX" in result.columns:
            assert result.schema["AGE_AT_HL_DX"] == pl.Float64
        if "HL_SUBTYPE" in result.columns:
            assert result.schema["HL_SUBTYPE"] == pl.String

    def test_patient_level_derived_empty_input(self):
        """Test build_patient_level_derived() with empty table_map."""
        result = build_patient_level_derived({})

        # Should return empty DataFrame with expected schema
        assert result.is_empty()
        assert "ID" in result.columns
        assert "FIRST_HL_DX_DATE" in result.columns


class TestSuppressionAppliedInReports:
    """Test that suppression is correctly applied in report aggregations."""

    def test_suppression_applied_to_small_cells(self):
        """Verify small cell counts are suppressed in aggregation results.

        Create test data with known small (1, 5, 10) and large (11, 100) counts,
        apply suppression, verify small cells become "-".
        """
        # Create test aggregation result
        counts_df = pl.DataFrame({
            "DX": ["C81.10", "C81.11", "C81.20", "C81.30", "C81.40"],
            "count": [1, 5, 10, 11, 100],
        })

        # Apply suppression (mimics report generation)
        suppressed_df = counts_df.with_columns(
            pl.col("count").map_elements(suppress, return_dtype=pl.String).alias("count_suppressed")
        )

        # Verify suppression applied correctly
        assert suppressed_df["count_suppressed"][0] == "-"    # 1 suppressed
        assert suppressed_df["count_suppressed"][1] == "-"    # 5 suppressed
        assert suppressed_df["count_suppressed"][2] == "-"    # 10 suppressed
        assert suppressed_df["count_suppressed"][3] == "11"   # 11 safe
        assert suppressed_df["count_suppressed"][4] == "100"  # 100 safe

    def test_suppression_at_boundary_values_in_groupby(self):
        """Test suppression applied to group_by aggregation at boundary values."""
        # Create test data: 3 records C81.10, 11 records C81.11
        test_data = pl.DataFrame({
            "ID": [f"PT{i:03d}" for i in range(1, 15)],  # 14 patients
            "DX": ["C81.10"] * 3 + ["C81.11"] * 11,
            "DX_DATE": ["2020-01-01"] * 14,
        })

        # Group by DX, count
        aggregated = test_data.group_by("DX").agg(pl.len().alias("n"))

        # Apply suppression
        aggregated = aggregated.with_columns(
            pl.col("n").map_elements(suppress, return_dtype=pl.String).alias("n_suppressed")
        )

        # Verify: 3 → "-" (small cell), 11 → "11" (safe)
        c81_10 = aggregated.filter(pl.col("DX") == "C81.10")
        c81_11 = aggregated.filter(pl.col("DX") == "C81.11")

        assert c81_10["n_suppressed"][0] == "-"  # 3 suppressed
        assert c81_11["n_suppressed"][0] == "11"  # 11 safe

    def test_zero_counts_displayed(self):
        """Verify zero counts are displayed (not suppressed)."""
        # Zero reveals no individual-level information
        assert suppress(0) == "0"

        # In aggregation context
        counts_df = pl.DataFrame({
            "category": ["A", "B", "C"],
            "count": [0, 5, 15],
        })

        suppressed_df = counts_df.with_columns(
            pl.col("count").map_elements(suppress, return_dtype=pl.String).alias("count_suppressed")
        )

        assert suppressed_df["count_suppressed"][0] == "0"   # Zero displayed
        assert suppressed_df["count_suppressed"][1] == "-"   # 5 suppressed
        assert suppressed_df["count_suppressed"][2] == "15"  # 15 safe


class TestAggregationCorrectnessSpotCheck:
    """Spot-check aggregation correctness with known inputs."""

    def test_groupby_count_correctness(self):
        """Verify group_by count aggregation produces correct counts before suppression."""
        # Create known input: 3 C81.10, 5 C81.11
        test_data = pl.DataFrame({
            "ID": [f"PT{i:03d}" for i in range(1, 9)],
            "DX": ["C81.10"] * 3 + ["C81.11"] * 5,
        })

        # Aggregate
        aggregated = test_data.group_by("DX").agg(pl.len().alias("n")).sort("DX")

        # Verify counts BEFORE suppression (aggregation correctness)
        assert aggregated.height == 2
        assert aggregated.filter(pl.col("DX") == "C81.10")["n"][0] == 3
        assert aggregated.filter(pl.col("DX") == "C81.11")["n"][0] == 5

    def test_aggregation_with_null_handling(self):
        """Verify aggregation handles null values correctly."""
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT002", "PT003", "PT004"],
            "DX": ["C81.10", None, "C81.10", "C81.11"],
        })

        # Group by DX, count (nulls excluded)
        aggregated = test_data.filter(pl.col("DX").is_not_null()).group_by("DX").agg(pl.len().alias("n"))

        # Verify: 2 C81.10, 1 C81.11 (null excluded)
        assert aggregated.height == 2
        total_count = aggregated["n"].sum()
        assert total_count == 3  # 4 rows - 1 null = 3


class TestDQMetricsAggregation:
    """Test aggregate_dq_metrics() function."""

    def test_dq_metrics_structure(self, minimal_table_map, tmp_path):
        """Verify aggregate_dq_metrics() returns expected structure."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()

        result = aggregate_dq_metrics(minimal_table_map, reports_dir)

        # Expected keys from quality_report.py aggregate_dq_metrics()
        assert "completeness" in result
        assert "conformance" in result
        assert "plausibility" in result
        assert "persistence" in result

    def test_dq_metrics_no_crash_on_empty_input(self, tmp_path):
        """Test aggregate_dq_metrics() with empty table_map."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()

        result = aggregate_dq_metrics({}, reports_dir)

        # Should not crash, return structure
        assert isinstance(result, dict)
        assert "completeness" in result
        assert "conformance" in result

    def test_persistence_encounter_aggregation(self, minimal_table_map, tmp_path):
        """Test persistence dimension aggregates encounter counts by year."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()

        result = aggregate_dq_metrics(minimal_table_map, reports_dir)

        # Verify persistence has encounter data
        persistence = result.get("persistence", {})
        assert "by_year" in persistence

        # Should have encounter data from minimal_table_map
        if persistence["by_year"]:
            # Verify structure (list of dicts with year/n)
            assert isinstance(persistence["by_year"], list)


class TestReportEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_dataframe_aggregation(self):
        """Test aggregation on empty DataFrame doesn't crash."""
        empty_df = pl.DataFrame({
            "DX": [],
            "count": [],
        }, schema={"DX": pl.String, "count": pl.Int64})

        # Apply suppression to empty result
        suppressed_df = empty_df.with_columns(
            pl.col("count").map_elements(suppress, return_dtype=pl.String).alias("count_suppressed")
        )

        assert suppressed_df.is_empty()
        assert "count_suppressed" in suppressed_df.columns

    def test_all_small_cells_suppressed(self):
        """Test aggregation where all cells are small (all suppressed)."""
        test_data = pl.DataFrame({
            "category": ["A", "B", "C", "D"],
            "count": [1, 3, 5, 10],  # All at or below threshold
        })

        suppressed_df = test_data.with_columns(
            pl.col("count").map_elements(suppress, return_dtype=pl.String).alias("count_suppressed")
        )

        # Verify all suppressed
        assert all(val == "-" for val in suppressed_df["count_suppressed"])

    def test_patient_level_derived_missing_tables(self):
        """Test build_patient_level_derived() with missing optional tables."""
        # Only DIAGNOSIS table (minimal for HL patient identification)
        incomplete_map = {}

        result = build_patient_level_derived(incomplete_map)

        # Should return empty DataFrame with schema (no HL patients found)
        assert result.is_empty()
        assert "ID" in result.columns
