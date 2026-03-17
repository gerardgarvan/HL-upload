# Phase 16: Secondary Payer & Dual-Eligible — Research

**Researched:** 2025-03-16  
**Domain:** Encounter payer logic, secondary payer fallback, dual-eligibility (PCORnet CDM)  
**Confidence:** HIGH

## Summary

Phase 16 extends the encounter-payer summary to use **effective payer** (primary with sentinel fallback to secondary), add **dual-eligible** flags (encounter- and patient-level), and ensure all downstream payer variables (categories, at first DX/chemo, transition) are based on this effective payer. The codebase currently uses only `PAYER_TYPE_PRIMARY` in `src/report/encounter_payer_summary.py`; ENCOUNTER may include `PAYER_TYPE_SECONDARY` (same value set per Phase 4 research). Valuesets (e.g. `hpc-upload/valuesets.csv`) confirm dual-eligibility codes 14, 141, 142; code 41 is Corrections Federal, not dual-eligible.

**Primary recommendation:** Compute one `effective_payer` column per encounter row at read time (sentinel fallback), then add encounter-level and patient-level `DUAL_ELIGIBLE`. Run all existing aggregation and _payer_at_date logic on `effective_payer`. Keep `flag_small_cell` / `_suppress` unchanged.

---

## Effective Payer (Sentinel Fallback)

### Definition

- **Effective payer per encounter** = primary if primary is valid (non-sentinel), else secondary if secondary is valid, else null.
- **Valid** = non-null, non-empty, and not in the sentinel list (see Sentinel List below).

### Where to compute

- **Recommendation:** Compute in one place, per encounter row, **before any group_by or aggregation**.
- **Implementation:** In the first ENCOUNTER scan in `build_encounter_payer_summary`, add a derived column (e.g. `effective_payer`) using a single expression so all downstream logic (N_ENCOUNTERS_WITH_PAYER, PAYER_CATEGORY, _payer_at_date, enc_chemo block) uses this column. Do not duplicate sentinel logic in multiple places.
- **Polars pattern:** Use `pl.when(primary_valid).then(primary).when(secondary_valid).then(secondary).otherwise(pl.lit(None))` (with null-safe checks). If `PAYER_TYPE_SECONDARY` is missing from schema, treat as no secondary: effective_payer = primary (with current valid check only).

### Code references

- `src/report/encounter_payer_summary.py`: `_valid_payer_expr()` currently applies to `PAYER_TYPE_PRIMARY` only (lines 51–55). Extend to a shared “valid” concept for both primary and secondary, then effective_payer expression.
- All `.select(PATID_COL, "ADMIT_DATE", "PAYER_TYPE_PRIMARY")` and filters on `PAYER_TYPE_PRIMARY` must be updated to use `effective_payer` (or the same expression) after it is added to the encounter scan/collect.

---

## Dual-Eligible Definition

### Encounter-level dual-eligible

Set to 1 when any of:

- (a) Primary is Medicare (category or code prefix 1) **and** secondary is Medicaid (category or prefix 2), or  
- (b) Primary is Medicaid **and** secondary is Medicare, or  
- (c) Primary **or** secondary is one of the explicit dual-eligibility codes: **14, 141, 142**.

Otherwise 0 (or null if no payer data).

**PCORnet valueset (verified in `hpc-upload/valuesets.csv`):**

| Code | Description |
|------|-------------|
| 14   | Dual Eligibility Medicare/Medicaid Organization |
| 141  | Dual Eligible Special Needs Plan (D-SNP)        |
| 142  | Fully Integrated Dual Eligible Special Needs Plan (FIDE-SNP) |

**Code 41:** In valuesets, **41 = Corrections Federal** (Other government). It is **not** a dual-eligibility code. Document 41 in codebook/comment for site-specific data if sites use it for dual-eligible; do not treat 41 as dual-eligible in the standard definition.

### Patient-level dual-eligible

- **Recommendation:** Add patient-level **DUAL_ELIGIBLE** to `derived/encounter_payer_summary.parquet`: 1 if the patient has **at least one encounter** with encounter-level dual-eligible = 1, else 0.
- Implementation: After computing encounter-level dual_eligible per row, aggregate by patient: `pl.col("dual_eligible").max()` or `any()` when rolling up to one row per patient; output as integer 0/1.

### Both in output

- **Encounter-level:** Used internally when building the summary (each encounter row has a dual_eligible flag); needed for correct aggregation (e.g. counting dual-eligible encounters).
- **Patient-level:** Add column **DUAL_ELIGIBLE** to the encounter_payer_summary.parquet schema so downstream reports (e.g. `build_insurance_summary.py`) can stratify or report without re-reading ENCOUNTER.

---

## Schema and Column Names

### ENCOUNTER

- **Column name for secondary payer:** **PAYER_TYPE_SECONDARY** (same value set as PAYER_TYPE_PRIMARY per Phase 4 research; confirmed in `scripts/validate_all.py` and `hpc-upload/valuesets.csv` — ENCOUNTER has both PAYER_TYPE_PRIMARY and PAYER_TYPE_SECONDARY entries).
- **Schema source:** ENCOUNTER columns are not listed in `datastructure.txt`; they come from the Parquet files (converted from source CSV). At runtime, use `pl.read_parquet_schema(enc_path)` and check `"PAYER_TYPE_SECONDARY" in schema.names()` before using secondary in effective_payer or dual_eligible logic. If absent, effective_payer = primary only; dual_eligible = 0 or null when no dual-eligible logic can be applied.

### derived/encounter_payer_summary.parquet

- **New column:** **DUAL_ELIGIBLE** (Int8 or Int64): 0/1 at patient level (ever dual-eligible across encounters).
- **Existing columns:** All existing payer variables (N_ENCOUNTERS_WITH_PAYER, PAYER_CATEGORY_*, PAYER_TRANSITION) should be defined as using **effective payer** in docs/codebook; implementation will already use the single effective_payer column once added.

---

## Order of Operations

1. **Read ENCOUNTER** with PATID_COL, ADMIT_DATE, PAYER_TYPE_PRIMARY, and PAYER_TYPE_SECONDARY (if present).
2. **Compute effective_payer** per row: primary if primary valid, else secondary if valid, else null (sentinel list + optional 99/9999 — see Sentinel List).
3. **Compute encounter-level dual_eligible** per row (Medicare+Medicaid or code 14/141/142 using effective_payer and, for (a)/(b), primary and secondary; for (c) primary or secondary in {14,141,142}).
4. **Filter to enrolled IDs** (unchanged).
5. **Base counts:** N_ENCOUNTERS, N_ENCOUNTERS_WITH_PAYER using **effective_payer** (valid = non-null, non-empty, not sentinel).
6. **Category and primary/transition:** Use **effective_payer** for PAYER_CATEGORY, N_DISTINCT_PAYER_CATEGORIES, PAYER_CATEGORY_PRIMARY, PAYER_TRANSITION (same logic as today, on effective_payer).
7. **_payer_at_date and chemo windows:** Use **effective_payer** (not PAYER_TYPE_PRIMARY) when selecting payer from the encounter closest to first DX / first chemo / last chemo and for “most frequent at chemo” (so all those blocks must read effective_payer from the encounter frame).
8. **Patient-level DUAL_ELIGIBLE:** From encounter-level dual_eligible, aggregate by patient (e.g. max or any) and add to the final summary DataFrame.
9. **Return** same columns as today plus **DUAL_ELIGIBLE**; write to `derived/encounter_payer_summary.parquet` as today. Suppression (flag_small_cell / _suppress) unchanged.

---

## Sentinel List

### Confirmed (trigger fallback to secondary)

- **null**
- **empty string** (`""`)
- **NI** (No Information)
- **UN** (Unknown)
- **OT** (Other)

These are the current `INVALID_PAYER` in `encounter_payer_summary.py` (line 24). Treat as “sentinel” for effective payer: when primary is one of these, use secondary if valid.

### Optional (user-specified)

- **99, 9999:** User said “optionally 99/9999” trigger fallback. Current `_collapse_payer_category` maps 99/9999 to **Unavailable**. Recommendation: **Make 99/9999 configurable or document as optional sentinel** — if included, primary = 99/9999 causes fallback to secondary when secondary is valid; if excluded, 99/9999 remains “valid” for effective payer and maps to Unavailable. Document the choice in CODEBOOK or PAYER_VARIABLES_AND_CATEGORIES.md.

### Valid (do not trigger fallback)

- Any other value in the PAYER_TYPE value set (including 14, 141, 142, 41, etc.) is treated as valid for “effective payer” when it appears in primary or secondary.

---

## Code References

### encounter_payer_summary.py

| Location | Current behavior | Change for Phase 16 |
|----------|------------------|---------------------|
| `INVALID_PAYER`, `_valid_payer_expr()` | Primary only | Introduce sentinel set and valid-primary / valid-secondary expressions; add `effective_payer` expression. |
| First `enc` scan (lines 243–256) | Selects PRIMARY, adds `_valid` from primary | Select PRIMARY and SECONDARY (if present); add `effective_payer`; `_valid` from effective_payer. |
| `valid_enc` (252–258) | Filters `_valid`, uses PAYER_TYPE_PRIMARY | Filter on effective_payer valid; use effective_payer for category. |
| `_payer_at_date` (147–179) | Reads ADMIT_DATE, PAYER_TYPE_PRIMARY | Read ADMIT_DATE, effective_payer (or compute effective_payer in same scan). Return effective_payer as _raw_payer. |
| enc_chemo block (360–377) | Selects ADMIT_DATE, PAYER_TYPE_PRIMARY; filters valid primary | Select ADMIT_DATE, effective_payer; filter on effective_payer valid; use effective_payer for PAYER_CATEGORY. |
| empty_schema / return | No DUAL_ELIGIBLE | Add DUAL_ELIGIBLE to schema and to final `.select()`. |

### valuesets

- **Path:** `valuesets_path` from config (e.g. `valuesets.csv` under project or `hpc-upload/valuesets.csv`). Structure: TABLE_NAME, FIELD_NAME, VALUESET_ITEM, VALUESET_ITEM_DESCRIPTOR.
- **Dual-eligibility codes:** ENCOUNTER, PAYER_TYPE_PRIMARY (and PAYER_TYPE_SECONDARY): 14, 141, 142 as above. 41 = Corrections Federal; document, do not treat as dual-eligible.

### Downstream

- **build_insurance_summary.py:** Reads `encounter_payer_summary.parquet`; no change required for suppression. Can add DUAL_ELIGIBLE to tables/stratification if desired (optional follow-up).
- **quality_report.py:** Uses PAYER_TYPE_PRIMARY from encounter for PAYER_AT_DX; if that report should use effective payer, it will need to either (1) use encounter_payer_summary’s PAYER_CATEGORY_AT_FIRST_DX (already based on effective payer after Phase 16) or (2) duplicate effective_payer logic when reading ENCOUNTER. Recommendation: document that encounter_payer_summary is the source of truth for payer-at-DX after Phase 16.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sentinel detection | Ad-hoc string lists in multiple places | Single sentinel set + one `effective_payer` expression | Consistency and one place to add 99/9999. |
| Dual-eligible codes | Hard-coded list from memory | Constants (14, 141, 142) with comment citing valuesets; document 41 | valuesets.csv is authoritative; 41 is not dual. |
| Category from payer code | Duplicate prefix logic | Reuse `_collapse_payer_category(code)` on effective_payer | Same categories for primary/secondary. |

---

## Common Pitfalls

### Pitfall 1: Using primary/secondary in different places

**What goes wrong:** Some code paths use effective_payer and others still use PAYER_TYPE_PRIMARY, so “at first DX” and “primary category” are inconsistent.  
**How to avoid:** One effective_payer column; every aggregation and _payer_at_date uses it. Grep for PAYER_TYPE_PRIMARY in the module and replace with effective_payer where the intent is “payer for this encounter.”

### Pitfall 2: Treating 41 as dual-eligible

**What goes wrong:** Code 41 is “Corrections Federal” (Other government). Including it in dual-eligible inflates counts.  
**How to avoid:** Dual-eligible codes = {14, 141, 142} only; document 41 in codebook for site-specific use.

### Pitfall 3: Missing PAYER_TYPE_SECONDARY in schema

**What goes wrong:** Assuming SECONDARY exists and crashing or producing null effective_payer when column is missing.  
**How to avoid:** Check schema at start; if SECONDARY not present, effective_payer = primary (current behavior); dual_eligible = 0 or null when secondary is required for (a)/(b).

### Pitfall 4: Dual-eligible on raw primary/secondary vs effective

**What goes wrong:** Defining dual-eligible on “primary and secondary” while other variables use effective_payer, so a row with primary=NI and secondary=Medicaid is dual-eligible by (b) but effective_payer=Medicaid only — acceptable. Recommendation: define encounter-level dual_eligible using **primary and secondary** (and codes 14/141/142 on either), not on effective_payer only, so that “Medicare + Medicaid” is detected even when one is in secondary and the other is effective.

---

## State of the Art

- **Current:** Single payer (PAYER_TYPE_PRIMARY) only; NI/UN/OT and empty/null treated as invalid; 99/9999 map to Unavailable.  
- **After Phase 16:** Effective payer with sentinel fallback; dual-eligible (encounter + patient); all encounter-payer summary variables use effective payer. Suppression and report scripts unchanged unless DUAL_ELIGIBLE is added to outputs.

---

## Open Questions

1. **99/9999 as sentinel**  
   - What we know: User said “optionally 99/9999” trigger fallback.  
   - What’s unclear: Default on or off.  
   - Recommendation: Implement as optional (e.g. constant INCLUDE_99_AS_SENTINEL = False); document in CODEBOOK; planner can add a task to expose via config if needed.

2. **quality_report.PAYER_AT_DX**  
   - What we know: quality_report.py reads ENCOUNTER and uses PAYER_TYPE_PRIMARY for PAYER_AT_DX.  
   - What’s unclear: Whether to switch to effective_payer there or rely on encounter_payer_summary.  
   - Recommendation: Phase 16 scope is encounter_payer_summary; quality_report can be updated in a later phase or left as-is and document that encounter_payer_summary is the canonical source for payer-at-DX.

---

## Sources

### Primary (HIGH confidence)

- `src/report/encounter_payer_summary.py` — full read; current payer logic and aggregation.
- `hpc-upload/valuesets.csv` — ENCOUNTER PAYER_TYPE_PRIMARY/SECONDARY; codes 14, 141, 142, 41 verified.
- `docs/PAYER_VARIABLES_AND_CATEGORIES.md` — variable definitions and category mapping.
- Phase 4 research (04-RESEARCH.md) — PAYER_TYPE_SECONDARY same value set as PRIMARY.

### Secondary (MEDIUM confidence)

- `scripts/validate_all.py` — insurance columns list (PAYER_TYPE_PRIMARY, PAYER_TYPE_SECONDARY, RAW_PAYER_TYPE_PRIMARY).
- `scripts/build_insurance_summary.py` — consumes encounter_payer_summary.parquet; suppression pattern.

### Tertiary (LOW confidence)

- Web search: PCORnet dual eligibility codes 14/141/142 not fully detailed in top results; valuesets.csv is the project’s authority.

---

## Metadata

**Confidence breakdown:**

- Effective payer / sentinel: HIGH — code and docs reviewed; sentinel list and fallback rule are explicit.
- Dual-eligible: HIGH — valuesets and code references; 41 clarified.
- Schema/order of operations: HIGH — single module, clear pipeline.

**Research date:** 2025-03-16  
**Valid until:** 30 days (stable domain).
