---
phase: 01-environment-extension-data-staging
plan: 01
subsystem: infra
tags: [toml, polars, duckdb, parquet, slurm, conda, hpc]

requires:
  - phase: none
    provides: first plan — no prior dependencies
provides:
  - config/paths.toml with data_root, scratch_root, parquet_dir
  - src/load/config.py Paths dataclass loader with parquet_dir extension
  - src/load/schema.py datastructure.txt parser (22 table filenames)
  - datastructure.txt and valuesets.csv shared assets
  - environment.yml draft spec with polars and duckdb
  - submit_job.sh SLURM template for HiPerGator
  - scripts/smoke_test.py end-to-end CSV→Parquet validation
affects: [01-02-PLAN, phase-02-csv-to-parquet]

tech-stack:
  added: [polars, duckdb]
  patterns: [config-driven-paths, toml-config-loader, datastructure-manifest-parsing]

key-files:
  created:
    - config/paths.toml
    - src/__init__.py
    - src/load/__init__.py
    - src/load/config.py
    - src/load/schema.py
    - environment.yml
    - submit_job.sh
    - scripts/smoke_test.py
  modified: []

key-decisions:
  - "Extended Paths dataclass with parquet_dir field; output section optional with sensible default"
  - "Copied schema.py directly from HL-EDA without modification — parse_datastructure works as-is"
  - "SLURM template uses 4 CPUs (up from 2) for Polars auto-parallelization"
  - "environment.yml is a draft spec; real export generated on HPC after mamba install"

patterns-established:
  - "Config-driven paths: all HPC paths from config/paths.toml, never hardcoded"
  - "Project root detection: _project_root() via Path(__file__).resolve().parents[2]"
  - "Smoke test pattern: load config → parse manifest → read CSV → transform → write Parquet → verify round-trip → DuckDB cross-check"

requirements-completed: [REQ-04, REQ-05]

duration: 8min
completed: 2026-02-27
---

# Phase 1 Plan 01: Project Scaffold Summary

**TOML config with Paths dataclass (parquet_dir extension), schema parser for 22 CSV manifest, conda env spec adding Polars+DuckDB, SLURM template (4 CPUs, 64GB), and 9-step smoke test script**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-02-27T14:47:39Z
- **Completed:** 2026-02-27T14:55:00Z
- **Tasks:** 2
- **Files created:** 10

## Accomplishments
- Complete project scaffold with config, source modules, and shared HL-EDA assets
- Config loader extends HL-EDA's Paths dataclass with parquet_dir for Parquet output directory
- Schema parser correctly extracts 22 table filenames from datastructure.txt
- Smoke test implements full 9-step pipeline: config→manifest→CSV→date-parse→Parquet→verify→DuckDB
- SLURM template configured for HiPerGator with erin.mobley-hl.bcu account, 64GB, 4 CPUs
- Environment spec adds polars and duckdb to existing hl-eda conda packages

## Task Commits

Each task was committed atomically:

1. **Task 1: Create project config and source modules** - `54e2cb9` (feat)
2. **Task 2: Add environment spec, SLURM template, and smoke test** - `c22f90a` (feat)

## Files Created/Modified
- `config/paths.toml` — HPC path configuration with [paths.output] section for parquet_dir and logs_dir
- `src/__init__.py` — Package marker
- `src/load/__init__.py` — Package marker
- `src/load/config.py` — TOML config loader returning Paths dataclass with parquet_dir
- `src/load/schema.py` — datastructure.txt parser and file verifier (copied from HL-EDA)
- `datastructure.txt` — 22 CSV table filename manifest (copied from HL-EDA)
- `valuesets.csv` — 15,193-row PCORnet code-to-label mappings (copied from HL-EDA)
- `environment.yml` — Draft conda env spec: hl-eda base + polars + duckdb
- `submit_job.sh` — SLURM batch template: hl-clean job, 64GB, 4 CPUs, 2hr wall time
- `scripts/smoke_test.py` — 9-step end-to-end validation: CSV→SAS date parse→Parquet→DuckDB verify

## Decisions Made
- Extended Paths dataclass with `parquet_dir` field; `[paths.output]` section is optional with default `scratch_root / hl-clean / parquet`
- Copied `schema.py` verbatim from HL-EDA — `parse_datastructure()` and `verify_files_exist()` work without modification
- Bumped SLURM `--cpus-per-task` from 2 to 4 for Polars auto-parallelization
- Environment spec is a draft — actual pinned versions will be captured on HPC via `mamba env export --no-builds`

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. HPC deployment is handled by Plan 02.

## Next Phase Readiness
- All local artifacts ready for HPC deployment (Plan 02)
- Plan 02 will: push files to /blue, install polars+duckdb in conda env, run smoke_test.py on HPC
- Config, source modules, and scripts are self-contained and tested locally

---
*Phase: 01-environment-extension-data-staging*
*Completed: 2026-02-27*
