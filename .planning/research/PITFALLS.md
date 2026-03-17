# Pitfalls Research

**Domain:** Clinical data pipeline hardening & documentation
**Researched:** 2026-03-17
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Documenting Without Understanding First

**What goes wrong:**
You add docstrings that describe what the code does literally ("joins two DataFrames") without understanding the clinical rationale. Documentation looks complete but doesn't help anyone understand why the logic exists.

**Why it happens:**
Pressure to document everything fast. Treating documentation as a checkbox exercise.

**How to avoid:**
Read and understand each function before documenting. Ask "why does this logic exist?" not "what does this code do?" If you can't explain the why, flag it as needing review.

**Warning signs:**
Docstrings that repeat the function name. Comments that describe syntax, not intent. "TODO: understand this" appearing frequently.

**Phase to address:** Phase 1 (documentation) — take time to understand before writing

---

### Pitfall 2: Tests That Pass But Don't Validate Correctness

**What goes wrong:**
Tests check that code runs without errors but don't verify output values. Payer logic tests assert "returns a DataFrame" instead of "patient X with codes 14+141 is classified as dual-eligible."

**Why it happens:**
Writing tests for functions with complex clinical logic is hard. Easier to test structure than content.

**How to avoid:**
For each test, define expected output from first principles (clinical definitions), then verify the code produces it. Use concrete patient scenarios: "Patient with Medicare primary, Medicaid secondary → dual-eligible."

**Warning signs:**
Tests with no `assert` on specific values. Tests that only check `len(result) > 0`. Tests that pass after intentionally breaking logic.

**Phase to address:** Phase 3 (test coverage) — require value-level assertions

---

### Pitfall 3: Breaking Working Pipeline During Hardening

**What goes wrong:**
Adding validation, refactoring for testability, or changing function signatures breaks the existing working pipeline. You end up debugging your changes instead of improving quality.

**How to avoid:**
- Never change function signatures or behavior — only add docstrings, tests, and validation
- Run full pipeline after each change to verify output is identical
- Keep a "golden" copy of current outputs for regression comparison
- If a function needs refactoring, document it first (so you understand it), test it (so you can verify behavior), THEN refactor

**Warning signs:**
Pipeline output changes after "documentation only" commits. Tests fail on existing code (means tests are wrong, not code). Merge conflicts in core pipeline files.

**Phase to address:** All phases — golden output comparison from Phase 1

---

### Pitfall 4: Inconsistent Small-Cell Suppression Creating HIPAA Risk

**What goes wrong:**
Audit finds that some report outputs suppress counts 1-10 correctly, but others use different thresholds, skip suppression in intermediate files, or expose small cells in figure axis labels. This is a compliance issue, not just a code quality issue.

**Why it happens:**
Suppression logic was added incrementally across scripts by different development phases. No central policy enforcement.

**How to avoid:**
- Audit ALL outputs (CSV, MD, PNG) for small-cell leakage
- Centralize suppression: single `_suppress()` function, single `SMALL_CELL_THRESHOLD` constant
- Add a regression test: scan all report files for raw counts 1-10

**Warning signs:**
Multiple `_suppress()` or suppression functions in different files. Hardcoded threshold values instead of using the constant. Figures with axis values between 1 and 10.

**Phase to address:** Phase 2 (validation/hardening) — dedicated suppression audit

---

### Pitfall 5: Date Parsing Failures That Degrade Silently

**What goes wrong:**
Date detection heuristic fails on a column, falls back to string type, and downstream joins/filters silently produce wrong results because they compare strings instead of dates.

**Why it happens:**
Current fallback strategy is "log and continue as string" — no downstream impact check. A column that was dates-as-strings in one phase becomes a broken join key in another.

**How to avoid:**
- Test date detection with all 3 formats + edge cases (nulls, mixed formats, partial dates)
- Add checkpoint: verify all expected date columns are actually Date type after conversion
- List all date columns explicitly (don't rely solely on regex heuristic)

**Warning signs:**
`file_inventory.csv` showing date columns "detected but not converted." Join results with unexpected null counts. Date filters returning zero rows.

**Phase to address:** Phase 3 (test coverage) — comprehensive date parsing tests + Phase 2 (checkpoint validation)

---

### Pitfall 6: Payer Logic Edge Cases Producing Wrong Classifications

**What goes wrong:**
Effective payer logic has complex fallback chains (primary → secondary → sentinel handling). Edge cases like: patient with NI primary and valid secondary gets classified as "Unknown" instead of using the secondary.

**Why it happens:**
Fallback logic was built incrementally. Each new case (dual-eligible, sentinel values, missing data) added a branch without comprehensive testing of all combinations.

**How to avoid:**
- Enumerate all payer code combinations systematically (primary × secondary × sentinel)
- Write parameterized tests covering every path
- Document the decision tree explicitly in the function docstring

**Warning signs:**
"Unknown" payer category counts higher than expected. Dual-eligible counts don't match when computed from different code paths. Insurance summary totals don't match patient-level totals.

**Phase to address:** Phase 3 (test coverage) — systematic payer logic testing

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Print-based logging | Simple, works now | Hard to filter, no levels, no timestamps | Acceptable for HPC batch jobs; upgrade if pipeline grows |
| pandas in outcomes_flags.py | Quick fix for CSV parsing | Mixed framework complicates testing and docs | Acceptable; isolate and document why |
| Regex-based date detection | Handles unknown schemas | Fragile on edge cases, silent fallback | Replace with explicit date column list for known tables |
| Duplicated _suppress() | Each script self-contained | Inconsistent behavior across scripts | Never — centralize immediately |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Collecting lazy frames too early | High memory usage, slow phases | Keep lazy until final write | > 1M rows per table |
| Many-to-many joins without filtering first | Cartesian explosion, OOM on HPC | Filter to HL cohort before joining | Any encounter-diagnosis join |
| Loading all 22 tables when only 5 needed | Slow startup, wasted I/O | Load only tables needed per phase | When source data grows |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Small cells in intermediate Parquet files | Raw counts accessible if files shared | Keep Parquet on secure filesystem; suppression in reports only |
| HIPAA-sensitive paths in config | Config file committed with HPC paths containing researcher names | Use environment variables or relative paths; don't commit absolute HPC paths |
| Patient IDs in error messages | PII in logs if pipeline fails mid-run | Sanitize error messages; log counts not IDs |

## "Looks Done But Isn't" Checklist

- [ ] **Docstrings:** Often missing Args/Returns sections — verify every public function has complete signature docs
- [ ] **Tests:** Often test happy path only — verify edge cases (nulls, empty DataFrames, single-row inputs)
- [ ] **Suppression:** Often applied to tables but not figures — verify PNG charts don't show small cells
- [ ] **Setup docs:** Often assume reader's environment matches author's — verify a fresh clone + instructions actually works
- [ ] **Validation:** Often checks input but not output — verify phase output validation exists, not just input validation
- [ ] **Config validation:** Often validates structure but not content — verify file paths exist and are accessible

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Broke working pipeline | LOW | Git revert; compare outputs to golden files |
| Wrong payer classifications | MEDIUM | Identify affected patients; rerun from clean phase |
| Small-cell leakage in shared reports | HIGH | Identify and recall shared outputs; audit all report files; centralize suppression |
| Silent date parsing failure | HIGH | Re-examine all joins using date columns; rerun conversion with explicit date list |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Documenting without understanding | Phase 1 (Documentation) | Docstrings explain "why" not just "what" |
| Tests that don't validate | Phase 3 (Testing) | Every test has value-level assertions |
| Breaking working pipeline | Phase 1 (Golden output) | Pipeline output matches golden files after each phase |
| Inconsistent suppression | Phase 2 (Validation) | Suppression audit passes; single _suppress() function |
| Silent date parsing | Phase 2-3 (Validation + Tests) | All date columns verified as Date type; edge case tests pass |
| Payer logic edge cases | Phase 3 (Testing) | Parameterized tests for all payer code combinations |

## Sources

- PCORnet CDM data quality best practices
- HIPAA small-cell suppression guidance
- Clinical data pipeline post-mortems (common failure modes)
- Python testing best practices (pytest documentation)

---
*Pitfalls research for: clinical data pipeline hardening*
*Researched: 2026-03-17*
