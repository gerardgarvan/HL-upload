# HL Data Pipeline: Setup and Reproducibility Guide

**Project:** HL insurance inequities pipeline (UFPTI 2405-HLX17A)
**Audience:** Collaborators with HyperGator access, Python experience, and clinical data familiarity
**Last Updated:** 2026-03-18

---

## Prerequisites

Before starting, ensure you have:

- **HyperGator account** with SSH access (`ssh <username>@hpg.rc.ufl.edu`)
- **Filesystem access** to `/orange` (read-only source data) and `/blue` (scratch space)
- **Basic familiarity** with Linux command line and conda
- **Project architecture overview** - See `docs/PIPELINE.md` for pipeline phases and data flow

---

## Section 1: Initial Setup (One-Time)

### Step 1.1: Clone the repository

```bash
ssh <username>@hpg.rc.ufl.edu
cd /blue/<group>/<username>
git clone <repo-url>
cd "Data loading and cleaing"
```

### Step 1.2: Set up conda environment

Load conda module and initialize:

```bash
module load conda
```

**Note:** If `module load conda` fails, try `module avail conda` to find the exact module name on your HyperGator installation (e.g., `conda/23.3.1`).

**IMPORTANT ONE-TIME SETUP:** Initialize conda for your shell (required once per HyperGator account):

```bash
conda init bash
```

**You MUST logout and login for changes to take effect.** After relogin, verify that `(base)` appears in your shell prompt.

Create the hl-eda environment from the specification:

```bash
conda env create -f environment.yml
```

**Faster alternative:** Use `mamba` for faster dependency resolution (optional):

```bash
conda install -n base mamba
mamba env create -f environment.yml
```

Activate the environment:

```bash
conda activate hl-eda
```

### Step 1.3: Verify environment

Confirm Python version and core dependencies:

```bash
python --version          # Should show Python 3.11.x
python -c "import polars; print(polars.__version__)"  # Should succeed without error
```

**Success criteria:**

- [ ] Repository cloned to your /blue directory
- [ ] `(base)` appears in shell prompt after relogin
- [ ] `conda activate hl-eda` succeeds
- [ ] Python 3.11+ and polars import successfully

---

## Section 2: Configuration

### Step 2.1: Edit `config/paths.toml`

The pipeline requires path configuration specific to your HyperGator setup. Open `config/paths.toml` in your editor and modify the paths:

**Current file structure:**

```toml
# HL data loading & cleaning path configuration
# Data lives on HPC: orange (read-only source), blue (scratch/output)
# Edit paths for staged subset or different HPC user dirs

[paths]
# Source data root (OneFlorida+ PCORnet Mailhot cohort)
data_root = "/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915"

# Scratch and derived outputs
scratch_root = "/blue/erin.mobley-hl.bcu"

# Paths relative to project root (where config/ lives)
datastructure_path = "datastructure.txt"
valuesets_path = "valuesets.csv"

[paths.output]
# Relative to scratch_root (not project root). Resolved: scratch_root / parquet_dir
# e.g. /blue/erin.mobley-hl.bcu/hpc-upload/parquet
parquet_dir = "hpc-upload/parquet"
logs_dir = "hpc-upload/logs"
# Relative to project root (HL-upload). Derived outputs: patient_level, encounter_payer_summary
derived_dir = "derived"
```

**Paths you MUST change:**

1. **`data_root`** - Full path to OneFlorida+ extract CSV files on `/orange` (read-only source data)
2. **`scratch_root`** - Full path to your output space on `/blue` (read-write scratch directory)

**Paths you typically do NOT change:**

- `datastructure_path` and `valuesets_path` are relative to project root (these reference files ship with the repo)
- `parquet_dir`, `logs_dir`, `derived_dir` can remain as defaults unless you have specific output organization requirements

**Example for a different user:**

```toml
[paths]
data_root = "/orange/research-group/my-username/oneflorida-extract"
scratch_root = "/blue/research-group/my-username"
```

### Step 2.2: Validate configuration

Run the configuration validation to confirm paths are correct:

```bash
python -c "from src.load.config import load_and_validate_config; load_and_validate_config()"
```

**Expected output:**

```
CONFIG VALIDATION PASSED
  data_root exists: /orange/erin.mobley-hl.bcu/Mailhot_V1_20250915
  scratch_root exists: /blue/erin.mobley-hl.bcu
  datastructure_path exists: /home/.../Data loading and cleaing/datastructure.txt
  valuesets_path exists: /home/.../Data loading and cleaing/valuesets.csv
```

**Common failure messages and fixes:**

- `FileNotFoundError: data_root does not exist` - Check `/orange` path and filesystem mount
- `FileNotFoundError: scratch_root does not exist` - Create directory with `mkdir -p <path>`
- `ModuleNotFoundError: No module named 'src'` - Ensure you're in the project root directory
- `FileNotFoundError: datastructure.txt` - Verify file exists in project root (ships with repo)

### Step 2.3: Run setup verification (optional but recommended)

Run the comprehensive setup verification script to check environment, dependencies, config, and compute node status:

```bash
bash scripts/verify_setup.sh
```

**What it checks:**

1. **Conda environment** - Verifies `hl-eda` is activated
2. **Python version** - Checks Python 3.11-3.14
3. **Core dependencies** - Tests import of polars, pandas, pyarrow, pytest, jinja2, tabulate
4. **Config validation** - Runs `load_and_validate_config()` to verify paths
5. **Compute node status** - Warns if on login node, provides `srun` command
6. **Source data accessibility** - Checks if `data_root` directory exists (expected to fail on login node)

**Expected output:** `6/6 checks passed` (or 5/6 if data not accessible from login node, which is normal).

**Success criteria:**

- [ ] `config/paths.toml` edited with your HyperGator paths
- [ ] Configuration validation passes
- [ ] Setup verification script shows 5-6/6 checks passed

---

## Section 3: Running the Pipeline

**IMPORTANT:** Do not run pipeline scripts on the login node. Pipeline scripts process large datasets and will be killed by HyperGator resource limits. Always request a compute node first.

### Step 3.0: Request compute node

Use `srun` to request an interactive compute node:

```bash
srun --pty --mem=16gb --time=2:00:00 bash
```

**Parameters explained:**
- `--pty` - Allocate pseudo-terminal for interactive session
- `--mem=16gb` - Request 16 GB RAM (sufficient for typical pipeline run; increase if needed)
- `--time=2:00:00` - Request 2-hour time limit (adjust based on dataset size)

**After `srun` allocates a node, re-activate the environment:**

```bash
conda activate hl-eda
```

Verify you're on a compute node (hostname should NOT contain "login"):

```bash
hostname
```

### Step 3.1: Full pipeline (5 phases in order)

Execute all 5 pipeline phases sequentially. Each script prints progress output (table names, row counts, elapsed time).

**Phase 1: CSV-to-Parquet conversion**

```bash
python scripts/convert_all.py
```

Converts 22 OneFlorida+ PCORnet CDM CSV files to typed Parquet format with automatic date column detection. Outputs Parquet files to `scratch_root/hpc-upload/parquet/` and creates `file_inventory.csv` metadata.

**Phase 2: Structural validation and cohort verification**

```bash
python scripts/validate_all.py
```

Performs read-only structural validation of typed Parquet files. Checks schema compliance, referential integrity (PATID/ENCOUNTERID), completeness by partner, and HL cohort membership. Writes validation reports to `reports/`.

**Phase 3: Deduplication, flagging, and harmonization**

```bash
python scripts/clean_all.py
```

Adds flag columns to identify duplicates (IS_DUPLICATE), cross-table consistency issues, partner provenance, and clinical flags (HL diagnosis, survivorship, oncology provider). No records deleted; all changes are additive flag columns.

**Phase 4: Patient-level assembly and quality reports**

```bash
python scripts/assemble_clean.py
```

Copies flagged Parquet files to `parquet_clean/` (final cleaned dataset), builds patient-level derived variables (one row per patient), and writes quality reports using Kahn Framework metrics.

**Phase 5: Insurance/payer analysis tables and figures**

```bash
python scripts/build_insurance_summary.py
```

Builds insurance/payer analysis tables and figures from patient-level data. Payer categories derived from PCORnet codes with effective payer logic, dual-eligible detection, and treatment window payer assignment. All outputs use small-cell suppression (counts 1-10 → "-").

**Note:** Each script accepts an optional config path argument if you're using a non-default config:

```bash
python scripts/convert_all.py config/paths_custom.toml
```

### Step 3.2: Individual phase re-runs

Each script can be run independently **IF** its input files exist from a prior run. Phase dependencies:

- Phase 1 (convert_all.py) - Requires raw CSVs in `data_root`
- Phase 2 (validate_all.py) - Requires Parquet files from Phase 1
- Phase 3 (clean_all.py) - Requires Parquet files from Phase 1
- Phase 4 (assemble_clean.py) - Requires flagged Parquet files from Phase 3
- Phase 5 (build_insurance_summary.py) - Requires `derived/encounter_payer_summary.parquet` from Phase 4

**When to use individual re-runs:**

- **Development/debugging** - Modify Phase 3 code, rerun only Phase 3-5 to test changes
- **Report regeneration** - Modify report template, rerun only Phase 5 to regenerate figures
- **Incremental processing** - New data arrives, rerun full pipeline from Phase 1

**For reproducibility, always run the full pipeline** (Phases 1-5 in sequence) when capturing final outputs.

**Success criteria:**

- [ ] Pipeline completes all 5 phases without errors
- [ ] Expected output files exist (see Section 4 for verification)

---

## Section 4: Verification

After pipeline completion, verify outputs using a two-tier approach: quick spot-checks first, then golden baseline comparison for full verification.

### Step 4.1: Quick spot-checks

Verify key output files exist and have expected structure:

**Check 1: Parquet files from Phase 1**

```bash
ls -la /blue/<group>/<username>/hpc-upload/parquet/
```

Expected: 22 `.parquet` files (DEMOGRAPHIC.parquet, ENCOUNTER.parquet, DIAGNOSIS.parquet, etc.)

**Check 2: Patient-level derived data from Phase 4**

```bash
ls -la derived/
```

Expected: `patient_level.parquet` and `encounter_payer_summary.parquet`

**Check 3: Quality reports from Phases 2-4**

```bash
ls -la reports/
```

Expected: `DATA_QUALITY_REPORT.md`, `CLEANING_DECISIONS.md`, `insurance_summary.md`, `structural_validation.md`, `dedup_report.md`

**Check 4: Figures from Phase 5**

```bash
ls -la reports/figures/
```

Expected: PNG files for insurance analyses (e.g., `insurance_payer_at_first_dx.png`, `insurance_payer_at_first_chemo.png`)

**Quick row count check (example):**

```bash
python -c "import polars as pl; print(pl.scan_parquet('derived/patient_level.parquet').select(pl.len()).collect())"
```

Expected: Patient count matching your HL cohort size (typically 5K-10K patients).

### Step 4.2: Golden baseline comparison

Use the golden baseline capture script to verify pipeline reproducibility:

```bash
python scripts/capture_golden.py
```

**First run:** Creates `.golden/manifest.json` baseline with SHA256 checksums, schemas (column names + dtypes), and row counts for all pipeline output files. The manifest contains **NO patient data** (PHI) - only file metadata safe for git commit.

**Subsequent runs:** Compares current outputs against existing manifest and reports:
- **Added files** - New outputs not in baseline (expected after pipeline changes)
- **Removed files** - Outputs missing from current run (unexpected, investigate)
- **Modified files** - Outputs with different SHA256 checksums (expected after code changes, unexpected otherwise)
- **"No changes detected"** - Pipeline reproduced exactly (perfect reproducibility)

**Interpreting results:**

- **No changes detected** - Pipeline outputs are identical to baseline (reproducibility confirmed)
- **Modified files with no code changes** - Indicates environment differences (library versions, random seeds, floating-point precision). Generate lock file for exact reproduction:

```bash
conda env export --no-builds > environment_lock.yml
```

Compare your `environment_lock.yml` with the original author's lock file to identify version differences.

**Note:** The manifest is safe to commit to git (contains only checksums and metadata, no PHI). Actual `.parquet` and `.csv` files are gitignored.

**Success criteria:**

- [ ] All expected output files exist
- [ ] Golden baseline capture completes without errors
- [ ] Manifest differences (if any) are explainable by intentional changes

---

## Section 5: Running Tests

The pipeline includes a comprehensive test suite covering payer logic, date parsing, report generation, and checkpoint validation. Tests use synthetic data fixtures and do **not** require HPC data access. Tests can run on login nodes.

**Run full test suite:**

```bash
make test
```

Or equivalently:

```bash
pytest tests/ -v
```

**Run tests by category (pytest markers):**

```bash
pytest tests/ -m payer -v          # Payer logic tests
pytest tests/ -m dates -v          # Date parsing tests
pytest tests/ -m reports -v        # Report generation tests
pytest tests/ -m checkpoint -v     # Checkpoint validation tests
pytest tests/ -m audit -v          # Tests resolving TODO(audit) items
```

**Run tests for specific modules:**

```bash
pytest tests/test_clean/ -v       # Tests for src/clean/ module
pytest tests/test_load/ -v        # Tests for src/load/ module
pytest tests/test_validate/ -v    # Tests for src/validate/ module
pytest tests/test_report/ -v      # Tests for src/report/ module
```

**Expected result:** All tests should pass. Test failures indicate environment issues or code regressions.

**Success criteria:**

- [ ] `make test` passes all tests
- [ ] No import errors or dependency issues

---

## Section 6: Troubleshooting

### Issue 1: "conda: command not found" after `conda init`

**Problem:** Conda not found in shell after running `conda init bash`.

**Solution:** Logout and login required after `conda init`. The init command modifies `.bashrc` but changes only take effect in new shell sessions.

```bash
exit
ssh <username>@hpg.rc.ufl.edu
# Now (base) should appear in prompt
```

### Issue 2: "ModuleNotFoundError: No module named 'polars'"

**Problem:** Core dependencies not installed or environment not activated.

**Solution:** Activate the hl-eda environment:

```bash
conda activate hl-eda
python -c "import polars; print(polars.__version__)"
```

If activation succeeds but import fails, reinstall environment:

```bash
conda env remove -n hl-eda
conda env create -f environment.yml
```

### Issue 3: "FileNotFoundError" during pipeline execution

**Problem:** Config paths incorrect or files missing.

**Solution:** Run config validation to diagnose:

```bash
python -c "from src.load.config import load_and_validate_config; load_and_validate_config()"
```

Check error message for specific missing path. Verify:
- `data_root` points to OneFlorida+ extract CSV directory
- `scratch_root` exists and is writable
- `datastructure.txt` and `valuesets.csv` exist in project root

### Issue 4: Process killed during pipeline execution

**Problem:** Pipeline script killed by HyperGator resource limits.

**Solution:** You're running on login node. Use `srun` to request compute node:

```bash
srun --pty --mem=16gb --time=2:00:00 bash
conda activate hl-eda
python scripts/convert_all.py
```

For larger datasets, increase memory:

```bash
srun --pty --mem=32gb --time=4:00:00 bash
```

### Issue 5: "module load conda" fails

**Problem:** Conda module not found or different module name on your HyperGator installation.

**Solution:** Find available conda modules:

```bash
module avail conda
```

Load specific version:

```bash
module load conda/23.3.1
```

### Issue 6: Slow `conda env create` (10+ minutes)

**Problem:** Conda dependency resolver is slow for complex environments.

**Solution:** Use mamba for faster resolution:

```bash
conda install -n base mamba
mamba env create -f environment.yml
```

Mamba uses libsolv (faster SAT solver) and typically resolves in 1-2 minutes vs 10-15 minutes for conda.

### Issue 7: Permission denied on `/orange` or `/blue`

**Problem:** Filesystem not accessible or insufficient permissions.

**Solution:**
- Verify group membership: `groups` (should list research group)
- Verify filesystem mounts: `df -h | grep -E 'orange|blue'`
- Contact PI or HyperGator support to request filesystem access

### Issue 8: Golden baseline shows differences after no code changes

**Problem:** Pipeline outputs changed despite no code modifications.

**Solution:** Library version differences causing non-deterministic behavior. Generate lock file to capture exact environment:

```bash
conda env export --no-builds > environment_lock.yml
```

Compare with original author's lock file. If versions differ significantly, use lock file for exact reproduction:

```bash
conda env create -f environment_lock.yml -n hl-eda-locked
conda activate hl-eda-locked
```

Rerun pipeline and capture golden baseline with locked environment.

---

## Section 7: Reference

### Quick Reference: Daily Workflow

```bash
# Connect and navigate
ssh <username>@hpg.rc.ufl.edu
cd /blue/<group>/<username>/"Data loading and cleaing"

# Activate environment
conda activate hl-eda

# Request compute node
srun --pty --mem=16gb --time=2:00:00 bash
conda activate hl-eda  # Re-activate in srun session

# Run full pipeline
python scripts/convert_all.py
python scripts/validate_all.py
python scripts/clean_all.py
python scripts/assemble_clean.py
python scripts/build_insurance_summary.py

# Verify outputs
python scripts/capture_golden.py
```

### Key Files

- **`config/paths.toml`** - Path configuration (edit for your HPC setup)
- **`environment.yml`** - Conda environment specification
- **`docs/PIPELINE.md`** - Pipeline architecture and data flow documentation
- **`docs/AUDIT_LOG.md`** - Known issues and technical debt (18 items)
- **`scripts/verify_setup.sh`** - Post-setup verification script (6 checks)
- **`scripts/capture_golden.py`** - Golden baseline capture for regression detection
- **`Makefile`** - Development targets (`make test`, `make lint`)
- **`pytest.ini`** - Test configuration with markers (payer, dates, reports, checkpoint)

### Pipeline Scripts (Execution Order)

1. **`scripts/convert_all.py`** - Phase 1: CSV → Parquet conversion
2. **`scripts/validate_all.py`** - Phase 2: Structural validation
3. **`scripts/clean_all.py`** - Phase 3: Deduplication and flagging
4. **`scripts/assemble_clean.py`** - Phase 4: Patient-level aggregation
5. **`scripts/build_insurance_summary.py`** - Phase 5: Insurance analysis

### Output Directories

- **`scratch_root/hpc-upload/parquet/`** - Typed Parquet files (Phase 1)
- **`scratch_root/hpc-upload/parquet_clean/`** - Flagged Parquet files (Phase 4 copy)
- **`derived/`** - Patient-level derived datasets (Phase 4)
- **`reports/`** - Quality reports, validation results, insurance summaries (Phases 2-5)
- **`reports/figures/`** - PNG charts (Phase 5)
- **`.golden/manifest.json`** - Golden baseline manifest (git-committed, no PHI)

---

**End of SETUP.md**
