# Pytest shared fixtures

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
