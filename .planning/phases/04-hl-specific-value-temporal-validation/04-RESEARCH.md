# Phase 4: HL-Specific Value & Temporal Validation - Research

**Researched:** 2026-02-27
**Domain:** PCORnet CDM value set validation, clinical plausibility, ICD concordance, temporal consistency, HL-specific clinical rules
**Confidence:** HIGH

## Summary

Phase 4 transforms the Parquet files from Phase 2 by adding binary validation flag columns (0/1) across multiple validation dimensions: PCORnet CDM value set conformance, vital sign and lab plausibility, ICD version-date concordance, temporal consistency, tumor registry validation, and insurance field validation. The phase validates and flags — it does not delete, correct, or impute data.

The technical approach builds on the existing codebase pattern: Polars lazy evaluation for memory-efficient processing of large tables, the `valuesets.csv` file (15,194 rows of PCORnet code-to-label mappings across ~90 TABLE_NAME+FIELD_NAME combinations) for coded field validation, and the HL-specific ICD code sets already defined in `cohort.py`. The major new complexities are: (1) value set validation requires building a lookup structure from `valuesets.csv` and checking every coded field in every table, (2) ICD concordance must handle a grace period around Oct 2015 and auto-detect mapped partners, (3) lab plausibility requires LOINC-specific ranges grouped by RESULT_UNIT, and (4) temporal consistency spans multiple tables with masked birth date handling. All results are written back as additional columns to the existing Parquet files.

The architecture follows a validation-function-per-domain pattern: each validation domain (value sets, plausibility, concordance, temporal) is implemented as a set of functions in `src/validate/values.py` that take a Parquet path, apply checks, and return the DataFrame with flag columns added. A new entry-point script orchestrates calling these functions across all tables and generates the reports.

**Primary recommendation:** Structure `src/validate/values.py` with one function per validation domain (value_set_check, vital_plausibility, lab_plausibility, icd_concordance, temporal_checks, tumor_registry_checks, insurance_checks), each returning a DataFrame with new flag columns. The entry-point script iterates over tables, applies relevant checks, writes back Parquet, and accumulates report data.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Validation Flag Strategy:**
- Storage: Add flag columns directly to Parquet files — each row gets binary (0/1) flag columns per check type (e.g., `_val_code`, `_val_range`, `_val_temporal`).
- Granularity: Binary pass/fail (0 or 1) per check type. Not coded issue types or free-text notes.
- Write-back: Overwrite existing Parquet files from Phase 2 — add flag columns to the same files. No separate validated directory.
- Downstream use: Flags are for context only — understanding data quality. Not for automatic exclusion.

**ICD Concordance Rules:**
- Cutover date: Grace period — allow overlap around Oct 2015.
- Exempt partners: Claude's discretion — auto-detect which partners likely mapped ICD-9 to ICD-10 based on data patterns. AMS and UMI are known mappers.
- Scope: All diagnosis codes, not just HL codes — comprehensive ICD concordance across full DIAGNOSIS table.
- Output: Both CSV (`icd_concordance.csv`) with per-partner breakdown AND a report section.

**Plausibility Thresholds:**
- Vital sign ranges: Claude's discretion — clinically reasonable.
- Lab ranges: Wide biological ranges — only flag truly impossible values. Not clinical reference ranges.
- Missing RESULT_UNIT: Flag as a separate validation issue.
- Tumor registry validation depth: Claude's discretion.

**Temporal Logic:**
- Same-day admit/discharge: Always flag.
- Future date cutoff: Dec 2025.
- Masked birth dates: When BIRTH_DATE = 1900-01-01, use AGE_AT_DIAGNOSIS from TUMOR_REGISTRY when available.
- HL disease timeline: 0-365 days from first HL diagnosis to first treatment.

### Claude's Discretion
- Vital sign plausibility thresholds (within clinically reasonable bounds)
- Tumor registry validation depth (format-only vs HL-specific histology/staging)
- Which partners to auto-detect as ICD-9→ICD-10 mappers (beyond known AMS, UMI)
- Exact flag column naming convention

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REQ-02 | Convert SAS date formats to standard dates (dates already converted in Phase 2 — validate them here) | Temporal validation checks confirm dates fall within plausible ranges; validate converted date columns haven't introduced errors; BIRTH_DATE masking detection at 1900-01-01 |
| REQ-03 | Clean data for HL insurance inequities analysis | HL diagnosis code validation, ICD concordance for complete diagnosis picture, vital/lab plausibility for outcome data, tumor registry staging validation, insurance/payer validation against CDM value sets, HL disease timeline checks |
| REQ-04 | Run on HiPerGator HPC | Polars lazy evaluation for memory efficiency; table-at-a-time processing pattern; same SLURM resource allocation as Phase 3 (64GB, 2hr) |
| REQ-05 | HIPAA-compliant data handling | Reports contain aggregate counts only; small-cell flagging on report outputs; data stays on `/blue` and `/orange`; flag columns added in-place to existing Parquet files |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Polars | 1.22.0+ | DataFrame manipulation, value set joins, temporal arithmetic, flag column creation | Already installed; lazy evaluation for memory-efficient processing; `scan_parquet()` + `collect()` pattern established in Phase 3 |
| Python | 3.11 | Runtime | Already in hl-eda env; stdlib `pathlib`, `re`, `csv`, `datetime` |

### Supporting (already installed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| DuckDB | 1.4.4+ | Optional complex cross-table temporal joins | Alternative for multi-table temporal validation if Polars joins become unwieldy; already installed |

### No Additional Dependencies Needed

Phase 4 uses only Polars (already installed) plus Python stdlib. The `valuesets.csv` is parsed with Polars `read_csv()`. All report generation uses Python string formatting.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Polars value set join | DuckDB SQL | DuckDB enables SQL-style semi-joins for value set validation but adds SQL string construction; Polars `is_in()` is simpler for categorical checks |
| Manual range checks | Great Expectations | Over-engineered for binary flag columns on Parquet; adds unnecessary dependency |
| Per-column flag approach | Single composite flag | User locked decision says binary per check type — separate flags needed |

## Architecture Patterns

### Recommended Project Structure (Phase 4 additions)

```
src/
├── load/
│   ├── config.py           # existing — Paths dataclass
│   ├── schema.py           # existing — datastructure.txt parser
│   └── convert.py          # existing — Phase 2
└── validate/
    ├── __init__.py          # existing
    ├── structural.py        # existing — Phase 3
    ├── cohort.py            # existing — Phase 3
    └── values.py            # NEW — value set, plausibility, temporal, ICD concordance
scripts/
├── validate_all.py          # existing — Phase 3 entry point
└── validate_values.py       # NEW — Phase 4 entry point
reports/                     # output directory
├── structural_validation.md # existing — Phase 3
├── value_validation.md      # NEW — Phase 4 main report
├── icd_concordance.csv      # NEW — per-partner ICD version analysis
├── temporal_issues.csv      # NEW — temporal violation summary
└── tumor_registry_validation.csv  # NEW — TR-specific findings
```

### Pattern 1: Value Set Validation via Lookup Table

**What:** Build a lookup dictionary from `valuesets.csv` keyed by `(TABLE_NAME, FIELD_NAME)` → `set(VALUESET_ITEM)`, then for each coded field in each table, flag rows where the value is not in the allowed set (treating NI/UN/OT/null as valid missing).

**When to use:** Every coded/categorical field in every CDM table.

**Implementation:**

```python
import polars as pl
from pathlib import Path

def build_valueset_lookup(valuesets_path: Path) -> dict[tuple[str, str], set[str]]:
    """Build {(TABLE, FIELD): {valid_values}} from valuesets.csv."""
    vs = pl.read_csv(valuesets_path)
    lookup: dict[tuple[str, str], set[str]] = {}
    for row in vs.iter_rows(named=True):
        key = (row["TABLE_NAME"], row["FIELD_NAME"])
        lookup.setdefault(key, set()).add(row["VALUESET_ITEM"])
    return lookup


def validate_coded_fields(
    df: pl.DataFrame,
    table_name: str,
    lookup: dict[tuple[str, str], set[str]],
) -> pl.DataFrame:
    """Add _val_code flag for each coded field with invalid values.

    Flag = 1 when value is non-null, non-empty, and not in value set.
    NI/UN/OT are always valid (they're PCORnet missing codes).
    """
    ALWAYS_VALID = {"NI", "UN", "OT", "", None}

    for col in df.columns:
        key = (table_name, col)
        if key not in lookup:
            continue
        valid = lookup[key] | ALWAYS_VALID
        flag_col = f"{col}_val_code"
        df = df.with_columns(
            pl.when(
                pl.col(col).is_null()
                | pl.col(col).is_in(valid)
            )
            .then(pl.lit(0))
            .otherwise(pl.lit(1))
            .cast(pl.Int8)
            .alias(flag_col)
        )
    return df
```

**Key insight:** The `valuesets.csv` has 15,194 rows across ~90 table+field combinations. Not every column in every table has a value set — only coded/categorical fields. The lookup naturally handles this by skipping columns without entries.

### Pattern 2: Vital Sign Plausibility Ranges

**What:** Apply clinically reasonable plausibility ranges to vital sign measurements and flag values outside those ranges.

**Discretion recommendation — Vital sign thresholds:**

| Measure | Column | Min | Max | Clinical Rationale |
|---------|--------|-----|-----|-------------------|
| Height (cm) | HT | 50 | 272 | 50cm = short child/wheelchair; 272cm = tallest recorded human |
| Weight (kg) | WT | 1 | 500 | 1kg = premature infant; 500kg = extreme obesity |
| Systolic BP | SYSTOLIC | 40 | 300 | 40 = severe shock; 300 = hypertensive crisis |
| Diastolic BP | DIASTOLIC | 20 | 200 | 20 = severe shock; 200 = extreme hypertension |
| BMI | ORIGINAL_BMI | 8 | 100 | 8 = extreme emaciation; 100 = extreme obesity |

These are wider than HL-EDA's `quality.py` ranges (HT 50-250, WT 2-500) to minimize false positives. Values outside these ranges represent likely data entry errors or unit confusion, not clinically plausible measurements.

```python
VITAL_RANGES: dict[str, tuple[float, float]] = {
    "HT": (50.0, 272.0),
    "WT": (1.0, 500.0),
    "SYSTOLIC": (40.0, 300.0),
    "DIASTOLIC": (20.0, 200.0),
    "ORIGINAL_BMI": (8.0, 100.0),
}

def validate_vital_plausibility(df: pl.DataFrame) -> pl.DataFrame:
    """Add _val_range flag for implausible vital sign values."""
    for col, (lo, hi) in VITAL_RANGES.items():
        if col not in df.columns:
            continue
        flag_col = f"{col}_val_range"
        df = df.with_columns(
            pl.when(
                pl.col(col).is_null()
                | (pl.col(col).ge(lo) & pl.col(col).le(hi))
            )
            .then(pl.lit(0))
            .otherwise(pl.lit(1))
            .cast(pl.Int8)
            .alias(flag_col)
        )
    return df
```

### Pattern 3: Lab Result Plausibility (Wide Biological Ranges)

**What:** Flag truly impossible lab values per LOINC code. Per locked decision: wide biological ranges only, not clinical reference ranges.

**Discretion recommendation — HL-relevant lab ranges:**

| Lab | LOINC Codes | Min | Max | Unit | Rationale |
|-----|-------------|-----|-----|------|-----------|
| WBC | 6690-2, 26464-8 | 0 | 500 | 10^3/uL | 0 = aplastic; 500 = extreme leukocytosis |
| Hemoglobin | 718-7, 30313-1 | 0 | 30 | g/dL | 0 = error; 30 = physiologically impossible |
| Platelets | 777-3, 26515-7 | 0 | 5000 | 10^3/uL | 0 = severe thrombocytopenia; 5000 = extreme |
| ALT | 1742-6 | 0 | 50000 | U/L | 0 = error; 50000 = extreme hepatotoxicity |
| AST | 1920-8 | 0 | 50000 | U/L | Same rationale |
| ALP | 6768-6 | 0 | 10000 | U/L | 0 = error; 10000 = extreme elevation |
| Bilirubin (total) | 1975-2 | 0 | 100 | mg/dL | 0 = error; 100 = extreme hepatic failure |
| TSH | 11580-8 | 0 | 500 | mIU/L | 0 = thyrotoxicosis; 500 = extreme hypothyroid |
| ESR | 4537-7 | 0 | 200 | mm/hr | 0 = normal; 200 = extreme inflammation |
| CRP | 1988-5 | 0 | 500 | mg/L | 0 = normal; 500 = severe sepsis |

**Key implementation detail:** Lab plausibility MUST check RESULT_UNIT before applying ranges. A hemoglobin of 150 is impossible in g/dL but correct in g/L. Per locked decision, missing RESULT_UNIT is flagged separately.

```python
HL_LAB_RANGES: dict[str, dict] = {
    "6690-2":  {"name": "WBC",         "min": 0, "max": 500,   "unit": "10*3/uL"},
    "718-7":   {"name": "Hemoglobin",  "min": 0, "max": 30,    "unit": "g/dL"},
    "777-3":   {"name": "Platelets",   "min": 0, "max": 5000,  "unit": "10*3/uL"},
    "1742-6":  {"name": "ALT",         "min": 0, "max": 50000, "unit": "U/L"},
    "1920-8":  {"name": "AST",         "min": 0, "max": 50000, "unit": "U/L"},
    "6768-6":  {"name": "ALP",         "min": 0, "max": 10000, "unit": "U/L"},
    "1975-2":  {"name": "Bilirubin",   "min": 0, "max": 100,   "unit": "mg/dL"},
    "11580-8": {"name": "TSH",         "min": 0, "max": 500,   "unit": "mIU/L"},
    "4537-7":  {"name": "ESR",         "min": 0, "max": 200,   "unit": "mm/hr"},
    "1988-5":  {"name": "CRP",         "min": 0, "max": 500,   "unit": "mg/L"},
}

def validate_lab_plausibility(df: pl.DataFrame) -> pl.DataFrame:
    """Add _val_range flag for implausible lab results.

    Only applies range checks when LAB_LOINC matches a known code.
    Flags missing RESULT_UNIT separately as _val_unit_missing.
    """
    if "LAB_LOINC" not in df.columns or "RESULT_NUM" not in df.columns:
        return df

    loinc_set = set(HL_LAB_RANGES.keys())

    # Flag: missing RESULT_UNIT on rows with numeric results
    if "RESULT_UNIT" in df.columns:
        df = df.with_columns(
            pl.when(
                pl.col("RESULT_NUM").is_not_null()
                & (pl.col("RESULT_UNIT").is_null() | (pl.col("RESULT_UNIT") == ""))
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
            .alias("RESULT_UNIT_val_missing")
        )

    # Flag: implausible RESULT_NUM for known LOINCs
    range_flag = pl.lit(0).cast(pl.Int8)
    for loinc, info in HL_LAB_RANGES.items():
        range_flag = pl.when(
            pl.col("LAB_LOINC").eq(loinc)
            & pl.col("RESULT_NUM").is_not_null()
            & (
                pl.col("RESULT_NUM").lt(info["min"])
                | pl.col("RESULT_NUM").gt(info["max"])
            )
        ).then(pl.lit(1).cast(pl.Int8)).otherwise(range_flag)

    df = df.with_columns(range_flag.alias("RESULT_NUM_val_range"))

    return df
```

### Pattern 4: ICD Version-Date Concordance

**What:** Flag diagnosis records where the ICD version (inferred from DX code prefix or DX_TYPE) is inconsistent with the DX_DATE relative to the Oct 2015 ICD-10 transition.

**Key complexity:** Grace period around Oct 2015, partner auto-detection for mapped codes.

**Auto-detection strategy for mapped partners:** A partner that has >95% ICD-10 codes (C/D/E/etc. prefixes) AND has data before Oct 2015 is likely a mapper. Specifically: if a partner has pre-2015 records AND zero or near-zero ICD-9 codes, they mapped ICD-9→ICD-10.

```python
import polars as pl
from datetime import date

ICD10_TRANSITION = date(2015, 10, 1)
GRACE_START = date(2015, 7, 1)   # 3 months before
GRACE_END = date(2016, 1, 1)     # 3 months after

def detect_mapped_partners(
    df: pl.DataFrame,
    partner_col: str = "SOURCE",
) -> set[str]:
    """Auto-detect partners that mapped ICD-9 to ICD-10.

    Criteria: partner has pre-Oct-2015 data AND >95% ICD-10 codes.
    """
    if partner_col not in df.columns or "DX_DATE" not in df.columns:
        return set()

    pre_transition = df.filter(
        pl.col("DX_DATE").is_not_null()
        & (pl.col("DX_DATE") < ICD10_TRANSITION)
    )

    if pre_transition.is_empty():
        return set()

    icd_version = pl.when(
        pl.col("DX").str.to_uppercase().str.contains(r"^[A-Z]")
    ).then(pl.lit("ICD10")).otherwise(pl.lit("ICD9"))

    partner_stats = (
        pre_transition
        .with_columns(icd_version.alias("_icd_ver"))
        .group_by(partner_col)
        .agg(
            pl.len().alias("total"),
            pl.col("_icd_ver").eq("ICD10").sum().alias("icd10_count"),
        )
        .with_columns(
            (pl.col("icd10_count") / pl.col("total")).alias("icd10_pct")
        )
        .filter(pl.col("icd10_pct") > 0.95)
    )

    return set(partner_stats[partner_col].to_list())


def validate_icd_concordance(
    df: pl.DataFrame,
    mapped_partners: set[str],
    partner_col: str = "SOURCE",
) -> pl.DataFrame:
    """Flag ICD version-date concordance violations.

    Rules:
    - ICD-9 code (DX starts with digit, DX_TYPE=09) after GRACE_END: flag=1
    - ICD-10 code (DX starts with letter, DX_TYPE=10) before GRACE_START: flag=1
      UNLESS partner is in mapped_partners
    - Grace period (GRACE_START to GRACE_END): never flag
    - Missing DX_DATE: don't flag
    """
    if "DX" not in df.columns or "DX_DATE" not in df.columns:
        return df

    is_icd10 = pl.col("DX").str.to_uppercase().str.contains(r"^[A-Z]")
    is_icd9 = ~is_icd10

    in_grace = (
        pl.col("DX_DATE").ge(GRACE_START)
        & pl.col("DX_DATE").lt(GRACE_END)
    )

    is_mapped = (
        pl.col(partner_col).is_in(mapped_partners)
        if partner_col in df.columns and mapped_partners
        else pl.lit(False)
    )

    flag = pl.when(pl.col("DX_DATE").is_null()).then(pl.lit(0))
    flag = flag.when(in_grace).then(pl.lit(0))
    flag = flag.when(
        is_icd9 & pl.col("DX_DATE").ge(GRACE_END)
    ).then(pl.lit(1))
    flag = flag.when(
        is_icd10 & pl.col("DX_DATE").lt(GRACE_START) & ~is_mapped
    ).then(pl.lit(1))
    flag = flag.otherwise(pl.lit(0))

    df = df.with_columns(flag.cast(pl.Int8).alias("DX_val_icd_concordance"))

    return df
```

### Pattern 5: Temporal Consistency Checks

**What:** Validate date relationships across and within tables.

**Checks per table:**

| Table | Check | Flag Name |
|-------|-------|-----------|
| ENCOUNTER | DISCHARGE_DATE >= ADMIT_DATE | `_val_admit_discharge` |
| ENCOUNTER | ADMIT_DATE == DISCHARGE_DATE (same-day) | `_val_same_day` |
| All with dates | No date > Dec 31, 2025 | `_val_future_date` |
| All with dates | Clinical date >= BIRTH_DATE (skip if masked) | `_val_before_birth` |
| All with dates | Clinical date <= DEATH_DATE (when present) | `_val_after_death` |
| ENROLLMENT | ENR_START_DATE <= ENR_END_DATE | `_val_enr_dates` |
| Cross-table | First HL DX → first treatment: 0-365 days | Reported in summary, not per-row flag |

**Masked birth date handling:**

```python
MASKED_BIRTH_DATE = date(1900, 1, 1)
FUTURE_CUTOFF = date(2025, 12, 31)

def is_birth_masked(birth_date_col: pl.Expr) -> pl.Expr:
    """Detect masked birth dates (01JAN1900)."""
    return birth_date_col.eq(pl.lit(MASKED_BIRTH_DATE))
```

For patients with masked BIRTH_DATE, the temporal check against birth needs AGE_AT_DIAGNOSIS from TUMOR_REGISTRY. This is a cross-table operation:
1. Load TUMOR_REGISTRY1 and extract `(ID, AGE_AT_DIAGNOSIS, DATE_OF_DIAGNOSIS)`
2. For masked patients, compute approximate birth year as `DATE_OF_DIAGNOSIS.year - AGE_AT_DIAGNOSIS`
3. Use this approximate birth year for temporal checks

### Pattern 6: Tumor Registry Validation

**Discretion recommendation — Depth: HL-specific histology/staging verification (not just format checks).**

**Rationale:** Since only 3 partners (ORL, TMH, UFH) have tumor registry data, the dataset is small enough for deeper validation. The HL-specific checks are clinically meaningful for the insurance inequities study.

| Check | Field(s) | Valid Values | Flag |
|-------|----------|-------------|------|
| HL histology | HISTOLOGY | 9650-9667 (ICD-O-3) | `HISTOLOGY_val_hl` |
| AJCC stage format | STAGE_GROUP | I, IA, IB, II, IIA, IIB, III, IIIA, IIIB, IV, IVA, IVB, UNK, 88, 99 | `STAGE_val_format` |
| B-symptoms coding | B_SYMPTOMS (or CS_SSF1) | A, B, or coded equivalent | `BSYMPTOMS_val_code` |
| AGE_AT_DIAGNOSIS | AGE_AT_DIAGNOSIS | 0-120, 200 (masked) | `AGE_val_range` |
| Treatment after DX | DT_* vs DATE_OF_DIAGNOSIS | Treatment date >= diagnosis date | `_val_tx_after_dx` |
| Primary site | PRIMARY_SITE | C770-C779 (lymph nodes), C778 (spleen) for HL | `PRIMARY_SITE_val_hl` |

**HL Histology Code Reference (ICD-O-3):**

| Code | Description |
|------|-------------|
| 9650 | Hodgkin lymphoma, NOS |
| 9651 | Hodgkin lymphoma, lymphocyte-rich |
| 9652 | Hodgkin lymphoma, mixed cellularity, NOS |
| 9653 | Hodgkin lymphoma, lymphocyte depletion, NOS |
| 9654 | Hodgkin lymphoma, lymphocyte depletion, diffuse fibrosis |
| 9655 | Hodgkin lymphoma, lymphocyte depletion, reticular |
| 9659 | Hodgkin lymphoma, nodular lymphocyte predominant |
| 9661 | Hodgkin granuloma |
| 9662 | Hodgkin sarcoma |
| 9663 | Hodgkin lymphoma, nodular sclerosis, NOS |
| 9664 | Hodgkin lymphoma, nodular sclerosis, cellular phase |
| 9665 | Hodgkin lymphoma, nodular sclerosis, grade 1 |
| 9667 | Hodgkin lymphoma, nodular sclerosis, grade 2 |

### Pattern 7: Insurance Validation

**What:** Validate PAYER_TYPE_PRIMARY against CDM value sets and check enrollment date ordering.

```python
def validate_insurance(
    encounter_df: pl.DataFrame,
    enrollment_df: pl.DataFrame,
    payer_valid_values: set[str],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Validate insurance fields in ENCOUNTER and ENROLLMENT.

    ENCOUNTER: PAYER_TYPE_PRIMARY against value set
    ENROLLMENT: ENR_START_DATE <= ENR_END_DATE
    """
    # ENCOUNTER: payer type validation
    if "PAYER_TYPE_PRIMARY" in encounter_df.columns:
        encounter_df = encounter_df.with_columns(
            pl.when(
                pl.col("PAYER_TYPE_PRIMARY").is_null()
                | pl.col("PAYER_TYPE_PRIMARY").is_in(payer_valid_values)
            )
            .then(pl.lit(0))
            .otherwise(pl.lit(1))
            .cast(pl.Int8)
            .alias("PAYER_TYPE_PRIMARY_val_code")
        )

    # ENROLLMENT: date ordering
    if "ENR_START_DATE" in enrollment_df.columns and "ENR_END_DATE" in enrollment_df.columns:
        enrollment_df = enrollment_df.with_columns(
            pl.when(
                pl.col("ENR_START_DATE").is_null()
                | pl.col("ENR_END_DATE").is_null()
                | (pl.col("ENR_START_DATE") <= pl.col("ENR_END_DATE"))
            )
            .then(pl.lit(0))
            .otherwise(pl.lit(1))
            .cast(pl.Int8)
            .alias("_val_enr_dates")
        )

    return encounter_df, enrollment_df
```

### Pattern 8: Write-Back with Flag Columns

**What:** After validation, overwrite the existing Parquet file with the DataFrame that now includes flag columns.

```python
def write_validated(df: pl.DataFrame, parquet_path: Path) -> dict:
    """Write DataFrame with flag columns back to Parquet, overwriting original.

    Returns stats about flags added and flagged rows.
    """
    flag_cols = [c for c in df.columns if "_val_" in c]
    stats = {
        "path": str(parquet_path),
        "total_rows": df.height,
        "flag_columns_added": len(flag_cols),
        "flags": {},
    }
    for fc in flag_cols:
        flagged = df[fc].sum()
        stats["flags"][fc] = int(flagged) if flagged is not None else 0

    df.write_parquet(parquet_path, compression="snappy")
    return stats
```

### Anti-Patterns to Avoid

- **Deleting or correcting flagged rows:** User locked decision — this phase flags only. No imputation, no deletion, no correction.
- **Using clinical reference ranges for labs:** User locked decision — use wide biological ranges that only catch truly impossible values. A hemoglobin of 7 g/dL is low but physiologically real (common in HL patients post-chemo).
- **Hard-coding ICD-10 transition at exactly Oct 1, 2015:** Need a grace period — facilities transitioned at different speeds. Jul-Dec 2015 is reasonable.
- **Ignoring RESULT_UNIT for lab plausibility:** A value of 150 for hemoglobin is impossible in g/dL but correct in g/L. Always check units.
- **Flagging mapped partners as ICD concordance violations:** AMS/UMI mapped all ICD-9→ICD-10 retrospectively. Their pre-2015 ICD-10 codes are expected, not errors.
- **Creating a separate validated directory:** User locked decision — overwrite existing Parquet files in-place.
- **Using composite flag columns:** User locked decision — binary per check type, not combined flags.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Value set lookup | Manual dict construction | `pl.read_csv()` + group-by to build lookup | `valuesets.csv` is already structured for this; 15,194 rows load instantly |
| Date arithmetic | Manual epoch math | `pl.col("date1") - pl.col("date2")` → Duration | Polars native date/duration types handle leap years, timezone-free |
| Conditional flag columns | Python loops over rows | `pl.when(...).then(...).otherwise(...)` chains | Vectorized; handles nulls naturally; stays in Polars expression engine |
| Cross-table joins for temporal | Manual ID matching in Python | `df1.join(df2, on="ID", how="left")` | Polars join handles type casting, null propagation |
| ICD code prefix detection | Regex on each row | `pl.col("DX").str.to_uppercase().str.contains(r"^[A-Z]")` | Vectorized string operation; ICD-10 starts with letter, ICD-9 with digit |
| Parquet write-back | Read-modify-write loop | `df.write_parquet(path, compression="snappy")` | Atomic write; Polars handles schema evolution with new columns |

**Key insight:** Every validation check maps to a `pl.when().then().otherwise()` expression that produces a binary flag column. This is the fundamental pattern — all checks are expressible as conditional column creation on DataFrames.

## Common Pitfalls

### Pitfall 1: Numeric Columns Stored as Strings After Phase 2

**What goes wrong:** Vital sign columns (HT, WT, SYSTOLIC, DIASTOLIC) or RESULT_NUM may be stored as String type in Parquet because Phase 2 used `infer_schema=False` for some tables.
**Why it happens:** Phase 2's `convert.py` reads CSVs with `infer_schema=False`, producing all-String DataFrames. Date columns are explicitly converted, but numeric columns may remain as String.
**How to avoid:** Before applying range checks, cast the relevant column to Float64 with `strict=False`. Check the dtype first: `if df[col].dtype == pl.String: df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))`.
**Warning signs:** Range comparison fails with type error; all values appear as String.

### Pitfall 2: Value Set Validation Generates Excessive Flags on Free-Text Fields

**What goes wrong:** Some fields in `valuesets.csv` have hundreds of valid values (e.g., LAB_RESULT_CM.SPECIMEN_SOURCE has 500+ entries, RESULT_QUAL has 200+). Attempting to validate free-text or semi-coded fields against these sets may produce too many false positives.
**Why it happens:** PCORnet CDM has both strictly coded fields (SEX: M/F/A/NI/UN/OT) and loosely coded fields where local values are common.
**How to avoid:** Focus value set validation on tightly-coded fields (ENC_TYPE, DX_TYPE, PX_TYPE, SEX, RACE, HISPANIC, etc.). For fields with 50+ valid values in the value set, consider logging the distribution but not per-row flagging. Apply judgment about which fields warrant per-row flags.
**Warning signs:** A flag column shows >50% flagged rows — likely a loosely-coded field.

### Pitfall 3: TUMOR_REGISTRY Column Names May Not Match Expected Names

**What goes wrong:** NAACCR variable names in TUMOR_REGISTRY may differ from expected names like `HISTOLOGY`, `STAGE_GROUP`, `B_SYMPTOMS`.
**Why it happens:** NAACCR uses standardized item numbers (e.g., Item 522 = Histologic Type ICD-O-3) but the column names in the data extract may use different conventions.
**How to avoid:** Use `pl.read_parquet_schema()` to inspect actual column names. In Phase 3, `TUMOR_REGISTRY_KEY_VARS` already identifies key variables — extend this approach. Build a mapping from expected variable concept to actual column name.
**Warning signs:** `ColumnNotFoundError` when accessing TUMOR_REGISTRY columns.

### Pitfall 4: Lab Plausibility Ranges Depend on Units

**What goes wrong:** A hemoglobin of 150 is flagged as implausible when it's actually correct — the unit is g/L (European standard) not g/dL (US standard).
**Why it happens:** Different partners may report in different units for the same LOINC code. The LOINC standard specifies a preferred unit but partners don't always comply.
**How to avoid:** Group lab results by LAB_LOINC + RESULT_UNIT before applying range checks. Only apply ranges when the unit matches the expected unit for that LOINC. For unexpected units, flag the unit discrepancy rather than the value.
**Warning signs:** Plausibility flag rates vary dramatically by partner for the same lab.

### Pitfall 5: Same-Day Admit/Discharge Overwhelming the Flags

**What goes wrong:** A large proportion of encounters are same-day (outpatient visits, ED visits, telehealth), making the `_val_same_day` flag very noisy.
**Why it happens:** Same-day encounters are legitimate — most HL patient encounters are outpatient chemo, follow-up visits, lab draws, etc.
**How to avoid:** Per locked decision, always flag same-day — but in the report, stratify by ENC_TYPE (AV/ED/TH/OS are expected same-day; IP same-day is more noteworthy). The flag exists for visibility; the report provides context.
**Warning signs:** >70% of ENCOUNTER rows flagged for same-day. This is expected behavior, not an error.

### Pitfall 6: Cross-Table Temporal Checks Require Joining Multiple Tables

**What goes wrong:** The HL disease timeline check (first DX → first treatment within 0-365 days) requires joining DIAGNOSIS, PROCEDURES, PRESCRIBING, and potentially TUMOR_REGISTRY to find the earliest treatment date per patient.
**Why it happens:** Treatment information is scattered across multiple CDM tables.
**How to avoid:** Compute the HL disease timeline as a separate summary analysis rather than a per-row flag on any single table. Output to the report with per-patient aggregates. Use `cohort.py`'s existing cohort results (union_ids_df, hl_dx) to identify first diagnosis dates, then find earliest treatment from PROCEDURES (chemo/radiation CPT codes) and PRESCRIBING (RXNORM for chemo drugs).
**Warning signs:** Memory pressure from joining 4+ large tables simultaneously.

### Pitfall 7: ICD Concordance on Full DIAGNOSIS Table is Expensive

**What goes wrong:** The full DIAGNOSIS table may have millions of rows. Running ICD concordance on every row (not just HL codes) could be slow.
**Why it happens:** User locked decision says "all diagnosis codes, not just HL codes" — comprehensive concordance.
**How to avoid:** Use lazy evaluation (`pl.scan_parquet()`), apply the flag expression, then collect. The concordance check is a simple conditional (code prefix + date comparison) that Polars can vectorize efficiently. Don't collect intermediate results.
**Warning signs:** Out-of-memory error if loading full DIAGNOSIS eagerly.

### Pitfall 8: Overwriting Parquet Files Loses Phase 2 State

**What goes wrong:** If Phase 4 fails mid-execution after overwriting some files but not others, the Parquet files are in an inconsistent state — some have flag columns, some don't.
**Why it happens:** User locked decision says overwrite in-place.
**How to avoid:** Process all tables, collect all validated DataFrames in memory (or write to temp files), then overwrite all at once at the end. Alternatively, write each file atomically (write to temp, then rename). If re-running Phase 4, detect existing flag columns and drop them before re-validating.
**Warning signs:** Some tables have `_val_*` columns and some don't after a partial run.

## Code Examples

### HL-Specific Outcome Code Sets (from concepts.py reference)

These code sets from the HL-EDA project define the procedure and lab codes for HL outcome monitoring. Use them for validating that HL-relevant procedures and labs have valid code formats.

```python
OUTCOMES_FEASIBILITY: dict[str, dict[str, list[str]]] = {
    "CBC": {
        "LOINC": ["6690-2", "718-7", "777-3", "4544-3", "26464-8",
                  "26515-7", "30313-1", "30428-7", "787-2"],
    },
    "Echo": {
        "CPT": ["93303", "93304", "93306", "93307", "93308",
                "93312", "93314", "93315", "93317", "93318",
                "93320", "93321", "93325", "93350", "93351"],
    },
    "ECG": {
        "CPT": ["93000", "93005", "93010", "93040", "93041", "93042"],
    },
    "MUGA": {
        "CPT": ["78472", "78473", "78481", "78483", "78494", "78496"],
    },
    "PFT": {
        "CPT": ["94010", "94060", "94070", "94375", "94726",
                "94727", "94728", "94729"],
    },
    "Liver_function": {
        "LOINC": ["1742-6", "1920-8", "6768-6", "1975-2",
                  "1751-7", "1968-7", "2324-2"],
    },
    "TSH": {
        "LOINC": ["11580-8", "3016-3"],
    },
    "Stem_cell_transplant": {
        "CPT": ["38204", "38205", "38206", "38207", "38208", "38209",
                "38210", "38211", "38212", "38213", "38214", "38215",
                "38220", "38221", "38222", "38230", "38232", "38240",
                "38241", "38242", "38243"],
        "ICD10PCS": ["30230G1", "30233G1", "30240G1", "30243G1",
                     "30250G1", "30253G1", "30260G1", "30263G1"],
    },
}
```

### Complete Entry Point Pattern

```python
def main():
    paths = load_config()
    table_map = build_table_map(paths)
    lookup = build_valueset_lookup(paths.valuesets_path)

    report_data = {}

    for table_name, pq_path in table_map.items():
        df = pl.read_parquet(pq_path)

        # Drop any existing flag columns from prior runs
        existing_flags = [c for c in df.columns if "_val_" in c]
        if existing_flags:
            df = df.drop(existing_flags)

        # 1. Value set validation (all tables)
        df = validate_coded_fields(df, table_name, lookup)

        # 2. Table-specific checks
        if table_name == "VITAL":
            df = validate_vital_plausibility(df)
        elif table_name == "LAB_RESULT_CM":
            df = validate_lab_plausibility(df)
        elif table_name == "DIAGNOSIS":
            mapped = detect_mapped_partners(df)
            df = validate_icd_concordance(df, mapped)
        elif table_name == "ENCOUNTER":
            df = validate_temporal_encounter(df)
        elif table_name == "ENROLLMENT":
            df = validate_enrollment_dates(df)
        elif table_name.startswith("TUMOR_REGISTRY"):
            df = validate_tumor_registry(df)

        # 3. Universal temporal checks
        df = validate_future_dates(df)

        # 4. Write back
        stats = write_validated(df, pq_path)
        report_data[table_name] = stats

    # 5. Cross-table checks (birth/death temporal, HL timeline)
    run_cross_table_temporal(table_map, report_data)

    # 6. Generate reports
    write_value_validation_report(report_data)
    write_icd_concordance_csv(report_data)
    write_temporal_issues_csv(report_data)
    write_tumor_registry_csv(report_data)
```

### Flag Column Naming Convention

**Discretion recommendation:**

```
{COLUMN}_val_{check_type}
```

Where `check_type` is one of:
- `code` — value not in CDM value set
- `range` — numeric value outside plausible range
- `icd_concordance` — ICD version inconsistent with date
- `temporal` — date relationship violation
- `future` — date after Dec 2025
- `same_day` — same-day admit/discharge
- `missing` — critical field unexpectedly empty (e.g., RESULT_UNIT)
- `hl` — HL-specific validation failure

Examples:
- `SEX_val_code` — SEX value not in value set
- `HT_val_range` — height outside 50-272 cm
- `DX_val_icd_concordance` — ICD version-date mismatch
- `ADMIT_DATE_val_future` — admit date after Dec 2025
- `_val_admit_discharge` — discharge before admit (table-level)
- `_val_same_day` — same-day admit/discharge (table-level)
- `HISTOLOGY_val_hl` — histology code not in HL range

The `_val_` infix makes flag columns easy to identify programmatically for downstream use.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Load full CSV per validation check | `pl.scan_parquet()` + lazy expressions + `collect()` | Polars 1.0+ | 10-100x faster; memory-bounded by result, not input |
| Separate "validated" output directory | In-place flag columns on existing Parquet | User decision | Simpler file management; no directory proliferation |
| Composite quality score per record | Binary per-check flags | User decision | More granular; analysts choose how to weight/combine |
| Hard ICD-10 cutover at Oct 1 | Grace period + auto-detect mapped partners | Domain knowledge | Reduces false positives from transition period and retrospective mapping |
| Clinical reference ranges for lab plausibility | Wide biological ranges | User decision | Avoids flagging clinically expected extreme values (chemo patients) |

**Deprecated/outdated:**
- `polars.DataFrame.melt()`: Renamed to `unpivot()` in Polars 1.0+
- `str.strptime()`: Deprecated in favor of `str.to_date()` / `str.to_datetime()`
- Writing separate "clean" files per validation pass: Modern pattern is additive flag columns on same file

## Open Questions

1. **Are numeric columns (HT, WT, SYSTOLIC, DIASTOLIC, RESULT_NUM) typed correctly in Parquet?**
   - What we know: Phase 2 used `infer_schema=False` for CSV loading (all String), then converted date columns. Numeric columns may still be String.
   - What's unclear: Whether `write_parquet` inferred numeric types from String values, or if they're stored as String.
   - Recommendation: Check dtypes at runtime. Cast to Float64 with `strict=False` before range checks. This is a LOW-risk issue — casting is straightforward and the pattern is well-established.

2. **What are the actual TUMOR_REGISTRY column names for staging, histology, and B-symptoms?**
   - What we know: Phase 3's `TUMOR_REGISTRY_KEY_VARS` includes `ID`, `DATE_OF_DIAGNOSIS`, `HISTOLOGY`, `PRIMARY_SITE`, `STAGE_GROUP`, `AGE_AT_DIAGNOSIS`. These were validated in Phase 3 schema checks.
   - What's unclear: Whether `B_SYMPTOMS` is a direct column name or requires interpretation from CS_SSF (Collaborative Staging Site-Specific Factors).
   - Recommendation: Probe TUMOR_REGISTRY1 schema at runtime. B-symptoms in NAACCR may be stored as a site-specific factor (SSF1) rather than a named column. Check for both `B_SYMPTOMS` and `CS_SSF1`.

3. **How should the HL disease timeline check handle patients with treatment before diagnosis?**
   - What we know: Treatment before diagnosis could mean: (a) diagnosis date is wrong, (b) treatment was for a different condition initially, (c) clinical treatment started before formal coding.
   - What's unclear: Whether this is common enough to warrant a separate investigation.
   - Recommendation: Flag treatment-before-diagnosis as `_val_temporal` but don't investigate individual cases. Report the count and leave interpretation to the analyst. This aligns with the "flags for context, not exclusion" principle.

4. **Should value set validation include PAYER_TYPE_SECONDARY and RAW_PAYER_TYPE_PRIMARY?**
   - What we know: `valuesets.csv` has 171 entries for PAYER_TYPE_PRIMARY. PAYER_TYPE_SECONDARY follows the same value set. RAW_PAYER_TYPE_PRIMARY is a free-text field.
   - What's unclear: Whether RAW_PAYER_TYPE_PRIMARY should be validated (it's intentionally free-text per CDM spec).
   - Recommendation: Validate PAYER_TYPE_PRIMARY and PAYER_TYPE_SECONDARY against the value set. Skip RAW_PAYER_TYPE_PRIMARY (free-text by design).

5. **What LOINC codes are most common in this dataset for HL-relevant labs?**
   - What we know: The OUTCOMES_FEASIBILITY dict from concepts.py lists expected LOINC codes. But the actual data may use different/additional LOINC codes for the same tests.
   - What's unclear: The actual LOINC distribution in LAB_RESULT_CM.
   - Recommendation: During execution, profile the top LOINC codes in LAB_RESULT_CM and compare against the expected list. Report any HL-relevant labs that use unexpected LOINC codes. The plausibility ranges should cover the most common LOINC variants.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `config.py`, `schema.py`, `convert.py`, `structural.py`, `cohort.py`, `validate_all.py` — verified module interfaces and patterns
- `valuesets.csv` — 15,194 rows of PCORnet CDM v6.1 value set mappings; structure verified (TABLE_NAME, FIELD_NAME, VALUESET_ITEM, VALUESET_ITEM_DESCRIPTOR)
- PCORnet CDM table schemas — from `.planning/research/HEALTHCARE_DATA_RESEARCH.md`, verified against official PCORnet documentation
- ICD-O-3 histology codes for Hodgkin Lymphoma (9650-9667) — standard SEER/WHO classification
- ICD-10 transition date (Oct 1, 2015) — CMS final rule

### Secondary (MEDIUM confidence)
- Vital sign plausibility ranges — based on clinical literature and established EHR validation practices; ranges intentionally wide per locked decision
- Lab plausibility ranges — based on biological feasibility, not clinical reference ranges; aligned with locked decision for wide ranges
- HL disease timeline (0-365 days dx to treatment) — based on NCCN Hodgkin Lymphoma clinical practice guidelines
- OUTCOMES_FEASIBILITY code sets — from HL-EDA project `concepts.py`; assumed current but not independently verified against LOINC/CPT updates

### Tertiary (LOW confidence)
- TUMOR_REGISTRY column naming for B-symptoms — may be `B_SYMPTOMS` or `CS_SSF1`; needs runtime verification
- Numeric column dtypes in existing Parquet files — unclear whether Phase 2 preserved String type for numeric columns
- Auto-detection threshold for mapped partners (>95% ICD-10 pre-transition) — reasonable heuristic but may need adjustment based on actual data distribution

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Same Polars stack as Phases 2-3; no new dependencies
- Architecture: HIGH — Flag column pattern is straightforward `when/then/otherwise`; value set lookup from CSV is standard
- Value set validation: HIGH — `valuesets.csv` structure verified; lookup construction is mechanical
- Vital/lab plausibility: MEDIUM — Ranges are clinically reasonable but discretionary; locked decision provides clear guidance (wide ranges, impossible only)
- ICD concordance: HIGH — Oct 2015 transition date is well-established; grace period and partner auto-detection are sound approaches
- Temporal consistency: HIGH — Date comparison patterns are standard Polars operations
- Tumor registry: MEDIUM — Column naming uncertainty; HL-specific checks (histology, staging) are clinically well-defined but runtime column probing needed
- Pitfalls: HIGH — Well-documented from Phase 3 experience and clinical domain knowledge

**Research date:** 2026-02-27
**Valid until:** 2026-03-29 (30 days — Polars APIs stable; clinical coding standards don't change; project data is fixed extract)
