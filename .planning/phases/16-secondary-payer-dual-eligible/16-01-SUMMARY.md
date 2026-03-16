# Phase 16: Secondary Payer and Dual-Eligible — Execution Summary

**Executed:** Phase 16 implementation complete

## Implemented

### 1. Effective payer and sentinel fallback (`src/report/encounter_payer_summary.py`)

- **Sentinel set:** Reused and extended from `INVALID_PAYER` (null, `""`, NI, UN, OT). Optional 99/9999 via `INCLUDE_99_AS_SENTINEL` (default: False); documented in CODEBOOK and PAYER_VARIABLES_AND_CATEGORIES.
- **Helpers:** `_sentinel_set()`, `_valid_payer_expr(col)` for any payer column. Schema check: `PAYER_TYPE_SECONDARY` in `pl.read_parquet_schema(enc_path).names()`; when missing, effective_payer = primary only.
- **Single computation:** `_effective_payer_and_dual_exprs(has_secondary)` returns `(effective_payer, _valid, dual_eligible)` expressions. First ENCOUNTER scan selects PRIMARY and SECONDARY (if present), adds effective_payer, _valid, dual_eligible. All downstream logic uses effective_payer.

### 2. Encounter-level and patient-level dual-eligible

- **Dual-eligible codes:** `DUAL_ELIGIBLE_CODES = ("14", "141", "142")`; 41 = Corrections Federal (not dual-eligible), documented in docs.
- **Encounter-level:** (a) primary Medicare & secondary Medicaid, (b) primary Medicaid & secondary Medicare, (c) primary or secondary in {14, 141, 142}. When PAYER_TYPE_SECONDARY missing, dual_eligible = 0.
- **Patient-level:** `DUAL_ELIGIBLE` = max(dual_eligible) per patient in group_by; added to `empty_schema` and final `.select()`; written to `derived/encounter_payer_summary.parquet` as Int8.

### 3. All payer logic on effective_payer

- Base counts and valid_enc use effective_payer and _valid.
- `_payer_at_date`: reads ENCOUNTER with PRIMARY/SECONDARY (if present), computes effective_payer via `_effective_payer_and_dual_exprs`, returns effective_payer as `_raw_payer`.
- enc_chemo block: same expressions, selects effective_payer and _valid, filters on _valid, maps effective_payer to PAYER_CATEGORY for most-frequent-at-chemo.
- No remaining use of PAYER_TYPE_PRIMARY for “payer for this encounter” except inside effective_payer/dual_eligible computation.

### 4. Documentation

- **CODEBOOK.md (Section 6a):** Effective payer definition, sentinel list, optional 99/9999; DUAL_ELIGIBLE variable; dual-eligible definition; when SECONDARY missing. All variable rows updated to “effective payer”.
- **PAYER_VARIABLES_AND_CATEGORIES.md:** Section 1 updated with effective payer, sentinel, 99/9999; DUAL_ELIGIBLE in table; Section 2 now “effective payer” and code 41 = Corrections Federal; new Section 3 “Dual-eligible definition” (encounter-level, patient-level, code 41 not dual-eligible).

## Verification

- `python -c "from src.report.encounter_payer_summary import build_encounter_payer_summary; df = build_encounter_payer_summary({}); print('DUAL_ELIGIBLE' in df.columns)"` → True; empty schema includes DUAL_ELIGIBLE.
- No linter errors in `encounter_payer_summary.py`.
- When ENCOUNTER exists with or without PAYER_TYPE_SECONDARY, schema check and single effective_payer path used; dual_eligible = 0 when secondary missing.

## Outputs

| Artifact | Status |
|----------|--------|
| `src/report/encounter_payer_summary.py` | Updated: effective_payer, dual_eligible, all logic on effective_payer |
| `derived/encounter_payer_summary.parquet` | Will include DUAL_ELIGIBLE when produced by assemble_clean |
| `docs/CODEBOOK.md` | Section 6a updated |
| `docs/PAYER_VARIABLES_AND_CATEGORIES.md` | Sections 1–3 updated |
