# Codebase Concerns

**Analysis Date:** 2026-03-09

## Tech Debt

**Datastructure filename mismatch:** **Resolved (Phase 8):** `FILENAME_TO_TABLE_ALIAS` and `resolve_table_name()` in `schema.py` map LAB_RESULT → LAB_RESULT_CM.
- `datastructure.txt` lists `LAB_RESULT_Mailhot_V1.csv` but ROADMAP and code expect `LAB_RESULT_CM`. Verify actual file names on HPC.
- Files: `datastructure.txt`, `src/load/schema.py`

**Duplicate code paths:**
- `hpc-upload/` mirrors `scripts/`, `src/` — risk of divergence if only one tree is updated.
- Mitigation: Treat `hpc-upload` as deploy copy; sync before runs.

**config.paths.toml parquet_dir:** **Resolved (Phase 8):** PATH_RESOLUTION.md documents `parquet_dir = scratch_root / parquet_rel`; config comments clarify resolution.
- `config/paths.toml` uses `parquet_dir = "hpc-upload/parquet"` relative to project; ROADMAP mentions `scratch_root / hl-clean/parquet`. Verify resolution for HPC runs.
- Files: `config/paths.toml`, `src/load/config.py`

## Data Paths

**Orange vs Blue HPC:**
- Source: `/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915` (read-only)
- Output: `/blue/erin.mobley-hl.bcu` (scratch, derived)
- Risk: Local dev uses different roots; `paths.toml` must be edited for staged subsets.
- Files: `config/paths.toml`, `hpc-upload/config/paths.toml`

**Path resolution:** **Resolved (Phase 8):** See .planning/docs/PATH_RESOLUTION.md.
- `parquet_dir` is `scratch_root / parquet_rel`; `parquet_rel` from `output.parquet_dir` defaults to `hl-clean/parquet` if absent.
- Config uses `hpc-upload/parquet` — may not match HPC layout.

## Cohort Definition

**HL cohort:**
- Definition: 9,331 patients with C81*/201* at 2+ encounters on different dates.
- Implementation: 149 exact ICD codes (77 ICD-10 + 72 ICD-9); Method A (2+ DX_DATEs) and Method B (2+ ADMIT_DATEs); union used.
- Risk: Actual union count may differ from 9,331; ROADMAP documents this as expected discrepancy to investigate.
- AMS/UMI: ICD-9→ICD-10 mapping inflates ICD10 counts pre-2015; flagged via `ICD_MAPPED`.

**Files:** `src/validate/cohort.py`, `scripts/validate_all.py`

## PCORnet CDM Tables

**Partner availability:**
- 15 partners with different table availability. BND, UCI, UMI lack PAYER_TYPE_PRIMARY.
- TUMOR_REGISTRY only from ORL, TMH, UFH (and stale).
- CHP: no ENCOUNTERID in LAB_RESULT_CM — handled via `skip_partner="CHP"` in encounter integrity checks.
- VRT: death data only; FLM: claims-only.

**Tumor Registry:**
- TR1/2/3 expected column counts (~265, 120, 120); schema validation warns if diff > 10.
- NAACCR date formats may vary (DATE9, YYYYMMDD, MM/DD/YYYY) — `dedup.py` uses fallback parsing.

**Files:** `src/validate/structural.py`, `src/validate/cohort.py`, `src/clean/dedup.py`

## Security Considerations

**HIPAA:**
- Data must stay on `/blue` and `/orange`; no local patient-level exports.
- Small-cell suppression: counts 1–10 → "-" or "N ⚠" in reports. **Resolved (Phase 8):** Audit complete; all report paths use `flag_small_cell` or `_suppress`.
- `flag_small_cell` and `_suppress` used; ensure every report path applies one of them.

**Files:** `src/validate/structural.py`, `scripts/assemble_clean.py`, `scripts/clean_all.py`, `scripts/validate_all.py`, `scripts/validate_values.py`

## Performance Bottlenecks

**Large tables:**
- Polars lazy evaluation used for scans; `pl.scan_parquet` where possible.
- Some paths still `.collect()` eagerly; review for tables >1GB.
- ROADMAP: If files exceed 64GB, consider Polars streaming or DuckDB.

**Files:** `src/validate/cohort.py`, `src/validate/values.py`, `src/clean/outcomes_flags.py`

## Fragile Areas

**Date parsing:** **Resolved (Phase 9):** See .planning/docs/DATE_PARSING_FALLBACKS.md.
- SAS DATE9., datetime, YYYYMMDD detected by sampling; >10% parse failure → column kept as string.
- TUMOR_REGISTRY dates may use different formats — `dedup.py` and convert logic handle multiple formats.

**Outcomes.xlsx:** **Resolved (Phase 9):** See .planning/docs/OUTCOMES_XLSX_SCHEMA.md.
- Phase 7 modality mapping depends on Outcomes sheet structure (Modality, Code system, Code).
- Forward-fill for Modality and Code system; changes to Excel layout could break `load_outcomes_code_lookup`.

**Files:** `src/load/convert.py`, `src/clean/outcomes_flags.py`, `src/clean/dedup.py`

## Modality Flags (Phase 7)

**Integration:**
- `add_modality_flags()` called from `assemble_clean.py` after `build_patient_level_derived()`.
- Requires Outcomes.xlsx at project root; skipped if missing.
- Scans PROCEDURES, LAB_RESULT_CM, DIAGNOSIS; adds MODALITY_SCT, MODALITY_MAMMO, etc. to patient_level.parquet.

**Risk:**
- Excel format changes; code normalization (uppercase, strip dots) must match Outcomes codes.

**Files:** `src/clean/outcomes_flags.py`, `scripts/assemble_clean.py`, `reports/modality_flags.md`

## Test Coverage Gaps

**Resolved (Phase 9):** pytest suite in `tests/` covers `flag_small_cell`, `_suppress`, `load_outcomes_code_lookup`, `validate_table_schema`, `check_patid_integrity`, `verify_hl_cohort`, `add_modality_flags`.

**Untested (remaining):**
- `convert_table`, date detection/conversion edge cases
- `validate_table_schema`, `check_patid_integrity`, `verify_hl_cohort`
- `flag_duplicates`, `add_partner_flags`, `add_modality_flags`
- `flag_small_cell` boundary (0, 1, 10, 11)

**Priority:** Medium — smoke test covers critical path; unit tests would reduce regression risk.

## Dependencies at Risk

**pandas for Excel:** **Resolved (Phase 8):** openpyxl added to environment.yml.
- `outcomes_flags.py` uses `pd.read_excel`; requires openpyxl. Not listed in `environment.yml` pip section.
- Add `openpyxl` to environment if missing.

**Files:** `src/clean/outcomes_flags.py`, `environment.yml`

## Missing Critical Features

**Automated tests:** **Resolved (Phase 9):** pytest suite in `tests/` (15 tests).
- No pytest suite; only smoke test.

**Linting/formatting:** **Resolved (Phase 9):** ruff + pyproject.toml configured.
- No ruff, black, or pyproject.toml for consistency.

**Incremental convert:** **Resolved (Phase 9):** convert_all.py skips when Parquet exists and CSV mtime ≤ Parquet mtime.
- `convert_all.py` reconverts all tables; no skip-existing for unchanged CSVs.

---

*Concerns audit: 2026-03-09*
