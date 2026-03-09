"""Unit tests for flag_small_cell (small-cell suppression for markdown)."""

from src.validate.structural import flag_small_cell


def test_flag_small_cell_zero():
    assert flag_small_cell(0) == "0"


def test_flag_small_cell_one():
    assert flag_small_cell(1) == "1 ⚠"


def test_flag_small_cell_ten():
    assert flag_small_cell(10) == "10 ⚠"


def test_flag_small_cell_eleven():
    assert flag_small_cell(11) == "11"


def test_flag_small_cell_large():
    assert flag_small_cell(100) == "100"
