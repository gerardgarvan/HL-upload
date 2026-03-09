# Architecture

**Analysis Date:** 2026-03-09

## Pattern Overview

**Overall:** Sequential ETL pipeline (load → convert → validate → clean → report) with phase-gated outputs.

**Key Characteristics:**
- File-based: CSV → Parquet; no database
- Polars as primary engine; lazy evaluation for large tables
- Additive flags (no record deletion); all outputs HIPAA-aware (small-cell suppression)
- HPC-first: paths on `/orange` (source) and `/blue` (scratch/output)

## Layers

**Load:**
- Purpose: Ingest CSVs, convert dates, write Parquet
- Location: `src/load/`
- Contains: `config.py`, `convert.py`, `schema.py`
- Depends on: Polars, TOML, datastructure.txt
- Used by: `scripts/convert_all.py`, smoke test

**Validate:**
- Purpose: Schema, integrity, cohort, value set, temporal, tumor registry checks
- Location: `src/validate/`
- Contains: `structural.py`, `values.py`, `cohort.py`
- Depends on: Polars, valuesets.csv, DatasetCoverPage
- Used by: `scripts/validate_all.py`, `scripts/validate_values.py`

**Clean:**
- Purpose: Dedup, partner harmonization, consistency flags, modality flags
- Location: `src/clean/`
- Contains: `dedup.py`, `harmonize.py`, `outcomes_flags.py`
- Depends on: Polars, validate modules
- Used by: `scripts/clean_all.py`, `scripts/assemble_clean.py`

**Report:**
- Purpose: DQ aggregation, derived variables, cleaning decisions, reports
- Location: `src/report/`
- Contains: `quality_report.py`, `site_table.py`
- Depends on: Polars, validate, clean
- Used by: `scripts/assemble_clean.py`, `scripts/build_site_table.py`

## Data Flow

**Pipeline Flow (Phases 1–7):**

1. **Phase 1** — Environment + config; smoke test verifies Polars, DuckDB, paths
2. **Phase 2** — `convert_all.py` → CSV → Parquet (SAS dates converted)
3. **Phase 3** — `validate_all.py` → schema, integrity, completeness, cohort verification
4. **Phase 4** — `validate_values.py` → value set, plausibility, temporal, tumor registry
5. **Phase 5** — `clean_all.py` → dedup, partner flags, consistency flags
6. **Phase 6** — `assemble_clean.py` → parquet_clean, patient_level.parquet, DQ report, CLEANING_DECISIONS
7. **Phase 7** — `add_modality_flags()` (called from `assemble_clean.py`) → MODALITY_* columns in patient_level.parquet

**State Management:**
- Stateless per run; each script reads Parquet, writes outputs
- No in-memory state store; intermediate files are the source of truth

## Key Abstractions

**Paths:**
- `load_config()` → `Paths` dataclass (data_root, scratch_root, parquet_dir, valuesets_path, datastructure_path)
- `config/paths.toml` as source

**Table Map:**
- `{table_name: Path}` built from `parse_datastructure()` + parquet_dir
- Used across validate, clean, report scripts

**Flag Columns:**
- Validation: `_val_*` (e.g. `_val_code`, `_val_range`)
- Clean: `IS_DUPLICATE`, `ICD_MAPPED`, `CLAIMS_ONLY`, `DEATH_ONLY`, `_con_*`
- Modality: `MODALITY_SCT`, `MODALITY_MAMMO`, etc. (Phase 7)

**Small-Cell Suppression:**
- `flag_small_cell(value)` in `structural.py` — returns `f"{value} ⚠"` for 1–10, else `str(value)`
- `_suppress(value)` in scripts — returns `"-"` for 1–10
- SMALL_CELL_THRESHOLD = 10

## Entry Points

| Script | Purpose |
|--------|---------|
| `scripts/smoke_test.py` | Phase 1 verification |
| `scripts/convert_all.py` | Phase 2: CSV → Parquet |
| `scripts/validate_all.py` | Phase 3: structural + cohort |
| `scripts/validate_values.py` | Phase 4: value + temporal validation |
| `scripts/clean_all.py` | Phase 5: dedup + harmonization |
| `scripts/assemble_clean.py` | Phase 6 + 7: assemble, derived vars, modality flags, reports |
| `scripts/build_site_table.py` | Site-level summary table |
| `submit_job.sh` | SLURM batch wrapper (runs smoke_test) |

## Error Handling

**Strategy:** Fail fast; print traceback and exit(1).

**Patterns:**
- `convert_all.py`: stops on first table failure
- Scripts wrap `main()` in try/except, print error, `sys.exit(1)`
- No retries or graceful degradation

## Phase Dependencies (ROADMAP)

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7
```

- Phase 7 (modality flags) depends on Phase 6 (`patient_level.parquet`, `table_map`)
- `add_modality_flags()` is invoked inside `assemble_clean.py` after `build_patient_level_derived()`
- Modality flags integrate by scanning PROCEDURES.PX, LAB_RESULT_CM.LAB_LOINC, DIAGNOSIS.DX for Outcomes.xlsx codes

---

*Architecture analysis: 2026-03-09*
