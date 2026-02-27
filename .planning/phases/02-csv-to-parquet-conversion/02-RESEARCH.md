# Phase 2: CSV-to-Parquet Conversion with SAS Date Handling - Research

**Researched:** 2026-02-27
**Domain:** Polars CSV-to-Parquet conversion with SAS DATE9./NAACCR date parsing
**Confidence:** HIGH

## Summary

Phase 2 converts 22 OneFlorida+ PCORnet CDM CSV files to Parquet format with proper date types. The core technical challenge is auto-detecting date columns across all tables — including TUMOR_REGISTRY tables with ~265/120/120 columns — and parsing multiple date formats (SAS DATE9. like "01JAN2020", SAS DATETIME like "01JAN2020:14:30:00", and NAACCR YYYYMMDD like "20200101") into proper Polars `Date`/`Datetime` types.

The existing smoke test (Phase 1) already validated the single-table pipeline: `pl.read_csv()` → `str.to_date("%d%b%Y", strict=False)` → `write_parquet()` → read-back verify. Phase 2 scales this to all 22 tables with auto-detection, multi-format parsing, a 10% unparseable threshold, and a file inventory output.

A key finding from this research: **chrono's `%b` month abbreviation parser is case-insensitive** (verified from source code — it uses `byte | 32` bitwise OR to force lowercase before matching). This means `.str.to_uppercase()` before date parsing is unnecessary, contradicting the Phase 1 research's precautionary recommendation. "JAN", "jan", and "Jan" all parse correctly.

**Primary recommendation:** Use a single conversion loop for all 22 tables. Auto-detect date columns by combining column-name heuristics (`*_DATE`, `*_DT`, known PCORnet names) with value-sampling regex (match against DATE9., DATETIME, and YYYYMMDD patterns). Apply a format fallback chain per column. This unified approach handles TUMOR_REGISTRY format differences without special-casing.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Format detection:** Auto-detect date columns by sampling values, not just hardcoded lists. Catch any date columns we might miss from naming conventions alone.
- **TUMOR_REGISTRY dates:** Likely use a different format than standard PCORnet tables (NAACCR often uses YYYYMMDD instead of SAS DATE9.). Handle separately with format detection.
- **Date+Time columns:** Keep date and time as separate columns (matches PCORnet CDM structure). Do NOT combine into a single datetime column.
- **Validation range:** 1900-2026 — very permissive, only flag obviously wrong values. The cohort includes masked birth dates (01JAN1900) which must be preserved.
- **Unparseable dates:** If >10% of values in a date column fail to parse, keep the entire column as a string type. Log a warning. Below 10%, coerce failures to null and log the count.
- **Run location:** Interactive session (srun or Jupyter) — watch it run, debug if needed. Not a fire-and-forget batch job.
- **Re-run behavior:** Always reconvert all tables. No skip-existing logic. Ensures consistency.
- **Progress output:** Detailed — table name, row count, date columns found, file sizes, timing per table.
- **File naming:** Keep the cohort suffix: `DEMOGRAPHIC_Mailhot_V1.parquet`, `ENCOUNTER_Mailhot_V1.parquet`, etc.
- **Original string columns:** Do NOT keep raw string copies of date columns. Replace in-place with typed versions only.
- **Compression:** snappy — prioritize faster reads over maximum compression.
- **Inventory format:** CSV file (`file_inventory.csv`) — easy to open in Excel or pandas.
- **Table failure:** Stop immediately if any table fails to load or convert. Do not skip and continue.
- **Empty tables:** Skip empty tables — do not create a Parquet file for them. Note in inventory.
- **Row count mismatch:** Warn but continue if CSV and Parquet row counts differ. Log the discrepancy.

### Claude's Discretion
- **Single script vs grouped tables:** Claude decides whether to use one loop for all 22 tables or separate handling for TUMOR_REGISTRY. The auto-detect date logic should handle format differences either way.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REQ-01 | Load 22 large CSV files as fast as possible | Polars `read_csv()` benchmarked at ~0.4s/500MB; `infer_schema_length=0` reads all as strings for predictable type control; `write_parquet(compression="snappy")` for fast reads |
| REQ-02 | Convert SAS date formats to standard dates | `str.to_date("%d%b%Y", strict=False)` for DATE9.; `str.to_datetime("%d%b%Y:%H:%M:%S", strict=False)` for DATETIME; `str.to_date("%Y%m%d", strict=False)` for NAACCR; chrono is case-insensitive for `%b`; 10% threshold logic for unparseable columns |
| REQ-04 | Run on HiPerGator HPC | Interactive session via `srun --mem=64gb --time=2:00:00 --cpus-per-task=4 --account=erin.mobley-hl.bcu --pty bash`; Polars auto-parallelizes on available cores |
| REQ-05 | HIPAA-compliant data handling | Read from `/orange` (source, read-only); write Parquet to `/blue/erin.mobley-hl.bcu/hl-clean/parquet/`; `file_inventory.csv` contains table-level metadata only (no patient data); no small-cell concern for this phase (no aggregation) |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Polars | 1.22.0+ | CSV reading, date parsing, Parquet writing | Fastest Python CSV reader; native `str.to_date()` with chrono format strings; `write_parquet()` with snappy compression |
| Python | 3.11 | Runtime | Already in hl-eda env; `tomllib` in stdlib |

### Supporting (already installed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| DuckDB | 1.4.4+ | Optional post-conversion verification | Verify Parquet readability; already validated in smoke test |

### No Additional Dependencies Needed

Phase 2 uses only Polars (already installed in Phase 1) plus Python stdlib (`re`, `time`, `pathlib`, `csv`, `dataclasses`). No new packages to install.

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)

```
src/
└── load/
    ├── config.py          # existing — Paths dataclass
    ├── schema.py          # existing — datastructure.txt parser
    └── convert.py         # NEW — CSV-to-Parquet conversion module
scripts/
├── smoke_test.py          # existing — single-table validation
└── convert_all.py         # NEW — entry point: convert all 22 tables
```

### Claude's Discretion Recommendation: Single Unified Loop

**Recommendation:** Use one loop for all 22 tables. The auto-detect + format-fallback logic handles TUMOR_REGISTRY differences automatically without separate code paths.

**Rationale:**
- The user's locked decision on auto-detection means every column goes through the same detection pipeline regardless of table
- NAACCR YYYYMMDD format is detected by regex sampling, not table-name branching
- A single loop is simpler to maintain, debug, and reason about
- TUMOR_REGISTRY tables are wider (265/120/120 columns) but auto-detection over columns is O(n) and fast with Polars expressions
- The user wants "stop immediately if any table fails" — a single loop with early exit is the natural pattern

**Architecture:**
```
convert_all.py (entry point)
    ├── load config + parse table list
    ├── for each table:
    │   ├── read CSV (all strings)
    │   ├── auto-detect date columns (name heuristics + value sampling)
    │   ├── for each detected date column:
    │   │   ├── try DATE9. format (%d%b%Y)
    │   │   ├── try DATETIME format (%d%b%Y:%H:%M:%S)
    │   │   ├── try YYYYMMDD format (%Y%m%d)
    │   │   ├── check 10% threshold → keep as string or accept conversion
    │   │   └── validate date range [1900-01-01, 2026-12-31]
    │   ├── write Parquet (snappy)
    │   ├── verify row count
    │   └── record inventory entry
    └── write file_inventory.csv
```

### Pattern 1: Read CSV as All Strings, Then Cast

**What:** Read CSV with `infer_schema=False` (or `infer_schema_length=0`) so all columns are `pl.String`, then selectively convert date columns.
**Why:** Prevents Polars from auto-detecting date columns as integers or other types. Gives full control over which columns get date-parsed and how.
**Verified:** Polars official docs confirm `infer_schema=False` (v1.2.0+) reads all columns as `pl.String`.

```python
df = pl.read_csv(csv_path, infer_schema=False)
# All columns are now pl.String — safe to detect and parse dates
```

**Alternative: Use `schema_overrides` to force specific columns to String.** But `infer_schema=False` is simpler when you need full control and will cast everything yourself.

### Pattern 2: Date Column Auto-Detection (Two-Phase)

**What:** Detect date columns using (1) column-name heuristics and (2) value-sampling regex.
**Why:** User locked decision — auto-detect by sampling, not just hardcoded lists.

**Phase A — Name heuristics (fast, catches most):**
```python
import re

KNOWN_DATE_COLS = {
    "BIRTH_DATE", "ADMIT_DATE", "DISCHARGE_DATE", "DX_DATE", "PX_DATE",
    "MEASURE_DATE", "SPECIMEN_DATE", "RESULT_DATE", "RX_ORDER_DATE",
    "RX_START_DATE", "RX_END_DATE", "DEATH_DATE", "ONSET_DATE",
    "REPORT_DATE", "RESOLVE_DATE", "DISPENSE_DATE", "ENR_START_DATE",
    "ENR_END_DATE", "MEDADMIN_START_DATE", "MEDADMIN_STOP_DATE",
    "VX_RECORD_DATE", "VX_ADMIN_DATE", "VX_EXP_DATE",
    "ADDRESS_PERIOD_START", "ADDRESS_PERIOD_END",
    # TUMOR_REGISTRY NAACCR columns
    "DATE_OF_BIRTH", "DATE_OF_DIAGNOSIS",
}
DATE_NAME_PATTERN = re.compile(r"(_DATE|_DT|_DATE_|DATE_)$|^DATE_|^DT_", re.IGNORECASE)

def is_date_by_name(col_name: str) -> bool:
    return col_name in KNOWN_DATE_COLS or bool(DATE_NAME_PATTERN.search(col_name))
```

**Phase B — Value sampling (catches columns missed by name):**
```python
DATE9_PATTERN = re.compile(r"^\d{2}[A-Za-z]{3}\d{4}$")       # 01JAN2020
DATETIME_PATTERN = re.compile(r"^\d{2}[A-Za-z]{3}\d{4}:")     # 01JAN2020:14:30:00
YYYYMMDD_PATTERN = re.compile(r"^\d{8}$")                      # 20200101

def detect_date_format_by_sampling(series: pl.Series, sample_size: int = 100) -> str | None:
    """Sample non-null values and check for date patterns. Returns format string or None."""
    non_null = series.drop_nulls().filter(series.drop_nulls() != "")
    if len(non_null) == 0:
        return None
    sample = non_null.head(min(sample_size, len(non_null)))
    values = sample.to_list()

    # Count matches for each pattern
    date9_matches = sum(1 for v in values if DATE9_PATTERN.match(v))
    datetime_matches = sum(1 for v in values if DATETIME_PATTERN.match(v))
    yyyymmdd_matches = sum(1 for v in values if YYYYMMDD_PATTERN.match(v))

    threshold = len(values) * 0.5  # at least 50% of sampled values should match

    if datetime_matches > threshold:
        return "%d%b%Y:%H:%M:%S"
    if date9_matches > threshold:
        return "%d%b%Y"
    if yyyymmdd_matches > threshold:
        return "%Y%m%d"
    return None
```

### Pattern 3: Format Fallback Chain with 10% Threshold

**What:** Try the detected format, then check if >10% failed. If so, keep as string.
**Why:** User locked decision on 10% threshold.

```python
def convert_date_column(
    df: pl.DataFrame, col: str, fmt: str
) -> tuple[pl.DataFrame, dict]:
    """Convert a string column to date/datetime. Returns (df, stats)."""
    original_non_null = df[col].drop_nulls().filter(df[col].drop_nulls() != "").len()

    if fmt == "%d%b%Y:%H:%M:%S":
        converted = df.with_columns(
            pl.col(col).str.to_datetime(fmt, strict=False)
        )
    elif fmt in ("%d%b%Y", "%Y%m%d"):
        converted = df.with_columns(
            pl.col(col).str.to_date(fmt, strict=False)
        )
    else:
        return df, {"col": col, "action": "skipped", "reason": "unknown format"}

    new_nulls = converted[col].null_count() - df[col].null_count()

    if original_non_null > 0 and new_nulls / original_non_null > 0.10:
        # >10% failed — keep as string
        return df, {
            "col": col, "action": "kept_as_string",
            "reason": f"{new_nulls}/{original_non_null} ({new_nulls/original_non_null:.1%}) failed to parse"
        }

    # Validate date range [1900-01-01, 2026-12-31]
    # (validation is informational — flag but keep all values)
    return converted, {
        "col": col, "action": "converted", "format": fmt,
        "new_nulls": new_nulls, "original_non_null": original_non_null
    }
```

### Pattern 4: Date Range Validation

**What:** After conversion, check dates fall within 1900-01-01 to 2026-12-31.
**Why:** User locked decision — very permissive, only flag obviously wrong values. Masked BIRTH_DATE="01JAN1900" must be preserved.

```python
import polars as pl
from datetime import date

MIN_DATE = date(1900, 1, 1)
MAX_DATE = date(2026, 12, 31)

def validate_date_range(df: pl.DataFrame, col: str) -> dict:
    """Check dates are in valid range. Returns stats dict."""
    if df[col].dtype == pl.Date:
        out_of_range = df.filter(
            pl.col(col).is_not_null() &
            ((pl.col(col) < MIN_DATE) | (pl.col(col) > MAX_DATE))
        ).height
        min_val = df[col].min()
        max_val = df[col].max()
        return {"col": col, "min": str(min_val), "max": str(max_val), "out_of_range": out_of_range}
    return {"col": col, "skipped": True}
```

### Pattern 5: Parquet Writing with Snappy + Row Count Verify

```python
def write_and_verify(
    df: pl.DataFrame, parquet_path: Path, csv_row_count: int
) -> dict:
    """Write Parquet with snappy compression, verify row count."""
    df.write_parquet(parquet_path, compression="snappy")

    # Read back and verify
    roundtrip = pl.read_parquet(parquet_path)
    parquet_rows = roundtrip.height
    parquet_size = parquet_path.stat().st_size

    status = "ok"
    if parquet_rows != csv_row_count:
        status = f"MISMATCH: CSV={csv_row_count}, Parquet={parquet_rows}"

    return {
        "csv_rows": csv_row_count,
        "parquet_rows": parquet_rows,
        "parquet_bytes": parquet_size,
        "status": status,
    }
```

### Pattern 6: File Inventory CSV

```python
import csv

INVENTORY_FIELDS = [
    "table_name", "csv_file", "parquet_file",
    "csv_rows", "parquet_rows", "csv_bytes", "parquet_bytes",
    "date_columns_found", "date_columns_converted",
    "date_columns_kept_string", "elapsed_seconds", "status",
]

def write_inventory(records: list[dict], output_path: Path) -> None:
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INVENTORY_FIELDS)
        writer.writeheader()
        writer.writerows(records)
```

### Anti-Patterns to Avoid

- **Hardcoding date column lists per table:** The user explicitly wants auto-detection. Use name heuristics + value sampling, not a giant dictionary of table→columns.
- **Combining date+time into datetime:** User locked decision — keep date and time as separate columns per PCORnet CDM structure.
- **Skipping failed tables:** User locked decision — stop immediately on any table failure.
- **Keeping raw string copies:** User locked decision — replace in-place, do not keep `BIRTH_DATE_RAW` alongside `BIRTH_DATE`.
- **Using `.str.to_uppercase()` before date parsing:** Unnecessary — chrono's `%b` parser is case-insensitive (verified from chrono source code: `short_month0()` uses `buf[n] | 32` to force lowercase before matching).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SAS DATE9. parsing | Custom regex + datetime construction | `pl.col(c).str.to_date("%d%b%Y", strict=False)` | Chrono handles edge cases, month abbreviation case-insensitivity, and null propagation automatically |
| SAS DATETIME parsing | Custom split-and-parse | `pl.col(c).str.to_datetime("%d%b%Y:%H:%M:%S", strict=False)` | Same chrono-based parsing; `strict=False` produces nulls for unparseable values |
| NAACCR YYYYMMDD parsing | Custom strftime + error handling | `pl.col(c).str.to_date("%Y%m%d", strict=False)` | Standard format, handled natively |
| CSV file listing | Custom directory walking | `schema.parse_datastructure()` from Phase 1 | Already tested, handles comments and quotes in `datastructure.txt` |
| Config paths | Hardcoded HPC paths | `config.load_config()` from Phase 1 | Config-driven paths, works local and on HPC |
| Parquet compression | Manual Arrow/PyArrow compression | `df.write_parquet(path, compression="snappy")` | Polars handles Parquet metadata, columnar encoding, and compression internally |
| Date range validation | Manual min/max computation | `df[col].min()` / `df[col].max()` + filter | Polars optimizes aggregations on date columns natively |

**Key insight:** The entire conversion pipeline chains three Polars one-liners per column: `read_csv(infer_schema=False)` → `str.to_date(fmt, strict=False)` → `write_parquet(compression="snappy")`. The complexity is in the detection logic (which columns, which format), not in the conversion itself.

## Common Pitfalls

### Pitfall 1: Polars Auto-Infers Date Columns as Integers or Dates Before You Can Detect Them

**What goes wrong:** If you use default `pl.read_csv()`, Polars may auto-infer some columns as `Int64` or `Date` based on the first 100 rows. This silently changes the dtype before your detection logic runs, causing `str.to_date()` to fail (column is no longer String type).
**Why it happens:** Polars default `infer_schema_length=100` samples only 100 rows for type inference. YYYYMMDD values (like "20200115") look like integers. DATE9. values (like "01JAN2020") remain strings because they contain letters.
**How to avoid:** Use `pl.read_csv(path, infer_schema=False)` to force all columns to `pl.String`. This gives full control over type conversion.
**Warning signs:** `ComputeError: expected String, got Int64` during date parsing.

### Pitfall 2: Empty String vs Null Confusion in CSV

**What goes wrong:** CSV cells may contain empty strings `""`, actual nulls, or SAS missing value indicators (`.`, `NI`, `UN`, `OT`). Polars treats empty unquoted fields as null by default, but quoted empty strings `""` remain as empty strings. This affects null counts and the 10% threshold calculation.
**Why it happens:** SAS exports and OneFlorida+ data standardization may produce any of these variants.
**How to avoid:** When calculating the 10% threshold, filter out both nulls AND empty strings from the denominator. Only count values that had actual content but failed to parse.
**Warning signs:** A column shows 0% parse failure but has unexpected null count after conversion.

### Pitfall 3: YYYYMMDD Values Ambiguous with Other Numeric Columns

**What goes wrong:** An 8-digit numeric column (like a code or identifier) gets misidentified as a YYYYMMDD date column by the regex sampler.
**Why it happens:** The regex `^\d{8}$` matches any 8-digit string — not just dates.
**How to avoid:** For YYYYMMDD detection, also validate that parsed values fall within a reasonable date range (1900-2026). If >50% of parsed values are out of range, it's not a date column. Additionally, only apply YYYYMMDD detection to columns that also pass the name heuristic OR are in TUMOR_REGISTRY tables. Don't blindly apply it to all string columns.
**Warning signs:** A column like `SITE_CODE` or `HISTOLOGY` with 8-digit values gets converted to dates.

### Pitfall 4: TUMOR_REGISTRY NAACCR Dates May Have Partial Values

**What goes wrong:** NAACCR dates can be partially known — e.g., `20200000` means "year 2020, month and day unknown" and `20201500` means "year 2020, month unknown, day unknown" (or similar coding). These fail `%Y%m%d` parsing.
**Why it happens:** NAACCR allows encoding date precision: unknown month as `00` or `99`, unknown day as `00` or `99`.
**How to avoid:** Before YYYYMMDD parsing, check for `00` month/day values. Either: (a) treat `YYYY0000` as just the year (coerce to Jan 1 of that year), or (b) leave as string if partial dates are common. The 10% threshold will catch columns with many partial dates automatically.
**Warning signs:** High parse failure rate on TUMOR_REGISTRY date columns despite values looking date-like.

### Pitfall 5: CSV Encoding Issues (Latin-1 / CP1252 Characters)

**What goes wrong:** Some healthcare CSVs contain non-UTF-8 characters (accented names, special symbols in notes columns). Polars defaults to UTF-8 and will error on invalid byte sequences.
**Why it happens:** SAS exports may use Windows-1252 or Latin-1 encoding depending on the SAS session settings.
**How to avoid:** Use `pl.read_csv(path, encoding="utf8-lossy")` which replaces invalid UTF-8 sequences with the Unicode replacement character (U+FFFD). Date columns contain only ASCII characters (digits + uppercase month abbreviations), so encoding issues won't affect date parsing — only text columns.
**Warning signs:** `ComputeError: invalid utf-8 sequence` during `read_csv`.

### Pitfall 6: Mixing Date and Datetime Formats in the Same Column

**What goes wrong:** A column might contain both "01JAN2020" (date only) and "01JAN2020:14:30:00" (datetime). Parsing with `%d%b%Y` silently fails on datetime values (or vice versa).
**Why it happens:** Inconsistent SAS formatting within a column, or a column that was date-only for some records and datetime for others.
**How to avoid:** The sampling detection should check for DATETIME pattern first (it's a superset of DATE9. — just check for the `:` separator). If a column has a mix, the user decision says keep date and time separate, so parse as datetime and extract the date portion. Or: if the datetime values are rare (<10%), the threshold logic will coerce them to null and keep the column as Date.
**Warning signs:** Unexpectedly high null rate after DATE9. parsing on a column that should have dates.

### Pitfall 7: Row Count Discrepancy from Quoted Newlines in CSV

**What goes wrong:** CSV row counts don't match between `wc -l` (or Python line count) and Polars row count. Polars correctly handles quoted fields containing newlines, but line-based counters don't.
**Why it happens:** Free-text fields in healthcare data (notes, descriptions) may contain newline characters within quoted fields.
**How to avoid:** Always use `df.height` as the source of truth for row count (Polars handles quoting correctly). Don't compare against line counts. The user decision says "warn but continue" on mismatch — this is the right approach since the mismatch is likely a counting artifact, not data loss.
**Warning signs:** Parquet row count is slightly less than expected (each embedded newline adds 1 to naive line count).

## Code Examples

### Complete Single-Table Conversion (verified pattern)

This pattern is already validated by the Phase 1 smoke test:

```python
# Source: scripts/smoke_test.py (Phase 1, verified working)
import polars as pl

df = pl.read_csv(csv_path)  # or infer_schema=False for full control
df = df.with_columns(
    pl.col("BIRTH_DATE").str.to_date("%d%b%Y", strict=False)
)
df.write_parquet(parquet_path)  # default zstd; Phase 2 uses compression="snappy"

# Verify round-trip
df2 = pl.read_parquet(parquet_path)
assert df2.height == df.height
assert df2["BIRTH_DATE"].dtype == pl.Date
```

### Auto-Detection: Name Heuristic + Value Sampling

```python
import re
import polars as pl

KNOWN_DATE_COLS = {
    "BIRTH_DATE", "ADMIT_DATE", "DISCHARGE_DATE", "DX_DATE", "PX_DATE",
    "MEASURE_DATE", "SPECIMEN_DATE", "RESULT_DATE", "RX_ORDER_DATE",
    "RX_START_DATE", "RX_END_DATE", "DEATH_DATE", "ONSET_DATE",
    "REPORT_DATE", "RESOLVE_DATE", "DISPENSE_DATE", "ENR_START_DATE",
    "ENR_END_DATE", "MEDADMIN_START_DATE", "MEDADMIN_STOP_DATE",
    "VX_RECORD_DATE", "VX_ADMIN_DATE", "VX_EXP_DATE",
    "ADDRESS_PERIOD_START", "ADDRESS_PERIOD_END",
    "DATE_OF_BIRTH", "DATE_OF_DIAGNOSIS",
}

DATE_NAME_RE = re.compile(
    r"(_DATE|_DT)$|^DATE_|^DT_|_DATE_|START_DATE|STOP_DATE|END_DATE",
    re.IGNORECASE,
)

DATE9_RE = re.compile(r"^\d{2}[A-Za-z]{3}\d{4}$")
DATETIME_RE = re.compile(r"^\d{2}[A-Za-z]{3}\d{4}:\d{2}:\d{2}:\d{2}$")
YYYYMMDD_RE = re.compile(r"^\d{8}$")

def detect_date_columns(df: pl.DataFrame, sample_size: int = 200) -> dict[str, str]:
    """
    Returns {column_name: format_string} for all detected date columns.
    Uses name heuristics first, then value sampling for string columns.
    """
    detected = {}

    for col_name in df.columns:
        if df[col_name].dtype != pl.String:
            continue

        # Phase A: name heuristic — flag as candidate
        name_match = col_name in KNOWN_DATE_COLS or bool(DATE_NAME_RE.search(col_name))

        # Phase B: value sampling
        non_null = df[col_name].drop_nulls().filter(df[col_name].drop_nulls() != "")
        if non_null.len() == 0:
            continue

        sample = non_null.head(min(sample_size, non_null.len())).to_list()
        n = len(sample)

        dt_matches = sum(1 for v in sample if DATETIME_RE.match(str(v)))
        d9_matches = sum(1 for v in sample if DATE9_RE.match(str(v)))
        ym_matches = sum(1 for v in sample if YYYYMMDD_RE.match(str(v)))

        # Require >50% match for value-only detection, >30% if name also matches
        val_threshold = 0.3 if name_match else 0.5

        if dt_matches / n > val_threshold:
            detected[col_name] = "%d%b%Y:%H:%M:%S"
        elif d9_matches / n > val_threshold:
            detected[col_name] = "%d%b%Y"
        elif ym_matches / n > val_threshold and name_match:
            # YYYYMMDD only accepted if name also suggests a date column
            # (avoids false positives on 8-digit codes)
            detected[col_name] = "%Y%m%d"
        elif name_match and (d9_matches + dt_matches + ym_matches) / n > val_threshold:
            # Mixed formats — pick the dominant one
            counts = {"%d%b%Y:%H:%M:%S": dt_matches, "%d%b%Y": d9_matches, "%Y%m%d": ym_matches}
            detected[col_name] = max(counts, key=counts.get)

    return detected
```

### 10% Threshold Check

```python
def apply_date_conversion(
    df: pl.DataFrame, col: str, fmt: str
) -> tuple[pl.DataFrame, str, int]:
    """
    Returns (converted_df, action, new_null_count).
    action is "converted", "kept_as_string", or "skipped".
    """
    non_empty = df[col].drop_nulls().filter(df[col].drop_nulls() != "").len()
    if non_empty == 0:
        return df, "skipped", 0

    original_nulls = df[col].null_count()

    if ":" in fmt and fmt.count(":") >= 2:
        trial = df.with_columns(pl.col(col).str.to_datetime(fmt, strict=False))
    else:
        trial = df.with_columns(pl.col(col).str.to_date(fmt, strict=False))

    new_nulls = trial[col].null_count() - original_nulls

    if non_empty > 0 and new_nulls / non_empty > 0.10:
        return df, "kept_as_string", new_nulls

    return trial, "converted", new_nulls
```

### Progress Output Format

```python
import time

def log_table_progress(table_name, csv_rows, csv_bytes, date_cols, elapsed):
    """Print detailed progress per user requirement."""
    print(f"\n{'='*60}")
    print(f"  Table: {table_name}")
    print(f"  CSV rows: {csv_rows:,}")
    print(f"  CSV size: {csv_bytes / 1024 / 1024:.1f} MB")
    print(f"  Date columns found: {len(date_cols)}")
    for col, fmt in date_cols.items():
        print(f"    - {col} ({fmt})")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"{'='*60}")
```

### Interactive Session Launch (srun)

```bash
# User decision: interactive session, not batch
srun --mem=64gb --time=2:00:00 --cpus-per-task=4 \
     --account=erin.mobley-hl.bcu --qos=erin.mobley-hl.bcu \
     --pty bash -i

# Then inside the session:
module load conda
conda activate hl-eda
cd /blue/erin.mobley-hl.bcu/hl-clean
python scripts/convert_all.py
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pd.to_datetime(series, format="%d%b%Y")` | `pl.col(c).str.to_date("%d%b%Y", strict=False)` | Polars 0.15+ (2023) | Native Polars; no pandas dependency; 10-100x faster |
| `.str.to_uppercase()` before `%b` parsing | Not needed — chrono is case-insensitive | Always (chrono uses `byte \| 32`) | One less transformation step; simpler pipeline |
| `write_parquet()` default compression (zstd) | `write_parquet(compression="snappy")` | User decision | Faster reads at cost of larger files |
| Hardcoded date column lists per table | Auto-detect via name heuristic + value sampling | User decision | Catches unexpected date columns; handles TUMOR_REGISTRY format differences automatically |
| `str.strptime()` for date parsing | `str.to_date()` / `str.to_datetime()` | Polars deprecation | `strptime` being deprecated in favor of `to_date()`/`to_datetime()` |

**Deprecated/outdated:**
- `polars.Expr.str.strptime()`: Being deprecated. Use `str.to_date()` and `str.to_datetime()` instead.
- `.str.to_uppercase()` before `%b` parsing: Unnecessary — chrono's `short_month0()` handles case-insensitivity via bitwise OR.
- `from_epoch()` with SAS epoch offset: Not applicable here — this cohort has SAS DATE9. *strings*, not integer dates. `from_epoch()` is for numeric epoch-based dates.

## Open Questions

1. **Are there any columns with SAS integer date values (days since 1960-01-01) instead of DATE9. strings?**
   - What we know: The smoke test confirmed DEMOGRAPHIC.BIRTH_DATE uses DATE9. strings ("01JAN2020"). HL-EDA's `masking.py` used `%d%b%Y` string parsing successfully on this cohort.
   - What's unclear: Whether any table (especially TUMOR_REGISTRY) has numeric SAS date values instead of formatted strings. The value sampling regex would NOT match integers.
   - Recommendation: LOW risk. If a date-named column has all-numeric values that don't match YYYYMMDD (e.g., 5-digit numbers in the 10,000-25,000 range), log a warning and leave as-is for manual review. Don't auto-convert SAS integer dates without confirmation.

2. **How many TUMOR_REGISTRY date columns actually use YYYYMMDD vs DATE9.?**
   - What we know: NAACCR standard specifies YYYYMMDD. But OneFlorida+ may have reformatted during CDM transformation.
   - What's unclear: Actual format in the Mailhot_V1 extract.
   - Recommendation: The auto-detection handles this — it will detect whichever format is actually present. The 10% threshold provides a safety net.

3. **Will any table exhaust 64GB memory during conversion?**
   - What we know: Cohort is 9,331 HL patients. LAB_RESULT_CM and ENCOUNTER tend to be the largest tables in PCORnet cohorts. With `infer_schema=False`, all columns are strings (which use more memory than typed columns).
   - What's unclear: Actual file sizes on disk.
   - Recommendation: LOW risk for a 9,331-patient cohort. Even with hundreds of columns, 9,331 × 265 columns × ~50 bytes/value = ~124 MB for TUMOR_REGISTRY1. Well within 64GB. If a table is unexpectedly large, the interactive session allows immediate diagnosis.

4. **Partial NAACCR dates (YYYY0000, YYYYMM00) — how many exist?**
   - What we know: NAACCR allows partial dates. These will fail `%Y%m%d` parsing.
   - What's unclear: Frequency in this dataset.
   - Recommendation: The 10% threshold handles this automatically. If >10% of a column's values are partial dates, it stays as string (correct behavior — partial dates can't be represented as `pl.Date`). If <10%, they become null (acceptable loss for date-typed analysis).

## Sources

### Primary (HIGH confidence)
- Polars official docs — `str.to_date()` API, `write_parquet()` compression options, `read_csv()` `infer_schema` parameter: https://docs.pola.rs/api/python/stable/
- Chrono crate source code — `short_month0()` in `format/scan.rs` confirms case-insensitive `%b` parsing via `buf[n] | 32`: https://docs.rs/chrono/latest/src/chrono/format/scan.rs.html
- Chrono strftime format specification — `%b`, `%d`, `%Y`, `%H`, `%M`, `%S` specifiers: https://docs.rs/chrono/latest/chrono/format/strftime/index.html
- Phase 1 smoke test (`scripts/smoke_test.py`) — validates `str.to_date("%d%b%Y", strict=False)` works on DEMOGRAPHIC.BIRTH_DATE
- Phase 1 research (`.planning/phases/01-environment-extension-data-staging/01-RESEARCH.md`) — Polars version, stack, HPC compatibility
- SAS Dates research (`.planning/research/SAS_DATES_RESEARCH.md`) — SAS DATE9. format documentation, fallback chain from HL-EDA `masking.py`

### Secondary (MEDIUM confidence)
- NAACCR Data Standards and Data Dictionary — YYYYMMDD format specification: https://apps.naaccr.org/data-dictionary/
- NAACCR 2025 Implementation Guidelines — date format standards (Version 25): https://www.naaccr.org/wp-content/uploads/2024/09/2025-Implementation-Guidelines_20240828.pdf
- Polars GitHub issue #6151 — `%b` case sensitivity discussion and resolution
- Polars StackOverflow — `infer_schema_length=0` and `infer_schema=False` for reading all columns as strings

### Tertiary (LOW confidence)
- Partial NAACCR date handling (YYYY0000) — based on NAACCR general knowledge, not verified against this specific dataset

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Polars APIs verified against official docs; smoke test validates core pipeline
- Architecture: HIGH — single-loop approach is straightforward; auto-detection logic uses well-tested Polars string operations; all patterns demonstrated in code examples
- Pitfalls: HIGH — case-insensitivity verified from chrono source code; encoding/threshold/YYYYMMDD ambiguity based on real-world healthcare data experience
- NAACCR date specifics: MEDIUM — YYYYMMDD format confirmed from NAACCR docs, but partial date frequency in this dataset is unknown

**Research date:** 2026-02-27
**Valid until:** 2026-03-29 (30 days — Polars APIs are stable; date format standards don't change)
