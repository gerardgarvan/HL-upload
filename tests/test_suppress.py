"""Unit tests for _suppress (small-cell suppression for CSV)."""

from src.report.suppression import suppress as _suppress


def test_suppress_zero():
    assert _suppress(0) == "0"


def test_suppress_one():
    assert _suppress(1) == "-"


def test_suppress_ten():
    assert _suppress(10) == "-"


def test_suppress_eleven():
    assert _suppress(11) == "11"
