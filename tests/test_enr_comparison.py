"""Tests for Phase 8 enrollment coverage comparison logic.

Tests enrollment union coverage algorithm, comparison table structure, and
Unknown post-treatment payer encounter breakdown.
"""

import pytest
import polars as pl
from datetime import date, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Import will work after script is created
try:
    from scripts.build_insurance_enr_comparison import (
        _check_enrollment_covers_window,
        _build_comparison_table,
        _build_unknown_encounter_breakdown,
        _normalize_payer_with_na,
    )
    SCRIPT_AVAILABLE = True
except ImportError:
    SCRIPT_AVAILABLE = False


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script not yet created")
class TestEnrollmentCoverageUnion:
    """Test enrollment union coverage checking logic (D-04, D-05, D-06)."""

    def test_single_period_fully_covers_window(self, make_enrollment_df):
        """Test 1: Single enrollment period fully covers [treatment_date-30, treatment_date+30]."""
        # Treatment date: 2025-06-15
        # Window: [2025-05-16, 2025-07-15] = 61 days
        # Enrollment: 2025-05-01 to 2025-08-01 (fully covers)
        enrollment_df = make_enrollment_df(
            n_rows=1,
            enr_start=[date(2025, 5, 1)],
            enr_end=[date(2025, 8, 1)]
        )

        treatment_date = date(2025, 6, 15)
        window_start = treatment_date - timedelta(days=30)
        window_end = treatment_date + timedelta(days=30)

        result = _check_enrollment_covers_window(
            "PT000", window_start, window_end, enrollment_df
        )

        assert result is True, "Single period covering full window should return True"

    def test_two_adjacent_periods_cover_window(self, make_enrollment_df):
        """Test 2: Two adjacent enrollment periods together cover full window (D-05)."""
        # Treatment date: 2025-06-15
        # Window: [2025-05-16, 2025-07-15]
        # Enrollment 1: 2025-05-01 to 2025-06-14 (covers first half)
        # Enrollment 2: 2025-06-15 to 2025-08-01 (covers second half, adjacent)
        enrollment_df = pl.DataFrame({
            "ID": ["PT000", "PT000"],
            "ENR_START_DATE": [date(2025, 5, 1), date(2025, 6, 15)],
            "ENR_END_DATE": [date(2025, 6, 14), date(2025, 8, 1)],
        })

        treatment_date = date(2025, 6, 15)
        window_start = treatment_date - timedelta(days=30)
        window_end = treatment_date + timedelta(days=30)

        result = _check_enrollment_covers_window(
            "PT000", window_start, window_end, enrollment_df
        )

        assert result is True, "Adjacent periods should combine to cover window"

    def test_gap_in_enrollment_periods(self, make_enrollment_df):
        """Test 3: Enrollment periods have gap in window -> returns False."""
        # Treatment date: 2025-06-15
        # Window: [2025-05-16, 2025-07-15]
        # Enrollment 1: 2025-05-01 to 2025-06-01 (covers start)
        # Enrollment 2: 2025-07-01 to 2025-08-01 (covers end)
        # Gap: 2025-06-02 to 2025-06-30 (29 days uncovered)
        enrollment_df = pl.DataFrame({
            "ID": ["PT000", "PT000"],
            "ENR_START_DATE": [date(2025, 5, 1), date(2025, 7, 1)],
            "ENR_END_DATE": [date(2025, 6, 1), date(2025, 8, 1)],
        })

        treatment_date = date(2025, 6, 15)
        window_start = treatment_date - timedelta(days=30)
        window_end = treatment_date + timedelta(days=30)

        result = _check_enrollment_covers_window(
            "PT000", window_start, window_end, enrollment_df
        )

        assert result is False, "Gap in enrollment should return False"

    def test_no_enrollment_records(self, make_enrollment_df):
        """Test 4: Patient has no enrollment records -> returns False (D-06)."""
        # Empty enrollment for PT000, but enrollment_df has records for other patients
        enrollment_df = make_enrollment_df(n_rows=2)  # PT000, PT001

        treatment_date = date(2025, 6, 15)
        window_start = treatment_date - timedelta(days=30)
        window_end = treatment_date + timedelta(days=30)

        result = _check_enrollment_covers_window(
            "PT999", window_start, window_end, enrollment_df
        )

        assert result is False, "No enrollment records should return False"

    def test_partial_overlap_not_full_coverage(self, make_enrollment_df):
        """Test 5: Enrollment period only partially overlaps window -> returns False."""
        # Treatment date: 2025-06-15
        # Window: [2025-05-16, 2025-07-15]
        # Enrollment: 2025-06-01 to 2025-06-30 (covers middle but not start/end)
        enrollment_df = make_enrollment_df(
            n_rows=1,
            enr_start=[date(2025, 6, 1)],
            enr_end=[date(2025, 6, 30)]
        )

        treatment_date = date(2025, 6, 15)
        window_start = treatment_date - timedelta(days=30)
        window_end = treatment_date + timedelta(days=30)

        result = _check_enrollment_covers_window(
            "PT000", window_start, window_end, enrollment_df
        )

        assert result is False, "Partial overlap should return False"


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script not yet created")
class TestComparisonTableStructure:
    """Test comparison table building (D-11, D-15)."""

    def test_na_row_for_null_payer(self):
        """Test 6: Null payer values shown as 'N/A' row, separate from 'Unknown' (D-11)."""
        # Patient with null payer at treatment
        df = pl.DataFrame({
            "ID": ["PT001", "PT002", "PT003"],
            "PAYER_CATEGORY_AT_FIRST_DX": [None, "Medicare", "Unknown"],
            "ENR_COVERS_WINDOW": [1, 1, 0],
        })

        rows, n_covered, n_not_covered = _build_comparison_table(
            df, "PAYER_CATEGORY_AT_FIRST_DX", "ENR_COVERS_WINDOW"
        )

        # Extract payer categories from rows
        payer_categories = [row["Payer Category"] for row in rows]

        assert "N/A" in payer_categories, "N/A row should be present for null payer"
        assert "Unknown" in payer_categories, "Unknown row should be separate from N/A"

        # Check N/A has count 1 in covered group
        na_row = [r for r in rows if r["Payer Category"] == "N/A"][0]
        assert "1" in na_row["ENR Covers Window (N_Pct)"], "N/A should have 1 patient in covered group"

    def test_null_treatment_date_exclusion(self):
        """Test 7: Patients with null treatment dates excluded from cohort (D-15)."""
        # This test verifies table excludes nulls BEFORE calling _build_comparison_table
        # The function itself doesn't filter nulls — that's the caller's responsibility

        # Simulate pre-filtered data (nulls already removed)
        df = pl.DataFrame({
            "ID": ["PT001", "PT002"],
            "PAYER_CATEGORY_AT_FIRST_CHEMO": ["Medicare", "Medicaid"],
            "ENR_COVERS_WINDOW": [1, 0],
            "FIRST_CHEMO_DATE": [date(2025, 1, 15), date(2025, 2, 10)],
        })

        # All rows should have non-null dates after filtering
        assert df.filter(pl.col("FIRST_CHEMO_DATE").is_null()).height == 0

        # Table should work normally
        rows, n_covered, n_not_covered = _build_comparison_table(
            df, "PAYER_CATEGORY_AT_FIRST_CHEMO", "ENR_COVERS_WINDOW"
        )

        assert len(rows) >= 9, "Table should have at least 9 payer categories"

    def test_comparison_table_column_structure(self):
        """Test 9: Comparison table has correct column structure."""
        df = pl.DataFrame({
            "ID": ["PT001", "PT002", "PT003"],
            "PAYER_CATEGORY_AT_FIRST_DX": ["Medicare", "Medicaid", "Private"],
            "ENR_COVERS_WINDOW": [1, 1, 0],
        })

        rows, n_covered, n_not_covered = _build_comparison_table(
            df, "PAYER_CATEGORY_AT_FIRST_DX", "ENR_COVERS_WINDOW"
        )

        assert n_covered == 2, "Should count 2 covered patients"
        assert n_not_covered == 1, "Should count 1 not-covered patient"

        # Check first row has all expected columns
        first_row = rows[0]
        assert "Payer Category" in first_row
        assert any("ENR Covers Window" in k and "N_Pct" in k for k in first_row.keys())
        assert any("ENR Does Not Cover" in k and "N_Pct" in k for k in first_row.keys())


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script not yet created")
class TestUnknownEncounterBreakdown:
    """Test Unknown post-treatment payer encounter breakdown (D-17)."""

    def test_encounter_count_binning(self, make_encounter_df):
        """Test 8: Patients binned correctly into [0, 1-5, 6-10, 11-20, 21+]."""
        # Create enc_payer_summary with Unknown post-treatment payers
        enc_payer_summary = pl.DataFrame({
            "ID": ["PT001", "PT002", "PT003", "PT004", "PT005"],
            "POST_TREATMENT_PAYER": ["Unknown", "Unknown", "Unknown", "Unknown", "Unknown"],
            "LAST_CHEMO_DATE": [date(2025, 1, 1)] * 5,
            "LAST_RADIATION_DATE": [None] * 5,
            "LAST_SCT_DATE": [None] * 5,
        })

        # Create encounters: PT001=0, PT002=3, PT003=7, PT004=15, PT005=25
        # Spread across multiple months to avoid day overflow
        encounters = []
        for i in range(3):
            encounters.append({"ID": "PT002", "ADMIT_DATE": date(2025, 1, 10 + i)})
        for i in range(7):
            encounters.append({"ID": "PT003", "ADMIT_DATE": date(2025, 2, 1 + i)})
        for i in range(15):
            encounters.append({"ID": "PT004", "ADMIT_DATE": date(2025, 3, 1 + i)})
        for i in range(25):
            encounters.append({"ID": "PT005", "ADMIT_DATE": date(2025, 4, 1 + i)})

        enc_df = pl.DataFrame(encounters) if encounters else pl.DataFrame({"ID": [], "ADMIT_DATE": []})

        # Write temp parquet for function to read
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            enc_df.write_parquet(tmp.name)
            enc_path = Path(tmp.name)

        try:
            rows, n_unknown = _build_unknown_encounter_breakdown(enc_payer_summary, enc_path)

            bin_map = {row["Encounter Count Bin"]: row["N Patients (N)"] for row in rows}

            assert bin_map.get("0", 0) == 1, "PT001 should be in 0 bin"
            assert bin_map.get("1-5", 0) == 1, "PT002 (3 encounters) should be in 1-5 bin"
            assert bin_map.get("6-10", 0) == 1, "PT003 (7 encounters) should be in 6-10 bin"
            assert bin_map.get("11-20", 0) == 1, "PT004 (15 encounters) should be in 11-20 bin"
            assert bin_map.get("21+", 0) == 1, "PT005 (25 encounters) should be in 21+ bin"
            assert n_unknown == 5, "Should count 5 Unknown patients total"

        finally:
            enc_path.unlink(missing_ok=True)


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script not yet created")
class TestNormalizePayer:
    """Test payer normalization with N/A handling."""

    def test_normalize_payer_with_na(self):
        """Test _normalize_payer_with_na converts nulls to 'N/A' not 'Unknown'."""
        df = pl.DataFrame({
            "payer": [None, "Medicare", "No payment / Self-pay", "Unknown"]
        })

        result_df = df.with_columns(
            _normalize_payer_with_na(pl.col("payer")).alias("normalized")
        )

        result = result_df["normalized"].to_list()

        assert result[0] == "N/A", "Null should map to N/A"
        assert result[1] == "Medicare", "Medicare unchanged"
        assert result[2] == "Self-pay", "'No payment / Self-pay' should map to 'Self-pay'"
        assert result[3] == "Unknown", "Unknown unchanged"
