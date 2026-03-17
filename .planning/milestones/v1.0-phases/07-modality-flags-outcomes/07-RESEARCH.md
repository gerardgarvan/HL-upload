# Phase 7 Research: Outcomes.xlsx Schema

## Outcomes Sheet Structure

| Column    | Type   | Notes                                           |
|-----------|--------|-------------------------------------------------|
| Modality  | string | Forward-filled (first row per modality)         |
| Code system | string | CPT, HCPCS, ICD-10-PCS, ICD-10, LOINC; NaN = same as prior row |
| Code      | string | Actual code value                               |
| Description | string | Human-readable description                      |

**Shape:** 138 rows × 4 columns

## Code Systems

- **CPT** — procedure codes → PROCEDURES.PX (PX_TYPE 09)
- **HCPCS** — procedure codes → PROCEDURES.PX (PX_TYPE HC)
- **ICD-10-PCS** — procedure codes → DIAGNOSIS.DX (DX_TYPE 10) or PROCEDURES if applicable
- **ICD-10** — diagnosis/procedure → DIAGNOSIS.DX
- **LOINC** — lab codes → LAB_RESULT_CM.LAB_LOINC

Note: PROCEDURES stores both CPT and HCPCS in PX. DIAGNOSIS stores ICD-10 (including PCS) in DX. Match by code value.

## Modalities (10)

| Modality                          | Slug    | Code counts (approx) |
|-----------------------------------|---------|----------------------|
| Stem cell transplant              | SCT     | 59                   |
| Mammogram                         | MAMMO   | 10                   |
| Breast MRI                        | BREAST_MRI | 14                 |
| Echocardiogram                    | ECHO    | 8                    |
| Stress test                       | STRESS  | 2                    |
| Electrocardiogram                 | ECG     | 11                   |
| Multiple gated acquisition (MUGA) | MUGA    | 9                    |
| Pulmonary function test           | PFT     | 12                   |
| Thyroid stimulating hormone       | TSH     | 4                    |
| Complete blood count              | CBC     | 9                    |

## CDM Table Mapping

| Code type      | CDM table   | Column    | Match logic          |
|----------------|-------------|-----------|----------------------|
| CPT, HCPCS     | PROCEDURES  | PX        | Exact (normalize case) |
| LOINC          | LAB_RESULT_CM | LAB_LOINC | Exact (LOINC format) |
| ICD-10-PCS, ICD-10 | DIAGNOSIS | DX      | Exact; strip dots for ICD-10 |

DX may be dotted (C81.10) or undotted. ICD-10-PCS codes in Outcomes (e.g. 30230C0) have no dots. Normalize DX by stripping dots before match.
