# Phase 18: Most Common Insurance at Radiation and SCT; Expand Treatment Window by 30 Days — Research

**Goal:** (1) Add most common payer at **radiation** encounters and at **stem cell transplant (SCT)** encounters; (2) expand the first/last insurance “around treatments” window by 30 days (90 → 120 days).

**Researched:** `encounter_payer_summary.py`, `quality_report.py`, `validate_values.py`, structural.

---

## Summary

- **Current:** Payer at first DX, first chemo, last chemo uses `_payer_at_date(..., window_days=90)`. Most frequent payer at chemo uses encounters with ADMIT_DATE in [FIRST_CHEMO_DATE, LAST_CHEMO_DATE]. No radiation- or SCT-specific payer variables.
- **Target:**  
  - **Window:** Use **±120 days** (90 + 30) for “insurance around treatments”: payer at first DX, first chemo, last chemo (and any new at-date treatment payers).  
  - **New variables:** **PAYER_CATEGORY_MOST_FREQUENT_AT_RADIATION**, **PAYER_CATEGORY_MOST_FREQUENT_AT_SCT** — same logic as MOST_FREQUENT_AT_CHEMO: get first/last radiation date and first/last SCT date per patient; take encounters with ADMIT_DATE in [first, last]; assign category (effective_payer + dual_eligible → "Dual eligible" when applicable); mode per patient.

---

## 1. Expand window by 30 days

- **Current:** `_payer_at_date(..., window_days=90)`.
- **Change:** Use **120** for all call sites that represent “insurance around treatments”: first HL DX, first chemo, last chemo. Options: (a) change default to 120 in `_payer_at_date`; (b) add a constant e.g. `PAYER_AT_TREATMENT_WINDOW_DAYS = 120` and pass it explicitly for first_dx, first_chemo, last_chemo. Recommendation: (b) so other potential callers keep 90 if needed; or (a) if the only use is treatment-related. Plan: add constant `PAYER_AT_TREATMENT_WINDOW_DAYS = 120`, pass it into `_payer_at_date` for FIRST_HL_DX_DATE, FIRST_CHEMO_DATE, LAST_CHEMO_DATE.
- **Scope:** No change to the chemo **range** for MOST_FREQUENT_AT_CHEMO (still [FIRST_CHEMO_DATE, LAST_CHEMO_DATE]); only the ±day window for “closest encounter” to a single date is 120.

---

## 2. Radiation dates (first/last per patient)

- **Sources:**  
  - **TUMOR_REGISTRY:** column **DT_RAD** (if present). Same pattern as `_get_chemo_dates` for TR: scan TR tables, parse DT_RAD as date, collect (PATID, _rad_d), aggregate min/max per patient.  
  - **PROCEDURES:** PX in **radiation CPT set** (77401, 77402, 77407, 77412, 77427 per `validate_values.py`), PX_DATE → treat as radiation procedure date. Combine with TR DT_RAD: union of dates, then group_by PATID → FIRST_RADIATION_DATE = min, LAST_RADIATION_DATE = max.
- **Code:** New helper `_get_radiation_dates(table_map, ids)` returning DataFrame with PATID_COL, FIRST_RADIATION_DATE, LAST_RADIATION_DATE, or None if no radiation dates found. Reuse TR date-parsing pattern from `_get_chemo_dates`; add PROCEDURES scan for PX in RADIATION_CPTS.

---

## 3. Stem cell transplant (SCT) dates (first/last per patient)

- **Source:** **PROCEDURES** only (no standard DT_SCT in TR). PX in **SCT CPT set**: 38240, 38241, 38242, 38230, 38232 (stem cell / bone marrow, per `validate_values.py` and `quality_report.py`). PX_DATE → first/last per patient.
- **Code:** New helper `_get_sct_dates(table_map, ids)` returning DataFrame with PATID_COL, FIRST_SCT_DATE, LAST_SCT_DATE, or None if no SCT procedure dates. PROCEDURES scan: filter PX in SCT_CPTS, group_by PATID, agg min(PX_DATE), max(PX_DATE).

---

## 4. Most common payer at radiation / at SCT

- **Pattern:** Same as enc_chemo. For radiation: get `radiation = _get_radiation_dates(table_map, ids)`. If not None, filter ENCOUNTER to PATID in radiation, join to radiation on PATID, filter ADMIT_DATE in [FIRST_RADIATION_DATE, LAST_RADIATION_DATE], add effective_payer + dual_eligible, compute PAYER_CATEGORY per row ("Dual eligible" when dual_eligible else _collapse_payer_category(effective_payer)), filter _valid, then group_by PATID + PAYER_CATEGORY, count, take mode per PATID → PAYER_CATEGORY_MOST_FREQUENT_AT_RADIATION. Same for SCT with `_get_sct_dates` and [FIRST_SCT_DATE, LAST_SCT_DATE] → PAYER_CATEGORY_MOST_FREQUENT_AT_SCT.
- **Schema:** Add to empty_schema and to final select: "PAYER_CATEGORY_MOST_FREQUENT_AT_RADIATION", "PAYER_CATEGORY_MOST_FREQUENT_AT_SCT" (both String, nullable).
- **When no radiation/SCT dates:** Column null for that patient (same as MOST_FREQUENT_AT_CHEMO when no chemo).

---

## 5. Code references

| Location | Current | Change |
|----------|---------|--------|
| `encounter_payer_summary.py` | `window_days=90` in _payer_at_date | Add PAYER_AT_TREATMENT_WINDOW_DAYS=120; pass to _payer_at_date for first_dx, first_chemo, last_chemo. |
| `encounter_payer_summary.py` | _get_chemo_dates only | Add _get_radiation_dates (TR DT_RAD + PROCEDURES radiation CPTs), _get_sct_dates (PROCEDURES SCT CPTs). |
| `encounter_payer_summary.py` | enc_chemo → MOST_FREQUENT_AT_CHEMO | Add enc_radiation → MOST_FREQUENT_AT_RADIATION, enc_sct → MOST_FREQUENT_AT_SCT (same pattern). |
| empty_schema / return select | No rad/SCT columns | Add PAYER_CATEGORY_MOST_FREQUENT_AT_RADIATION, PAYER_CATEGORY_MOST_FREQUENT_AT_SCT. |

---

## 6. Constants (define in encounter_payer_summary.py)

- **PAYER_AT_TREATMENT_WINDOW_DAYS** = 120 (was 90 for treatment-related at-date payer).
- **RADIATION_CPTS** = {"77401", "77402", "77407", "77412", "77427"} (radiation therapy/management).
- **SCT_CPTS** = {"38240", "38241", "38242", "38230", "38232"} (stem cell / bone marrow procedures). Can import from quality_report if already defined there and avoid duplication; else define in encounter_payer_summary.

---

## 7. Documentation

- **CODEBOOK.md** and **PAYER_VARIABLES_AND_CATEGORIES.md:** Document PAYER_CATEGORY_MOST_FREQUENT_AT_RADIATION, PAYER_CATEGORY_MOST_FREQUENT_AT_SCT; note that the “closest encounter” window for first DX and first/last chemo is ±120 days (expanded by 30 from 90). build_insurance_summary: add the two new variables to INSURANCE_VARS if we want them in encounter_payer_summary.csv and in report tables (plan can include that).
