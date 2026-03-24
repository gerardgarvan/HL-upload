---
phase: 8
slug: look-at-insurance-in-treatment-windows-but-do-a-comparison-of-people-whose-enr-dates-where-within-the-timeframe-vs-those-that-weren-t
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-24
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + integration tests (script execution + output validation) |
| **Config file** | `tests/` directory (existing) |
| **Quick run command** | `python scripts/build_insurance_enr_comparison.py && python -c "import polars as pl; dx=pl.read_csv('reports/insurance_enr_comparison/dx_enr_comparison.csv'); assert dx.height >= 9; print('PASS')"` |
| **Full suite command** | `pytest tests/ -v && python scripts/build_insurance_enr_comparison.py` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick command (script execution + output validation)
- **After every plan wave:** Run full suite
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | ENR coverage + tables | integration | `python scripts/build_insurance_enr_comparison.py && python -c "..."` (output validation) | ✅ (plan-generated) | ⬜ pending |
| 08-01-02 | 01 | 1 | Visual checkpoint | manual | Human inspection of PNG/HTML outputs | N/A | ⬜ pending |
| 08-02-01 | 02 | 2 | PowerPoint slides | integration | Script execution + PPTX file existence check | ✅ (plan-generated) | ⬜ pending |
| 08-02-02 | 02 | 2 | Visual checkpoint | manual | Human inspection of PPTX | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing pytest infrastructure covers framework needs. No Wave 0 test stubs required.

**Rationale:** Phase 8 is a data analysis/reporting phase. Verification is best served by integration testing — running the actual script and validating output file structure, row counts, and column presence. Unit test stubs for enrollment coverage logic would duplicate the integration test coverage without adding meaningful value for this reporting-focused phase.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PNG visual style matches Phase 5/6 | D-20 | Visual comparison | Compare color palette, fonts, layout side-by-side |
| PowerPoint slide layout | D-22 | Visual/layout check | Open PPTX, verify slides are readable and branded |
| HTML rendering | D-19 | Browser rendering | Open HTML files, verify styling matches PNG |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none — integration tests are plan-generated)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-24 (integration-test-first approach for data analysis phase)
