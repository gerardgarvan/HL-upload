# Phase 1: Environment Extension & Data Staging - Research

**Researched:** 2026-02-27
**Domain:** Conda environment extension (Polars + DuckDB), HPC project scaffolding, CSV-to-Parquet smoke test
**Confidence:** HIGH

## Summary

Phase 1 extends the existing `hl-eda` conda environment with Polars and DuckDB, sets up the project directory structure on HiPerGator, links shared configuration assets from the HL-EDA project, and validates the end-to-end pipeline with a single-table smoke test (DEMOGRAPHIC CSV → parse SAS DATE9. dates → write Parquet → read back → verify).

This is largely an infrastructure phase — most of the hard decisions (stack, HPC paths, SLURM account, conda env) were already made and validated in HL-EDA. The primary risks are: (1) conda dependency conflicts when adding Polars/DuckDB to the existing env, (2) ensuring Polars correctly parses SAS DATE9. formatted strings (e.g., "01JAN2020") using `str.to_date("%d%b%Y")`, and (3) verifying Parquet round-trip preserves date types on HiPerGator's `/blue` filesystem.

**Primary recommendation:** Extend the existing `hl-eda` conda env in-place with `mamba install polars duckdb -c conda-forge`. If dependency conflicts arise, create a new `hl-clean` env cloning the base packages. Use symlinks to reference HL-EDA's shared assets (paths.toml, datastructure.txt, valuesets.csv) rather than copying.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REQ-01 | Load 22 large CSV files as fast as possible | Polars 1.22.0 `read_csv()` benchmarked at ~0.4s/500MB; `write_parquet()` creates compressed columnar files for 10-100x faster subsequent reads; smoke test verifies this works on HiPerGator `/blue` |
| REQ-04 | Run on HiPerGator HPC | Extend existing `hl-eda` conda env on `/blue`; reuse SLURM template from HL-EDA (`--account=erin.mobley-hl.bcu`, `--mem=64gb`, `--time=2:00:00`); Polars and DuckDB installable via conda-forge |
| REQ-05 | HIPAA-compliant data handling | Data reads from `/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915` (read-only source); derived Parquet files written to `/blue/erin.mobley-hl.bcu/hl-clean/parquet/`; no local copies; paths enforced via `config/paths.toml` |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Polars | 1.22.0 | CSV reading, date parsing, Parquet writing | Fastest Python CSV reader (~0.4s/500MB); lazy evaluation via `scan_csv()`; native `str.to_date()` for SAS DATE9. strings; auto-parallelizes on HPC multi-core nodes |
| DuckDB | 1.4.4 | SQL queries on Parquet, cross-table validation | Embedded SQL engine; out-of-core for datasets exceeding RAM; zero-copy Arrow exchange with Polars; no server needed on HPC |
| Python | 3.11 | Runtime | Already pinned in HL-EDA env; `tomllib` in stdlib eliminates `tomli` dependency |

### Already Installed (from HL-EDA)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| pandas | >=2.2 | Downstream compatibility with HL-EDA code | Keep; do not remove |
| pyarrow | >=18.0 | Parquet I/O, Arrow columnar backend | Keep; used by both Polars and pandas |
| matplotlib | >=3.9 | Visualization (downstream) | Keep |
| seaborn | >=0.13 | Statistical visualization (downstream) | Keep |
| jinja2 | >=3.1 | Report templating (downstream) | Keep |
| tabulate | latest | Table formatting | Keep |
| tomli | >=2.0 | TOML config parsing (Python <3.11 fallback) | Keep for compatibility |

### Installation

```bash
# On HiPerGator, in the existing hl-eda env:
module load conda
conda activate hl-eda
mamba install polars duckdb -c conda-forge

# Verify installation
python -c "import polars as pl; print(f'Polars {pl.__version__}')"
python -c "import duckdb; print(f'DuckDB {duckdb.__version__}')"

# Export updated environment
mamba env export --no-builds > environment.yml
```

**Fallback if dependency conflicts occur:**
```bash
# Create a new env extending hl-eda's packages
mamba create -n hl-clean python=3.11 pandas>=2.2 pyarrow>=18.0 polars duckdb \
    matplotlib>=3.9 seaborn>=0.13 jupyter ipykernel -c conda-forge
conda activate hl-clean
pip install jinja2>=3.1 tabulate tomli>=2.0
mamba env export --no-builds > environment.yml
```

## Architecture Patterns

### Recommended Project Structure

```
Data loading and cleaning/          # workspace root (local dev)
├── config/
│   └── paths.toml                  # symlink or copy from HL-EDA; HPC path config
├── datastructure.txt               # symlink or copy from HL-EDA; 22 CSV filenames
├── valuesets.csv                   # symlink or copy from HL-EDA; PCORnet code mappings
├── environment.yml                 # updated conda env (adds polars, duckdb)
├── submit_job.sh                   # SLURM batch template (adapted from HL-EDA)
├── src/
│   └── load/
│       ├── __init__.py
│       ├── config.py               # path config loader (reuse HL-EDA pattern)
│       └── schema.py               # datastructure.txt parser (reuse HL-EDA pattern)
├── scripts/
│   └── smoke_test.py               # Phase 1 validation: CSV→Parquet round-trip
└── .planning/                      # planning artifacts (not deployed to HPC)
```

**On HiPerGator (`/blue`):**
```
/blue/erin.mobley-hl.bcu/
├── hl-clean/                       # project working directory
│   ├── parquet/                    # output: converted Parquet files
│   ├── logs/                       # SLURM job output logs
│   ├── scripts/                    # deployed scripts
│   └── config/                     # deployed config
└── .conda/envs/hl-eda/            # conda env (or hl-clean if new)
```

**On HiPerGator (`/orange`, read-only):**
```
/orange/erin.mobley-hl.bcu/
└── Mailhot_V1_20250915/           # 22 source CSVs (never modified)
```

### Pattern 1: Config-Driven Paths (from HL-EDA)

**What:** All HPC paths are read from `config/paths.toml`, never hardcoded.
**When to use:** Every script that reads source data or writes output.
**Why:** Same code works locally (staged subset) and on HPC (full data).

```python
# config/paths.toml format (reuse from HL-EDA)
[paths]
data_root = "/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915"
scratch_root = "/blue/erin.mobley-hl.bcu"
datastructure_path = "datastructure.txt"
valuesets_path = "valuesets.csv"

# New paths for this project
[paths.output]
parquet_dir = "hl-clean/parquet"    # relative to scratch_root
```

```python
# Source: HL-EDA/src/load/config.py pattern
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from pathlib import Path

def load_config(config_path: Path | None = None) -> dict:
    root = Path(__file__).resolve().parents[2]
    path = config_path or (root / "config" / "paths.toml")
    with open(path, "rb") as f:
        return tomllib.load(f)
```

### Pattern 2: SAS DATE9. Parsing with Polars

**What:** Parse SAS DATE9. formatted strings (e.g., "01JAN2020") into proper Date type.
**When to use:** During CSV-to-Parquet conversion for all date columns.
**Verified with:** Polars official docs (`str.to_date` uses chrono format strings).

```python
import polars as pl

# Parse SAS DATE9. strings to Date type
df = pl.read_csv("DEMOGRAPHIC_Mailhot_V1.csv")
date_cols = ["BIRTH_DATE"]  # identified per table

df = df.with_columns([
    pl.col(c).str.to_date("%d%b%Y", strict=False).alias(c)
    for c in date_cols
    if c in df.columns
])

df.write_parquet("DEMOGRAPHIC.parquet")
```

**For datetime columns (SAS DATETIME format):**
```python
datetime_cols = ["UPDATE_DTTM"]
df = df.with_columns([
    pl.col(c).str.to_datetime("%d%b%Y:%H:%M:%S", strict=False).alias(c)
    for c in datetime_cols
    if c in df.columns
])
```

### Pattern 3: SLURM Job Template (from HL-EDA)

**What:** Batch job submission script for HiPerGator.
**Source:** Adapted from `HL-EDA/EDA/run_report.slurm`.

```bash
#!/bin/bash
#SBATCH --job-name=hl-clean-smoke
#SBATCH --account=erin.mobley-hl.bcu
#SBATCH --qos=erin.mobley-hl.bcu
#SBATCH --mem=64gb
#SBATCH --time=2:00:00
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/smoke_%j.log

module load conda
source $(conda info --base)/etc/profile.d/conda.sh
conda activate hl-eda   # or hl-clean if new env

cd /blue/erin.mobley-hl.bcu/hl-clean
python scripts/smoke_test.py
```

**Changes from HL-EDA SLURM template:**
- `--cpus-per-task=4` (up from 2) — Polars auto-parallelizes on available cores
- `--output=logs/smoke_%j.log` — dedicated log directory
- `cd` target changed to `/blue/erin.mobley-hl.bcu/hl-clean`

### Anti-Patterns to Avoid

- **Copying data to local machine:** Source CSVs on `/orange` contain PHI. Never copy to local disk. Always work on HPC.
- **Hardcoding HPC paths:** Use `config/paths.toml` for all paths. The existing HL-EDA `config.py` already handles this.
- **Running pip install outside conda env:** On HiPerGator, this pollutes `~/.local` and causes conflicts across kernels.
- **Running computation on login nodes:** Always use SLURM (`sbatch` or `srun`). Login node computation can get your account suspended.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CSV parsing | Custom CSV reader | `pl.read_csv()` | Handles encoding, quoting, type inference, multi-threading automatically |
| Parquet I/O | Custom binary format | `df.write_parquet()` / `pl.read_parquet()` | Columnar compression, type preservation, column pruning built-in |
| Date string parsing | Regex-based date parser | `pl.col().str.to_date("%d%b%Y")` | Handles edge cases, missing values, and is 10-100x faster than Python regex |
| TOML config loading | Custom config parser | `tomllib` (stdlib) / `tomli` | Standard library in Python 3.11; already used in HL-EDA |
| Environment export | Manual package listing | `mamba env export --no-builds` | Captures exact versions, handles platform differences |
| Datastructure parsing | Re-implement file list | Reuse HL-EDA `schema.parse_datastructure()` | Already handles comments, quotes, path extraction |

**Key insight:** Phase 1 is infrastructure glue. Almost every component already exists in HL-EDA — the task is referencing/extending, not building from scratch.

## Common Pitfalls

### Pitfall 1: Conda Dependency Conflicts When Adding Polars/DuckDB

**What goes wrong:** Adding `polars` and `duckdb` to an existing conda env may trigger dependency conflicts with pinned packages (especially `pyarrow` version constraints).
**Why it happens:** Polars bundles its own Arrow implementation; DuckDB has specific pyarrow version requirements. The existing env pins `pyarrow>=18.0`.
**How to avoid:** Use `mamba install` (faster solver). If conflicts arise, create a fresh `hl-clean` env with all packages specified together so the solver can find a compatible set.
**Warning signs:** `mamba install` hangs for >5 minutes, or reports "conflicting requests."

### Pitfall 2: SAS DATE9. Case Sensitivity in Polars

**What goes wrong:** Polars `str.to_date("%d%b%Y")` may fail if month abbreviations in the CSV have unexpected casing (e.g., "01jan2020" vs "01JAN2020" vs "01Jan2020").
**Why it happens:** The `%b` format specifier's case sensitivity depends on the underlying chrono parser. SAS typically exports uppercase month abbreviations (JAN, FEB, etc.), but some extracts may vary.
**How to avoid:** Apply `.str.to_uppercase()` before parsing, or test with actual data first. The existing HL-EDA data uses uppercase (confirmed from `masking.py` which successfully parses with `%d%b%Y`).
**Warning signs:** High null count after date parsing that doesn't match the raw data's missing rate.

### Pitfall 3: Parquet Write Location on Wrong Filesystem

**What goes wrong:** Writing Parquet files to `/orange` (read-only for derived data) or `/home` (40GB quota, backed up — not for PHI).
**Why it happens:** Paths misconfigured or `scratch_root` not used.
**How to avoid:** Always write derived outputs under `scratch_root` (`/blue/erin.mobley-hl.bcu`). The `paths.toml` config enforces this.
**Warning signs:** Permission denied errors on `/orange`; quota exceeded on `/home`.

### Pitfall 4: SLURM Job Using Wrong Conda Env

**What goes wrong:** Job script activates `hl-eda` but Polars/DuckDB were installed in `hl-clean`, or vice versa.
**Why it happens:** Multiple conda envs with similar names.
**How to avoid:** The SLURM template must match whichever env has polars+duckdb. Verify with `python -c "import polars"` in the job script before running main logic.
**Warning signs:** `ModuleNotFoundError: No module named 'polars'` in SLURM output logs.

### Pitfall 5: Forgetting `--no-builds` in Environment Export

**What goes wrong:** `mamba env export` without `--no-builds` includes platform-specific build strings (e.g., `h1234567_0`), making the `environment.yml` non-portable between Linux (HPC) and Windows (dev).
**Why it happens:** Default export includes full build metadata.
**How to avoid:** Always use `mamba env export --no-builds > environment.yml`. This produces a cross-platform reproducible spec.
**Warning signs:** `environment.yml` contains long hash strings in package specifications.

### Pitfall 6: Not Verifying Data Path Accessibility

**What goes wrong:** Script assumes `/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915` is accessible but the directory doesn't exist or has wrong permissions.
**Why it happens:** Storage migration (UF migrated Blue storage Nov 2025–Jan 2026), permissions change, or path typo.
**How to avoid:** The smoke test must verify: (1) source directory exists, (2) at least one CSV is readable, (3) output directory is writable. Fail fast with clear error messages.
**Warning signs:** `FileNotFoundError` or `PermissionError` in job logs.

## Code Examples

### Smoke Test Script Pattern

The smoke test validates the entire Phase 1 pipeline end-to-end:

```python
"""Smoke test: load DEMOGRAPHIC CSV → parse SAS dates → write Parquet → read back → verify."""
import polars as pl
from pathlib import Path
import sys

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

def load_paths(config_path: Path) -> dict:
    with open(config_path, "rb") as f:
        return tomllib.load(f)["paths"]

def smoke_test(config_path: Path) -> None:
    paths = load_paths(config_path)
    data_root = Path(paths["data_root"])
    scratch_root = Path(paths["scratch_root"])
    parquet_dir = scratch_root / "hl-clean" / "parquet"
    parquet_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Verify data path accessible
    csv_path = data_root / "DEMOGRAPHIC_Mailhot_V1.csv"
    assert csv_path.exists(), f"Source CSV not found: {csv_path}"
    print(f"[OK] Source CSV exists: {csv_path}")

    # Step 2: Load CSV with Polars
    df = pl.read_csv(csv_path)
    print(f"[OK] Loaded {df.shape[0]:,} rows, {df.shape[1]} columns")

    # Step 3: Parse SAS DATE9. dates
    date_col = "BIRTH_DATE"
    if date_col in df.columns:
        n_before = df[date_col].null_count()
        df = df.with_columns(
            pl.col(date_col).str.to_date("%d%b%Y", strict=False)
        )
        n_after = df[date_col].null_count()
        print(f"[OK] Parsed {date_col}: {df[date_col].dtype}, "
              f"nulls {n_before} -> {n_after}")

    # Step 4: Write Parquet
    out_path = parquet_dir / "DEMOGRAPHIC.parquet"
    df.write_parquet(out_path)
    print(f"[OK] Wrote Parquet: {out_path} "
          f"({out_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # Step 5: Read back and verify
    df2 = pl.read_parquet(out_path)
    assert df2.shape == df.shape, "Shape mismatch after round-trip"
    assert df2[date_col].dtype == pl.Date, f"Date type lost: {df2[date_col].dtype}"
    print(f"[OK] Round-trip verified: {df2.shape[0]:,} rows, "
          f"{date_col} dtype={df2[date_col].dtype}")

    # Step 6: Verify /blue has space (informational)
    print(f"[OK] Parquet directory writable: {parquet_dir}")
    print("\n=== SMOKE TEST PASSED ===")

if __name__ == "__main__":
    config = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config/paths.toml")
    smoke_test(config)
```

### DuckDB Verification

```python
import duckdb

parquet_path = "/blue/erin.mobley-hl.bcu/hl-clean/parquet/DEMOGRAPHIC.parquet"
con = duckdb.connect()

result = con.sql(f"""
    SELECT COUNT(*) AS n_rows,
           MIN(BIRTH_DATE) AS min_birth,
           MAX(BIRTH_DATE) AS max_birth
    FROM read_parquet('{parquet_path}')
""").fetchone()

print(f"DuckDB reads Parquet: {result[0]:,} rows, "
      f"birth range {result[1]} to {result[2]}")
```

### Polars-DuckDB Zero-Copy Exchange

```python
import polars as pl
import duckdb

df = pl.read_parquet("DEMOGRAPHIC.parquet")
con = duckdb.connect()

# DuckDB can query Polars DataFrames directly via Arrow exchange
result = con.sql("SELECT SEX, COUNT(*) AS n FROM df GROUP BY SEX").pl()
print(result)  # returns a Polars DataFrame
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pd.read_csv()` with C engine | `pl.read_csv()` or `pd.read_csv(engine='pyarrow')` | 2023-2024 | 7-15x faster CSV reading |
| Re-read CSVs every run | One-time CSV→Parquet conversion | Best practice since ~2022 | 10-100x faster subsequent reads |
| `conda install` for deps | `mamba install` for deps | 2021+ | 10-100x faster dependency resolution |
| Hardcoded file paths | `config/paths.toml` | HL-EDA project pattern | Same code works on HPC and local |
| pandas `object` dtype for dates | Polars `Date`/`Datetime` native types | Polars 0.15+ (2023) | Type safety, faster operations |
| `pd.to_datetime(series, format="%d%b%Y")` | `pl.col().str.to_date("%d%b%Y")` | Polars equivalent | Native Polars; no pandas dependency for date parsing |

**Deprecated/outdated:**
- `polars.from_epoch()` with integer offset: NOT needed here — our data uses SAS DATE9. strings, not integer days-since-epoch
- `conda` without mamba: Still works but 10-100x slower dependency resolution; always prefer `mamba`

## Open Questions

1. **Will `mamba install polars duckdb` succeed in the existing `hl-eda` env?**
   - What we know: Both packages are available on conda-forge. HL-EDA env has `pyarrow>=18.0` which should be compatible.
   - What's unclear: Whether the exact pinned versions in the existing env conflict with Polars 1.22.0 or DuckDB 1.4.4.
   - Recommendation: Try in-place first. If it fails, create a new `hl-clean` env (fallback documented above).

2. **Blue storage migration status**
   - What we know: UF migrated Blue storage Nov 2025–Jan 2026. Paths remain `/blue/<group>`.
   - What's unclear: Whether the migration is fully complete and all data/envs are accessible.
   - Recommendation: Verify access as first step in smoke test. Check with `blue_quota` command.

3. **Exact CSV file sizes for the 22 tables**
   - What we know: The 22 filenames are known from `datastructure.txt`. Cohort is 9,331 HL patients.
   - What's unclear: Total data volume on disk (affects Parquet conversion time and storage needs).
   - Recommendation: Phase 1 smoke test should report file sizes. Phase 2 will handle full conversion.

4. **TUMOR_REGISTRY date format**
   - What we know: Most tables use SAS DATE9. ("01JAN2020"). TUMOR_REGISTRY may use NAACCR YYYYMMDD format.
   - What's unclear: Actual format in the Mailhot_V1 extract.
   - Recommendation: Not a Phase 1 concern — deferred to Phase 2. Smoke test uses DEMOGRAPHIC (confirmed SAS DATE9.).

## Sources

### Primary (HIGH confidence)
- Polars official docs (docs.pola.rs) — `read_csv()`, `write_parquet()`, `str.to_date()` API verified
- DuckDB official site (duckdb.org) — version 1.4.4, Python installation, embedded SQL
- Anaconda.org conda-forge — Polars 1.22.0, DuckDB 1.4.4 package availability confirmed
- HL-EDA project source code — `config.py`, `reader.py`, `schema.py`, `masking.py` patterns verified by reading actual files
- HL-EDA `environment.yml` — exact current dependencies confirmed
- HL-EDA `config/paths.toml` — HPC path configuration confirmed
- HL-EDA `EDA/run_report.slurm` — SLURM template confirmed

### Secondary (MEDIUM confidence)
- UF Research Computing docs (docs.rc.ufl.edu) — SLURM, conda, storage policies (verified in HIPERGATOR_RESEARCH.md)
- Multiple CSV benchmark sources — Polars ~0.4s/500MB (verified in TECH_RESEARCH.md)
- DuckDB-Polars zero-copy integration — Arrow IPC exchange (verified via multiple sources)

### Tertiary (LOW confidence)
- Blue storage migration timeline — inferred from HIPERGATOR_RESEARCH.md, needs runtime verification
- Exact Polars/DuckDB conda-forge dependency compatibility with existing env — needs runtime test

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Polars 1.22.0 and DuckDB 1.4.4 versions confirmed on conda-forge; APIs verified against official docs
- Architecture: HIGH — project structure mirrors proven HL-EDA patterns; all shared assets exist and are verified
- Pitfalls: HIGH — based on direct codebase analysis (HL-EDA source), HPC documentation, and conda best practices

**Research date:** 2026-02-27
**Valid until:** 2026-03-29 (30 days — stable infrastructure; Polars/DuckDB may release minor versions but APIs are stable)
