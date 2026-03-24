---
phase: 8
slug: look-at-insurance-in-treatment-windows-but-do-a-comparison-of-people-whose-enr-dates-where-within-the-timeframe-vs-those-that-weren-t
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `tests/` directory (existing) |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | ENR coverage | unit | `pytest tests/test_enr_coverage.py -v` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | Comparison tables | integration | `python scripts/build_enr_comparison_tables.py && ls reports/insurance_enr_comparison/` | ❌ W0 | ⬜ pending |
| TBD | 02 | 2 | Unknown diagnostic | unit | `pytest tests/test_unknown_diagnostic.py -v` | ❌ W0 | ⬜ pending |
| TBD | 03 | 3 | PowerPoint | manual | visual inspection | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_enr_coverage.py` — stubs for enrollment union coverage algorithm
- [ ] `tests/test_unknown_diagnostic.py` — stubs for Unknown post-treatment encounter breakdown
- [ ] Fixtures for synthetic enrollment + encounter_payer_summary data

*Existing pytest infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PNG visual style matches Phase 5/6 | D-20 | Visual comparison | Compare color palette, fonts, layout side-by-side |
| PowerPoint slide layout | D-22 | Visual/layout check | Open PPTX, verify slides are readable and branded |
| HTML rendering | D-19 | Browser rendering | Open HTML files, verify styling matches PNG |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
