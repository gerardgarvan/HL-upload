# Technology Stack

**Analysis Date:** 2026-03-17

## Languages

**Primary:**
- Python 3.11 - All pipeline scripts, data processing, cleaning, and reporting

**Secondary:**
- R - Optional analysis scripts (e.g., `scripts/inspect_variables.R`)
- Shell - Job submission and environment setup (`submit_job.sh`)

## Runtime

**Environment:**
- Python 3.11 (target version specified in `environment.yml` and `pyproject.toml`)

**Package Manager:**
- Conda/Mamba - Primary dependency management via `environment.yml`
- Pip - Secondary package management for packages not in conda-forge

**Lockfile:**
- Not present in repository root (note: `environment.yml` is aspirational; actual resolved versions should be captured via `mamba env export --no-builds`)

## Frameworks

**Core Data Processing:**
- Polars - DataFrame processing for CSV-to-Parquet conversion, data cleaning, and validation
- Pandas >= 2.2 - Fallback for specific operations (e.g., `load_outcomes_code_lookup()` in `src/clean/outcomes_flags.py` uses pd.read_csv)
- PyArrow >= 18.0 - Parquet serialization backend

**Data Analysis/Query:**
- DuckDB - Analytical SQL queries over Parquet files (listed in `environment.yml`)

**Visualization/Reporting:**
- Matplotlib >= 3.9 - Static plotting
- Seaborn >= 0.13 - Statistical visualization
- Jinja2 >= 3.1 - Report template rendering (in `pip:` section)

**Testing:**
- Pytest - Test runner (specified in `environment.yml` pip dependencies)

**Build/Dev:**
- Ruff - Linting and formatting (v0.8.4 in `.pre-commit-config.yaml`)
- Pre-commit - Git hook framework for automated checks
- Jupyter - Interactive notebooks (in `environment.yml`)

## Key Dependencies

**Critical:**
- Polars - Entire data pipeline depends on Polars for efficient columnar processing; used in `src/load/convert.py`, `src/clean/dedup.py`, `src/validate/structural.py`, and most scripts
- PyArrow >= 18.0 - Parquet read/write support (format for all converted data)
- Pandas >= 2.2 - Fallback for CSV parsing with forward-fill semantics (`src/clean/outcomes_flags.py`)

**Infrastructure:**
- Pathlib - Path handling throughout (standard library)
- tomllib/tomli - TOML config parsing in `src/load/config.py` (Python 3.11+ uses built-in tomllib)
- csv - Standard CSV reader for quick scans in `src/load/convert.py`
- re - Regex for code normalization and date detection
- dataclasses - Type hints and data structures in `src/load/config.py`

## Configuration

**Environment:**
- Configuration loaded from `config/paths.toml` via `src/load/config.load_config()`
- Required vars: `data_root`, `scratch_root`, `datastructure_path`, `valuesets_path`
- Optional: `output.parquet_dir`, `output.logs_dir`, `output.derived_dir` (fallback defaults apply)

**Paths Configuration:**
- Config file: `config/paths.toml`
- Data source: HPC orange filesystem at `/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915` (OneFlorida+ PCORnet CDM)
- Scratch/Output: HPC blue filesystem at `/blue/erin.mobley-hl.bcu`
- Parquet output: `{scratch_root}/hpc-upload/parquet` (configurable)
- Derived outputs: `derived/` directory (relative to project root)

**Linting/Formatting:**
- File: `.pre-commit-config.yaml`
- Ruff target: Python 3.11
- Line length: 140 characters (in `pyproject.toml`)
- Ruff rules: E, F, I, W (errors, flakes, imports, warnings)
- Quote style: double quotes
- Per-file ignores: `scripts/*.py` ignores E402 (module-level import not at top)

**Pre-commit Hooks:**
- Ruff check with auto-fix
- Ruff format
- Pytest (runs `python -m pytest tests/ -v`)

## Build/Run Commands

**Local Development:**
```bash
make test              # Run pytest
make lint              # Run ruff check and format check
make lint-fix          # Auto-fix linting issues
make ci                # Run lint + test (CI target)
```

**Data Processing (HPC Interactive):**
```bash
python scripts/convert_all.py [config/paths.toml]    # Phase 1: CSV to Parquet
python scripts/clean_all.py [config/paths.toml]      # Phase 5: Deduplication & harmonization
python scripts/assemble_clean.py [config/paths.toml] # Phase 6: Patient-level assembly
```

## Platform Requirements

**Development:**
- Python 3.11+ with conda/mamba
- Git with pre-commit hooks
- Ruff 0.8.4+
- Pytest

**Production/HPC:**
- HPC environment with Slurm job scheduler
- Access to orange filesystem (read-only source data)
- Access to blue filesystem (scratch/output)
- Conda/mamba with resolved `environment.yml`
- HyperGator (UFL HPC cluster assumed from `datastructure.txt` reference)

**Data Sources:**
- OneFlorida+ PCORnet CDM CSV files (22 tables) from Mailhot cohort
- Valuesets lookup table (valuesets.csv)
- Outcomes codes mapping (Outcomes.csv) for modality detection

---

*Stack analysis: 2026-03-17*
