---
phase: 01-environment-extension-data-staging
plan: 02
subsystem: infra
tags: [hpc, setup, conda, smoke-test]

requires:
  - plan: 01-01
    provides: project scaffold, smoke_test.py, config, SLURM template
provides:
  - scripts/setup_hpc.sh — HPC deployment automation
  - (on HPC after user run) environment.yml with actual polars+duckdb versions
affects: [phase-02-csv-to-parquet]

key-files:
  created:
    - scripts/setup_hpc.sh
  modified: []
  to-create-on-hpc: environment.yml (exported after mamba install)

key-decisions:
  - "setup_hpc.sh uses BLUE_PROJECT=/blue/erin.mobley-hl.bcu/hl-clean; smoke test runs from that dir"
  - "Script is idempotent; ANSI colors for success/failure/warn"
  - "Task 2 is human checkpoint — user must run on HiPerGator to complete verification"

requirements-completed: [REQ-01, REQ-04, REQ-05]
autonomous: false
completed: 2026-02-27
---

# Phase 1 Plan 02: HPC Setup Script Summary

**HPC deployment script automates directory creation, conda env extension (polars+duckdb), smoke test execution, and environment export. Human verification required: user runs script on HiPerGator.**

## Task 1: Create setup_hpc.sh — COMPLETE

`scripts/setup_hpc.sh` exists and passes `bash -n` syntax check. It:

1. Creates project dirs: `/blue/erin.mobley-hl.bcu/hl-clean/{parquet,logs,scripts,config,src/load}`
2. Verifies source data: `/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915` and `DEMOGRAPHIC_Mailhot_V1.csv`
3. Checks /blue quota via `blue_quota` or `lfs quota`
4. Loads conda, activates `hl-eda`, runs `mamba install -y polars duckdb -c conda-forge`
5. Verifies imports: polars, duckdb, pyarrow
6. Prints rsync instructions for copying project files
7. Runs `python scripts/smoke_test.py` if smoke_test.py is present
8. Exports `mamba env export --no-builds > environment.yml`
9. Prints summary and next steps

Script is idempotent and uses ANSI color output.

## Task 2: Human Verification — USER ACTION REQUIRED

**You must run the setup script on HiPerGator to complete this plan.**

### Steps

1. **SSH to HiPerGator**
   ```bash
   ssh your_username@hpg.rc.ufl.edu
   ```

2. **Copy project files to HPC**
   ```bash
   rsync -av --exclude='.planning' --exclude='.git' /path/to/Data\ loading\ and\ cleaing/ hpg:/blue/erin.mobley-hl.bcu/hl-clean/
   ```

3. **Run the setup script**
   ```bash
   cd /blue/erin.mobley-hl.bcu/hl-clean && bash scripts/setup_hpc.sh
   ```

4. **Expected output**
   - Polars, DuckDB, PyArrow version prints
   - Smoke test [OK] for each step
   - BIRTH_DATE dtype=Date
   - Row count preserved
   - Parquet written
   - DuckDB reads Parquet
   - "SMOKE TEST PASSED"
   - environment.yml exported

5. **Copy environment.yml back to local**
   ```bash
   scp hpg:/blue/erin.mobley-hl.bcu/hl-clean/environment.yml .
   ```

### Success criteria

- [ ] polars and duckdb installed in conda env
- [ ] Smoke test passed (DEMOGRAPHIC CSV loaded, SAS dates parsed, Parquet written and verified, DuckDB reads Parquet)
- [ ] environment.yml exported with actual versions

## Verification

- [x] `bash -n scripts/setup_hpc.sh` — syntax valid
- [x] Script contains: `mkdir -p`, `mamba install`, `conda activate`, `smoke_test.py`, `env export`
- [ ] Smoke test output shows [OK] and SMOKE TEST PASSED — **requires HiPerGator run**

## Next steps

After human verification on HiPerGator:
- Update STATE.md: Phase 1 → 2/2 plans complete
- Phase 2: full 22-table CSV-to-Parquet conversion
