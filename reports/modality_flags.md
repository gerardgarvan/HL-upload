# Modality Flags from Outcomes.csv

## Source

Outcomes.csv, columns: Modality, Code system, Code, Description.

Modality and Code system are forward-filled (NaN = same as previous row).

## Code-to-Table Mapping

| Code type | CDM table | Column |
|-----------|-----------|--------|
| CPT, HCPCS | PROCEDURES | PX |
| LOINC | LAB_RESULT_CM | LAB_LOINC |
| ICD-10, ICD-10-PCS | DIAGNOSIS | DX |

## Modalities

| Slug | Full name | CPT/HCPCS | LOINC | ICD-10 |
|------|-----------|-----------|-------|--------|
| SCT | Stem cell transplant | 5 | 0 | 54 |
| MAMMO | Mammogram | 7 | 0 | 3 |
| BREAST_MRI | Breast MRI | 8 | 0 | 6 |
| ECHO | Echocardiogram | 6 | 0 | 2 |
| STRESS | Stress test | 2 | 0 | 0 |
| ECG | Electrocardiogram | 10 | 0 | 1 |
| MUGA | Multiple gated acquisition (MUGA) | 6 | 0 | 2 |
| PFT | Pulmonary function test | 11 | 0 | 1 |
| TSH | Thyroid stimulating hormone | 2 | 2 | 0 |
| CBC | Complete blood count | 4 | 5 | 0 |

## Flag Logic

`MODALITY_{slug}` = 1 if patient has ≥1 matching code in PROCEDURES, LAB_RESULT_CM, or DIAGNOSIS, else 0.

- **PX** (PROCEDURES): normalized to uppercase, stripped, for exact match against Outcomes CPT/HCPCS codes
- **LAB_LOINC**: normalized to uppercase for match against Outcomes LOINC codes
- **DX** (DIAGNOSIS): dots stripped, uppercase, for ICD-10/ICD-10-PCS matching
