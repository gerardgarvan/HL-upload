# Encounter-Payer Summary: Variable and Category Definitions

**Source:** `src/report/encounter_payer_summary.py` — `build_encounter_payer_summary()`  
**Output:** `derived/encounter_payer_summary.parquet` (one row per patient with encounters who has ENROLLMENT)

---

## 1. How the payer variables are calculated

**Scope:** Only patients with at least one ENROLLMENT record. All payer fields use **effective payer** per encounter (see below), mapped to categories via PCORnet typology (see Section 2).

**Effective payer (per encounter):** The value used for every payer-derived variable is: **primary if valid**, else **secondary if valid** (when ENCOUNTER has PAYER_TYPE_SECONDARY), else null. This gives a single “effective” payer per encounter and supports sentinel fallback (e.g. when primary is NI/UN/OT, secondary is used if present and valid).

**Sentinel list:** Values that trigger fallback to secondary when they appear as primary: **null**, **empty string**, **NI**, **UN**, **OT**. Optional: **99** and **9999** can be treated as sentinel via the configurable constant `INCLUDE_99_AS_SENTINEL` in code (default: **False**); when False, 99/9999 are not treated as sentinel and map to category “Unavailable”. The choice is documented here and in the CODEBOOK.

**Valid payer:** Effective payer is non-null, non-empty, and not in the sentinel set. Encounters whose effective payer is sentinel or null are excluded from payer category logic.

**When PAYER_TYPE_SECONDARY is missing:** Effective payer = primary only (same valid check). Encounter-level dual-eligible cannot be computed, so patient-level DUAL_ELIGIBLE = 0.

| Variable | Type | How it is calculated |
|----------|------|------------------------|
| `N_ENCOUNTERS` | Int64 | Total number of ENCOUNTER rows per patient (all encounters, regardless of payer). |
| `N_ENCOUNTERS_WITH_PAYER` | Int64 | Number of encounters where **effective payer** is valid (non-null, non-empty, not sentinel). |
| `N_DISTINCT_PAYER_CATEGORIES` | Int64 | Among **valid** encounters only: count of distinct payer **categories** per patient after mapping effective payer to category. Sentinel/missing encounters are excluded; if a patient has only sentinel/missing, this is 0. |
| `PAYER_CATEGORY_PRIMARY` | String | Among **valid** encounters only: the payer **category** that appears most often (mode). Each valid effective payer is mapped to a category; the category with the highest encounter count is primary. Null if the patient has no valid payer on any encounter. Ties: first after sort by count descending. |
| `PAYER_CATEGORY_AT_FIRST_DX` | String | Payer category from the **single encounter** whose ADMIT_DATE is closest to the patient's first HL diagnosis date, within ±90 days. **Effective payer** from that encounter is mapped to category. Null if no HL diagnosis, no encounter, or no encounter within ±90 days. |
| `PAYER_CATEGORY_AT_FIRST_CHEMO` | String | Payer category from the encounter whose ADMIT_DATE is closest to the patient's **first chemo date**, within ±90 days. First chemo date = earliest of TUMOR_REGISTRY (DT_CHEMO, CHEMO_START_DATE_SUMMARY) or PRESCRIBING RX_ORDER_DATE. **Effective payer** from that encounter is mapped to category. Null if no chemo date or no qualifying encounter. |
| `PAYER_CATEGORY_AT_LAST_CHEMO` | String | Payer category from the encounter whose ADMIT_DATE is closest to the patient's **last chemo date**, within ±90 days. **Effective payer** from that encounter is mapped to category. Null if no chemo or no qualifying encounter. |
| `PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO` | String | Among encounters with ADMIT_DATE between the patient's first and last chemo date (inclusive), the payer **category** that appears most often (mode). Only encounters with valid **effective payer** in that window are used. Null if no chemo dates or no valid payer in that window. |
| `PAYER_TRANSITION` | Int8 | 1 if the patient has **more than one distinct payer category** across valid encounters (N_DISTINCT_PAYER_CATEGORIES > 1); 0 otherwise. Based only on valid effective payer. |
| `DUAL_ELIGIBLE` | Int8 | Patient-level: 1 if the patient has **at least one encounter** that is dual-eligible; 0 otherwise. See “Dual-eligible definition” below. When PAYER_TYPE_SECONDARY is missing, DUAL_ELIGIBLE = 0. |

---

## 2. How payer categories are calculated

Payer categories are derived from **effective payer** and **dual-eligible** status in `src/report/encounter_payer_summary.py` via `_payer_category_from_effective_and_dual()` and `_collapse_payer_category(code)`.

**Override:** When an encounter is **dual-eligible** (Medicare+Medicaid or code 14/141/142), the payer category for that encounter is **"Dual eligible"** (instead of Medicare or Medicaid). Otherwise the code is mapped by **prefix** (PCORnet typology):

| If encounter... | Category |
|-----------------|----------|
| **dual-eligible** (primary+secondary Medicare+Medicaid or code 14/141/142) | **Dual eligible** |
| null, empty, or **NI, UN, OT**, or string **"UNKNOWN"** | **Unknown** |
| **99** or **9999** | **Unavailable** |
| starts with **1** (e.g. 1, 11, 12, 111) | **Medicare** |
| starts with **2** (e.g. 2, 21, 22) | **Medicaid** |
| starts with **5** or **6** (e.g. 51, 61) | **Private** |
| starts with **3** or **4** (e.g. 31, 32, **41** = Corrections Federal) | **Other government** |
| starts with **8** (e.g. 81, 82) | **No payment / Self-pay** |
| starts with **7** or **9** (but not 99/9999) (e.g. 71, 91) | **Other** |
| anything else | **Other** |

**Summary:** Possible category levels are **Medicare, Medicaid, Dual eligible, Private, Other government, No payment / Self-pay, Other, Unavailable, Unknown**. Dual-eligible encounters map to "Dual eligible"; all others use the table above. The same logic is used for every payer-derived variable (primary, at first DX, at first/last chemo, most frequent at chemo).

---

## 3. Dual-eligible definition

**Encounter-level dual-eligible** is set to 1 when any of:

- (a) Primary is Medicare (prefix 1) **and** secondary is Medicaid (prefix 2), or  
- (b) Primary is Medicaid **and** secondary is Medicare, or  
- (c) Primary **or** secondary is one of the explicit dual-eligibility codes: **14**, **141**, **142** (PCORnet: Dual Eligibility Medicare/Medicaid Organization, D-SNP, FIDE-SNP).

Otherwise encounter-level dual-eligible = 0. When PAYER_TYPE_SECONDARY is missing from ENCOUNTER, dual-eligible is set to 0 (cannot compute (a) or (b); (c) could use primary only but the implementation sets 0 when secondary is absent).

**Code 41** is **Corrections Federal** (Other government) in the PCORnet valueset and is **not** a dual-eligibility code. It maps to category “Other government” only.

**Patient-level DUAL_ELIGIBLE:** 1 if the patient has at least one encounter with encounter-level dual-eligible = 1; 0 otherwise. Written to `derived/encounter_payer_summary.parquet`.
