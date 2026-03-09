# Technology Stack

**Analysis Date:** 2026-03-09

## Languages

**Primary:**
- Python 3.11 — All source code in `src/`, scripts in `scripts/`

**Secondary:**
- Bash — `submit_job.sh` (SLURM batch script)

## Runtime

**Environment:**
- Conda (`hl-eda`) — managed via `environment.yml`
- Target platform: UF HiPerGator HPC

**Package Manager:**
- Conda/Mamba (conda-forge, defaults)
- Lockfile: DRAFT spec; run `mamba env export --no-builds > environment.yml` on HPC to capture resolved versions

## Frameworks

**Core:**
- Polars — CSV load, Parquet I/O, DataFrame operations, lazy evaluation (primary data engine)
- PyArrow — Parquet storage, type-preserving reads
- Pandas — Used in `src/clean/outcomes_flags.py` for Excel (Outcomes.xlsx) parsing via `pd.read_excel`

**Testing:**
- Smoke test only — `scripts/smoke_test.py` (manual run; no pytest)
- No formal test framework

**Build/Dev:**
- Not used — No build step; scripts run directly

## Key Dependencies

**Critical:**
- **polars** — All load/convert (`src/load/convert.py`), validate, clean, report logic; lazy scans for large tables
- **pyarrow** — Parquet read/write; pandas uses `engine='pyarrow'` for Parquet
- **duckdb** — Verified in smoke test for Parquet read (out-of-core SQL capability)
- **pandas** — Excel read in `outcomes_flags.py`
- **openpyxl** (implied) — Required for `pd.read_excel` on `.xlsx`

**Infrastructure:**
- **jinja2** — Template rendering (if used in reporting)
- **tabulate** — Table formatting

## Configuration

**Environment:**
- `config/paths.toml` — TOML config for data_root, scratch_root, parquet_dir, valuesets_path, datastructure_path
- Paths: `/orange/erin.mobley-hl.bcu/` (source), `/blue/erin.mobley-hl.bcu` (output)
- Optional config path via CLI: `python scripts/convert_all.py [config/paths.toml]`

**Build:**
- Not applicable — No build step

## Config Formats

- **TOML** — `config/paths.toml` for paths; `tomllib`/`tomli` for loading
- **CSV** — `valuesets.csv` (PCORnet value sets), `file_inventory.csv`, `completeness_by_partner.csv`, etc.
- **Excel** — `Outcomes.xlsx` (Outcomes sheet for modality code mapping)
- **TXT** — `datastructure.txt` (table manifest), `DatasetCoverPage*.txt` (schema reference)

## Platform Requirements

**Development:**
- Python 3.11+, Conda, Polars, DuckDB, Pandas, PyArrow, openpyxl
- Access to `/orange` and `/blue` on HiPerGator (or staged local subset with edited `paths.toml`)

**Production:**
- UF HiPerGator HPC — SLURM, 64GB RAM, 2hr, `erin.mobley-hl.bcu` account

---

*Stack analysis: 2026-03-09*
