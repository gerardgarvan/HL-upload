# Codebase Structure

**Analysis Date:** 2026-03-17

## Directory Layout

```
[project-root]/
├── config/                          # Configuration & reference data
│   └── paths.toml                   # Path declarations (data_root, scratch_root, output dirs)
├── src/                             # Core library modules (reusable functions)
│   ├── load/                        # CSV parsing, Parquet conversion, path config
│   │   ├── __init__.py
│   │   ├── config.py                # Path resolution from TOML
│   │   ├── schema.py                # Manifest parsing, table name aliasing
│   │   └── convert.py               # Date detection, CSV→Parquet, inventory
│   ├── validate/                    # Structural integrity, cohort, value validation
│   │   ├── __init__.py
│   │   ├── structural.py            # Schema comparison, key integrity, completeness, small-cell
│   │   ├── cohort.py                # 149 HL ICD codes, cohort membership, DX_TYPE validation
│   │   └── values.py                # Vital/lab ranges, date bounds, masked values
│   ├── clean/                       # Deduplication, flagging, harmonization
│   │   ├── __init__.py
│   │   ├── dedup.py                 # Composite-key dedup, cross-table consistency checks
│   │   ├── harmonize.py             # Partner flags, enrollment coverage checks
│   │   ├── flags_diagnosis_provider.py  # HL/survivorship/provider flags
│   │   ├── outcomes_flags.py        # Modality code matching, treatment flags
│   │   └── validate/                # Validation helper functions (mirrors src/validate structure)
│   │       ├── __init__.py
│   │       ├── structural.py
│   │       ├── cohort.py
│   │       └── values.py
│   └── report/                      # Quality metrics, patient-level summaries, payer analysis
│       ├── __init__.py
│       ├── quality_report.py        # DQ aggregation, patient-level derived, cleaning decisions
│       ├── encounter_payer_summary.py  # Payer categorization, effective payer, dual-eligible
│       └── site_table.py            # Per-site HL summary tables, outcomes cross-tabs
├── scripts/                         # Entry point scripts (phase executables)
│   ├── convert_all.py               # Phase 1: CSV→Parquet conversion
│   ├── validate_all.py              # Phase 2: Structural validation & cohort verification
│   ├── clean_all.py                 # Phase 3: Deduplication & flagging
│   ├── assemble_clean.py            # Phase 4: Copy to clean dir, derive patient-level, write reports
│   ├── build_insurance_summary.py   # Phase 5: Payer tables and figures
│   ├── build_site_table.py          # Per-site HL summary (adjacent to Phase 4)
│   ├── add_modality_flags.py        # Standalone: add treatment flags to existing Parquet
│   ├── check_insurance_outputs.py   # Validation: verify payer summary outputs
│   ├── pipeline_smoke_test.py       # Integration test: run minimal convert → clean → report
│   ├── smoke_test.py                # Unit test runner for individual modules
│   ├── validate_values.py           # Standalone: deep value validation (ICD, dates, etc.)
│   ├── inspect_tr_stage.py          # Debugging: inspect tumor registry tables
│   ├── setup_hpc.sh                 # HPC environment setup (not Python)
│   └── inspect_variables.R          # R script for outcome variable exploration
├── tests/                           # pytest test suite
│   ├── conftest.py                  # Shared pytest fixtures
│   ├── test_cohort.py               # HL cohort membership, DX_TYPE validation
│   ├── test_structural.py           # Key integrity, small-cell flagging
│   ├── test_flags_diagnosis_provider.py  # Flag logic (HL, survivorship, provider)
│   ├── test_add_modality_flags.py   # Modality code matching
│   ├── test_flag_small_cell.py      # Small-cell threshold and suppression
│   ├── test_suppress.py             # Suppression function (_suppress)
│   └── test_load_outcomes_code_lookup.py  # Outcomes.csv parsing
├── docs/                            # Documentation and reference materials
├── reports/                         # Output reports (Phase 4 & 5 outputs)
│   ├── figures/                     # Generated PNG charts (payer distributions)
│   ├── DATA_QUALITY_REPORT.md       # Phase 4: comprehensive quality metrics
│   ├── CLEANING_DECISIONS.md        # Phase 4: documentation of cleaning choices
│   ├── structural_validation.md     # Phase 2: schema and key validation results
│   ├── insurance_summary.md         # Phase 5: payer category summary tables
│   ├── encounter_payer_summary.csv  # Phase 5: per-variable counts and percentages
│   ├── payer_at_first_dx.csv        # Phase 5: payer at first HL diagnosis
│   ├── payer_at_first_chemo.csv     # Phase 5: payer at first chemotherapy
│   ├── payer_crosstab_*.csv         # Phase 5: payer category transitions
│   └── completeness_by_partner.csv  # Phase 2: per-partner completeness metrics
├── derived/                         # Derived data (input to downstream analysis)
│   ├── patient_level.parquet        # Phase 4: one-row-per-patient with all demographics, flags, outcomes
│   └── encounter_payer_summary.parquet  # Phase 4: payer summary per patient
├── .planning/                       # GSD planning directory (internal)
│   ├── codebase/                    # Codebase analysis docs (this directory)
│   ├── phases/                      # Per-phase implementation plans
│   ├── docs/                        # Project documentation
│   └── milestones/                  # Project milestones
├── Makefile                         # Development targets (lint, test, ci)
├── pyproject.toml                   # Python project config, ruff settings
├── environment.yml                  # Conda environment specification
├── .pre-commit-config.yaml          # Pre-commit hooks (ruff lint + format)
├── .ruff_cache/                     # Ruff linter cache (generated)
├── .pytest_cache/                   # Pytest cache (generated)
├── datastructure.txt                # OneFlorida+ PCORnet CDM manifest (input spec)
├── STAGE_ajcc_column_values2.csv    # AJCC stage reference data (staging validation)
├── valuesets.csv                    # PCORnet value set reference (input data)
├── Outcomes.csv                     # Modality code lookup (input data)
└── _commit_msg.txt                  # Last commit message (internal)
```

## Directory Purposes

**`config/`:**
- Purpose: Configuration and environment declarations
- Contains: `paths.toml` with data_root, scratch_root, parquet_dir, derived_dir locations
- Key files: `config/paths.toml` (required; no default fallback)

**`src/load/`:**
- Purpose: Load layer for configuration and CSV-to-Parquet conversion
- Contains: Path resolution (Paths dataclass), datastructure.txt parsing, date format detection, Parquet write
- Key files: `src/load/config.py` (Paths dataclass, load_config()), `src/load/schema.py` (parse_datastructure), `src/load/convert.py` (convert_table, write_inventory)

**`src/validate/`:**
- Purpose: Data validation layer with no side effects (read-only)
- Contains: Schema validation, referential integrity (PATID/ENCOUNTERID), completeness metrics, cohort membership checks, value validation
- Key files: `src/validate/structural.py` (key checks, small-cell, schema), `src/validate/cohort.py` (149 HL codes, dual format), `src/validate/values.py` (ranges, date bounds)

**`src/clean/`:**
- Purpose: Data cleaning and flagging (adding flag columns, no deletions)
- Contains: Deduplication logic, consistency flags, partner provenance flags, diagnosis/provider flags, modality matching
- Key files: `src/clean/dedup.py` (composite keys, consistency), `src/clean/harmonize.py` (partner/enrollment flags), `src/clean/flags_diagnosis_provider.py` (HL/survivorship/oncology), `src/clean/outcomes_flags.py` (treatment modality)

**`src/report/`:**
- Purpose: Aggregation and summarization for human consumption
- Contains: Patient-level derived variables, quality metrics, payer analysis, small-cell suppression
- Key files: `src/report/quality_report.py` (DQ metrics, patient-level), `src/report/encounter_payer_summary.py` (payer logic), `src/report/site_table.py` (site-level summaries)

**`scripts/`:**
- Purpose: Phase executables (one script per major phase + utilities)
- Contains: Main entry points that orchestrate library calls, config loading, Parquet I/O
- Key files: `scripts/convert_all.py`, `scripts/validate_all.py`, `scripts/clean_all.py`, `scripts/assemble_clean.py`, `scripts/build_insurance_summary.py`

**`tests/`:**
- Purpose: pytest test suite
- Contains: Unit tests for validation logic, flag logic, small-cell suppression
- Coverage: Cohort membership, structural checks, flag logic, modality matching, suppress function

**`docs/`, `reports/`, `derived/`:**
- Purpose: Output and reference artifacts
- Generated: Not version-controlled; written by phases 2-5
- Retention: Kept for review between phases; deleted before re-running pipeline

## Key File Locations

**Entry Points (main scripts):**
- `scripts/convert_all.py`: CSV→Parquet conversion (Phase 1)
- `scripts/validate_all.py`: Structural validation (Phase 2)
- `scripts/clean_all.py`: Deduplication & flagging (Phase 3)
- `scripts/assemble_clean.py`: Assembly & derived (Phase 4)
- `scripts/build_insurance_summary.py`: Payer analysis & figures (Phase 5)

**Configuration:**
- `config/paths.toml`: Path declarations (required; load_config() resolves relative paths against project root)
- `pyproject.toml`: Ruff linter/formatter settings (target-version=py311, line-length=140), pytest discovery
- `environment.yml`: Conda environment spec (Python 3.11, polars, ruff, pytest)

**Core Logic:**
- `src/load/config.py`: Paths dataclass and load_config() function
- `src/load/schema.py`: parse_datastructure() to read manifest, resolve_table_name() for aliases
- `src/load/convert.py`: convert_table() with date detection (3 formats), write_inventory()
- `src/validate/structural.py`: check_patid_integrity(), check_encounterid_integrity(), validate_table_schema(), flag_small_cell()
- `src/validate/cohort.py`: ICD10_HL_CODES, ICD9_HL_CODES (149 codes), verify_hl_cohort() with dual-date methods
- `src/clean/dedup.py`: DEDUP_KEYS (composite per table), flag_duplicates(), check_demographic_consistency()
- `src/clean/harmonize.py`: PARTNER_FLAGS, add_partner_flags(), flag_encounters_outside_enrollment()
- `src/clean/flags_diagnosis_provider.py`: add_diagnosis_flags() (HL + survivorship), add_provider_flags() (oncology)
- `src/clean/outcomes_flags.py`: load_outcomes_code_lookup(), add_modality_flags() (CHEMO, RADIATION, SCT)
- `src/report/quality_report.py`: build_patient_level_derived(), aggregate_dq_metrics(), generate_cleaning_decisions_content()
- `src/report/encounter_payer_summary.py`: build_encounter_payer_summary() with effective payer logic

**Testing:**
- `tests/conftest.py`: Shared pytest fixtures (minimal; most tests use tmp_path)
- `tests/test_cohort.py`: verify_hl_cohort() correctness
- `tests/test_structural.py`: Key integrity and small-cell flagging
- `tests/test_flags_diagnosis_provider.py`: Flag logic for HL, survivorship, provider
- `tests/test_add_modality_flags.py`: Modality code matching

## Naming Conventions

**Files:**
- `{phase_name}_all.py`: Main entry point for phase (convert_all, validate_all, clean_all, assemble_clean)
- `test_{module_name}.py`: Test file for module in src/
- `{lowercase_with_underscores}.py`: All Python files

**Directories:**
- `src/{layer_name}/`: Layer module (load, validate, clean, report)
- `scripts/`: Top-level executables
- `tests/`: Test files
- `reports/`: Report outputs

**Functions:**
- camelCase is NOT used; all snake_case (e.g., load_config, flag_duplicates, check_patid_integrity)
- Leading underscore for internal/helper functions (e.g., _suppress, _get_first_hl_dx_dates)

**Variables & Constants:**
- UPPERCASE for immutable sets/dicts (e.g., DEDUP_KEYS, PARTNER_FLAGS, ICD10_HL_CODES, SMALL_CELL_THRESHOLD)
- snake_case for local and module-level variables
- _infix for internal flag column names (e.g., _con_outside_enrollment, _DX_MATCH)

**Flag Column Names:**
- IS_DUPLICATE: 0/1, exact-match duplicates per composite key
- FLAG_HL_DX: 0/1, matches 149-code HL set
- FLAG_SURVIVORSHIP_DX: 0/1, matches survivorship code list
- FLAG_CANCER_PROVIDER: 0/1, provider has oncology specialty keywords
- ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY: 0/1, partner provenance flags
- _con_*: consistency flags (e.g., _con_outside_enrollment, _con_demo_inconsistent)
- HAD_CHEMO, HAD_RADIATION, HAD_SCT: 0/1, treatment modality indicators
- DUAL_ELIGIBLE: 0/1, payer category indicator

## Where to Add New Code

**New Feature (e.g., add validation rule):**
- Implementation: `src/validate/{domain}.py` (add function, add constant if reusable)
- Tests: `tests/test_{domain}.py` (add test for new function)
- Entry point: Integrate call into `scripts/validate_all.py` or other appropriate phase script
- Example: Add lab value range check to `src/validate/values.py`, test in `tests/test_structural.py` (if structural) or new test file

**New Phase Script:**
- Location: `scripts/{phase_name}.py`
- Pattern: Import config loader, call library functions, write Parquet/CSV/MD outputs
- Structure: main() function with print headers, path setup, orchestration calls
- Example: `scripts/convert_all.py` is template

**New Flag Column:**
- Definition: Add flag name to relevant module constant (e.g., PARTNER_FLAGS, CLEAN_FLAG_COLS)
- Implementation: Add flag-adding function in appropriate module (dedup, clean, report)
- Usage: Call from phase script (clean_all.py or assemble_clean.py)
- Example: HAD_CHEMO added to outcomes_flags.py, called from assemble_clean.py

**Utility Functions (shared helpers):**
- Belong in: `src/load/`, `src/validate/`, `src/clean/`, or `src/report/` depending on domain
- Reuse pattern: Import from library module in scripts and tests
- Example: _suppress() in quality_report.py, imported by build_insurance_summary.py

**New Report Output:**
- Location: Write from `scripts/assemble_clean.py` (Phase 4) or new dedicated script
- Format: Parquet (derived/), CSV (reports/), or Markdown (reports/)
- Small-cell handling: Apply _suppress() to any CSV/MD with counts
- Example: encounter_payer_summary.parquet written by Phase 4, used by Phase 5

## Special Directories

**`.planning/`:**
- Purpose: GSD planning and analysis (internal; not committed to main codebase)
- Generated: By /gsd commands
- Contents: Phase plans, milestones, codebase analysis (ARCHITECTURE.md, STRUCTURE.md, etc.)
- Committed: No (in .gitignore)

**`.ruff_cache/`, `.pytest_cache/`:**
- Purpose: Tool caches
- Generated: By ruff linter and pytest
- Committed: No (in .gitignore)

**`derived/`:**
- Purpose: Derived data for downstream analysis
- Generated: By assemble_clean.py (Phase 4)
- Contents: patient_level.parquet, encounter_payer_summary.parquet
- Retention: Kept between phases as input to build_insurance_summary.py; deleted on full re-run

**`reports/figures/`:**
- Purpose: Generated visualization outputs
- Generated: By build_insurance_summary.py (Phase 5)
- Format: PNG (matplotlib/seaborn)
- Example: insurance_payer_at_first_dx.png (bar chart, small cells 1-10 excluded)

---

*Structure analysis: 2026-03-17*
