# Codebase Structure

**Analysis Date:** 2026-03-09

## Directory Layout

```
[project-root]/
├── config/
│   └── paths.toml           # Path configuration (data_root, scratch_root, parquet_dir)
├── scripts/                 # Entry point scripts
│   ├── convert_all.py       # Phase 2: CSV → Parquet
│   ├── validate_all.py      # Phase 3: structural + cohort
│   ├── validate_values.py   # Phase 4: value + temporal validation
│   ├── clean_all.py         # Phase 5: dedup + harmonization
│   ├── assemble_clean.py    # Phase 6 + 7: assemble, derived, modality flags, reports
│   ├── build_site_table.py  # Site-level summary
│   ├── smoke_test.py        # Phase 1 verification
│   └── inspect_tr_stage.py  # Tumor registry inspection
├── src/
│   ├── load/                # Load and convert
│   │   ├── config.py
│   │   ├── convert.py
│   │   └── schema.py
│   ├── validate/            # Validation logic
│   │   ├── structural.py
│   │   ├── values.py
│   │   └── cohort.py
│   ├── clean/               # Cleaning logic
│   │   ├── dedup.py
│   │   ├── harmonize.py
│   │   └── outcomes_flags.py
│   └── report/              # Reporting
│       ├── quality_report.py
│       └── site_table.py
├── reports/                 # Generated reports (Markdown, CSVs)
├── .planning/               # Roadmap, phases, research
├── datastructure.txt        # Table manifest
├── valuesets.csv            # PCORnet value sets
├── Outcomes.xlsx            # Modality code mapping (Phase 7)
├── environment.yml          # Conda env spec
└── submit_job.sh            # SLURM batch script
```

## Directory Purposes

**config/:**
- Purpose: Project configuration
- Contains: `paths.toml`
- Key: `data_root`, `scratch_root`, `parquet_dir`, `valuesets_path`, `datastructure_path`

**scripts/:**
- Purpose: Runnable entry points
- Contains: Phase scripts, smoke test, site table builder
- Pattern: `sys.path.insert(0, PROJECT_ROOT)`; optional config path from `sys.argv[1]`

**src/load/:**
- Purpose: Config loading, schema parsing, CSV→Parquet conversion
- Key files: `config.py`, `convert.py`, `schema.py`

**src/validate/:**
- Purpose: Schema, integrity, completeness, cohort, value sets, temporal, tumor registry
- Key files: `structural.py`, `values.py`, `cohort.py`

**src/clean/:**
- Purpose: Dedup, partner harmonization, consistency, modality flags
- Key files: `dedup.py`, `harmonize.py`, `outcomes_flags.py`

**src/report/:**
- Purpose: DQ aggregation, derived variables, cleaning decisions content
- Key files: `quality_report.py`, `site_table.py`

**reports/:**
- Purpose: Output markdown and CSVs (structural_validation.md, value_validation.md, etc.)

**hpc-upload/:**
- Purpose: HPC-deployable copy (mirrors scripts/src, config, env)
- Contains: `scripts/`, `src/`, `config/`, `environment.yml`, `submit_job.sh`

## Key File Locations

**Entry Points:**
- `scripts/convert_all.py`: Phase 2
- `scripts/validate_all.py`: Phase 3
- `scripts/validate_values.py`: Phase 4
- `scripts/clean_all.py`: Phase 5
- `scripts/assemble_clean.py`: Phases 6 + 7

**Configuration:**
- `config/paths.toml`: Path config
- `datastructure.txt`: Table manifest
- `valuesets.csv`: PCORnet value sets
- `Outcomes.xlsx`: Modality codes (Phase 7)

**Core Logic:**
- `src/load/convert.py`: Date detection, conversion, inventory
- `src/validate/structural.py`: Schema, integrity, completeness, `flag_small_cell`
- `src/validate/cohort.py`: HL cohort verification (149 ICD codes, dual-date methods)
- `src/validate/values.py`: Value set, plausibility, temporal, tumor registry
- `src/clean/dedup.py`: Composite-key duplicate flagging
- `src/clean/outcomes_flags.py`: Modality flags from Outcomes.xlsx

**Testing:**
- `scripts/smoke_test.py`: Manual smoke test (no pytest)

## Naming Conventions

**Files:**
- Scripts: `snake_case.py`
- Modules: `snake_case.py`

**Directories:**
- `src/load`, `src/validate`, `src/clean`, `src/report`

**Constants:**
- UPPER_SNAKE: `PATID_COL`, `SMALL_CELL_THRESHOLD`, `DEDUP_KEYS`

**Flag columns:**
- `_val_*` (validation), `_con_*` (consistency), `MODALITY_*` (modality)

## Where to Add New Code

**New validation check:**
- Implementation: `src/validate/structural.py` or `src/validate/values.py`
- Wire: `scripts/validate_all.py` or `scripts/validate_values.py`

**New modality flag:**
- Update `MODALITY_SLUG_MAP` in `src/clean/outcomes_flags.py`; add row in Outcomes.xlsx
- `add_modality_flags()` already iterates over lookup

**New script:**
- Add to `scripts/`; use `load_config()`, `parse_datastructure()`, `_build_table_map()`

**New report section:**
- Add to `scripts/assemble_clean.py` or `src/report/quality_report.py`

## Special Directories

**hpc-upload/:**
- Purpose: HPC deployment bundle
- Generated: No (maintained)
- Committed: Yes

**reports/:**
- Purpose: Generated reports
- Generated: Yes (by scripts)
- Committed: Yes (per project)

---

*Structure analysis: 2026-03-09*
