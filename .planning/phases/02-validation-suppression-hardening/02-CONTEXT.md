# Phase 2: Validation & Suppression Hardening - Context

**Gathered:** 2026-03-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Add validation checkpoints at pipeline phase boundaries to catch silent failures (lost rows, schema drift, bad config), and centralize HIPAA-compliant small-cell suppression into a single function with a single threshold constant. The pipeline phases are: convert (CSV→Parquet) → validate (structural) → clean (dedup/flags) → assemble (patient-level + reports) → insurance summary.

</domain>

<decisions>
## Implementation Decisions

### Failure behavior
- All checkpoint failures are **hard stops** — row-count violations, schema violations, and config errors all raise exceptions and halt the pipeline immediately
- No warning-only mode — if data integrity is compromised, nothing proceeds
- Config validation runs **upfront before any processing** — fail fast at the very start, no partial runs from bad config

### Cleanup on failure
- **Claude's discretion** — Claude decides whether to clean up partial outputs or leave them for debugging, based on what's most practical

### Checkpoint placement
- **Claude's discretion** — Claude identifies which phase boundaries are most at risk for silent data loss and places checkpoints accordingly
- **Claude's discretion** — Claude decides whether checkpoints are embedded in scripts or implemented as a separate validation layer, based on existing codebase structure

### Row-count validation
- **Claude's discretion** — Claude picks the check approach (full accounting vs. no-vanish) that best matches data correctness goals

### Schema validation
- **Claude's discretion** — Claude decides whether schema expectations are hardcoded or snapshot-based, based on PCORnet CDM evolution patterns

### Suppression centralization
- **Claude's discretion** — Claude picks whether to use a single utility function or post-processing pass, based on how current report code is structured
- Zero counts (0) are displayed as-is — 0 reveals no individual and is safe
- **Primary suppression only** — no complementary suppression. Most reports don't have row/column totals requiring back-calculation protection
- Threshold is **per-report configurable** — default threshold (10) with ability for reports to override

### Reporting & visibility
- Checkpoint failure messages use **structured log format**: `[CHECKPOINT FAIL] phase=X table=Y expected=N got=M delta=D`
- **Claude's discretion** — whether successful checkpoint passes are also logged (audit trail consideration)
- **Claude's discretion** — whether suppression audit produces a standalone report or log entries
- Config validation on startup **prints a summary on success** — confirms tables found, paths verified, settings loaded

</decisions>

<specifics>
## Specific Ideas

- Error format explicitly requested as machine-parseable structured log lines — suggests HPC/batch context where parsing logs matters
- Config summary on success — user wants visible confirmation that setup is correct before long pipeline runs

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-validation-suppression-hardening*
*Context gathered: 2026-03-17*
