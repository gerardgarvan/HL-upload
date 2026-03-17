# Feature Research

**Domain:** Clinical data pipeline hardening & documentation
**Researched:** 2026-03-17
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Pipeline Is Unreliable Without These)

Features that any production-quality data pipeline must have. Missing these means you can't trust the output.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Docstrings on all public functions | Collaborators can't understand intent without them | LOW | Mechanical but high-volume; ~40-60 functions across src/ |
| Module-level docstrings | Each module needs a "what this does and why" header | LOW | Quick wins; one paragraph per module |
| Pipeline overview document | No single doc explains the full data flow end-to-end | MEDIUM | Narrative doc covering CSV → Parquet → reports |
| Row-count validation between phases | Records can silently drop in joins/filters with no detection | MEDIUM | Assert expected counts at phase boundaries |
| Schema validation at phase boundaries | Column additions/removals between phases go unchecked | MEDIUM | Validate dtypes and expected columns after each phase |
| Test coverage for payer logic | Complex fallback chains with no tests; most likely source of errors | HIGH | Payer logic has many edge cases (dual-eligible, sentinel values, missing data) |
| Test coverage for date parsing | 3-format heuristic detection is fragile; failures degrade silently | MEDIUM | Test all 3 formats + edge cases (nulls, mixed formats, invalid dates) |
| Consistent small-cell suppression | Applied inconsistently across scripts; HIPAA compliance risk | MEDIUM | Audit and standardize _suppress() usage in all report outputs |
| Setup/reproducibility docs | No documented way for a collaborator to set up and run the pipeline | MEDIUM | Environment setup, data access, run order, expected outputs |
| Error messages that identify root cause | Current errors are generic or missing; debugging requires reading source | MEDIUM | Specific error messages with file/table/column context |

### Differentiators (Above and Beyond for a Research Pipeline)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Data lineage tracking | Trace any output value back to its source record and transformation | HIGH | Valuable but significant engineering effort |
| Automated regression tests | Run against known-good output to detect unexpected changes | MEDIUM | Compare current output to golden files |
| Pipeline DAG visualization | Visual diagram of phase dependencies and data flow | LOW | Could be a simple Mermaid diagram in docs |
| Incremental processing | Only re-process changed data instead of full re-run | HIGH | Not needed unless data size becomes a problem |
| Structured logging | Replace print statements with proper logging (levels, timestamps) | MEDIUM | Nice for debugging but not blocking |
| Configuration validation | Validate paths.toml on load instead of failing mid-pipeline | LOW | Quick win; check file existence, required keys |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full Pandera schemas for all 22 tables | "Validate everything" | Schema drift in source data is expected; rigid schemas break on CDM updates | Validate critical columns only; log unexpected columns as warnings |
| Real-time monitoring dashboard | "See pipeline progress" | Pipeline runs in minutes on HPC; monitoring adds infra complexity for no gain | Print-based progress (already exists) is sufficient |
| Automated data quality scoring | "Single number for data quality" | Reduces nuanced DQ issues to misleading score | Keep existing per-dimension DQ reports; they're more informative |
| Full CDC/incremental loads | "Don't reprocess everything" | Source data is a one-time extract; no incremental updates expected | Full reprocess is fine for this use case |

## Feature Dependencies

```
[Docstrings]
    └──enables──> [Sphinx API docs generation]

[Row-count validation]
    └──requires──> [Schema validation framework]
                       └──requires──> [Pandera setup]

[Test coverage for payer logic]
    └──requires──> [Understanding of payer logic] (read + document first)

[Setup/reproducibility docs]
    └──requires──> [Pipeline overview document]
    └──requires──> [Docstrings] (to reference function behavior)

[Consistent small-cell suppression]
    └──independent (audit + fix)
```

### Dependency Notes

- **Sphinx docs require docstrings:** Must add docstrings before generating API docs
- **Tests require understanding:** Document payer/date logic before writing tests (forces clarity)
- **Setup docs require overview:** Can't explain setup without the pipeline overview

## MVP Definition

### v1 — This Milestone

Minimum to achieve "trusted, reproducible pipeline."

- [ ] Docstrings on all public functions and modules — enables understanding
- [ ] Pipeline overview document — the missing "how it all works" doc
- [ ] Row-count and schema validation at phase boundaries — catch silent failures
- [ ] Test coverage for payer logic, date parsing, report generation — cover fragile areas
- [ ] Consistent small-cell suppression audit — HIPAA compliance
- [ ] Setup and reproducibility documentation — collaborators can run it
- [ ] Configuration validation on load — fail fast with clear errors

### Add After Validation (v1.x)

- [ ] Sphinx-generated API docs — once docstrings are complete
- [ ] Automated regression tests (golden file comparison) — once outputs are trusted
- [ ] Structured logging — after core hardening is done
- [ ] Pipeline DAG visualization — after architecture is documented

### Future Consideration (v2+)

- [ ] Data lineage tracking — if provenance questions become frequent
- [ ] Incremental processing — only if data size grows significantly

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Docstrings | HIGH | LOW | P1 |
| Pipeline overview doc | HIGH | MEDIUM | P1 |
| Row-count validation | HIGH | MEDIUM | P1 |
| Payer logic tests | HIGH | HIGH | P1 |
| Small-cell suppression audit | HIGH | MEDIUM | P1 |
| Setup/reproducibility docs | HIGH | MEDIUM | P1 |
| Date parsing tests | MEDIUM | MEDIUM | P1 |
| Config validation | MEDIUM | LOW | P1 |
| Report generation tests | MEDIUM | MEDIUM | P2 |
| Sphinx API docs | MEDIUM | LOW | P2 |
| Regression tests | MEDIUM | MEDIUM | P2 |
| Structured logging | LOW | MEDIUM | P3 |
| DAG visualization | LOW | LOW | P3 |

## Sources

- PCORnet CDM documentation practices
- Clinical data pipeline best practices (FDA, NIH data management guidance)
- Python packaging and documentation standards (PEP 257, Sphinx)

---
*Feature research for: clinical data pipeline hardening*
*Researched: 2026-03-17*
