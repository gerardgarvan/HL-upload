# Phase 7: Add Modality Flags from Outcomes.xlsx

**Goal:** Use the Outcomes sheet as a code-to-modality lookup. Scan CDM tables for CPT/HCPCS/ICD-10/LOINC codes; add per-modality flags to patient_level. No join—Outcomes defines which codes map to which modality.

**Source:** Outcomes.xlsx (project root), **Outcomes sheet only**

**Modalities (10):**
- Stem cell transplant
- Mammogram
- Breast MRI
- Echocardiogram
- Stress test
- Electrocardiogram
- Multiple gated acquisition (MUGA)
- Pulmonary function test
- Thyroid stimulating hormone (TSH)
- Complete blood count (CBC)

**Code types:** CPT, HCPCS, ICD-10, LOINC  
**CDM tables:** PROCEDURES (PX), LAB_RESULT_CM (LAB_LOINC), DIAGNOSIS (DX)

**Dependencies:** Phase 6 (clean dataset, patient_level.parquet)

**Next steps:**
1. Inspect Outcomes sheet structure (columns for modality, code type, code value)
2. Build lookup: modality → {CPT/HCPCS codes}, {LOINC codes}, {ICD-10 codes}
3. Design flag logic (prefix, exact vs prefix match per code type)
