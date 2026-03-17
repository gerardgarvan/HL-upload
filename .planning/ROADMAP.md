# Roadmap: HL Data Pipeline — Hardening & Documentation

## Overview

This roadmap transforms an existing, functional clinical data pipeline into a trustworthy, reproducible system. We start by understanding and documenting what exists (Phase 1), add validation checkpoints to catch silent failures (Phase 2), lock in correctness with comprehensive tests (Phase 3), and finally make it reproducible for collaborators (Phase 4). The approach is documentation-first: understand before changing, validate before testing, test before publishing.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (e.g., 2.1): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Documentation & Baseline** - Understand and document the pipeline; capture golden outputs for regression protection (completed 2026-03-17)
- [ ] **Phase 2: Validation & Suppression Hardening** - Add checkpoints at phase boundaries; centralize HIPAA-compliant small-cell suppression
- [ ] **Phase 3: Test Coverage for Fragile Areas** - Lock in correctness with comprehensive tests for payer logic, date parsing, and reports
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
**Plans**: TBD

Plans:
- [ ] TBD during planning

### Phase 3: Test Coverage for Fragile Areas
**Goal**: Correctness of complex, fragile logic is locked in with comprehensive test coverage
**Depends on**: Phase 2
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. Tests cover payer logic including effective payer derivation, dual-eligible detection, fallback chains, and sentinel value handling with edge cases enumerated
  2. Tests cover date parsing for all 3 formats (MM/DD/YYYY, YYYY-MM-DD, YYYYMMDD) including edge cases for nulls, mixed formats, invalid dates, and tumor registry format
  3. Tests cover report generation including output structure verification, suppression applied correctly, and aggregation correctness
  4. Tests cover phase checkpoint validation including row-count matching and schema validation passing for expected inputs
**Plans**: TBD

Plans:
- [ ] TBD during planning

### Phase 4: Reproducibility & Onboarding
**Goal**: A collaborator can clone the repo, follow setup documentation, and reproduce pipeline outputs
**Depends on**: Phase 3
**Requirements**: DOC-04
**Success Criteria** (what must be TRUE):
  1. `docs/SETUP.md` exists with step-by-step instructions covering environment setup (conda/mamba), configuration file setup, file path mapping (orange/blue filesystems), and execution of the full pipeline
  2. A collaborator with HyperGator access can follow the setup guide and successfully run the pipeline from raw CSVs to final outputs without needing to ask the author questions
**Plans**: TBD

Plans:
- [ ] TBD during planning

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Documentation & Baseline | 0/5 | Complete    | 2026-03-17 |
| 2. Validation & Suppression Hardening | 0/TBD | Not started | - |
| 3. Test Coverage for Fragile Areas | 0/TBD | Not started | - |
| 4. Reproducibility & Onboarding | 0/TBD | Not started | - |
