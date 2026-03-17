# Insurance Summary (Phase 15)

Summary tables from encounter-payer summary. Counts 1–10 flagged (⚠) for HIPAA.

## Counts by payer at first HL diagnosis

| Payer category | N |
|----------------|---|
| Medicare | 2 ⚠ |
| Medicaid | 3 ⚠ |
| Private | 5 ⚠ |
| Other government | 1 ⚠ |
| Unknown | 1 ⚠ |

## Counts by payer at first chemotherapy

| Payer category | N |
|----------------|---|
| Medicare | 2 ⚠ |
| Medicaid | 3 ⚠ |
| Private | 5 ⚠ |
| Other government | 1 ⚠ |
| Unknown | 1 ⚠ |

## Cross-tab: Payer at first diagnosis vs payer at first chemotherapy

| Payer (first DX) | Medicare | Medicaid | Private | Other government | Unknown | Total |
|---|---|---|---|---|---|---|
| Medicare | 2 ⚠ | 0 | 0 | 0 | 0 | 2 ⚠ |
| Medicaid | 0 | 3 ⚠ | 0 | 0 | 0 | 3 ⚠ |
| Private | 0 | 0 | 5 ⚠ | 0 | 0 | 5 ⚠ |
| Other government | 0 | 0 | 0 | 1 ⚠ | 0 | 1 ⚠ |
| Unknown | 0 | 0 | 0 | 0 | 1 ⚠ | 1 ⚠ |
| Total | 2 ⚠ | 3 ⚠ | 5 ⚠ | 1 ⚠ | 1 ⚠ | 12 |

## Payer transition prevalence

| Metric | Value |
|--------|-------|
| Patients with payer transition (1+ category change) | 2 ⚠ |
| Total N | 12 |
| % with transition | 17 |

## Dual-eligible prevalence

| Metric | Value |
|--------|-------|
| Patients dual-eligible (Medicare+Medicaid or code 14/141/142) | 0 |
| Patients not dual-eligible | 12 |
| Total N | 12 |
| % dual-eligible | 0 |

## Summary by treatment type

Cohorts: enrolled patients who had at least one occurrence of the treatment. Full counts by variable are in the CSV files below.

| Cohort | N | Summary file |
|--------|---|--------------|
| Chemo (any chemo) | 0 | insurance_summary_chemo.csv |
| Radiation (any radiation) | 0 | insurance_summary_radiation.csv |
| Stem cell transplant (any SCT) | 0 | insurance_summary_sct.csv |

Each CSV has: Variable, Category, N, Pct (general insurance + treatment-specific payer variables; PAYER_TRANSITION and DUAL_ELIGIBLE included).
