# Project Research Summary

**Project:** HL Data Pipeline — Hardening & Documentation
**Domain:** Clinical data pipeline hardening & documentation
**Researched:** 2026-03-17
**Confidence:** HIGH

## Executive Summary

This is a brownfield hardening project: an existing Polars-based clinical data pipeline that works but needs to be trustworthy, understandable, and reproducible. The pipeline processes OneFlorida+ PCORnet CDM data for a Hodgkin Lymphoma cohort through 5 phases (convert, validate, clean, assemble, report).

The recommended approach is documentation-first: understand and document the pipeline before adding validation and tests. This forces a thorough review of every function, surfaces hidden assumptions, and creates the foundation for meaningful tests. The key risk is breaking the working pipeline during hardening — mitigated by creating golden output files before making any changes.

The critical areas to harden are: payer logic (complex fallback chains, untested), date parsing (silent degradation), small-cell suppression (HIPAA compliance, inconsistent application), and phase boundary validation (no row-count checks between phases).

## Key Findings

### Recommended Stack

Keep the existing stack (Python 3.11, Polars, PyArrow, pytest, ruff). Add lightweight hardening tools:

- **Pandera (polars backend):** Schema validation at phase boundaries — lightweight, Polars-native
- **pytest-cov:** Coverage tracking to measure and improve test coverage
- **Sphinx + autodoc2 + myst-parser:** Generate API docs from docstrings (after docstrings are complete)

Avoid Great Expectations (too heavy), Airflow/Prefect (overkill for batch pipeline), and rigid schema validation for all 22 tables (source schema drifts).

### Expected Features

**Must have (table stakes):**
- Docstrings on all public functions (LOW complexity, HIGH value)
- Pipeline overview document (MEDIUM complexity)
- Row-count validation between phases (MEDIUM complexity)
- Test coverage for payer logic and date parsing (HIGH complexity)
- Consistent small-cell suppression (MEDIUM complexity — audit + centralize)
- Setup/reproducibility documentation (MEDIUM complexity)

**Should have (v1.x):**
- Sphinx-generated API docs
- Regression tests (golden file comparison)
- Structured logging

**Defer (v2+):**
- Data lineage tracking
- Incremental processing

### Architecture Approach

Layer hardening on top of the existing architecture without changing it. Add checkpoint validation at phase boundaries (between scripts), docstrings throughout `src/`, expanded tests in `tests/`, and documentation in `docs/`. The build order matters: document first (forces understanding), validate second (catches silent failures), test third (locks in correctness), then make reproducible.

**Major components:**
1. Documentation layer — docstrings in `src/`, pipeline overview in `docs/`
2. Validation layer — phase boundary checkpoints, schema validation
3. Testing layer — expanded `tests/` covering payer, date, report logic
4. Reproducibility layer — setup docs, environment pinning

### Critical Pitfalls

1. **Documenting without understanding** — write "why" not "what"; take time to understand clinical logic before documenting
2. **Tests that pass but don't validate** — require value-level assertions, not just "runs without error"
3. **Breaking the working pipeline** — create golden output files first; never change function signatures during hardening
4. **Inconsistent small-cell suppression** — centralize `_suppress()` to single function; audit all report outputs
5. **Silent date parsing failures** — verify all expected date columns are Date type after conversion; don't rely solely on regex heuristic

## Implications for Roadmap

### Phase 1: Documentation & Baseline
**Rationale:** Must understand the pipeline before changing it. Golden output files protect against regressions.
**Delivers:** Docstrings on all functions, pipeline overview doc, golden output files for regression comparison
**Addresses:** Docstrings, pipeline overview, understanding of logic
**Avoids:** "Documenting without understanding" pitfall

### Phase 2: Validation & Suppression Hardening
**Rationale:** After understanding the pipeline, add checkpoints to catch silent failures. Fix HIPAA compliance issue.
**Delivers:** Phase boundary validation (row counts, schema checks), centralized small-cell suppression, config validation
**Addresses:** Row-count validation, schema validation, suppression audit, config validation
**Avoids:** "Inconsistent suppression" and "silent date parsing" pitfalls

### Phase 3: Test Coverage for Fragile Areas
**Rationale:** Now that logic is documented and validated, lock it in with comprehensive tests.
**Delivers:** Tests for payer logic, date parsing, report generation, phase checkpoints
**Addresses:** All P1 test coverage requirements
**Avoids:** "Tests that don't validate" and "payer edge cases" pitfalls

### Phase 4: Reproducibility & Onboarding
**Rationale:** Pipeline is now trusted — make it reproducible by others.
**Delivers:** Setup documentation, environment pinning, run instructions, Sphinx API docs
**Addresses:** Setup/reproducibility docs, Sphinx generation, collaborator onboarding
**Avoids:** "Setup docs that assume author's environment" pitfall

### Phase 5: Regression & Polish
**Rationale:** Final quality pass — automated regression tests, structured logging, DAG visualization.
**Delivers:** Golden file regression tests, optional structured logging, pipeline DAG diagram
**Addresses:** v1.x features (regression tests, logging, visualization)

### Phase Ordering Rationale

- Documentation first because understanding drives everything else
- Validation before tests because checkpoint failures reveal what to test
- Tests before reproducibility because reproducibility is only valuable if outputs are trusted
- Regression tests last because they need stable, validated outputs to compare against

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Pandera polars backend setup and schema definition patterns
- **Phase 3:** Payer logic decision tree needs careful enumeration of all code combinations

Phases with standard patterns (skip research-phase):
- **Phase 1:** Docstring writing is mechanical; pipeline overview is domain knowledge
- **Phase 4:** Setup docs follow standard patterns
- **Phase 5:** Regression testing is well-documented

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Minimal additions to proven stack |
| Features | HIGH | Based on codebase analysis and clinical data best practices |
| Architecture | HIGH | Layering on existing architecture, not restructuring |
| Pitfalls | HIGH | Derived from actual codebase concerns and clinical data patterns |

**Overall confidence:** HIGH

### Gaps to Address

- Pandera polars backend maturity: verify API stability for Polars lazy frames during Phase 2 planning
- Exact scope of payer logic edge cases: enumerate during Phase 3 planning after documentation reveals full logic

## Sources

- Codebase analysis (`.planning/codebase/` — 7 documents)
- PCORnet CDM documentation standards
- Python packaging and documentation standards (PEP 257, Sphinx)
- HIPAA small-cell suppression guidance
- Pandera documentation (Polars integration)

---
*Research completed: 2026-03-17*
*Ready for roadmap: yes*
