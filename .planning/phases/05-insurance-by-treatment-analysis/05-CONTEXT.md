# Phase 5: Insurance by Treatment Analysis - Context

**Gathered:** 2026-03-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the existing `scripts/build_insurance_summary.py` with a new script that produces presentation-ready summary tables of insurance coverage patterns stratified by treatment type (chemotherapy, radiation, SCT). The upstream data source (`encounter_payer_summary.parquet`) may need to be audited to confirm it has the right columns, but the pipeline assembly logic itself is not in scope for changes unless columns are missing.

</domain>

<decisions>
## Implementation Decisions

### Existing script disposition
- Replace `scripts/build_insurance_summary.py` entirely with a new implementation
- The current output (CSVs, markdown, charts) has wrong structure, missing analyses, and wrong format
- New script reads from `encounter_payer_summary.parquet` (same data source, pending audit of column sufficiency)

### Table structure
- Rows: One row per payer category (Medicare, Medicaid, Dual eligible, Private, Other government, Self-pay, Other, Unavailable, Unknown)
- Columns per table: Primary insurance (mode), Insurance at first treatment, Insurance at last treatment
- Cell values: N (%) format, e.g. "45 (23.4%)"
- No total row, no total column
- Cohort size in table header, e.g. "Chemotherapy Cohort (N=192)"
- Three separate treatment-specific tables (chemo, radiation, SCT) PLUS a combined overview table
- No payer transition analysis — just snapshots at each timepoint

### Output formats (all three required)
- **PNG images**: Color-coded tables (by payer category or treatment type) for easy paste into presentation slides
- **CSV + markdown**: CSV for data, markdown for readable preview
- **HTML**: Styled HTML tables for screenshot or paste

### Visual style
- Colorful, presentation-appropriate — color-coded by payer category or treatment type for visual impact
- No bar charts or other visualizations — tables only

### HIPAA suppression
- No small-cell suppression — show all counts as-is (internal/working tables, not for publication)

### Statistical detail
- N (%) only — no confidence intervals, no statistical tests

### Claude's Discretion
- Specific color palette for payer categories
- PNG rendering approach (matplotlib table, plotly, or other)
- HTML styling details
- Whether to audit/modify upstream encounter_payer_summary.parquet or just use existing columns
- Script naming and module organization

</decisions>

<specifics>
## Specific Ideas

- Tables are for presentation slides — visual clarity and paste-ability are key
- The existing `encounter_payer_summary.parquet` already has `PAYER_CATEGORY_PRIMARY`, `PAYER_CATEGORY_AT_FIRST_CHEMO`, `PAYER_CATEGORY_AT_LAST_CHEMO`, `PAYER_CATEGORY_AT_FIRST_RADIATION`, `PAYER_CATEGORY_AT_LAST_RADIATION`, `PAYER_CATEGORY_AT_FIRST_SCT`, `PAYER_CATEGORY_AT_LAST_SCT` columns plus `HAD_CHEMO`, `HAD_RADIATION`, `HAD_SCT` treatment flags
- Current pipeline uses 9 payer categories: Medicare, Medicaid, Dual eligible, Private, Other government, Self-pay, Other, Unavailable, Unknown

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-insurance-by-treatment-analysis*
*Context gathered: 2026-03-18*
