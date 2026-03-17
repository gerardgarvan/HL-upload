# HL Data Pipeline — Hardening & Documentation

## What This Is

A clinical data pipeline that loads, validates, cleans, and summarizes OneFlorida+ PCORnet CDM data for a Hodgkin Lymphoma (HL) cohort study. It converts raw CSV extracts to typed Parquet, applies validation and deduplication, derives patient-level variables (demographics, treatment, payer), and generates quality reports and insurance summaries with HIPAA-compliant small-cell suppression.

## Core Value

Data correctness — if the output data is wrong, nothing else matters. Every number in every report must be explainable and traceable back to its source.

## Requirements

### Validated

- CSV-to-Parquet conversion with automatic date detection (3 formats) — existing
- Structural validation: schema comparison, PATID/ENCOUNTERID integrity, completeness profiling — existing
- HL cohort verification: 149 ICD codes (ICD-9 + ICD-10), dual-format matching — existing
- Composite-key deduplication per table with IS_DUPLICATE flags — existing
- Cross-table consistency flagging (demographic, temporal, enrollment) — existing
- Partner provenance flags (ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY) — existing
- Diagnosis flags (FLAG_HL_DX, FLAG_SURVIVORSHIP_DX) and provider flags (FLAG_CANCER_PROVIDER) — existing
- Treatment modality flags (HAD_CHEMO, HAD_RADIATION, HAD_SCT) from Outcomes.csv — existing
- Patient-level derived dataset (patient_level.parquet) — existing
- Payer analysis: effective payer logic, dual-eligible detection, payer at treatment windows — existing
- Small-cell suppression (HIPAA, threshold 10) across all reports — existing
- Quality reports: DATA_QUALITY_REPORT.md, CLEANING_DECISIONS.md — existing
- Basic test suite: cohort, structural, flags, modality, suppress — existing
- Pre-commit hooks: ruff lint/format + pytest — existing

### Active

- [ ] Code-level documentation: docstrings for all public functions and modules explaining what and why
- [ ] Pipeline overview document: high-level flow from raw CSV to final outputs, readable by collaborators
- [ ] Expanded data validation: catch silent errors, dropped records, wrong joins before they reach reports
- [ ] Robustness: handle edge cases, bad input, and schema changes without breaking silently
- [ ] Reproducibility: a collaborator can clone the repo, follow setup docs, and reproduce outputs
- [ ] Audit unknown problem areas: systematic review of pipeline logic to surface issues the author may not be aware of

### Out of Scope

- Rewriting the pipeline in a different framework — the Polars-based architecture works
- Adding new data sources or CDM tables beyond the current 22 — focus on existing pipeline
- Building a web interface or dashboard — this is a batch processing pipeline
- Performance optimization for its own sake — only if correctness or robustness requires it

## Context

- **Data**: OneFlorida+ PCORnet CDM, 22 tables, Mailhot HL cohort (extracted 2025-09-15)
- **Environment**: HyperGator HPC (UFL), orange filesystem (source), blue filesystem (scratch/output)
- **Stack**: Python 3.11, Polars, PyArrow, conda/mamba, pytest, ruff
- **Pipeline phases**: convert (CSV to Parquet) -> validate (structural) -> clean (dedup/flags) -> assemble (patient-level + reports) -> insurance summary
- **Known fragile areas**: insurance/payer logic (complex fallback chains), date parsing (3-format detection), many-to-many joins (encounter-based), report generation scripts
- **Existing codebase map**: `.planning/codebase/` (7 documents, freshly mapped 2026-03-17)

## Constraints

- **HIPAA**: All published counts must pass small-cell suppression (1-10 -> "-"); no patient-level data in reports
- **Data access**: Source CSVs are read-only on HPC orange filesystem; cannot modify source data
- **Python 3.11**: Locked by HPC environment and existing environment.yml
- **Polars**: Core processing library; switching would require full rewrite

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Harden before extending | Pipeline logic is complex and hard to follow; adding features on a shaky foundation compounds problems | — Pending |
| Document for collaborators + future self | Pipeline needs to be reproducible and maintainable by people who didn't write it | — Pending |
| Systematic audit of unknowns | Author suspects problems they're unaware of; proactive review is more efficient than reactive debugging | — Pending |

---
*Last updated: 2026-03-17 after initialization*
