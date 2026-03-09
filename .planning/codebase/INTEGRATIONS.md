# External Integrations

**Analysis Date:** 2026-03-09

## APIs & External Services

**None** — No external HTTP APIs or cloud services. All data is local/HPC filesystem.

## Data Storage

**File-based:**
- **Source:** OneFlorida+ PCORnet CDM v6.1 CSV files on `/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915`
- **Output:** Parquet on `/blue/erin.mobley-hl.bcu` (parquet, parquet_clean, derived, logs)
- No databases; Polars/DuckDB operate on files

**File Formats:**
- CSV (source) — 22 tables, SAS DATE9. date strings
- Parquet (derived) — snappy compression, typed date columns
- Excel (Outcomes.xlsx) — modality code mapping for Phase 7

## Authentication & Identity

**None** — No auth; HPC account via SLURM (`account=erin.mobley-hl.bcu`).

## Monitoring & Observability

**Error Tracking:**
- None — Exceptions printed to stdout; scripts exit with code 1 on failure

**Logs:**
- SLURM logs: `logs/hl-clean_%j.log` (from `submit_job.sh`)
- Scripts print progress to stdout

## CI/CD & Deployment

**Hosting:**
- UF HiPerGator HPC — scripts run interactively (`srun --pty bash`) or via SLURM batch

**CI Pipeline:**
- None — Manual runs; smoke test (`scripts/smoke_test.py`) used for verification

## Environment Configuration

**Required:**
- `config/paths.toml` — data_root, scratch_root, datastructure_path, valuesets_path, parquet_dir
- Conda env `hl-eda` activated

**Secrets:**
- None — No API keys or secrets; HIPAA data stays on HPC

## Data Sources

**OneFlorida+ PCORnet CDM v6.1:**
- Mailhot_V1 cohort, extracted Sept 15, 2025
- 22 tables: DEMOGRAPHIC, ENCOUNTER, DIAGNOSIS, PROCEDURES, LAB_RESULT_CM, PRESCRIBING, VITAL, ENROLLMENT, DEATH, DEATH_CAUSE, CONDITION, DISPENSING, MED_ADMIN, LDS_ADDRESS_HISTORY, IMMUNIZATION, OBS_CLIN, OBS_GEN, PRO_CM, PROVIDER, HARVEST, TUMOR_REGISTRY1/2/3
- `valuesets.csv` — 15,000+ rows, PCORnet code-to-label mappings
- `datastructure.txt` — file manifest
- `DatasetCoverPage_Mailhot_V1_*.txt` — expected column lists for schema validation

**Outcomes.xlsx (Phase 7):**
- Outcomes sheet — code-to-modality mapping (CPT, HCPCS, LOINC, ICD-10)
- Used for MODALITY_SCT, MODALITY_MAMMO, MODALITY_ECHO, etc. flags

## Webhooks & Callbacks

**None**

---

*Integration audit: 2026-03-09*
