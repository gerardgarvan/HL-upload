# Phase 3: Structural Validation & HL Cohort Verification - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Validate that all 22 Parquet files match the expected PCORnet CDM v6.1 schema, verify PATID and ENCOUNTERID referential integrity across tables, confirm the HL cohort definition (expected ~9,331 patients with C81*/201* at 2+ encounters on different dates), and profile per-column completeness stratified by partner. This phase is purely diagnostic — it reports problems but does not modify data (data fixes belong to Phases 4-5).

</domain>

<decisions>
## Implementation Decisions

### CDM Schema Reference
- **Source for expected columns:** Parse from DatasetCoverPage variable lists that came with the data extract. Do not hardcode from the official CDM documentation.
- **Extra columns (in data but not in CDM):** Warn and keep — flag in the report but leave them in the Parquet files.
- **Missing columns (expected but absent):** Warn only — note in the report, do not add empty placeholder columns.
- **TUMOR_REGISTRY schema:** Do not validate against CDM spec (they follow NAACCR, not PCORnet). Just verify column counts match expectations (~265, ~120, ~120) and that key cancer staging variables are present.

### HL Cohort Verification
- **Diagnosis code matching:** Use an exact code list enumerating all valid C81.x and 201.x subcodes, not a loose prefix match.
- **DX_TYPE filter:** Match by code prefix alone — do not require DX_TYPE=10 for ICD-10 or DX_TYPE=09 for ICD-9. DX_TYPE may be missing for some partners. Report any DX_TYPE mismatches found (e.g., C81 code with DX_TYPE=09) but don't use them to exclude records.
- **2+ encounters rule:** Check both ways — (1) 2+ distinct DX_DATE values with HL codes, and (2) 2+ distinct ADMIT_DATEs from ENCOUNTER where linked HL DX exists. Report any differences between the two methods.
- **Count mismatch handling:** Investigate if the verified count doesn't match 9,331. Break down where the discrepancy comes from (which partners, which ICD version, which date range). The user notes that the ENROLLMENT dataset already doesn't have 9,331 unique patients — investigate this too.
- **Enrollment cross-check:** Deep investigation — report how many HL patients have enrollment records and coverage periods, AND check if uncovered patients cluster in specific partners or time periods.
- **ICD version flag:** Add a flag column to the cohort summary — ICD9_ONLY, ICD10_ONLY, or BOTH — for each patient.

### Validation Report Format
- **Report format:** Markdown (.md) — readable in GitHub and editors, easy to generate.
- **Per-partner detail:** Heatmap-style — partners as rows, columns as columns, color-coded completeness. (In markdown, approximate with symbols like full/half/empty blocks or percentage coloring.)
- **Completeness CSV structure:** Claude's discretion on row granularity.
- **Small-cell suppression:** Flag cells that would need suppression if published, but show actual counts. These are internal QC reports, not publishable outputs.

### Integrity Failure Handling
- **Orphan patient IDs (clinical tables with IDs not in DEMOGRAPHIC):** Flag and report — count orphans per table, list in report, but keep them in the data.
- **Orphan encounter IDs (event tables with ENCOUNTERIDs not in ENCOUNTER):** Flag and report — count per table, note in report.
- **CHP LAB_RESULT_CM exception:** Skip ENCOUNTERID check for CHP lab records — document as known limitation from DatasetCoverPage.
- **Phase 3 is diagnostic only:** Do NOT modify Parquet files or drop records. Report problems. Phases 4-5 handle data fixes.

### Claude's Discretion
- Completeness CSV row granularity (per table+column+partner vs per table+column)
- Internal report organization (single large report vs multiple focused reports)
- Heatmap symbols for markdown completeness display

</decisions>

<specifics>
## Specific Ideas

- The user has observed that ENROLLMENT doesn't have 9,331 unique patients — this is a known discrepancy that needs investigation as part of cohort verification. The gap could be partner-specific (some partners don't contribute enrollment data) or time-period-specific.
- Some partners (AMS) mapped ICD-9 to ICD-10 for all diagnoses — the ICD version flag should account for this (these patients may appear as ICD10_ONLY even though their historical records were originally ICD-9).
- CHP is known to have no ENCOUNTERID in LAB_RESULT_CM — skip this specific check.
- Partners BND, UCI, UMI have no payer data — completeness heatmap should make this visible.
- FLM is claims-only, VRT is death-data-only — these partners will show very different completeness profiles.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-structural-validation-hl-cohort-verification*
*Context gathered: 2026-02-27*
