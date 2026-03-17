# Phase 17: Dual Eligible as a Payer Category Level — Execution Summary

**Executed:** Phase 17 implementation complete

## Implemented

### 1. "Dual eligible" as a category level (`encounter_payer_summary.py`)

- **Helper:** `_payer_category_from_effective_and_dual(effective_payer, dual_eligible)` returns `"Dual eligible"` when `dual_eligible == 1`, else `_collapse_payer_category(effective_payer)`.
- **valid_enc:** Selects `PATID_COL`, `effective_payer`, `dual_eligible` from the enc scan. PAYER_CATEGORY is set per row via the helper (so dual-eligible encounters get category "Dual eligible"). PAYER_CATEGORY_PRIMARY, N_DISTINCT_PAYER_CATEGORIES, and PAYER_TRANSITION now use this category.

### 2. _payer_at_date returns _dual_eligible; AT_FIRST_DX, AT_FIRST_CHEMO, AT_LAST_CHEMO use it

- **_payer_at_date:** ENCOUNTER scan includes `dual_eligible` (via `_effective_payer_and_dual_exprs`). Returns `_raw_payer` (effective_payer) and `_dual_eligible` (0 when no encounter or missing). All early-exit paths return both columns.
- **Callers:** PAYER_CATEGORY_AT_FIRST_DX, PAYER_CATEGORY_AT_FIRST_CHEMO, PAYER_CATEGORY_AT_LAST_CHEMO are computed with `_payer_category_from_effective_and_dual(_raw_payer, _dual_eligible)` so the closest encounter can show "Dual eligible".

### 3. enc_chemo block — "Dual eligible" when dual_eligible

- enc_chemo scan adds `dual_expr`; select keeps `effective_payer`, `dual_eligible`, `_valid`. PAYER_CATEGORY per row is set via `_payer_category_from_effective_and_dual(effective_payer, dual_eligible)`. PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO can therefore be "Dual eligible".

### 4. Reports and docs

- **build_insurance_summary.py:** `PAYER_CATEGORY_ORDER` now includes `"Dual eligible"` after Medicaid (Medicare, Medicaid, Dual eligible, Private, …).
- **CODEBOOK.md (Section 6a):** Payer category mapping states that dual-eligible encounters map to "Dual eligible"; possible levels listed as Medicare, Medicaid, Dual eligible, Private, etc.
- **PAYER_VARIABLES_AND_CATEGORIES.md:** Section 2 updated with override (dual-eligible → "Dual eligible") and table; summary lists "Dual eligible" as a category level.

## Verification

- `_payer_category_from_effective_and_dual("1", 1)` → "Dual eligible"; `("1", 0)` → "Medicare".
- `build_encounter_payer_summary({})` runs and returns schema with all columns.
- No linter errors in `encounter_payer_summary.py`.

## Outputs

| Artifact | Status |
|----------|--------|
| `src/report/encounter_payer_summary.py` | Helper added; valid_enc, _payer_at_date, enc_chemo use "Dual eligible" when dual_eligible |
| `scripts/build_insurance_summary.py` | PAYER_CATEGORY_ORDER includes "Dual eligible" |
| `docs/CODEBOOK.md`, `docs/PAYER_VARIABLES_AND_CATEGORIES.md` | "Dual eligible" documented as a category level |
