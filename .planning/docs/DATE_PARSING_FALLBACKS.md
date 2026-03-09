# Date Parsing Fallbacks

**Reference:** `src/load/convert.py`, `src/clean/dedup.py`, `src/report/site_table.py`

## Supported formats (convert.py)

| Format       | Pattern            | Example              |
|--------------|--------------------|----------------------|
| SAS DATE9.   | `%d%b%Y`           | 01JAN2020            |
| SAS DATETIME | `%d%b%Y:%H:%M:%S`  | 01JAN2020:14:30:00   |
| YYYYMMDD     | `%Y%m%d`           | 20200101             |

YYYYMMDD is only used when the column name heuristic also matches (avoids false positives on 8-digit codes like SITE_CODE or HISTOLOGY).

## Additional formats (dedup, site_table)

| Format      | Pattern    | Notes                             |
|-------------|-----------|------------------------------------|
| MM/DD/YYYY  | `%m/%d/%Y`| TUMOR_REGISTRY, site_table fallback |

## Detection logic (convert.py)

1. **Name heuristic:** Column in `KNOWN_DATE_COLS` or matches `DATE_NAME_RE` (`_DATE`, `_DT`, `DATE_`, etc.)
2. **Value sampling:** Non-null values matched via regex (DATE9_RE, DATETIME_RE, YYYYMMDD_RE)
3. **Thresholds:**
   - 30% when name heuristic matches
   - 50% when value-only
   - YYYYMMDD requires name match

## >10% parse failure

When more than 10% of values fail to parse, the column is **kept as string**. `convert_date_column` returns `action: "kept_as_string"` with a reason. This avoids corrupting valid string identifiers that look like dates.

## Reference files

- `src/load/convert.py` — `detect_date_columns()`, `convert_date_column()`, `KNOWN_DATE_COLS`, `DATE9_RE`, `DATETIME_RE`, `YYYYMMDD_RE`
- `src/clean/dedup.py` — date parsing for TUMOR_REGISTRY, death consistency
- `src/report/site_table.py` — age band date fallbacks
