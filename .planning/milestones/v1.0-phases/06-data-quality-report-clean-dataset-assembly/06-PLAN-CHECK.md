# Phase 6 Plan Verification Report

**Phase:** 06-data-quality-report-clean-dataset-assembly  
**Phase Goal:** Produce a comprehensive data quality report and assemble final analysis-ready Parquet files with derived variables for the HL insurance inequities study.  
**Plans verified:** 2 (06-01, 06-02)  
**Status:** ISSUES FOUND  

---

## Summary

One **blocker** and zero warnings. Plans are structurally sound (all tasks have files, action, verify, done) and the dependency graph is valid. The main gap is requirement coverage: REQ-06 is a core Phase 6 deliverable but is absent from both plans' `requirements` frontmatter.

---

## Coverage Summary

### Success Criteria vs Plans

| Success Criterion | Plan 01 | Plan 02 | Status |
|-------------------|---------|---------|--------|
| DQ report (4 dimensions, partner-stratified) | Task 2: aggregate_dq_metrics | Task 2: DATA_QUALITY_REPORT.md | Covered |
| HL-derived vars (all 9) | Task 1: build_patient_level_derived | Task 1: patient_level.parquet | Covered |
| Small cell suppression | Task 2: flag_small_cell throughout | Task 2: flag_small_cell for reports | Covered |
| Clean Parquet with flags retained | — | Task 1: copy to parquet_clean | Covered |
| CLEANING_DECISIONS.md | Task 2: generate_cleaning_decisions_content | Task 2: write file | Covered |

### Requirement Coverage (Frontmatter)

| Requirement | Description | In Plans | Status |
|-------------|-------------|----------|--------|
| REQ-03 | HL-specific cleaning, partner-stratified quality report | 01, 02 | Covered |
| REQ-04 | Run on HiPerGator HPC | 01, 02 | Covered |
| REQ-05 | HIPAA (small cell suppression) | 01, 02 | Covered |
| REQ-06 | Reusable cleaned output (Parquet + derived vars) | **—** | **MISSING** |

---

## Plan Summary

| Plan | Tasks | Files | Wave | Depends | Status |
|------|-------|-------|------|---------|--------|
| 06-01 | 2 | 2 | 1 | [] | Valid |
| 06-02 | 2 | 4 | 2 | [06-01] | Valid |

- **Dependency graph:** Acyclic. 06-02 correctly depends on 06-01.
- **Task completeness:** All 4 tasks have `<files>`, `<action>`, `<verify>`, `<done>`.
- **Scope:** 2 tasks per plan — within budget (target 2–3).

---

## Issues Found

### Blockers (must fix)

**1. [requirement_coverage] REQ-06 (reusable cleaned output) absent from plan requirements**

- **Description:** Phase 6 produces parquet_clean and patient_level.parquet — the main REQ-06 deliverables. Neither plan includes REQ-06 in its `requirements` frontmatter.
- **Plans:** 06-01, 06-02
- **Fix:** Add `REQ-06` to the `requirements` field in both plans, e.g. `requirements: [REQ-03, REQ-04, REQ-05, REQ-06]`.

---

### Structured Issues

```yaml
issues:
  - plan: "06-01"
    dimension: requirement_coverage
    severity: blocker
    description: "REQ-06 (reusable cleaned output) absent from requirements frontmatter"
    fix_hint: "Add REQ-06 to requirements: [REQ-03, REQ-04, REQ-05, REQ-06]"
  - plan: "06-02"
    dimension: requirement_coverage
    severity: blocker
    description: "REQ-06 (reusable cleaned output) absent from requirements frontmatter"
    fix_hint: "Add REQ-06 to requirements: [REQ-03, REQ-04, REQ-05, REQ-06]"
```

---

## Verification Dimensions

| Dimension | Result |
|-----------|--------|
| Requirement coverage | **FAIL** — REQ-06 missing from frontmatter |
| Task completeness | Pass — all tasks have files, action, verify, done |
| Dependency correctness | Pass — 06-02 → 06-01, no cycles |
| Key links planned | Pass — assemble_clean → quality_report; quality_report → structural/cohort/values |
| Scope sanity | Pass — 2 tasks per plan |
| Verification derivation | Pass — must_haves are user-observable (DQ report, derived vars, reports) |
| Context compliance | N/A — no CONTEXT.md |

---

## Derived Variable Coverage

All 9 required derived variables are specified in Plan 01 Task 1:

- AGE_AT_HL_DX
- AGE_BAND
- HL_SUBTYPE
- FIRST_HL_DX_DATE
- FIRST_HL_TX_DATE
- DX_TO_TX_DAYS
- PAYER_AT_DX
- INSURANCE_CONTINUITY
- REGION

---

## Recommendation

**1 blocker** needs a fix before execution. Add REQ-06 to the `requirements` frontmatter in both 06-01-PLAN.md and 06-02-PLAN.md, then re-run verification.

After that, plans are ready for `/gsd:execute-phase 06`.
