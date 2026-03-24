# Roadmap: HL Data Pipeline — Hardening & Documentation

## Overview

This roadmap transforms an existing, functional clinical data pipeline into a trustworthy, reproducible system. We start by understanding and documenting what exists (Phase 1), add validation checkpoints to catch silent failures (Phase 2), lock in correctness with comprehensive tests (Phase 3), and finally make it reproducible for collaborators (Phase 4). The approach is documentation-first: understand before changing, validate before testing, test before publishing.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (e.g., 2.1): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Documentation & Baseline** - Understand and document the pipeline; capture golden outputs for regression protection (completed 2026-03-17)
- [x] **Phase 2: Validation & Suppression Hardening** - Add checkpoints at phase boundaries; centralize HIPAA-compliant small-cell suppression (completed 2026-03-17)
- [x] **Phase 3: Test Coverage for Fragile Areas** - Lock in correctness with comprehensive tests for payer logic, date parsing, and reports (completed 2026-03-17)
- [ ] **Phase 4: Reproducibility & Onboarding** - Enable collaborators to clone, configure, and run the pipeline

## Phase Details

### Phase 1: Documentation & Baseline
**Goal**: Pipeline logic is documented and understood; golden output files protect against regressions
**Depends on**: Nothing (first phase)
**Requirements**: BASE-01, DOC-01, DOC-02, DOC-03
**Success Criteria** (what must be TRUE):
  1. All public functions in `src/` have Google-style docstrings explaining purpose, parameters, returns, and clinical rationale
  2. All modules in `src/` have module-level docstrings explaining what the module does and how it fits in the pipeline
  3. `docs/PIPELINE.md` exists and describes the full data flow from raw CSV to final outputs, readable by a collaborator unfamiliar with the codebase
  4. Golden output files are captured for all pipeline phases (converted Parquet, cleaned tables, patient_level.parquet, quality reports, insurance summaries) enabling regression comparison
**Plans:** 5/5 plans complete

Plans:
- [ ] 01-01-PLAN.md — Docstrings for src/load/, src/validate/, src/clean/validate/ (DOC-01, DOC-02)
- [ ] 01-02-PLAN.md — Docstrings for src/clean/ core and src/report/ (DOC-01, DOC-02)
- [ ] 01-03-PLAN.md — Docstrings for scripts/ and docs/AUDIT_LOG.md (DOC-01, DOC-02)
- [ ] 01-04-PLAN.md — Pipeline overview document docs/PIPELINE.md (DOC-03)
- [ ] 01-05-PLAN.md — Golden baseline capture script and manifest (BASE-01)

### Phase 2: Validation & Suppression Hardening
**Goal**: Silent failures are caught at phase boundaries; HIPAA compliance is centralized and consistent
**Depends on**: Phase 1
**Requirements**: VAL-01, VAL-02, VAL-03, VAL-04
**Success Criteria** (what must be TRUE):
  1. Row-count validation executes at each phase boundary and fails fast with clear errors when records are silently lost
  2. Schema validation checks expected columns and dtypes after each phase writes output, catching schema drift or type degradation
  3. Configuration validation runs on pipeline startup and fails fast with actionable errors for missing files, bad paths, or invalid settings
  4. Small-cell suppression uses a single `_suppress()` function with a single threshold constant, and all report outputs have been audited for HIPAA compliance
**Plans:** 3/3 plans complete

Plans:
- [ ] 02-01-PLAN.md — Checkpoint module (row-count + schema validation) and config validation with startup summary (VAL-01, VAL-02, VAL-03)
- [ ] 02-02-PLAN.md — Centralized suppression module and rewire all report imports (VAL-04)
- [ ] 02-03-PLAN.md — Wire checkpoints into all 5 pipeline scripts (VAL-01, VAL-02, VAL-03)

### Phase 3: Test Coverage for Fragile Areas
**Goal**: Correctness of complex, fragile logic is locked in with comprehensive test coverage
**Depends on**: Phase 2
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. Tests cover payer logic including effective payer derivation, dual-eligible detection, fallback chains, and sentinel value handling with edge cases enumerated
  2. Tests cover date parsing for all 3 formats (MM/DD/YYYY, YYYY-MM-DD, YYYYMMDD) including edge cases for nulls, mixed formats, invalid dates, and tumor registry format
  3. Tests cover report generation including output structure verification, suppression applied correctly, and aggregation correctness
  4. Tests cover phase checkpoint validation including row-count matching and schema validation passing for expected inputs
**Plans**: 6 plans in 2 waves

Plans:
- [ ] 03-01-PLAN.md — Payer logic tests with exhaustive edge case coverage (TEST-01)
- [ ] 03-02-PLAN.md — Date parsing tests for all 3 SAS formats with edge cases (TEST-02)
- [ ] 03-03-PLAN.md — Report generation and dedup tests with suppression validation (TEST-03)
- [ ] 03-04-PLAN.md — Checkpoint validation tests with row-count and schema checks (TEST-04)
- [ ] 03-05-PLAN.md — TODO(audit) systematic resolution and conftest enhancement
- [ ] 03-06-PLAN.md — Test reorganization to mirror src/ structure and pytest config

### Phase 4: Reproducibility & Onboarding
**Goal**: A collaborator can clone the repo, follow setup documentation, and reproduce pipeline outputs
**Depends on**: Phase 3
**Requirements**: DOC-04
**Success Criteria** (what must be TRUE):
  1. `docs/SETUP.md` exists with step-by-step instructions covering environment setup (conda/mamba), configuration file setup, file path mapping (orange/blue filesystems), and execution of the full pipeline
  2. A collaborator with HyperGator access can follow the setup guide and successfully run the pipeline from raw CSVs to final outputs without needing to ask the author questions
**Plans:** 2 plans in 2 waves

Plans:
- [ ] 04-01-PLAN.md — Finalize environment.yml and create setup verification script (DOC-04)
- [ ] 04-02-PLAN.md — Write comprehensive docs/SETUP.md onboarding guide (DOC-04)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Documentation & Baseline | 5/5 | Complete    | 2026-03-17 |
| 2. Validation & Suppression Hardening | 3/3 | Complete    | 2026-03-17 |
| 3. Test Coverage for Fragile Areas | 0/6 | Complete    | 2026-03-17 |
| 4. Reproducibility & Onboarding | 0/2 | Not started | - |

### Phase 5: Insurance by Treatment Analysis
**Goal**: Presentation-ready summary tables of insurance coverage patterns stratified by treatment type (chemotherapy, radiation, SCT) with color-coded PNG, CSV/markdown, and styled HTML outputs
**Depends on**: Phase 4
**Requirements**: (none -- extends beyond v1 requirements; defined by CONTEXT.md decisions)
**Success Criteria** (what must be TRUE):
  1. New `scripts/build_insurance_by_treatment.py` replaces old insurance summary script with correct table structure
  2. Four treatment-stratified tables (chemo, radiation, SCT, overview) each with 9 payer category rows and 3 columns (Primary, First treatment, Last treatment) in N (%) format
  3. All tables output in 3 formats: color-coded PNG images, CSV + markdown, and styled HTML
  4. No HIPAA small-cell suppression applied (internal/working tables)
  5. Cohort sizes displayed in table headers
**Plans:** 2 plans in 2 waves

Plans:
- [ ] 05-01-PLAN.md — Core data aggregation script with CSV and markdown output
- [ ] 05-02-PLAN.md — PNG table rendering and styled HTML output with visual verification

### Phase 6: Post-Treatment Insurance: most prevalent payer after last chemo, radiation, or SCT date

**Goal**: Standalone summary tables showing post-treatment insurance distributions derived from the mode payer category across encounters after each patient's last treatment date (max of last chemo, radiation, SCT dates)
**Depends on:** Phase 5
**Requirements**: (none -- extends beyond v1 requirements; defined by CONTEXT.md decisions)
**Success Criteria** (what must be TRUE):
  1. New `scripts/build_post_treatment_insurance.py` computes post-treatment payer as mode category from encounters after max(LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE)
  2. Four standalone tables (combined, chemo cohort, radiation cohort, SCT cohort) each with single "Post-Treatment Insurance" column in N (%) format
  3. Combined table includes N/A row for patients with no treatment; per-cohort tables have 9 payer rows
  4. All tables output in 3 formats: color-coded PNG (matching Phase 5 style), CSV + markdown, and styled HTML
  5. No HIPAA small-cell suppression applied (internal working tables)
**Plans:** 2 plans in 2 waves

Plans:
- [ ] 06-01-PLAN.md — Core script with post-treatment payer computation and CSV/markdown output
- [ ] 06-02-PLAN.md — PNG table rendering and styled HTML output with visual verification

### Phase 7: present insurance tables in nice powerpoint

**Goal:** Assemble the insurance summary tables from Phases 5 and 6 into a polished, UF-branded PowerPoint presentation using python-pptx
**Depends on:** Phase 6
**Requirements:** (none -- extends beyond v1 requirements; defined by CONTEXT.md decisions)
**Success Criteria** (what must be TRUE):
  1. New `scripts/build_insurance_presentation.py` creates a PowerPoint from Phase 5/6 CSV data
  2. Title slide with presentation title and cohort sizes (total N, chemo N, radiation N, SCT N)
  3. 8 table slides: overview + combined post-treatment, then chemo pair, radiation pair, SCT pair — grouped by treatment type
  4. Native PowerPoint tables with UF Health branding (blue #003087, orange #FA4616), not embedded PNG images
  5. Each table slide has descriptive title and subtitle with cohort size (N=X)
  6. Output saved to reports/insurance_tables_YYYY-MM-DD.pptx (date-stamped)
  7. Script re-runnable — reads from reports/ CSVs, produces .pptx anytime
**Plans:** 1 plan in 1 wave

Plans:
- [ ] 07-01-PLAN.md — Build UF-branded PowerPoint presentation from Phase 5/6 insurance CSVs

### Phase 8: look at insurance in treatment windows but do a comparison of people whose ENR dates where within the timeframe vs those that weren't

**Goal:** Compare insurance coverage patterns between patients whose ENROLLMENT dates fully cover the +/-30 day treatment window vs those whose enrollment does not, producing side-by-side comparison tables for each treatment type plus a diagnostic breakdown of Unknown post-treatment payer patients
**Depends on:** Phase 7
**Requirements**: D-01 through D-23 (defined by CONTEXT.md decisions; extends beyond v1 requirements)
**Success Criteria** (what must be TRUE):
  1. New `scripts/build_insurance_enr_comparison.py` checks enrollment coverage using union-of-periods algorithm for 7 treatment windows
  2. Four comparison tables (DX 2-column, Chemo 4-column, Radiation 4-column, SCT 4-column) showing payer distributions split by enrollment coverage
  3. Diagnostic breakdown table showing Unknown post-treatment payer patients grouped by post-treatment encounter count (0, 1-5, 6-10, 11-20, 21+)
  4. All tables output in 3 formats: color-coded PNG (matching Phase 5/6 style), CSV + markdown, and styled HTML
  5. No HIPAA small-cell suppression applied (internal working tables)
  6. All Phase 8 tables added as slides to the existing PowerPoint presentation with UF Health branding
**Plans:** 2 plans in 2 waves

Plans:
- [ ] 08-01-PLAN.md — Core enrollment comparison script with ENR coverage logic, comparison tables, Unknown breakdown, CSV/PNG/HTML/markdown outputs
- [ ] 08-02-PLAN.md — Add Phase 8 slides to existing PowerPoint presentation

### Phase 9: Investigate unknown/unavailable insurance in enrollment windows and post-treatment encounters

**Goal:** Diagnostic investigation answering 5 questions about Unknown and Unavailable insurance patients — enrollment coverage cross-references, post-treatment encounter gap analysis per treatment type, and SCT primary Unknown discrepancy trace
**Depends on:** Phase 8
**Requirements**: DIAG-01, DIAG-02, DIAG-03, DIAG-04, DIAG-05
**Success Criteria** (what must be TRUE):
  1. Diagnostic script cross-references enrollment coverage for Unknown/Unavailable patients at treatment windows, showing ENR covers vs ENR gap counts for chemo, radiation, SCT (DIAG-01)
  2. For Unknown and Unavailable chemo post-treatment patients, report shows % with zero encounters after LAST_CHEMO_DATE with encounter count distribution (DIAG-02)
  3. For Unknown and Unavailable radiation post-treatment patients, report shows % with zero encounters after LAST_RADIATION_DATE with encounter count distribution (DIAG-03)
  4. For Unknown and Unavailable SCT post-treatment patients, report shows % with zero encounters after LAST_SCT_DATE with encounter count distribution (DIAG-04)
  5. Patient-level trace for 4 SCT patients with primary Unknown explains mechanism causing first/last SCT payer to be non-Unknown (DIAG-05)
**Plans:** 1 plan in 1 wave

Plans:
- [x] 09-01-PLAN.md — Diagnostic script answering 5 insurance questions with console output and structured markdown report
