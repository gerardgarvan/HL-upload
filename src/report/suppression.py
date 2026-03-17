# HL data loading & cleaning — centralized HIPAA suppression module
"""Centralized small-cell suppression for HIPAA Safe Harbor compliance.

HIPAA Safe Harbor method requires suppressing small cell counts (<10) in
geographic subdivisions to prevent re-identification. This module provides
a single source of truth for all suppression logic across the pipeline.

Clinical rationale:
- Primary suppression only (no complementary suppression) per user decision
- Zero counts are displayed as-is (reveal no individual-level information)
- Threshold of 10 per CMS Cell Suppression Policy and WA DOH standards

References:
- CMS Cell Size Suppression Policy (2022)
- WA DOH Small Numbers Guidelines for Public Health Data
- HIPAA Privacy Rule §164.514(b)(2) (Safe Harbor method)

Usage:
    from src.report.suppression import suppress, flag_small_cell, DEFAULT_THRESHOLD

    # Suppress values for publication
    suppress(0)   # "0" (safe to display)
    suppress(5)   # "-" (suppressed)
    suppress(15)  # "15" (safe to display)

    # Flag values in quality reports
    flag_small_cell(5)   # "5 ⚠" (needs review before publication)
    flag_small_cell(15)  # "15" (safe to display)

    # Audit suppression impact
    audit_suppression([0, 3, 5, 12, 15])
    # {"total_cells": 5, "suppressed_cells": 2, "zero_cells": 1, "pct_suppressed": 40.0}
"""

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# HIPAA small-cell suppression threshold (counts 1-10 must be masked in publications)
DEFAULT_THRESHOLD = 10


# ---------------------------------------------------------------------------
# Core suppression functions
# ---------------------------------------------------------------------------


def suppress(value: int, threshold: int = DEFAULT_THRESHOLD) -> str:
    """Suppress small cell counts for HIPAA Safe Harbor compliance.

    Masks counts in the range [1, threshold] with "-" to prevent re-identification.
    Zero counts are displayed as-is (reveal no individual-level information).

    Clinical rationale: HIPAA Safe Harbor method requires suppressing small counts
    to prevent re-identification. Zero is safe to display because it reveals no
    individual exists in that cell (cannot re-identify from absence).

    Args:
        value: Count to evaluate for suppression
        threshold: Maximum count to suppress (default 10 per CMS/WA DOH standards)

    Returns:
        str: Suppression marker "-" if 1 <= value <= threshold,
             "0" if value == 0,
             str(value) otherwise

    Examples:
        >>> suppress(0)
        '0'
        >>> suppress(5)
        '-'
        >>> suppress(10)
        '-'
        >>> suppress(11)
        '11'
        >>> suppress(5, threshold=3)
        '5'
    """
    if value == 0:
        return "0"
    if 1 <= value <= threshold:
        return "-"
    return str(value)


def flag_small_cell(value: int, threshold: int = DEFAULT_THRESHOLD) -> str:
    """Flag counts that would need suppression if published under HIPAA Safe Harbor.

    Shows actual count with warning marker (⚠) for 1 ≤ value ≤ threshold.
    Used in quality reports to identify counts that must be masked before publication.

    Clinical rationale: Internal quality reports need to show actual counts for
    data validation, but must flag values that require suppression before external
    publication to prevent inadvertent disclosure.

    Args:
        value: Count to evaluate for flagging
        threshold: Maximum count to flag (default 10 per CMS/WA DOH standards)

    Returns:
        str: Value with "⚠" marker if 1 <= value <= threshold, otherwise str(value)

    Examples:
        >>> flag_small_cell(0)
        '0'
        >>> flag_small_cell(5)
        '5 ⚠'
        >>> flag_small_cell(10)
        '10 ⚠'
        >>> flag_small_cell(11)
        '11'
        >>> flag_small_cell(5, threshold=3)
        '5'
    """
    if 1 <= value <= threshold:
        return f"{value} ⚠"
    return str(value)


def audit_suppression(counts: list[int], threshold: int = DEFAULT_THRESHOLD) -> dict:
    """Calculate suppression impact metrics for a set of counts.

    Useful for logging suppression statistics during report generation to track
    how many cells are being masked and assess data utility.

    Args:
        counts: List of count values to evaluate
        threshold: Maximum count to consider suppressed (default 10)

    Returns:
        dict: Suppression metrics with keys:
            * "total_cells": Total number of cells
            * "suppressed_cells": Number of cells that would be suppressed (1-threshold)
            * "zero_cells": Number of zero-count cells
            * "pct_suppressed": Percentage of non-zero cells suppressed

    Examples:
        >>> audit_suppression([0, 3, 5, 12, 15])
        {'total_cells': 5, 'suppressed_cells': 2, 'zero_cells': 1, 'pct_suppressed': 50.0}
        >>> audit_suppression([0, 0, 0, 15, 20])
        {'total_cells': 5, 'suppressed_cells': 0, 'zero_cells': 3, 'pct_suppressed': 0.0}
    """
    total_cells = len(counts)
    zero_cells = sum(1 for c in counts if c == 0)
    suppressed_cells = sum(1 for c in counts if 1 <= c <= threshold)

    non_zero_cells = total_cells - zero_cells
    pct_suppressed = (suppressed_cells / non_zero_cells * 100) if non_zero_cells > 0 else 0.0

    return {
        "total_cells": total_cells,
        "suppressed_cells": suppressed_cells,
        "zero_cells": zero_cells,
        "pct_suppressed": round(pct_suppressed, 1),
    }


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

# Alias for backward compatibility with code that uses _suppress naming
_suppress = suppress
