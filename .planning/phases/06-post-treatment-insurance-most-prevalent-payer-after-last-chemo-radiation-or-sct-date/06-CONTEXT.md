# Phase 6: Post-Treatment Insurance - Context

**Gathered:** 2026-03-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Derive the most prevalent (mode) payer category from encounters occurring after a patient's last treatment date, and produce summary tables showing post-treatment insurance distributions. The last treatment date is the maximum of last chemo, last radiation, and last SCT dates (nulls ignored). Output is a new standalone set of tables — not added as columns to the Phase 5 tables.

</domain>

<decisions>
## Implementation Decisions

### Post-treatment date logic
- Last treatment date = max(LAST_CHEMO_DATE, LAST_RADIATION_DATE, LAST_SCT_DATE), nulls ignored
- Single date per patient across all treatment types (not per-treatment-type windows)
- Post-treatment period starts immediately after last treatment date (no buffer/gap)
- Any encounter with ADMIT_DATE > last_treatment_date counts as post-treatment

### Output destination
- Separate standalone table(s) — NOT added as a column to existing Phase 5 tables
- One combined table for all patients who had any treatment, PLUS per-cohort breakdowns (chemo, radiation, SCT)
- So 4 tables total: combined post-treatment, post-treatment for chemo cohort, radiation cohort, SCT cohort
- Same 3 output formats as Phase 5: PNG (color-coded), CSV + markdown, HTML (styled)
- Same visual style, colors, and layout as Phase 5 tables

### Edge cases
- Patients with no encounters after last treatment: count under "Unknown" payer category
- Patients with no treatment at all (HAD_CHEMO=0, HAD_RADIATION=0, HAD_SCT=0): include in combined table with payer marked as N/A
- One post-treatment encounter is sufficient — no minimum threshold

### Payer selection rule
- Mode (most frequent) payer category across all post-treatment encounters — same approach as Phase 5
- No time cap — all encounters after last treatment count, even years later
- No HIPAA small-cell suppression — show all counts as-is (internal working tables)

### Table structure
- Same structure as Phase 5 tables: 9 payer category rows (+ N/A row for no-treatment patients in combined table)
- Single column per table: "Post-Treatment Insurance" showing N (%) format
- Cohort size in table header, e.g., "Post-Treatment: Chemotherapy Cohort (N=XXX)"

### Claude's Discretion
- Whether to compute post-treatment payer in the existing encounter_payer_summary.py or inline in the script
- Script organization (extend build_insurance_by_treatment.py or new script)
- Exact table column header wording
- How to handle the N/A row visually (color, placement)

</decisions>

<specifics>
## Specific Ideas

- Tables should match the Phase 5 visual style exactly so they can be presented together
- The per-cohort breakdowns use the same cohort definitions as Phase 5 (HAD_CHEMO=1, HAD_RADIATION=1, HAD_SCT=1)
- A patient in the chemo cohort table gets their post-treatment payer based on encounters after max(all treatment dates), not just after last chemo

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-post-treatment-insurance-most-prevalent-payer-after-last-chemo-radiation-or-sct-date*
*Context gathered: 2026-03-18*
