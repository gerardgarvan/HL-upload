# HPC Upload Sync Strategy

**Reference:** [CONCERNS.md](../codebase/CONCERNS.md) — "Duplicate code paths: hpc-upload mirrors project; sync before runs"

## Overview

`hpc-upload/` is the deploy copy. It mirrors `scripts/`, `src/`, and `config/` from the project root. To avoid divergence:

1. **Sync before HPC runs** — copy updated code from project root into hpc-upload
2. **Do not edit hpc-upload directly** — edit project root; sync when ready to run on HPC
3. **Exclude outputs** — `hpc-upload/parquet` and `hpc-upload/logs` are output dirs; don't overwrite during sync

## Sync Commands

From project root (e.g. `Data loading and cleaing/`):

```bash
# Sync scripts, src, config (exclude parquet, logs, pycache)
rsync -av --exclude='parquet' --exclude='logs' --exclude='__pycache__' \
  scripts/ src/ config/ datastructure.txt valuesets.csv Outcomes.xlsx \
  hpc-upload/
```

Or copy specific dirs:

```bash
cp -r scripts hpc-upload/
cp -r src hpc-upload/
cp -r config hpc-upload/
cp datastructure.txt valuesets.csv Outcomes.xlsx hpc-upload/ 2>/dev/null || true
```

## Before HPC Submission

1. Run sync (above)
2. Copy `environment.yml` if dependencies changed
3. Submit job (e.g. `sbatch submit_job.sh` or `srun` for interactive)

## Files to Sync

| Source | Destination | Notes |
|--------|-------------|-------|
| scripts/ | hpc-upload/scripts/ | Entry points |
| src/ | hpc-upload/src/ | Modules |
| config/ | hpc-upload/config/ | paths.toml |
| datastructure.txt | hpc-upload/ | Table manifest |
| valuesets.csv | hpc-upload/ | Value sets |
| Outcomes.xlsx | hpc-upload/ | Phase 7 modality codes |
| environment.yml | hpc-upload/ | Optional, if deps changed |

## Do Not Overwrite

- `hpc-upload/parquet/` — Parquet outputs (large)
- `hpc-upload/logs/` — Job logs
