# HL data loading & cleaning — CSV-to-Parquet conversion module
"""Date detection, conversion, validation, and inventory functions.

Converts OneFlorida+ PCORnet CDM CSV files to Parquet with properly typed
date columns.  Uses Polars exclusively (no pandas).
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

KNOWN_DATE_COLS: set[str] = {
    "BIRTH_DATE", "ADMIT_DATE", "DISCHARGE_DATE", "DX_DATE", "PX_DATE",
    "MEASURE_DATE", "SPECIMEN_DATE", "RESULT_DATE", "RX_ORDER_DATE",
    "RX_START_DATE", "RX_END_DATE", "DEATH_DATE", "ONSET_DATE",
    "REPORT_DATE", "RESOLVE_DATE", "DISPENSE_DATE", "ENR_START_DATE",
    "ENR_END_DATE", "MEDADMIN_START_DATE", "MEDADMIN_STOP_DATE",
    "VX_RECORD_DATE", "VX_ADMIN_DATE", "VX_EXP_DATE",
    "ADDRESS_PERIOD_START", "ADDRESS_PERIOD_END",
    "DATE_OF_BIRTH", "DATE_OF_DIAGNOSIS",
}

DATE_NAME_RE = re.compile(r"(_DATE|_DT)$|^DATE_|^DT_|_DATE_", re.IGNORECASE)

DATE9_RE = re.compile(r"^\d{2}[A-Za-z]{3}\d{4}$")          # 01JAN2020
DATETIME_RE = re.compile(r"^\d{2}[A-Za-z]{3}\d{4}:\d{2}:\d{2}:\d{2}$")  # 01JAN2020:14:30:00
YYYYMMDD_RE = re.compile(r"^\d{8}$")                        # 20200101

MIN_DATE = date(1900, 1, 1)
MAX_DATE = date(2026, 12, 31)

INVENTORY_FIELDS = [
    "table_name", "csv_file", "parquet_file",
    "csv_rows", "parquet_rows", "csv_bytes", "parquet_bytes",
    "date_columns_found", "date_columns_converted",
    "date_columns_kept_string", "elapsed_seconds", "status",
]

# ---------------------------------------------------------------------------
# Date detection
# ---------------------------------------------------------------------------

def detect_date_columns(
    df: pl.DataFrame, sample_size: int = 200
) -> dict[str, str]:
    """Auto-detect date columns using name heuristics and value sampling.

    Two-phase approach:
      A) Name heuristic — column in KNOWN_DATE_COLS or matches DATE_NAME_RE.
      B) Value sampling — regex match against DATETIME, DATE9., YYYYMMDD.

    Lower match threshold (30 %) when name also matches; 50 % for value-only.
    YYYYMMDD accepted only when name heuristic also matches (avoids false
    positives on 8-digit codes like SITE_CODE or HISTOLOGY).

    Returns ``{column_name: format_string}`` dict.
    """
    detected: dict[str, str] = {}

    for col_name in df.columns:
        if df[col_name].dtype != pl.String:
            continue

        name_match = (
            col_name in KNOWN_DATE_COLS
            or bool(DATE_NAME_RE.search(col_name))
        )

        non_null = df[col_name].drop_nulls().filter(
            df[col_name].drop_nulls() != ""
        )
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

def convert_date_column(
    df: pl.DataFrame, col: str, fmt: str
) -> tuple[pl.DataFrame, dict]:
    """Convert a single string column to date/datetime with 10 % threshold.

    If >10 % of non-null, non-empty values fail to parse the column is kept
    as string.  Otherwise the column is replaced in-place (no raw copies).

    Returns ``(df, stats_dict)``.
    """
    series = df[col]
    non_null_non_empty = series.drop_nulls().filter(series.drop_nulls() != "")
    denominator = non_null_non_empty.len()

    if denominator == 0:
        return df, {"col": col, "action": "skipped", "reason": "all null/empty"}

    original_nulls = series.null_count()

    if ":%H:%M:%S" in fmt:
        converted = df.with_columns(
            pl.col(col).str.to_datetime(fmt, strict=False)
        )
    else:
        converted = df.with_columns(
            pl.col(col).str.to_date(fmt, strict=False)
        )

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

    Informational only — flags but preserves all values.
    """
    dtype = df[col].dtype

    if dtype == pl.Date:
        out_of_range = df.filter(
            pl.col(col).is_not_null()
            & ((pl.col(col) < MIN_DATE) | (pl.col(col) > MAX_DATE))
        ).height
        min_val = df[col].min()
        max_val = df[col].max()
    elif dtype in (pl.Datetime, pl.Datetime("us"), pl.Datetime("ns"), pl.Datetime("ms")):
        date_cast = pl.col(col).cast(pl.Date)
        out_of_range = df.filter(
            pl.col(col).is_not_null()
            & ((date_cast < MIN_DATE) | (date_cast > MAX_DATE))
        ).height
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
    """Orchestrate single-table conversion. Returns an inventory record dict."""
    t0 = time.time()
    csv_bytes = csv_path.stat().st_size

    stem = csv_path.stem                       # e.g. DEMOGRAPHIC_Mailhot_V1
    table_name = resolve_table_name(stem)      # e.g. DEMOGRAPHIC or LAB_RESULT_CM
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
        print(
            f"  [WARN] Row count mismatch: CSV={csv_rows:,}, Parquet={parquet_rows:,}"
        )

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
    """Write file_inventory.csv with per-table conversion metadata."""
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INVENTORY_FIELDS)
        writer.writeheader()
        writer.writerows(records)
    print(f"\n  Inventory written to {output_path}")
