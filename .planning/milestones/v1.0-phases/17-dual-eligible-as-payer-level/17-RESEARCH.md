# Phase 17: Dual Eligible as a Payer Category Level — Research

**Goal:** Make "Dual eligible" a **level** (category value) of each payer variable, so that tables and reports show: Medicare, Medicaid, **Dual eligible**, Private, Other government, etc., instead of a separate DUAL_ELIGIBLE 0/1 column.

**Researched:** Codebase `encounter_payer_summary.py`, `build_insurance_summary.py`, docs.

---

## Summary

- **Current:** Payer categories are Medicare, Medicaid, Private, Other government, No payment / Self-pay, Other, Unavailable, Unknown (from `_collapse_payer_category(effective_payer)`). Dual-eligibility is a separate binary column `DUAL_ELIGIBLE` (0/1).
- **Target:** Add **"Dual eligible"** as a category level. For any encounter that is dual-eligible (Medicare+Medicaid or code 14/141/142), assign category **"Dual eligible"** instead of "Medicare" or "Medicaid". So each payer variable (PAYER_CATEGORY_PRIMARY, AT_FIRST_DX, AT_FIRST_CHEMO, AT_LAST_CHEMO, MOST_FREQUENT_AT_CHEMO) can take the value "Dual eligible" alongside the existing levels.
- **Keep:** The patient-level column `DUAL_ELIGIBLE` (0/1) can remain for convenience (filtering, stratification); it is redundant with having "Dual eligible" as a category but does not conflict.

---

## Where category is assigned

1. **valid_enc → PAYER_CATEGORY_PRIMARY**  
   We have encounter-level `effective_payer` and `dual_eligible`. When building PAYER_CATEGORY per encounter for the primary/mode logic: use **"Dual eligible"** when `dual_eligible == 1`, else `_collapse_payer_category(effective_payer)`.

2. **\_payer_at_date → PAYER_CATEGORY_AT_FIRST_DX, AT_FIRST_CHEMO, AT_LAST_CHEMO**  
   Currently `_payer_at_date` returns only `_raw_payer` (effective_payer). We need dual-eligibility for the **closest** encounter. So: in `_payer_at_date`, also compute and return `dual_eligible` for that encounter (same ENCOUNTER scan with primary/secondary, add dual_eligible expr, keep it through closest-row selection). Return `_raw_payer` and `_dual_eligible`. Callers then set category = **"Dual eligible"** when `_dual_eligible == 1`, else `_collapse_payer_category(_raw_payer)`.

3. **enc_chemo block → PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO**  
   The chemo-window encounter scan already has access to primary/secondary; we can add `dual_eligible` there (same `_effective_payer_and_dual_exprs`). For each row, category = **"Dual eligible"** when dual_eligible else `_collapse_payer_category(effective_payer)`.

---

## Implementation notes

- **Category string:** Use exactly **"Dual eligible"** (capital D, lowercase rest) for consistency with "Other government", "No payment / Self-pay".
- **Order:** In reports, list "Dual eligible" after Medicaid (or after Medicare/Medicaid) in `PAYER_CATEGORY_ORDER` in `build_insurance_summary.py`.
- **Helper:** Add a small helper in `encounter_payer_summary.py` that, given (effective_payer, dual_eligible), returns "Dual eligible" if dual_eligible else _collapse_payer_category(effective_payer). Use it everywhere we assign a payer category so logic stays in one place.
- **DUAL_ELIGIBLE column:** Keep in parquet; reports can still show it or rely on the new level.

---

## Files to touch

| File | Change |
|------|--------|
| `src/report/encounter_payer_summary.py` | (1) Category = "Dual eligible" when dual_eligible else _collapse; valid_enc; (2) _payer_at_date return _dual_eligible; callers use it for AT_FIRST_DX, AT_FIRST_CHEMO, AT_LAST_CHEMO; (3) enc_chemo add dual_eligible, category with "Dual eligible" level. |
| `scripts/build_insurance_summary.py` | Add "Dual eligible" to `PAYER_CATEGORY_ORDER`. |
| `docs/CODEBOOK.md`, `docs/PAYER_VARIABLES_AND_CATEGORIES.md` | Document "Dual eligible" as a category level; update category list. |

---

## Order of operations (encounter_payer_summary.py)

1. Add helper e.g. `_payer_category_from_effective_and_dual(effective_payer, dual_eligible)` → "Dual eligible" if dual_eligible else _collapse_payer_category(effective_payer). For Polars expressions: where we have both effective_payer and dual_eligible columns, use `pl.when(pl.col("dual_eligible") == 1).then(pl.lit("Dual eligible")).otherwise(pl.col("effective_payer").map_batches(...))` or equivalent.
2. valid_enc: when building PAYER_CATEGORY from effective_payer, use dual_eligible from the same enc scan so category can be "Dual eligible". (valid_enc currently selects PATID_COL, effective_payer; add dual_eligible, then compute PAYER_CATEGORY via the new rule.)
3. _payer_at_date: include dual_eligible in the scan and in the returned columns (e.g. _raw_payer, _dual_eligible). Callers compute PAYER_CATEGORY_AT_FIRST_DX etc. as "Dual eligible" when _dual_eligible else _collapse_payer_category(_raw_payer).
4. enc_chemo: add dual_eligible to the scan; when assigning PAYER_CATEGORY for each row, use "Dual eligible" when dual_eligible else _collapse_payer_category(effective_payer).
5. build_insurance_summary: PAYER_CATEGORY_ORDER includes "Dual eligible"; docs updated.
