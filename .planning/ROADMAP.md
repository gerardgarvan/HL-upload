# Project Roadmap: HL Data Loading & Cleaning Pipeline

**Study:** UFPTI 2405-HLX17A — "Insurance Inequities in Hodgkin Lymphoma Treatment and Survivorship in the Southeast"
**PI:** Raymond Mailhot | **IRB:** IRB202400721 | **Programmer:** Myra Smith
**Created:** 2026-02-27
**Data Source:** OneFlorida+ PCORnet CDM v6.1, Mailhot_V1 cohort (extracted Sept 15, 2025)
**Platform:** UF HiPerGator HPC
**Cohort:** 9,331 HL patients (ICD-10 C81\*, ICD-9 201\*), 2+ encounters on different dates, Jan 2012–Mar 2025

---

## Project Overview

This project builds the data loading and cleaning layer for the Hodgkin Lymphoma insurance inequities study. The pipeline ingests 22 PCORnet CDM v6.1 CSV flat files (with SAS date formats) from the OneFlorida+ Mailhot_V1 cohort, converts them to fast-reading Parquet format, applies HL-specific cleaning rules, and produces validated analysis-ready datasets.

**Relationship to HL-EDA:** The existing `HL-EDA` project completed a full EDA pipeline (load→clean→characterize→visualize). This project refactors and extends the **loading and cleaning layers** to:
- Convert CSVs to Parquet for 10-100x faster subsequent reads (HL-EDA re-reads CSVs every run)
- Add SAS date type conversion (HL-EDA parses SAS DATE9. strings but doesn't convert to proper date types)
- Deepen cleaning beyond EDA-level dedup/value-set mapping (add structural validation, temporal consistency, cross-table integrity)
- Produce a standalone cleaned dataset that any downstream analysis can consume without re-running the cleaning

**What carries over from HL-EDA (reuse, don't rebuild):**
- `valuesets.csv` (15,000+ rows of PCORnet code-to-label mappings)
- `datastructure.txt` (file manifest with all 22 table filenames)
- `config/paths.toml` (HPC paths: `/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915`, `/blue/erin.mobley-hl.bcu`)
- `environment.yml` (base conda environment — extend, don't replace)
- Dedup logic for DIAGNOSIS, PROCEDURES, LAB_RESULT_CM (same keys)
- Age masking logic (BIRTH_DATE=01JAN1900, AGE_AT_DIAGNOSIS=200)
- Small-cell suppression (counts 1–10 → "-")
- `concepts.py` outcome/lab code sets (CBC, echo, ECG, MUGA, PFT, liver function, TSH, stem cell transplant)
- Partner nuances from DatasetCoverPage (15 partners with varying table availability)

**Top-level success criteria:**
- All 22 CSV files converted to Parquet with SAS dates converted to proper date types
- Structural validation against PCORnet CDM v6.1 completed
- HL-specific cleaning applied (cohort verification, tumor registry integration, insurance variable validation)
- Data quality report produced, stratified by SOURCE (partner)
- Clean Parquet files usable by any downstream script without re-cleaning
- All data stays on `/blue` or `/orange` (HIPAA compliance)

---

## Requirements

| ID | Requirement | Deliverable |
|----|-------------|-------------|
| REQ-01 | Load 22 large CSV files as fast as possible | CSV-to-Parquet conversion using Polars; all subsequent reads use Parquet (10-100x faster) |
| REQ-02 | Convert SAS date formats to standard dates | SAS DATE9. string parsing (e.g., "01JAN2020") → proper datetime types in Parquet; validate ranges |
| REQ-03 | Clean data for HL insurance inequities analysis | HL-specific pipeline: cohort verification (C81\*/201\*), tumor registry staging, insurance/payer validation, partner-stratified quality report |
| REQ-04 | Run on HiPerGator HPC | Extend existing `hl-eda` conda env on `/blue`; reuse SLURM template (64GB, 2hr, `erin.mobley-hl.bcu` account) |
| REQ-05 | HIPAA-compliant data handling | Data on `/orange` (source, read-only) and `/blue` (derived); no local copies; small cell suppression (1–10) on all outputs |
| REQ-06 | Reusable cleaned output | Standalone Parquet files with flag columns and derived variables consumable by EDA, modeling, or reporting pipelines |

---

## Technology Stack

| Technology | Purpose | Notes |
|------------|---------|-------|
| **Polars** | CSV-to-Parquet conversion, fast loading | ~0.4s/500MB; lazy evaluation; add to existing conda env |
| **Pandas + PyArrow** | Downstream analysis (already in HL-EDA env) | Keep for compatibility with existing EDA code; use `engine='pyarrow'` |
| **DuckDB** | SQL queries on Parquet, cross-table joins | Out-of-core capable; add to conda env; answers "does HiPerGator have SQL?" |
| **PyArrow / Parquet** | Storage format after conversion | 5-10x compression; columnar reads; type-preserving |
| **Conda / Mamba** | Environment management | Extend existing `hl-eda` env; stored on `/blue/erin.mobley-hl.bcu` |

**Existing env to extend** (from `HL-EDA/environment.yml`):
```
python=3.11, pandas>=2.2, pyarrow>=18.0, matplotlib>=3.9, seaborn>=0.13, jinja2, tabulate, tomli
```
**Add:** `polars`, `duckdb`

---

## Data Inventory

### Source Files (22 CSVs on `/orange`)

All files follow naming pattern `TABLE_Mailhot_V1.csv` at:
`/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915/`

| Table | Key Variables | HL-Relevant? | Notes |
|-------|--------------|--------------|-------|
| DEMOGRAPHIC | ID, BIRTH_DATE, SEX, RACE, HISPANIC, ZIP_CODE | Core | Age masking: >89 → BIRTH_DATE=01JAN1900 |
| ENCOUNTER | ENCOUNTERID, ID, ADMIT_DATE, DISCHARGE_DATE, ENC_TYPE, PAYER_TYPE_PRIMARY | Core | **Insurance is the core research question** — PAYER missing for BND, UCI, UMI |
| DIAGNOSIS | ID, DX, DX_TYPE, DX_DATE | Core | HL cohort defined by C81\*/201\* at 2+ encounters |
| PROCEDURES | ID, PX, PX_TYPE, PX_DATE | Core | Stem cell transplant, cardiac/pulmonary monitoring |
| PRESCRIBING | ID, RXNORM_CUI, RX_ORDER_DATE | Core | Chemotherapy regimens |
| LAB_RESULT_CM | ID, LAB_LOINC, RESULT_NUM, SPECIMEN_DATE | Core | CBC, CRP, liver function, TSH |
| VITAL | ID, HT, WT, SYSTOLIC, DIASTOLIC, MEASURE_DATE | Core | Survivorship monitoring |
| ENROLLMENT | ID, ENR_START_DATE, ENR_END_DATE, ENR_BASIS | Core | Insurance coverage periods |
| DEATH | ID, DEATH_DATE, DEATH_SOURCE | Core | Survival analysis |
| DEATH_CAUSE | ID, DEATH_CAUSE, DEATH_CAUSE_CODE | Core | HL-specific mortality |
| TUMOR_REGISTRY1 | ~265 NAACCR vars: staging, histology, treatment dates, B_SYMPTOMS | **Critical for HL** | Only 3 partners have data (ORL, TMH, UFH); AJCC TNM staging |
| TUMOR_REGISTRY2 | ~120 NAACCR vars: staging summary, collaborative staging | **Critical for HL** | CS_SZ, CS_EXT, CS_NODES, CS_METS, SSF1-25 |
| TUMOR_REGISTRY3 | ~120 NAACCR vars: similar to TR2 | **Critical for HL** | Compact format |
| CONDITION | ID, CONDITION, CONDITION_TYPE, ONSET_DATE | Secondary | Comorbidities |
| DISPENSING | ID, NDC, DISPENSE_DATE | Secondary | Pharmacy dispensing records |
| MED_ADMIN | ID, MEDADMIN_CODE, MEDADMIN_START_DATE | Secondary | Inpatient medication administration |
| LDS_ADDRESS_HISTORY | ID, ADDRESS_STATE, ADDRESS_ZIP5 | Secondary | Geographic analysis (SE region focus) |
| IMMUNIZATION | ID, VX_CODE, VX_ADMIN_DATE | Secondary | Post-treatment vaccination |
| OBS_CLIN | ID, OBSCLIN_CODE, OBSCLIN_RESULT_NUM | Secondary | Clinical observations |
| OBS_GEN | ID, OBSGEN_CODE, OBSGEN_RESULT_NUM | Secondary | General observations |
| PRO_CM | ID, PRO_ITEM_NAME | Low priority | Patient-reported outcomes (most partners lack this) |
| PROVIDER | PROVIDERID, PROVIDER_SPECIALTY_PRIMARY | Low priority | Provider demographics |

### Partner Data Availability Matrix

15 partners with drastically different table availability. Key gaps for HL research:

| Partner | Dates | TUMOR | PAYER | LABS | VITALS | PRESCRIBING | Critical Notes |
|---------|-------|-------|-------|------|--------|-------------|----------------|
| AMS | May 2014–Jan 2025 | No | Yes | Partial (no CBC) | Yes | Yes | Mapped ICD-9→ICD-10 for all DX |
| AVH | Jan 2012–Feb 2025 | No | Yes | Yes | Yes | Yes | EHR conversion Jun 2022 |
| BND | Feb 2017–Mar 2025 | No | **No** | Yes | Yes | Yes | No MUGA/SCT procedures |
| CHP | Jan 2015–Jan 2025 | No | Yes | Yes (no ENCOUNTERID) | **No** | **No** | Many tables missing |
| EMY | Apr 2021–Feb 2025 | No | Yes | Partial (no CBC) | Yes | Yes | Short date range |
| FLM | Jan 2012–Nov 2024 | No | Yes | **No** | **No** | **No** | **Claims-only** |
| NCH | May 2012–Feb 2025 | No | Yes | Yes | Yes | Yes | No MUGA |
| ORL | Jan 2012–Feb 2025 | **Yes** (stale, Dec 2020) | Yes | Yes | Yes | Yes | Limited outpatient pre-2021 |
| TMH | Jan 2012–Feb 2025 | **Yes** (stale, Feb 2019) | Yes | Yes | Yes | Yes | — |
| UAB | Jan 2012–Feb 2025 | No | Yes | Partial (no CBC) | Yes | Yes | — |
| UCI | Nov 2017–Mar 2025 | No | **No** | Yes | Yes | Yes | No payer, no ZIP |
| UFH | Jan 2012–Feb 2025 | **Yes** (May 2024) | Yes | Yes | Yes | Yes | Most complete partner |
| UMI | Jan 2012–Feb 2025 | No | **No** | Yes | Yes | Yes | Mapped ICD-9→ICD-10 |
| USF | Jan 2012–Feb 2025 | No | Yes | Partial (no CBC) | Yes | Yes | — |
| VRT | Jan 2012–Mar 2025 | No | No | No | No | No | **Death data only** |

**Impact on study:** Insurance inequities research depends on PAYER_TYPE_PRIMARY — **BND, UCI, UMI have no payer data**. Tumor staging available only from **ORL, TMH, UFH** (and stale). This limits staging-stratified analysis to ~3 partners.

---

## Phase Breakdown

### Phase 1: Environment Extension & Data Staging

**Goal:** Extend the existing `hl-eda` conda environment with Polars and DuckDB; verify data paths; set up project structure that references HL-EDA shared assets.

**Success Criteria:**
- [ ] `polars` and `duckdb` added to existing `hl-eda` conda env (or a new `hl-clean` env extending it)
- [ ] Updated `environment.yml` exported and saved
- [ ] Project config references shared assets: `valuesets.csv`, `datastructure.txt`, `paths.toml` from HL-EDA
- [ ] Smoke test: load one CSV with Polars, convert SAS DATE9. dates, write Parquet, read back on `/blue`
- [ ] SLURM template created (reuse `erin.mobley-hl.bcu` account, 64GB, adjust time)
- [ ] Data paths verified: `/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915` accessible; `/blue` has space

**Dependencies:** None (first phase).

**Estimated Effort:** 0.5–1 day (most infrastructure already exists in HL-EDA)

**Key Tasks:**
1. Copy/symlink shared config from HL-EDA (paths.toml, datastructure.txt, valuesets.csv)
2. Extend conda env: `mamba install polars duckdb -c conda-forge`
3. Export: `mamba env export > environment.yml`
4. Create project directory structure on `/blue`
5. Create SLURM batch template (adapt from `HL-EDA/EDA/run_report.slurm`)
6. Smoke test with DEMOGRAPHIC table: load CSV → parse SAS dates → write Parquet → read back → verify dates

**Output Files:**
- `environment.yml` — updated conda env
- `config/paths.toml` — project path configuration (reference HL-EDA)
- `submit_job.sh` — SLURM batch template

**Plans:** 2 plans

Plans:
- [ ] 01-01-PLAN.md — Project scaffold, config, source modules, environment spec, SLURM template, and smoke test script
- [ ] 01-02-PLAN.md — HPC deployment automation and environment/smoke test verification

---

### Phase 2: CSV-to-Parquet Conversion with SAS Date Handling

**Goal:** Convert all 22 CSV files to Parquet with SAS dates properly typed, producing a complete file inventory.

**Success Criteria:**
- [ ] All 22 CSVs loaded and written as Parquet to `/blue`
- [ ] SAS DATE9. strings (e.g., "01JAN2020") parsed to proper date types — **not** integer SAS dates (this cohort uses DATE9. format strings, not raw integers)
- [ ] SAS datetime strings (e.g., "01JAN2020:14:30:00") parsed to datetime types
- [ ] Date columns identified by PCORnet CDM column naming convention (`*_DATE`, `BIRTH_DATE`, `ADMIT_DATE`, etc.)
- [ ] All converted dates validated: fall within Jan 1900 – Dec 2026 (flag outliers)
- [ ] Parquet row counts match source CSV row counts
- [ ] File inventory CSV produced with table name, CSV rows, Parquet size, date columns found
- [ ] Tumor Registry date columns handled (NAACCR date formats may differ from PCORnet)

**Dependencies:** Phase 1 (working environment with Polars).

**Estimated Effort:** 1–2 days

**Key Tasks:**
1. Load `datastructure.txt` to get file list (reuse `schema.parse_datastructure` from HL-EDA)
2. For each CSV, load with Polars: `pl.read_csv(path)`
3. Identify date columns using PCORnet CDM naming:
   - Standard date columns: `BIRTH_DATE`, `ADMIT_DATE`, `DISCHARGE_DATE`, `DX_DATE`, `PX_DATE`, `MEASURE_DATE`, `SPECIMEN_DATE`, `RESULT_DATE`, `RX_ORDER_DATE`, `RX_START_DATE`, `RX_END_DATE`, `DEATH_DATE`, `ONSET_DATE`, `REPORT_DATE`, `RESOLVE_DATE`, `DISPENSE_DATE`, `ENR_START_DATE`, `ENR_END_DATE`, `MEDADMIN_START_DATE`, `MEDADMIN_STOP_DATE`, `VX_RECORD_DATE`, `VX_ADMIN_DATE`, `VX_EXP_DATE`, `ADDRESS_PERIOD_START`, `ADDRESS_PERIOD_END`
   - Columns matching `*_DATE` or `*_DT` pattern
   - TUMOR_REGISTRY date columns: `DATE_OF_BIRTH`, `DATE_OF_DIAGNOSIS`, `CHEMO_START_DATE_SUMMARY`, `DT_RAD`, `DT_SURG`, `DT_CHEMO`, `MOST_DEFINITIVE_SURGERY_DATE`, `IMMUNO_START_DATE`, `HORMONE_START_DATE`, etc.
4. Parse SAS DATE9. format: use `pd.to_datetime(col, format="%d%b%Y", errors="coerce")` or Polars equivalent (existing `parse_sas_dates` from HL-EDA handles this)
5. Parse SAS datetime format: try `%d%b%Y:%H:%M:%S` as in HL-EDA's `masking.py`
6. Validate: assert dates in range [1900-01-01, 2026-12-31]; flag but keep outliers
7. Handle TUMOR_REGISTRY NAACCR dates (may use YYYYMMDD format rather than DATE9.)
8. Write Parquet with `zstd` compression
9. Verify round-trip row counts
10. Generate `file_inventory.csv`

**Important:** HL-EDA's `masking.py` already has `parse_sas_dates()` that handles DATE9. format. The dates in this cohort are **SAS DATE9. formatted strings** (like "01JAN2020"), **not** raw SAS integer dates. The original research incorrectly assumed integer dates — the actual conversion is string parsing, not epoch arithmetic.

**Risks:**
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| TUMOR_REGISTRY dates use different format than PCORnet tables | Medium | Medium | Test NAACCR date columns separately; may be YYYYMMDD or DATE9. |
| Mixed date formats within a column | Low | Medium | `parse_sas_dates` fallback chain handles this |
| Encoding issues in CSV (latin-1 vs utf-8) | Low | Low | HL-EDA reader already handles this with fallback |

**Output Files:**
- `data/parquet/*.parquet` — one per CDM table
- `file_inventory.csv` — table metadata
- `src/load/convert.py` — conversion script

**Plans:** 1 plan

Plans:
- [ ] 02-01-PLAN.md — CSV-to-Parquet conversion module and entry point (auto-detect dates, 3 format parsers, 10% threshold, inventory)

---

### Phase 3: Structural Validation & HL Cohort Verification

**Goal:** Validate table structure against PCORnet CDM v6.1, verify key integrity, and confirm the HL cohort definition.

**Success Criteria:**
- [ ] All table schemas validated against CDM v6.1 (columns present/missing/extra)
- [ ] PATID (column: `ID`) uniqueness verified in DEMOGRAPHIC
- [ ] PATID referential integrity across all tables (every `ID` in clinical tables exists in DEMOGRAPHIC)
- [ ] ENCOUNTERID referential integrity (every ENCOUNTERID in event tables exists in ENCOUNTER)
- [ ] **HL cohort confirmed:** 9,331 patients with C81\* or 201\* at 2+ encounters on different dates
- [ ] Per-column completeness rates calculated, stratified by SOURCE
- [ ] Missing value classification: NI/UN/OT/NULL distinguished and handling rules documented
- [ ] Partner data availability matrix validated against DatasetCoverPage

**Dependencies:** Phase 2 (Parquet files with proper date types).

**Estimated Effort:** 2–3 days

**Key Tasks:**
1. Load PCORnet CDM v6.1 expected column lists (from DatasetCoverPage variable lists)
2. Compare actual vs. expected columns per table
3. PATID (`ID`) integrity:
   - Verify `ID` is unique in DEMOGRAPHIC
   - For each clinical table, verify all `ID` values exist in DEMOGRAPHIC
   - Report orphaned IDs
4. ENCOUNTERID integrity:
   - Verify all ENCOUNTERIDs in DIAGNOSIS, PROCEDURES, LAB_RESULT_CM, VITAL, etc. exist in ENCOUNTER
   - **Known issue:** CHP has no ENCOUNTERID in LAB_RESULT_CM — handle gracefully
5. **HL cohort verification:**
   - Extract all DIAGNOSIS records where DX matches `C81%` (DX_TYPE=10) or `201%` (DX_TYPE=09)
   - Group by ID; count distinct DX_DATEs per patient
   - Verify ≥ 2 distinct dates per patient
   - Confirm 9,331 unique patients (or document discrepancy)
   - Flag patients with ICD-9 only vs. ICD-10 only vs. both
6. Completeness analysis:
   - Reuse HL-EDA's KEY_COLUMNS approach but expand to all columns
   - Stratify by SOURCE (partner)
   - **Highlight insurance variables:** PAYER_TYPE_PRIMARY completeness per partner (critical for study)
7. Missing value classification: scan for "NI", "UN", "OT", "", NaN per coded field
8. Generate structural validation report

**Output Files:**
- `reports/structural_validation.md` — schema match, key integrity, cohort verification
- `reports/completeness_by_partner.csv` — per-column completeness stratified by SOURCE
- `reports/cohort_summary.csv` — HL cohort breakdown (ICD version, partner, date range)
- `src/validate/structural.py` — validation script

**Plans:** 2 plans

Plans:
- [ ] 03-01-PLAN.md — Structural validation module (schema, integrity, completeness) + report framework
- [ ] 03-02-PLAN.md — HL cohort verification (149 ICD codes, dual-date methods, enrollment cross-check)

---

### Phase 4: HL-Specific Value & Temporal Validation

**Goal:** Validate data values against PCORnet CDM value sets and HL-specific clinical rules; verify temporal consistency.

**Success Criteria:**
- [ ] All PCORnet coded fields validated against CDM value sets (reuse `valuesets.csv` from HL-EDA)
- [ ] Clinical code format validation: ICD-10-CM (C81\* subcode structure), CPT, NDC, LOINC
- [ ] **ICD-9/ICD-10 concordance:** ICD-10 (C81\*) after Oct 1, 2015; ICD-9 (201\*) before — with exception for AMS, UMI who mapped ICD-9→ICD-10
- [ ] Vital signs plausibility: HT 50-250cm, WT 2-500kg, SBP 60-300, DBP 30-200
- [ ] Lab result plausibility for HL-relevant labs: CBC components, liver function, TSH, CRP
- [ ] Temporal consistency: DISCHARGE ≥ ADMIT, events after birth, events before death, no future dates
- [ ] **HL-specific date logic:** First HL diagnosis date → first treatment date sequence is plausible
- [ ] **Tumor registry validation:** AJCC staging values valid, treatment dates plausible, B-symptoms coded correctly
- [ ] **Insurance timeline:** ENR_START_DATE ≤ ENR_END_DATE; enrollment periods cover encounter dates
- [ ] Validation flags added as columns (not deletions)

**Dependencies:** Phase 3 (structural validation confirms schema and CDM version; cohort verified).

**Estimated Effort:** 3–4 days

**Key Tasks:**
1. Value set validation using `valuesets.csv` (reuse HL-EDA's mapper logic for reference lookup)
2. HL diagnosis code validation:
   - C81.0 (nodular LP), C81.1 (nodular sclerosis), C81.2 (mixed cellularity), C81.3 (lymphocyte depleted), C81.4 (lymphocyte rich), C81.7 (other), C81.9 (unspecified)
   - ICD-9 201.x subtypes
3. ICD version-date concordance (with partner exceptions):
   - General rule: DX_TYPE="10" should have DX_DATE ≥ 2015-10-01
   - **Exception:** AMS, UMI mapped all ICD-9→ICD-10, so pre-2015 C81\* codes are expected from these partners
4. HL outcome procedure/lab validation using `concepts.py` code sets:
   - Verify CBC, echo, ECG, MUGA, PFT, liver function, TSH, stem cell transplant codes match expected formats
5. Vital signs plausibility (reuse HL-EDA's `quality.py` ranges, expand)
6. Lab result plausibility for HL-relevant LOINC codes
7. Temporal consistency:
   - ENCOUNTER: DISCHARGE_DATE ≥ ADMIT_DATE
   - All clinical dates ≥ BIRTH_DATE (accounting for masked dates → skip if BIRTH_DATE_MASKED)
   - All clinical dates ≤ DEATH_DATE (when present)
   - No future dates (> 2025-03-31, the data extraction cutoff)
   - HL disease timeline: first DX_DATE → first treatment date is reasonable (0–365 days typical)
8. Tumor registry validation (TUMOR_REGISTRY1/2/3):
   - AJCC TNM stage values are valid (I-IV with substages)
   - Treatment dates are after diagnosis date
   - B_SYMPTOMS coded correctly (A=absent, B=present)
   - AGE_AT_DIAGNOSIS is plausible (0-100; 200=masked)
   - Histology codes correspond to HL (9650-9667 in ICDO3)
9. Insurance validation:
   - PAYER_TYPE_PRIMARY against CDM value sets
   - ENR_START_DATE ≤ ENR_END_DATE
   - Enrollment gaps flagged
10. Add validation flag columns: `_val_code`, `_val_range`, `_val_temporal`, `_val_notes`

**Risks:**
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Partner ICD-9→ICD-10 mapping makes concordance check noisy | High | Low | Exclude AMS, UMI from ICD version-date concordance; document |
| Tumor registry NAACCR coding varies across registries | Medium | Medium | Validate format but not exhaustive code sets; flag unusual values |
| Lab units vary across partners (same LOINC, different units) | High | Medium | Group by RESULT_UNIT before plausibility; flag missing units |
| Masked ages break birth-before-event checks | Medium | Low | Skip temporal checks when BIRTH_DATE_MASKED=True |

**Output Files:**
- `reports/value_validation.md` — per-table, per-check findings
- `reports/icd_concordance.csv` — ICD version vs. date analysis by partner
- `reports/temporal_issues.csv` — all temporal violations
- `reports/tumor_registry_validation.csv` — TR-specific findings
- `src/validate/values.py` — validation script

**Plans:** 2 plans

Plans:
- [ ] 04-01-PLAN.md — Core validation module (value set, plausibility, ICD concordance, temporal, tumor registry, insurance functions)
- [ ] 04-02-PLAN.md — Entry point script, cross-table temporal analysis, and 4-file report generation

---

### Phase 5: Deduplication, Cross-Table Consistency & Partner Harmonization

**Goal:** Detect duplicates, verify cross-table consistency, and harmonize partner-level differences; flag but don't delete.

**Success Criteria:**
- [ ] Exact and near-duplicates detected per table (reuse HL-EDA dedup keys, extend)
- [ ] Cross-table consistency verified: demographics match across tables, events fall within encounters
- [ ] **Partner harmonization:** ICD-9→ICD-10 mapping partners (AMS, UMI) flagged; claims-only partner (FLM) flagged
- [ ] **Insurance consistency:** Enrollment periods vs. encounter dates aligned
- [ ] All flags are additive columns — no records deleted
- [ ] Duplicate rates reported per table per partner

**Dependencies:** Phase 4 (validated values needed for meaningful dedup).

**Estimated Effort:** 2–3 days

**Key Tasks:**
1. Deduplication (extend HL-EDA `dedup.py`):
   - DIAGNOSIS: ID + DX_DATE + DX (same as HL-EDA)
   - PROCEDURES: ID + PX_DATE + PX (same as HL-EDA)
   - LAB_RESULT_CM: ID + SPECIMEN_DATE + LAB_LOINC (same as HL-EDA)
   - **New:** ENCOUNTER: ID + ADMIT_DATE + ENC_TYPE + FACILITYID (detect fragmented encounters)
   - **New:** VITAL: ID + MEASURE_DATE (detect same-day duplicates)
   - **New:** PRESCRIBING: ID + RX_ORDER_DATE + RXNORM_CUI
   - Add `IS_DUPLICATE` flag column (HL-EDA drops duplicates; this project flags them)
2. Cross-table consistency:
   - Single BIRTH_DATE and SEX per ID across DEMOGRAPHIC (and vs. TUMOR_REGISTRY)
   - Events within encounter admission-discharge window (±1 day tolerance)
   - DEATH_DATE consistency between DEATH table and TUMOR_REGISTRY
3. Partner harmonization:
   - Flag all records from AMS, UMI with `ICD_MAPPED=True` (they converted ICD-9→ICD-10)
   - Flag all FLM records with `CLAIMS_ONLY=True` (no clinical data)
   - Flag VRT records with `DEATH_ONLY=True`
   - Document partner-specific encounter type distributions (LNK = multi-source patient)
4. Insurance consistency:
   - Match ENROLLMENT periods to ENCOUNTER dates
   - Flag encounters outside enrollment windows
   - Flag patients with no enrollment but with encounters (coverage gap analysis)
5. Write flagged Parquet files

**Output Files:**
- `reports/dedup_report.md` — duplicate rates by table and partner
- `reports/consistency_report.md` — cross-table findings
- `reports/partner_harmonization.md` — partner-specific flags and notes
- `data/parquet_flagged/*.parquet` — Parquet files with flag columns
- `src/clean/dedup.py` — extended dedup script
- `src/clean/harmonize.py` — partner harmonization script

**Plans:** 2 plans

Plans:
- [ ] 05-01-PLAN.md — Core modules: dedup flagging (6 tables), cross-table consistency, partner harmonization flags, insurance enrollment coverage
- [ ] 05-02-PLAN.md — Entry point script and three markdown reports (dedup, consistency, partner harmonization)

---

### Phase 6: Data Quality Report & Clean Dataset Assembly

**Goal:** Produce a comprehensive data quality report and assemble final analysis-ready Parquet files with derived variables for the HL insurance inequities study.

**Success Criteria:**
- [ ] Data quality report covering all four dimensions: completeness, conformance, plausibility, persistence
- [ ] Report stratified by SOURCE (partner) — critical for understanding partner-level data gaps
- [ ] **HL-specific derived variables** created: age at first HL diagnosis, age bands (<21, 21-39, 40-64, 65+), HL subtype (from C81.x), time from diagnosis to first treatment
- [ ] **Insurance-specific derived variables:** payer category at HL diagnosis, insurance continuity flag, payer transitions
- [ ] Small cell suppression applied to all aggregate outputs (counts 1-10 → "-")
- [ ] Clean Parquet files written with all flags retained and derived variables added
- [ ] Cleaning decisions documented (what was flagged, what ranges were used, what was excluded)

**Dependencies:** Phases 1–5 completed.

**Estimated Effort:** 2–3 days

**Key Tasks:**
1. Aggregate quality metrics from Phases 3–5:
   - Completeness: per-field non-null rates, by partner (extend HL-EDA's `quality.py`)
   - Conformance: invalid code counts per coded field
   - Plausibility: out-of-range counts, temporal violations
   - Persistence: data volume over time by partner (detect drop-offs, coverage gaps)
2. Create HL-specific derived variables:
   - `AGE_AT_HL_DX`: age at first HL diagnosis date (from DEMOGRAPHIC.BIRTH_DATE and first C81\*/201\* DX_DATE); masked ages → fold into 65+ band (reuse HL-EDA logic)
   - `AGE_BAND`: <21, 21-39, 40-64, 65+ (same as HL-EDA)
   - `HL_SUBTYPE`: from C81.x 4th character (nodular LP, nodular sclerosis, mixed cellularity, etc.)
   - `FIRST_HL_DX_DATE`: earliest DX_DATE for C81\*/201\*
   - `FIRST_HL_TX_DATE`: earliest treatment date (from PROCEDURES/PRESCRIBING/TUMOR_REGISTRY)
   - `DX_TO_TX_DAYS`: FIRST_HL_TX_DATE - FIRST_HL_DX_DATE
   - `PAYER_AT_DX`: PAYER_TYPE_PRIMARY from encounter closest to first HL diagnosis
   - `INSURANCE_CONTINUITY`: flag for gaps in enrollment covering HL treatment period
   - `REGION`: Southeast vs. other from ADDRESS_STATE
3. Apply small cell suppression to all summary tables (reuse HL-EDA's `mask_small_cells`)
4. Write final clean Parquet files:
   - One per CDM table: `{TABLE}_clean.parquet`
   - Include all flag columns (dedup, validation, partner harmonization)
   - Include derived variables in a separate `derived/` directory
5. Generate final reports:
   - `DATA_QUALITY_REPORT.md` — comprehensive, by partner
   - `CLEANING_DECISIONS.md` — every rule, threshold, and rationale
   - Completeness heatmap (tables × partners)
   - Temporal coverage plot (patients and encounters over time, by partner)

**Output Files:**
- `reports/DATA_QUALITY_REPORT.md` — comprehensive DQ report
- `reports/CLEANING_DECISIONS.md` — all cleaning rules documented
- `reports/figures/` — quality visualizations
- `data/parquet_clean/*.parquet` — final analysis-ready datasets
- `data/derived/patient_level.parquet` — patient-level derived variables (age, subtype, insurance, region)
- `src/report/quality_report.py` — report generation script

---

## Risk Register

| # | Risk | Phase | Likelihood | Impact | Mitigation |
|---|------|-------|------------|--------|------------|
| R1 | **SAS DATE9. parsing fails on variant formats** — TUMOR_REGISTRY or NAACCR dates may use YYYYMMDD instead of DATE9. | 2 | Medium | High | Test each table's date format independently; `parse_sas_dates` fallback chain handles most cases |
| R2 | **HIPAA violation** — PHI leaves `/blue`/`/orange` or small cells not suppressed | All | Low | Critical | All data on HPC only; small cell function applied to every output; no patient-level exports |
| R3 | **Payer data missing for 3 partners** — BND, UCI, UMI have no PAYER_TYPE_PRIMARY | 3, 6 | Certain | High | Document completeness gap; derive insurance from ENROLLMENT.ENR_BASIS where available; report findings with partner-level caveats |
| R4 | **Tumor registry only from 3/15 partners** — staging analysis severely limited | 3, 4 | Certain | Medium | Report TR availability upfront; staging analysis is supplementary, not primary (insurance is primary) |
| R5 | **ICD-9→ICD-10 mapping by AMS/UMI inflates ICD-10 counts pre-2015** | 4 | Certain | Medium | Flag mapped records; exclude from ICD version-date concordance; report separately |
| R6 | **Partner FLM is claims-only** — no labs, vitals, prescribing, or clinical detail | 3, 5 | Certain | Medium | Flag FLM records; include in insurance/encounter analysis but exclude from clinical outcomes |
| R7 | **CHP has no ENCOUNTERID in LAB_RESULT_CM** | 3 | Certain | Low | Skip encounter linkage for CHP labs; join on ID + date instead |
| R8 | **Over-cleaning removes valid HL data** — aggressive plausibility filters on chemo-related labs | 4 | Medium | High | Flag, don't delete; chemo patients have expected extreme lab values; document |
| R9 | **Age masking obscures age distribution** — patients >89 masked to 01JAN1900 | 2, 6 | Certain | Low | Use HL-EDA's masking flag approach; fold into 65+ age band |
| R10 | **Files too large for memory** — some tables may exceed 64GB | 2 | Low | Medium | Use Polars streaming or DuckDB; increase SLURM memory allocation |

---

## Open Questions

1. **Is this project meant to replace HL-EDA's clean layer, or produce a separate cleaned dataset?** Current assumption: separate, standalone cleaned Parquet files that any downstream analysis can consume.

2. **Should we use the existing `hl-eda` conda env or create a new one?** Extending the existing env is simpler; a new env avoids conflicts.

3. **Are there specific chemotherapy regimens to track?** ABVD, BEACOPP, and other HL-specific regimens need RXNORM_CUI or NDC code lists if we want to identify them programmatically.

4. **What are the study's primary vs. secondary endpoints?** Insurance inequities in what specifically — time to treatment, treatment choice, survival, surveillance adherence? This determines which derived variables are essential.

5. **Should tumor registry integration (NAACCR staging) be included in v1 or deferred?** HL-EDA deferred this to v2. Only 3 partners have TR data, and the data is stale.

6. **What insurance categories matter?** Private, Medicaid, Medicare, uninsured, other? Need category mapping for PAYER_TYPE_PRIMARY values.

7. **Is geographic analysis (Southeast region) in scope?** If yes, need state/county mapping from LDS_ADDRESS_HISTORY and RUCA/ADI codes.

8. **Are there specific time windows for survivorship outcome monitoring?** E.g., cardiac monitoring within 1 year of treatment, thyroid function at 5 years — these define the outcome feasibility analysis.

9. **Is radiation therapy data needed?** The Tumor Registry has DT_RAD and radiation codes, but PROCEDURES may also capture this via CPT/ICD-10-PCS.

10. **What is the deadline?** Determines how much of Phase 4-6 can be completed in v1 vs. deferred.

---

## Phase Dependencies

```
Phase 1: Environment Extension & Data Staging
    │
    ▼
Phase 2: CSV-to-Parquet Conversion with SAS Date Handling
    │
    ▼
Phase 3: Structural Validation & HL Cohort Verification
    │
    ▼
Phase 4: HL-Specific Value & Temporal Validation
    │
    ▼
Phase 5: Deduplication, Cross-Table Consistency & Partner Harmonization
    │
    ▼
Phase 6: Data Quality Report & Clean Dataset Assembly
```

**All phases are sequential.** Each depends on outputs of the previous phase.

**Critical path:** Phase 2 (CSV-to-Parquet) is the single biggest performance win — it makes everything after 10-100x faster.

---

## Estimated Total Effort

| Phase | Effort | Cumulative |
|-------|--------|------------|
| 1. Environment Extension & Data Staging | 0.5–1 day | 0.5–1 day |
| 2. CSV-to-Parquet Conversion | 1–2 days | 1.5–3 days |
| 3. Structural Validation & HL Cohort Verification | 2–3 days | 3.5–6 days |
| 4. HL-Specific Value & Temporal Validation | 3–4 days | 6.5–10 days |
| 5. Deduplication & Partner Harmonization | 2–3 days | 8.5–13 days |
| 6. Data Quality Report & Clean Dataset Assembly | 2–3 days | 10.5–16 days |
| **Total** | **10.5–16 working days** | ~2.5–3.5 weeks |

Faster than the generic roadmap because Phase 1 reuses existing infrastructure and existing HL-EDA code accelerates every subsequent phase.

---

*Roadmap created: 2026-02-27*
*Based on: HL-EDA project analysis + .planning/research/*
*Ready for phase planning: yes*
