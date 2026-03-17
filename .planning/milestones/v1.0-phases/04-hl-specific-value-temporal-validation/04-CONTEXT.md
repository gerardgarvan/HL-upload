# Phase 4: HL-Specific Value & Temporal Validation - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Validate data values against PCORnet CDM value sets and HL-specific clinical rules, verify temporal consistency across all tables, and add binary validation flag columns to the existing Parquet files. This phase validates and flags — it does not delete, correct, or impute data. All flags are for context/understanding, not automatic exclusion.

</domain>

<decisions>
## Implementation Decisions

### Validation Flag Strategy
- **Storage:** Add flag columns directly to Parquet files — each row gets binary (0/1) flag columns per check type (e.g., `_val_code`, `_val_range`, `_val_temporal`).
- **Granularity:** Binary pass/fail (0 or 1) per check type. Not coded issue types or free-text notes.
- **Write-back:** Overwrite existing Parquet files from Phase 2 — add flag columns to the same files. No separate validated directory.
- **Downstream use:** Flags are for context only — understanding data quality. Not for automatic exclusion of flagged rows by downstream scripts. Analysis decides how to use them via sensitivity analysis or contextual review.

### ICD Concordance Rules
- **Cutover date:** Grace period — allow some overlap around Oct 2015 since facilities transitioned at different speeds. Don't treat Oct-Dec 2015 mixed codes as hard violations.
- **Exempt partners:** Claude's discretion — auto-detect which partners likely mapped ICD-9 to ICD-10 based on what the data shows (e.g., partners with 0% ICD-9 codes). AMS and UMI are known mappers, but let the data reveal others.
- **Scope:** All diagnosis codes, not just HL codes — comprehensive ICD concordance validation across the full DIAGNOSIS table.
- **Output:** Both CSV (`icd_concordance.csv`) with per-partner breakdown AND a report section in the validation markdown.

### Plausibility Thresholds
- **Vital sign ranges:** Claude's discretion — use clinically reasonable ranges (roadmap suggests HT 50-250cm, WT 2-500kg, SBP 60-300, DBP 30-200; adjust as clinically appropriate).
- **Lab ranges:** Wide biological ranges — very permissive, only flag truly impossible values (e.g., negative WBC, Hgb > 30 g/dL). Not clinical reference ranges.
- **Missing RESULT_UNIT:** Flag as a separate validation issue. Missing unit is its own failure — do not assume a default unit or skip plausibility checks silently.
- **Tumor registry validation depth:** Claude's discretion — decide between format-only checks and HL-specific histology/staging verification based on what's practical.

### Temporal Logic
- **Same-day admit/discharge:** Always flag — review separately. Even outpatient encounters get flagged for visibility (common in HL treatment but worth tracking).
- **Future date cutoff:** Dec 2025 — generous buffer beyond the Sept 15, 2025 extraction date to account for processing delays. Anything after Dec 31, 2025 is flagged.
- **Masked birth dates:** When BIRTH_DATE = 1900-01-01 (masked), use AGE_AT_DIAGNOSIS from TUMOR_REGISTRY when available instead of birth date for temporal checks. If neither is available, skip birth-related temporal checks for that patient.
- **HL disease timeline:** 0-365 days from first HL diagnosis to first treatment. Flag if treatment precedes diagnosis or if gap exceeds 365 days.

### Claude's Discretion
- Vital sign plausibility thresholds (within clinically reasonable bounds)
- Tumor registry validation depth (format-only vs HL-specific histology/staging)
- Which partners to auto-detect as ICD-9→ICD-10 mappers (beyond known AMS, UMI)
- Exact flag column naming convention (e.g., `_val_code`, `_val_range`, `_val_temporal`, or similar)

</decisions>

<specifics>
## Specific Ideas

- HL-EDA's `quality.py` already has plausibility checks for HT, WT, ADMIT_DATE vs DISCHARGE_DATE, and BIRTH_DATE vs today. Extend these patterns with Polars equivalents.
- HL-EDA's `concepts.py` has HL-specific lab/procedure code sets (CBC, echo, ECG, MUGA, PFT, liver function, TSH, stem cell transplant) — use these for HL outcome validation.
- `valuesets.csv` (15,000+ rows) provides PCORnet code-to-label mappings — reuse for coded field validation.
- Histology codes for HL are 9650-9667 in ICD-O-3 (TUMOR_REGISTRY). B-symptoms should be coded as A=absent, B=present.
- AJCC staging for HL uses I-IV with substages (IA, IB, IIA, IIB, IIIA, IIIB, IVA, IVB). The A/B suffix corresponds to B-symptom status.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 04-hl-specific-value-temporal-validation*
*Context gathered: 2026-02-27*
