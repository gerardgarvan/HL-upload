# HL-EDA schema / manifest
"""Parse datastructure.txt manifest and verify files exist.

This module handles the 22-table PCORnet CDM manifest (datastructure.txt) that
lists expected CSV files for the HL cohort extract. It parses the manifest,
resolves table name aliases (LAB_RESULT → LAB_RESULT_CM), and verifies that
all expected files exist before conversion begins.

**Pipeline Position:** Phase 2 (Loading) - pre-conversion verification

**Input:** datastructure.txt manifest file

**Output:** List of table filenames and data_root path for validation

**Orchestrated by:** scripts/convert_all.py

**Key functions:**
- parse_datastructure(): Parse manifest file to extract table list
- resolve_table_name(): Map filename stems to CDM table names (handles LAB_RESULT alias)
- verify_files_exist(): Check that all tables exist on disk before conversion
"""

from pathlib import Path

# Alias mapping for filename stems that don't match PCORnet CDM table names.
# Datastructure manifest uses LAB_RESULT_Mailhot_V1.csv as filename, but the
# official PCORnet CDM table name is LAB_RESULT_CM (Common Model). This alias
# ensures consistent table naming throughout the pipeline.
# TODO(audit): Verify if other tables need aliases (TUMOR_REGISTRY naming?)
FILENAME_TO_TABLE_ALIAS: dict[str, str] = {"LAB_RESULT": "LAB_RESULT_CM"}


def resolve_table_name(stem: str) -> str:
    """Map filename stem to official PCORnet CDM table name.

    Strips the _Mailhot_V1 suffix from filenames (cohort-specific naming) and
    applies alias mapping to produce the canonical CDM table name. This ensures
    consistent table names across pipeline scripts regardless of source filename
    conventions.

    Clinical rationale: Consistent table naming is critical for downstream joins
    and cross-table integrity checks.

    Args:
        stem: Filename stem (e.g., "LAB_RESULT_Mailhot_V1" or "DEMOGRAPHIC_Mailhot_V1")

    Returns:
        str: Official CDM table name (e.g., "LAB_RESULT_CM" or "DEMOGRAPHIC")

    Example:
        >>> resolve_table_name("LAB_RESULT_Mailhot_V1")
        "LAB_RESULT_CM"
        >>> resolve_table_name("DEMOGRAPHIC_Mailhot_V1")
        "DEMOGRAPHIC"
    """
    table_part = stem.split("_Mailhot_V1")[0]
    return FILENAME_TO_TABLE_ALIAS.get(table_part, table_part)


def parse_datastructure(path: Path) -> tuple[str | None, list[str]]:
    """Parse datastructure.txt manifest to extract data root path and table filenames.

    The datastructure.txt file is a mixed-format manifest that contains:
    - One line starting with "/" indicating the data_root path
    - Multiple lines ending with ".csv" for table filenames (22 tables expected)
    - Comment lines starting with "#"
    - Blank lines (ignored)

    Clinical rationale: The manifest ensures all 22 PCORnet CDM tables are
    present before conversion, preventing silent missing-table errors that could
    compromise cohort completeness.

    Args:
        path: Path to datastructure.txt manifest file

    Returns:
        tuple: (data_root_path, list_of_csv_filenames)
            - data_root_path: String path from file (may be None if not found)
            - list_of_csv_filenames: List of .csv filenames (excludes valuesets.csv)

    Format assumptions:
        - Data root line: starts with "/" (absolute path)
        - Table lines: end with ".csv" (case-insensitive check for "valueset" to exclude)
        - Quotes stripped from all values (handles both single and double quotes)

    Example manifest content:
        # OneFlorida+ HL Cohort Extract
        /orange/mailhot/data/hl-cohort/
        DEMOGRAPHIC_Mailhot_V1.csv
        DIAGNOSIS_Mailhot_V1.csv
        ...
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
    """Verify each table file exists under data_root before conversion begins.

    Performs existence check for all table files to fail fast if any are missing,
    rather than failing partway through conversion. Accumulates all missing files
    and reports them in a single exception for debugging efficiency.

    Clinical rationale: Missing tables compromise cohort completeness and downstream
    analysis validity; fail-fast is safer than partial conversion.

    Args:
        data_root: Base directory containing CSV files (OneFlorida+ extract location)
        table_filenames: List of expected CSV filenames from datastructure.txt manifest

    Returns:
        None: Function returns normally if all files exist

    Raises:
        FileNotFoundError: If any table files are missing, with complete list of missing files
    """
    missing: list[str] = []
    for name in table_filenames:
        if not (data_root / name).exists():
            missing.append(name)
    if missing:
        raise FileNotFoundError(f"Missing table files under {data_root}: {missing}")
