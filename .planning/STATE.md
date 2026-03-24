---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
stopped_at: Phase 9 context gathered
last_updated: "2026-03-24T19:00:18.919Z"
progress:
  total_phases: 9
  completed_phases: 5
  total_plans: 23
  completed_plans: 19
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-17)

**Core value:** Data correctness — if the output data is wrong, nothing else matters
**Current focus:** Phase 08 — look-at-insurance-in-treatment-windows-but-do-a-comparison-of-people-whose-enr-dates-where-within-the-timeframe-vs-those-that-weren-t

## Current Position

Phase: 08 (look-at-insurance-in-treatment-windows-but-do-a-comparison-of-people-whose-enr-dates-where-within-the-timeframe-vs-those-that-weren-t) — EXECUTING
Plan: 1 of 2

## Performance Metrics

**Velocity:**

- Total plans completed: 18
- Average duration: 4.0 minutes
- Total execution time: 1.22 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-documentation-baseline | 4 | 30 min | 7.5 min |
| 02-validation-suppression-hardening | 3 | 10 min | 3.3 min |
| 03-test-coverage-fragile-areas | 6 | 21 min | 3.5 min |
| 04-reproducibility-onboarding | 2 | 1.6 min | 0.8 min |
| 05-insurance-by-treatment-analysis | 1 | 2 min | 2.0 min |
| 06-post-treatment-insurance-most-prevalent-payer-after-last-chemo-radiation-or-sct-date | 1 | 3 min | 3.0 min |
| 07-present-insurance-tables-in-nice-powerpoint | 1 | 6 min | 6.0 min |

**Recent Trend:**

- Last 3 plans: 05-01 (2 min), 06-01 (3 min), 07-01 (6 min)
- Trend: All phases complete - presentation layer finalized

*Updated after each plan completion*

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 01-documentation-baseline | P01 | 11 min | 2 tasks | 12 files |
| 01-documentation-baseline | P02 | 11 min | 2 tasks | 9 files |
| 01-documentation-baseline | P05 | 3 min | 2 tasks | N/A |
| Phase 01 P03 | 13 | 2 tasks | 13 files |
| Phase 01-documentation-baseline P04 | 5 | 1 tasks | 1 files |
| Phase 02 P01 | 3 | 2 tasks | 4 files |
| 02-validation-suppression-hardening P02 | 4 | 2 tasks | 10 files |
| Phase 02 P03 | 3 | 2 tasks | 5 files |
| Phase 03-test-coverage-fragile-areas P04 | 3 | 2 tasks | 3 files |
| Phase 03 P01 | 3 | 2 tasks | 2 files |
| Phase 03 P03 | 5 | 3 tasks | 5 files |
| Phase 03-test-coverage-fragile-areas P02 | 6 min | 2 tasks | 3 files |
| Phase 03 P05 | 2 | 2 tasks | 2 files |
| Phase 03-test-coverage-fragile-areas P06 | 6 | 3 tasks | 14 files |
| Phase 04 P01 | 83 | 2 tasks | 2 files |
| Phase 04 P02 | 10 | 2 tasks | 1 files |
| Phase 05-insurance-by-treatment-analysis P01 | 2 min | 2 tasks | 1 files |
| Phase 06-post-treatment-insurance-most-prevalent-payer-after-last-chemo-radiation-or-sct-date P01 | 3 min | 2 tasks | 1 files |
| Phase 06 P01 | 3 | 2 tasks | 1 files |
| Phase 07 P01 | 6 | 2 tasks | 1 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Harden before extending: Pipeline logic is complex and hard to follow; adding features on a shaky foundation compounds problems
- Document for collaborators + future self: Pipeline needs to be reproducible and maintainable by people who didn't write it
- Systematic audit of unknowns: Author suspects problems they're unaware of; proactive review is more efficient than reactive debugging

**From 01-05 (Golden Baseline Capture):**

- SHA256 for checksums per NIST/HIPAA (not MD5/SHA1 which have collision vulnerabilities)
- Manifest in git, actual data files gitignored (PHI protection)
- Network/HPC path handling with graceful fallback to absolute paths
- Priority-based output categorization (HIGH/MEDIUM/LOW) for regression focus
- Support partial pipeline runs (missing directories skipped, empty manifest valid)
- [Phase 01-02]: Documented actual behavior (what code DOES), not intended — per Phase 1 context
- [Phase 01-02]: Added TODO(audit) for 8 unknowns: VITAL dedup, pandas dependency, payer logic assumptions, 30-day windows
- [Phase 01-01]: Document actual behavior, not intended; flag suspected bugs separately with TODO(audit)
- [Phase 01-01]: Side effects in description paragraphs (not separate section) per 01-CONTEXT.md
- [Phase 01-01]: TODO(audit) with severity categorization for Phase 2/3 planning input
- [Phase 01-03]: Google-style docstrings on ALL functions with clinical rationale
- [Phase 01-03]: Both inline TODO(audit) and centralized AUDIT_LOG.md for unknowns
- [Phase 01-documentation-baseline]: Phase-by-phase structure for PIPELINE.md (matches script execution order)
- [Phase 02-01]: Plain Polars dtype dicts for checkpoint validation (not Pandera) - lightweight, zero dependencies
- [Phase 02-01]: Plain pathlib validation for config (not Pydantic) - sufficient for 6 path checks
- [Phase 02-01]: Structured logging format for all validations: [CHECKPOINT PASS/FAIL] phase=X table=Y
- [Phase 02-02]: DEFAULT_THRESHOLD=10 as single source of truth in suppression.py (eliminates threshold drift)
- [Phase 02-02]: Zero counts displayed as-is, not suppressed (reveal no individual-level information)
- [Phase 02-02]: Backward compatible _suppress alias and deprecation comments for safe migration
- [Phase 02-03]: validate_no_vanish instead of validate_row_count for clean_all.py (dedup reduces rows legitimately)
- [Phase 02-03]: Checkpoint after write_cleaned() to validate persisted state, not in-memory state
- [Phase 02-03]: Schema validation only for CRITICAL_SCHEMAS (4 tables), not all 22 tables (execution time vs value tradeoff)
- [Phase 03-04]: Use Polars Series with explicit dtype for test expectations (Int8 matching actual output)
- [Phase 03-04]: Document schema validation behavior rather than adding explicit checks (pandas raises KeyError)
- [Phase 03-04]: Reorganize outcomes tests to align with source module location (src/clean/outcomes_flags.py)
- [Phase 03-01]: Factory fixtures over direct DataFrame fixtures for test data generation
- [Phase 03-01]: AUDIT-005 verified correct (primary 14/141/142 codes set dual_eligible=1 with null secondary)
- [Phase 03-01]: AUDIT-001 documented (99/9999 as Unavailable vs fallback sentinel, INCLUDE_99_AS_SENTINEL=False for data retention)
- [Phase 03]: AUDIT-004 RESOLVED: Polars is_duplicated() treats null == null (nulls DO match duplicates)
- [Phase 03]: AUDIT-007 RESOLVED: Suppression consistency verified - both functions use DEFAULT_THRESHOLD=10
- [Phase 03]: Test strategy: structural validation + spot-checks, not exact value matching (avoids brittleness)
- [Phase 03-test-coverage-fragile-areas]: Parametrized tests for exhaustive edge case coverage — Enables testing all format/case combinations without test duplication
- [Phase 03-test-coverage-fragile-areas]: Document AUDIT items with rationale rather than changing validated behavior
- [Phase 03-05]: Systematic audit resolution: All 18 Phase 1 TODO(audit) items resolved with evidence or clear deferral rationale
- [Phase 03-05]: Complete PCORnet factory fixture set: Added 4 tables (diagnosis, enrollment, vital, procedures) following same pattern for consistency
- [Phase 03-05]: Systematic audit resolution: All 18 Phase 1 TODO(audit) items resolved with evidence or clear deferral rationale
- [Phase 03-05]: Complete PCORnet factory fixture set: Added 4 tables (diagnosis, enrollment, vital, procedures) following same pattern for consistency
- [Phase 03-test-coverage-fragile-areas]: Mirror src/ directory structure in tests/ for test discoverability
- [Phase 03-test-coverage-fragile-areas]: Marker-based test organization (payer, dates, reports, checkpoint) for selective CI/CD execution
- [Phase 04-01]: Two-file environment pattern: keep environment.yml human-editable with loose pins, generate lock file on-demand
- [Phase 04-01]: Comprehensive verification: 6 automated checks covering conda env, Python version, imports, config, compute node, and data access
- [Phase 04-02]: Cookbook-style guide over reference format for step-by-step onboarding clarity
- [Phase 04-02]: Two-tier verification in documentation: quick spot-checks then golden baseline comparison
- [Phase 04-02]: Full scope onboarding guide (pipeline + tests + reports) in single comprehensive SETUP.md
- [Phase 04-02]: HyperGator-only documentation per user decision (no local dev instructions)
- [Phase 05-01]: Graceful degradation for treatment columns — continue with available treatments, only exit if ALL missing
- [Phase 05-01]: No small-cell suppression for insurance analysis tables — internal working tables show all counts as-is
- [Phase 05-01]: Dual CSV structure (raw N/% + formatted N_Pct) enables both analysis and presentation use cases
- [Phase 05-01]: Standard 9-category payer order with Self-pay label (not "No payment / Self-pay")
- [Phase 06]: Post-treatment payer computed inline in script (not added to encounter_payer_summary.py) for single-use analysis
- [Phase 06]: Self-pay label (not 'No payment / Self-pay') for consistency with Phase 5 tables
- [Phase 06]: Post-treatment payer computed inline in script (not added to encounter_payer_summary.py) for single-use analysis
- [Phase 06]: Self-pay label (not 'No payment / Self-pay') for consistency with Phase 5 tables
- [Phase 07-01]: UF Health branding with exact hex colors (#003087 blue, #FA4616 orange) for institutional presentation quality
- [Phase 07-01]: Native PowerPoint tables (not embedded images) for editability and collaboration
- [Phase 07-01]: Blank slide layout (index 6) for full formatting control without template placeholders
- [Phase 07-01]: 16:9 aspect ratio for modern widescreen displays
- [Phase 07-01]: Cohort size N=X in subtitle (not title) for cleaner slide headers

### Roadmap Evolution

- Phase 5 added: Insurance by Treatment Analysis — summary tables of insurance coverage patterns by treatment type (chemo, radiation, SCT)
- Phase 6 added: Post-Treatment Insurance — most prevalent payer after last chemo, radiation, or SCT date
- Phase 7 added: Present insurance tables in nice PowerPoint
- Phase 8 added: Insurance in treatment windows — comparison of patients whose ENR dates were within the timeframe vs those that weren't
- Phase 9 added: Investigate unknown/unavailable insurance in enrollment windows and post-treatment encounters

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-03-24T19:00:18.914Z
Stopped at: Phase 9 context gathered
Resume file: .planning/phases/09-investigate-unknown-unavailable-insurance-in-enrollment-windows-and-post-treatment-encounters/09-CONTEXT.md
