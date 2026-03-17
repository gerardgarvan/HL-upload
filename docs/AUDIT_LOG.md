# Audit Log: Unknowns & Technical Debt

**Created:** 2026-03-17 (Phase 1 documentation)
**Purpose:** Track unknowns discovered during documentation for validation/testing in Phase 2/3
**How to use:** Each entry maps to a Phase 2/3 requirement for follow-up

---

## HIGH Severity (Data Correctness Impact)

### AUDIT-001: Sentinel value 99/9999 in payer fields not consistently handled

**Location:** `src/report/encounter_payer_summary.py:58`
**Code context:**
```python
INCLUDE_99_AS_SENTINEL: bool = False  # Line 58
# TODO(audit): Validate 99/9999 semantics with data partners. If partners use inconsistently,
# may need per-partner configuration.
```

**Issue:** `INCLUDE_99_AS_SENTINEL` flag exists but defaults to False. Code has logic to treat 99/9999 as sentinel values triggering fallback to secondary payer (similar to NI/UN/OT), but this behavior is disabled by default. Unclear if this is intentional (99 is valid "Unavailable" category) or an incomplete feature.

**What code DOES (actual behavior):**
- When `INCLUDE_99_AS_SENTINEL = False` (current): 99/9999 treated as valid payer, mapped to "Unavailable" category, no fallback to secondary
- When `INCLUDE_99_AS_SENTINEL = True`: 99/9999 treated like NI/UN/OT, triggers fallback to PAYER_TYPE_SECONDARY

**Clinical context:** 99 in PCORnet = "Unable to categorize", 9999 = Missing/not collected. Both are distinct from NI/UN/OT (data collected but unusable). Category "Unavailable" (99/9999) vs "Unknown" (NI/UN/OT) semantic distinction matters for insurance equity analysis where missing data patterns may indicate systematic collection gaps.

**Impact on data correctness:** HIGH - If 99/9999 should trigger fallback, currently missing opportunity to use secondary payer data, potentially misclassifying patients' insurance status. If 99/9999 should be "Unavailable", current behavior is correct.

**Confidence level:** MEDIUM — this appears to be a user decision, not a bug, but the disabled flag suggests uncertainty

**Recommended action:**
1. Validate with domain expert: Should 99/9999 trigger secondary payer fallback?
2. If YES: Enable flag or remove conditional logic, add tests for fallback behavior
3. If NO: Remove flag and conditional logic, document why 99/9999 is distinct from NI/UN/OT
4. Either way: Add docstring explaining the decision

**Phase 2/3 follow-up:**
- VAL-04 (configuration validation): Flag should have clear documentation
- TEST-01 (payer logic tests): Test both 99/9999 behaviors

---

### AUDIT-002: Date parsing 30%/50% match thresholds for auto-detection

**Location:** `src/load/convert.py:90-100`
**Code context:**
```python
def detect_date_columns(...):
    # Name heuristic: 30% match threshold
    if pct_matched >= 0.30 and any(...):
        date_cols.add(...)
    # Value-only heuristic: 50% match threshold
    elif pct_matched >= 0.50:
        date_cols.add(...)
```

**Issue:** `detect_date_columns()` uses 30% match threshold for name+value heuristic, 50% for value-only. Thresholds are reasonable but not validated empirically against actual OneFlorida+ data. May miss some date columns (false negative if <30% match) or false-positive on numeric codes that happen to match date patterns.

**What code DOES (actual behavior):** Auto-detects date columns using 4-format fallback (DATETIME_RE → DATE9_RE → YYYYMMDD_RE → MM/DD/YYYY). If ≥30% of non-null values match a date regex AND column name contains date-related words, column is typed as Date. If ≥50% match without name heuristic, also typed as Date.

**Clinical context:** Date columns (BIRTH_DATE, ADMIT_DATE, DX_DATE, etc.) are critical for temporal validation and cohort selection. Missing a date column (false negative) breaks downstream temporal logic. Incorrectly typing a numeric ID as date (false positive) corrupts data.

**Impact on data correctness:** HIGH (potential) — False negatives break temporal analyses; false positives corrupt data

**Confidence level:** LOW — thresholds seem reasonable but unverified on real data. No known failures reported.

**Recommended action:** Sample 10 tables, manually verify all date columns detected correctly. Adjust thresholds if systematic misses found. Add unit tests for edge cases.

**Phase 2/3 follow-up:**
- TEST-02 (date parsing tests): Add edge case tests (partial dates, mixed formats, numeric codes)
- Validate in Phase 2 against full dataset

---

### AUDIT-003: LAB_RESULT vs LAB_RESULT_CM table name mismatch

**Location:** `src/load/schema.py:29`, `src/clean/dedup.py:27`, `src/validate/structural.py:15`
**Code context:**
```python
# src/load/schema.py:29
# TODO(audit): Verify if other tables need aliases (TUMOR_REGISTRY naming?)

# DEDUP_KEYS references LAB_RESULT_CM
DEDUP_KEYS = {
    "LAB_RESULT_CM": ["ID", "LAB_LOINC", "SPECIMEN_DATE", "RESULT_NUM"],
    ...
}
```

**Issue:** Schema and code refer to `LAB_RESULT_CM` (PCORnet CDM standard name) but actual HPC CSV files may be named `LAB_RESULT_Mailhot_V1.csv` (without _CM suffix). Filename resolution in `resolve_table_name()` may fail if CSV naming doesn't match schema expectations.

**What code DOES (actual behavior):** `resolve_table_name()` uses exact stem matching. If CSV is "LAB_RESULT_Mailhot_V1.csv", stem is "LAB_RESULT_Mailhot_V1", which resolves to "LAB_RESULT" (not "LAB_RESULT_CM"). Downstream code expecting "LAB_RESULT_CM" key will silently skip the table.

**Clinical context:** LAB_RESULT_CM contains lab results (WBC, ANC, HGB, PLT, CRCL) critical for HL chemotherapy toxicity monitoring. Missing lab data silently breaks plausibility validation and clinical outcome analyses.

**Impact on data correctness:** HIGH — Pipeline may silently skip LAB_RESULT data if CSV naming doesn't match schema; integrity checks incomplete; Phase 5 dedup misses LAB records

**Confidence level:** HIGH — Code inspection confirms mismatch between expected table name and potential CSV naming

**Recommended action:**
1. Query HPC for actual LAB_RESULT filename
2. Add alias mapping in `schema.py` if needed (e.g., "LAB_RESULT" → "LAB_RESULT_CM")
3. Document in datastructure.txt
4. Add validation check: warn if expected table missing from table_map

**Phase 2/3 follow-up:**
- VAL-02 (schema validation): Add table name alias resolution check
- TEST-01 (structural tests): Test table resolution with both naming conventions

---

### AUDIT-004: Null key behavior in deduplication

**Location:** `src/clean/dedup.py:81-97`
**Code context:**
```python
def flag_duplicates(df: pl.DataFrame, table_name: str) -> pl.DataFrame:
    # Composite key deduplication
    if table_name in DEDUP_KEYS:
        keys = DEDUP_KEYS[table_name]
        # is_duplicated() behavior with nulls: null != null (Polars default)
        df = df.with_columns(pl.struct(keys).is_duplicated().cast(pl.Int8).alias("IS_DUPLICATE"))
```

**Issue:** Dedup logic uses `is_duplicated()` on composite keys. Polars default behavior is `null != null`, so rows with null keys are NOT flagged as duplicates. This is correct behavior (nulls shouldn't match), but documentation doesn't explicitly state this assumption and there's no validation that Polars hasn't changed this behavior.

**What code DOES (actual behavior):** Flags ALL occurrences of a composite key as duplicates (not just subsequent rows). Rows with any null key column are NOT flagged (null != null). No records are deleted; flags are additive Int8 columns.

**Clinical context:** Composite keys (e.g., DIAGNOSIS: ID+DX_DATE+DX) identify exact duplicate records. Null DX_DATE means date wasn't recorded, so two diagnoses with null dates are NOT duplicates (they could be from different encounters).

**Impact on data correctness:** MEDIUM — If Polars `is_duplicated()` behavior changes to treat nulls as equal, dedup logic would incorrectly flag non-duplicates. Current behavior is correct.

**Confidence level:** MEDIUM — Polars behavior is correct today, but API stability not verified

**Recommended action:**
1. Add unit test confirming null keys don't match (test `is_duplicated()` with null composite keys)
2. Document null handling in `flag_duplicates()` docstring and DEDUP.md
3. Pin Polars version in environment.yml to prevent breaking changes

**Phase 2/3 follow-up:**
- TEST-03 (dedup tests): Add test for null key handling
- Validate against data: check if any tables have high null rates in key columns

---

### AUDIT-005: Dual-eligible detection incomplete when secondary payer absent

**Location:** `src/report/encounter_payer_summary.py:385`
**Code context:**
```python
# TODO(audit): When secondary is absent, dual-eligible forced to 0 even if primary is 14/141/142.
# Should check primary alone if secondary missing?
def _effective_payer(...):
    # If PAYER_TYPE_SECONDARY is null, dual_eligible = 0
    # But primary could be 14/141/142 (dual-eligible codes)
```

**Issue:** Dual-eligible detection uses both `PAYER_TYPE_PRIMARY` and `PAYER_TYPE_SECONDARY`. When secondary is null, dual-eligible is set to 0 even if primary is 14/141/142 (explicit dual-eligible codes). This may undercount true dual-eligible patients.

**What code DOES (actual behavior):** Dual-eligible = 1 if: (1) primary is 1 (Medicare) AND secondary is 2 (Medicaid), OR (2) primary is 14/141/142 (dual-eligible codes). If secondary is null, logic (1) fails even if patient has primary 1 (Medicare alone doesn't prove dual-eligible).

**Clinical context:** Dual-eligible patients (Medicare + Medicaid) are a critical population for health equity analysis. PCORnet codes 14/141/142 explicitly indicate dual-eligible status. If secondary payer is frequently missing but primary is 14/141/142, current logic undercounts dual-eligible patients.

**Impact on data correctness:** MEDIUM-HIGH — May undercount dual-eligible prevalence if secondary payer data is sparse. Affects insurance equity analyses.

**Confidence level:** MEDIUM — Logic is defensible (Medicare alone ≠ dual-eligible) but 14/141/142 codes should be sufficient alone

**Recommended action:**
1. Check data: What % of encounters have null PAYER_TYPE_SECONDARY?
2. Update logic: If primary is 14/141/142, set dual_eligible=1 regardless of secondary
3. Add tests for all dual-eligible combinations

**Phase 2/3 follow-up:**
- VAL-01 (payer validation): Check secondary payer completeness rates
- TEST-01 (payer logic tests): Test dual-eligible detection with null secondary

---

## MEDIUM Severity (Usability/Maintenance Impact)

### AUDIT-006: Pandas dependency in outcomes_flags.py (Polars codebase)

**Location:** `src/clean/outcomes_flags.py:34`, `src/clean/outcomes_flags.py:79`
**Code context:**
```python
import pandas as pd  # Line 9

# TODO(audit): Outcomes.csv uses pandas for CSV parsing in an otherwise Polars codebase.

# TODO(audit): Uses pandas for CSV parsing. Migrate to pl.read_csv() to remove pandas
# dependency and keep codebase Polars-first.
def load_outcomes_code_lookup(path: Path) -> dict:
    df = pd.read_csv(path)  # Line 44
```

**Issue:** `outcomes_flags.py` uses pandas for CSV reading (`pd.read_csv()`) in an otherwise Polars-first codebase. This adds pandas as a dependency and creates inconsistency.

**What code DOES (actual behavior):** Reads Outcomes.csv using pandas `read_csv()`, assumes columns are ["Modality", "Code system", "Code"] with forward-fill applied. Returns dict mapping (modality, code_system, code) to modality name.

**Clinical context:** Outcomes.csv defines treatment modality codes (Chemotherapy J-codes, Radiation CPTs, SCT CPTs) used to identify patients who received specific treatments. Critical for treatment-stratified analyses.

**Impact on data correctness:** LOW (functionality works correctly) — Correctness not affected, but adds maintenance burden (two CSV parsers), dependency bloat (pandas + polars), and inconsistency

**Confidence level:** HIGH — Code works but violates architecture principle (Polars-first)

**Recommended action:**
1. Replace `pd.read_csv()` with `pl.read_csv()`
2. Update `load_outcomes_code_lookup()` to use Polars API (select, group_by, etc.)
3. Remove pandas from environment.yml pip dependencies
4. Test with actual Outcomes.csv to ensure schema assumptions hold

**Phase 2/3 follow-up:**
- TEST-04 (modality flag tests): Add unit test for `load_outcomes_code_lookup()` using mock Outcomes.csv
- Refactor during Phase 2 or 3

---

### AUDIT-007: Small-cell suppression inconsistency (flag vs suppress)

**Location:** `scripts/build_insurance_summary.py:269`, `scripts/clean_all.py:110`
**Code context:**
```python
# Markdown tables use flag_small_cell() (adds ⚠ warning but keeps value visible)
lines.append(f"| {table_name} | {flag_small_cell(dup_count)} |")

# CSV files use _suppress() (replaces 1-10 with dash)
t1_csv = t1.with_columns(pl.col("N").map_batches(lambda s: pl.Series([_suppress(int(v)) for v in s])))
```

**Issue:** Report markdown tables use `flag_small_cell()` (adds ⚠ warning for counts 1-10 but value visible) while CSV outputs use `_suppress()` (replaces with dash). Inconsistent UX: users see flagged values in markdown but suppressed values in CSV.

**What code DOES (actual behavior):** `flag_small_cell()` returns "⚠ N" for 1 ≤ N ≤ 10. `_suppress()` returns "-" for 1 ≤ N ≤ 10. Both use SMALL_CELL_THRESHOLD=10 constant.

**Clinical context:** HIPAA requires suppression of counts 1-10 to prevent re-identification. Markdown reports (for internal review) allow viewing small counts with warning. CSV reports (for external sharing) must truly suppress.

**Impact on data correctness:** LOW — This is a design choice (show+warn vs suppress), not a bug. Markdown warnings help debugging; CSV suppression protects PHI.

**Confidence level:** HIGH — Intentional design, documented in REQ-05

**Recommended action:**
1. Document in CLEANING_DECISIONS.md: why markdown shows flagged values vs CSV suppresses
2. Consider adding "Internal Use Only" header to markdown reports
3. Centralize suppression logic in `src/report/suppression.py` to avoid code duplication

**Phase 2/3 follow-up:**
- TEST-03 (report tests): Add test verifying all CSV outputs use `_suppress()`, all markdown uses `flag_small_cell()`
- Phase 4: Centralize suppression logic (code cleanup, not correctness issue)

---

### AUDIT-008: src/clean/validate/ near-duplication of src/validate/

**Location:** `src/clean/validate/cohort.py:23`, `src/clean/validate/structural.py:25`, `src/clean/validate/values.py:32`, `src/clean/validate/__init__.py:19`
**Code context:**
```python
# src/clean/validate/cohort.py
**TODO(audit): Near-duplication with src/validate/cohort.py**
# Function-level duplication: verify_hl_cohort, detect_dx_format, etc.

# src/clean/validate/structural.py
**TODO(audit): Near-duplication with src/validate/structural.py**
# Constant duplication: PATID_LINKED_TABLES, TUMOR_REGISTRY_TABLES, etc.

# src/clean/validate/values.py
**TODO(audit): Near-duplication with src/validate/values.py**
# Value set validation logic duplicated

# src/clean/validate/__init__.py
**TODO(audit): Near-duplication with src/validate/**
# Entire module duplicated under src/clean/
```

**Issue:** `src/clean/validate/` directory is near-duplicate of `src/validate/`. Both contain cohort.py, structural.py, values.py with similar (but not identical) functions and constants. Unclear which is authoritative; changes to one don't propagate to the other.

**What code DOES (actual behavior):** Scripts import from both locations: `validate_all.py` imports from `src/validate/`, `clean_all.py` imports from `src/clean/validate/`. Each works but divergence risk is high.

**Clinical context:** Validation logic (HL cohort identification, PCORnet value sets, structural checks) is foundational. Divergent implementations risk inconsistent results across pipeline phases.

**Impact on data correctness:** MEDIUM — Currently working but maintenance burden doubles; bug fixes may only apply to one copy

**Confidence level:** HIGH — Directory structure inspection confirms duplication

**Recommended action:**
1. Audit differences between `src/validate/` and `src/clean/validate/` (git diff, function-by-function comparison)
2. If identical: delete `src/clean/validate/`, update imports to use `src/validate/`
3. If divergent: document why divergence needed (e.g., phase-specific logic) or refactor to shared + phase-specific modules
4. Add CI check preventing future duplication

**Phase 2/3 follow-up:**
- Phase 2: Audit differences, document divergence or consolidate
- TEST-02 (structural tests): Add test ensuring validation logic is consistent

---

### AUDIT-009: Date parsing fallback: no parse failure rate reporting

**Location:** `src/load/convert.py:81-150`
**Code context:**
```python
def detect_date_columns(...):
    # 4-format fallback: DATETIME_RE → DATE9_RE → YYYYMMDD_RE → MM/DD/YYYY
    # Silently keeps unparsed dates as strings
    # No reporting of parse failure rate per format
```

**Issue:** `detect_date_columns()` uses 4-format fallback but silently keeps unparsed dates as strings without reporting parse failure rate. If >10% of dates fail to parse, dates treated as strings in groupby operations, breaking temporal logic.

**What code DOES (actual behavior):** Tries each format in order; uses first match. If all formats fail, column remains String dtype. No warning printed. Parse success tracked at column level (pct_matched for auto-detection) but not reported to user.

**Clinical context:** Date parsing errors (mixed formats, non-English month abbreviations, 2-digit years) break temporal validation (events before birth, after death) and cohort selection (2+ encounters on different dates).

**Impact on data correctness:** MEDIUM — >10% parse failures go unnoticed; dates treated as strings break temporal logic

**Confidence level:** MEDIUM — No known failures but failure rate not monitored

**Recommended action:**
1. Add parse failure threshold check: if >10% fail, log warning and report which formats tried
2. Add per-format success rate to file_inventory.csv
3. Fallback to String dtype with warning if all formats fail

**Phase 2/3 follow-up:**
- TEST-02 (date parsing tests): Add tests for mixed formats, partial dates, non-English months
- VAL-03 (date validation): Add check for String columns that look like dates (name contains "DATE" but dtype is String)

---

### AUDIT-010: VITAL dedup key uses only MEASURE_DATE without vital type

**Location:** `src/clean/dedup.py:43`
**Code context:**
```python
# TODO(audit): VITAL uses only MEASURE_DATE without vital type (HT/WT/BP/etc) — may flag
# same-day vitals of different types (HT and WT on same date) as duplicates if ID+date match.
DEDUP_KEYS = {
    "VITAL": ["ID", "MEASURE_DATE"],  # Missing: VITAL_SOURCE or vital-type discriminator
    ...
}
```

**Issue:** VITAL table dedup key is ["ID", "MEASURE_DATE"] without vital type (HT, WT, SYSTOLIC, DIASTOLIC). Same-day vitals of different types (e.g., HT and WT measured on same encounter) will be flagged as duplicates.

**What code DOES (actual behavior):** Flags ALL rows with same (ID, MEASURE_DATE) as duplicates, regardless of vital type. Two distinct vitals (HT, WT) on same date → both flagged.

**Clinical context:** Vitals are typically measured together (HT + WT + BP on same encounter). Flagging all same-day vitals as duplicates is incorrect — they're distinct measurements.

**Impact on data correctness:** MEDIUM — Overcounts duplicate vitals; flags legitimate same-day multi-vital measurements

**Confidence level:** HIGH — Composite key is missing vital type discriminator

**Recommended action:**
1. Check VITAL schema: Does it have VITAL_SOURCE or vital-type column?
2. Update DEDUP_KEYS to include vital-type column: `["ID", "MEASURE_DATE", "VITAL_SOURCE"]`
3. If no vital-type column: dedup by (ID, MEASURE_DATE, HT, WT, SYSTOLIC, DIASTOLIC) — exact value match

**Phase 2/3 follow-up:**
- VAL-02 (schema validation): Check if VITAL has vital-type column
- TEST-03 (dedup tests): Add test for same-day multi-vital scenario

---

## LOW Severity (Nice-to-Have)

### AUDIT-011: No logging framework (print-only)

**Location:** All scripts in `scripts/` and `src/`
**Issue:** Scripts use `print()` for all logging; no log levels, no option to write to file, no structured logging, no timestamps

**What code DOES (actual behavior):** Prints progress messages to stdout. HPC runs redirect stdout to log files manually (`python script.py > log.txt 2>&1`).

**Impact on data correctness:** NONE (usability issue only) — No effect on correctness, but difficult to capture HPC run output for debugging

**Recommended action:** Add logging configuration (e.g., Python `logging` module) with levels (DEBUG, INFO, WARN, ERROR), file output option, and timestamps

**Phase 2/3 follow-up:** Phase 4 (setup): Add logging framework

---

### AUDIT-012: No incremental conversion (re-reads all CSVs)

**Location:** `scripts/convert_all.py`
**Issue:** `convert_all.py` converts all CSVs to Parquet every run, even if CSV hasn't changed (checked by mtime)

**What code DOES (actual behavior):** Sequential processing of all tables; skips conversion if parquet.mtime > csv.mtime (mtime check exists in code but not advertised)

**Impact on data correctness:** NONE (performance issue only) — Large datasets (100K+ rows per table) re-convert unnecessarily; 10+ minute runs on repeated executions

**Recommended action:** Add skip-if-exists logic clearly documented; add `--force` flag to override

**Phase 2/3 follow-up:** Phase 4: Add incremental conversion

---

### AUDIT-013: Partner abbreviations not verified with current data sources

**Location:** `src/clean/harmonize.py:43`
**Code context:**
```python
# TODO(audit): Verify partner abbreviations (AMS, UMI, FLM, VRT) match current data sources.
PARTNER_FLAGS = {
    "ICD_MAPPED": {"AMS", "UMI"},  # Assume these are current
    "CLAIMS_ONLY": {"FLM"},
    "DEATH_ONLY": {"VRT"},
}
```

**Issue:** Partner abbreviations (AMS, UMI, FLM, VRT) hardcoded but not verified against actual SOURCE column values in data

**What code DOES (actual behavior):** Adds partner flags based on SOURCE column exact match. If SOURCE uses different abbreviations (e.g., "AMC" instead of "AMS"), flags won't be added.

**Impact on data correctness:** LOW — Flags are provenance metadata, not critical for analyses. But missing flags reduce utility.

**Recommended action:** Query actual SOURCE values from DEMOGRAPHIC or ENCOUNTER; update PARTNER_FLAGS to match

**Phase 2/3 follow-up:** VAL-01: Add check for unrecognized SOURCE values

---

### AUDIT-014: Outcomes.csv schema fragility (no validation)

**Location:** `src/clean/outcomes_flags.py:44-76`
**Code context:**
```python
def load_outcomes_code_lookup(path: Path) -> dict:
    df = pd.read_csv(path)
    # Assumes columns are exactly ["Modality", "Code system", "Code"] with forward-fill
    # No schema validation; if columns renamed or reordered, function silently produces empty lookup dict
```

**Issue:** Function assumes Outcomes.csv columns are exactly ["Modality", "Code system", "Code"] with forward-fill applied. No schema validation. If columns renamed or reordered, function silently produces empty lookup dict.

**What code DOES (actual behavior):** Reads CSV with pandas, fills forward modality column, returns dict. If schema wrong, returns empty dict → modality flags not added.

**Impact on data correctness:** LOW — If schema changes, modality flags will be silently missing. But Outcomes.csv is infrequently updated.

**Recommended action:**
1. Add schema check at top of `load_outcomes_code_lookup()`
2. Raise ValueError if columns missing
3. Document expected column order in docstring

**Phase 2/3 follow-up:** TEST-04 (modality tests): Add test with wrong schema (should raise ValueError)

---

### AUDIT-015: SCT_CPTS constant includes radiation CPTs (774xx)

**Location:** `src/report/quality_report.py:95`
**Code context:**
```python
# TODO(audit): This constant includes radiation CPTs (774xx) but is named SCT_CPTS. Consider
# renaming to TREATMENT_CPTS or separating into SCT_CPTS and RADIATION_CPTS.
SCT_CPTS = {
    "38240", "38241", "38242",  # SCT codes
    "77401", "77402", "77407", "77412", "77427",  # Radiation codes (not SCT)
}
```

**Issue:** `SCT_CPTS` constant includes both stem cell transplant CPTs (382xx) and radiation CPTs (774xx). Naming is misleading.

**What code DOES (actual behavior):** Uses constant to identify treatment encounters (both SCT and radiation). Works correctly but naming is confusing.

**Impact on data correctness:** NONE (naming issue only) — Functionally correct but misleading variable name

**Recommended action:** Rename to `TREATMENT_CPTS` or separate into `SCT_CPTS` and `RADIATION_CPTS`

**Phase 2/3 follow-up:** Phase 4: Refactor constant naming (code cleanup)

---

### AUDIT-016: VITAL/LAB ranges may be too permissive (unit conversion errors undetected)

**Location:** `src/validate/values.py:26`, `src/validate/values.py:44`
**Code context:**
```python
# TODO(audit): Are these ranges too permissive? Check for unit conversion errors (HT in mm, WT in lbs vs kg)
VITAL_RANGES = {
    "HT": (0, 300),  # cm — but what if HT is in mm (0-3000)?
    "WT": (0, 500),  # kg — but what if WT is in lbs (0-1100)?
    ...
}

# TODO(audit): Validate these ranges against actual distribution in HL cohort. Are maxes too permissive?
HL_LAB_RANGES = {
    "1751-7": {"name": "Albumin", "min": 0, "max": 10, "unit": "g/dL"},
    ...
}
```

**Issue:** VITAL ranges may be too permissive. HT max is 300 cm (10 feet) but if data is in mm, real max is 3000 mm (3 meters). WT max is 500 kg but if data is in lbs, real max is 1100 lbs (500 kg).

**What code DOES (actual behavior):** Flags HT >300 or WT >500. If units are wrong (mm instead of cm, lbs instead of kg), ranges don't catch unit conversion errors.

**Impact on data correctness:** LOW — Unit conversion errors would be caught as out-of-range, but ranges may be too permissive to catch all errors

**Recommended action:**
1. Check actual vital/lab distributions in HL cohort
2. Tighten ranges if appropriate (e.g., HT 50-250 cm for adults)
3. Add unit column validation (check VITAL_SOURCE, RESULT_UNIT for expected units)

**Phase 2/3 follow-up:** VAL-01 (vital validation): Check actual distributions, adjust ranges

---

### AUDIT-017: 30-day payer-at-treatment window is arbitrary

**Location:** `src/report/encounter_payer_summary.py:81`
**Code context:**
```python
# TODO(audit): 30-day window is arbitrary — no clinical standard. Consider sensitivity analysis
# (15 days, 60 days, 90 days) to check robustness.
PAYER_AT_TREATMENT_WINDOW_DAYS: int = 30
```

**Issue:** 30-day window for "payer around treatment" dates is arbitrary — no clinical standard. Chosen pragmatically but not validated.

**What code DOES (actual behavior):** For each treatment date, finds payer within ±30 days. Takes mode of valid (non-missing) payers in window.

**Impact on data correctness:** LOW — Window size affects payer assignment for ~5-10% of encounters (those with payer changes). Sensitivity analysis needed to check robustness.

**Recommended action:** Run sensitivity analysis with 15, 30, 60, 90 day windows. Document rationale for chosen window. Report payer stability across windows.

**Phase 2/3 follow-up:** TEST-01 (payer tests): Add sensitivity analysis test

---

### AUDIT-018: 1900-01-01 birth dates: masked or legitimate?

**Location:** `src/load/convert.py:90`
**Code context:**
```python
# TODO(audit): Are there legitimate 1900-01-01 birth dates or are they all masked values?
MASKED_BIRTH_DATE = date(1900, 1, 1)
```

**Issue:** Code assumes 1900-01-01 birth dates are masked values (HIPAA de-identification). But there could be legitimate 1900-01-01 births (patients born on that date).

**What code DOES (actual behavior):** Treats 1900-01-01 as masked, excludes from before-birth validation, attempts recovery from TUMOR_REGISTRY.AGE_AT_DIAGNOSIS.

**Impact on data correctness:** LOW — Extremely unlikely a patient in the cohort was born on exactly 1900-01-01 (would be 126 years old in 2026). But possible.

**Recommended action:** Check data: are there any 1900-01-01 births? If none, document assumption. If any, flag for manual review.

**Phase 2/3 follow-up:** VAL-01 (date validation): Check for 1900-01-01 births, flag if found

---

## Phase 2/3 Mapping

**Phase 2 (Validation): VAL-01 through VAL-04**

- VAL-01 (row count validation): AUDIT-005 (dual-eligible prevalence check), AUDIT-013 (partner abbreviations), AUDIT-016 (vital/lab distribution checks), AUDIT-018 (1900-01-01 birth date check)
- VAL-02 (schema validation): AUDIT-003 (LAB_RESULT_CM alias resolution), AUDIT-010 (VITAL schema check for vital-type column)
- VAL-03 (configuration validation): AUDIT-001 (99/9999 payer flag documentation), AUDIT-009 (date parse failure reporting)
- VAL-04 (small-cell suppression validation): AUDIT-007 (flag_small_cell vs _suppress consistency check)

**Phase 3 (Testing): TEST-01 through TEST-04**

- TEST-01 (payer logic tests): AUDIT-001 (99/9999 handling), AUDIT-005 (dual-eligible detection), AUDIT-017 (payer window sensitivity)
- TEST-02 (date parsing tests): AUDIT-002 (date auto-detection thresholds), AUDIT-009 (parse failure handling)
- TEST-03 (dedup and report tests): AUDIT-004 (null key handling), AUDIT-007 (suppression consistency), AUDIT-010 (VITAL dedup key)
- TEST-04 (checkpoint and modality tests): AUDIT-006 (pandas to Polars migration), AUDIT-014 (Outcomes.csv schema validation)

**Phase 4 (Setup/Infrastructure): SETUP-01 through SETUP-04**

- SETUP-01 (environment): AUDIT-006 (remove pandas dependency), AUDIT-011 (logging framework)
- SETUP-02 (documentation): AUDIT-007 (document suppression strategy), AUDIT-008 (document src/validate/ vs src/clean/validate/ divergence)
- SETUP-03 (code cleanup): AUDIT-008 (consolidate validation modules), AUDIT-015 (rename SCT_CPTS constant)
- SETUP-04 (performance): AUDIT-012 (incremental conversion)

---

**Total Audit Items:** 18 (5 HIGH, 5 MEDIUM, 8 LOW)

**Next Steps:**
1. Review with domain expert: AUDIT-001 (99/9999 semantics), AUDIT-017 (30-day window)
2. Check actual data: AUDIT-002 (date detection), AUDIT-005 (dual-eligible prevalence), AUDIT-010 (VITAL schema), AUDIT-013 (partner abbreviations), AUDIT-016 (vital/lab distributions), AUDIT-018 (1900-01-01 births)
3. Prioritize for Phase 2: HIGH severity items (AUDIT-001 through AUDIT-005)
4. Defer to Phase 4: LOW severity items (AUDIT-011 through AUDIT-018)
