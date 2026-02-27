# Phase 2: CSV-to-Parquet Conversion with SAS Date Handling - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Convert all 22 OneFlorida+ Mailhot_V1 CSV flat files to Parquet format with proper date types. Produce a file inventory. This is a data format conversion phase — no cleaning, validation, or derived variables (those are Phases 3-6).

</domain>

<decisions>
## Implementation Decisions

### Date Column Strategy
- **Format detection:** Auto-detect date columns by sampling values, not just hardcoded lists. Catch any date columns we might miss from naming conventions alone.
- **TUMOR_REGISTRY dates:** Likely use a different format than standard PCORnet tables (NAACCR often uses YYYYMMDD instead of SAS DATE9.). Handle separately with format detection.
- **Date+Time columns:** Keep date and time as separate columns (matches PCORnet CDM structure). Do NOT combine into a single datetime column.
- **Validation range:** 1900-2026 — very permissive, only flag obviously wrong values. The cohort includes masked birth dates (01JAN1900) which must be preserved.
- **Unparseable dates:** If >10% of values in a date column fail to parse, keep the entire column as a string type. Log a warning. Below 10%, coerce failures to null and log the count.

### Conversion Approach
- **Run location:** Interactive session (srun or Jupyter) — watch it run, debug if needed. Not a fire-and-forget batch job.
- **Re-run behavior:** Always reconvert all tables. No skip-existing logic. Ensures consistency.
- **Progress output:** Detailed — table name, row count, date columns found, file sizes, timing per table.

### Claude's Discretion
- **Single script vs grouped tables:** Claude decides whether to use one loop for all 22 tables or separate handling for TUMOR_REGISTRY. The auto-detect date logic should handle format differences either way.

### Parquet Output Layout
- **File naming:** Keep the cohort suffix: `DEMOGRAPHIC_Mailhot_V1.parquet`, `ENCOUNTER_Mailhot_V1.parquet`, etc.
- **Original string columns:** Do NOT keep raw string copies of date columns. Replace in-place with typed versions only.
- **Compression:** snappy — prioritize faster reads over maximum compression.
- **Inventory format:** CSV file (`file_inventory.csv`) — easy to open in Excel or pandas.

### Error Tolerance
- **Table failure:** Stop immediately if any table fails to load or convert. Do not skip and continue.
- **Empty tables:** Skip empty tables — do not create a Parquet file for them. Note in inventory.
- **Row count mismatch:** Warn but continue if CSV and Parquet row counts differ. Log the discrepancy.

</decisions>

<specifics>
## Specific Ideas

- The HL-EDA project's `parse_sas_dates()` function in `src/characterize/masking.py` already handles the DATE9. format with a fallback chain (`%d%b%Y` → `%d%b%Y:%H:%M:%S` → general `pd.to_datetime`). The Polars equivalent should follow a similar fallback pattern.
- TUMOR_REGISTRY tables have ~265, ~120, and ~120 columns respectively — many more than standard PCORnet tables. Date auto-detection needs to be efficient across hundreds of columns.
- Known masked values: BIRTH_DATE="01JAN1900", DATE_OF_BIRTH containing "1900", AGE_AT_DIAGNOSIS=200. These are valid data points, not errors.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-csv-to-parquet-conversion*
*Context gathered: 2026-02-27*
