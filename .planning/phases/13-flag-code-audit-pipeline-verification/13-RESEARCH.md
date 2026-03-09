# Phase 13: Flag Code Audit & Pipeline Verification — Research

**Researched:** 2026-03-09
**Domain:** HL pipeline — flag code consistency, survivorship/provider validation, pipeline verification
**Confidence:** HIGH

## Summary

Phase 13 verifies that Phase 12 flag variables (FLAG_HL_DX, FLAG_SURVIVORSHIP_DX, FLAG_CANCER_PROVIDER) use correct, consistent code logic and that the pipeline runs end-to-end. The research identifies a **critical inconsistency**: FLAG_HL_DX uses prefix matching (any 201*, any C81*) while `cohort.py` uses an exact set of 149 codes that excludes ICD-9 201.3x and ICD-10 C81.5x/C81.6x. This phase should align FLAG_HL_DX with cohort logic, document survivorship and oncology code sources, validate oncology keywords against actual data, add regression tests that assert flag-code alignment, and extend smoke tests to cover the full pipeline.

**Primary recommendation:** (1) Align FLAG_HL_DX with `ALL_HL_CODES` / `ALL_HL_NORMALIZED` from `cohort.py` so both use the same 149-code set. (2) Add `test_flag_hl_dx_matches_cohort_codes` that asserts every code in cohort’s HL sets is flagged by add_diagnosis_flags and no excluded codes are flagged. (3) Add a pipeline smoke test that runs convert_all → validate_all → clean_all → assemble_clean in sequence (or a lightweight variant) and optionally validate flag outputs on a small HPC subset.

---

## User Constraints

No CONTEXT.md exists for Phase 13. No locked decisions, discretion areas, or deferred items were provided. Research assumes Phase 12 design (prefix-based FLAG_HL_DX) is revisable for consistency.

---

## What to Verify

| Item | Location | Verification |
|------|----------|--------------|
| **FLAG_HL_DX vs cohort logic** | `flags_diagnosis_provider.py` vs `cohort.py` | FLAG_HL_DX currently uses prefix match; cohort uses exact 149 codes. Align or document divergence. |
| **Survivorship code list** | `flags_diagnosis_provider.py` (SURVIVORSHIP_*) | Document source; validate completeness against study protocol. |
| **Oncology keywords** | `flags_diagnosis_provider.py` (ONCOLOGY_KEYWORDS) | Validate against distinct PROVIDER_SPECIALTY_PRIMARY values in data. |
| **Pipeline order** | `scripts/` | convert_all → validate_all → clean_all → assemble_clean. Verify dependency chain. |
| **Pipeline execution** | Scripts | Smoke test, full pytest, optional HPC subset run. |
| **Flag documentation** | Module docstrings, planning docs | Single traceable doc for all flag code sets. |

---

## Where Flag Codes Live

| Source | Contents |
|--------|----------|
| `src/validate/cohort.py` | `ICD10_HL_CODES`, `ICD9_HL_CODES`, `ALL_HL_CODES`, `ALL_HL_NORMALIZED` — 149 exact HL codes (77 ICD-10, 72 ICD-9) |
| `src/clean/flags_diagnosis_provider.py` | FLAG_HL_DX (prefix 201*/C81*), SURVIVORSHIP_EXACT_ICD9/ICD10, SURVIVORSHIP_PREFIX_ICD10, ONCOLOGY_KEYWORDS |
| `src/report/site_table.py` | Imports `ALL_HL_CODES`, `ALL_HL_NORMALIZED` from cohort for HL DX counting |
| `src/clean/dedup.py` | `CLEAN_FLAG_COLS` includes FLAG_HL_DX, FLAG_SURVIVORSHIP_DX, FLAG_CANCER_PROVIDER |

---

## FLAG_HL_DX vs Cohort Logic — Inconsistency

**cohort.py (exact 149 codes):**

- ICD-10: C81.00–C81.9A, excluding C81.5x and C81.6x → 77 codes
- ICD-9: 201.00–201.98, excluding 201.3x → 72 codes
- Matching: `DX is_in code_set` (dotted or normalized)

**flags_diagnosis_provider.py (prefix match):**

- ICD-10: `dx_norm.str.starts_with("C81")`
- ICD-9: `pl.col("DX").str.starts_with("201")`
- Result: flags 201.3x and C81.5x/C81.6x, which are **excluded** from cohort

**Recommendation:** Use `ALL_HL_CODES` / `ALL_HL_NORMALIZED` from cohort for FLAG_HL_DX so the flag and cohort verification are consistent. If intentional divergence is desired, document it explicitly.

---

## Survivorship Codes — Source and Completeness

**Current list (flags_diagnosis_provider.py):**

- ICD-10 exact: V8741, V8742, V8743, V8746, Z9221, Z9222, Z9223, Z9225, Z923 (normalized, no dots)
- ICD-9 exact: V153
- Prefix: Z08, Z85

**Semantic mapping (verified via ICD references):**

- V87.41/42/43/46: Personal history of antineoplastic chemotherapy, monoclonal therapy, estrogen, immunosuppression
- V15.3: ICD-9 personal history (exact meaning varies; verify against study protocol)
- Z92.21-25, Z92.3: Personal history of chemotherapy, immunotherapy, estrogen, immunosuppression, irradiation
- Z08*: Encounter for follow-up after malignant neoplasm treatment
- Z85*: Personal history of malignant neoplasm

**Recommendation:** (1) Add a short `FLAG_CODES.md` (or equivalent) that cites study protocol for the list. (2) If protocol is unavailable, cite standard ICD-10/ICD-9 references and note V15.3 for review.

---

## Oncology Keywords — Validation Against Data

**Current keywords (flags_diagnosis_provider.py):**

- oncology, medical oncology, radiation oncology, hematology[\-\s]*oncology, hematology/oncology, pediatric oncology

Phase 12 RESEARCH recommended a one-time profile of distinct `PROVIDER_SPECIALTY_PRIMARY` values. This phase should implement that: scan PROVIDER, collect distinct values, and report (a) how many rows match oncology keywords and (b) any values containing "oncolog" or "hematolog" that are not matched — to catch edge cases (e.g., "Clinical Oncology", "Surgical Oncology").

---

## Pipeline Verification

### Pipeline order (from ARCHITECTURE.md, ROADMAP)

1. `convert_all` — CSV → Parquet
2. `validate_all` — structural + cohort verification
3. `clean_all` — dedup, harmonize, diagnosis/provider flags
4. `assemble_clean` — parquet_clean, patient_level, DQ report

### How to run verification

| Type | Command / approach |
|------|--------------------|
| **Smoke test (existing)** | `python scripts/smoke_test.py [config/paths.toml]` — DEMOGRAPHIC only |
| **Full pytest** | `python -m pytest tests/ -v` — unit tests (cohort, flags_diagnosis_provider, etc.) |
| **Pipeline smoke test (new)** | Run convert_all → validate_all → clean_all → assemble_clean in sequence on minimal config; assert exit 0 and expected outputs exist |
| **HPC subset (optional)** | Run full pipeline on a small date/partner subset for end-to-end validation |

---

## Add Validation Tests Asserting Flag–Cohort Alignment

**Recommendation:** Add tests that enforce consistency between flags and cohort:

1. **test_flag_hl_dx_matches_cohort_codes**

   - Sample codes from `ALL_HL_CODES` and `ALL_HL_NORMALIZED`; for each, build a DIAGNOSIS row (with appropriate DX_TYPE) and assert `add_diagnosis_flags` sets FLAG_HL_DX=1.
   - Sample excluded codes (201.30, C81.50) and assert FLAG_HL_DX=0 when aligned with cohort logic.

2. **test_flag_hl_dx_excluded_codes_not_flagged** (if alignment chosen)

   - Assert that 201.3x and C81.5x/C81.6x yield FLAG_HL_DX=0 when using cohort-aligned logic.

3. **test_survivorship_codes** (optional extension)

   - Assert all codes in SURVIVORSHIP_EXACT_* and prefix-covered examples (Z08.0, Z85.3) produce FLAG_SURVIVORSHIP_DX=1.

---

## Standard Stack

| Library | Purpose |
|---------|---------|
| Polars | DataFrame ops, code matching |
| pytest | Test execution |
| Python 3.11 | Runtime |

No new dependencies. Use existing patterns from `test_flags_diagnosis_provider.py` and `test_cohort.py`.

---

## Architecture Patterns

### Pattern: Single Source of Truth for HL Codes

Import `ALL_HL_CODES` and `ALL_HL_NORMALIZED` from `src.validate.cohort` in `flags_diagnosis_provider.py`; use them for FLAG_HL_DX instead of `starts_with`. Detect DX format (dotted vs undotted) or use normalized form consistently. Reuse `normalize_dx` or equivalent for DX normalization.

### Pattern: Pipeline Smoke Test

Create `scripts/pipeline_smoke_test.py` or extend `smoke_test.py` to run the four scripts in order, checking:

1. Config loads
2. Parquet dir exists after convert_all
3. Reports exist after validate_all
4. Flag columns present in DIAGNOSIS/PROVIDER after clean_all
5. parquet_clean/ and patient_level.parquet exist after assemble_clean

Use `subprocess` or direct `main()` calls; optionally use `--dry-run` or minimal data if available.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| HL code set | Duplicate code list | Import from `cohort.py` |
| DX normalization | Custom string logic | `cohort.normalize_dx` or Polars `str.to_uppercase().str.replace_all(r"\.", "")` |
| Flag–cohort consistency | Manual checklist | Automated pytest assertions |

---

## Common Pitfalls

| Pitfall | What goes wrong | How to avoid |
|---------|-----------------|--------------|
| **Prefix vs exact mismatch** | FLAG_HL_DX and cohort disagree on which DX are HL | Use same code set for both |
| **DX format** | Dotted vs undotted DX; cohort uses both forms | Use `detect_dx_format` / normalized set when appropriate |
| **Oncology false negatives** | Specialty strings like "Surgical Oncology" not matched | Profile distinct values; extend keywords if needed |
| **Pipeline order** | Running clean_all before validate_all | Document and enforce order in smoke test |

---

## Code Examples

### FLAG_HL_DX using cohort constants (proposed)

```python
# In flags_diagnosis_provider.py
from src.validate.cohort import ALL_HL_CODES, ALL_HL_NORMALIZED, ICD9_HL_CODES, ICD10_HL_CODES

# Normalize DX for matching
dx_norm = pl.col("DX").fill_null("").str.to_uppercase().str.replace_all(r"\.", "")

# Use exact set: dotted vs normalized depends on data format
# Option A: Detect format (requires diagnosis_path) — not available in add_diagnosis_flags(df)
# Option B: Check both — DX in ALL_HL_CODES (dotted) OR dx_norm in ALL_HL_NORMALIZED
in_hl_set = pl.col("DX").is_in(ALL_HL_CODES) | dx_norm.is_in(ALL_HL_NORMALIZED)

# With DX_TYPE filtering
flag_hl = (
    pl.when(_is_icd9_type() & (pl.col("DX").is_in(ICD9_HL_CODES) | dx_norm.is_in(ICD9_HL_NORMALIZED)))
    .then(pl.lit(1, dtype=pl.Int8))
    .when(_is_icd10_type() & (pl.col("DX").is_in(ICD10_HL_CODES) | dx_norm.is_in(ICD10_HL_NORMALIZED)))
    .then(pl.lit(1, dtype=pl.Int8))
    .otherwise(pl.lit(0, dtype=pl.Int8))
)
```

### Test: assert FLAG_HL_DX aligns with cohort

```python
def test_flag_hl_dx_matches_cohort_codes() -> None:
    from src.validate.cohort import ALL_HL_CODES, ICD9_HL_CODES, ICD10_HL_CODES
    from src.clean.flags_diagnosis_provider import add_diagnosis_flags

    # Sample from cohort — all should yield FLAG_HL_DX=1
    icd9_sample = list(ICD9_HL_CODES)[:3]
    icd10_sample = list(ICD10_HL_CODES)[:3]
    df = pl.DataFrame({
        "ID": ["P"] * 6,
        "DX": icd9_sample + icd10_sample,
        "DX_TYPE": ["09"] * 3 + ["10"] * 3,
        "DX_DATE": [None] * 6,
    })
    result = add_diagnosis_flags(df)
    assert result["FLAG_HL_DX"].sum() == 6

    # Excluded codes — should yield FLAG_HL_DX=0 (if aligned)
    df_excl = pl.DataFrame({
        "ID": ["P", "P"],
        "DX": ["201.30", "C81.50"],
        "DX_TYPE": ["09", "10"],
        "DX_DATE": [None, None],
    })
    result_excl = add_diagnosis_flags(df_excl)
    assert result_excl["FLAG_HL_DX"].sum() == 0
```

---

## Effort Estimate

| Task | Effort |
|------|--------|
| Align FLAG_HL_DX with cohort (import + logic change) | 0.5 day |
| Add test_flag_hl_dx_matches_cohort_codes | 0.25 day |
| Document survivorship codes (FLAG_CODES.md or equivalent) | 0.25 day |
| Profile PROVIDER_SPECIALTY_PRIMARY + validate oncology keywords | 0.5 day |
| Pipeline smoke test (extend or new script) | 0.5 day |
| Run full pytest, smoke test, optional HPC subset | 0.5 day |
| **Total** | **~2.5 days** |

---

## Open Questions

1. **V15.3 semantics**  
   ICD-9 V15.3 can mean different things across references. Confirm intended meaning in study protocol.

2. **FLAG_HL_DX intent**  
   If Phase 12 intentionally used a broader definition (prefix) for exploratory analyses, document that and decide whether to keep divergence or align.

3. **Pipeline smoke test scope**  
   Full run on real data may take hours. Consider a "minimal" mode (e.g., subset of tables) for CI, with full run reserved for manual/HPC validation.

---

## Sources

### Primary (HIGH confidence)

- `src/validate/cohort.py` — ALL_HL_CODES, ICD9/ICD10 sets, exact 149-code definition
- `src/clean/flags_diagnosis_provider.py` — FLAG_HL_DX, survivorship, oncology logic
- `scripts/clean_all.py` — integration of add_diagnosis_flags, add_provider_flags
- `.planning/codebase/ARCHITECTURE.md` — pipeline order

### Secondary (MEDIUM confidence)

- Phase 12 RESEARCH — design rationale, oncology keyword recommendation
- ICD-10/ICD-9 references (web) — survivorship code semantics

### Tertiary (LOW confidence)

- V15.3 exact study-protocol meaning — recommend verification

---

## Metadata

**Confidence breakdown:**

- FLAG_HL_DX vs cohort: HIGH — direct code comparison
- Survivorship codes: MEDIUM — standard ICD references; protocol source not verified
- Oncology keywords: MEDIUM — Phase 12 recommendation; data profiling not yet done
- Pipeline verification: HIGH — scripts and order documented

**Research date:** 2026-03-09  
**Valid until:** ~30 days (stable domain)
