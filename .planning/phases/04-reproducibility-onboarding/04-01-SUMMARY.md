---
phase: 04-reproducibility-onboarding
plan: 01
subsystem: infrastructure
tags: [reproducibility, documentation, environment, verification, onboarding]

dependency_graph:
  requires: []
  provides:
    - production-ready environment.yml
    - automated setup verification
  affects:
    - docs/SETUP.md (Plan 02 will reference these artifacts)

tech_stack:
  added:
    - conda environment specification (production-ready)
    - bash verification script
  patterns:
    - two-file environment pattern (human-editable spec + lock file)
    - automated pre-flight checks via bash script

key_files:
  created:
    - scripts/verify_setup.sh (109 lines, 6 verification checks)
  modified:
    - environment.yml (finalized from DRAFT to production-ready)

decisions:
  - "Two-file environment pattern: keep environment.yml human-editable with loose pins, generate lock file on-demand"
  - "Comprehensive verification: 6 automated checks covering conda env, Python version, imports, config, compute node, and data access"
  - "Preserve setup_hpc.sh: serves different purpose (initial installation) vs verify_setup.sh (post-setup verification)"

metrics:
  duration: 83 seconds
  tasks_completed: 2
  files_modified: 2
  commits: 2
  completed_at: 2026-03-18T15:44:23Z
---

# Phase 04 Plan 01: Environment Setup Infrastructure Summary

**One-liner:** Production-ready conda environment spec with automated 6-check verification script for collaborator onboarding

## Objective

Finalize the environment specification and create a setup verification script that collaborators can run to confirm their HyperGator environment is correctly configured before running the pipeline.

## What Was Built

### 1. Production-Ready environment.yml

Converted the DRAFT environment.yml to a clean, production-ready conda environment specification:

**Changes:**
- Removed DRAFT marker and installation instructions
- Added clear header explaining this is the pipeline environment spec
- Added lock file generation comment for exact reproduction
- Removed commented pandera/pydantic optional dependencies block (Phase 2 decision confirmed these are not needed)
- Kept all working dependencies unchanged: python=3.11, pandas>=2.2, pyarrow>=18.0, polars, duckdb, jupyter, matplotlib>=3.9, seaborn>=0.13, pip section with jinja2, tabulate, pytest, ruff, pre-commit
- Kept hl-eda environment name (used by all existing scripts)

**File:** environment.yml (32 lines, clean and ready for collaborator use)

**Commit:** f9e33fa

### 2. Automated Setup Verification Script

Created scripts/verify_setup.sh - a bash script collaborators run after completing environment setup to verify everything is configured correctly before attempting the pipeline.

**6 Verification Checks:**

1. **Conda environment** - Verifies hl-eda environment is activated, exits with clear error if not
2. **Python version** - Checks Python 3.11-3.14, exits on unexpected version
3. **Core dependencies** - Tests import of polars, pandas, pyarrow, pytest, jinja2, tabulate
4. **Config validation** - Runs load_and_validate_config() to verify config/paths.toml paths
5. **Compute node status** - Warns if on login node, provides srun command for compute node access
6. **Source data accessibility** - Checks if data_root directory exists, warns gracefully if not (expected on login node)

**Features:**
- Color-coded output (green=OK, red=FAIL, yellow=WARN)
- Clear pass/fail/warn messages for each check
- Exit codes: 0 on success, 1 on critical failure
- Graceful handling of expected failures (e.g., data not accessible on login node)
- Summary line showing N/N checks passed

**File:** scripts/verify_setup.sh (109 lines, executable)

**Commit:** b214ae8

## Deviations from Plan

None - plan executed exactly as written. No bugs found, no missing functionality, no blocking issues.

## Verification Results

### Task 1: environment.yml Verification
- No "DRAFT" marker present
- All original dependencies preserved (python=3.11, pandas>=2.2, pyarrow>=18.0, polars, duckdb, jupyter, matplotlib>=3.9, seaborn>=0.13, pip section with jinja2, tabulate, pytest, ruff, pre-commit)
- Pandera/pydantic commented block removed
- Lock file generation comment present
- Name is hl-eda

**Status:** PASS

### Task 2: verify_setup.sh Verification
1. Read scripts/verify_setup.sh - all 6 checks present
2. Bash syntax check (`bash -n`) - PASS (no errors)
3. scripts/setup_hpc.sh still exists unchanged - CONFIRMED

**Status:** PASS

### Overall Verification
1. environment.yml is clean and production-ready - PASS
2. scripts/verify_setup.sh exists with all 6 checks and passes syntax validation - PASS
3. scripts/setup_hpc.sh is preserved (not modified) - PASS
4. Both files are internally consistent (verify_setup.sh references hl-eda env name matching environment.yml) - PASS

**Status:** ALL CHECKS PASSED

## Key Decisions

### 1. Two-File Environment Pattern

**Decision:** Keep environment.yml as human-editable specification with loose version pins (e.g., `pandas>=2.2`, `polars` without version). Generate lock file on-demand with `conda env export --no-builds > environment_lock.yml`.

**Rationale:** Research in 04-RESEARCH.md identified this as the two-file pattern used by successful HPC data science projects. The human-editable spec is easier to maintain and update (bump minimum versions, add new packages). The lock file provides exact reproduction when needed (e.g., for published results, debugging environment-specific issues).

**Impact:** Collaborators use environment.yml for initial setup, can generate lock file after successful installation if exact version reproduction is needed.

### 2. Comprehensive Verification Strategy

**Decision:** Implement 6 distinct verification checks covering the full setup chain: environment activation, Python version, dependency imports, config file validation, compute node status, and data access.

**Rationale:** Each check catches a different class of setup failure. Conda env check catches "forgot to activate". Python version catches "activated wrong env". Import check catches "dependencies not installed". Config check catches "paths.toml has wrong paths". Compute node check prevents "ran pipeline on login node and got killed". Data access check catches "data path not mounted on this node".

**Impact:** Collaborators get immediate, actionable feedback on what's wrong with their setup before attempting the pipeline. Reduces "works on my machine" debugging cycles.

### 3. Preserve setup_hpc.sh

**Decision:** Do not modify or remove scripts/setup_hpc.sh. Create verify_setup.sh as a separate script.

**Rationale:** setup_hpc.sh serves a different purpose (initial HPC installation with conda install, directory creation, smoke test). verify_setup.sh is for post-setup verification (assumes environment already exists). Both scripts are needed for the full onboarding workflow.

**Impact:** Collaborators have two distinct scripts: setup_hpc.sh for first-time setup, verify_setup.sh for validation after following SETUP.md.

## Dependencies and Integration

### Upstream Dependencies
- None (this is foundation infrastructure)

### Downstream Dependents
- **docs/SETUP.md (Plan 02):** Will reference environment.yml for environment creation step and verify_setup.sh as the verification step
- **Future collaborators:** Will use these artifacts as their primary onboarding tools

### Integration Points

**environment.yml → verify_setup.sh:**
- verify_setup.sh checks for $CONDA_DEFAULT_ENV == "hl-eda" (matches environment.yml name)
- verify_setup.sh imports all packages listed in environment.yml dependencies

**verify_setup.sh → src/load/config.py:**
- Check 4 runs `from src.load.config import load_and_validate_config; load_and_validate_config()`
- Check 6 runs `from src.load.config import load_config; p = load_config(); print(p.data_root)`
- Verifies the config module and paths.toml are correctly set up

## Next Steps

**Immediate (Plan 02 - docs/SETUP.md):**
- Reference environment.yml in "Environment Setup" section
- Reference verify_setup.sh as final validation step
- Document the two-file pattern (spec vs lock file)

**Future Enhancements (if needed):**
- Add verify_setup.sh check for Git LFS (if pipeline starts using LFS for large files)
- Add check for Slurm job scheduler availability
- Add check for sufficient /blue storage quota

## Self-Check

Verifying all claimed artifacts exist and commits are recorded.

### Files Created/Modified

```bash
[ -f "C:/cygwin64/home/Owner/Data loading and cleaing/environment.yml" ] && echo "FOUND: environment.yml" || echo "MISSING: environment.yml"
```
FOUND: environment.yml

```bash
[ -f "C:/cygwin64/home/Owner/Data loading and cleaing/scripts/verify_setup.sh" ] && echo "FOUND: verify_setup.sh" || echo "MISSING: verify_setup.sh"
```
FOUND: verify_setup.sh

```bash
[ -x "C:/cygwin64/home/Owner/Data loading and cleaing/scripts/verify_setup.sh" ] && echo "EXECUTABLE: verify_setup.sh" || echo "NOT EXECUTABLE: verify_setup.sh"
```
EXECUTABLE: verify_setup.sh

### Commits Exist

```bash
git log --oneline --all | grep -q "f9e33fa" && echo "FOUND: f9e33fa" || echo "MISSING: f9e33fa"
```
FOUND: f9e33fa

```bash
git log --oneline --all | grep -q "b214ae8" && echo "FOUND: b214ae8" || echo "MISSING: b214ae8"
```
FOUND: b214ae8

## Self-Check: PASSED

All files verified to exist:
- environment.yml: FOUND
- scripts/verify_setup.sh: FOUND and EXECUTABLE

All commits verified:
- f9e33fa: FOUND (Task 1 - environment.yml finalized)
- b214ae8: FOUND (Task 2 - verify_setup.sh created)

---

**Plan Status:** COMPLETE
**All Tasks:** 2/2 executed
**All Verifications:** PASSED
**Deviations:** None
**Blockers:** None
