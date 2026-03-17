# Codebase Concerns

**Analysis Date:** 2026-03-17

## Tech Debt

**LAB_RESULT vs LAB_RESULT_CM Column Name Mismatch:**
- Issue: Schema and code refer to `LAB_RESULT_CM` (PCORnet CDM standard) but actual HPC CSV files may be named `LAB_RESULT_Mailhot_V1.csv`, causing filename resolution failures in Phase 2–3 convert/validate steps
- Files: `src/load/schema.py`, `src/load/convert.py`, `src/validate/structural.py` (constants ENCOUNTER_LINKED_TABLES, PATID_LINKED_TABLES reference LAB_RESULT_CM)
- Impact: Pipeline may silently skip LAB_RESULT data if CSV naming doesn't match schema; integrity checks incomplete; Phase 5 dedup misses LAB records
- Fix approach: (1) Query HPC for actual filename; (2) add alias mapping in schema.py if needed; (3) document in datastructure.txt

**Duplicate hpc-upload/ Directory (Deploy Divergence):**
- Issue: `hpc-upload/` subdirectory is treated as independent copy for HPC deployments, but `scripts/src/config` may diverge from project root versions, causing version skew
- Files: `hpc-upload/scripts/`, `hpc-upload/src/`, `hpc-upload/environment.yml` vs root versions
- Impact: Bug fixes in root scripts may not propagate to HPC copy; unclear which version is authoritative; maintenance burden doubles
- Fix approach: Establish deploy strategy: treat hpc-upload/ as deploy artifact; update sync documentation; consider single-source approach for shared code

**Unclear parquet_dir Configuration:**
- Issue: `config/paths.toml` specifies `parquet_dir` but resolution is ambiguous: `src/load/config.py` computes `scratch_root / parquet_rel` (defaults to `hl-clean/parquet`), but scripts also reference `PROJECT_ROOT / "hpc-upload" / "parquet"`, creating two possible locations
- Files: `src/load/config.py` (lines 49–64), `scripts/clean_all.py` (line 396), `scripts/build_insurance_summary.py` (line 62)
- Impact: HPC runs may write parquet to one location while code reads from another; path errors on blue/orange filesystems; unclear which is source-of-truth
- Fix approach: Clarify: is parquet_dir under scratch_root (/blue/.../hl-clean/parquet) or project-local (project/hpc-upload/parquet)? Document in config/paths.toml comments; audit all hard-coded paths

**Missing openpyxl Dependency:**
- Issue: `src/clean/outcomes_flags.py` (line 9) imports pandas and calls `pd.read_excel()` to load `Outcomes.csv`, but openpyxl not listed in `environment.yml`
- Files: `environment.yml` (pip section), `src/clean/outcomes_flags.py` (line 44: `df = pd.read_csv(path)`)
- Impact: Phase 7 (add_modality_flags) fails at runtime with ImportError when xlsx reading triggered; `assemble_clean.py` breaks
- Fix approach: Add `openpyxl` to `environment.yml` pip section (critical blocker)

## Known Bugs

**Small-Cell Suppression Inconsistency in Markdown Tables:**
- Symptoms: Report markdown tables use `flag_small_cell()` (adds ⚠ warning) for counts 1–10, but this is a flag-not-suppress approach; CSV outputs use `_suppress()` (replaces with dash). Inconsistent UX
- Files: `scripts/build_insurance_summary.py` (lines 269, 302, 334, etc. use flag_small_cell); `scripts/clean_all.py` lines 110, 122 use _suppress for CSV
- Trigger: Run build_insurance_summary.py on dataset with small cells
- Workaround: Markdown tables show warning but values visible; CSV truly suppressed. Document choice in CLEANING_DECISIONS
- Note: This is a design choice (show+warn vs suppress) rather than a bug, but inconsistency may confuse users

**Date Parsing Fallback Fragility:**
- Symptoms: `src/load/convert.py` uses 4-format fallback (DATETIME_RE → DATE9_RE → YYYYMMDD_RE → MM/DD/YYYY) but silently keeps unparsed dates as strings without reporting parse failure rate
- Files: `src/load/convert.py` (lines 81–150 detect_date_columns, lines 150–200+ conversion logic)
- Trigger: Data with mixed or non-standard date formats (e.g., 2-digit year, non-English month abbreviations)
- Impact: >10% parse failures may go unnoticed; dates treated as strings in groupby operations, breaking temporal logic
- Workaround: Add parse failure threshold check; log rate; fallback to string if >10% fails

## Security Considerations

**Small-Cell Suppression Not Applied Uniformly:**
- Risk: HIPAA requires suppression of counts 1–10. Audit reveals inconsistent application across report outputs
- Files: `scripts/build_insurance_summary.py` (uses flag_small_cell for markdown, _suppress for CSV), `scripts/clean_all.py` (dedup_report, consistency_report use flag_small_cell), `src/report/site_table.py`, `src/report/quality_report.py`
- Current mitigation: Most outputs do apply suppression; but code duplication of _suppress/_flag_small_cell logic creates maintenance risk
- Recommendations: (1) Centralize suppression in src/report/suppression.py with single API; (2) audit all output paths (markdown, CSV, PNG); (3) add test for every report generator ensuring 1–10 counts are flagged/suppressed

**Environment Variable Exposure (config/paths.toml):**
- Risk: config/paths.toml may contain absolute paths to sensitive data directories (HPC blue/orange paths); not in .gitignore, could be committed
- Files: `config/paths.toml` (not listed in .gitignore)
- Current mitigation: File is not committed (verified in git history); but accidental commits possible
- Recommendations: Add config/paths.toml to .gitignore; maintain config/paths.toml.example as template

## Performance Bottlenecks

**No Incremental Conversion (Re-reads All CSVs):**
- Problem: `scripts/convert_all.py` converts all CSVs to Parquet every run, even if CSV hasn't changed (checked by mtime)
- Files: `scripts/convert_all.py`
- Cause: No skip-if-exists logic; sequential processing of all tables
- Impact: Large datasets (100K+ rows per table) re-convert unnecessarily; 10+ minute runs on repeated executions
- Improvement path: Add mtime check: skip conversion if parquet.mtime > csv.mtime; reduces re-run time to <1 minute for no-change runs

**Lazy Evaluation Not Used in Many-to-Many Joins:**
- Problem: `src/clean/harmonize.py` and `src/report/encounter_payer_summary.py` use left joins with patient-to-enrollment (many-to-many explosion) on full DataFrames
- Files: `src/clean/harmonize.py` (lines 74–104), `src/report/encounter_payer_summary.py` (lines 154+)
- Cause: `.lazy()` used in some places but collected prematurely; intermediate DataFrames materialized in memory
- Impact: Memory usage spikes on datasets with high encounter-to-enrollment ratios; may OOM on HPC with limited memory
- Improvement path: Expand lazy evaluation scope; defer collect() until final aggregations; profile memory on 500K+ patient datasets

**No Parallel Processing for Table Loop:**
- Problem: `scripts/clean_all.py` processes 20+ tables sequentially (lines 448–507), each parquet read/write is single-threaded
- Files: `scripts/clean_all.py` (main loop, lines 448–507)
- Cause: Polars and PyArrow support parallel, but current code doesn't use them
- Impact: Typical run time ~5–10 minutes on HPC; could be 2–3 min with parallel reads
- Improvement path: Profile per-table durations; parallelize independent table processing with multiprocessing.Pool or dask

## Fragile Areas

**Outcomes.xlsx Schema Fragility:**
- Files: `src/clean/outcomes_flags.py` (lines 44–76: load_outcomes_code_lookup)
- Why fragile: Function assumes Outcomes.csv columns are exactly ["Modality", "Code system", "Code"] with forward-fill applied; no schema validation; if columns renamed or reordered, function silently produces empty lookup dict
- Safe modification: (1) Add schema check at top of load_outcomes_code_lookup; (2) raise ValueError if columns missing; (3) document expected column order in docstring and separate .md file
- Test coverage: test_load_outcomes_code_lookup.py exists but uses mock; no actual Outcomes.csv tested

**Date Parsing Multi-Format Fallback:**
- Files: `src/load/convert.py` (lines 81–200, detect_date_columns and convert logic)
- Why fragile: Four-level fallback regex chain; if format order wrong or regex too loose, parses incorrectly (e.g., YYYYMMDD_RE matches 8-digit SITE_CODE if name heuristic triggers). No validation that parsed dates are sensible (e.g., 1800, 2100)
- Safe modification: (1) Add date range bounds check (MIN_DATE=1900, MAX_DATE=2026); (2) add sample validation after parsing; (3) report parse failure % per format; (4) document all tested formats in CLEANING_DECISIONS.md
- Test coverage: No unit tests for date parsing; only end-to-end smoke_test

**LAB_RESULT_CM Column Assumption in Dedup Keys:**
- Files: `src/clean/dedup.py` (lines 22–27, DEDUP_KEYS dict assumes LAB_RESULT_CM present), `src/validate/structural.py` (ENCOUNTER_LINKED_TABLES)
- Why fragile: If actual CSV uses LAB_RESULT (without _CM suffix), table_map["LAB_RESULT_CM"] doesn't exist; code silently skips that table in consistency checks; no validation of table_map completeness
- Safe modification: (1) Add table_map validation function; (2) alias resolution in schema.py if both LAB_RESULT and LAB_RESULT_CM may occur; (3) raise warning if expected table missing from map
- Test coverage: None for table resolution

## Scaling Limits

**Memory: Many-to-Many Encounter-Payer Joins:**
- Current capacity: Tested on ~5K patients, ~50K encounters; works in memory
- Limit: Datasets >50K patients with high enrollment churning (avg >10 enrollment periods per patient) will see memory explosion in payer summary joins
- Scaling path: (1) Partition patients by chunks; (2) use streaming join if Polars supports; (3) materialize intermediate aggregates to disk between phases

**Processing Time: Sequential Table Cleaning:**
- Current capacity: 20 tables process in ~5–10 min (varies by table size)
- Limit: 50+ table datasets or >1M rows per table push to >30 min
- Scaling path: Parallelize table loop; profile Polars lazy/eager thresholds; use dask or Ray for distributed processing

**Storage: Parquet Compression Ratio:**
- Current capacity: ~10GB CSV → ~1.5GB Parquet (snappy, typical ratio 7:1)
- Limit: No partitioning by date/cohort; single monolithic parquet files difficult to iterate
- Scaling path: Add partitioned parquet option (by year or cohort); implement incremental append

## Dependencies at Risk

**pandas (indirect via openpyxl for Outcomes.xlsx):**
- Risk: outcomes_flags.py uses pandas for CSV read; if move to pure Polars, must migrate
- Current: environment.yml specifies pandas>=2.2
- Impact: Added dependency beyond Polars-first; maintenance burden
- Migration plan: Replace pd.read_csv with pl.read_csv; update load_outcomes_code_lookup to use Polars API

**Polars Lazy Evaluation API Maturity:**
- Risk: Code uses `.lazy()` → `.collect()` pattern; Polars API evolving; future versions may change LazyFrame behavior
- Current: No version pin in environment.yml (uses conda-forge default, ~0.20+)
- Impact: Potential breaking changes in lazy join semantics
- Mitigation: Pin polars version in environment.yml; document min/max supported versions

## Missing Critical Features

**No Test Suite for Report Output Validation:**
- Problem: Report scripts generate markdown, CSV, PNG; no tests verify outputs are valid, counts suppressed, column names correct
- Blocks: Cannot confidently refactor report generation; regression detection impossible
- Files: `scripts/build_insurance_summary.py`, `scripts/clean_all.py` report generators, `src/report/site_table.py`

**No Incremental Data Load (Everything Re-processed):**
- Problem: Every run converts all CSVs, validates all tables, dedup all data; no checkpoint/resume
- Blocks: Cannot efficiently re-run subset of tables or phases after failure mid-pipeline
- Impact: 1 failed table → re-run everything (20+ min)

**No Logging Configuration:**
- Problem: Scripts use print() for all logging; no log levels, no option to write to file, no structured logging
- Blocks: Difficult to capture HPC run output for debugging; no timestamp on events
- Files: All scripts in scripts/ and src/

**No Data Lineage Tracking:**
- Problem: Derived table outputs (encounter_payer_summary, quality_report outputs) don't record input file paths, versions, or git commit
- Blocks: Cannot reproduce exact analysis; unclear which version of code generated which report
- Impact: Report provenance unclear for regulatory audit

## Test Coverage Gaps

**Date Parsing Edge Cases:**
- What's not tested: Non-English month abbreviations, partial dates, future dates, 1800s, leap day Feb 29 edge case
- Files: `src/load/convert.py` (detect_date_columns, conversion logic)
- Risk: Edge cases silently kept as strings; temporal logic breaks
- Priority: High (affects data quality)

**Dedup Composite Keys with Nulls:**
- What's not tested: Dedup behavior when key columns are null; expected: null keys don't match each other (per design); but unclear if Polars.is_duplicated() honors this
- Files: `src/clean/dedup.py` (flag_duplicates function, lines 81–97)
- Risk: Nulls may be incorrectly flagged as duplicates if Polars behavior differs
- Priority: High (data integrity)

**Modality Flag Lookups with Missing Codes:**
- What's not tested: add_modality_flags with Outcomes.csv missing code; code should gracefully skip missing codes
- Files: `src/clean/outcomes_flags.py`, test_add_modality_flags.py
- Risk: Sparse code coverage may silently miss modality flags
- Priority: Medium

**Report Generators (Markdown/CSV Output):**
- What's not tested: build_insurance_summary.py, clean_all.py report generators don't have unit tests; tested only by smoke_test
- Files: `scripts/build_insurance_summary.py` (500+ lines), `scripts/clean_all.py` (150+ lines for report generation)
- Risk: Refactoring breaks output format; regressions undetected
- Priority: High (user-facing)

**Cross-Table Consistency Checks:**
- What's not tested: check_demographic_consistency, check_death_consistency logic with various enrollment/death scenarios
- Files: `src/clean/dedup.py` (lines 105–276)
- Risk: Edge cases (multi-BIRTH_DATE, death date mismatch) may be miscounted
- Priority: Medium

---

*Concerns audit: 2026-03-17*
