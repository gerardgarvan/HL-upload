# Project Research Summary

**Project:** Healthcare Data Loading and Cleaning Pipeline
**Domain:** Healthcare / Biomedical Research Data Processing (PCORnet CDM / OneFlorida+)
**Researched:** 2026-02-27
**Confidence:** HIGH

---

## Executive Summary

This project involves loading, converting, and cleaning large healthcare CSV flat files exported from SAS — likely OneFlorida+ data in PCORnet CDM v7.0 format — on UF's HiPerGator HPC cluster. The data covers ~26 million patients with billions of clinical records (diagnoses, procedures, medications, labs, vitals). Files use SAS date encoding (integer days since 1960-01-01), which must be converted before any analysis. The environment is SLURM-scheduled Linux nodes with conda-based package management.

The recommended approach is a **Python-first pipeline using Polars for loading, with a one-time CSV-to-Parquet conversion** as the single highest-impact optimization. Polars provides top-tier loading speed (~0.4s for 500MB), lazy evaluation for selective reading, and multi-threaded processing that naturally exploits HiPerGator's multi-core nodes. DuckDB should be used alongside Polars for SQL-based exploratory queries and for processing files that exceed available RAM. After the initial load, all subsequent reads should use Parquet files (5-10x smaller, 10-100x faster). Pandas remains essential for downstream statistical modeling and visualization, but should not be the loading tool.

The primary risks are: (1) **SAS date/datetime confusion** — applying a days-since-epoch conversion to a seconds-since-epoch column produces catastrophically wrong dates, and this error is silent; (2) **HIPAA compliance** — OneFlorida+ data is a Limited Data Set containing PHI (full dates, ZIP codes), requiring secure storage on `/blue` or `/orange` with no local copies; (3) **data quality pitfalls inherent to PCORnet CDM** — missing values encoded as `NI`/`UN`/`OT` carry different semantics that are lost if treated uniformly, and cross-site variability means cleaning rules must account for inconsistent coding practices across health systems.

---

## Key Findings

### Recommended Stack

**See:** [TECH_RESEARCH.md](./TECH_RESEARCH.md) for full benchmarks and comparison tables.

Python is the primary language, with R available for specialized statistical work via HiPerGator's module system. All tools are installable via conda on HiPerGator with no special permissions.

**Core technologies:**

| Technology | Purpose | Why |
|-----------|---------|-----|
| **Polars** | Primary CSV/Parquet loading & transformation | Fastest Python DataFrame library (~0.4s/500MB); lazy evaluation via `scan_csv()`/`scan_parquet()` enables selective column/row reads; auto-parallelizes across cores |
| **DuckDB** | SQL queries on files, out-of-core processing | Queries files larger than RAM via streaming execution; SQL interface natural for data exploration; handles messy CSVs robustly; no server needed |
| **Pandas + PyArrow** | Downstream analysis & modeling interface | Required by scikit-learn, statsmodels, lifelines; use `engine='pyarrow', dtype_backend='pyarrow'` for fast loading when pandas DataFrame is the target |
| **PyArrow / Parquet** | Storage format after initial conversion | 5-10x compression; columnar reads; type-preserving; universal interchange format |
| **Conda / Mamba** | Environment management on HiPerGator | Isolated environments on `/blue` storage; mamba is faster; avoids global pip conflicts |

**When to use R instead:** If the team's statistical workflow requires R-native packages (survival analysis with `survival`, mixed models with `lme4`, visualization with `ggplot2`), use `data.table::fread()` for loading and `arrow` for Parquet I/O. `fread()` is competitive with Polars and superior for string-heavy data.

### Healthcare Data Context

**See:** [HEALTHCARE_DATA_RESEARCH.md](./HEALTHCARE_DATA_RESEARCH.md) for full PCORnet CDM table schemas and cleaning pipeline.

OneFlorida+ uses PCORnet CDM v7.0 with 24+ tables covering demographics, encounters, diagnoses, procedures, medications, labs, vitals, and death records. The data integrates EHR sources (UF Health, AdventHealth, others) with Florida Medicaid claims. Key characteristics:

**Must-have cleaning steps (table stakes):**
- SAS date conversion for all date columns (days since 1960-01-01)
- Schema validation against PCORnet CDM specification
- Primary/foreign key integrity checks (PATID across all tables, ENCOUNTERID linkage)
- Coded field validation (ENC_TYPE, DX_TYPE, PX_TYPE against CDM value sets)
- Date consistency checks (discharge ≥ admission, events after birth/before death)
- Missing value classification (distinguish `NI` / `UN` / `OT` / true NULL)

**Should-have cleaning steps (quality improvement):**
- Clinical code validation (ICD-10-CM format, NDC format, LOINC check digits)
- Vital signs and lab result plausibility ranges
- Duplicate detection (exact and near-duplicates, encounter fragmentation)
- Cross-table consistency (sex-diagnosis alignment, date-code version concordance)
- Data quality report generation (completeness, conformance, plausibility, persistence)

**Defer (study-specific, v2+):**
- Imputation strategies for missing data
- Advanced patient linkage via HASH_TOKEN
- Study-specific cohort definitions and analytic variable derivation
- Longitudinal consistency analysis across quarterly refreshes

### SAS Date Conversion

**See:** [SAS_DATES_RESEARCH.md](./SAS_DATES_RESEARCH.md) for full conversion formulas, pitfall catalog, and validation functions.

SAS dates are integers (days since 1960-01-01); SAS datetimes are real numbers (seconds since 1960-01-01). Modern healthcare dates fall in the range ~10,000–25,000 (days) or hundreds of millions to low billions (datetimes). The conversion is straightforward but has critical pitfalls:

| Conversion | Python (pandas) | R |
|-----------|----------------|---|
| SAS Date → Date | `pd.to_datetime(col, unit='D', origin='1960-01-01')` | `as.Date(col, origin="1960-01-01")` |
| SAS Datetime → Datetime | `pd.to_datetime(col, unit='s', origin='1960-01-01')` | `as.POSIXct(col, origin="1960-01-01", tz="UTC")` |

### HiPerGator Environment

**See:** [HIPERGATOR_RESEARCH.md](./HIPERGATOR_RESEARCH.md) for full SLURM reference, storage tiers, and resource sizing.

**Major constraints and guidance:**

| Constraint | Detail |
|-----------|--------|
| **Storage** | Work from `/blue/<group>` only; `/home` is 40GB and backed up (no PHI); `/orange` for archival |
| **Compute** | Never run on login nodes; use SLURM batch (`sbatch`) or interactive (`srun`) |
| **Resources** | Default is 1 core / 4GB / 10min — always set explicit `--cpus-per-task`, `--mem`, `--time` |
| **SQL** | No traditional SQL server (MySQL/MSSQL); SQLite via Python stdlib; DuckDB via conda install |
| **Conda** | Use `mamba` for speed; environments stored on `/blue`; never `pip install` outside conda env |
| **Interactive** | Open OnDemand (ood.rc.ufl.edu) for Jupyter/RStudio; allocates compute node automatically |
| **Multi-file** | SLURM array jobs for processing independent files in parallel |

### Critical Pitfalls

**Top 5 pitfalls distilled from all research:**

1. **SAS Date vs. Datetime confusion (CRITICAL)** — A datetime value of 1,893,456,000 treated as days produces year 5,185,000+. A date value of 22,000 treated as seconds gives 6 hours after midnight on 1960-01-01. **Prevention:** Check magnitude (dates <30,000; datetimes >100,000), check column name suffixes (`_DT` vs `_DTTM`), always spot-check converted values.

2. **HIPAA violations from insecure data handling (CRITICAL)** — OneFlorida+ LDS data contains PHI (full dates, ZIP codes, pseudoidentified PATIDs). Storing on `/home` (which is backed up and potentially accessible) or transferring to local machines violates the Data Use Agreement. **Prevention:** Store exclusively on `/blue` or `/orange`; no local copies; suppress cell counts < 11 in all outputs.

3. **Silent type inference failures on large CSVs (HIGH)** — Pandas samples only early rows for dtype inference. If early rows have missing dates (blanks), columns get classified as `object` or `float64`, causing downstream conversion failures or spurious decimal noise. **Prevention:** Explicitly specify dtypes when reading (`dtype={'ADMIT_DT': 'Float64'}`); use `errors='coerce'` on all date conversions.

4. **Conflating PCORnet missing value codes (MODERATE)** — `NI` (no information), `UN` (unknown), `OT` (other), and true NULL have different research implications. Treating them all as "missing" loses semantic meaning. **Prevention:** Preserve original codes in separate columns; document handling decisions; check `RAW_*` fields for `OT` values.

5. **Over-requesting HPC resources (MODERATE)** — Requesting 128GB memory for a job that uses 8GB wastes group allocation and delays scheduling. Conversely, under-requesting causes out-of-memory kills. **Prevention:** Test with a subset first; check actual usage with `sacct -j <id> --format=MaxRSS`; add 15-20% buffer; use Polars/DuckDB to reduce memory needs.

---

## Implications for Roadmap

Based on the combined research, the project decomposes into 6 phases with clear dependencies. The first three phases are sequential prerequisites; phases 4-5 can partially overlap; phase 6 depends on all prior phases.

### Phase 1: Environment Setup & Security

**Rationale:** Nothing else can proceed without a working compute environment and HIPAA-compliant storage configuration. This is the foundation.
**Delivers:** Reproducible conda environment on HiPerGator with all tools installed; verified secure storage paths; SLURM job templates.
**Stack elements:** Conda/Mamba, Python 3.11, Polars, DuckDB, PyArrow, Pandas, ipykernel
**Addresses:** HiPerGator constraints (storage, modules, conda config); HIPAA compliance (data placement on `/blue`)
**Avoids:** Pitfall #2 (HIPAA violations), Pitfall #5 (resource misallocation)

**Key tasks:**
- Create conda environment with full data stack
- Verify storage configuration (`/blue` paths, conda env location)
- Create SLURM job template scripts (batch and interactive)
- Register Jupyter kernel for Open OnDemand
- Document data access protocols and security requirements

### Phase 2: Data Intake & Format Conversion

**Rationale:** Raw CSV files with SAS dates are the input; Parquet files with proper date types are the intermediate format that makes everything else fast. This phase is the critical path bottleneck — all subsequent work depends on having properly converted data.
**Delivers:** Parquet versions of all input CSVs with SAS dates converted to proper date types; file inventory with row counts, column counts, and size.
**Stack elements:** Polars (`read_csv`, `write_parquet`), SAS date conversion formulas
**Addresses:** CSV-to-Parquet conversion (10-100x speedup for all future reads); SAS date/datetime detection and conversion
**Avoids:** Pitfall #1 (date/datetime confusion), Pitfall #3 (type inference failures)

**Key tasks:**
- Inventory all CSV files (map to PCORnet CDM tables)
- Detect which columns are SAS dates vs. SAS datetimes (magnitude check + column name heuristics)
- Convert SAS dates/datetimes to proper date types
- Run immediate validation (range checks, epoch-date detection, spot-check conversions)
- Write Parquet files with correct types
- Log conversion summary (files, rows, columns, date columns found, issues)

### Phase 3: Structural Validation

**Rationale:** Before checking values, verify the structural integrity of the data — are the right tables present, do the schemas match, are keys valid? This catches gross data delivery issues early.
**Delivers:** Structural validation report; confirmed PCORnet CDM version; key integrity assessment.
**Stack elements:** Polars/DuckDB for scanning Parquet files; PCORnet CDM v7.0 spec as reference
**Addresses:** Schema validation, primary/foreign key integrity, row-level completeness assessment
**Avoids:** Pitfall #4 (missing value code conflation — set up proper handling here)

**Key tasks:**
- Validate column names against PCORnet CDM spec
- Check HARVEST table for CDM version and date management strategy
- Verify PATID uniqueness in DEMOGRAPHIC; PATID presence across all tables
- Verify ENCOUNTERID referential integrity
- Calculate per-column completeness rates
- Classify missing value codes (NI/UN/OT/NULL) and document handling rules

### Phase 4: Value & Temporal Validation

**Rationale:** Now that structure is confirmed, validate the actual data values. This is the deepest and most domain-specific phase, requiring healthcare knowledge for plausibility ranges.
**Delivers:** Value validation report with flagged records; date consistency assessment; code validation results.
**Stack elements:** Polars for fast filtering/aggregation; pandas for validation function prototyping
**Addresses:** Coded field validation, clinical code format checks, vital signs and lab plausibility, date consistency rules, ICD version-date concordance
**Avoids:** Pitfall #1 (catches any remaining date conversion errors via range checks)

**Key tasks:**
- Validate PCORnet value sets (ENC_TYPE, DX_TYPE, PX_TYPE, SEX, RACE, etc.)
- Validate clinical code formats (ICD-10-CM, CPT/HCPCS, NDC, LOINC, RxNorm)
- Apply vital signs plausibility ranges
- Apply lab result plausibility ranges (LOINC-specific with unit awareness)
- Run full temporal validation suite (discharge ≥ admission, events within encounter windows, birth precedes all)
- Check ICD-9 vs ICD-10 date concordance (ICD-10 after Oct 1, 2015)

### Phase 5: Deduplication & Cross-Table Consistency

**Rationale:** Duplicates and cross-table inconsistencies require the validated data from Phase 4 as input. This phase resolves record-level issues.
**Delivers:** Deduplicated dataset with flags (no records deleted); cross-table consistency report.
**Stack elements:** Polars for hashing and groupby operations; DuckDB for cross-table SQL joins
**Addresses:** Exact and near-duplicate detection, encounter fragmentation, demographic consistency, encounter-event alignment

**Key tasks:**
- Detect exact duplicates per table (hash all non-ID columns)
- Detect near-duplicates using table-specific keys (e.g., PATID + ENCOUNTERID + DX + DX_TYPE for diagnoses)
- Check demographic consistency across encounters (single SEX, BIRTH_DATE per PATID)
- Verify encounter-event alignment (diagnosis/procedure dates within admission window)
- Flag, don't delete — add IS_DUPLICATE and consistency flag columns

### Phase 6: Data Quality Reporting & Analytic Dataset Preparation

**Rationale:** Consolidate all findings into a reproducible data quality report and prepare clean datasets for analysis. This is the deliverable phase.
**Delivers:** Comprehensive data quality report (completeness, conformance, plausibility, persistence); clean Parquet files with quality flags; analytic variable definitions.
**Stack elements:** Pandas for report generation; Polars for final Parquet output; matplotlib/seaborn for quality visualizations
**Addresses:** DQ reporting standards (Kahn framework / PCORnet four-dimension model); derived variable creation (age, LOS, time-to-event); small cell suppression

**Key tasks:**
- Generate completeness report (per-table, per-field)
- Generate conformance report (invalid code counts)
- Generate plausibility report (out-of-range value counts, distributions)
- Create derived analytic variables (age, length of stay, age groups)
- Apply cleaning rules (set implausible values to NULL with flag columns)
- Write final clean Parquet files
- Document all exclusion criteria and cleaning decisions

### Phase Ordering Rationale

- **Phases 1→2→3 are strictly sequential.** You cannot load data without an environment (Phase 1), cannot validate structure without loaded data (Phase 2→3).
- **Phase 4 depends on Phase 3** because structural validation may reveal schema issues (wrong CDM version, missing tables) that change how value validation works.
- **Phase 5 depends on Phase 4** because deduplication logic uses validated values (e.g., validated dates for temporal overlap detection).
- **Phase 6 depends on all prior phases** as it consolidates and reports on everything.
- **Parquet conversion in Phase 2 is the critical optimization** — it makes Phases 3-6 dramatically faster since all subsequent reads use Parquet instead of CSV.
- **HIPAA compliance spans all phases** but is configured in Phase 1 and enforced throughout.

### Research Flags

**Phases likely needing deeper research during planning:**
- **Phase 4 (Value & Temporal Validation):** Requires study-specific plausibility ranges and may need reference code set files (ICD-10-CM annual releases, LOINC database). The exact PCORnet CDM version and site-specific date management strategies (from HARVEST table) will shape validation rules.
- **Phase 6 (Reporting & Analytic Prep):** Study-specific analytic variable definitions depend on the research question. Small cell suppression rules and publication requirements need confirmation with OneFlorida+ data governance.

**Phases with standard patterns (skip deep research):**
- **Phase 1 (Environment Setup):** Well-documented HiPerGator procedures; conda environment creation is routine.
- **Phase 2 (Data Intake & Conversion):** SAS date conversion and CSV-to-Parquet are solved problems with verified code patterns from the research.
- **Phase 3 (Structural Validation):** PCORnet CDM spec is published and stable; key integrity checks are standard.
- **Phase 5 (Deduplication):** Established patterns for healthcare duplicate detection; PCORnet has documented common patterns.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack (Polars/DuckDB/Pandas) | **HIGH** | Multiple independent benchmarks agree; all tools verified on HiPerGator via conda |
| SAS Date Conversion | **HIGH** | Official SAS documentation; community-verified formulas; magnitude-based detection is reliable |
| PCORnet CDM Structure | **HIGH** | Official specification (v6.0/v7.0); OneFlorida+ confirmed as PCORnet CDM user |
| Healthcare Cleaning Pipeline | **HIGH** | Based on PCORnet's own curation framework (Kahn et al.) and peer-reviewed literature |
| HiPerGator Environment | **HIGH** | Official UF Research Computing documentation; storage/SLURM/conda details verified |
| Pitfall Catalog | **HIGH** | Synthesized from multiple domain-specific sources; date pitfalls verified with concrete examples |
| Parquet Performance Claims | **HIGH** | Verified across all tools (5-10x compression, 10-100x read speedup) |
| OneFlorida+ Data Scale | **MEDIUM** | Published figures (~26M patients) but exact file sizes/counts for this delivery unknown |
| HIPAA Storage Requirements | **MEDIUM** | Based on general UF policy; specific group storage paths and DUA terms need confirmation |

**Overall confidence:** HIGH

### Gaps to Address

- **Exact file inventory:** Which PCORnet CDM tables are included in the data delivery? File sizes and row counts are unknown until Phase 2.
- **SAS date vs. datetime per column:** Without a data dictionary or PROC CONTENTS output, date/datetime detection relies on magnitude heuristics and column name patterns. Request metadata from data provider if available.
- **HiPerGator group-specific quotas:** The `/blue` storage allocation and QoS limits depend on the research group's investment. Verify with `blue_quota` and `slurmInfo` commands.
- **CDM version:** The HARVEST table will confirm whether data is CDM v6.0 or v7.0, which affects which tables and fields exist.
- **Special missing values:** If the SAS source used `.A`–`.Z` special missing values, these are lost in CSV export. If missingness reasons matter for the study, request SAS7BDAT files or companion documentation.
- **SQL availability:** HiPerGator does not have MySQL/PostgreSQL as a service. DuckDB (installable via conda) provides full SQL capabilities as an embedded database — this fully resolves the user's question about SQL availability.

---

## Sources

### Primary (HIGH confidence)
- Official UF Research Computing documentation (docs.rc.ufl.edu) — HiPerGator storage, SLURM, conda, modules
- PCORnet CDM v7.0 Specification (pcornet.org) — Table schemas, value sets, data quality framework
- OneFlorida+ Clinical Research Network (onefloridaconsortium.org) — Data model, scale, governance
- SAS Official Documentation (support.sas.com) — Date/datetime value definitions, special missing values
- DuckDB Official Blog and Documentation — CSV performance benchmarks, out-of-core architecture

### Secondary (MEDIUM confidence)
- Hocking 2024 benchmark — Fair R-vs-Python CSV reader comparison
- Sean Ma 2024 — pandas PyArrow engine benchmarks
- Kahn et al. 2016 (EGEMS) — Harmonized data quality framework
- CMS CCW Medicare FFS Claims Codebook — Healthcare date field naming conventions
- PharmaSUG 2024 — Healthcare data cleaning practices

### Tertiary (needs validation at runtime)
- Specific Polars/DuckDB behavior on HiPerGator's filesystem — should be verified during Phase 1 setup
- OneFlorida+ small cell suppression threshold (< 11) — confirm with current DUA
- Blue storage migration status (Nov 2025–Jan 2026) — confirm paths still valid

---
*Research completed: 2026-02-27*
*Ready for roadmap: yes*
