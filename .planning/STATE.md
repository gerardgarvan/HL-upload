# Project State

## Current Position
- **Current Phase:** 04
- **Current Plan:** Not started
- **Status:** Milestone complete
- **Last session:** 2026-02-28T00:00:00Z
- **Stopped at:** Completed 04-02-PLAN.md (entry point script and report generation with pre-transition ICD-10 concordance)

## Progress

```
Phase 1: ████░░░░░░░░░░░░░░░░ 1/2 plans (50%)
Phase 2: ████████████████████ 1/1 plans (100%)
Phase 3: ████████████████████ 2/2 plans (100%)
Phase 4: ████████████████████ 2/2 plans (100%)
Overall: ████████████████████ 6/7 plans
```

## Decisions
- Extended Paths dataclass with parquet_dir field; output section optional with sensible default
- Copied schema.py directly from HL-EDA without modification
- SLURM template uses 4 CPUs (up from 2) for Polars auto-parallelization
- environment.yml is a draft spec; real export generated on HPC after mamba install
- Single unified loop for all 22 tables; auto-detection handles TUMOR_REGISTRY format differences
- Three date formats: SAS DATE9. (%d%b%Y), SAS DATETIME (%d%b%Y:%H:%M:%S), NAACCR YYYYMMDD (%Y%m%d)
- No .str.to_uppercase() before %b parsing — chrono is case-insensitive
- encoding=utf8-lossy for CSV reads to handle non-UTF-8 characters
- DatasetCoverPage parser is format-adaptive with BOM handling; probes for table name section markers at runtime
- TUMOR_REGISTRY tables get column-count validation only (NAACCR, not PCORnet CDM)
- CHP LAB_RESULT_CM ENCOUNTERID exception via skip_partner parameter
- Partner column fallback: SOURCE → SITE → overall completeness
- Missing value classifier counts NI/UN/OT/empty/null per string column
- Per-table completeness heatmap capped at 20 columns in markdown; full data in CSV
- Cohort section added as Section 5 (not 4) since Plan 01 created 4 existing sections
- DX format auto-detection samples 1000 records to choose dotted vs normalized code set
- ICD version classification uses normalized _DX_MATCH column for consistent prefix matching
- build_cohort_summary_df produces per-patient CSV with method membership, ICD flag, DX date range
- Wide vital ranges (HT 50-272cm, WT 1-500kg) to minimize false positives
- 20 LOINC codes covering CBC, liver function, TSH, ESR, CRP with wide biological ranges
- ICD grace period Jul 2015 - Jan 2016; AMS/UMI always treated as mapped partners
- Value set validation skips fields with >200 valid values (loosely-coded fields)
- B-symptom probing: check B_SYMPTOMS first, fall back to CS_SSF1
- Primary site check is informational (non-lymph-node sites possible in some HL)
- Masked birth date recovery uses TUMOR_REGISTRY AGE_AT_DIAGNOSIS + DATE_OF_DIAGNOSIS → Jan 1 of computed year
- HL timeline is cross-table summary (not per-row flags), combining PROCEDURES/PRESCRIBING/TUMOR_REGISTRY
- Stem cell transplant CPTs (38240-38242) + radiation CPTs (77401-77427) for treatment detection
- Small-cell suppression: dash in CSVs, warning marker in markdown reports
- Pre-transition ICD-10 counts (before Oct 2015) added to concordance CSV for mapped partner detection

## Blockers
None.

## Performance Metrics

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 01    | 01   | ~8min    | 2     | 10    |
| 02    | 01   | ~6min    | 2     | 2     |
| 03    | 01   | ~8min    | 2     | 3     |
| 03    | 02   | ~8min    | 2     | 2     |
| 04    | 01   | ~8min    | 2     | 1     |
| 04    | 02   | ~5min    | 2     | 1     |
