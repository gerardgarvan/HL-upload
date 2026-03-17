# Phase 1: Documentation & Baseline - Context

**Gathered:** 2026-03-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Document the existing pipeline logic and capture golden output baselines for regression protection. The pipeline transforms raw clinical CSVs through loading, cleaning, transformation, and reporting stages. This phase adds documentation and captures baselines — no behavioral changes to the pipeline itself.

</domain>

<decisions>
## Implementation Decisions

### Docstring depth
- Google-style docstrings on ALL functions (public, private, helpers — no exceptions)
- Brief clinical rationale: one sentence of "why" in the docstring (e.g., "Derives effective payer because dual-eligible patients need primary payer for billing"), with full clinical context reserved for PIPELINE.md
- Side effects (file writes, DataFrame mutations, prints) mentioned naturally in the description paragraph, not a separate section
- Parameters, returns, and types documented for every function

### Pipeline doc structure
- Claude decides the overall organization based on what fits the codebase best
- Include Mermaid diagrams for data flow visualization (renders on GitHub)
- Summary-level descriptions in the main flow, with linked/expandable sections for column-level detail (columns, dtypes, shape changes per stage)
- Known quirks and gotchas collected in a separate "Known Issues" section at the end, not inline with the main flow

### Golden output strategy
- Store checksums (SHA256), schemas (columns + dtypes), and row counts in a committed manifest — no actual patient data in the repo
- Real output files captured locally but gitignored — enables local regression comparison without PHI exposure
- Automated capture script (e.g., `scripts/capture_golden.py`) that reads existing pipeline outputs and records the manifest; rerunnable when baseline needs updating
- Claude decides which pipeline outputs get golden file treatment based on regression detection value

### Handling unknowns
- Both: TODO(audit) comments in source code for local visibility + collected list in `docs/AUDIT_LOG.md` for overview
- Claude categorizes unknowns by severity based on potential impact to data correctness
- Hardcoded values (magic numbers, sentinel values like 999, filter thresholds): research and explain with best-guess documentation, flagging confidence level
- Document actual behavior in docstrings (what the code DOES), not intended behavior — flag suspected bugs separately
- Claude decides when to check git history for context on unclear code
- Claude decides whether to include recommended actions in audit log entries

### Claude's Discretion
- Overall PIPELINE.md organization structure (narrative vs phase-by-phase vs module-by-module)
- Which specific pipeline outputs get golden file treatment
- Severity categorization for unknowns (HIGH/MEDIUM/LOW based on data correctness impact)
- Whether to include recommended actions in audit log entries
- When to consult git history for context
- How unknowns feed into Phase 2/3 planning

</decisions>

<specifics>
## Specific Ideas

- Payer logic (effective payer derivation, dual-eligible detection, fallback chains) and date parsing (3 formats, mixed-format columns, tumor registry format) are known complex areas — expect heavy documentation and audit flagging there
- User values data correctness above all else — documentation should make correctness verifiable
- Pipeline handles clinical/PHI data — golden outputs must never expose patient data in the repository

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-documentation-baseline*
*Context gathered: 2026-03-17*
