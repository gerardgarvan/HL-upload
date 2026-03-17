# Architecture

**Analysis Date:** 2026-03-17

## Pattern Overview

**Overall:** Layered pipeline with distinct loading, validation, cleaning, and reporting phases. Data flows from raw CSV → Parquet (typed) → validated → flagged/harmonized → clean Parquet + derived patient-level + reports. Modular abstraction of constants and functions per data domain (cohort definitions, deduplication keys, validation rules, payer logic).

**Key Characteristics:**
- Phase-driven execution: each script is idempotent and independent (can re-run without artifact conflicts)
- Configuration-driven: single TOML file (`config/paths.toml`) with data_root, scratch_root, output dirs
- Polars-based (no pandas except outcomes CSV parsing), lazy evaluation for large datasets
- Domain-specific modules with reusable functions, e.g., flag-adding, date detection, completeness profiling
- Small-cell suppression (HIPAA) pervasive: counts 1-10 replaced with "-" across all reports
- Cohort definition immutable: 149 HL ICD codes (77 ICD-10 C81.xx + 72 ICD-9 201.xx) with dual format support (dotted + normalized)

## Layers

**Load Layer (`src/load/`):**
- Purpose: Parse manifest, load config, detect and convert CSV-to-Parquet with proper typing
- Location: `src/load/config.py`, `src/load/schema.py`, `src/load/convert.py`
- Contains: Path resolution, datastructure.txt parsing, date column auto-detection (DATE9_RE, DATETIME_RE, YYYYMMDD_RE patterns), Parquet write with snappy compression, inventory metadata
- Depends on: pathlib, tomllib, polars, regex patterns
- Used by: `scripts/convert_all.py` (entry point)

**Validate Layer (`src/validate/`):**
- Purpose: Structural integrity, schema comparison, cohort membership, value ranges, referential integrity
- Location: `src/validate/structural.py`, `src/validate/cohort.py`, `src/validate/values.py`
- Contains:
  - Structural: PATID/ENCOUNTERID key integrity, completeness profiling per partner, small-cell flagging, schema comparison vs. DatasetCoverPage
  - Cohort: HL ICD code matching (exact 149-code set, dual format), DX_TYPE validation, dual-date methods (direct match or encounter-based)
  - Values: vital ranges, lab reference ranges, date bounds, masked birth date handling, ICD-10 transition date (2015-10-01)
- Depends on: constant definitions, referential relationships (PATID_LINKED_TABLES, ENCOUNTER_LINKED_TABLES)
- Used by: `scripts/validate_all.py` (entry point)

**Clean Layer (`src/clean/`):**
- Purpose: Deduplication, cross-table consistency, partner/diagnosis/provider flagging, harmonization
- Location: `src/clean/dedup.py`, `src/clean/harmonize.py`, `src/clean/flags_diagnosis_provider.py`, `src/clean/outcomes_flags.py`
- Contains:
  - Dedup: composite-key duplicate detection (ID + date + code per table), cross-table demographic/temporal consistency checks, event-outside-encounter flagging
  - Harmonize: partner provenance flags (ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY), enrollment coverage checks
  - Diagnosis/Provider: HL flag (149-code match), survivorship flag (specific + prefix codes), oncology provider classification
  - Outcomes: modality code lookup from CSV, treatment flags (CHEMO, RADIATION, SCT)
- Depends on: validation constants, cohort definitions
- Used by: `scripts/clean_all.py` (entry point)

**Report Layer (`src/report/`):**
- Purpose: Patient-level summaries, quality metrics, insurance/payer analysis
- Location: `src/report/quality_report.py`, `src/report/encounter_payer_summary.py`, `src/report/site_table.py`
- Contains:
  - Quality: DQ aggregation, patient-level derived variables (demographics, treatment, outcomes), HL subtype mapping, cleaning decisions
  - Encounter/Payer: one-row-per-patient with payer-focused variables, effective payer logic (primary → secondary fallback), dual-eligible detection, payer at treatment windows, transition flags
  - Site: per-site HL summary tables, partner completeness, outcomes cross-tabs
- Depends on: all validation and clean layer constants
- Used by: `scripts/assemble_clean.py`, `scripts/build_insurance_summary.py`, `scripts/build_site_table.py` (entry points)

## Data Flow

**Phase 1: CSV-to-Parquet (convert_all.py):**
1. Load config from `config/paths.toml` → Paths object with data_root, scratch_root, parquet_dir
2. Parse `datastructure.txt` → list of 22 table filenames (with Mailhot_V1 suffix for LAB_RESULT)
3. For each CSV file:
   - Detect date columns: known set (BIRTH_DATE, DX_DATE, etc.) + regex heuristic for any _DATE/_DT
   - Sample first rows, try 3 formats (DATE9: 01JAN2020, DATETIME, YYYYMMDD: 20200101)
   - Read as Polars, cast detected cols to date, write Parquet with snappy compression
4. Write `file_inventory.csv` with per-table: row count, byte sizes, date columns found/converted, elapsed time

**Phase 2: Structural Validation (validate_all.py):**
1. Load all Parquet files from parquet_dir
2. Schema validation: compare columns vs. DatasetCoverPage expected
3. Key integrity: check PATID exists, ENCOUNTERID exists and links back, no orphaned events
4. Completeness profiling: per-partner, per-table, flag small cells (1-10 → "-" in report)
5. Cohort verification: filter DIAGNOSIS for 149 HL codes (dual format), count methods (A: direct date match, B: encounter-based)
6. Enrollment cross-check: verify HL patients have enrollment records
7. Write `structural_validation.md`, `completeness_by_partner.csv`, `cohort_summary.csv`

**Phase 3: Deduplication & Harmonization (clean_all.py):**
1. Load flagged Parquet files
2. For each table with dedup key:
   - Sort by ID + date + code, flag exact matches as IS_DUPLICATE (0/1)
3. Add consistency flags (_con_ prefix):
   - Demographic: birth date, gender consistency across records
   - Temporal: events within encounter date bounds, outside enrollment periods
   - Death: death records consistent with death flags
4. Add partner flags: ICD_MAPPED (AMS/UMI), CLAIMS_ONLY (FLM), DEATH_ONLY (VRT)
5. Add diagnosis flags to DIAGNOSIS: FLAG_HL_DX, FLAG_SURVIVORSHIP_DX
6. Add provider flags to PROVIDER: FLAG_CANCER_PROVIDER (oncology keywords)
7. Write flagged Parquet to intermediate location
8. Write `dedup_report.md` with per-table duplicate counts, small-cell suppression

**Phase 4: Assembly & Derived (assemble_clean.py):**
1. Load flagged Parquet
2. Copy to `parquet_clean/` with snappy compression
3. Build patient-level derived from multiple tables:
   - Demographics (first of DEMOGRAPHIC)
   - Treatment flags (CHEMO, RADIATION, SCT from Outcomes.csv code matching)
   - HL subtype (4th character of C81.xx)
   - Payer summaries (from ENCOUNTER + ENROLLMENT, effective payer logic)
   - Outcomes (readmission, survivorship flags)
4. Write `patient_level.parquet`
5. Write quality reports: `DATA_QUALITY_REPORT.md`, `CLEANING_DECISIONS.md`
6. Aggregate DQ metrics: small-cell suppressed counts per partner, per table

**Phase 5: Payer/Insurance (build_insurance_summary.py):**
1. Load `derived/encounter_payer_summary.parquet` (from Phase 4)
2. Build cross-tables and summaries:
   - Payer category distribution (Medicare, Medicaid, Dual, Private, Other, Unknown)
   - Payer at first DX, first/last treatment (30-day windows)
   - Dual-eligible flags and transitions
   - Treatment-cohort-specific tables (HAD_CHEMO, HAD_RADIATION, HAD_SCT)
3. Write CSVs and MD tables with _suppress() for small cells
4. Generate bar charts (PNG): payer at first DX, payer at first chemo (1-10 excluded)

**State Management:**
- Stateless scripts: each script reads fresh from config → parquet paths, no global state
- Intermediate artifacts: Parquet files in scratch_root/hl-clean/parquet act as contracts between phases
- Derived artifacts: patient_level.parquet, encounter_payer_summary.parquet in derived_dir for downstream analysis
- Reports: written to reports/ directory after each phase (not loaded back by scripts)

## Key Abstractions

**Cohort Definition (`src/validate/cohort.py`):**
- Purpose: Immutable HL ICD code set (149 codes) and matching logic
- Examples: `ICD10_HL_CODES`, `ICD9_HL_CODES`, `ALL_HL_NORMALIZED`
- Pattern: Exact-match set membership, dual-format handling (dotted: C81.10 vs. undotted: C8110), ICD version detection

**Deduplication Keys (`src/clean/dedup.py`):**
- Purpose: Composite key per table for exact-match duplicate detection
- Examples: `DEDUP_KEYS = {"DIAGNOSIS": ["ID", "DX_DATE", "DX"], "PROCEDURES": ["ID", "PX_DATE", "PX"], ...}`
- Pattern: Sort, group by key, count duplicates, mark first occurrence as 0, rest as 1

**Payer Logic (`src/report/encounter_payer_summary.py`):**
- Purpose: Effective payer selection (primary → secondary fallback) and categorization
- Pattern: Collapse PCORnet PAYER_TYPE_PRIMARY codes to readable categories, handle sentinel values (NI, UN, OT), detect dual-eligible (codes 14/141/142)
- Special: Payer at treatment = mode of valid payers in 30-day window around procedure date

**Small-Cell Suppression (`src/validate/structural.py`, threshold=10):**
- Purpose: HIPAA compliance across all reports
- Pattern: `_suppress(count)` → "-" if 1-10 else str(count); applied to all published CSVs/MDfiles
- Threshold: Configurable SMALL_CELL_THRESHOLD constant (default 10)

**Flag Naming Convention:**
- Dedup flags: `IS_DUPLICATE` (0/1, Int8)
- Clean flags: `FLAG_HL_DX`, `FLAG_SURVIVORSHIP_DX`, `FLAG_CANCER_PROVIDER` (0/1, Int8)
- Partner flags: `ICD_MAPPED`, `CLAIMS_ONLY`, `DEATH_ONLY` (0/1, Int8)
- Consistency flags: prefix `_con_` (e.g., `_con_outside_enrollment`, `_con_demo_inconsistent`)
- Treatment flags: `HAD_CHEMO`, `HAD_RADIATION`, `HAD_SCT` (0/1, Int8)

## Entry Points

**`scripts/convert_all.py`:**
- Location: `scripts/convert_all.py`
- Triggers: Manual invocation or HPC job submission
- Responsibilities: Load config, parse datastructure.txt, convert all CSVs to Parquet with date detection, write file_inventory.csv

**`scripts/validate_all.py`:**
- Location: `scripts/validate_all.py`
- Triggers: After convert_all.py
- Responsibilities: Schema validation, key integrity checks, cohort verification, completeness profiling, write structural_validation.md, cohort_summary.csv

**`scripts/clean_all.py`:**
- Location: `scripts/clean_all.py`
- Triggers: After validate_all.py
- Responsibilities: Deduplication, consistency flagging, partner/diagnosis/provider flagging, write flagged Parquet and dedup_report.md

**`scripts/assemble_clean.py`:**
- Location: `scripts/assemble_clean.py`
- Triggers: After clean_all.py
- Responsibilities: Copy to parquet_clean/, build patient_level.parquet, write quality reports and cleaning decisions

**`scripts/build_insurance_summary.py`:**
- Location: `scripts/build_insurance_summary.py`
- Triggers: After assemble_clean.py (requires encounter_payer_summary.parquet)
- Responsibilities: Build payer summary tables, cross-tabs, figures with small-cell suppression

## Error Handling

**Strategy:** Early validation (file existence, schema match), lazy errors logged not raised

**Patterns:**
- Missing files: log skip and continue (e.g., optional manifest entries)
- Schema mismatches: report in validation output but proceed (non-blocking)
- Small-cell data: suppress in report but retain in Parquet for re-use
- Date detection: fallback to string if all 3 formats fail, note in inventory
- Orphaned keys: flag in consistency output but don't exclude records

## Cross-Cutting Concerns

**Logging:** Print to stdout in main() functions with "=" headers per phase; scripts self-document progress

**Validation:** Pervasive constants for known columns, tables, code sets; raises FileNotFoundError only for truly missing inputs

**Authentication:** None (local file system only; suitable for HPC shared filesystem)

**Configuration:** Single TOML file with relative path resolution (rooted at project directory containing `config/`)

---

*Architecture analysis: 2026-03-17*
