# SAS Date Formats in CSV Files: Research & Conversion Guide

**Domain:** Healthcare data exported from SAS to CSV
**Researched:** 2026-02-27
**Overall Confidence:** HIGH (based on official SAS documentation and widely verified community practices)

---

## 1. How SAS Date Values Work

### The SAS Epoch

SAS uses **January 1, 1960 (midnight)** as its epoch — the zero-point reference for all date and time calculations.

| Value Type | Unit | Definition | Example |
|------------|------|------------|---------|
| **SAS Date** | Days since 1960-01-01 | Integer count of days | `0` = Jan 1, 1960; `22281` = Jan 1, 2021 |
| **SAS Datetime** | Seconds since 1960-01-01 00:00:00 | Real number (may have decimals) | `1924992000` = Jan 1, 2021 00:00:00 |
| **SAS Time** | Seconds since midnight | Real number, range 0–86400 | `43200` = 12:00:00 noon |

**Key facts:**
- Dates before 1960 are **negative numbers** (e.g., `-365` = Jan 1, 1959)
- SAS can handle dates from A.D. 1582 to A.D. 19,900
- Date values are always **integers** (whole days)
- Datetime and time values are **real numbers** (may contain decimal fractions for sub-second precision)

### Magnitude Reference Table

Use this to sanity-check raw numeric values in CSV columns:

| Date | SAS Date Value (days) | SAS Datetime Value (seconds) |
|------|-----------------------|------------------------------|
| 1960-01-01 | 0 | 0 |
| 1970-01-01 | 3,653 | 315,619,200 |
| 1980-01-01 | 7,305 | 631,152,000 |
| 1990-01-01 | 10,958 | 946,771,200 |
| 2000-01-01 | 14,610 | 1,262,304,000 |
| 2010-01-01 | 18,263 | 1,577,923,200 |
| 2020-01-01 | 21,915 | 1,893,456,000 |
| 2025-01-01 | 23,742 | 2,051,222,400 |
| 2026-01-01 | 24,107 | 2,082,844,800 |

**Rule of thumb:**
- SAS **date** values for modern healthcare data fall in the range **~10,000–25,000**
- SAS **datetime** values are in the **hundreds of millions to low billions**
- If a "date" column has values > 100,000, it is almost certainly a **datetime** (seconds), not a date (days)

### Common SAS Date/Time Formats

These are the format names applied to columns in SAS before export. When exported to CSV *without* formatting, the raw numeric values appear instead.

| Format | Display Example | Type |
|--------|----------------|------|
| `DATE9.` | `17OCT1991` | Date |
| `MMDDYY10.` | `10/17/1991` | Date |
| `YYMMDD10.` | `1991-10-17` | Date |
| `DDMMYY10.` | `17/10/1991` | Date |
| `DATETIME20.` | `17OCT1991:13:45:00` | Datetime |
| `DATETIME26.6` | `17OCT91:13:45:00.000000` | Datetime |
| `MONYY7.` | `OCT1991` | Date (month-level) |
| `YEAR4.` | `1991` | Date (year-level) |
| `TIME8.` | `13:45:00` | Time |
| `HHMM5.` | `13:45` | Time |

---

## 2. Identifying SAS Date Columns in CSV Files

When SAS exports to CSV without applying display formats, date columns lose their human-readable formatting and appear as **plain integers or real numbers**. This is the core problem.

### Detection Strategy

#### Step 1: Check for metadata or data dictionaries

Many healthcare SAS datasets come with:
- A SAS format catalog or `PROC CONTENTS` output listing variable formats
- A data dictionary (PDF/Excel) describing each column's meaning and SAS format
- Column names with date-related suffixes (see healthcare section below)

**Always look for metadata first** — guessing from raw values is error-prone.

#### Step 2: Column name heuristics

Look for columns whose names contain:

| Pattern | Likely Type |
|---------|-------------|
| `*_DT`, `*_DATE`, `*DATE` | SAS date |
| `*_DTM`, `*_DTTM`, `*_DATETIME` | SAS datetime |
| `*_TM`, `*_TIME` | SAS time |
| `DOB`, `BIRTH_DT`, `DEATH_DT` | SAS date |
| `ADMIT_DT`, `DISCH_DT` | SAS date |
| `CLM_FROM_DT`, `CLM_THRU_DT` | SAS date |

#### Step 3: Value range analysis

If column names are ambiguous, examine the numeric values:

| Value Range | Likely Type | Reasoning |
|-------------|-------------|-----------|
| -500 to 30,000 | SAS date | Days since 1960 covering ~1958–2042 |
| 30,000 to 100,000 | **Ambiguous** | Could be far-future date or small time |
| > 100,000 | SAS datetime | Seconds since 1960 |
| 0 to 86,400 | SAS time | Seconds in a day |
| Blank or `.` | Missing value | SAS missing |

#### Step 4: Spot-check conversions

Convert a few sample values and verify they make sense for the domain:

```python
from datetime import date, timedelta
test_value = 22281
print(date(1960, 1, 1) + timedelta(days=test_value))
# Output: 2021-01-01 — looks like a plausible date
```

### How Missing Values Appear in CSV

| SAS Internal | CSV Representation | Notes |
|-------------|-------------------|-------|
| `.` (numeric missing) | Blank/empty cell | Most common; **not** a literal dot in CSV |
| `.A` through `.Z` | Blank/empty cell or literal `.A` | Special missing values; behavior depends on export method |
| `.` in character var | Literal `.` | Character variable, not numeric |

**Critical:** When reading CSV into Python/R, blank cells in numeric columns become `NaN`/`NA`. The distinction between "missing" and "never collected" (which SAS encodes with special missing values `.A`–`.Z`) is **lost** in CSV export. If your data uses special missing values, request the SAS7BDAT file instead.

---

## 3. Conversion Formulas and Functions

### Python (pandas)

```python
import pandas as pd
from datetime import date, timedelta

# --- SAS Date (days since 1960-01-01) ---

# Method 1: pandas (recommended for DataFrames)
df['converted_date'] = pd.to_datetime(df['sas_date_col'], unit='D', origin='1960-01-01')

# Method 2: stdlib (for single values)
converted = date(1960, 1, 1) + timedelta(days=int(sas_value))

# --- SAS Datetime (seconds since 1960-01-01 00:00:00) ---
df['converted_datetime'] = pd.to_datetime(df['sas_datetime_col'], unit='s', origin='1960-01-01')

# --- SAS Time (seconds since midnight) ---
df['converted_time'] = pd.to_timedelta(df['sas_time_col'], unit='s')

# --- Batch conversion of multiple date columns ---
SAS_EPOCH = '1960-01-01'

date_cols = ['ADMIT_DT', 'DISCH_DT', 'BIRTH_DT', 'DEATH_DT']
for col in date_cols:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], unit='D', origin=SAS_EPOCH, errors='coerce')

datetime_cols = ['EXTRACT_DTTM', 'UPDATE_DTTM']
for col in datetime_cols:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], unit='s', origin=SAS_EPOCH, errors='coerce')
```

**Important:** Use `errors='coerce'` to convert unparseable values to `NaT` instead of raising exceptions. This handles blanks and special missing values gracefully.

### R

```r
# --- SAS Date (days since 1960-01-01) ---
df$converted_date <- as.Date(df$sas_date_col, origin = "1960-01-01")

# --- SAS Datetime (seconds since 1960-01-01 00:00:00) ---
df$converted_datetime <- as.POSIXct(df$sas_datetime_col, origin = "1960-01-01", tz = "UTC")

# --- Using the SASdates package (CRAN) ---
# install.packages("SASdates")
library(SASdates)
df$converted_date <- sas_date_to_r(df$sas_date_col)

# --- Batch conversion ---
date_cols <- c("ADMIT_DT", "DISCH_DT", "BIRTH_DT", "DEATH_DT")
for (col in date_cols) {
  if (col %in% names(df)) {
    df[[col]] <- as.Date(df[[col]], origin = "1960-01-01")
  }
}

datetime_cols <- c("EXTRACT_DTTM", "UPDATE_DTTM")
for (col in datetime_cols) {
  if (col %in% names(df)) {
    df[[col]] <- as.POSIXct(df[[col]], origin = "1960-01-01", tz = "UTC")
  }
}
```

**Warning:** Do **not** use `as.POSIXct()` for SAS date values — `POSIXct` treats the origin offset as seconds, not days. Use `as.Date()` for dates, `as.POSIXct()` only for datetimes.

### SQL Server (T-SQL)

```sql
-- SAS Date (days since 1960-01-01)
SELECT DATEADD(DAY, sas_date_col, '19600101') AS converted_date
FROM healthcare_table;

-- SAS Datetime (seconds since 1960-01-01 00:00:00)
SELECT DATEADD(SECOND, sas_datetime_col, '19600101') AS converted_datetime
FROM healthcare_table;

-- With NULL handling (SAS missing = NULL after import)
SELECT
    CASE WHEN sas_date_col IS NOT NULL
         THEN DATEADD(DAY, sas_date_col, '19600101')
         ELSE NULL
    END AS converted_date
FROM healthcare_table;
```

### PostgreSQL

```sql
-- SAS Date
SELECT DATE '1960-01-01' + sas_date_col * INTERVAL '1 day' AS converted_date
FROM healthcare_table;

-- SAS Datetime
SELECT TIMESTAMP '1960-01-01 00:00:00' + sas_datetime_col * INTERVAL '1 second' AS converted_datetime
FROM healthcare_table;
```

### SQLite

```sql
-- SAS Date (SQLite stores dates as text; use date function)
SELECT date('1960-01-01', '+' || sas_date_col || ' days') AS converted_date
FROM healthcare_table;

-- SAS Datetime
SELECT datetime('1960-01-01', '+' || sas_datetime_col || ' seconds') AS converted_datetime
FROM healthcare_table;
```

---

## 4. Common Pitfalls

### Pitfall 1: Confusing SAS Date vs. SAS Datetime (CRITICAL)

**What goes wrong:** Applying a date conversion (days) to a datetime value (seconds) or vice versa. A datetime value of 1,893,456,000 treated as days produces a date in the year 5,185,000+. A date value of 22,000 treated as seconds produces a time ~6 hours after midnight on Jan 1, 1960.

**Prevention:**
- Check the magnitude: date values are 5 digits or fewer for modern dates; datetime values are 9–10 digits
- Check the column name for `_DT` vs `_DTTM`/`_DTM` suffixes
- Check if values have decimal components (datetimes may; dates never do)
- **Always spot-check** a few converted values for sanity

### Pitfall 2: Missing Values as Dots or Blanks

**What goes wrong:** SAS exports numeric missing values (`.`) as blanks in CSV. When pandas reads these, they become `NaN`. If the column also contains legitimate numeric date values, pandas may infer the column as `float64` instead of `int64`, adding spurious `.0` decimals to the date values.

**Prevention:**
- After reading CSV, check dtypes — date columns read as `float64` likely have missing values
- Convert with `errors='coerce'` to handle `NaN` gracefully
- In R, `NA` handling is native — just ensure you pass `na.rm = TRUE` in aggregations

### Pitfall 3: SAS Date Value of 0 = January 1, 1960

**What goes wrong:** A date value of `0` is a valid SAS date (the epoch itself), but it often indicates a **data error** rather than a real date of January 1, 1960 — especially in healthcare data where this date has no clinical significance.

**Prevention:**
- Flag any dates converting to exactly 1960-01-01 as suspicious
- Check if these should actually be missing/NULL
- Same applies to very small positive values that convert to dates in the early 1960s — unlikely for modern patient data

### Pitfall 4: Timezone Issues with Datetimes

**What goes wrong:** SAS datetime values have no inherent timezone — they are "wall clock" time in whatever timezone the data was collected. Converting to `POSIXct` in R or `datetime64` in Python may apply the system's local timezone, shifting the time.

**Prevention:**
- Always specify `tz = "UTC"` in R's `as.POSIXct()` unless you know the source timezone
- In Python, `pd.to_datetime()` with `unit='s'` produces timezone-naive datetimes by default (safe)
- If comparing across facilities in different timezones, document which timezone the original data used

### Pitfall 5: Large CSV Files and Type Inference

**What goes wrong:** When reading multi-GB healthcare CSVs, pandas samples only the first rows to infer dtypes. If early rows have missing dates (blanks), pandas may classify the column as `object` (string) rather than numeric, causing downstream conversion to fail silently.

**Prevention:**
- Explicitly specify dtypes when reading: `pd.read_csv(file, dtype={'ADMIT_DT': 'Float64'})`
- Or use `low_memory=False` to force full-file type inference (slower but safer)
- In R, `readr::read_csv()` scans more rows by default; set `guess_max` higher for safety

### Pitfall 6: Special Missing Values Lost in CSV Export

**What goes wrong:** SAS supports 27 flavors of missing (`.`, `.A`–`.Z`, `._`). These carry semantic meaning (e.g., `.D` = deceased, `.R` = refused). In CSV export, they all collapse to blank cells — the reason for missingness is lost.

**Prevention:**
- Request the original SAS7BDAT file if special missing values matter
- Ask the data provider for documentation on which special missing values were used
- Check if a companion "reason" column encodes the missing value semantics separately

### Pitfall 7: Date Values Stored as Character Strings in SAS

**What goes wrong:** Some SAS datasets store dates as character strings (e.g., `"01/15/2021"`) rather than numeric SAS date values. In CSV, these appear as text, not integers. Applying the days-since-1960 conversion to these would be wrong — they need standard date parsing instead.

**Prevention:**
- Before applying SAS epoch arithmetic, verify that date columns contain integers (not formatted date strings)
- If a column contains slashes, dashes, or month abbreviations, it's already a formatted string — parse with `pd.to_datetime()` or `as.Date()` directly

---

## 5. Healthcare-Specific Date Fields

### Standard CMS/Medicare Variable Names

| Variable Name | Description | Type | Notes |
|---------------|-------------|------|-------|
| `BENE_BIRTH_DT` | Beneficiary date of birth | Date | Should be 1900–2026 range |
| `BENE_DEATH_DT` | Beneficiary date of death | Date | Missing if alive; validate ≥ birth date |
| `CLM_FROM_DT` | Claim service start date | Date | First day of service period |
| `CLM_THRU_DT` | Claim service end date | Date | Last day; must be ≥ `CLM_FROM_DT` |
| `CLM_ADMSN_DT` | Claim admission date | Date | Inpatient admission |
| `NCH_BENE_DSCHRG_DT` | Discharge date | Date | Must be ≥ admission date |
| `CLM_PMT_AMT_DT` | Claim payment date | Date | Processing/adjudication date |
| `DOB_DT` | Date of birth (generic) | Date | Alternate naming convention |
| `PRNCPAL_DGNS_DT` | Principal diagnosis date | Date | When diagnosis was made |

### Common Healthcare Date Fields (Non-CMS)

| Field Pattern | Description | Validation Rule |
|---------------|-------------|-----------------|
| `ADMIT_DT` / `ADMISSION_DATE` | Hospital admission | 1950–present |
| `DISCH_DT` / `DISCHARGE_DATE` | Hospital discharge | ≥ admission date |
| `PROC_DT` / `PROCEDURE_DATE` | Procedure performed | Between admit and discharge |
| `DIAG_DT` / `DIAGNOSIS_DATE` | Diagnosis recorded | Reasonable clinical timeframe |
| `BIRTH_DT` / `DOB` | Patient birth date | 1900–present; must precede all other dates |
| `DEATH_DT` / `DOD` | Patient death date | ≥ birth date; ≤ today |
| `SERVICE_DT` / `SVC_DT` | Date of service | Between claim from/thru dates |
| `RX_FILL_DT` | Prescription fill date | Pharmacy claims |
| `LAB_DT` | Lab result date | Should be near service date |
| `ENROLL_START_DT` | Enrollment start | Insurance eligibility |
| `ENROLL_END_DT` | Enrollment end | ≥ enrollment start |
| `EXTRACT_DT` / `EXTRACT_DTTM` | Data extract timestamp | Usually a datetime, not date |

### Clinical Trial / Research Date Fields

| Field | Description | Notes |
|-------|-------------|-------|
| `VISIT_DT` | Study visit date | Must follow visit schedule |
| `RAND_DT` | Randomization date | Must precede treatment dates |
| `FIRST_DOSE_DT` | First drug dose | Must be on/after randomization |
| `LAST_DOSE_DT` | Last drug dose | Must be ≥ first dose |
| `AE_START_DT` | Adverse event start | Event onset |
| `AE_END_DT` | Adverse event end | ≥ AE start |
| `DEATH_DT` | Death date | Terminal event |

---

## 6. Validation Strategies

### Range Checks After Conversion

```python
import pandas as pd

def validate_sas_dates(df, date_cols, context='healthcare'):
    """Validate converted SAS date columns for common issues."""
    issues = []

    for col in date_cols:
        if col not in df.columns:
            continue

        series = pd.to_datetime(df[col], errors='coerce')

        # Count missing
        n_missing = series.isna().sum()
        n_total = len(series)
        pct_missing = (n_missing / n_total) * 100

        if pct_missing > 50:
            issues.append(f"{col}: {pct_missing:.1f}% missing — verify this is expected")

        valid = series.dropna()
        if len(valid) == 0:
            issues.append(f"{col}: ALL values missing — wrong column or conversion error")
            continue

        min_date = valid.min()
        max_date = valid.max()

        # Flag epoch date (likely data error)
        n_epoch = (valid == pd.Timestamp('1960-01-01')).sum()
        if n_epoch > 0:
            issues.append(f"{col}: {n_epoch} values = 1960-01-01 (SAS epoch) — likely data error")

        # Flag unreasonable ranges
        if min_date < pd.Timestamp('1900-01-01'):
            issues.append(f"{col}: min date {min_date.date()} is before 1900 — check conversion")

        if max_date > pd.Timestamp('2030-12-31'):
            issues.append(f"{col}: max date {max_date.date()} is after 2030 — possible datetime-as-date error")

        # Healthcare-specific: birth dates
        if any(kw in col.upper() for kw in ['BIRTH', 'DOB', 'BENE_BIRTH']):
            if min_date < pd.Timestamp('1890-01-01'):
                issues.append(f"{col}: birth date {min_date.date()} implausibly old")
            if max_date > pd.Timestamp.now():
                issues.append(f"{col}: birth date {max_date.date()} is in the future")

        # Healthcare-specific: death dates
        if any(kw in col.upper() for kw in ['DEATH', 'DOD', 'BENE_DEATH']):
            if max_date > pd.Timestamp.now():
                issues.append(f"{col}: death date {max_date.date()} is in the future")

    return issues
```

### Cross-Field Consistency Checks

```python
def validate_date_relationships(df):
    """Check logical ordering of healthcare date fields."""
    issues = []

    # Admission before discharge
    if 'ADMIT_DT' in df.columns and 'DISCH_DT' in df.columns:
        bad = df[df['DISCH_DT'] < df['ADMIT_DT']]
        if len(bad) > 0:
            issues.append(f"{len(bad)} records have discharge before admission")

    # Birth before admission
    if 'BIRTH_DT' in df.columns and 'ADMIT_DT' in df.columns:
        bad = df[df['ADMIT_DT'] < df['BIRTH_DT']]
        if len(bad) > 0:
            issues.append(f"{len(bad)} records have admission before birth")

    # Death after birth
    if 'BIRTH_DT' in df.columns and 'DEATH_DT' in df.columns:
        bad = df[df['DEATH_DT'] < df['BIRTH_DT']].dropna(subset=['DEATH_DT'])
        if len(bad) > 0:
            issues.append(f"{len(bad)} records have death before birth")

    # Claim from before claim thru
    if 'CLM_FROM_DT' in df.columns and 'CLM_THRU_DT' in df.columns:
        bad = df[df['CLM_THRU_DT'] < df['CLM_FROM_DT']]
        if len(bad) > 0:
            issues.append(f"{len(bad)} records have claim thru before claim from")

    # Procedure during admission
    if 'PROC_DT' in df.columns and 'ADMIT_DT' in df.columns and 'DISCH_DT' in df.columns:
        bad = df[(df['PROC_DT'] < df['ADMIT_DT']) | (df['PROC_DT'] > df['DISCH_DT'])]
        bad = bad.dropna(subset=['PROC_DT', 'ADMIT_DT', 'DISCH_DT'])
        if len(bad) > 0:
            issues.append(f"{len(bad)} records have procedure outside admission window")

    return issues
```

### R Validation

```r
validate_sas_dates <- function(df, date_cols) {
  issues <- character()

  for (col in date_cols) {
    if (!(col %in% names(df))) next

    vals <- df[[col]]

    # Missing rate
    pct_missing <- sum(is.na(vals)) / length(vals) * 100
    if (pct_missing > 50) {
      issues <- c(issues, sprintf("%s: %.1f%% missing", col, pct_missing))
    }

    valid <- vals[!is.na(vals)]
    if (length(valid) == 0) {
      issues <- c(issues, sprintf("%s: ALL values missing", col))
      next
    }

    # Epoch check
    n_epoch <- sum(valid == as.Date("1960-01-01"))
    if (n_epoch > 0) {
      issues <- c(issues, sprintf("%s: %d values = 1960-01-01 (SAS epoch)", col, n_epoch))
    }

    # Range check
    if (min(valid) < as.Date("1900-01-01")) {
      issues <- c(issues, sprintf("%s: min date %s before 1900", col, min(valid)))
    }
    if (max(valid) > as.Date("2030-12-31")) {
      issues <- c(issues, sprintf("%s: max date %s after 2030 — likely wrong conversion", col, max(valid)))
    }
  }

  return(issues)
}
```

### Quick Diagnostic Summary

Run this immediately after conversion to catch errors early:

```python
def date_diagnostic(df, date_cols):
    """Print a quick summary of converted date columns."""
    for col in date_cols:
        if col not in df.columns:
            continue
        s = df[col]
        print(f"\n--- {col} ---")
        print(f"  dtype:   {s.dtype}")
        print(f"  non-null: {s.notna().sum()} / {len(s)} ({s.notna().mean()*100:.1f}%)")
        if s.notna().any():
            print(f"  min:     {s.min()}")
            print(f"  max:     {s.max()}")
            print(f"  median:  {s.dropna().median()}")
            n_epoch = (s == pd.Timestamp('1960-01-01')).sum()
            if n_epoch > 0:
                print(f"  WARNING: {n_epoch} values = 1960-01-01 (epoch)")
```

---

## 7. Complete Conversion Workflow (Python)

Putting it all together for a healthcare CSV exported from SAS:

```python
import pandas as pd

SAS_EPOCH = '1960-01-01'

# 1. Read CSV with explicit types for date columns to prevent misdetection
date_columns = ['ADMIT_DT', 'DISCH_DT', 'BIRTH_DT', 'DEATH_DT',
                'CLM_FROM_DT', 'CLM_THRU_DT', 'PROC_DT']
datetime_columns = ['EXTRACT_DTTM', 'UPDATE_DTTM']
all_date_like = date_columns + datetime_columns

dtype_spec = {col: 'Float64' for col in all_date_like}

df = pd.read_csv('healthcare_data.csv', dtype=dtype_spec, low_memory=False)

# 2. Convert SAS date columns (days since 1960-01-01)
for col in date_columns:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], unit='D', origin=SAS_EPOCH, errors='coerce')

# 3. Convert SAS datetime columns (seconds since 1960-01-01)
for col in datetime_columns:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], unit='s', origin=SAS_EPOCH, errors='coerce')

# 4. Run diagnostics
for col in all_date_like:
    if col in df.columns:
        s = df[col]
        print(f"{col}: {s.notna().sum()}/{len(s)} non-null, "
              f"range {s.min()} to {s.max()}")

# 5. Validate
issues = validate_sas_dates(df, date_columns)
issues += validate_date_relationships(df)
for issue in issues:
    print(f"  ISSUE: {issue}")
```

---

## Sources

- SAS Documentation: "About SAS Date, Time, and Datetime Values" — https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a002200738.htm
- SAS Documentation: "DATETIME Format" — https://documentation.sas.com/doc/de/vdmmlcdc/8.1/leforinforref/n0av4h8lmnktm4n1i33et4wyz5yy.htm
- SAS Documentation: "Special Missing Values" — https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a000992455.htm
- SAS Paper: "Do Not Let a Bad Date Ruin Your Day" (SGF 2013) — https://support.sas.com/resources/papers/proceedings13/122-2013.pdf
- WUSS 2023: "The Essentials of SAS Dates and Times" — https://www.wuss.org/proceedings/2023/WUSS-2023-Paper-130.pdf
- CRAN: SASdates package — https://cran.r-project.org/package=SASdates
- CMS CCW Medicare FFS Claims Codebook — https://www2.ccwdata.org/documents/10280/19022436/codebook-ffs-claims.pdf
- ResDAC Medicare Data Documentation — https://resdac.org/cms-data/files/ip-ffs/data-documentation
- PharmaSUG 2024: "Understanding Administrative Healthcare Data Sets" — https://pharmasug.org/proceedings/2024/HT/PharmaSUG-2024-HT-157.pdf
