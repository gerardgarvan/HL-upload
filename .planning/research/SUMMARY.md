# Project Research Summary

**Project:** HL Data Loading and Cleaning Pipeline
**Study:** UFPTI 2405-HLX17A — "Insurance Inequities in Hodgkin Lymphoma Treatment and Survivorship in the Southeast"
**PI:** Raymond Mailhot | **IRB:** IRB202400721
**Domain:** Hodgkin Lymphoma / OneFlorida+ PCORnet CDM v6.1
**Researched:** 2026-02-27
**Confidence:** HIGH

---

## Executive Summary

This project builds the data loading and cleaning layer for the Hodgkin Lymphoma insurance inequities study (UFPTI 2405-HLX17A). It ingests 22 PCORnet CDM v6.1 CSV flat files from the OneFlorida+ Mailhot_V1 cohort (9,331 HL patients, ICD-10 C81\*/ICD-9 201\*, 2+ encounters on different dates, Jan 2012–Mar 2025) on UF's HiPerGator HPC cluster. Files use SAS DATE9. formatted strings (e.g., "01JAN2020"), not raw integer dates.

An existing `HL-EDA` project has already completed a full EDA pipeline (load→clean→characterize→visualize) using pandas+pyarrow. This project extends and refactors the loading/cleaning layers to: (1) convert CSVs to Parquet for 10-100x faster reads, (2) add Polars and DuckDB for speed, (3) deepen validation beyond EDA-level cleaning, and (4) produce standalone analysis-ready Parquet datasets.

The recommended approach adds **Polars and DuckDB** to the existing pandas+pyarrow stack. Polars handles fast CSV-to-Parquet conversion; DuckDB provides SQL capability (answering the question about SQL on HiPerGator); pandas remains for compatibility with existing HL-EDA code. The one-time CSV-to-Parquet conversion is the single highest-impact optimization.

The primary risks are: (1) **Partner data heterogeneity** — 15 partners with wildly different table availability (FLM is claims-only, VRT is death-only, 3 partners lack payer data critical for the insurance inequities study); (2) **HIPAA compliance** — OneFlorida+ LDS data contains PHI, requiring storage on `/blue` or `/orange` with small cell suppression (1–10); (3) **Tumor registry limitations** — only 3 of 15 partners (ORL, TMH, UFH) provide TUMOR_REGISTRY data, and it's stale, limiting staging-stratified analysis.

---

## Key Findings

### Recommended Stack

**See:** [TECH_RESEARCH.md](./TECH_RESEARCH.md) for full benchmarks and comparison tables.

**Existing stack (from HL-EDA):** python=3.11, pandas>=2.2, pyarrow>=18.0, matplotlib, seaborn, jinja2, tabulate, tomli. Conda env `hl-eda` on `/blue/erin.mobley-hl.bcu`.

**Add to existing stack:**

| Technology | Purpose | Why |
|-----------|---------|-----|
| **Polars** | CSV-to-Parquet conversion, fast loading | Fastest Python DataFrame library (~0.4s/500MB); lazy evaluation; auto-parallelizes |
| **DuckDB** | SQL queries on Parquet, cross-table joins | No-server SQL on HiPerGator; out-of-core capable; answers "does HiPerGator have SQL?" |

**Keep from HL-EDA (already installed):**

| Technology | Purpose | Why |
|-----------|---------|-----|
| **Pandas + PyArrow** | Downstream analysis, compatibility with HL-EDA code | Existing clean/characterize/visualize code uses pandas throughout |
| **PyArrow / Parquet** | Storage format after initial conversion | 5-10x compression; columnar reads; type-preserving |
| **Conda / Mamba** | Environment management on HiPerGator | Existing `hl-eda` env on `/blue` |

### Healthcare Data Context

**See:** [HEALTHCARE_DATA_RESEARCH.md](./HEALTHCARE_DATA_RESEARCH.md) for full PCORnet CDM table schemas and cleaning pipeline.

**Correction from initial research:** The cohort uses PCORnet CDM **v6.1** (not v7.0). The Mailhot_V1 extract contains **22 tables** for **9,331 HL patients** from **15 partners**. Data integrates EHR sources (UF Health, AdventHealth, NCH, etc.) with Florida Medicaid claims (FLM). The existing HL-EDA project has already implemented value set mapping, deduplication, and age masking for all 22 tables. Key characteristics:

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

### SAS Date Handling

**See:** [SAS_DATES_RESEARCH.md](./SAS_DATES_RESEARCH.md) for full conversion formulas, pitfall catalog, and validation functions.

**Correction from initial research:** The Mailhot_V1 CSV files use **SAS DATE9. formatted strings** (e.g., "01JAN2020", "15MAR2023"), **not** raw integer SAS dates. This was confirmed by examining the existing HL-EDA codebase, which parses dates using `pd.to_datetime(series, format="%d%b%Y")` in `masking.py`. Datetime columns use `%d%b%Y:%H:%M:%S` format.

The integer-to-date conversion formulas from the initial research are **not needed** for this cohort. The actual conversion is string parsing:

| Conversion | Python (pandas) | Polars |
|-----------|----------------|-------|
| SAS DATE9. → Date | `pd.to_datetime(col, format="%d%b%Y", errors="coerce")` | `pl.col("date").str.to_date("%d%b%Y")` |
| SAS DATETIME. → Datetime | `pd.to_datetime(col, format="%d%b%Y:%H:%M:%S", errors="coerce")` | `pl.col("dt").str.to_datetime("%d%b%Y:%H:%M:%S")` |

**Note:** TUMOR_REGISTRY tables may use different date formats (NAACCR standard is YYYYMMDD). Test separately.

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

### Critical Pitfalls (Revised for HL Study)

**Top 5 pitfalls for the Mailhot_V1 HL cohort:**

1. **Partner data heterogeneity (CRITICAL for insurance study)** — 15 partners with wildly different data availability. BND, UCI, UMI have **no PAYER_TYPE_PRIMARY** — the core variable for an insurance inequities study. FLM is claims-only (no labs, vitals, prescribing). VRT has death data only. CHP has no ENCOUNTERID in labs. **Prevention:** Report all analyses stratified by SOURCE; document which partners contribute to which analyses; do not pool across partners without accounting for availability.

2. **HIPAA violations from insecure data handling (CRITICAL)** — OneFlorida+ LDS data contains PHI (full dates, ZIP codes, pseudoidentified PATIDs). **Prevention:** Store exclusively on `/blue` or `/orange`; no local copies; suppress cell counts 1–10 in all outputs (existing `mask_small_cells` function from HL-EDA).

3. **ICD-9→ICD-10 mapping by specific partners (HIGH)** — AMS and UMI mapped all historical ICD-9 codes to ICD-10, meaning pre-2015 C81\* codes from these partners are actually converted 201\* codes. This inflates ICD-10 counts and breaks ICD version-date concordance checks. **Prevention:** Flag AMS/UMI records with `ICD_MAPPED=True`; exclude from concordance analysis; report separately.

4. **Tumor registry data severely limited (MODERATE)** — Only ORL (stale, Dec 2020), TMH (stale, Feb 2019), and UFH (May 2024) have TUMOR_REGISTRY data. Staging, histology, and NAACCR treatment data is unavailable for ~80% of the cohort. **Prevention:** Treat TR analysis as supplementary; do not make staging a required stratification variable.

5. **Age masking breaks temporal logic (MODERATE)** — Patients >89 have BIRTH_DATE=01JAN1900 and AGE_AT_DIAGNOSIS=200. Birth-before-event checks will flag these as violations; age calculations will produce impossible ages. **Prevention:** Check `BIRTH_DATE_MASKED` flag before temporal/age calculations; fold masked ages into 65+ band (existing HL-EDA approach).

---

## Implications for Roadmap

See `ROADMAP.md` for the full revised roadmap. Key changes from the initial generic roadmap:

1. **Phase 1 is much shorter** (0.5–1 day vs. 1–2 days) because the HL-EDA project already has a working conda env, SLURM templates, and HPC config. We extend rather than rebuild.

2. **Phase 2 uses string parsing, not epoch arithmetic** — SAS DATE9. strings ("01JAN2020"), not integer days since 1960. This simplifies conversion significantly.

3. **Phase 3 adds HL cohort verification** — confirm the 9,331 patients match the C81\*/201\* inclusion criteria at 2+ encounters. Uses CDM v6.1 (not v7.0).

4. **Phase 4 adds HL-specific validation** — ICD-9→ICD-10 partner exceptions (AMS, UMI), tumor registry NAACCR staging validation, HL-specific outcome code validation (from `concepts.py`), insurance variable completeness checks.

5. **Phase 5 adds partner harmonization** — flags for claims-only (FLM), death-only (VRT), ICD-mapped (AMS, UMI) partners. Extends HL-EDA dedup logic with flag columns instead of dropping records.

6. **Phase 6 creates HL-specific derived variables** — age at first HL diagnosis, HL subtype from C81.x, diagnosis-to-treatment interval, payer at diagnosis, insurance continuity. All stratified by partner.

**Total estimated effort: 10.5–16 working days** (~2.5–3.5 weeks), down from 13–20 days in the generic roadmap.

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

### Gaps Resolved by HL-EDA Analysis

- **File inventory:** All 22 CSVs are known from `datastructure.txt`. File sizes will be confirmed in Phase 2.
- **Date format:** SAS DATE9. strings confirmed (not integer dates). HL-EDA's `parse_sas_dates()` already handles this.
- **CDM version:** v6.1, confirmed from DatasetCoverPage.
- **HPC config:** SLURM account `erin.mobley-hl.bcu`, 64GB memory, 2hr time limit already tested in HL-EDA.
- **SQL availability:** DuckDB via conda resolves this.

### Remaining Gaps

- **Chemotherapy regimen codes:** Need RXNORM_CUI or NDC lists for ABVD, BEACOPP, and other HL regimens if treatment-specific analysis is in scope.
- **Study endpoints:** What specific insurance inequities are being measured? Time to treatment, treatment type, surveillance adherence, survival? This shapes Phase 6 derived variables.
- **Insurance category mapping:** How to group PAYER_TYPE_PRIMARY into analytically useful categories (private, Medicaid, Medicare, uninsured, other).
- **TUMOR_REGISTRY date formats:** May use NAACCR YYYYMMDD rather than SAS DATE9. — needs testing in Phase 2.

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
