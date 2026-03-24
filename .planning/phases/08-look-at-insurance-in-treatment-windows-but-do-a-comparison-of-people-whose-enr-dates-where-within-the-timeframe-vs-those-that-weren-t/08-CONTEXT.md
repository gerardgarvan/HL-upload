# Phase 8: Insurance in Treatment Windows — ENR Date Comparison - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Compare insurance coverage patterns between patients whose ENROLLMENT dates fully cover the ±30 day treatment window vs those whose enrollment doesn't cover it. Produces side-by-side comparison tables (enrolled-covered vs not-covered) for each treatment type, plus a diagnostic breakdown of "Unknown" post-treatment payer patients from Phase 6. All outputs in PNG, CSV/markdown, HTML, and added to the PowerPoint presentation.

</domain>

<decisions>
## Implementation Decisions

### Treatment window definition
- **D-01:** Reuse existing ±30 day windows from the pipeline (PAYER_AT_TREATMENT_WINDOW_DAYS=30)
- **D-02:** 7 windows total: FIRST_HL_DX_DATE, FIRST_CHEMO_DATE, LAST_CHEMO_DATE, FIRST_RADIATION_DATE, LAST_RADIATION_DATE, FIRST_SCT_DATE, LAST_SCT_DATE
- **D-03:** Window = [treatment_date - 30 days, treatment_date + 30 days]

### ENR overlap logic
- **D-04:** Full coverage required — the union of a patient's ENROLLMENT periods must span the entire ±30 day window for the patient to count as "enrolled covers window"
- **D-05:** Multiple enrollment periods: combined coverage OK (adjacent/overlapping ENR records can together cover the window)
- **D-06:** Patients with no ENROLLMENT records at all count as "ENR does not cover window"

### Comparison table structure
- **D-07:** Side-by-side columns: "ENR Covers Window N (%)" | "ENR Does Not Cover Window N (%)" per table
- **D-08:** 4 tables total: DX table (2 columns), Chemo table (4 columns: first covers/doesn't + last covers/doesn't), Radiation table (4 columns), SCT table (4 columns)
- **D-09:** N per column in header (each column shows its own group size)
- **D-10:** Payer values from existing pipeline: PAYER_CATEGORY_AT_FIRST_* and PAYER_CATEGORY_AT_LAST_* columns from encounter_payer_summary.parquet
- **D-11:** Patients with null PAYER_CATEGORY_AT_* shown as "N/A" row (not under Unknown)
- **D-12:** Same 9 payer categories + N/A row where applicable

### Cohort scoping
- **D-13:** DX table: all HL patients with non-null FIRST_HL_DX_DATE
- **D-14:** Treatment tables: treatment-specific cohorts (HAD_CHEMO=1 for chemo, HAD_RADIATION=1 for radiation, HAD_SCT=1 for SCT) — same as Phase 5
- **D-15:** Exclude patients with null treatment dates from that treatment type's table (e.g., HAD_CHEMO=1 but FIRST_CHEMO_DATE is null = excluded from chemo table)

### Unknown post-treatment encounter analysis
- **D-16:** Additional diagnostic analysis: for patients with "Unknown" post-treatment payer from Phase 6 logic, show a count breakdown of encounters after last treatment
- **D-17:** Breakdown table: how many Unknown-payer patients have 0 encounters, 1-5, 6+, etc. after last treatment date — reveals whether Unknown = no data vs Unknown = encounters with no payer info
- **D-18:** Same 3-format output (PNG, CSV/markdown, HTML) and included in PowerPoint

### Output and presentation
- **D-19:** All tables output in 3 formats: PNG (color-coded, seaborn Pastel1 palette), CSV + markdown, styled HTML
- **D-20:** Same visual style as Phases 5/6 (same colors, fonts, layout)
- **D-21:** No HIPAA small-cell suppression (internal working tables)
- **D-22:** Add all tables as slides to the existing PowerPoint presentation (extend Phase 7 script or rebuild)
- **D-23:** Report directory: reports/insurance_enr_comparison/

### Claude's Discretion
- Column header wording for enrolled/not-enrolled groups
- How to organize the 4+1 tables in the PowerPoint (section dividers, slide order)
- Exact encounter count bins for the Unknown breakdown table (0, 1-5, 6+ or finer)
- Whether to extend build_insurance_presentation.py or create new script for PowerPoint additions
- Script naming (new standalone script or extension of existing Phase 5/6 scripts)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing insurance pipeline
- `src/report/encounter_payer_summary.py` — Payer derivation logic, ±30 day window function (_payer_mode_in_window), treatment date sources, ENROLLMENT filtering
- `scripts/build_insurance_by_treatment.py` — Phase 5 table rendering (PNG, HTML, CSV), color palette, payer category order, visual style reference
- `scripts/build_post_treatment_insurance.py` — Phase 6 post-treatment payer computation, N/A row handling

### Enrollment data
- `src/validate/schemas.py` — ENROLLMENT_EXPECTED schema (ENR_START_DATE, ENR_END_DATE)
- `src/clean/harmonize.py` — Existing enrollment coverage check logic (_con_outside_enrollment flag)

### Presentation
- `scripts/build_insurance_presentation.py` — Phase 7 PowerPoint generation (UF branding, native tables, slide structure)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_payer_mode_in_window()` in encounter_payer_summary.py — computes mode payer in ±N day window; can be used to verify window dates
- `PAYER_CATEGORY_ORDER`, `PAYER_COLORS`, `HEADER_COLOR` in build_insurance_by_treatment.py — reuse for visual consistency
- `flag_encounters_outside_enrollment()` in harmonize.py — existing ENR date overlap logic (single-period check, but pattern is reusable)
- `encounter_payer_summary.parquet` — already has all PAYER_CATEGORY_AT_* columns and treatment dates/flags
- ENROLLMENT table in cleaned Parquet — has ENR_START_DATE, ENR_END_DATE per patient (multiple rows possible)

### Established Patterns
- Phase 5/6 scripts: standalone scripts in scripts/ that read from derived/ Parquet and write to reports/ subdirectory
- PNG rendering: matplotlib with seaborn Pastel1 palette, non-interactive Agg backend
- HTML: self-contained with inline CSS matching PNG colors
- PowerPoint: python-pptx with UF Health branding (#003087 blue, #FA4616 orange), native tables

### Integration Points
- Input: `derived/encounter_payer_summary.parquet` (PAYER_CATEGORY_AT_* columns, treatment dates, treatment flags)
- Input: `cleaned/ENROLLMENT.parquet` (ENR_START_DATE, ENR_END_DATE per patient)
- Output: `reports/insurance_enr_comparison/` (new directory)
- PowerPoint: extend or rebuild `reports/insurance_tables_YYYY-MM-DD.pptx`

</code_context>

<specifics>
## Specific Ideas

- The key insight is splitting patients by enrollment coverage to understand whether payer classifications at treatment are reliable (enrolled patients) vs potentially missing data (unenrolled)
- The Unknown post-treatment analysis is diagnostic — it answers "are these patients actually missing encounters, or are they missing payer info on encounters they do have?"
- Tables should be presentable alongside Phase 5/6 tables in the same PowerPoint

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-look-at-insurance-in-treatment-windows-but-do-a-comparison-of-people-whose-enr-dates-where-within-the-timeframe-vs-those-that-weren-t*
*Context gathered: 2026-03-24*
