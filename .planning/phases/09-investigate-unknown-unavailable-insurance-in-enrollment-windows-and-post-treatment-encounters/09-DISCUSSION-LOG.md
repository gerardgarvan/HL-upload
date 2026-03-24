# Phase 9: Investigate Unknown/Unavailable Insurance - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 09-investigate-unknown-unavailable-insurance-in-enrollment-windows-and-post-treatment-encounters
**Areas discussed:** Output format, Counting rules, Per-treatment vs combined, SCT discrepancy

---

## Output Format

| Option | Description | Selected |
|--------|-------------|----------|
| Diagnostic script | Standalone Python script that prints findings to console + writes summary markdown report. No PNG/HTML/slides. | ✓ |
| Full table pipeline | Formal tables like Phases 5-8 with PNG, HTML, CSV, and PowerPoint slides. | |
| Jupyter notebook | Interactive notebook for exploring data and iterating on analysis. | |

**User's choice:** Diagnostic script
**Notes:** Quick to build, answers the questions directly.

### Follow-up: Report file

| Option | Description | Selected |
|--------|-------------|----------|
| Console + markdown report | Print findings AND write reports/phase9_diagnostic.md | ✓ |
| Console only | Just print findings, disposable output. | |

**User's choice:** Console + markdown report

---

## Counting Rules

| Option | Description | Selected |
|--------|-------------|----------|
| Report findings only | Just report numbers; don't change Phases 5-8 tables. | ✓ |
| Recommend exclusions | Produce recommendation with specific exclusion criteria. | |
| Flag but include | Keep everyone but add SHOULD_EXCLUDE flag column. | |

**User's choice:** Report findings only

### Follow-up: Unknown vs Unavailable grouping

| Option | Description | Selected |
|--------|-------------|----------|
| Separate | Report Unknown and Unavailable as distinct groups. | ✓ |
| Combined | Group Unknown + Unavailable together. | |

**User's choice:** Separate

### Follow-up: Treatment date reference

| Option | Description | Selected |
|--------|-------------|----------|
| Treatment-specific date | Use LAST_CHEMO_DATE for chemo, LAST_RADIATION_DATE for radiation, etc. | ✓ |
| Overall last treatment date | Use max(all treatment dates) for all cohorts. | |

**User's choice:** Treatment-specific date

---

## Per-Treatment vs Combined (Enrollment Cross-Reference)

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, cross-reference | Show ENR coverage vs not for Unknown/Unavailable patients per treatment type. | ✓ |
| No, just encounter presence | Only report encounter presence after treatment. | |

**User's choice:** Yes, cross-reference

### Follow-up: Enrollment window type

| Option | Description | Selected |
|--------|-------------|----------|
| ±30d treatment window | Reuse Phase 8's window logic for direct comparability. | ✓ |
| Any enrollment | Just check if patient has any ENROLLMENT records at all. | |

**User's choice:** ±30d treatment window

---

## SCT Discrepancy

| Option | Description | Selected |
|--------|-------------|----------|
| Full patient trace | Identify the 4 patients, show encounters, SCT dates, derived payer. | ✓ |
| Summary explanation | Just report the likely reason without per-patient detail. | |
| You decide | Claude determines depth based on data. | |

**User's choice:** Full patient trace

### Follow-up: Report inclusion

| Option | Description | Selected |
|--------|-------------|----------|
| Include in report | Show per-patient table with IDs, payers, dates in markdown. | ✓ |
| Summarize only | Explain pattern in prose only. | |

**User's choice:** Include in report

---

## Claude's Discretion

- Script naming and organization
- Exact markdown report structure
- Whether to import Phase 8 functions or recompute inline
- Presentation of enrollment cross-reference findings
- Encounter count bin sizes

## Deferred Ideas

None — discussion stayed within phase scope
