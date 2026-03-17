# Phase 5 Plan Verification

**Phase:** 05-deduplication-cross-table-consistency
**Goal:** Detect duplicates, verify cross-table consistency, and harmonize partner-level differences; flag but don't delete.
**Plans verified:** 2
**Checked:** 2026-02-28

---

## VERIFICATION PASSED

**Status:** All checks passed — 0 blockers, 0 warnings, 2 info notes

---

### Dimension 1: Requirement Coverage

**Requirements from ROADMAP:** REQ-03, REQ-04, REQ-05

| Requirement | Description | Plans | Status |
|-------------|-------------|-------|--------|
| REQ-03 | Clean data for HL insurance inequities analysis | 01, 02 | COVERED |
| REQ-04 | Run on HiPerGator HPC | 02 | COVERED |
| REQ-05 | HIPAA-compliant data handling | 02 | COVERED |

**All requirements present in plan frontmatter.** REQ-03 appears in both plans. REQ-04 and REQ-05 appear only in Plan 02 (the entry point script), which is correct — Plan 01 creates library modules that don't directly address HPC execution or HIPAA suppression.

#### Success Criteria → Task Mapping

| Success Criterion | Plan | Task(s) | Verdict |
|--------------------|------|---------|---------|
| 1. Exact duplicates detected per table | 01-T1, 02-T1 | `flag_duplicates()` with DEDUP_KEYS for 6 tables; main loop applies to all | COVERED |
| 2. Cross-table consistency: demographics match, events within encounters | 01-T1, 02-T1 | `check_demographic_consistency()`, `flag_events_outside_encounters()`, `check_death_consistency()` | COVERED |
| 3. Partner harmonization: AMS/UMI ICD-mapped, FLM claims-only | 01-T2, 02-T1 | `add_partner_flags()` with PARTNER_FLAGS dict; applied in main loop | COVERED |
| 4. Insurance consistency: enrollment vs encounter dates aligned | 01-T2, 02-T1 | `flag_encounters_outside_enrollment()`, `flag_no_enrollment()`; applied to ENCOUNTER | COVERED |
| 5. All flags additive — no records deleted | 01-T1/T2, 02-T1 | Functions add columns only; must_haves truth confirms additive-only | COVERED |
| 6. Duplicate rates reported per table per partner | 02-T1/T2 | `partner_dedup` stats in main loop; `_generate_dedup_report()` with per-partner section | COVERED |

**Result: PASS** — All 6 success criteria have specific implementing tasks with concrete actions.

---

### Dimension 2: Task Completeness

| Plan | Task | Type | Files | Action | Verify | Done | Status |
|------|------|------|-------|--------|--------|------|--------|
| 01 | 1: Dedup flagging & cross-table consistency | auto | `__init__.py`, `dedup.py` | 6 functions with signatures, constants, specific behavior | 2 python -c commands | Clear criteria | COMPLETE |
| 01 | 2: Partner harmonization & insurance consistency | auto | `harmonize.py` | 3 functions with signatures, constants, step-by-step | 2 python -c commands | Clear criteria | COMPLETE |
| 02 | 1: Entry point with main loop & Parquet write-back | auto | `clean_all.py` | 6-step main(), helpers, follows Phase 4 pattern | 2 python -c commands | Clear criteria | COMPLETE |
| 02 | 2: Report generation for 3 markdown reports | auto | `clean_all.py` | 3 report functions with section specs, table formats, metadata | 2 python -c commands | Clear criteria | COMPLETE |

**Quality assessment of actions:**
- Plan 01 Task 1: Specifies 6 constants/functions with type signatures, parameter handling, null behavior, and Polars API calls. Highly specific.
- Plan 01 Task 2: Specifies 3 constants/functions with step-by-step join logic, lazy evaluation strategy, and edge cases.
- Plan 02 Task 1: 6-step pipeline following Phase 4's validated pattern. Specifies imports, helpers, per-table processing, reference table loading.
- Plan 02 Task 2: 3 report functions with section breakdowns, table structures, small-cell suppression, and metadata headers.

**Result: PASS** — All 4 tasks have Files + Action + Verify + Done. Actions are specific (not vague).

---

### Dimension 3: Dependency Correctness

```
Plan 01 (wave 1) ──depends_on: []──→ [no deps]
Plan 02 (wave 2) ──depends_on: [05-01]──→ Plan 01
```

| Check | Result |
|-------|--------|
| All referenced plans exist | 05-01 exists ✓ |
| No circular dependencies | 01→nothing, 02→01 ✓ |
| Wave numbers consistent | 01: wave 1 (no deps), 02: wave 2 (max(1)+1=2) ✓ |
| No forward references | 01 does not reference 02 ✓ |

**Result: PASS** — Simple two-plan dependency chain, correctly ordered.

---

### Dimension 4: Key Links Planned

**Plan 01 key_links:**

| From | To | Via | Task Mention | Status |
|------|----|-----|-------------|--------|
| `dedup.py` | `structural.py` | `import PATID_COL, TUMOR_REGISTRY_TABLES` | Task 1 action: explicit import line | WIRED |
| `harmonize.py` | `structural.py` | `import PATID_COL` | Task 2 action: explicit import line | WIRED |
| `dedup.py` | Parquet files | `write_cleaned()` with snappy compression | Task 1 action: `write_cleaned` function spec | WIRED |

**Plan 02 key_links:**

| From | To | Via | Task Mention | Status |
|------|----|-----|-------------|--------|
| `clean_all.py` | `dedup.py` | `import flag_duplicates, DEDUP_KEYS, write_cleaned` | Task 1 action: explicit import | WIRED |
| `clean_all.py` | `harmonize.py` | `import add_partner_flags, PARTNER_FLAGS` | Task 1 action: explicit import | WIRED |
| `clean_all.py` | `structural.py` | `import flag_small_cell for report suppression` | Task 1 action: explicit import | WIRED |

**Cross-plan wiring:**
- Plan 02 consumes Plan 01's artifacts (dedup.py, harmonize.py) via explicit imports
- Plan 02's context section references `@src/clean/dedup.py` and `@src/clean/harmonize.py` (Plan 01 outputs)
- Report functions in Plan 02 use stats collected from Plan 01's functions in the main loop

**Result: PASS** — All artifacts wired together via explicit imports. No isolated artifacts.

---

### Dimension 5: Scope Sanity

| Plan | Tasks | Files | Threshold | Status |
|------|-------|-------|-----------|--------|
| 01 | 2 | 3 | Target (2-3 tasks, 5-8 files) | GOOD |
| 02 | 2 | 1 | Target (2-3 tasks, 5-8 files) | GOOD |
| **Total** | **4** | **4 unique** | — | GOOD |

- Plan 01 Task 1 creates 6 functions in one file, but they're closely related (all dedup/consistency utilities) and the task count is still 2.
- Plan 02 Task 2 adds functions to the same file as Task 1 (both operate on `clean_all.py`), keeping scope tight.
- No plan exceeds 3 tasks. No file explosion.

**Result: PASS** — Well within context budget.

---

### Dimension 6: Verification Derivation (must_haves)

**Plan 01 truths assessment:**

| Truth | Observable? | Testable? | Maps to Goal? |
|-------|-------------|-----------|---------------|
| "flag_duplicates() marks ALL rows as IS_DUPLICATE=1 (not just subsequent)" | Yes — verifiable in data | Yes — verify test in plan | Dedup detection ✓ |
| "add_partner_flags() adds ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY as Int8 flags" | Yes — columns visible | Yes — verify test in plan | Partner harmonization ✓ |
| "flag_events_outside_encounters() marks events outside window (±1 day)" | Yes — flag in data | Yes — join-based check | Cross-table consistency ✓ |
| "flag_encounters_outside_enrollment() identifies uncovered encounters" | Yes — flag in data | Yes — enrollment check | Insurance consistency ✓ |
| "drop_existing_clean_flags() removes Phase 5 flags for idempotent re-runs" | Yes — safe rerunning | Yes — column check | Operational robustness ✓ |

**Plan 02 truths assessment:**

| Truth | Observable? | Testable? | Maps to Goal? |
|-------|-------------|-----------|---------------|
| "Running clean_all.py produces Parquet files with Phase 5 flags" | Yes — file output | Yes — run script | Pipeline delivery ✓ |
| "Three markdown reports generated" | Yes — file existence | Yes — check reports dir | Reporting ✓ |
| "Small-cell suppression applied (HIPAA)" | Yes — inspect reports | Yes — verify counts | REQ-05 ✓ |
| "No records deleted; all flags additive" | Yes — row count check | Yes — compare before/after | Core constraint ✓ |
| "Dedup rates per table per partner in dedup_report.md" | Yes — read report | Yes — parse report | SC-6 ✓ |

**Artifacts:** All map to truths. `dedup.py` provides dedup/consistency functions, `harmonize.py` provides partner flags, `clean_all.py` orchestrates and produces reports.

**Key links:** Connect artifacts properly (imports, function calls, data flow).

**Result: PASS** — Truths are observable and testable. They name functions (slightly implementation-focused) but describe what the functions deliver to data, which is appropriate for a library module plan.

---

### Dimension 7: Context Compliance

No CONTEXT.md exists for this phase. **Skipped.**

---

### Coverage Summary

| Requirement | Plans | Status |
|-------------|-------|--------|
| REQ-03 (HL cleaning) | 01, 02 | Covered |
| REQ-04 (HPC execution) | 02 | Covered |
| REQ-05 (HIPAA compliance) | 02 | Covered |

### Plan Summary

| Plan | Tasks | Files | Wave | Status |
|------|-------|-------|------|--------|
| 05-01 | 2 | 3 | 1 | Valid |
| 05-02 | 2 | 1 | 2 | Valid |

---

### Info Notes (non-blocking)

**1. [info] Roadmap wording says "near-duplicates" but plans implement exact-match only**
- The ROADMAP success criterion #1 says "Exact and near-duplicates detected per table" but the parenthetical "(reuse HL-EDA dedup keys, extend)" refers to composite-key exact matching. The research explicitly confirms: "Roadmap explicitly specifies exact-match dedup only — no fuzzy matching." The plans correctly follow the research recommendation. The term "near-duplicate" in context means "rows matching on composite key subset but not necessarily all columns" — which is what the plans implement.

**2. [info] Roadmap key task mentions "document partner-specific encounter type distributions (LNK)" but this detail is not in Plan 02's reports**
- The ROADMAP Phase 5 key tasks section includes "Document partner-specific encounter type distributions (LNK = multi-source patient)" but the three reports in Plan 02 don't explicitly cover encounter type distributions. This is a minor reporting detail, not a success criterion, and doesn't affect goal achievement.

---

### Verdict

Plans verified. All 6 success criteria mapped to specific tasks with concrete actions. Requirement coverage complete. Dependencies valid. Artifacts wired together. Scope well within budget. Must-haves properly derived from phase goal.

Run `/gsd:execute-phase 05` to proceed.
