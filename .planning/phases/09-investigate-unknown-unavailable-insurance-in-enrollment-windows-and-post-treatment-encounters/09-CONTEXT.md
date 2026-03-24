# Phase 9: Investigate Unknown/Unavailable Insurance in Enrollment Windows and Post-Treatment Encounters - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Answer diagnostic questions about patients with Unknown and Unavailable insurance status across treatment windows and post-treatment periods. Specifically:

1. Look at ENROLLMENT windows along with treatment first/last dates to determine if patients with Unknown/Unavailable insurance should still be counted in treatment windows
2. For Unknown and Unavailable on chemo post-treatment: what % have no encounters after their last chemo encounter?
3. For Unknown and Unavailable on radiation post-treatment: what % have no encounters after their last radiation encounter?
4. For Unknown and Unavailable on SCT post-treatment: what % have no encounters after their last SCT encounter?
5. For SCT: why does primary insurance Unknown=4 but Unknown at first and last are both zero?

This is a diagnostic/investigative phase. It reports findings — it does NOT modify Phases 5-8 tables or change counting rules.

</domain>

<decisions>
## Implementation Decisions

### Output format
- **D-01:** Diagnostic Python script (not a full table pipeline) — prints findings to console AND writes a structured markdown report to `reports/phase9_insurance_diagnostic.md`
- **D-02:** No PNG, HTML, CSV, or PowerPoint output — this is exploratory analysis, not presentation tables
- **D-03:** Report format: structured markdown with numbered sections matching the 5 questions, tables where appropriate

### Counting approach
- **D-04:** Report findings only — do NOT recommend exclusions or change existing Phase 5-8 tables
- **D-05:** Unknown and Unavailable are reported as separate groups (not combined), since they may have different underlying patterns
- **D-06:** For "no encounters after last treatment" questions, use treatment-specific dates (LAST_CHEMO_DATE for chemo, LAST_RADIATION_DATE for radiation, LAST_SCT_DATE for SCT) — matches the questions as asked

### Cross-referencing enrollment
- **D-07:** Cross-reference Phase 8's enrollment coverage for Unknown/Unavailable post-treatment patients
- **D-08:** Use ±30 day treatment window enrollment check (reuse Phase 8's `_check_enrollment_covers_window` logic) for direct comparability with Phase 8 tables
- **D-09:** For each treatment type, report: of the Unknown/Unavailable patients, how many had ENR coverage vs not around the treatment-specific window

### SCT discrepancy investigation
- **D-10:** Full patient-level trace for the 4 SCT patients with primary Unknown — identify them, show their primary payer source encounters, first/last SCT dates, and derived payer at first/last SCT
- **D-11:** Include per-patient trace table in the markdown report (patient IDs are already de-identified in PCORnet CDM)
- **D-12:** Explain the mechanism causing the discrepancy (e.g., different encounter payer in the ±30d SCT window vs primary/mode payer)

### Claude's Discretion
- Script naming and organization within `scripts/`
- Exact markdown report structure and section headings
- Whether to reuse Phase 8's enrollment functions via import or recompute inline
- How to present the enrollment cross-reference findings (table vs narrative)
- Bin sizes for encounter count distributions

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing insurance analysis scripts
- `scripts/build_insurance_enr_comparison.py` — Phase 8 enrollment comparison logic, `_check_enrollment_covers_window()` and `_flag_enrollment_coverage()` functions to reuse
- `scripts/build_post_treatment_insurance.py` — Phase 6 post-treatment payer computation, `_compute_post_treatment_payer()` logic
- `scripts/build_insurance_by_treatment.py` — Phase 5 insurance tables, PAYER_CATEGORY_ORDER, encounter_payer_summary.parquet column reference

### Core payer logic
- `src/report/encounter_payer_summary.py` — Payer derivation logic, `_payer_mode_in_window()`, `_payer_category_from_effective_and_dual()`, treatment date columns, effective payer expressions

### Data sources
- `derived/encounter_payer_summary.parquet` — Patient-level summary with PAYER_CATEGORY_PRIMARY, PAYER_CATEGORY_AT_FIRST_*/LAST_* columns, treatment dates, treatment flags
- `cleaned/ENROLLMENT*.parquet` — ENR_START_DATE, ENR_END_DATE per patient (multiple rows possible)
- `cleaned/ENCOUNTER*.parquet` — Encounter records with ADMIT_DATE, PAYER_TYPE_PRIMARY, PAYER_TYPE_SECONDARY

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_check_enrollment_covers_window()` in build_insurance_enr_comparison.py — union-of-periods enrollment coverage check, directly reusable for ±30d window checks
- `_flag_enrollment_coverage()` in build_insurance_enr_comparison.py — batch enrollment coverage flagging per cohort
- `_compute_post_treatment_payer()` in build_post_treatment_insurance.py — post-treatment payer derivation logic
- `_payer_category_from_effective_and_dual()` in encounter_payer_summary.py — maps effective payer + dual flag to 9-category system
- `PAYER_CATEGORY_ORDER` — standard 9-category order used across all scripts
- `load_and_validate_config()` — standard config loading pattern

### Established Patterns
- Standalone scripts in `scripts/` reading from `derived/` and `cleaned/` parquet files
- Config-driven path resolution via `load_and_validate_config()`
- Console progress output with section numbering (`[1/N]`, `[2/N]`, ...)
- Polars-based data manipulation throughout

### Integration Points
- Input: `derived/encounter_payer_summary.parquet` (same source as Phases 5-8)
- Input: `cleaned/ENROLLMENT*.parquet` (same as Phase 8)
- Input: `cleaned/ENCOUNTER*.parquet` (same as Phase 6/8)
- Output: `reports/phase9_insurance_diagnostic.md` (new)
- Can import functions from `scripts/build_insurance_enr_comparison.py` or recompute inline

</code_context>

<specifics>
## Specific Ideas

- The core question is whether Unknown/Unavailable insurance in treatment windows reflects genuinely missing data vs enrollment gaps — the enrollment cross-reference should help distinguish these
- For questions 2-4, the key metric is: "of patients who got payer X (Unknown or Unavailable) at last treatment, how many have ZERO encounters after that treatment date?" — this reveals if they dropped out of the system
- The SCT discrepancy (primary Unknown=4, first/last=0) likely means those 4 patients had Unknown as their overall mode payer but happened to have encounters with known payer in the ±30d SCT windows — the patient trace should confirm this mechanism

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-investigate-unknown-unavailable-insurance-in-enrollment-windows-and-post-treatment-encounters*
*Context gathered: 2026-03-24*
