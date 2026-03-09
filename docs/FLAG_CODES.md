# Flag Code Documentation

**Reference:** `src/clean/flags_diagnosis_provider.py`, `src/validate/cohort.py`

## FLAG_HL_DX (DIAGNOSIS)

**Source:** Single source of truth: `src/validate/cohort.py` (ALL_HL_CODES, ICD9_HL_CODES, ICD10_HL_CODES).

**Definition:** Hodgkin lymphoma diagnosis codes. 149 codes total:

- **ICD-10-CM:** 77 codes — C81.00 through C81.9A, excluding C81.5x and C81.6x
- **ICD-9-CM:** 72 codes — 201.00 through 201.98, excluding 201.3x

**Exclusions:** 201.3x (ICD-9), C81.5x and C81.6x (ICD-10) are not in the HL cohort set.

---

## FLAG_SURVIVORSHIP_DX (DIAGNOSIS)

**Source:** `flags_diagnosis_provider.py` (SURVIVORSHIP_EXACT_*, SURVIVORSHIP_PREFIX_ICD10).

**Definition:** Cancer survivorship / personal history codes.

- **Exact ICD-10:** V87.41, V87.42, V87.43, V87.46 (personal history chemotherapy, immunotherapy, etc.); Z92.21, Z92.22, Z92.23, Z92.25, Z92.3
- **Exact ICD-9:** V15.3 (personal history; semantics vary — verify against study protocol if needed)
- **Prefix ICD-10:** Z08 (encounter for follow-up after malignancy treatment), Z85 (personal history of malignant neoplasm)

**References:** Standard ICD-10-CM / ICD-9-CM; study protocol may refine V15.3.

---

## FLAG_CANCER_PROVIDER (PROVIDER)

**Source:** `flags_diagnosis_provider.py` (ONCOLOGY_KEYWORDS).

**Definition:** Case-insensitive match on PROVIDER_SPECIALTY_PRIMARY for oncology-related specialties.

**Keywords:** oncology, medical oncology, radiation oncology, hematology-oncology, hematology/oncology, pediatric oncology.
