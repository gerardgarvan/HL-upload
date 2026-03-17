# Architecture Research

**Domain:** Clinical data pipeline hardening & documentation
**Researched:** 2026-03-17
**Confidence:** HIGH

## Standard Architecture

### Current System (Kept As-Is)

```
┌─────────────────────────────────────────────────────────────┐
│                    Entry Points (scripts/)                    │
│  convert_all → validate_all → clean_all → assemble → reports │
├─────────────────────────────────────────────────────────────┤
│                    Library Layers (src/)                      │
│  ┌──────────┐  ┌────────────┐  ┌─────────┐  ┌──────────┐   │
│  │  load/   │  │  validate/ │  │  clean/ │  │  report/ │   │
│  └──────────┘  └────────────┘  └─────────┘  └──────────┘   │
├─────────────────────────────────────────────────────────────┤
│                    Data (Parquet files)                       │
│  raw/ → parquet/ → flagged/ → parquet_clean/ → derived/      │
└─────────────────────────────────────────────────────────────┘
```

### Where Hardening Layers Fit

```
┌─────────────────────────────────────────────────────────────┐
│                    Entry Points (scripts/)                    │
│  convert_all → validate_all → clean_all → assemble → reports │
│       ↓              ↓            ↓           ↓        ↓     │
│  [CHECKPOINT]   [CHECKPOINT]  [CHECKPOINT] [CHECKPOINT]      │  ← NEW: validation gates
├─────────────────────────────────────────────────────────────┤
│                    Library Layers (src/)                      │
│  ┌──────────┐  ┌────────────┐  ┌─────────┐  ┌──────────┐   │
│  │  load/   │  │  validate/ │  │  clean/ │  │  report/ │   │
│  │ +docstr  │  │ +docstr    │  │ +docstr │  │ +docstr  │   │  ← NEW: docstrings
│  └──────────┘  └────────────┘  └─────────┘  └──────────┘   │
├─────────────────────────────────────────────────────────────┤
│                    Tests (tests/)                             │
│  existing tests + payer tests + date tests + report tests    │  ← NEW: expanded coverage
├─────────────────────────────────────────────────────────────┤
│                    Docs (docs/)                               │
│  PIPELINE.md + API reference (Sphinx) + SETUP.md             │  ← NEW: documentation
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Hardening Action |
|-----------|----------------|------------------|
| `scripts/` | Phase orchestration | Add checkpoint validation after each phase writes output |
| `src/load/` | Config + conversion | Docstrings, config validation, better error messages |
| `src/validate/` | Data integrity | Docstrings, expand validation rules, Pandera schemas |
| `src/clean/` | Dedup + flagging | Docstrings, test payer and date logic |
| `src/report/` | Summaries + reports | Docstrings, test report generation, audit suppression |
| `tests/` | Correctness verification | Expand to cover payer, date, report, join edge cases |
| `docs/` | Human-readable docs | Pipeline overview, setup guide, API reference |

## Where Documentation Belongs

### Inline Documentation (Docstrings)

**Where:** Every public function and every module in `src/`

**Pattern:** Google-style docstrings (matches ruff D-series rules)

```python
def build_encounter_payer_summary(encounters: pl.LazyFrame, enrollment: pl.LazyFrame) -> pl.DataFrame:
    """Build one-row-per-patient payer summary from encounter and enrollment data.

    Applies effective payer logic: uses PAYER_TYPE_PRIMARY, falls back to
    PAYER_TYPE_SECONDARY if primary is missing or sentinel (NI/UN/OT).
    Detects dual-eligible status from codes 14/141/142.

    Args:
        encounters: Lazy frame with PATID, ENCOUNTERID, PAYER_TYPE_PRIMARY,
            PAYER_TYPE_SECONDARY columns.
        enrollment: Lazy frame with PATID, ENR_START_DATE, ENR_END_DATE,
            PAYER_TYPE_PRIMARY columns.

    Returns:
        DataFrame with one row per PATID containing payer category, dual-eligible
        flag, payer at treatment windows, and transition indicators.
    """
```

**Module-level pattern:**
```python
"""Encounter-level payer summary and effective payer logic.

Collapses PCORnet PAYER_TYPE_PRIMARY/SECONDARY codes into readable categories
(Medicare, Medicaid, Private, Dual, Other, Unknown). Handles sentinel values
(NI, UN, OT) and detects dual-eligible patients.

Used by: scripts/assemble_clean.py (Phase 4)
Produces: derived/encounter_payer_summary.parquet
"""
```

### External Documentation (docs/)

**Where:** `docs/` directory, handwritten

1. `docs/PIPELINE.md` — Full pipeline overview (phases, data flow, what each script does)
2. `docs/SETUP.md` — Environment setup, data access, how to run the pipeline
3. `docs/DATA_DICTIONARY.md` — Derived columns, flag definitions, payer categories (optional, v1.x)

### Generated Documentation (Sphinx)

**Where:** `docs/api/` — auto-generated from docstrings

**When:** After docstrings are complete (Phase 2+)

**Setup:** Sphinx with autodoc2, myst-parser, furo theme

## Where Validation Checks Should Go

### Phase Boundary Checkpoints

Insert validation after each phase script writes its output:

```
convert_all.py writes parquet/
  └── CHECKPOINT: row counts match CSV, all date columns converted, no empty tables

validate_all.py writes reports/
  └── CHECKPOINT: all 22 tables validated, cohort size in expected range

clean_all.py writes flagged parquet/
  └── CHECKPOINT: row counts unchanged (dedup adds flags, doesn't delete), all flag columns present

assemble_clean.py writes derived/
  └── CHECKPOINT: patient_level.parquet has expected columns, row count = unique PATID count

build_insurance_summary.py writes reports/
  └── CHECKPOINT: all CSVs non-empty, suppression applied, no raw counts < 11 in outputs
```

### Implementation Pattern

```python
def validate_phase_output(phase_name: str, checks: list[tuple[str, bool]]) -> None:
    """Run checkpoint validation after a phase completes.

    Args:
        phase_name: Name of the phase (for error messages).
        checks: List of (description, passed) tuples.

    Raises:
        ValueError: If any check fails, with details of all failures.
    """
    failures = [(desc, passed) for desc, passed in checks if not passed]
    if failures:
        msg = f"Phase '{phase_name}' checkpoint failed:\n"
        for desc, _ in failures:
            msg += f"  - {desc}\n"
        raise ValueError(msg)
```

## Where New Tests Should Go

### Test Structure

```
tests/
├── conftest.py                      # Shared fixtures (expand with common test data)
├── test_cohort.py                   # HL cohort membership [EXISTS]
├── test_structural.py               # Key integrity, small-cell [EXISTS]
├── test_flags_diagnosis_provider.py # Flag logic [EXISTS]
├── test_add_modality_flags.py       # Modality matching [EXISTS]
├── test_flag_small_cell.py          # Small-cell threshold [EXISTS]
├── test_suppress.py                 # Suppression function [EXISTS]
├── test_load_outcomes_code_lookup.py # Outcomes parsing [EXISTS]
├── test_payer_logic.py              # NEW: effective payer, dual-eligible, fallbacks
├── test_date_parsing.py             # NEW: 3-format detection, edge cases
├── test_report_generation.py        # NEW: report output structure, suppression
├── test_phase_checkpoints.py        # NEW: row-count and schema validation
└── test_config_validation.py        # NEW: config loading, missing keys, bad paths
```

### Test Patterns to Follow

**Existing pattern (keep):**
- Small, focused test functions
- Polars DataFrame fixtures created inline
- Assert specific values, not just "no error"

**New pattern (add for payer/date):**
- Parameterized tests for edge cases (`@pytest.mark.parametrize`)
- Test each payer fallback path independently
- Test date format detection with known-good and known-bad inputs

## Suggested Build Order

1. **Docstrings + pipeline overview** — understand before changing; forces review of every function
2. **Phase checkpoint validation** — catch silent failures immediately
3. **Test coverage for fragile areas** — payer logic, date parsing, report generation
4. **Small-cell suppression audit** — HIPAA compliance fix
5. **Setup/reproducibility docs** — collaborator onboarding
6. **Sphinx API docs** — generate from completed docstrings

**Rationale:** Documentation first forces understanding. Understanding reveals problems. Tests lock in correctness. Then make it reproducible.

## Anti-Patterns

### Anti-Pattern 1: Testing Implementation Instead of Behavior

**What people do:** Test internal helper functions and implementation details
**Why it's wrong:** Tests break when you refactor, even if behavior is unchanged
**Do this instead:** Test public API behavior — "given this input DataFrame, expect this output"

### Anti-Pattern 2: Documenting What the Code Does Instead of Why

**What people do:** `# Filter rows where IS_DUPLICATE == 1`
**Why it's wrong:** Anyone can read the code; they can't read your reasoning
**Do this instead:** `# Exclude exact duplicates (same ID + date + code) to avoid double-counting in reports`

### Anti-Pattern 3: Validating Everything With Equal Priority

**What people do:** Add validation for every column in every table
**Why it's wrong:** Noisy validation masks real issues; clinical data has expected variability
**Do this instead:** Validate critical columns (IDs, dates, codes) strictly; validate others loosely or not at all

## Sources

- Python documentation standards (PEP 257, Google style guide)
- Pandera documentation (Polars integration)
- Clinical data pipeline patterns (PCORnet CDM documentation)
- Sphinx autodoc2 documentation

---
*Architecture research for: clinical data pipeline hardening*
*Researched: 2026-03-17*
