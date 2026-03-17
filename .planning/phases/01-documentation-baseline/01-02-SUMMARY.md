---
phase: 01-documentation-baseline
plan: 02
subsystem: [src/clean, src/report]
tags: [documentation, docstrings, clinical-rationale, payer-logic]
completed: 2026-03-17
duration_minutes: 11

requires:
  tables: [DIAGNOSIS, PROCEDURES, LAB_RESULT_CM, ENCOUNTER, VITAL, PRESCRIBING, DEMOGRAPHIC, DEATH, TUMOR_REGISTRY, ENROLLMENT, PROVIDER, LDS_ADDRESS_HISTORY]
  constants: [DEDUP_KEYS, PARTNER_FLAGS, ONCOLOGY_KEYWORDS, MODALITY_SLUG_MAP, HL_SUBTYPE_MAP, PAYER_AT_TREATMENT_WINDOW_DAYS, DUAL_ELIGIBLE_CODES]

provides:
  documentation:
    - "Complete Google-style docstrings for 32+ functions across src/clean/ and src/report/"
    - "Module-level docstrings explaining Phase 5/6+ pipeline position"
    - "Clinical rationale for all payer logic, treatment windows, and dual-eligible detection"
    - "Documented constants: DEDUP_KEYS, PARTNER_FLAGS, payer constants, HL_SUBTYPE_MAP, treatment CPTs"

affects:
  modules: [src/clean/dedup.py, src/clean/harmonize.py, src/clean/flags_diagnosis_provider.py, src/clean/outcomes_flags.py, src/report/quality_report.py, src/report/encounter_payer_summary.py, src/report/site_table.py]
  future_work: ["Audit unknowns flagged in TODO(audit) comments", "Validate payer logic assumptions with stakeholders", "Consider migrating pandas dependency in outcomes_flags.py"]

tech-stack:
  added: []
  patterns: ["Google-style docstrings", "Clinical rationale in docstrings", "TODO(audit) for unknowns"]

key-files:
  created: []
  modified:
    - src/clean/__init__.py
    - src/clean/dedup.py
    - src/clean/harmonize.py
    - src/clean/flags_diagnosis_provider.py
    - src/clean/outcomes_flags.py
    - src/report/__init__.py
    - src/report/quality_report.py
    - src/report/encounter_payer_summary.py
    - src/report/site_table.py

decisions:
  - "Google-style docstrings for ALL functions (public, private, helpers) per Phase 1 context"
  - "Brief clinical rationale in docstrings (one sentence 'why') per locked decision"
  - "Side effects mentioned naturally in description paragraph, not separate section"
  - "Document actual behavior (what code DOES), not intended behavior per Phase 1 context"
  - "TODO(audit) comments mark unknowns with severity assessment where applicable"

metrics:
  files_modified: 9
  functions_documented: 32
  constants_documented: 10
  todo_audit_added: 8
  tests_passing: 22
---

# Phase 1 Plan 02: Core Module Documentation Summary

**One-liner:** Added comprehensive Google-style docstrings to 32+ functions across src/clean/ and src/report/ with clinical rationale for complex payer logic, treatment windows, and dual-eligible detection.

## What Was Built

### Task 1: src/clean/ Core Modules (17 functions, 4 modules)
- **dedup.py (6 functions):** Composite-key duplicate detection, demographic consistency checks, temporal window validation, death date consistency, Parquet write with stats
  - Documented DEDUP_KEYS: Composite key rationale per table (patient+date+code for clinical events)
  - Documented null dedup behavior: Polars treats null != null (correct for unknowns)
  - TODO(audit): VITAL dedup uses only MEASURE_DATE without vital type — may flag legitimate multiple measurements
- **harmonize.py (3 functions):** Partner provenance flags, enrollment coverage checks
  - Documented PARTNER_FLAGS: ICD_MAPPED (AMS/UMI retrospective coding), CLAIMS_ONLY (FLM claims data), DEATH_ONLY (VRT death registry)
  - Documented many-to-many join memory management (lazy evaluation)
  - TODO(audit): Verify partner abbreviations match current data sources
- **flags_diagnosis_provider.py (5 functions):** HL diagnosis, survivorship, cancer provider flags
  - Documented ONCOLOGY_KEYWORDS: Provider specialty regex patterns with naming variations
  - Documented SURVIVORSHIP codes: Personal history of treatment (V87.4x, Z92.2x, Z08, Z85)
  - Clinical context: FLAG_HL_DX for cohort inclusion, FLAG_SURVIVORSHIP_DX for survivorship phase
- **outcomes_flags.py (3 functions):** Treatment modality flags from Outcomes.csv
  - Documented MODALITY_SLUG_MAP: Treatment modalities (SCT, CHEMO) and surveillance (cardiac, pulmonary, lab)
  - TODO(audit): Pandas dependency in otherwise Polars codebase — consider migration

### Task 2: src/report/ Modules (15+ functions, 3 modules)
- **quality_report.py (11 functions):** Patient-level derived variables, DQ metrics, cleaning decisions
  - Documented HL_SUBTYPE_MAP: ICD-10 4th character histologic subtype classification (nodular sclerosis most common)
  - Documented SOUTHEAST_STATES: Geographic region for access/treatment analysis
  - Documented _suppress: HIPAA small-cell suppression (counts 1-10 → "-")
  - Documented build_patient_level_derived: Age, HL subtype, treatment dates, payer, insurance continuity, region
  - Documented aggregate_dq_metrics: Kahn Framework (completeness, conformance, plausibility, persistence)
  - TODO(audit): SCT_CPTS constant includes radiation CPTs (misnomer — consider renaming)
- **encounter_payer_summary.py (12 functions):** Complex payer logic with effective payer, dual-eligible detection
  - Documented INVALID_PAYER: NI/UN/OT sentinels trigger secondary fallback
  - Documented INCLUDE_99_AS_SENTINEL: 99/9999 semantics vary by partner (currently False = valid but unavailable)
  - Documented DUAL_ELIGIBLE_CODES: 14/141/142 PCORnet dual Medicare-Medicaid codes
  - Documented PAYER_AT_TREATMENT_WINDOW_DAYS: 30-day window for payer-at-treatment (arbitrary — no clinical standard)
  - Documented _collapse_payer_category: PCORnet typology prefix→category (1xx→Medicare, 2xx→Medicaid, etc.)
  - Documented _effective_payer_and_dual_exprs: Primary→secondary fallback, dual-eligible detection logic
  - Documented build_encounter_payer_summary: Payer-focused patient-level summary with treatment windows
  - TODO(audit): 99/9999 vs NI/UN/OT semantic distinction unclear; 30-day window arbitrary; dual-eligible when secondary absent
- **site_table.py (18 functions):** Per-site HL summary tables with small-cell suppression
  - Documented site assignment: Predominant SOURCE (most records), TMA+TMC→TM
  - Documented small-cell handling: flag_small_cell marks counts 1-10 with "[!]" for HIPAA compliance

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written. All verification checks passed (ruff lint, ruff format, pytest).

## Verification Results

- [x] `ruff check src/clean/ src/report/` — All checks passed (1 line length fixed + formatted)
- [x] `ruff format --check src/clean/ src/report/` — All files formatted correctly
- [x] `pytest tests/ -x` — All 22 tests passing (no regressions)
- [x] Every function in src/clean/ (17 functions) and src/report/ (15+ functions) has Google-style docstrings
- [x] All 9 modules have module-level docstrings with Phase 5/6+ pipeline position
- [x] Complex payer logic documented: effective payer fallback, dual-eligible detection, 30-day treatment windows, sentinel handling
- [x] DEDUP_KEYS, PARTNER_FLAGS, payer constants, HL_SUBTYPE_MAP documented with clinical rationale
- [x] 8 TODO(audit) comments added for unknowns: VITAL dedup, partner abbreviations, pandas dependency, 99/9999 semantics, 30-day window, dual-eligible when secondary absent, SCT_CPTS misnomer

## Key Decisions

1. **Documented actual behavior, not intended:** Per Phase 1 context, docstrings describe what code DOES (e.g., null dedup behavior, effective payer fallback chain) with suspected issues flagged separately in TODO(audit).

2. **Clinical rationale brevity:** One-sentence clinical rationale per function explains "why" logic exists (e.g., "Dual-eligible patients have complex payer status affecting cost and access") without duplicating full clinical context reserved for PIPELINE.md.

3. **TODO(audit) severity:** Unknowns categorized by potential correctness impact:
   - HIGH: Pandas dependency (consistency), dual-eligible detection gaps (data loss)
   - MEDIUM: 99/9999 sentinel semantics (varies by partner), 30-day window (arbitrary)
   - LOW: Partner abbreviations (maintenance), VITAL dedup granularity (edge case), SCT_CPTS naming (cosmetic)

4. **Payer logic complexity:** encounter_payer_summary.py has most complex logic in codebase — extensive docstrings for effective payer fallback, dual-eligible detection, sentinel handling, and treatment windows. Every magic number (30 days, window sizes) documented with clinical/data rationale or flagged as arbitrary.

## Next Steps

1. **Plan 03:** Document src/validate/ modules (cohort, structural, values validation)
2. **Audit log assembly:** Collect TODO(audit) comments across Plans 01-03 for docs/AUDIT_LOG.md
3. **Stakeholder review:** Validate payer logic assumptions (99/9999 semantics, 30-day windows, dual-eligible codes) with data partners and clinical team

## Authentication Gates

None.

## Commits

| Task | Commit | Message | Files |
|------|--------|---------|-------|
| 1 | 3e13f46 | feat(01-02): add docstrings to src/clean/ core modules | src/clean/__init__.py, dedup.py, harmonize.py, flags_diagnosis_provider.py, outcomes_flags.py |
| 2 | 09d13b6 | feat(01-02): add docstrings to src/report/ modules | src/report/__init__.py, quality_report.py, encounter_payer_summary.py, site_table.py |

---

**Status:** ✅ Complete — all 32+ functions documented, all tests passing, ready for Plan 03
