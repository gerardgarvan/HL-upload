# Phase 4: Plan Verification Report

**Phase:** 04-hl-specific-value-temporal-validation
**Plans verified:** 2 (04-01-PLAN.md, 04-02-PLAN.md)
**Status:** ISSUES FOUND
**Checked:** 2026-02-27

---

## Overall Result

**Issues:** 1 blocker, 2 warnings, 1 info

The plans are well-structured, detailed, and cover the vast majority of Phase 4 requirements. One locked decision from CONTEXT.md is not fully implemented (masked birth date → AGE_AT_DIAGNOSIS fallback). Two roadmap success criteria are partially addressed. After fixing the blocker, the plans are ready for execution.

---

## 1. Requirement Coverage

| Requirement | Plan 01 | Plan 02 | Status |
|-------------|---------|---------|--------|
| REQ-02 (Validate converted dates) | `validate_future_dates`, `validate_temporal_encounter` | `_validate_against_birth`, `_validate_against_death` | **COVERED** |
| REQ-03 (Clean data for HL analysis) | All validation functions (ICD, plausibility, tumor registry) | HL timeline, ICD concordance CSV, reports | **COVERED** |
| REQ-04 (Run on HiPerGator HPC) | Polars-based, table-at-a-time | Same entry-point pattern as Phase 3 | **COVERED** |
| REQ-05 (HIPAA-compliant) | No PII in function outputs | `flag_small_cell` on all report counts | **COVERED** |

All four requirements have implementing tasks in both plans. ✓

---

## 2. Success Criteria Coverage

| # | Criterion | Covering Plan:Task | Status |
|---|-----------|-------------------|--------|
| 1 | All PCORnet coded fields validated against CDM value sets | 01:T1 `validate_coded_fields` + `build_valueset_lookup` | **COVERED** |
| 2 | Clinical code format validation: ICD-10-CM, CPT, NDC, LOINC | Partially: ICD concordance (01:T2), value set types (01:T1) | **WARNING** — see Issue #2 |
| 3 | ICD-9/ICD-10 concordance with partner exceptions | 01:T2 `detect_mapped_partners` + `validate_icd_concordance` | **COVERED** |
| 4 | Vital signs plausibility: HT, WT, SBP, DBP | 01:T1 `validate_vital_plausibility` with VITAL_RANGES | **COVERED** |
| 5 | Lab result plausibility for HL-relevant labs | 01:T1 `validate_lab_plausibility` with 20 LOINC codes | **COVERED** |
| 6 | Temporal consistency: DISCHARGE ≥ ADMIT, birth/death, future dates | 01:T2 `validate_temporal_encounter`, `validate_future_dates`; 02:T1 `_validate_against_birth/death` | **COVERED** |
| 7 | HL disease timeline: first DX → first treatment plausible | 02:T1 `_compute_hl_timeline` (0-365 day window) | **COVERED** |
| 8 | Tumor registry: AJCC staging, treatment dates, B-symptoms, histology | 01:T2 `validate_tumor_registry` (6 checks) | **COVERED** |
| 9 | Insurance timeline: ENR_START ≤ ENR_END; enrollment covers encounters | 01:T2 `validate_enrollment_dates` (ordering only) | **WARNING** — see Issue #3 |
| 10 | Validation flags added as columns (not deletions) | Both plans: `_val_` infix columns, `drop_existing_flags` for idempotency | **COVERED** |

**Coverage:** 8/10 fully covered, 2/10 partially covered.

---

## 3. Context Compliance

### Locked Decisions

| Decision | Plan Implementation | Status |
|----------|-------------------|--------|
| Binary (0/1) flags in Parquet, overwrite in-place | Int8 flags via `_val_` columns, `write_validated` overwrites | ✓ |
| ICD grace period around Oct 2015 | GRACE_START = Jul 2015, GRACE_END = Jan 2016 | ✓ |
| Auto-detect mapped partners + AMS/UMI always included | `detect_mapped_partners` with >95% threshold, union with {AMS, UMI} | ✓ |
| All DX codes (comprehensive concordance) | `validate_icd_concordance` on full DIAGNOSIS table | ✓ |
| ICD output: CSV + report section | `icd_concordance.csv` + `_section_icd_concordance` | ✓ |
| Wide biological plausibility ranges | VITAL_RANGES and HL_LAB_RANGES use wide ranges | ✓ |
| Flag missing RESULT_UNIT separately | `RESULT_UNIT_val_missing` flag column | ✓ |
| Always flag same-day admit/discharge | `_val_same_day` flag, report stratifies by ENC_TYPE | ✓ |
| Dec 2025 future date cutoff | `FUTURE_DATE_CUTOFF = date(2025, 12, 31)` | ✓ |
| Masked birth → use AGE_AT_DIAGNOSIS from TR | `_validate_against_birth` only SKIPS masked patients | **BLOCKER** — see Issue #1 |
| HL timeline 0-365 days | `_compute_hl_timeline` flags < 0 and > 365 | ✓ |
| Flags for context only, not exclusion | No deletion/imputation anywhere in plans | ✓ |

### Deferred Ideas

No deferred ideas in CONTEXT.md → no scope creep possible. ✓

### Claude's Discretion Areas

| Area | Planner's Choice | Valid? |
|------|-----------------|--------|
| Vital sign thresholds | HT 50-272, WT 1-500, SBP 40-300, DBP 20-200, BMI 8-100 | ✓ Wider than roadmap suggestion, clinically sound |
| Tumor registry depth | HL-specific: histology, AJCC, B-symptoms, age, treatment timing, primary site | ✓ Deep validation appropriate for 3 partners |
| Mapped partner detection | >95% ICD-10 in pre-transition data | ✓ Reasonable heuristic |
| Flag naming convention | `{COLUMN}_val_{check_type}` with `_val_` infix | ✓ Consistent and discoverable |

---

## 4. Task Completeness

| Plan | Task | Files | Action | Verify | Done | Status |
|------|------|-------|--------|--------|------|--------|
| 01 | T1: Value set, plausibility, utilities | ✓ | ✓ (detailed) | ✓ | ✓ | Valid |
| 01 | T2: ICD, temporal, tumor, insurance, write-back | ✓ | ✓ (detailed) | ✓ | ✓ | Valid |
| 02 | T1: Entry point, cross-table temporal, HL timeline | ✓ | ✓ (very detailed) | ✓ | ✓ | Valid |
| 02 | T2: Report generation (4 output files) | ✓ | ✓ (detailed) | ✓ | ✓ | Valid |

All tasks have complete structure with specific actions, runnable verification commands, and measurable acceptance criteria. ✓

---

## 5. Dependency Correctness

| Plan | Wave | depends_on | Status |
|------|------|-----------|--------|
| 04-01 | 1 | [] | ✓ — Foundation, no dependencies |
| 04-02 | 2 | ["04-01"] | ✓ — Imports values.py functions from Plan 01 |

Dependency graph is valid: Plan 01 creates `src/validate/values.py`, Plan 02 creates `scripts/validate_values.py` which imports from it. No cycles. ✓

---

## 6. Key Links

| From | To | Via | Task | Status |
|------|-----|-----|------|--------|
| values.py | valuesets.csv | `build_valueset_lookup` reads CSV | 01:T1 | ✓ Wired |
| values.py | Parquet files | `write_validated` overwrites in-place | 01:T2 | ✓ Wired |
| values.py | structural.py | `PATID_COL`, `SMALL_CELL_THRESHOLD` imports | 01:T1 | ✓ Wired |
| validate_values.py | values.py | Imports all 12 functions | 02:T1 | ✓ Wired |
| validate_values.py | config.py | `load_config` for paths | 02:T1 | ✓ Wired |
| validate_values.py | schema.py | `parse_datastructure` for table list | 02:T1 | ✓ Wired |
| validate_values.py | cohort.py | HL code sets for timeline analysis | 02:T1 | ✓ Wired |
| validate_values.py | Parquet files | Read + write via `write_validated` | 02:T1 | ✓ Wired |

All artifacts connected. No isolated components. ✓

---

## 7. Output Files

| Expected File | Plan | Status |
|--------------|------|--------|
| src/validate/values.py | 01 (T1+T2) | ✓ |
| scripts/validate_values.py | 02 (T1+T2) | ✓ |
| reports/value_validation.md | 02 (T2) | ✓ |
| reports/icd_concordance.csv | 02 (T1+T2) | ✓ |
| reports/temporal_issues.csv | 02 (T2) | ✓ |
| reports/tumor_registry_validation.csv | 02 (T2) | ✓ |

All 6 output files accounted for. ✓

---

## 8. Scope Sanity

| Plan | Tasks | Files Modified | Wave | Status |
|------|-------|---------------|------|--------|
| 01 | 2 | 1 (values.py) | 1 | ✓ Within limits |
| 02 | 2 | 1 (validate_values.py) + 4 reports | 2 | ✓ Within limits |

Total: 4 tasks across 2 plans, 2 source files + 4 report outputs. Well within context budget. ✓

---

## Issues

### Blockers (must fix before execution)

**Issue #1: [context_compliance] Masked birth date fallback not implemented**

```yaml
issue:
  plan: "04-02"
  dimension: context_compliance
  severity: blocker
  description: "Plan contradicts locked decision: user specified 'use AGE_AT_DIAGNOSIS from TUMOR_REGISTRY when available' for masked birth dates, but _validate_against_birth only skips masked patients entirely"
  task: 1
  user_decision: "When BIRTH_DATE = 1900-01-01 (masked), use AGE_AT_DIAGNOSIS from TUMOR_REGISTRY when available instead of birth date for temporal checks. If neither is available, skip."
  plan_action: "_validate_against_birth skips when BIRTH_DATE != MASKED_BIRTH_DATE — no AGE_AT_DIAGNOSIS lookup"
  fix_hint: "In _load_birth_death_lookup, also load TUMOR_REGISTRY AGE_AT_DIAGNOSIS + DATE_OF_DIAGNOSIS. For masked patients with TR data, compute approximate BIRTH_DATE = DATE_OF_DIAGNOSIS.year - AGE_AT_DIAGNOSIS, then use that in _validate_against_birth. Only skip if both BIRTH_DATE is masked AND no TR data available."
```

**Why this matters:** The user explicitly chose this behavior during `/gsd:discuss-phase`. Skipping all masked patients means temporal checks are silently omitted for an unknown portion of the cohort. The AGE_AT_DIAGNOSIS fallback applies to the 3 partners with tumor registry data (ORL, TMH, UFH), which are likely the core HL treatment centers.

**Suggested fix in Plan 02 Task 1:**

Modify `_load_birth_death_lookup` to return a third DataFrame:
```
(birth_df, death_df, tr_age_df)
```
Where `tr_age_df` contains (ID, AGE_AT_DIAGNOSIS, DATE_OF_DIAGNOSIS) from TUMOR_REGISTRY tables. Then in `_validate_against_birth`, when BIRTH_DATE is masked, compute approximate birth date from TR data before skipping.

---

### Warnings (should fix)

**Issue #2: [requirement_coverage] Clinical code format validation not explicitly implemented**

```yaml
issue:
  plan: null
  dimension: requirement_coverage
  severity: warning
  description: "Success criterion #2 (clinical code format validation: ICD-10-CM, CPT, NDC, LOINC) has no explicit format-pattern tasks. Value set checks cover coded FIELD values (DX_TYPE, PX_TYPE) but not the actual code strings (DX, PX, LAB_LOINC format patterns)."
  fix_hint: "This is largely mitigated by existing coverage: ICD concordance validates ICD version-date consistency, lab plausibility validates LOINC-specific ranges, value sets validate category fields. Explicit CPT/NDC/LOINC regex validation could be added to validate_coded_fields or as a separate function, but the ROI is low since malformed codes would likely be caught by value set checks on their TYPE fields. Consider adding a note in the report rather than implementing format checks."
```

**Why this is a warning, not a blocker:** The roadmap's Key Task 4 ("HL outcome procedure/lab validation using concepts.py code sets") is addressed by lab plausibility using LOINC-specific ranges. The ICD concordance handles ICD version validation. CPT/NDC format validation (e.g., `\d{5}` for CPT, `\d{11}` for NDC) is a relatively low-value check since the TYPE fields (PX_TYPE, RX_TYPE) are already validated against CDM value sets. If the type says "CH" (CPT) and the code isn't a valid CPT format, the value-set check on PX_TYPE would still pass — but this is an edge case unlikely to occur at scale.

---

**Issue #3: [requirement_coverage] Enrollment-encounter coverage check deferred**

```yaml
issue:
  plan: "04-02"
  dimension: requirement_coverage
  severity: warning
  description: "Success criterion #9 states 'enrollment periods cover encounter dates' but plans only implement ENR_START <= ENR_END ordering. The enrollment-to-encounter coverage cross-table check is not in Phase 4 plans."
  fix_hint: "This is likely intentional — Phase 5 Key Task 4 explicitly covers 'Match ENROLLMENT periods to ENCOUNTER dates' and 'Flag encounters outside enrollment windows'. Recommend either: (a) remove 'enrollment periods cover encounter dates' from Phase 4 success criteria in ROADMAP.md, or (b) add a basic enrollment-encounter coverage check to Plan 02. Option (a) is recommended since this is a cross-table consistency check that fits Phase 5's scope better."
```

---

### Info

**Issue #4: [task_completeness] HL_HISTOLOGY_CODES uses full range vs. specific codes**

```yaml
issue:
  plan: "04-01"
  dimension: task_completeness
  severity: info
  description: "HL_HISTOLOGY_CODES = set(range(9650, 9668)) includes 18 codes (9650-9667), but only 13 are real ICD-O-3 HL histology codes. Codes 9656, 9657, 9658, 9660, 9666 are not valid WHO classifications."
  task: 1
  fix_hint: "Non-issue in practice — unused ICD-O-3 codes won't appear in real cancer registry data. Using the full range is conservative (fewer false positives). No change needed."
```

---

## Plan Summary

| Plan | Tasks | Files | Wave | Issues | Status |
|------|-------|-------|------|--------|--------|
| 04-01 | 2 | 1 | 1 | 1 info | Valid (minor info only) |
| 04-02 | 2 | 1 + 4 reports | 2 | 1 blocker, 2 warnings | Needs revision |

---

## Recommendation

**1 blocker requires revision** before execution can proceed.

The masked birth date fallback (Issue #1) is a locked user decision that must be implemented. The fix is localized to Plan 02 Task 1: extend `_load_birth_death_lookup` to include TR age data, and modify `_validate_against_birth` to compute approximate birth dates for masked patients with tumor registry records.

The two warnings are judgment calls:
- **Issue #2** (code format validation) has low ROI and is largely mitigated by existing coverage. Could be addressed with a note in the validation report.
- **Issue #3** (enrollment-encounter coverage) should be resolved by clarifying the Phase 4/5 boundary in the roadmap. The check fits Phase 5 better.

After fixing the blocker, run `/gsd:execute-phase 04` to proceed.

---

*Verified: 2026-02-27*
*Plans: 04-01-PLAN.md, 04-02-PLAN.md*
*Against: ROADMAP.md Phase 4, 04-CONTEXT.md*
