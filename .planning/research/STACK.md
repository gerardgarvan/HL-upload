# Stack Research

**Domain:** Clinical data pipeline hardening & documentation
**Researched:** 2026-03-17
**Confidence:** HIGH

## Recommended Stack

### Core Technologies (Already In Place)

| Technology | Version | Purpose | Status |
|------------|---------|---------|--------|
| Python | 3.11 | Pipeline language | Keep |
| Polars | latest | DataFrame processing | Keep |
| PyArrow | >= 18.0 | Parquet I/O | Keep |
| pytest | latest | Test runner | Keep — expand coverage |
| ruff | 0.8.4+ | Lint + format | Keep |

### Supporting Libraries (Add for Hardening)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Pandera (polars backend) | >= 0.20 | Schema validation for DataFrames | Validate DataFrame shapes, dtypes, and value constraints at phase boundaries |
| pytest-cov | >= 5.0 | Coverage reporting | Measure and track test coverage during hardening |
| Sphinx | >= 7.0 | Documentation generation | Generate API docs from docstrings |
| sphinx-autodoc2 | >= 0.5 | Auto-extract docstrings | Automatically build docs from Python modules |
| myst-parser | >= 3.0 | Markdown in Sphinx | Write docs in Markdown instead of RST |
| furo | latest | Sphinx theme | Clean, modern doc theme |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest --cov | Coverage tracking | Add to Makefile `make test-cov` target |
| sphinx-build | Doc generation | Add to Makefile `make docs` target |
| pre-commit (existing) | Git hooks | Already configured; add coverage check |

## Installation

```bash
# Add to environment.yml pip section
pip:
  - pandera[polars]>=0.20
  - pytest-cov>=5.0
  - sphinx>=7.0
  - sphinx-autodoc2>=0.5
  - myst-parser>=3.0
  - furo
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Pandera | Great Expectations | GX is heavier, designed for data platforms with scheduling; overkill for a batch pipeline |
| Pandera | Custom assertions | Already have some custom validation; Pandera adds schema declaration on top |
| Sphinx | MkDocs | MkDocs is simpler but Sphinx has better autodoc for Python API reference |
| Sphinx | pdoc | pdoc is zero-config but less flexible for mixing API docs + narrative docs |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Great Expectations | Heavy orchestration layer, complex setup, designed for data platforms not research pipelines | Pandera — lightweight, Polars-native |
| dbt | SQL-centric transformation tool; this pipeline is Python/Polars | Keep current Python scripts |
| Airflow/Prefect | Workflow orchestrators; overkill for a 5-phase batch pipeline run manually on HPC | Keep current sequential script execution |
| pandas for new code | Polars is already the standard; mixing increases complexity | Polars for all new code; keep pandas only in outcomes_flags.py |

## Stack Patterns

**For validation:**
- Use Pandera DataFrameSchema at phase boundaries (after each script writes Parquet)
- Keep existing custom validation (cohort, structural) — Pandera complements, doesn't replace
- Add row-count assertions between phases (no silent record loss)

**For documentation:**
- Sphinx for generated API docs (from docstrings)
- Handwritten pipeline overview in `docs/PIPELINE.md` (not generated)
- Keep existing reports as-is (they document data quality, not code)

**For testing:**
- pytest with coverage tracking
- Property-based testing (hypothesis) is overkill for this domain — stick with example-based tests
- Focus coverage on: payer logic, date parsing, join logic, report generation

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| Pandera >= 0.20 | Polars >= 0.20 | Polars backend added in Pandera 0.18; 0.20+ has stable API |
| Sphinx >= 7.0 | Python 3.11 | Fully supported |
| pytest-cov >= 5.0 | pytest >= 7.0 | Standard combination |

## Sources

- Pandera documentation — Polars integration guide
- Sphinx documentation — Python autodoc setup
- Community consensus on data pipeline validation patterns

---
*Stack research for: clinical data pipeline hardening*
*Researched: 2026-03-17*
