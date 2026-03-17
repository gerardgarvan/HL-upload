"""Comprehensive tests for deduplication logic with null key handling.

Tests src.clean.dedup.flag_duplicates() covering:
- Composite key duplicate detection (DIAGNOSIS, PROCEDURES, LAB_RESULT_CM, VITAL, PRESCRIBING)
- Null key behavior (nulls DO match - AUDIT-004 RESOLVED)
- All occurrences flagged (not just subsequent)
- VITAL dedup key edge case (AUDIT-010)
- DEDUP_KEYS table coverage

AUDIT-004 RESOLVED: Null key behavior - rows with null keys ARE flagged as duplicates
when other key columns match (Polars is_duplicated() treats null == null). This may be
undesirable as null represents unknown, not semantic match.

AUDIT-010: VITAL dedup key missing vital-type discriminator - same-day vitals of
different types incorrectly flagged as duplicates. Fix requires schema check for
VITAL_SOURCE column.
"""

import pytest
import polars as pl

from src.clean.dedup import flag_duplicates, DEDUP_KEYS


class TestFlagDuplicatesCompositeKey:
    """Test duplicate detection using composite keys."""

    def test_diagnosis_composite_key(self):
        """Test DIAGNOSIS dedup key: [ID, DX_DATE, DX].

        Exact duplicates (same ID + DX_DATE + DX) should be flagged.
        Different date or different DX should NOT be flagged.
        """
        # DIAGNOSIS dedup key: ["ID", "DX_DATE", "DX"]
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001", "PT001", "PT002"],
            "DX_DATE": ["2020-01-01", "2020-01-01", "2020-01-02", "2020-01-01"],
            "DX": ["C81.10", "C81.10", "C81.10", "C81.10"],
            "ENCOUNTERID": ["ENC001", "ENC001", "ENC002", "ENC003"],
        }).with_columns(pl.col("DX_DATE").str.to_date())

        result = flag_duplicates(test_data, "DIAGNOSIS")

        # Row 0 and 1: Same ID + DX_DATE + DX → IS_DUPLICATE=1
        assert result["IS_DUPLICATE"][0] == 1
        assert result["IS_DUPLICATE"][1] == 1

        # Row 2: Different DX_DATE → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][2] == 0

        # Row 3: Different ID → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][3] == 0

    def test_procedures_composite_key(self):
        """Test PROCEDURES dedup key: [ID, PX_DATE, PX]."""
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001", "PT001"],
            "PX_DATE": ["2020-01-01", "2020-01-01", "2020-01-02"],
            "PX": ["38240", "38240", "38240"],
        }).with_columns(pl.col("PX_DATE").str.to_date())

        result = flag_duplicates(test_data, "PROCEDURES")

        # Row 0 and 1: Same ID + PX_DATE + PX → IS_DUPLICATE=1
        assert result["IS_DUPLICATE"][0] == 1
        assert result["IS_DUPLICATE"][1] == 1

        # Row 2: Different PX_DATE → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][2] == 0

    def test_lab_result_cm_composite_key(self):
        """Test LAB_RESULT_CM dedup key: [ID, SPECIMEN_DATE, LAB_LOINC]."""
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001", "PT001"],
            "SPECIMEN_DATE": ["2020-01-01", "2020-01-01", "2020-01-02"],
            "LAB_LOINC": ["6690-2", "6690-2", "6690-2"],
            "RESULT_NUM": [4.5, 4.5, 5.0],
        }).with_columns(pl.col("SPECIMEN_DATE").str.to_date())

        result = flag_duplicates(test_data, "LAB_RESULT_CM")

        # Row 0 and 1: Same ID + SPECIMEN_DATE + LAB_LOINC → IS_DUPLICATE=1
        assert result["IS_DUPLICATE"][0] == 1
        assert result["IS_DUPLICATE"][1] == 1

        # Row 2: Different SPECIMEN_DATE → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][2] == 0

    def test_encounter_composite_key(self):
        """Test ENCOUNTER dedup key: [ID, ADMIT_DATE, ENC_TYPE, FACILITYID]."""
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001", "PT001"],
            "ADMIT_DATE": ["2020-01-01", "2020-01-01", "2020-01-01"],
            "ENC_TYPE": ["IP", "IP", "AV"],
            "FACILITYID": ["FAC001", "FAC001", "FAC001"],
        }).with_columns(pl.col("ADMIT_DATE").str.to_date())

        result = flag_duplicates(test_data, "ENCOUNTER")

        # Row 0 and 1: Same ID + ADMIT_DATE + ENC_TYPE + FACILITYID → IS_DUPLICATE=1
        assert result["IS_DUPLICATE"][0] == 1
        assert result["IS_DUPLICATE"][1] == 1

        # Row 2: Different ENC_TYPE → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][2] == 0

    def test_prescribing_composite_key(self):
        """Test PRESCRIBING dedup key: [ID, RX_ORDER_DATE, RXNORM_CUI]."""
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001", "PT001"],
            "RX_ORDER_DATE": ["2020-01-01", "2020-01-01", "2020-01-02"],
            "RXNORM_CUI": ["1234567", "1234567", "1234567"],
        }).with_columns(pl.col("RX_ORDER_DATE").str.to_date())

        result = flag_duplicates(test_data, "PRESCRIBING")

        # Row 0 and 1: Same ID + RX_ORDER_DATE + RXNORM_CUI → IS_DUPLICATE=1
        assert result["IS_DUPLICATE"][0] == 1
        assert result["IS_DUPLICATE"][1] == 1

        # Row 2: Different RX_ORDER_DATE → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][2] == 0


class TestFlagDuplicatesNullKeyBehavior:
    """Test null key handling in duplicate detection.

    AUDIT-004 RESOLVED: Polars is_duplicated() treats null == null (DOES match nulls).
    Rows with null keys ARE flagged as duplicates of each other if other key columns match.

    This is potentially problematic: null date/code values represent unknowns, not
    semantic matches. However, Polars default behavior is null == null for is_duplicated().
    """

    def test_null_keys_are_matched(self):
        """Test that rows with null keys ARE flagged as duplicates of each other.

        AUDIT-004 RESOLVED: Contrary to initial assumption, Polars is_duplicated()
        treats null == null (nulls DO match). This means rows with null in composite
        key are flagged as duplicates if other key columns match.

        Implication: Two diagnoses with same ID + DX but null DX_DATE are flagged
        as duplicates. This may be undesirable (null represents unknown, not semantic match).
        """
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001", "PT001"],
            "DX_DATE": [None, None, "2020-01-01"],  # Two null dates
            "DX": ["C81.10", "C81.10", "C81.10"],
        }).with_columns(pl.col("DX_DATE").str.to_date())

        result = flag_duplicates(test_data, "DIAGNOSIS")

        # Row 0 and 1: Both have null DX_DATE + same ID/DX → IS_DUPLICATE=1
        # Polars treats null == null in is_duplicated()
        assert result["IS_DUPLICATE"][0] == 1
        assert result["IS_DUPLICATE"][1] == 1

        # Row 2: Non-null, unique → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][2] == 0

    def test_partial_null_keys_are_matched(self):
        """Test that partial null in composite key still matches duplicates."""
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001", "PT001"],
            "DX_DATE": ["2020-01-01", "2020-01-01", "2020-01-01"],
            "DX": [None, None, "C81.10"],  # Two null DX codes
        }).with_columns(pl.col("DX_DATE").str.to_date())

        result = flag_duplicates(test_data, "DIAGNOSIS")

        # Row 0 and 1: Null DX + same ID/DX_DATE → IS_DUPLICATE=1
        # Polars treats null == null
        assert result["IS_DUPLICATE"][0] == 1
        assert result["IS_DUPLICATE"][1] == 1

        # Row 2: Non-null DX, unique → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][2] == 0

    def test_mixed_null_and_valid_duplicates(self):
        """Test duplicate detection with mix of null and valid keys."""
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001", "PT001", "PT001"],
            "DX_DATE": [None, "2020-01-01", "2020-01-01", "2020-01-02"],
            "DX": ["C81.10", "C81.10", "C81.10", "C81.10"],
        }).with_columns(pl.col("DX_DATE").str.to_date())

        result = flag_duplicates(test_data, "DIAGNOSIS")

        # Row 0: Null DX_DATE → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][0] == 0

        # Row 1 and 2: Same ID + DX_DATE + DX → IS_DUPLICATE=1
        assert result["IS_DUPLICATE"][1] == 1
        assert result["IS_DUPLICATE"][2] == 1

        # Row 3: Different DX_DATE → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][3] == 0


class TestFlagDuplicatesAllOccurrences:
    """Verify ALL occurrences of duplicate key are flagged (not just subsequent)."""

    def test_all_occurrences_flagged(self):
        """Test that both first and subsequent occurrences are flagged.

        Polars is_duplicated() flags ALL rows sharing duplicate key values.
        """
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001", "PT002"],
            "DX_DATE": ["2020-01-01", "2020-01-01", "2020-01-01"],
            "DX": ["C81.10", "C81.10", "C81.10"],
        }).with_columns(pl.col("DX_DATE").str.to_date())

        result = flag_duplicates(test_data, "DIAGNOSIS")

        # Row 0: First occurrence → IS_DUPLICATE=1 (ALL occurrences flagged)
        assert result["IS_DUPLICATE"][0] == 1

        # Row 1: Second occurrence → IS_DUPLICATE=1
        assert result["IS_DUPLICATE"][1] == 1

        # Row 2: Different ID → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][2] == 0

    def test_three_way_duplicate(self):
        """Test that all three occurrences of a triplicate are flagged."""
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001", "PT001"],
            "DX_DATE": ["2020-01-01", "2020-01-01", "2020-01-01"],
            "DX": ["C81.10", "C81.10", "C81.10"],
        }).with_columns(pl.col("DX_DATE").str.to_date())

        result = flag_duplicates(test_data, "DIAGNOSIS")

        # All three rows flagged as duplicates
        assert result["IS_DUPLICATE"][0] == 1
        assert result["IS_DUPLICATE"][1] == 1
        assert result["IS_DUPLICATE"][2] == 1


class TestVitalDedupKeyEdgeCase:
    """Test VITAL dedup key edge case.

    AUDIT-010: VITAL dedup key missing vital-type discriminator - same-day vitals of
    different types incorrectly flagged as duplicates. Fix requires schema check for
    VITAL_SOURCE column.
    """

    def test_vital_same_day_multi_vital_scenario(self):
        """Test VITAL dedup key: [ID, MEASURE_DATE].

        Current key doesn't include vital type (HT, WT, BP, etc.), so same-day
        vitals of different types are incorrectly flagged as duplicates.

        AUDIT-010: This test documents current behavior (bug). Fix requires adding
        vital-type discriminator to dedup key (needs schema investigation for
        VITAL_SOURCE or measurement type column).
        """
        # Simulate same-day measurements of different vital types
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001", "PT001"],
            "MEASURE_DATE": ["2020-01-01", "2020-01-01", "2020-01-02"],
            "HT": [170.0, None, 170.0],  # Height on day 1, height on day 2
            "WT": [None, 70.0, 71.0],    # Weight on day 1, weight on day 2
        }).with_columns(pl.col("MEASURE_DATE").str.to_date())

        result = flag_duplicates(test_data, "VITAL")

        # CURRENT BEHAVIOR (documents bug):
        # Row 0 and 1: Same ID + MEASURE_DATE → IS_DUPLICATE=1
        # This is INCORRECT - they are different vital types (HT vs WT)
        assert result["IS_DUPLICATE"][0] == 1
        assert result["IS_DUPLICATE"][1] == 1

        # Row 2: Different MEASURE_DATE → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][2] == 0

        # TODO(fix): VITAL dedup key should include vital type to avoid this.
        # Expected behavior after fix: Row 0 and 1 should be IS_DUPLICATE=0
        # (different vital types, not semantic duplicates).
        #
        # Fix requires schema investigation:
        # - Check if VITAL_SOURCE column exists
        # - Or use presence of HT/WT/BP values to infer type
        # - Update DEDUP_KEYS["VITAL"] to include vital type discriminator

    def test_vital_same_type_same_day_is_duplicate(self):
        """Test that same vital type on same day IS correctly flagged."""
        # Two height measurements on same day (true duplicate)
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001"],
            "MEASURE_DATE": ["2020-01-01", "2020-01-01"],
            "HT": [170.0, 170.0],
            "WT": [None, None],
        }).with_columns(pl.col("MEASURE_DATE").str.to_date())

        result = flag_duplicates(test_data, "VITAL")

        # Same ID + MEASURE_DATE → IS_DUPLICATE=1
        # This is CORRECT - same vital type, same day
        assert result["IS_DUPLICATE"][0] == 1
        assert result["IS_DUPLICATE"][1] == 1


class TestDedupKeysTableCoverage:
    """Verify DEDUP_KEYS coverage and documentation."""

    def test_dedup_keys_expected_tables(self):
        """Verify all expected tables have dedup keys defined."""
        expected_tables = {
            "DIAGNOSIS",
            "PROCEDURES",
            "LAB_RESULT_CM",
            "ENCOUNTER",
            "VITAL",
            "PRESCRIBING",
        }

        assert expected_tables.issubset(set(DEDUP_KEYS.keys()))

    def test_dedup_keys_composite_structure(self):
        """Verify each dedup key has multiple columns (composite keys)."""
        for table, keys in DEDUP_KEYS.items():
            # All should have at least 2 columns (ID + date/code)
            assert len(keys) >= 2, f"{table} should have composite key (≥2 columns)"

            # All should include ID column
            assert "ID" in keys, f"{table} dedup key should include ID"

    def test_tables_without_dedup_keys(self):
        """Document tables NOT in DEDUP_KEYS (intentional, single-row-per-patient).

        Tables like DEMOGRAPHIC, DEATH, ENROLLMENT are single-row-per-patient
        or have different uniqueness constraints (not event-based).
        """
        # These tables intentionally NOT in DEDUP_KEYS
        single_row_tables = {"DEMOGRAPHIC", "DEATH", "ENROLLMENT"}

        for table in single_row_tables:
            assert table not in DEDUP_KEYS, f"{table} should NOT have dedup key"


class TestFlagDuplicatesEdgeCases:
    """Test edge cases and error handling."""

    def test_unknown_table_returns_unchanged(self):
        """Test that unknown table name returns DataFrame unchanged."""
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001"],
            "SOME_DATE": ["2020-01-01", "2020-01-01"],
        })

        result = flag_duplicates(test_data, "UNKNOWN_TABLE")

        # Should return unchanged (no IS_DUPLICATE column added)
        assert "IS_DUPLICATE" not in result.columns
        assert result.equals(test_data)

    def test_missing_key_columns_returns_unchanged(self):
        """Test that missing key columns returns DataFrame unchanged."""
        # DIAGNOSIS requires ["ID", "DX_DATE", "DX"]
        test_data = pl.DataFrame({
            "ID": ["PT001", "PT001"],
            "SOME_OTHER_COL": ["A", "B"],
        })

        result = flag_duplicates(test_data, "DIAGNOSIS")

        # Missing DX_DATE and DX → returns unchanged
        assert "IS_DUPLICATE" not in result.columns
        assert result.equals(test_data)

    def test_empty_dataframe(self):
        """Test flag_duplicates() on empty DataFrame."""
        test_data = pl.DataFrame({
            "ID": [],
            "DX_DATE": [],
            "DX": [],
        }, schema={"ID": pl.String, "DX_DATE": pl.Date, "DX": pl.String})

        result = flag_duplicates(test_data, "DIAGNOSIS")

        # Should add IS_DUPLICATE column but no rows
        assert "IS_DUPLICATE" in result.columns
        assert result.is_empty()

    def test_single_row_not_duplicate(self):
        """Test that single row is NOT flagged as duplicate."""
        test_data = pl.DataFrame({
            "ID": ["PT001"],
            "DX_DATE": ["2020-01-01"],
            "DX": ["C81.10"],
        }).with_columns(pl.col("DX_DATE").str.to_date())

        result = flag_duplicates(test_data, "DIAGNOSIS")

        # Single row → IS_DUPLICATE=0
        assert result["IS_DUPLICATE"][0] == 0
