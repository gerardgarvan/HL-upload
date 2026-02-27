# HiPerGator HPC Environment Research

**University of Florida — UFIT Research Computing**
**Researched:** 2026-02-27
**Overall confidence:** HIGH (based on official UF RC documentation)

---

## 1. Software Modules Available

HiPerGator has **2,000+ applications** installed via the Lmod environment module system. Users load software with `module load <appname>` and discover available versions with `module spider <appname>`.

### Key Data Processing Modules

| Software | Module Command | Notes |
|----------|---------------|-------|
| **Python** | `module load python` or `module load python/3.11` | Multiple versions available; always specify version in scripts |
| **R** | `module load R` | Multiple versions; check with `module spider R` |
| **SAS** | `module load sas` | Licensed; run with `-nodms -nonews` for batch mode |
| **MATLAB** | `module load matlab` | Available via modules and Open OnDemand |
| **SQLite** | Available in Python stdlib | In-process, serverless SQL engine |
| **Oracle SQL Developer** | Available as module | For database development tasks |

### Finding Modules

```bash
# Search for a specific application
module spider python
module spider R
module spider sas

# List all loaded modules
module list

# See all available modules
module avail

# Get detailed info about a specific module version
module spider R/4.3
```

**Important:** Always include version numbers in scripts (e.g., `module load python/3.11`) to ensure reproducibility and avoid breaking changes when new versions are installed.

### SQL Database Access

- **SQLite:** Built into Python (`import sqlite3`), zero-configuration, ideal for local analytical databases
- **Oracle SQL Developer:** Available as a module for Oracle database work
- **MySQL/MSSQL:** Not native to HiPerGator compute nodes; available as separate UFIT hosting services
- **DuckDB:** Not a pre-installed module, but installable via conda/pip (see Section 2)

---

## 2. Modern Data Tools: DuckDB, Polars, and Similar

DuckDB, Polars, and other modern data tools are **not pre-installed as system modules** but are fully installable in user conda environments. This is the standard and recommended approach on HiPerGator.

### Installing in a Conda Environment (Python)

```bash
module load conda
mamba create -n data_tools python=3.11
conda activate data_tools

# Install modern data stack
mamba install -c conda-forge duckdb polars pyarrow pandas
pip install ibis-framework[duckdb,polars]  # if not on conda-forge
```

### Installing in R

```r
# From CRAN
install.packages(c("duckdb", "arrow", "dplyr", "tidyr", "duckplyr"))

# Polars for R (from R-universe, not CRAN)
Sys.setenv(NOT_CRAN = "true")
install.packages(c("polars", "tidypolars"), repos = "https://community.r-multiverse.org")
```

### Why These Tools Matter for HPC Data Processing

| Tool | Use Case | HPC Advantage |
|------|----------|---------------|
| **DuckDB** | SQL analytics on local files (CSV, Parquet) | Processes files larger than RAM; zero-config; no server needed |
| **Polars** | DataFrame operations (Rust-based, multi-threaded) | Automatically uses multiple cores; much faster than pandas |
| **PyArrow** | Columnar data format / Parquet I/O | Memory-mapped I/O; zero-copy reads; interop between tools |
| **data.table** (R) | Fast R data manipulation | Multi-threaded; efficient memory use |

**Recommendation:** Use DuckDB for SQL-based analysis of large files and Polars for DataFrame-based pipelines. Both handle out-of-core processing and multi-threading natively, making them ideal for HiPerGator jobs where you can request many cores.

---

## 3. Conda and Pip Environments on HiPerGator

### Loading Conda

```bash
module load conda
# "ml conda" also works (ml is shorthand for module load)
```

On first load, HiPerGator auto-configures conda to store environments on `/blue` storage instead of the 40 GB home directory.

### Critical: Storage Configuration

Conda environments can be very large. **Never store them in your home directory.** The auto-configuration sets:

```
envs_dirs: /blue/<group>/<user>/.conda/envs
pkgs_dirs: /blue/<group>/<user>/.conda/pkgs
```

Verify with:
```bash
conda config --show envs_dirs pkgs_dirs
```

If you belong to multiple groups, add secondary paths:
```bash
conda config --prepend envs_dirs /blue/<other_group>/<user>/.conda/envs
conda config --prepend pkgs_dirs /blue/<other_group>/<user>/.conda/pkgs
```

### Creating and Managing Environments

```bash
# Create a new environment (use mamba for speed)
mamba create -n myenv python=3.11

# Activate
conda activate myenv

# Install packages (prefer mamba, fall back to pip)
mamba install -c conda-forge pandas numpy scipy matplotlib
pip install some-package-not-on-conda  # only within activated env

# Export for reproducibility
conda env export > environment.yml

# Recreate from file
mamba env create -f environment.yml
```

### Why Not `pip install` Directly?

On HiPerGator, running `pip install` **outside** a conda environment causes serious problems:

1. Installs to `~/.local/lib/python3.X/site-packages/` — a single shared location
2. Conflicts with system-installed modules loaded via `module load`
3. In Jupyter, `pip install` goes to `.local` regardless of which kernel is selected
4. No isolation between projects — dependency conflicts are inevitable

**Rule:** Always activate a conda environment before using pip. Inside a conda env, pip installs to the environment's directory tree, avoiding global contamination.

### Alternatives to Conda

HiPerGator also supports:
- **mamba** — Drop-in replacement for conda, much faster dependency resolution (recommended)
- **pixi** — Modern alternative to conda
- **uv** — Fast Python package installer (Python packages only, not compiled C/Fortran)

---

## 4. SLURM Job Submission Basics

HiPerGator uses SLURM (Simple Linux Utility for Resource Management) to schedule all computational work. **Never run computations on login nodes** — this is the #1 reason for account suspension.

### SLURM Script Structure

Every batch script has three sections:

```bash
#!/bin/bash
# --- Section 1: Resource directives ---
#SBATCH --job-name=my_analysis
#SBATCH --output=my_analysis_%j.log
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=you@ufl.edu
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16gb
#SBATCH --time=04:00:00

# --- Section 2: Load software ---
module load conda
conda activate myenv

# --- Section 3: Run your code ---
python my_script.py
```

### Key SBATCH Directives

| Directive | Purpose | Example |
|-----------|---------|---------|
| `--job-name` | Name shown in queue | `--job-name=clean_data` |
| `--output` | Stdout log file (`%j` = job ID) | `--output=job_%j.log` |
| `--error` | Stderr log file (optional) | `--error=job_%j.err` |
| `--ntasks` | Number of tasks (usually 1) | `--ntasks=1` |
| `--cpus-per-task` | CPU cores per task | `--cpus-per-task=8` |
| `--mem` | Total memory for job | `--mem=32gb` |
| `--mem-per-cpu` | Memory per core (use instead of `--mem` for MPI) | `--mem-per-cpu=4gb` |
| `--time` | Maximum wall time | `--time=08:00:00` or `--time=2-00:00:00` |
| `--mail-type` | Email notifications | `--mail-type=END,FAIL` |
| `--mail-user` | Email address | `--mail-user=you@ufl.edu` |
| `--account` | SLURM account (if multiple) | `--account=mygroup` |
| `--qos` | Quality of service | `--qos=mygroup` or `--qos=mygroup-b` |

### Submitting and Monitoring

```bash
# Submit a job
sbatch my_script.sh

# Check your jobs
squeue -u $USER

# Cancel a job
scancel <job_id>

# Check group resource usage
slurmInfo

# View job details after completion
sacct -j <job_id> --format=JobID,JobName,MaxRSS,Elapsed,State
```

### QoS (Quality of Service)

| QoS Type | Priority | Max Time | Guaranteed? |
|----------|----------|----------|-------------|
| **Investment** (`--qos=<group>`) | High | 31 days (744 hours) | Yes |
| **Burst** (`--qos=<group>-b`) | Low | 4 days (96 hours) | No — uses idle resources |

**Defaults:** If unspecified, jobs get 1 CPU core, 4 GB memory, 10-minute time limit. Always set explicit values.

### Array Jobs (Processing Multiple Files)

For processing many files independently (e.g., one script per input file):

```bash
#!/bin/bash
#SBATCH --job-name=process_files
#SBATCH --output=process_%A-%a.log
#SBATCH --array=1-100
#SBATCH --ntasks=1
#SBATCH --mem=8gb
#SBATCH --time=02:00:00

module load conda
conda activate myenv

# Use array task ID to select input file
FILE=$(sed -n "${SLURM_ARRAY_TASK_ID}p" file_list.txt)
python process_single_file.py "$FILE"
```

---

## 5. Storage Options

### Storage Tier Summary

| Storage | Path | Quota | Speed | Purpose | Backed Up? |
|---------|------|-------|-------|---------|------------|
| **Home** | `~/` or `/home/$USER` | **40 GB** | Moderate | Config files, scripts, small code | Daily snapshots (1 week) + weekly (3 weeks) |
| **Blue** | `/blue/<group>` | Group allocation (purchased) | **High** | Active data, job I/O, conda envs | No automatic backup |
| **Orange** | `/orange/<group>` | Group allocation (purchased) | Low | Long-term archival, raw data freeze | No automatic backup |
| **Scratch** | `$TMPDIR` (on compute node) | No quota | **Fastest** (local SSD) | Temporary job files | **Deleted when job ends** |

### Critical Storage Rules

1. **Run all jobs from `/blue`** — This is the high-performance parallel filesystem designed for job I/O. Running from `/home` or `/orange` degrades performance and can lead to account suspension.
2. **Store conda environments on `/blue`** — The 40 GB home quota is too small for most conda environments.
3. **Use `/orange` for archival only** — Lower performance, lower cost. Store raw data here once processed.
4. **`$TMPDIR` is ephemeral** — Data disappears when the job ends. Use for intermediate scratch files only.

### Checking Quotas

```bash
home_quota     # Check home directory usage
blue_quota     # Check blue storage usage
orange_quota   # Check orange storage usage
```

### Data Transfer

| Method | When to Use |
|--------|-------------|
| `sftp` / `scp` | Small files, ad-hoc transfers (connect to `sftp.rc.ufl.edu`) |
| `rsync` | Incremental syncing, many files (connect to `rsync.rc.ufl.edu`) |
| **Globus** | Large files or bulk transfers — best performance and resumability |

---

## 6. Running R or Python: Interactive vs. Batch

### Interactive Sessions

#### Option A: Open OnDemand (Recommended for GUI work)

1. Go to **https://ood.rc.ufl.edu**
2. Log in with GatorLink credentials
3. Select **Interactive Apps** → **Jupyter Notebook** or **RStudio**
4. Configure resources (cores, memory, time, partition)
5. Click **Launch** → wait for allocation → **Connect**

#### Option B: Command-Line Interactive Session

```bash
# Request an interactive shell with 4 cores, 16 GB RAM, 2 hours
srun --ntasks=1 --cpus-per-task=4 --mem=16gb --time=02:00:00 --pty bash -i

# Once on the compute node:
module load R
R  # starts R console

# Or for Python:
module load conda
conda activate myenv
python  # starts Python REPL
```

### Batch Jobs

#### Python Batch Job

```bash
#!/bin/bash
#SBATCH --job-name=python_analysis
#SBATCH --output=python_%j.log
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32gb
#SBATCH --time=08:00:00

module load conda
conda activate myenv

python my_analysis.py
```

#### R Batch Job

```bash
#!/bin/bash
#SBATCH --job-name=r_analysis
#SBATCH --output=r_%j.log
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64gb
#SBATCH --time=12:00:00

module load R

Rscript my_analysis.R
```

#### SAS Batch Job

```bash
#!/bin/bash
#SBATCH --job-name=sas_job
#SBATCH --output=sas_%j.log
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8gb
#SBATCH --time=04:00:00

module load sas

sas -memsize 8192M -nodms -nonews -work $TMPDIR -filelocks none -sysin my_program.sas
```

### When to Use Each

| Scenario | Mode | Why |
|----------|------|-----|
| Exploring data, building plots | Interactive (OOD) | Need visual feedback, iterative |
| Developing/debugging code | Interactive (OOD) | Need to test line-by-line |
| Running a finalized script | Batch (`sbatch`) | Runs unattended, can queue overnight |
| Processing many files | Batch array job | Submit once, processes all in parallel |
| Long-running analysis (hours+) | Batch | Interactive sessions tie up a terminal |

---

## 7. Jupyter and RStudio via Open OnDemand

### Access

URL: **https://ood.rc.ufl.edu**

### Jupyter Notebook

1. **Interactive Apps** → **Jupyter Notebook**
2. Configure:
   - **Number of CPU cores** — most notebooks need 1-2; use more for parallel work
   - **Maximum memory (GB)** — start with 4-8 GB; increase for large datasets
   - **SLURM Account** — your group account
   - **QoS** — your group QoS (or burst)
   - **Time** — session duration (GPU sessions max 72 hours)
   - **Cluster partition** — leave as `default` unless requesting GPU
3. Click **Launch**, wait for resources, then **Connect to Jupyter**

#### Using Conda Environments as Jupyter Kernels

To make a conda environment available in Jupyter:

```bash
module load conda
conda activate myenv
mamba install ipykernel
python -m ipykernel install --user --name myenv --display-name "My Env"
```

The kernel then appears in the Jupyter launcher.

**Warning:** Never run `!pip install` inside a Jupyter notebook on HiPerGator. It installs to `~/.local` regardless of kernel, causing conflicts. Instead, install packages in your conda environment before starting Jupyter.

### RStudio

1. **Interactive Apps** → **RStudio**
2. Configure resources (same options as Jupyter)
3. **Launch** → **Connect to RStudio**

RStudio runs as a SLURM job on a compute node, not on the login node. Your R session has access to `/blue` and `/orange` storage.

### Session Management

- **My Interactive Sessions** menu shows all running sessions
- You can reconnect to running sessions from any browser
- Settings are saved between sessions
- Sessions end when the SLURM time limit expires

---

## 8. Memory and CPU Allocation for Data-Heavy Jobs

### Resource Defaults (Insufficient for Data Work)

| Resource | Default | Typical Data Job |
|----------|---------|-----------------|
| CPU cores | 1 | 4-16 |
| Memory | 4 GB | 16-128 GB |
| Time | 10 minutes | 2-24 hours |

### Sizing Guidelines for Data Processing

| Task | Cores | Memory | Time |
|------|-------|--------|------|
| Loading/cleaning a single CSV (<1 GB) | 1 | 8 GB | 1-2 hours |
| Loading/cleaning a large CSV (1-10 GB) | 1-4 | 16-32 GB | 2-4 hours |
| Processing a very large file (10-50 GB) | 4-8 | 64-128 GB | 4-12 hours |
| Polars/DuckDB on large files | 4-16 | 16-64 GB | 2-8 hours |
| R data.table on large files | 4-8 | 32-64 GB | 2-6 hours |
| SAS processing | 1-2 | 8-32 GB | 2-8 hours |
| Merging/joining multiple large datasets | 4-8 | 64-128 GB | 4-12 hours |

### Memory Strategy

1. **Start small, scale up:** Submit a test run with modest resources. The completion email shows actual usage.
2. **Add 15-20% buffer:** If your test used 22 GB, request `--mem=26gb`.
3. **Don't over-request:** Requesting 500 GB when you need 20 GB wastes your group's allocation and slows everyone down.
4. **Use `sacct` to check actual usage:**
   ```bash
   sacct -j <job_id> --format=JobID,MaxRSS,Elapsed,State
   ```

### CPU Strategy

- **Most R and Python scripts are single-threaded by default.** Requesting 16 cores won't help unless your code explicitly uses them.
- **Polars automatically uses all available cores** — request more cores for larger speedups.
- **DuckDB uses multiple cores automatically** — same as Polars.
- **pandas is mostly single-threaded** — extra cores don't help much.
- **R `parallel` / `foreach` packages** — must be explicitly coded to use multiple cores.

### For R Parallel Jobs

```bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8    # R parallel threads bind to cpus-per-task
#SBATCH --mem=64gb
```

In R:
```r
library(parallel)
ncores <- as.integer(Sys.getenv("SLURM_CPUS_PER_TASK"))
cl <- makeCluster(ncores)
# ... parallel work ...
stopCluster(cl)
```

### Big Memory Partition

For jobs requiring >128 GB RAM, HiPerGator has `bigmem` partition nodes. Contact RC support for access details and current node specifications.

---

## 9. Best Practices for Processing Large Files on HPC

### General Principles

1. **Work from `/blue` storage** — the only filesystem designed for job I/O
2. **Use Parquet instead of CSV** — columnar format is 5-10x smaller and 10-100x faster to read
3. **Profile before scaling** — test with a subset on an interactive session first
4. **Right-size resource requests** — check actual usage with `sacct`
5. **Don't load what you don't need** — select columns and filter rows at read time

### Chunking Strategies

#### Python (pandas)

```python
import pandas as pd

chunks = pd.read_csv("large_file.csv", chunksize=100_000)
results = []
for chunk in chunks:
    processed = chunk.query("state == 'FL'")
    results.append(processed)
final = pd.concat(results)
```

#### Python (DuckDB — better approach)

```python
import duckdb

# DuckDB reads directly from files, processes larger-than-RAM data
con = duckdb.connect()
result = con.sql("""
    SELECT col1, col2, SUM(amount)
    FROM read_csv_auto('large_file.csv')
    WHERE state = 'FL'
    GROUP BY col1, col2
""").df()
```

#### Python (Polars — best for DataFrames)

```python
import polars as pl

# Lazy evaluation: builds a query plan, executes only what's needed
df = (
    pl.scan_csv("large_file.csv")
    .filter(pl.col("state") == "FL")
    .select(["col1", "col2", "amount"])
    .group_by(["col1", "col2"])
    .agg(pl.col("amount").sum())
    .collect()
)
```

#### R (data.table)

```r
library(data.table)

# fread is already very fast and multi-threaded
dt <- fread("large_file.csv", select = c("col1", "col2", "state", "amount"))
result <- dt[state == "FL", .(total = sum(amount)), by = .(col1, col2)]
```

#### R (DuckDB)

```r
library(duckdb)
library(DBI)

con <- dbConnect(duckdb())
result <- dbGetQuery(con, "
    SELECT col1, col2, SUM(amount) as total
    FROM read_csv_auto('large_file.csv')
    WHERE state = 'FL'
    GROUP BY col1, col2
")
dbDisconnect(con, shutdown = TRUE)
```

### Parallel Processing Patterns

#### Processing Independent Files in Parallel (SLURM Array Jobs)

The simplest and most effective HPC parallelism: let SLURM manage it.

```bash
#!/bin/bash
#SBATCH --job-name=process_batch
#SBATCH --output=logs/batch_%A_%a.log
#SBATCH --array=1-50
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16gb
#SBATCH --time=02:00:00

module load conda
conda activate myenv

FILE=$(ls /blue/mygroup/data/input_*.csv | sed -n "${SLURM_ARRAY_TASK_ID}p")
python process_file.py "$FILE"
```

#### Within-Job Parallelism (Python multiprocessing)

```python
from multiprocessing import Pool
import os

def process_chunk(filename):
    # your processing logic
    return result

if __name__ == "__main__":
    ncpus = int(os.environ.get("SLURM_CPUS_PER_TASK", 1))
    files = [f"chunk_{i}.csv" for i in range(ncpus)]
    with Pool(ncpus) as pool:
        results = pool.map(process_chunk, files)
```

### Converting CSV to Parquet (Do This First)

If you're going to read the same large CSV multiple times, convert it to Parquet once:

```python
import duckdb
con = duckdb.connect()
con.sql("""
    COPY (SELECT * FROM read_csv_auto('large_file.csv'))
    TO 'large_file.parquet' (FORMAT PARQUET)
""")
```

Parquet benefits:
- **5-10x smaller** on disk (columnar compression)
- **10-100x faster** to read (only reads needed columns)
- **Type-preserving** (dates stay dates, integers stay integers)
- **Supported natively** by DuckDB, Polars, Arrow, pandas, R arrow

### Temporary Files and Scratch

```bash
# In your SLURM script, use $TMPDIR for temporary files
# This is fast local SSD on the compute node
export TMPDIR_JOB=$TMPDIR/my_job_$$
mkdir -p $TMPDIR_JOB

# Copy input data to local scratch for faster I/O
cp /blue/mygroup/data/input.csv $TMPDIR_JOB/

# Process using local scratch
python process.py --input $TMPDIR_JOB/input.csv --output $TMPDIR_JOB/output.parquet

# Copy results back to /blue
cp $TMPDIR_JOB/output.parquet /blue/mygroup/results/
```

---

## Quick Reference: Workflow Summary

### First-Time Setup

```bash
# 1. SSH into HiPerGator
ssh <gatorlink>@hpg.rc.ufl.edu

# 2. Set up conda
module load conda
conda config --show envs_dirs  # verify /blue is configured

# 3. Create your data processing environment
mamba create -n datawork python=3.11
conda activate datawork
mamba install -c conda-forge duckdb polars pyarrow pandas ipykernel
python -m ipykernel install --user --name datawork --display-name "Data Work"
```

### Daily Workflow

```bash
# Interactive exploration via Open OnDemand
# Go to https://ood.rc.ufl.edu → Jupyter or RStudio

# OR batch processing
cd /blue/<group>/<user>/project
sbatch run_analysis.sh
squeue -u $USER       # check status
sacct -j <id>         # check results after completion
```

---

## Sources

All findings verified against official UF Research Computing documentation:

| Source | URL | Confidence |
|--------|-----|-----------|
| UFRC Software Modules | https://docs.rc.ufl.edu/software | HIGH |
| Conda Environments | https://docs.rc.ufl.edu/software/conda_environments/ | HIGH |
| Conda Configuration | https://docs.rc.ufl.edu/software/conda_configuration | HIGH |
| SLURM Scheduler | https://docs.rc.ufl.edu/scheduler/ | HIGH |
| Sample SLURM Scripts | https://docs.rc.ufl.edu/scheduler/sample_job_scripts/ | HIGH |
| Storage Policies | https://rc.ufl.edu/documentation/policies/storage | HIGH |
| Open OnDemand | https://docs.rc.ufl.edu/interfaces/ood | HIGH |
| Jupyter via OOD | https://docs.rc.ufl.edu/interfaces/jupyter_ood | HIGH |
| SAS on HiPerGator | https://docs.rc.ufl.edu/software/apps/sas | HIGH |
| R on HiPerGator | https://docs.rc.ufl.edu/software/apps/r/usage | HIGH |
| QoS and Limits | https://docs.rc.ufl.edu/scheduler/qos_limits | HIGH |
| Data Management | https://docs.rc.ufl.edu/quickstart/data_management | HIGH |
| Gator-AIM HiPerGator Guide | https://gatoraim.com/docs/research/hipergator/ | MEDIUM |
| Weecology HiPerGator Reference | https://wiki.weecology.org/docs/computers-and-programming/hipergator-reference | MEDIUM |
| DuckDB Installation | https://duckdb.org/docs/stable/guides/python/install | HIGH |

---

## Gaps and Open Questions

- **Exact SAS version** currently available — run `module spider sas` on HiPerGator to confirm
- **Specific R versions** available — run `module spider R` to see current options
- **Group-specific blue/orange quotas** — varies by investment; check with `blue_quota` and `orange_quota`
- **DuckDB/Polars compilation issues** — pip wheels generally work fine in conda envs on HiPerGator's Linux nodes, but if issues arise, install via `mamba install -c conda-forge` instead
- **New Blue Storage Migration (Nov 2025 - Jan 2026)** — UF is migrating to a new Blue storage system; paths remain the same (`/blue/<group>`) but confirm with your group's migration status
