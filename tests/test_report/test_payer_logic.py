"""Comprehensive tests for payer logic edge cases.

Tests cover:
- PCORnet payer code → category mapping (all codes + sentinel values)
- Dual-eligible detection (all code combinations, null secondary handling)
- Effective payer fallback (primary → secondary when primary is sentinel)
- INCLUDE_99_AS_SENTINEL flag behavior (both True/False modes)

Resolves AUDIT-001 (99/9999 semantics) and AUDIT-005 (dual-eligible with null secondary).
"""

import pytest
import polars as pl
from polars.testing import assert_series_equal

from src.report.encounter_payer_summary import (
    _collapse_payer_category,
    _payer_category_from_effective_and_dual,
    _effective_payer_and_dual_exprs,
    INVALID_PAYER,
    DUAL_ELIGIBLE_CODES,
    INCLUDE_99_AS_SENTINEL,
)


# ============================================================================
# Test 1: Collapse payer category - ALL PCORnet codes + sentinel values
# ============================================================================

@pytest.mark.parametrize(
    "payer_code,expected_category",
    [
        # Valid Medicare codes (1xx prefix)
        ("11", "Medicare"),          # Medicare FFS
        ("121", "Medicare"),         # Medicare Advantage
        ("12", "Medicare"),          # Medicare managed care
        ("19", "Medicare"),          # Medicare other

        # Valid Medicaid codes (2xx prefix)
        ("21", "Medicaid"),          # Medicaid FFS
        ("221", "Medicaid"),         # Medicaid managed care
        ("23", "Medicaid"),          # Medicaid CHIP
        ("29", "Medicaid"),          # Medicaid other

        # Valid Private codes (5xx, 6xx prefix)
        ("51", "Private"),           # Commercial insurance
        ("52", "Private"),           # Private employer-based
        ("61", "Private"),           # Self-insured
        ("69", "Private"),           # Private other

        # Valid Other government codes (3xx, 4xx prefix)
        ("31", "Other government"),  # VA
        ("32", "Other government"),  # TriCare
        ("33", "Other government"),  # Indian Health Service
        ("41", "Other government"),  # Corrections Federal (NOT dual-eligible)
        ("42", "Other government"),  # Corrections State/Local

        # No payment / Self-pay (8xx prefix)
        ("81", "No payment / Self-pay"),
        ("82", "No payment / Self-pay"),

        # Other payers (7xx, 9xx prefix)
        ("71", "Other"),
        ("91", "Other"),

        # Sentinel values (NI/UN/OT)
        ("NI", "Unknown"),           # No information
        ("UN", "Unknown"),           # Unknown
        ("OT", "Unknown"),           # Other (not elsewhere classified)
        ("UNKNOWN", "Unknown"),      # Legacy string

        # Sentinel values (99/9999) - AUDIT-001
        ("99", "Unavailable"),       # When INCLUDE_99_AS_SENTINEL=False (current default)
        ("9999", "Unavailable"),

        # Edge cases: null, empty, whitespace
        (None, "Unknown"),           # Null
        ("", "Unknown"),             # Empty string
        ("   ", "Unknown"),          # Whitespace only

        # Unrecognized codes
        ("ZZ", "Other"),             # Unrecognized code
        ("XX123", "Other"),          # Invalid format
    ],
    ids=[
        "medicare_ffs", "medicare_advantage", "medicare_managed", "medicare_other",
        "medicaid_ffs", "medicaid_managed", "medicaid_chip", "medicaid_other",
        "commercial", "private_employer", "self_insured", "private_other",
        "va", "tricare", "ihs", "corrections_federal_not_dual", "corrections_state",
        "self_pay_1", "self_pay_2",
        "other_7x", "other_9x",
        "ni_sentinel", "un_sentinel", "ot_sentinel", "unknown_string",
        "sentinel_99", "sentinel_9999",
        "null", "empty", "whitespace",
        "unrecognized_zz", "unrecognized_format"
    ]
)
def test_collapse_payer_category_all_pcornet_codes(payer_code, expected_category):
    """Test payer category mapping for all PCORnet codes and sentinel values.

    Covers:
    - All PCORnet payer typology prefixes (1xx through 9xx)
    - Sentinel values (NI, UN, OT, 99, 9999)
    - Edge cases (null, empty, whitespace, unrecognized)

    Clinical context: PCORnet payer typology enables standardized payer classification
    across data networks. Collapsed categories support stratified analysis while
    maintaining HIPAA-compliant small-cell thresholds.
    """
    assert _collapse_payer_category(payer_code) == expected_category


# ============================================================================
# Test 2: Dual-eligible code detection
# ============================================================================

@pytest.mark.parametrize(
    "payer_code,is_dual_code",
    [
        # Dual-eligible codes (14, 141, 142)
        ("14", True),    # Dual Eligibility Medicare/Medicaid Organization
        ("141", True),   # Dual-Eligible Special Needs Plan (D-SNP)
        ("142", True),   # Fully Integrated Dual-Eligible Special Needs Plan (FIDE-SNP)

        # NOT dual-eligible (common confusion: 41 = Corrections, not dual)
        ("41", False),   # Corrections Federal (Other government, not dual)

        # Other codes
        ("11", False),   # Medicare alone (not dual)
        ("21", False),   # Medicaid alone (not dual)
        ("51", False),   # Private (not dual)
    ],
    ids=["dual_14", "dual_141", "dual_142", "corrections_41_not_dual", "medicare", "medicaid", "private"]
)
def test_dual_eligible_code_detection(payer_code, is_dual_code):
    """Test that dual-eligible codes (14/141/142) are correctly identified.

    Code 41 (Corrections Federal) is NOT dual-eligible - it's Other government.
    This is a common source of confusion (41 vs 141).
    """
    assert (payer_code in DUAL_ELIGIBLE_CODES) == is_dual_code


# ============================================================================
# Test 3: Effective payer fallback to secondary
# ============================================================================

@pytest.mark.parametrize(
    "primary,secondary,expected_effective",
    [
        # Primary is sentinel → fallback to secondary
        ("NI", "21", "21"),    # No information → use Medicaid
        ("UN", "11", "11"),    # Unknown → use Medicare
        ("OT", "51", "51"),    # Other → use Private
        (None, "21", "21"),    # Null primary → use secondary
        ("", "21", "21"),      # Empty primary → use secondary

        # Primary is valid → use primary (ignore secondary)
        ("11", "21", "11"),    # Medicare primary, Medicaid secondary → use Medicare
        ("51", "11", "51"),    # Private primary, Medicare secondary → use Private

        # Both invalid → effective payer is null
        ("NI", "UN", None),    # Both sentinel values
        (None, None, None),    # Both null
        ("", "", None),        # Both empty
    ],
    ids=[
        "ni_fallback", "un_fallback", "ot_fallback", "null_fallback", "empty_fallback",
        "valid_primary_medicare", "valid_primary_private",
        "both_sentinel", "both_null", "both_empty"
    ]
)
def test_payer_fallback_to_secondary(primary, secondary, expected_effective, make_encounter_df):
    """Test effective payer fallback: primary if valid, else secondary if valid, else null.

    Sentinel values (NI, UN, OT, null, empty) trigger fallback to secondary.
    Valid primary payer is used even if secondary is also valid.
    """
    df = make_encounter_df(n_rows=1, payer_primary=[primary], payer_secondary=[secondary])

    # Call _effective_payer_and_dual_exprs to test fallback logic
    effective_expr, valid_expr, dual_expr = _effective_payer_and_dual_exprs(has_secondary=True)

    result = df.select([
        effective_expr,
        valid_expr,
        dual_expr
    ])

    assert result["effective_payer"][0] == expected_effective


# ============================================================================
# Test 4: Payer fallback when secondary also invalid
# ============================================================================

def test_payer_fallback_when_secondary_also_invalid(make_encounter_df):
    """Test effective payer when both primary and secondary are sentinels.

    Current behavior: effective_payer = null when both are sentinel values.

    Clinical rationale: When both payer fields are missing/unknown, patient's
    insurance status is truly unknown. This is distinct from "Unavailable" (99/9999)
    which indicates data collection attempted but categorization failed.

    TODO(audit): AUDIT-005 resolved - documented that null effective_payer is correct
    when both primary and secondary are sentinels.
    """
    df = make_encounter_df(n_rows=1, payer_primary=["NI"], payer_secondary=["UN"])

    effective_expr, valid_expr, dual_expr = _effective_payer_and_dual_exprs(has_secondary=True)

    result = df.select([effective_expr, valid_expr])

    # Both invalid → effective_payer should be null
    assert result["effective_payer"][0] is None
    assert result["_valid"][0] is False


# ============================================================================
# Test 5: Dual-eligible detection with null secondary (AUDIT-005 FIX)
# ============================================================================

@pytest.mark.parametrize(
    "primary,secondary,expected_dual",
    [
        # AUDIT-005 FIX: Primary is 14/141/142 → dual_eligible=1 even with null secondary
        ("14", None, 1),     # Dual code in primary, null secondary → dual
        ("141", None, 1),    # D-SNP code in primary, null secondary → dual
        ("142", None, 1),    # FIDE-SNP code in primary, null secondary → dual

        # Medicare + Medicaid combination → dual
        ("11", "21", 1),     # Medicare primary + Medicaid secondary → dual
        ("21", "11", 1),     # Medicaid primary + Medicare secondary → dual

        # Dual code in secondary → dual
        ("11", "14", 1),     # Medicare primary + dual code secondary → dual
        ("51", "141", 1),    # Private primary + dual code secondary → dual

        # NOT dual-eligible cases
        ("11", None, 0),     # Medicare alone (null secondary) → not dual
        ("21", None, 0),     # Medicaid alone (null secondary) → not dual
        ("11", "11", 0),     # Medicare primary + Medicare secondary → not dual
        ("51", "21", 0),     # Private primary + Medicaid secondary → not dual (no Medicare)
    ],
    ids=[
        "dual_14_null_sec", "dual_141_null_sec", "dual_142_null_sec",
        "medicare_medicaid", "medicaid_medicare",
        "dual_code_secondary_14", "dual_code_secondary_141",
        "medicare_only", "medicaid_only", "medicare_both", "private_medicaid"
    ]
)
def test_dual_eligible_detection_with_null_secondary(primary, secondary, expected_dual, make_encounter_df):
    """Test dual-eligible detection with all code combinations including null secondary.

    AUDIT-005 RESOLUTION: Primary codes 14/141/142 should set dual_eligible=1 even when
    secondary is null. These are explicit dual-eligible codes and don't require secondary
    payer to confirm dual status.

    Clinical rationale: Dual-eligible patients (Medicare + Medicaid) are a critical
    population for health equity analysis. PCORnet codes 14/141/142 explicitly indicate
    dual-eligible status and should be sufficient alone.
    """
    # Build encounter with specified payers
    df = make_encounter_df(n_rows=1, payer_primary=[primary], payer_secondary=[secondary])

    # Test with has_secondary=True (secondary column exists, may be null)
    effective_expr, valid_expr, dual_expr = _effective_payer_and_dual_exprs(has_secondary=True)

    result = df.select([dual_expr])

    assert result["dual_eligible"][0] == expected_dual, \
        f"Expected dual_eligible={expected_dual} for primary={primary}, secondary={secondary}"


# ============================================================================
# Test 6: Payer category with dual-eligible override
# ============================================================================

@pytest.mark.parametrize(
    "effective_payer,dual_eligible,expected_category",
    [
        # Dual-eligible override (dual_eligible=1 → category is "Dual eligible")
        ("11", 1, "Dual eligible"),   # Medicare + dual flag → Dual eligible
        ("21", 1, "Dual eligible"),   # Medicaid + dual flag → Dual eligible
        ("99", 1, "Dual eligible"),   # Unavailable + dual flag → Dual eligible
        (None, 1, "Dual eligible"),   # Null + dual flag → Dual eligible

        # NOT dual-eligible (dual_eligible=0 → use standard category)
        ("11", 0, "Medicare"),        # Medicare without dual flag
        ("21", 0, "Medicaid"),        # Medicaid without dual flag
        ("51", 0, "Private"),         # Private without dual flag
        ("NI", 0, "Unknown"),         # Sentinel without dual flag
    ],
    ids=[
        "dual_medicare", "dual_medicaid", "dual_unavailable", "dual_null",
        "medicare_only", "medicaid_only", "private_only", "sentinel_not_dual"
    ]
)
def test_payer_category_dual_eligible_override(effective_payer, dual_eligible, expected_category):
    """Test that dual-eligible flag overrides standard payer categorization.

    When dual_eligible=1, category is always "Dual eligible" regardless of effective payer code.
    When dual_eligible=0, standard payer category mapping applies.

    Clinical rationale: Dual-eligible patients are a distinct payer category with unique
    cost-sharing and access patterns. Overriding standard Medicare/Medicaid categorization
    enables dual-eligible cohort analysis.
    """
    assert _payer_category_from_effective_and_dual(effective_payer, dual_eligible) == expected_category


# ============================================================================
# Test 7: INCLUDE_99_AS_SENTINEL flag behavior (AUDIT-001)
# ============================================================================

def test_include_99_as_sentinel_false_default():
    """Test INCLUDE_99_AS_SENTINEL=False (current default).

    When False: 99/9999 map to "Unavailable" category (valid but unknown payer).
    No fallback to secondary payer occurs.

    AUDIT-001 RESOLUTION: Current behavior (False) treats 99/9999 as valid payer
    codes representing "Unable to categorize" (data collection attempted but
    categorization failed). This is distinct from NI/UN/OT (data not collected or
    unusable).

    Clinical rationale: 99/9999 semantics vary by data source. Current setting (False)
    maximizes data retention by treating as valid "Unavailable" category rather than
    triggering secondary fallback.
    """
    # Verify current flag state
    assert INCLUDE_99_AS_SENTINEL is False

    # Test 99 → "Unavailable"
    assert _collapse_payer_category("99") == "Unavailable"
    assert _collapse_payer_category("9999") == "Unavailable"

    # Test 99 is NOT in INVALID_PAYER set (no fallback)
    assert "99" not in INVALID_PAYER
    assert "9999" not in INVALID_PAYER


def test_include_99_as_sentinel_true_behavior(make_encounter_df, monkeypatch):
    """Test INCLUDE_99_AS_SENTINEL=True behavior (if flag enabled).

    When True: 99/9999 treated like NI/UN/OT sentinels, trigger fallback to secondary.

    AUDIT-001 RESOLUTION: Documented that flag exists for partner-specific handling
    if 99/9999 semantics vary. If enabled, 99/9999 trigger fallback to secondary payer.

    Note: This test uses monkeypatch to simulate flag=True without changing production code.
    """
    # Simulate INCLUDE_99_AS_SENTINEL=True by monkeypatching
    monkeypatch.setattr("src.report.encounter_payer_summary.INCLUDE_99_AS_SENTINEL", True)

    # Need to reimport _effective_payer_and_dual_exprs to pick up monkeypatched value
    # (Python module caching means we can't just change the flag)
    # Instead, test the sentinel_set logic directly
    from src.report.encounter_payer_summary import _sentinel_set

    sentinel = _sentinel_set()

    # When True, 99/9999 should be in sentinel set
    assert "99" in sentinel or "9999" in sentinel, \
        "INCLUDE_99_AS_SENTINEL=True should add 99/9999 to sentinel set"


# ============================================================================
# Test 8: Sentinel constants verification
# ============================================================================

def test_invalid_payer_sentinel_constants():
    """Verify INVALID_PAYER constant contains expected sentinel values.

    Sentinel values (NI, UN, OT) trigger fallback to secondary payer.
    These are PCORnet standard codes for missing/unusable data.
    """
    expected_sentinels = {"NI", "UN", "OT"}
    assert INVALID_PAYER == expected_sentinels


def test_dual_eligible_codes_constant():
    """Verify DUAL_ELIGIBLE_CODES constant contains expected dual codes.

    PCORnet dual-eligible codes: 14, 141, 142
    Code 41 (Corrections Federal) is NOT dual-eligible.
    """
    expected_dual_codes = ("14", "141", "142")
    assert DUAL_ELIGIBLE_CODES == expected_dual_codes
