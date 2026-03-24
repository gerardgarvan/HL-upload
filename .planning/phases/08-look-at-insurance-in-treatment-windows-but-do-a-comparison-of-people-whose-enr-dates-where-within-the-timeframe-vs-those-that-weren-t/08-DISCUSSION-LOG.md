# Phase 8: Insurance in Treatment Windows (ENR Comparison) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 08-look-at-insurance-in-treatment-windows-but-do-a-comparison-of-people-whose-enr-dates-where-within-the-timeframe-vs-those-that-weren-t
**Areas discussed:** Treatment window definition, ENR overlap logic, Comparison structure, Cohort scoping, Unknown post-treatment encounters

---

## Treatment Window Definition

| Option | Description | Selected |
|--------|-------------|----------|
| First-to-last treatment span | Window = date range from first treatment to last treatment across all types | |
| Per-treatment ±30 day windows | Reuse existing pipeline logic: ±30 days around each treatment date | ✓ |
| Per-treatment-type span | Window = first to last per treatment type (chemo span, radiation span, SCT span) | |

**User's choice:** Per-treatment ±30 day windows
**Notes:** Reuses existing PAYER_AT_TREATMENT_WINDOW_DAYS=30 from pipeline

| Option | Description | Selected |
|--------|-------------|----------|
| First and last per type | 6 windows: first/last chemo, radiation, SCT | |
| First treatment only | 3 windows: first chemo, radiation, SCT | |
| All including DX | 7 windows: first DX + all 6 treatment windows | ✓ |

**User's choice:** All including DX (7 total windows)

| Option | Description | Selected |
|--------|-------------|----------|
| Keep ±30 days | Same as existing pipeline | ✓ |
| Different window | Specify custom window size | |

**User's choice:** Keep ±30 days

---

## ENR Overlap Logic

| Option | Description | Selected |
|--------|-------------|----------|
| Any overlap | Any enrollment period overlaps even partially with the ±30 day window | |
| Full coverage | Enrollment must fully cover the entire ±30 day window | ✓ |
| Active at treatment date | Enrollment active on exact treatment date only | |

**User's choice:** Full coverage of entire ±30 day window

| Option | Description | Selected |
|--------|-------------|----------|
| Single period must cover | One ENR record must span the full window | |
| Combined coverage OK | Union of all enrollment periods must cover the window | ✓ |

**User's choice:** Combined coverage OK

| Option | Description | Selected |
|--------|-------------|----------|
| Include as not enrolled | Patients with no ENR records go in "not covered" group | ✓ |
| Exclude entirely | Only analyze patients with at least one ENR record | |

**User's choice:** Include as not enrolled

---

## Comparison Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Side-by-side columns | One table with "ENR Covers" and "ENR Not Covers" columns | ✓ |
| Separate tables per group | Two tables per window: enrolled group and not-enrolled group | |
| Three columns with total | Covers, Not Covers, and Total columns | |

**User's choice:** Side-by-side columns

| Option | Description | Selected |
|--------|-------------|----------|
| All 7 separate tables | One table per treatment window | |
| 3 tables per treatment type | First+last combined into one table per treatment type + DX = 4 tables | ✓ |
| You decide | Claude picks best organization | |

**User's choice:** 3 tables per treatment type (4 total: DX, Chemo, Radiation, SCT)

| Option | Description | Selected |
|--------|-------------|----------|
| N per column | Each column header shows its own N | ✓ |
| Total N in title only | Only total cohort N in title | |

**User's choice:** N per column

| Option | Description | Selected |
|--------|-------------|----------|
| Existing pipeline payer | Use PAYER_CATEGORY_AT_* from encounter_payer_summary.parquet | ✓ |
| Enrollment payer | Derive payer from ENROLLMENT table | |
| Primary payer for all | Use PAYER_CATEGORY_PRIMARY for both groups | |

**User's choice:** Existing pipeline payer

| Option | Description | Selected |
|--------|-------------|----------|
| Show as Unknown | Count null-payer patients under Unknown | |
| Show as N/A row | Add N/A row for patients with no payer data | ✓ |
| Exclude from table | Only include patients with non-null payer | |

**User's choice:** Show as N/A row

| Option | Description | Selected |
|--------|-------------|----------|
| Separate reports only | Output to reports/ directory only | |
| Add to PowerPoint too | Add slides to Phase 7 presentation as well | ✓ |

**User's choice:** Add to PowerPoint too

---

## Cohort Scoping

| Option | Description | Selected |
|--------|-------------|----------|
| All HL patients | Every patient with FIRST_HL_DX_DATE | ✓ |
| Only treated patients | Only patients with at least one treatment | |

**User's choice:** All HL patients for DX table

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, treatment-specific | Chemo=HAD_CHEMO=1, Radiation=HAD_RADIATION=1, SCT=HAD_SCT=1 | ✓ |
| All treated patients | All treated in every table | |

**User's choice:** Treatment-specific cohorts (same as Phase 5)

| Option | Description | Selected |
|--------|-------------|----------|
| Exclude if date null | Only include patients with non-null treatment dates | ✓ |
| Include as N/A | Include but mark as unable to determine | |

**User's choice:** Exclude patients with null treatment dates from that type's table

---

## Unknown Post-Treatment Encounters (User-Initiated Addition)

User requested: "I also want to know if those [patients] that are unknown have any encounters past last treatment"

| Option | Description | Selected |
|--------|-------------|----------|
| Include in Phase 8 | Add as additional analysis output | ✓ |
| Separate phase | Defer to Phase 9 | |

| Option | Description | Selected |
|--------|-------------|----------|
| Count breakdown table | How many encounters after last treatment: 0, 1-5, 6+ bins | ✓ |
| Encounter detail summary | Simple N with/without + median count | |
| Payer audit table | Show raw PAYER_TYPE_PRIMARY values for those encounters | |

| Option | Description | Selected |
|--------|-------------|----------|
| Same formats + PowerPoint | PNG, CSV, markdown, HTML + presentation slide | ✓ |
| CSV + markdown only | Data/text output only | |

---

## Claude's Discretion

- Column header wording
- PowerPoint slide organization for new tables
- Encounter count bins for Unknown breakdown
- Script architecture (new vs extend existing)

## Deferred Ideas

None — discussion stayed within phase scope
