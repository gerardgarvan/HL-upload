# HL Data Loading & Cleaning — Variable Codebook

**Project:** HL insurance inequities pipeline  
**Study:** UFPTI 2405-HLX17A  
**Purpose:** Documents how derived and flag variables are created.

---

## 1. Pipeline Overview

| Phase | Script | Output | Variables Created |
|-------|--------|--------|-------------------|
| 2 | convert_all | Parquet | Date columns typed (no new vars) |
| 3–4 | validate_all, validate_values | Parquet + reports | `_val_*` flags |
| 5 | clean_all | parquet_clean | `IS_DUPLICATE`, partner flags, `_con_*`, `FLAG_*` |
| 6 | assemble_clean | patient_level, reports | Patient-level derived, `MODALITY_*` |

---

## 2. Convert Phase (Phase 2)

**Source:** `src/load/convert.py`, `scripts/convert_all.py`

No new columns are added. Existing date columns (e.g. BIRTH_DATE, DX_DATE, ADMIT_DATE) are auto-detected and converted from string (SAS DATE9., DATETIME, YYYYMMDD) to Polars Date type.

---

## 3. Validation Flags (`_val_*`)

**Source:** `src/validate/values.py`, `scripts/validate_values.py`  
**Output:** Parquet files in `parquet_dir` with `_val_*` columns appended.

| Variable | Table(s) | Creation logic |
|----------|----------|----------------|
| `{COL}_val_code` | Coded fields | 1 = value not in valueset; 0 = valid or null. Uses valuesets.csv. NI/UN/OT always valid. |
| `{COL}_val_range` | VITAL | 1 = value outside plausible range (e.g. HT 50–272 cm, WT 1–500 kg); 0 = in range. |
| `RESULT_NUM_val_range` | LAB_RESULT_CM | 1 = RESULT_NUM outside LOINC-specific range (HL_LAB_RANGES); 0 = in range. |
| `RESULT_UNIT_val_missing` | LAB_RESULT_CM | 1 = RESULT_NUM present but RESULT_UNIT null/empty; 0 = otherwise. |
| `DX_val_icd_concordance` | DIAGNOSIS | 1 = ICD version–date mismatch (ICD-9 after Jan 2016, or ICD-10 before Jul 2015 for non-mapped partners); 0 = concordant or in grace period. |
| `_val_admit_discharge` | ENCOUNTER | 1 = DISCHARGE_DATE &lt; ADMIT_DATE; 0 = otherwise. |
| `_val_same_day` | ENCOUNTER | 1 = ADMIT_DATE == DISCHARGE_DATE; 0 = otherwise. |
| `{COL}_val_future` | All | 1 = date &gt; cutoff (default 2026-12-31); 0 = otherwise. |
| `_val_enr_dates` | ENROLLMENT | 1 = ENR_START_DATE &gt; ENR_END_DATE; 0 = otherwise. |
| `HISTOLOGY_val_hl` | TUMOR_REGISTRY | 1 = HISTOLOGY not in HL range 9650–9667; 0 = in range. |
| `STAGE_GROUP_val_format` | TUMOR_REGISTRY | 1 = STAGE_GROUP not in expected format; 0 = valid. |
| `AGE_AT_DIAGNOSIS_val_range` | TUMOR_REGISTRY | 1 = AGE_AT_DIAGNOSIS &lt; 0 or (not 200 and &gt; 120); 0 = in range. |
| `{tx_col}_val_before_dx` | TUMOR_REGISTRY | 1 = chemo/radiation date &lt; DATE_OF_DIAGNOSIS; 0 = otherwise. |
| `PRIMARY_SITE_val_hl` | TUMOR_REGISTRY | 1 = PRIMARY_SITE not in HL site list; 0 = in list. |

---

## 4. Clean Flags (Phase 5)

**Source:** `src/clean/dedup.py`, `src/clean/harmonize.py`, `src/clean/flags_diagnosis_provider.py`  
**Output:** Parquet in parquet_clean with clean flags.

### 4.1 Duplicate flag

| Variable | Table(s) | Creation logic |
|----------|----------|----------------|
| `IS_DUPLICATE` | DIAGNOSIS, PROCEDURES, LAB_RESULT_CM, ENCOUNTER, VITAL, PRESCRIBING | 1 = row shares composite key with another; 0 = unique. Keys: ID+DX_DATE+DX (DIAGNOSIS), ID+PX_DATE+PX (PROCEDURES), etc. |

### 4.2 Partner provenance flags

| Variable | Creation logic |
|----------|----------------|
| `ICD_MAPPED` | 1 = SOURCE in {AMS, UMI} (retrospective ICD-9→ICD-10 mapping); 0 = otherwise. |
| `CLAIMS_ONLY` | 1 = SOURCE = FLM; 0 = otherwise. |
| `DEATH_ONLY` | 1 = SOURCE = VRT; 0 = otherwise. |

### 4.3 Cross-table consistency flags (`_con_`)

| Variable | Table(s) | Creation logic |
|----------|----------|----------------|
| `_con_outside_encounter` | Event tables | 1 = event date not within any encounter ADMIT_DATE–DISCHARGE_DATE (±1 day); 0 = within. |
| `_con_outside_enrollment` | ENCOUNTER | 1 = ADMIT_DATE not covered by any ENROLLMENT [ENR_START_DATE, ENR_END_DATE]; 0 = covered. |
| `_con_no_enrollment` | ENCOUNTER | 1 = patient has no ENROLLMENT records; 0 = has enrollment. |

### 4.4 Diagnosis and provider flags

See `docs/FLAG_CODES.md` for code sets.

| Variable | Table(s) | Creation logic |
|----------|----------|----------------|
| `FLAG_HL_DX` | DIAGNOSIS | 1 = DX in cohort HL set (149 codes; excludes 201.3x, C81.5x/6x); 0 = not HL. |
| `FLAG_SURVIVORSHIP_DX` | DIAGNOSIS | 1 = DX in survivorship set (V87.41/42/43/46, V15.3, Z92.21–25, Z92.3, Z08*, Z85*); 0 = not. |
| `FLAG_CANCER_PROVIDER` | PROVIDER | 1 = PROVIDER_SPECIALTY_PRIMARY matches oncology keywords; 0 = otherwise. |

---

## 5. Patient-Level Derived Variables (Phase 6)

**Source:** `src/report/quality_report.py` — `build_patient_level_derived()`  
**Output:** `derived/patient_level.parquet` (one row per HL patient)

| Variable | Type | Creation logic |
|----------|------|----------------|
| `FIRST_HL_DX_DATE` | Date | Earliest DX_DATE for HL codes (C81*, 201*) from DIAGNOSIS. |
| `FIRST_HL_TX_DATE` | Date | Earliest treatment date from PROCEDURES (SCT CPTs), PRESCRIBING, or TUMOR_REGISTRY chemo/radiation dates. |
| `DX_TO_TX_DAYS` | Int64 | FIRST_HL_TX_DATE − FIRST_HL_DX_DATE (null if no treatment). |
| `AGE_AT_HL_DX` | Float64 | (FIRST_HL_DX_DATE − BIRTH_DATE) / 365.25. Masked birth dates (01JAN1900) → null. |
| `AGE_BAND` | String | &lt;21, 21-39, 40-64, 65+. Masked ages → 65+. |
| `HL_SUBTYPE` | String | From C81.x 4th character: nodular lymphocyte predominant, nodular sclerosis, mixed cellularity, etc. |
| `PAYER_AT_DX` | String | PAYER_TYPE_PRIMARY from encounter with ADMIT_DATE closest to FIRST_HL_DX_DATE. |
| `INSURANCE_CONTINUITY` | Int8 | 1 = enrollment covers [first DX, last encounter]; 0 = gap. |
| `REGION` | String | Southeast (AL, AR, FL, GA, KY, LA, MS, NC, SC, TN, VA, WV) vs Other from LDS_ADDRESS_HISTORY.ADDRESS_STATE. |

---

## 6a. Encounter-Payer Summary (Phase 14)

**Source:** `src/report/encounter_payer_summary.py` — `build_encounter_payer_summary()`  
**Output:** `derived/encounter_payer_summary.parquet` (one row per patient with encounters)

| Variable | Type | Creation logic |
|----------|------|----------------|
| `N_ENCOUNTERS` | Int64 | Count of ENCOUNTER rows per patient |
| `N_ENCOUNTERS_WITH_PAYER` | Int64 | Count of rows where PAYER_TYPE_PRIMARY is non-null, non-empty, and not in {NI, UN, OT} |
| `N_DISTINCT_PAYERS` | Int64 | Count of distinct valid PAYER_TYPE_PRIMARY values per patient |
| `PAYER_PRIMARY` | String | Most frequent valid PAYER_TYPE_PRIMARY; null if none |
| `PAYER_TRANSITION` | Int8 | 1 if N_DISTINCT_PAYERS &gt; 1; 0 otherwise |

---

## 6. Modality Flags (Phase 7)

**Source:** `src/clean/outcomes_flags.py`, Outcomes.csv  
**Output:** Added to `patient_level.parquet` (MODALITY_* columns)

| Variable | Creation logic |
|----------|----------------|
| `MODALITY_SCT` | 1 = patient has PROCEDURES.PX in SCT CPT set (38240–38242, etc.) or matching LAB_LOINC/DIAGNOSIS.DX per Outcomes.csv; 0 = no match. |
| `MODALITY_MAMMO` | Same pattern for mammogram codes. |
| `MODALITY_BREAST_MRI` | Same pattern for breast MRI. |
| `MODALITY_ECHO` | Same pattern for echocardiogram. |
| `MODALITY_STRESS` | Same pattern for stress test. |
| `MODALITY_ECG` | Same pattern for electrocardiogram. |
| `MODALITY_MUGA` | Same pattern for MUGA. |
| `MODALITY_PFT` | Same pattern for pulmonary function test. |
| `MODALITY_TSH` | Same pattern for TSH. |
| `MODALITY_CBC` | Same pattern for CBC. |

---

## 7. Cohort Summary Variables

**Source:** `src/validate/cohort.py` — `build_cohort_summary_df()`  
**Output:** `reports/cohort_summary.csv` (one row per HL patient)

| Variable | Creation logic |
|----------|----------------|
| `in_method_a` | True = patient has 2+ distinct DX_DATEs for HL codes. |
| `in_method_b` | True = patient has 2+ distinct ADMIT_DATEs from encounters linked to HL DX. |
| `icd_flag` | ICD9_ONLY, ICD10_ONLY, BOTH, or UNKNOWN. |
| `has_enrollment` | True = patient has ENROLLMENT record; False = no enrollment. |
| `partner` | SOURCE/SITE from first HL DX record. |
| `earliest_dx_date` | Min DX_DATE for HL codes. |
| `latest_dx_date` | Max DX_DATE for HL codes. |
| `n_hl_dx_records` | Count of HL diagnosis records. |

---

## 8. Helper Functions

| Function | Source | Purpose |
|----------|--------|---------|
| `flag_small_cell()` | structural.py | Returns "N ⚠" for counts 1–10 (markdown reports). |
| `_suppress()` | scripts | Returns "-" for counts 1–10 (CSV outputs). |

---

## 9. References

- **Flag codes:** `docs/FLAG_CODES.md`
- **Date parsing:** `.planning/docs/DATE_PARSING_FALLBACKS.md`
- **Outcomes schema:** `.planning/docs/OUTCOMES_XLSX_SCHEMA.md` (now CSV)
- **Path resolution:** `.planning/docs/PATH_RESOLUTION.md`
