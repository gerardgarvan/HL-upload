"""Pytest shared fixtures for HL pipeline tests.

Factory fixtures for building PCORnet CDM test DataFrames with realistic defaults.
All factories return functions accepting kwargs for customization.

Available factories:
- make_encounter_df: ENCOUNTER table with payer columns
- make_diagnosis_df: DIAGNOSIS table with HL ICD-10 codes
- make_enrollment_df: ENROLLMENT table with date ranges
- make_vital_df: VITAL table with measurements
- make_procedures_df: PROCEDURES table with treatment CPTs

PCORnet code realism:
All factories use actual PCORnet value sets (payer codes 11/21/14, DX_TYPE 09/10,
ENC_TYPE IP/ED/AV) not synthetic integers or strings.
"""

import polars as pl
from datetime import date
import pytest


@pytest.fixture
def make_encounter_df():
    """Factory for ENCOUNTER DataFrames with PCORnet-realistic payer data.

    Returns a function that builds test DataFrames with sensible defaults and
    optional overrides for customization.

    Default behavior:
    - 3 rows with sequential patient IDs (PT001, PT002, PT003)
    - Medicare FFS (code "11") as primary payer
    - Medicaid FFS (code "21") as secondary payer
    - Recent admit dates (2025-01-01, 2025-01-02, 2025-01-03)
    - Inpatient encounters (ENC_TYPE "IP")

    Usage:
        def test_payer_fallback(make_encounter_df):
            df = make_encounter_df(
                n_rows=1,
                payer_primary=["NI"],  # No information - sentinel value
                payer_secondary=["21"]  # Medicaid FFS - valid payer
            )
            # Test effective payer fallback logic...
    """
    def _make(
        n_rows=3,
        patid_col="ID",
        payer_primary=None,
        payer_secondary=None,
        admit_dates=None,
        enc_types=None,
    ):
        """Build ENCOUNTER DataFrame with PCORnet-realistic defaults.

        Args:
            n_rows: Number of rows to generate (default: 3)
            patid_col: Patient ID column name (default: "ID")
            payer_primary: List of PAYER_TYPE_PRIMARY codes (default: ["11"] * n_rows - Medicare FFS)
            payer_secondary: List of PAYER_TYPE_SECONDARY codes (default: ["21"] * n_rows - Medicaid FFS)
            admit_dates: List of admit dates (default: [date(2025, 1, i+1) for i in range(n_rows)])
            enc_types: List of encounter types (default: ["IP"] * n_rows - inpatient)

        Returns:
            pl.DataFrame with columns: ID, ENCOUNTERID, PAYER_TYPE_PRIMARY,
            PAYER_TYPE_SECONDARY, ADMIT_DATE, ENC_TYPE
        """
        # Generate sequential patient IDs
        ids = [f"PT{i:03d}" for i in range(n_rows)]

        # Default to Medicare FFS (PCORnet code "11")
        payer_pri = payer_primary if payer_primary is not None else ["11"] * n_rows

        # Default to Medicaid FFS (PCORnet code "21")
        payer_sec = payer_secondary if payer_secondary is not None else ["21"] * n_rows

        # Default to sequential dates starting 2025-01-01
        dates = admit_dates if admit_dates is not None else [date(2025, 1, i+1) for i in range(n_rows)]

        # Default to inpatient encounters (PCORnet code "IP")
        enc_type = enc_types if enc_types is not None else ["IP"] * n_rows

        return pl.DataFrame({
            patid_col: ids,
            "ENCOUNTERID": [f"ENC{i:05d}" for i in range(n_rows)],
            "PAYER_TYPE_PRIMARY": payer_pri,
            "PAYER_TYPE_SECONDARY": payer_sec,
            "ADMIT_DATE": dates,
            "ENC_TYPE": enc_type,
        })

    return _make


@pytest.fixture
def make_diagnosis_df():
    """Factory for DIAGNOSIS DataFrames with PCORnet defaults.

    Default behavior:
    - 3 rows with sequential patient IDs (PT001, PT002, PT003)
    - HL ICD-10 codes (C81.10, C81.11, C81.12 - Hodgkin lymphoma subtypes)
    - DX_TYPE "10" (ICD-10-CM)
    - Recent DX_DATE (2025-01-01, 2025-01-02, 2025-01-03)

    Usage:
        def test_hl_cohort(make_diagnosis_df):
            df = make_diagnosis_df(
                n_rows=5,
                dx_codes=["C81.10"] * 5,  # All same HL subtype
                dx_type=["10"] * 5
            )
            # Test HL cohort identification...
    """
    def _make(
        n_rows=3,
        patid_col="ID",
        dx_codes=None,
        dx_type=None,
        dx_dates=None,
    ):
        """Build DIAGNOSIS DataFrame with PCORnet-realistic defaults.

        Args:
            n_rows: Number of rows to generate (default: 3)
            patid_col: Patient ID column name (default: "ID")
            dx_codes: List of diagnosis codes (default: HL ICD-10 codes C81.10-C81.12)
            dx_type: List of DX_TYPE codes (default: ["10"] * n_rows - ICD-10-CM)
            dx_dates: List of diagnosis dates (default: [date(2025, 1, i+1) for i in range(n_rows)])

        Returns:
            pl.DataFrame with columns: ID, ENCOUNTERID, DX, DX_TYPE, DX_DATE
        """
        # Generate sequential patient IDs
        ids = [f"PT{i:03d}" for i in range(n_rows)]

        # Default to HL ICD-10 codes (Hodgkin lymphoma subtypes)
        default_dx = ["C81.10", "C81.11", "C81.12"]
        dx = dx_codes if dx_codes is not None else [default_dx[i % len(default_dx)] for i in range(n_rows)]

        # Default to ICD-10-CM (PCORnet code "10")
        dtype = dx_type if dx_type is not None else ["10"] * n_rows

        # Default to sequential dates starting 2025-01-01
        dates = dx_dates if dx_dates is not None else [date(2025, 1, i+1) for i in range(n_rows)]

        return pl.DataFrame({
            patid_col: ids,
            "ENCOUNTERID": [f"ENC{i:05d}" for i in range(n_rows)],
            "DX": dx,
            "DX_TYPE": dtype,
            "DX_DATE": dates,
        })

    return _make


@pytest.fixture
def make_enrollment_df():
    """Factory for ENROLLMENT DataFrames with PCORnet defaults.

    Default behavior:
    - 3 rows with sequential patient IDs (PT001, PT002, PT003)
    - ENR_START_DATE: 2020-01-01
    - ENR_END_DATE: 2025-12-31
    - 5+ year enrollment span (typical for cohort selection)

    Usage:
        def test_enrollment_duration(make_enrollment_df):
            df = make_enrollment_df(
                n_rows=1,
                enr_start=["2015-01-01"],
                enr_end=["2020-12-31"]
            )
            # Test enrollment duration calculation...
    """
    def _make(
        n_rows=3,
        patid_col="ID",
        enr_start=None,
        enr_end=None,
    ):
        """Build ENROLLMENT DataFrame with PCORnet-realistic defaults.

        Args:
            n_rows: Number of rows to generate (default: 3)
            patid_col: Patient ID column name (default: "ID")
            enr_start: List of enrollment start dates (default: [date(2020, 1, 1)] * n_rows)
            enr_end: List of enrollment end dates (default: [date(2025, 12, 31)] * n_rows)

        Returns:
            pl.DataFrame with columns: ID, ENR_START_DATE, ENR_END_DATE
        """
        # Generate sequential patient IDs
        ids = [f"PT{i:03d}" for i in range(n_rows)]

        # Default to 5+ year enrollment (2020-01-01 to 2025-12-31)
        start_dates = enr_start if enr_start is not None else [date(2020, 1, 1)] * n_rows
        end_dates = enr_end if enr_end is not None else [date(2025, 12, 31)] * n_rows

        return pl.DataFrame({
            patid_col: ids,
            "ENR_START_DATE": start_dates,
            "ENR_END_DATE": end_dates,
        })

    return _make


@pytest.fixture
def make_vital_df():
    """Factory for VITAL DataFrames with PCORnet defaults.

    Default behavior:
    - 3 rows with sequential patient IDs (PT001, PT002, PT003)
    - HT: 170 cm (typical adult height)
    - WT: 70 kg (typical adult weight)
    - SYSTOLIC: 120 mmHg (normal BP)
    - DIASTOLIC: 80 mmHg (normal BP)
    - MEASURE_DATE: recent dates (2025-01-01, 2025-01-02, 2025-01-03)

    Usage:
        def test_vital_ranges(make_vital_df):
            df = make_vital_df(
                n_rows=1,
                ht=[300],  # Out of range height
                wt=[70]
            )
            # Test vital range validation...
    """
    def _make(
        n_rows=3,
        patid_col="ID",
        ht=None,
        wt=None,
        systolic=None,
        diastolic=None,
        measure_dates=None,
    ):
        """Build VITAL DataFrame with PCORnet-realistic defaults.

        Args:
            n_rows: Number of rows to generate (default: 3)
            patid_col: Patient ID column name (default: "ID")
            ht: List of heights in cm (default: [170] * n_rows)
            wt: List of weights in kg (default: [70] * n_rows)
            systolic: List of systolic BP in mmHg (default: [120] * n_rows)
            diastolic: List of diastolic BP in mmHg (default: [80] * n_rows)
            measure_dates: List of measure dates (default: [date(2025, 1, i+1) for i in range(n_rows)])

        Returns:
            pl.DataFrame with columns: ID, ENCOUNTERID, MEASURE_DATE, HT, WT, SYSTOLIC, DIASTOLIC
        """
        # Generate sequential patient IDs
        ids = [f"PT{i:03d}" for i in range(n_rows)]

        # Default to typical adult vitals
        heights = ht if ht is not None else [170] * n_rows
        weights = wt if wt is not None else [70] * n_rows
        sys_bp = systolic if systolic is not None else [120] * n_rows
        dia_bp = diastolic if diastolic is not None else [80] * n_rows

        # Default to sequential dates starting 2025-01-01
        dates = measure_dates if measure_dates is not None else [date(2025, 1, i+1) for i in range(n_rows)]

        return pl.DataFrame({
            patid_col: ids,
            "ENCOUNTERID": [f"ENC{i:05d}" for i in range(n_rows)],
            "MEASURE_DATE": dates,
            "HT": heights,
            "WT": weights,
            "SYSTOLIC": sys_bp,
            "DIASTOLIC": dia_bp,
        })

    return _make


@pytest.fixture
def make_procedures_df():
    """Factory for PROCEDURES DataFrames with PCORnet defaults.

    Default behavior:
    - 3 rows with sequential patient IDs (PT001, PT002, PT003)
    - PX: Treatment CPTs (77401 radiation, 38240 SCT)
    - PX_TYPE: "CH" (CPT-4 codes)
    - PX_DATE: recent dates (2025-01-01, 2025-01-02, 2025-01-03)

    Usage:
        def test_treatment_flags(make_procedures_df):
            df = make_procedures_df(
                n_rows=2,
                px_codes=["77401", "77401"],  # Both radiation
                px_type=["CH", "CH"]
            )
            # Test treatment modality flagging...
    """
    def _make(
        n_rows=3,
        patid_col="ID",
        px_codes=None,
        px_type=None,
        px_dates=None,
    ):
        """Build PROCEDURES DataFrame with PCORnet-realistic defaults.

        Args:
            n_rows: Number of rows to generate (default: 3)
            patid_col: Patient ID column name (default: "ID")
            px_codes: List of procedure codes (default: ["77401", "38240", "77401"] - treatment CPTs)
            px_type: List of PX_TYPE codes (default: ["CH"] * n_rows - CPT-4)
            px_dates: List of procedure dates (default: [date(2025, 1, i+1) for i in range(n_rows)])

        Returns:
            pl.DataFrame with columns: ID, ENCOUNTERID, PX, PX_TYPE, PX_DATE
        """
        # Generate sequential patient IDs
        ids = [f"PT{i:03d}" for i in range(n_rows)]

        # Default to treatment CPTs (radiation 77401, SCT 38240)
        default_px = ["77401", "38240", "77401"]  # Mix of radiation and SCT
        px = px_codes if px_codes is not None else [default_px[i % len(default_px)] for i in range(n_rows)]

        # Default to CPT-4 (PCORnet code "CH")
        ptype = px_type if px_type is not None else ["CH"] * n_rows

        # Default to sequential dates starting 2025-01-01
        dates = px_dates if px_dates is not None else [date(2025, 1, i+1) for i in range(n_rows)]

        return pl.DataFrame({
            patid_col: ids,
            "ENCOUNTERID": [f"ENC{i:05d}" for i in range(n_rows)],
            "PX": px,
            "PX_TYPE": ptype,
            "PX_DATE": dates,
        })

    return _make
