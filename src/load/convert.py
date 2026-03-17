# HL data loading & cleaning — CSV-to-Parquet conversion module
"""Date detection, conversion, validation, and inventory functions.

Converts OneFlorida+ PCORnet CDM CSV files to Parquet with properly typed
date columns. Uses Polars exclusively (no pandas). This module handles the
critical Phase 2 step of converting raw string-typed CSVs to typed Parquet
files with automatic date format detection across 3 SAS date formats.

**Pipeline Position:** Phase 2 (Loading/Conversion)

**Input:** Raw CSV files from data_root (OneFlorida+ extracts with mixed date formats)

**Output:** Typed Parquet files with converted date columns + file_inventory.csv

**Orchestrated by:** scripts/convert_all.py

**Key functions:**
- detect_date_columns(): Auto-detect date columns using name heuristics + value sampling
- convert_date_column(): Convert single column with 10% failure threshold
- validate_date_range(): Check converted dates against [1900-01-01, 2026-12-31]
- convert_table(): Orchestrate single-table conversion pipeline
- write_inventory(): Write conversion metadata to CSV

**Known fragile areas:**
- Date format detection relies on regex sampling (DATETIME_RE, DATE9_RE, YYYYMMDD_RE)
- Mixed-format date columns can exceed 10% conversion failure threshold
- YYYYMMDD format requires name heuristic to avoid false positives on 8-digit codes
"""

import csv
import re
import time
from datetime import date
from pathlib import Path

import polars as pl

from src.load.schema import resolve_table_name

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Known date column names from PCORnet CDM specification (v6.0).
# Used as first-pass name heuristic before value sampling.
# Clinical rationale: PCORnet standardizes these names across all sites,
# so they're reliable indicators of date columns even when values are sparse.
KNOWN_DATE_COLS: set[str] = {
    "BIRTH_DATE",
    "ADMIT_DATE",
    "DISCHARGE_DATE",
    "DX_DATE",
    "PX_DATE",
    "MEASURE_DATE",
    "SPECIMEN_DATE",
    "RESULT_DATE",
    "RX_ORDER_DATE",
    "RX_START_DATE",
    "RX_END_DATE",
    "DEATH_DATE",
    "ONSET_DATE",
    "REPORT_DATE",
    "RESOLVE_DATE",
    "DISPENSE_DATE",
    "ENR_START_DATE",
    "ENR_END_DATE",
    "MEDADMIN_START_DATE",
    "MEDADMIN_STOP_DATE",
    "VX_RECORD_DATE",
    "VX_ADMIN_DATE",
    "VX_EXP_DATE",
    "ADDRESS_PERIOD_START",
    "ADDRESS_PERIOD_END",
    "DATE_OF_BIRTH",
    "DATE_OF_DIAGNOSIS",
}

# Regex to detect date-like column names when not in KNOWN_DATE_COLS
DATE_NAME_RE = re.compile(r"(_DATE|_DT)$|^DATE_|^DT_|_DATE_", re.IGNORECASE)

# SAS date format regexes for value sampling
# OneFlorida+ exports dates in 3 formats depending on source system:
DATE9_RE = re.compile(r"^\d{2}[A-Za-z]{3}\d{4}$")  # 01JAN2020 (SAS DATE9. format)
DATETIME_RE = re.compile(r"^\d{2}[A-Za-z]{3}\d{4}:\d{2}:\d{2}:\d{2}$")  # 01JAN2020:14:30:00 (SAS DATETIME format)
YYYYMMDD_RE = re.compile(r"^\d{8}$")  # 20200101 (8-digit integer as string, tumor registry common)

# Plausibility bounds for converted dates (informational only, doesn't reject values)
# Lower bound: 1900-01-01 (PCORnet minimum, pre-1900 birth dates masked to this value)
# Upper bound: 2026-12-31 (conservative future cutoff beyond extract date 2025-09-15)
# TODO(audit): Are there legitimate 1900-01-01 birth dates or are they all masked values?
MIN_DATE = date(1900, 1, 1)
MAX_DATE = date(2026, 12, 31)

# Fieldnames for file_inventory.csv (conversion metadata report)
# Tracks per-table conversion success/failure and date column conversion outcomes
INVENTORY_FIELDS = [
    "table_name",
    "csv_file",
    "parquet_file",
    "csv_rows",
    "parquet_rows",
    "csv_bytes",
    "parquet_bytes",
    "date_columns_found",
    "date_columns_converted",
    "date_columns_kept_string",
    "elapsed_seconds",
    "status",
]

# ---------------------------------------------------------------------------
# Date detection
# ---------------------------------------------------------------------------


def detect_date_columns(df: pl.DataFrame, sample_size: int = 200) -> dict[str, str]:
    """Auto-detect date columns using name heuristics and value sampling.

    Two-phase detection approach to handle OneFlorida+'s mixed SAS date formats:
      A) Name heuristic: column in KNOWN_DATE_COLS or matches DATE_NAME_RE pattern
      B) Value sampling: regex match first N non-null values against 3 format patterns

    Adaptive thresholds based on name confidence:
      - 30% match required when name heuristic matches (high confidence)
      - 50% match required for value-only detection (avoid false positives)
      - YYYYMMDD format requires name match (prevents false positives on 8-digit IDs)

    Known fragile area: Mixed-format date columns (e.g., DATE9. + YYYYMMDD in same
    column) may fail to detect or may choose dominant format incorrectly.

    Clinical rationale: Accurate date detection is critical for temporal analyses
    (treatment timelines, enrollment periods, survival calculations). False negatives
    keep dates as strings (safe but inconvenient); false positives corrupt data.

    Args:
        df: Polars DataFrame with string-typed columns to analyze
        sample_size: Number of non-null values to sample per column (default 200)

    Returns:
        dict: Mapping of {column_name: strftime_format_string} for detected date columns
            Possible formats: "%d%b%Y:%H:%M:%S", "%d%b%Y", "%Y%m%d"

    Side effects:
        None (read-only analysis of DataFrame)

    Example:
        >>> df = pl.DataFrame({"DX_DATE": ["01JAN2020", "15FEB2020"], "ID": ["1", "2"]})
        >>> detect_date_columns(df)
        {"DX_DATE": "%d%b%Y"}
    """
    detected: dict[str, str] = {}

    for col_name in df.columns:
        if df[col_name].dtype != pl.String:
            continue

        name_match = col_name in KNOWN_DATE_COLS or bool(DATE_NAME_RE.search(col_name))

        non_null = df[col_name].drop_nulls().filter(df[col_name].drop_nulls() != "")
        if non_null.len() == 0:
            continue

        sample = non_null.head(min(sample_size, non_null.len())).to_list()
        n = len(sample)
        if n == 0:
            continue

        dt_matches = sum(1 for v in sample if DATETIME_RE.match(str(v)))
        d9_matches = sum(1 for v in sample if DATE9_RE.match(str(v)))
        ym_matches = sum(1 for v in sample if YYYYMMDD_RE.match(str(v)))

        val_threshold = 0.3 if name_match else 0.5

        if dt_matches / n > val_threshold:
            detected[col_name] = "%d%b%Y:%H:%M:%S"
        elif d9_matches / n > val_threshold:
            detected[col_name] = "%d%b%Y"
        elif ym_matches / n > val_threshold and name_match:
            detected[col_name] = "%Y%m%d"
        elif name_match and (d9_matches + dt_matches + ym_matches) / n > val_threshold:
            counts = {
                "%d%b%Y:%H:%M:%S": dt_matches,
                "%d%b%Y": d9_matches,
                "%Y%m%d": ym_matches,
            }
            detected[col_name] = max(counts, key=counts.get)  # type: ignore[arg-type]

    return detected


# ---------------------------------------------------------------------------
# Date conversion
# ---------------------------------------------------------------------------


def convert_date_column(df: pl.DataFrame, col: str, fmt: str) -> tuple[pl.DataFrame, dict]:
    """Convert a single string column to date/datetime with 10% failure threshold.

    Attempts strict=False parsing which converts parse failures to null. If more
    than 10% of non-null, non-empty values fail to parse, the column is kept as
    string (safety over convenience). Otherwise, the column is replaced in-place
    with the typed date/datetime column.

    Known fragile area: Mixed-format date columns (e.g., 01JAN2020 + 20200101 in
    same column) will exceed the 10% threshold and be kept as string. This is
    intentional conservative behavior.

    Clinical rationale: Incorrect date conversions silently corrupt temporal
    analyses. The 10% threshold balances format flexibility with data integrity—
    occasional bad values are acceptable, but systematic parse failures indicate
    format mismatch.

    Args:
        df: Polars DataFrame containing the column to convert
        col: Column name to convert (must be String dtype)
        fmt: strftime format string (e.g., "%d%b%Y", "%d%b%Y:%H:%M:%S", "%Y%m%d")

    Returns:
        tuple: (modified_df, stats_dict)
            - modified_df: DataFrame with column converted (or unchanged if kept as string)
            - stats_dict: Conversion statistics with keys:
                * "col": column name
                * "action": "converted" | "kept_as_string" | "skipped"
                * "reason": explanation if skipped/kept
                * "new_nulls": count of parse failures (if converted)
                * "failures": count of parse failures (if kept as string)

    Side effects:
        Modifies DataFrame by replacing string column with typed date/datetime column
        if conversion succeeds. No backup copy is kept (destructive operation).
    """
    series = df[col]
    non_null_non_empty = series.drop_nulls().filter(series.drop_nulls() != "")
    denominator = non_null_non_empty.len()

    if denominator == 0:
        return df, {"col": col, "action": "skipped", "reason": "all null/empty"}

    original_nulls = series.null_count()

    if ":%H:%M:%S" in fmt:
        converted = df.with_columns(pl.col(col).str.to_datetime(fmt, strict=False))
    else:
        converted = df.with_columns(pl.col(col).str.to_date(fmt, strict=False))

    new_nulls = converted[col].null_count() - original_nulls

    if new_nulls / denominator > 0.10:
        pct = new_nulls / denominator
        return df, {
            "col": col,
            "action": "kept_as_string",
            "reason": f"{new_nulls}/{denominator} ({pct:.1%}) failed to parse",
            "failures": new_nulls,
        }

    return converted, {
        "col": col,
        "action": "converted",
        "format": fmt,
        "new_nulls": new_nulls,
    }


# ---------------------------------------------------------------------------
# Date range validation
# ---------------------------------------------------------------------------


def validate_date_range(df: pl.DataFrame, col: str) -> dict:
    """Validate converted date/datetime column against [1900-01-01, 2026-12-31].

    Informational validation only—reports out-of-range values but does NOT filter
    or modify them. Out-of-range dates may be legitimate (e.g., 1900-01-01 is
    PCORnet's masked value for privacy-protected birth dates) or may indicate
    conversion errors.

    Clinical rationale: Date plausibility checks catch conversion errors (e.g.,
    YYYYMMDD interpreted as MMDDYYYY) without silently dropping potentially valid
    masked or edge-case dates.

    Args:
        df: Polars DataFrame with converted date column
        col: Column name to validate (must be Date or Datetime dtype)

    Returns:
        dict: Validation results with keys:
            * "col": column name
            * "min": minimum date value as string
            * "max": maximum date value as string
            * "out_of_range": count of values outside [MIN_DATE, MAX_DATE]
            * "skipped": True if column was wrong dtype (dict contains "reason")

    Side effects:
        None (read-only analysis)
    """
    dtype = df[col].dtype

    if dtype == pl.Date:
        out_of_range = df.filter(pl.col(col).is_not_null() & ((pl.col(col) < MIN_DATE) | (pl.col(col) > MAX_DATE))).height
        min_val = df[col].min()
        max_val = df[col].max()
    elif dtype in (pl.Datetime, pl.Datetime("us"), pl.Datetime("ns"), pl.Datetime("ms")):
        date_cast = pl.col(col).cast(pl.Date)
        out_of_range = df.filter(pl.col(col).is_not_null() & ((date_cast < MIN_DATE) | (date_cast > MAX_DATE))).height
        min_val = df[col].min()
        max_val = df[col].max()
    else:
        return {"col": col, "skipped": True, "reason": f"dtype {dtype}"}

    return {
        "col": col,
        "min": str(min_val),
        "max": str(max_val),
        "out_of_range": out_of_range,
    }


# ---------------------------------------------------------------------------
# Single-table conversion
# ---------------------------------------------------------------------------


def convert_table(csv_path: Path, parquet_dir: Path) -> dict:
    """Orchestrate single-table CSV-to-Parquet conversion pipeline.

    Complete workflow:
    1. Read CSV with infer_schema=False (all strings) using utf8-lossy encoding
    2. Detect date columns using name + value heuristics
    3. Convert each date column with 10% failure threshold
    4. Validate converted dates against plausibility range
    5. Write Parquet with snappy compression
    6. Roundtrip verification (read back to confirm row count)
    7. Print detailed conversion report to stdout
    8. Return inventory record dict for file_inventory.csv

    Clinical rationale: Roundtrip verification ensures no silent row loss during
    conversion, which would compromise cohort completeness.

    Args:
        csv_path: Path to source CSV file (e.g., DEMOGRAPHIC_Mailhot_V1.csv)
        parquet_dir: Output directory for Parquet file

    Returns:
        dict: Inventory record with keys matching INVENTORY_FIELDS constant
            Includes table_name, row counts, byte sizes, date conversion summary,
            elapsed time, and status ("ok" | "empty" | "MISMATCH: ...")

    Side effects:
        - Writes Parquet file to parquet_dir with same stem as CSV
        - Prints detailed conversion report to stdout (row count, size, date details)
        - Prints warnings for kept-as-string columns, out-of-range dates, row mismatches
    """
    t0 = time.time()
    csv_bytes = csv_path.stat().st_size

    stem = csv_path.stem  # e.g. DEMOGRAPHIC_Mailhot_V1
    table_name = resolve_table_name(stem)  # e.g. DEMOGRAPHIC or LAB_RESULT_CM
    parquet_filename = stem + ".parquet"

    df = pl.read_csv(
        csv_path,
        infer_schema=False,
        encoding="utf8-lossy",
    )

    if df.height == 0:
        elapsed = round(time.time() - t0, 2)
        print(f"  [SKIP] {table_name} — empty table (0 rows)")
        return {
            "table_name": table_name,
            "csv_file": csv_path.name,
            "parquet_file": "",
            "csv_rows": 0,
            "parquet_rows": 0,
            "csv_bytes": csv_bytes,
            "parquet_bytes": 0,
            "date_columns_found": 0,
            "date_columns_converted": 0,
            "date_columns_kept_string": 0,
            "elapsed_seconds": elapsed,
            "status": "empty",
        }

    csv_rows = df.height

    date_cols = detect_date_columns(df)
    converted_count = 0
    kept_string_count = 0
    date_details: list[str] = []

    for col, fmt in date_cols.items():
        df, stats = convert_date_column(df, col, fmt)

        if stats["action"] == "converted":
            converted_count += 1
            vr = validate_date_range(df, col)
            oor = vr.get("out_of_range", 0)
            detail = f"    {col}: {fmt} -> converted"
            if stats["new_nulls"]:
                detail += f" ({stats['new_nulls']} new nulls)"
            if oor:
                detail += f" [{oor} out of range]"
            date_details.append(detail)
            if oor:
                print(f"  [RANGE] {col}: min={vr['min']}, max={vr['max']}, out_of_range={oor}")
        elif stats["action"] == "kept_as_string":
            kept_string_count += 1
            date_details.append(f"    {col}: {fmt} -> KEPT AS STRING ({stats['reason']})")
            print(f"  [WARN] {col}: kept as string — {stats['reason']}")
        else:
            date_details.append(f"    {col}: skipped ({stats.get('reason', 'n/a')})")

    parquet_path = parquet_dir / parquet_filename
    df.write_parquet(parquet_path, compression="snappy")

    roundtrip = pl.read_parquet(parquet_path)
    parquet_rows = roundtrip.height
    parquet_bytes = parquet_path.stat().st_size

    if csv_rows != parquet_rows:
        print(f"  [WARN] Row count mismatch: CSV={csv_rows:,}, Parquet={parquet_rows:,}")

    elapsed = round(time.time() - t0, 2)

    print(f"  Rows: {csv_rows:,}")
    print(f"  CSV size: {csv_bytes / 1024 / 1024:.1f} MB")
    print(f"  Parquet size: {parquet_bytes / 1024 / 1024:.1f} MB")
    print(f"  Date columns found: {len(date_cols)}")
    for d in date_details:
        print(d)
    print(f"  Converted: {converted_count}  |  Kept as string: {kept_string_count}")
    print(f"  Elapsed: {elapsed:.1f}s")

    return {
        "table_name": table_name,
        "csv_file": csv_path.name,
        "parquet_file": parquet_filename,
        "csv_rows": csv_rows,
        "parquet_rows": parquet_rows,
        "csv_bytes": csv_bytes,
        "parquet_bytes": parquet_bytes,
        "date_columns_found": len(date_cols),
        "date_columns_converted": converted_count,
        "date_columns_kept_string": kept_string_count,
        "elapsed_seconds": elapsed,
        "status": "ok" if csv_rows == parquet_rows else f"MISMATCH: CSV={csv_rows}, Parquet={parquet_rows}",
    }


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def write_inventory(records: list[dict], output_path: Path) -> None:
    """Write file_inventory.csv with per-table conversion metadata.

    Creates CSV file with columns matching INVENTORY_FIELDS constant. Used for
    conversion audit trail and baseline documentation. Records include table names,
    row/byte counts, date conversion summary, and status flags.

    Clinical rationale: Conversion audit trail enables verification that all
    expected tables were converted and no data was lost in the process.

    Args:
        records: List of inventory dicts from convert_table() calls
        output_path: Path for output CSV file (typically parquet_dir/file_inventory.csv)

    Returns:
        None

    Side effects:
        - Writes CSV file to output_path
        - Prints confirmation message to stdout with file path
    """
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INVENTORY_FIELDS)
        writer.writeheader()
        writer.writerows(records)
    print(f"\n  Inventory written to {output_path}")
