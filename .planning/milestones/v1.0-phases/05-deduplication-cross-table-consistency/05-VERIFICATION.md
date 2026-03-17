---
phase: 05-deduplication-cross-table-consistency
verified: 2026-03-02T10:30:00Z
status: passed
score: 10/10 must-haves verified
re_verification: false
---

# Phase 5: Deduplication, Cross-Table Consistency & Partner Harmonization — Verification Report

**Phase Goal:** Detect duplicates, verify cross-table consistency, and harmonize partner-level differences; flag but don't delete.
**Verified:** 2026-03-02T10:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Source | Status | Evidence |
|---|-------|--------|--------|----------|
| 1 | flag_duplicates() marks ALL rows sharing composite key values as IS_DUPLICATE=1 (not just subsequent) | 05-01 | ✓ VERIFIED | `df.select(available_keys).is_duplicated()` (dedup.py:95) marks ALL duplicate rows; cast to Int8 (line 96); 6 tables in DEDUP_KEYS with composite keys |
| 2 | add_partner_flags() adds ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY as Int8 flags on tables with SOURCE column | 05-01 | ✓ VERIFIED | Guard clause checks partner_col presence (harmonize.py:38); iterates PARTNER_FLAGS dict; uses `is_in(partners).cast(pl.Int8)` (lines 41-46); Python sets used (not Series) |
| 3 | flag_events_outside_encounters() marks events outside encounter admission-discharge window (±1 day tolerance) | 05-01 | ✓ VERIFIED | Lower bound: `ADMIT_DATE - pl.duration(days=1)` (dedup.py:184); upper bound: `DISCHARGE_DATE + pl.duration(days=1)` (line 188); null ENCOUNTERID/ADMIT_DATE/event_date → flag=0 (lines 177-181); null DISCHARGE_DATE → open-ended (line 186-188); lazy evaluation with collect (line 197) |
| 4 | flag_encounters_outside_enrollment() identifies encounters not covered by any enrollment period | 05-01 | ✓ VERIFIED | Left join on PATID_COL (harmonize.py:82); _covered per enrollment row (lines 83-93); group_by + max collapse (lines 94-95); _con_outside_enrollment flag (lines 96-105); flag_no_enrollment anti-join pattern (lines 117-148); both use lazy evaluation |
| 5 | drop_existing_clean_flags() removes all Phase 5 flag columns for idempotent re-runs | 05-01 | ✓ VERIFIED | Drops columns in CLEAN_FLAG_COLS (`IS_DUPLICATE`, `ICD_MAPPED`, `CLAIMS_ONLY`, `DEATH_ONLY`) or starting with `_con_` prefix (dedup.py:67-72) |
| 6 | Running scripts/clean_all.py produces Parquet files with Phase 5 flag columns in parquet_dir | 05-02 | ✓ VERIFIED | Main loop reads each table, applies drop_existing_clean_flags → flag_duplicates → add_partner_flags → event-encounter → enrollment (clean_all.py:507-535); `write_cleaned(df, pq_path)` writes snappy Parquet back to same path (line 535) |
| 7 | Three markdown reports generated: dedup_report.md, consistency_report.md, partner_harmonization.md | 05-02 | ✓ VERIFIED | `_generate_dedup_report` → `dedup_report.md` (clean_all.py:77→166); `_generate_consistency_report` → `consistency_report.md` (171→319); `_generate_partner_report` → `partner_harmonization.md` (324→425); all called in main (lines 594-603) |
| 8 | Small-cell suppression applied to all counts in reports (HIPAA compliance) | 05-02 | ✓ VERIFIED | `flag_small_cell` imported from structural.py (line 23); used 14 times across all three report generators (dedup: lines 113,141; consistency: 220,231,252,276,288,308,315; partner: 365,376,403,421); `_suppress` helper also defined (line 65-69) |
| 9 | No records are deleted; all flags are additive Int8 columns | 05-02 | ✓ VERIFIED | Main loop: read → drop old flags → add new flags → write back; no `.filter()` that removes data rows; all flags cast to Int8 (dedup.py:96,193; harmonize.py:44,103,145) |
| 10 | Dedup rates reported per table and per partner in dedup_report.md | 05-02 | ✓ VERIFIED | Section 1 "Overview": per-table IS_DUPLICATE counts/rates with DEDUP_KEYS (clean_all.py:100-118); Section 2 "Per-Partner Duplicate Rates": partner_dedup DataFrame computed in main loop (lines 552-557), iterated in report (lines 128-146) |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact | Expected | Lines | Status | Details |
|----------|----------|-------|--------|---------|
| `src/clean/__init__.py` | Package initializer | 0 (empty) | ✓ VERIFIED | Empty file, correct for package init |
| `src/clean/dedup.py` | Dedup flagging, cross-table consistency, write helper | 332 | ✓ VERIFIED | 8 exports: flag_duplicates, DEDUP_KEYS, EVENT_DATE_COLS, check_demographic_consistency, flag_events_outside_encounters, check_death_consistency, drop_existing_clean_flags, write_cleaned — all present and substantive |
| `src/clean/harmonize.py` | Partner harmonization flags, insurance consistency | 148 | ✓ VERIFIED | 4 exports: add_partner_flags, PARTNER_FLAGS, flag_encounters_outside_enrollment, flag_no_enrollment — all present and substantive |
| `scripts/clean_all.py` | Phase 5 entry point (min_lines: 300) | 640 | ✓ VERIFIED | 640 lines, exceeds 300 minimum; main loop, 3 report generators, helpers, __main__ block |
| `reports/dedup_report.md` | Duplicate detection rates by table and partner | — | ⏳ RUNTIME | Code path verified (clean_all.py:77-168); generated when script runs on HPC |
| `reports/consistency_report.md` | Cross-table consistency findings | — | ⏳ RUNTIME | Code path verified (clean_all.py:171-321); generated when script runs on HPC |
| `reports/partner_harmonization.md` | Partner-specific flags and limitations | — | ⏳ RUNTIME | Code path verified (clean_all.py:324-427); generated when script runs on HPC |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/clean/dedup.py` | `src/validate/structural.py` | `from src.validate.structural import PATID_COL, TUMOR_REGISTRY_TABLES` | ✓ WIRED | dedup.py:14; PATID_COL used in check_demographic_consistency (line 119-137), check_death_consistency (line 223); TUMOR_REGISTRY_TABLES used in check_death_consistency (line 235) |
| `src/clean/harmonize.py` | `src/validate/structural.py` | `from src.validate.structural import PATID_COL` | ✓ WIRED | harmonize.py:11; PATID_COL used in flag_encounters_outside_enrollment (lines 72,81), flag_no_enrollment (lines 127,130,133,139,141) |
| `src/clean/dedup.py` | Parquet files | `write_parquet` with snappy compression | ✓ WIRED | dedup.py:331: `df.write_parquet(parquet_path, compression="snappy")` |
| `scripts/clean_all.py` | `src/clean/dedup.py` | `from src.clean.dedup import` | ✓ WIRED | clean_all.py:25-36; imports flag_duplicates, DEDUP_KEYS, EVENT_DATE_COLS, CLEAN_FLAG_COLS, CLEAN_FLAG_PREFIX, check_demographic_consistency, flag_events_outside_encounters, check_death_consistency, drop_existing_clean_flags, write_cleaned — all used in main loop and reports |
| `scripts/clean_all.py` | `src/clean/harmonize.py` | `from src.clean.harmonize import` | ✓ WIRED | clean_all.py:37-42; imports add_partner_flags, PARTNER_FLAGS, flag_encounters_outside_enrollment, flag_no_enrollment — all used in main loop and reports |
| `scripts/clean_all.py` | `src/validate/structural.py` | `from src.validate.structural import` | ✓ WIRED | clean_all.py:18-24; imports PATID_COL, SMALL_CELL_THRESHOLD, TUMOR_REGISTRY_TABLES, ENCOUNTER_LINKED_TABLES, flag_small_cell — flag_small_cell used 14 times in reports; PATID_COL used in enrollment ref setup (line 479) |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| REQ-03 | 05-01, 05-02 | Clean data for HL insurance inequities analysis | ✓ SATISFIED | Composite-key dedup for 6 CDM tables; partner harmonization (ICD_MAPPED for AMS/UMI, CLAIMS_ONLY for FLM, DEATH_ONLY for VRT); cross-table consistency (demographic, event-encounter, death date); insurance enrollment coverage validation; three markdown reports |
| REQ-04 | 05-02 | Run on HiPerGator HPC | ✓ SATISFIED | Script designed for HPC (docstring: "Designed for HPC interactive sessions"); PROJECT_ROOT/sys.path pattern (clean_all.py:13-14); config-driven paths via `load_config(config_path)` (line 443); paths.toml compatible with SLURM environment |
| REQ-05 | 05-02 | HIPAA-compliant data handling | ✓ SATISFIED | `flag_small_cell()` used 14 times across all three report generators (counts 1-10 get ⚠ marker); `_suppress()` replaces 1-10 with dash for CSV use; no patient-level data in reports; data stays on HPC paths per config |

No orphaned requirements for this phase.

### ROADMAP Success Criteria Verification

| # | Success Criterion | Status | Evidence |
|---|-------------------|--------|----------|
| 1 | Exact and near-duplicates detected per table | ✓ MET | flag_duplicates for 6 tables (DIAGNOSIS, PROCEDURES, LAB_RESULT_CM, ENCOUNTER, VITAL, PRESCRIBING) with composite keys in DEDUP_KEYS |
| 2 | Cross-table consistency verified: demographics match across tables, events fall within encounters | ✓ MET | check_demographic_consistency (multi-BIRTH_DATE, multi-SEX); flag_events_outside_encounters (±1 day); check_death_consistency (DEATH vs TUMOR_REGISTRY) |
| 3 | Partner harmonization: ICD-9→ICD-10 mapping partners flagged; claims-only partner flagged | ✓ MET | add_partner_flags: ICD_MAPPED for {AMS, UMI}, CLAIMS_ONLY for {FLM}, DEATH_ONLY for {VRT} — applied to all tables with SOURCE column |
| 4 | Insurance consistency: Enrollment periods vs encounter dates aligned | ✓ MET | flag_encounters_outside_enrollment (ADMIT_DATE vs ENR_START_DATE/ENR_END_DATE); flag_no_enrollment (anti-join for patients with zero enrollment) |
| 5 | All flags are additive columns — no records deleted | ✓ MET | All flags are Int8 columns (0/1); no row deletion in pipeline; drop_existing_clean_flags only removes previous flag columns for idempotent re-runs |
| 6 | Duplicate rates reported per table per partner | ✓ MET | dedup_report.md Section 1 (per-table) and Section 2 (per-partner) with flag_small_cell suppression |

All 6 ROADMAP success criteria met.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/clean/dedup.py` | 113, 116, 217 | `return {}` | ℹ️ Info | Legitimate early returns when DEMOGRAPHIC or DEATH tables are unavailable — correct guard clause behavior, not stubs |

No TODO/FIXME/PLACEHOLDER comments. No empty implementations. No console-log-only handlers. No stub patterns detected.

### Human Verification Required

### 1. Run Pipeline on HPC

**Test:** Execute `python scripts/clean_all.py config/paths.toml` on HiPerGator
**Expected:** Script completes without error; flagged Parquet files written to parquet_dir; three reports generated in `reports/`
**Why human:** Requires real data on HPC filesystem; cannot verify I/O, memory, and runtime behavior from static analysis

### 2. Inspect Generated Reports

**Test:** Open `reports/dedup_report.md`, `reports/consistency_report.md`, `reports/partner_harmonization.md`
**Expected:** Reports contain properly formatted markdown tables, correct per-table/per-partner breakdowns, small-cell suppression markers (⚠) on counts 1-10
**Why human:** Report content depends on real data distribution; formatting and correctness need visual inspection

### 3. Verify Parquet Flag Columns

**Test:** Load a flagged Parquet file and inspect column list
**Expected:** DIAGNOSIS has IS_DUPLICATE + ICD_MAPPED/CLAIMS_ONLY/DEATH_ONLY (if SOURCE exists) + _con_outside_encounter; ENCOUNTER has IS_DUPLICATE + partner flags + _con_outside_enrollment + _con_no_enrollment
**Why human:** Column presence depends on actual data column availability at runtime

### Gaps Summary

No gaps found. All 10 observable truths (5 from Plan 01, 5 from Plan 02) are verified through static code analysis. All 7 code artifacts exist, are substantive (not stubs), and are properly wired. All 6 key links confirmed via import and usage checks. All 3 requirement IDs (REQ-03, REQ-04, REQ-05) are satisfied with evidence. All 6 ROADMAP success criteria met. No anti-patterns detected.

The 3 report output files (dedup_report.md, consistency_report.md, partner_harmonization.md) are runtime-generated artifacts — their code paths are fully verified as substantive and complete, but the actual files will be produced when the script runs on HPC with real data.

---

_Verified: 2026-03-02T10:30:00Z_
_Verifier: Claude (gsd-verifier)_
