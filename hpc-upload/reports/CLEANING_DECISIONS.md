# Cleaning Decisions


**Generated:** 2026-03-02 15:00:51

Reference: Phase 3–5 reports (structural, values, cohort, dedup, harmonization).

## 1. Value Set Validation
- Coded fields validated against valuesets.csv
- NI (No Information), UN (Unknown), OT (Other): treated as valid missing codes

## 2. Plausibility Ranges
### Vital Signs (VITAL_RANGES)
- HT: 50.0–272.0
- WT: 1.0–500.0
- SYSTOLIC: 40.0–300.0
- DIASTOLIC: 20.0–200.0
- ORIGINAL_BMI: 8.0–100.0
### HL Lab Ranges (HL_LAB_RANGES)
- WBC (6690-2): 0–500 10*3/uL
- WBC alt (26464-8): 0–500 10*3/uL
- Hemoglobin (718-7): 0–30 g/dL
- Hgb alt (30313-1): 0–30 g/dL
- Platelets (777-3): 0–5000 10*3/uL
- ... (20 LOINC codes total)

## 3. Temporal Rules
- ICD-10 transition: 2015-10-01; grace period Jul 2015–Jan 2016
- DX_TO_TX_DAYS: 0–365 days considered plausible; outside flagged

## 4. Deduplication Keys (DEDUP_KEYS)
- DIAGNOSIS: ID, DX_DATE, DX
- PROCEDURES: ID, PX_DATE, PX
- LAB_RESULT_CM: ID, SPECIMEN_DATE, LAB_LOINC
- ENCOUNTER: ID, ADMIT_DATE, ENC_TYPE, FACILITYID
- VITAL: ID, MEASURE_DATE
- PRESCRIBING: ID, RX_ORDER_DATE, RXNORM_CUI

## 5. Partner Flags
- **ICD_MAPPED**: AMS, UMI
- **CLAIMS_ONLY**: FLM
- **DEATH_ONLY**: VRT

## 6. Masked Values
- BIRTH_DATE = 1900-01-01 → AGE_BAND folded into 65+
- AGE_AT_DIAGNOSIS = 200 (implausible placeholder) → 65+ band

## 7. TUMOR_REGISTRY Date Formats
- Supported: MM/DD/YYYY, YYYY.MM.DD, %d%b%Y (DATE9), %Y%m%d (YYYYMMDD)

## 8. INSURANCE_CONTINUITY
- Flag = 1 when gap > 30 days in enrollment covering treatment window
- Treatment window: FIRST_HL_DX_DATE to min(FIRST_HL_TX_DATE + 365, last encounter)

## 9. Small Cell Suppression
- SMALL_CELL_THRESHOLD = 10
- Counts 1–10 suppressed in reports (dash in CSV, warning marker in markdown)