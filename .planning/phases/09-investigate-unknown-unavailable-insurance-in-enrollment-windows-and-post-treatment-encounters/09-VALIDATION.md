---
phase: 9
slug: investigate-unknown-unavailable-insurance-in-enrollment-windows-and-post-treatment-encounters
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `pyproject.toml` or existing pytest config |
| **Quick run command** | `python -m pytest tests/test_phase9_diagnostic.py -x -q` |
| **Full suite command** | `python -m pytest tests/test_phase9_diagnostic.py -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_phase9_diagnostic.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/test_phase9_diagnostic.py -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | D-01 | integration | `python scripts/phase9_insurance_diagnostic.py && test -f reports/phase9_insurance_diagnostic.md` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 1 | D-04,D-05 | unit | `python -m pytest tests/test_phase9_diagnostic.py::test_separate_unknown_unavailable -v` | ❌ W0 | ⬜ pending |
| 09-01-03 | 01 | 1 | D-06 | unit | `python -m pytest tests/test_phase9_diagnostic.py::test_treatment_specific_dates -v` | ❌ W0 | ⬜ pending |
| 09-01-04 | 01 | 1 | D-07,D-08,D-09 | unit | `python -m pytest tests/test_phase9_diagnostic.py::test_enrollment_crossref -v` | ❌ W0 | ⬜ pending |
| 09-01-05 | 01 | 1 | D-10,D-11,D-12 | unit | `python -m pytest tests/test_phase9_diagnostic.py::test_sct_patient_trace -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_phase9_diagnostic.py` — stubs for D-01 through D-12
- [ ] Test fixtures with synthetic encounter_payer_summary, ENROLLMENT, ENCOUNTER data

*Existing pytest infrastructure covers framework; only test file stubs needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Markdown report readability | D-03 | Subjective formatting quality | Review `reports/phase9_insurance_diagnostic.md` sections match 5 questions |
| SCT discrepancy explanation | D-12 | Requires domain judgment | Verify explanation makes sense given patient traces |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
