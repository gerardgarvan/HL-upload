# Phase 7: Present Insurance Tables in Nice PowerPoint - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Assemble the insurance summary tables from Phases 5 and 6 into a polished, UF-branded PowerPoint presentation using python-pptx. The script reads existing report data (CSVs from reports/insurance_by_treatment/ and reports/post_treatment_insurance/) and produces a .pptx file. No new analysis or data processing — presentation layer only.

</domain>

<decisions>
## Implementation Decisions

### Slide organization
- Group by treatment type: all chemo tables together (Phase 5 chemo + Phase 6 chemo), then radiation, then SCT
- Title slide first with presentation title and high-level cohort sizes (total N, chemo N, radiation N, SCT N)
- Overview table (all treatments combined, Phase 5) immediately after title slide, before treatment-specific groups
- No section divider slides — each table slide has a descriptive title that provides context
- No final summary/conclusions slide — presentation ends after the last table

### Visual design
- UF Health branded: UF blue (#003087) and orange (#FA4616) color scheme applied to fresh layout (no external template file)
- Native PowerPoint tables (not embedded PNG images) — cells, borders, colors built with python-pptx for editability
- UF-branded table row colors (blue/orange tones) instead of the seaborn Pastel1 palette used in Phase 5/6 PNGs
- Professional, institutional look consistent with UF Health presentations

### Content & annotations
- Each table slide has a title and a brief one-line subtitle/caption explaining what the table shows
- Cohort size (N=X) in the subtitle, not the title — keeps titles clean (e.g., title: "Chemotherapy Insurance", subtitle: "N = 1,234 patients")
- Minimal footnotes — small text at bottom only where genuinely needed for key definitions or caveats
- No key findings callouts or narrative beyond subtitle

### Output & workflow
- Script integrated into pipeline — reads from reports/ outputs, can be re-run anytime data updates
- Output saved to reports/insurance_tables_YYYY-MM-DD.pptx (date-stamped)
- Uses python-pptx library
- Script location: scripts/build_insurance_presentation.py (follows existing naming convention)

### Claude's Discretion
- Exact UF blue/orange shade mapping to table rows (how to distribute 9 payer categories across the color scheme)
- Font choices and sizes within the UF brand guidelines
- Table cell padding and sizing
- Slide dimensions (standard 16:9 or 4:3)
- Subtitle wording for each table slide

</decisions>

<specifics>
## Specific Ideas

- Tables grouped by treatment type means the slide order is: Title → Overview → Chemo (Phase 5) → Chemo Post-Treatment (Phase 6) → Radiation (Phase 5) → Radiation Post-Treatment (Phase 6) → SCT (Phase 5) → SCT Post-Treatment (Phase 6)
- The combined post-treatment table (Phase 6, which includes N/A row) logically pairs with the overview table
- Existing CSV data in reports/insurance_by_treatment/ and reports/post_treatment_insurance/ has all the N (%) values needed

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-present-insurance-tables-in-nice-powerpoint*
*Context gathered: 2026-03-20*
