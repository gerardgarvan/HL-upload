# Requirements: HL Data Pipeline — Hardening & Documentation

**Defined:** 2026-03-17
**Core Value:** Data correctness — if the output data is wrong, nothing else matters

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Documentation

- [ ] **DOC-01**: All public functions have Google-style docstrings explaining purpose, args, returns, and clinical rationale
- [ ] **DOC-02**: All modules have module-level docstrings explaining what the module does and how it fits in the pipeline
- [ ] **DOC-03**: Pipeline overview document (docs/PIPELINE.md) covering full data flow from raw CSV to final outputs
- [ ] **DOC-04**: Setup and reproducibility guide (docs/SETUP.md) enabling a collaborator to clone, configure, and run the pipeline

### Validation

- [ ] **VAL-01**: Row-count validation at each phase boundary to detect silent record loss
- [ ] **VAL-02**: Schema validation (expected columns and dtypes) after each phase writes output
- [ ] **VAL-03**: Configuration validation on load — fail fast with clear errors for missing files or bad paths
- [ ] **VAL-04**: Centralized small-cell suppression — single `_suppress()` function, single threshold constant, audit of all report outputs for HIPAA compliance

### Testing

- [ ] **TEST-01**: Comprehensive tests for payer logic (effective payer, dual-eligible detection, fallback chains, sentinel value handling)
- [ ] **TEST-02**: Tests for date parsing (all 3 formats, edge cases: nulls, mixed formats, invalid dates, YYYYMMDD for tumor registry)
- [ ] **TEST-03**: Tests for report generation (output structure, suppression applied correctly, aggregation correctness)
- [ ] **TEST-04**: Tests for phase checkpoint validation (row counts match expectations, schema checks pass)

### Baseline

- [ ] **BASE-01**: Golden output files captured before any changes for regression comparison

## v2 Requirements

Deferred to future milestone. Tracked but not in current roadmap.

### Generated Documentation

- **GDOC-01**: Sphinx-generated API reference from docstrings (requires DOC-01/DOC-02 complete)
- **GDOC-02**: Data dictionary for derived columns, flag definitions, payer categories

### Advanced Quality

- **AQUAL-01**: Automated regression tests comparing current output to golden files
- **AQUAL-02**: Structured logging replacing print-based progress output
- **AQUAL-03**: Pipeline DAG visualization (Mermaid diagram)

### Observability

- **OBS-01**: Data lineage tracking (trace output values to source records)
- **OBS-02**: Incremental processing (only re-process changed data)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Pipeline rewrite / framework change | Existing Polars architecture works; hardening, not rebuilding |
| Great Expectations / heavy validation frameworks | Overkill for a batch research pipeline; Pandera is sufficient |
| Airflow / Prefect orchestration | 5-phase batch pipeline doesn't need a scheduler |
| Real-time monitoring dashboard | Pipeline runs in minutes on HPC; print progress is sufficient |
| Full Pandera schemas for all 22 CDM tables | Source schema drifts with CDM updates; validate critical columns only |
| New data sources or CDM tables | Focus on existing 22 tables |
| Automated data quality scoring | Single DQ score is misleading; keep per-dimension reports |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| BASE-01 | Phase 1 | Pending |
| DOC-01 | Phase 1 | Pending |
| DOC-02 | Phase 1 | Pending |
| DOC-03 | Phase 1 | Pending |
| VAL-01 | Phase 2 | Pending |
| VAL-02 | Phase 2 | Pending |
| VAL-03 | Phase 2 | Pending |
| VAL-04 | Phase 2 | Pending |
| TEST-01 | Phase 3 | Pending |
| TEST-02 | Phase 3 | Pending |
| TEST-03 | Phase 3 | Pending |
| TEST-04 | Phase 3 | Pending |
| DOC-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0

---
*Requirements defined: 2026-03-17*
*Last updated: 2026-03-17 after initial definition*
