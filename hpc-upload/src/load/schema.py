# HL-EDA schema / manifest
"""Parse datastructure.txt manifest and verify files exist."""

from pathlib import Path


def parse_datastructure(path: Path) -> tuple[str | None, list[str]]:
    """Parse datastructure.txt for data root path and table filenames.

    Skips # and blank lines. Path lines start with /. .csv lines (excluding
    valuesets.csv) are table files. Strips surrounding quotes.

    Returns:
        (data_root_from_file, list_of_table_filenames)
        data_root_from_file may be None if not found in file.
    """
    data_root: str | None = None
    tables: list[str] = []

    text = path.read_text()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        s = line.strip("'\"").strip()
        if s.startswith("/"):
            data_root = s
        elif s.endswith(".csv") and "valueset" not in s.lower():
            tables.append(s)

    return data_root, tables


def verify_files_exist(data_root: Path, table_filenames: list[str]) -> None:
    """Verify each table file exists under data_root.

    Raises:
        FileNotFoundError: with message listing any missing files.
    """
    missing: list[str] = []
    for name in table_filenames:
        if not (data_root / name).exists():
            missing.append(name)
    if missing:
        raise FileNotFoundError(
            f"Missing table files under {data_root}: {missing}"
        )
