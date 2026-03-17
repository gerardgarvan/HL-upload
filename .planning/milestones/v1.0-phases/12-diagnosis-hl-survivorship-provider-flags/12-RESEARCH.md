# Phase 12: Diagnosis HL / Survivorship / Provider Flags — Research

**Researched:** 2026-03-09
**Domain:** HL data pipeline — diagnosis flags (HL, survivorship) and provider cancer-specialty flag
**Confidence:** HIGH

## Summary

Phase 12 adds three binary flag columns: (1) `FLAG_HL_DX` on DIAGNOSIS for Hodgkin lymphoma diagnosis rows, (2) `FLAG_SURVIVORSHIP_DX` on DIAGNOSIS for cancer survivorship diagnosis rows, and (3) `FLAG_CANCER_PROVIDER` on PROVIDER for oncology-related providers. These flags enable insurance inequities and survivorship analyses without re-scanning raw tables.

**Primary recommendation:** Create a new module `src/clean/flags_diagnosis_provider.py` with functions that add the three flags via Polars; integrate these calls into `scripts/clean_all.py` in the main cleaning loop, after dedup and harmonize and before write. Normalize DX_TYPE to support both PCORnet numeric (09/10) and full labels (ICD-9-CM/ICD-10-CM). For survivorship, use exact match for specific codes and prefix match for Z08/Z85. For PROVIDER, use a keyword list with case-insensitive regex matching on PROVIDER_SPECIALTY_PRIMARY.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Polars | (existing) | Flag computation, in-place column addition | Already used in cohort.py, dedup.py, harmonize.py, clean_all.py |
| Python 3.11 | (existing) | Runtime | Project standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `re` | stdlib | Regex for oncology keyword matching | PROVIDER_SPECIALTY_PRIMARY free-text matching |

**Installation:** No new dependencies. Uses existing Polars and stdlib.

## Architecture Patterns

### Recommended Project Structure

```
src/clean/
├── dedup.py           # IS_DUPLICATE, event-encounter, death consistency
├── harmonize.py       # ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY
├── flags_diagnosis_provider.py   # NEW: FLAG_HL_DX, FLAG_SURVIVORSHIP_DX, FLAG_CANCER_PROVIDER
└── outcomes_flags.py  # Modality flags (Phase 7)

scripts/
└── clean_all.py       # Main loop — add flags_diagnosis_provider calls
```

### Pattern 1: Row-Level Diagnosis Flags via Polars

**What:** Add binary Int8 columns to DIAGNOSIS using `pl.when().then().otherwise()` with DX_TYPE and DX predicates.

**When to use:** Per-row diagnosis categorization (HL, survivorship).

**Example:**

```python
# Source: cohort.py, values.py patterns
is_icd9 = pl.col("DX_TYPE").is_in(ICD9_DX_TYPES)  # "09", "ICD-9-CM"
is_icd10 = pl.col("DX_TYPE").is_in(ICD10_DX_TYPES)  # "10", "ICD-10-CM"

flag_hl = (
    pl.when(is_icd9 & pl.col("DX").str.starts_with("201"))
    .then(pl.lit(1, dtype=pl.Int8))
    .when(is_icd10 & pl.col("DX").str.to_uppercase().str.starts_with("C81"))
    .then(pl.lit(1, dtype=pl.Int8))
    .otherwise(pl.lit(0, dtype=pl.Int8))
)
df = df.with_columns(flag_hl.alias("FLAG_HL_DX"))
```

### Pattern 2: DX Format Normalization

**What:** DIAGNOSIS.DX may be dotted (C81.10) or undotted (C8110). Normalize before matching using `normalize_dx()` from `src/validate/cohort.py`.

**When to use:** Any DX code matching (HL, survivorship, modality).

**Example:**

```python
# Source: cohort.py:29-31
def normalize_dx(code: str) -> str:
    return code.upper().replace(".", "")
# Polars: pl.col("DX").str.to_uppercase().str.replace_all(r"\.", "")
```

### Pattern 3: PROVIDER Specialty Keyword Matching

**What:** PROVIDER_SPECIALTY_PRIMARY is free text. Match using case-insensitive regex over a keyword list.

**When to use:** Flagging oncology/cancer providers.

**Example:**

```python
ONCOLOGY_KEYWORDS = [
    r"\boncology\b",
    r"\bmedical oncology\b",
    r"\bradiation oncology\b",
    r"\bhematology[\-/]oncology\b",
    r"\bpediatric oncology\b",
]
pattern = "|".join(ONCOLOGY_KEYWORDS)
is_oncology = pl.col("PROVIDER_SPECIALTY_PRIMARY").str.to_lowercase().str.contains(pattern)
df = df.with_columns(is_oncology.cast(pl.Int8).alias("FLAG_CANCER_PROVIDER"))
```

### Anti-Patterns to Avoid

- **Don't assume DX_TYPE is always 09/10:** OneFlorida+ and other PCORnet sites may use "ICD-9-CM"/"ICD-10-CM". Normalize both.
- **Don't match survivorship Z08/Z85 with exact match only:** Z08.x and Z85.xx are valid subcodes; use prefix match for Z08 and Z85.
- **Don't hardcode PROVIDER specialty values:** Free-text values vary; use keyword/regex, not a fixed value set.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DX code matching | Custom string parsing | Polars `str.starts_with`, `str.contains`, `is_in` | Vectorized, handles nulls, consistent with cohort.py |
| DX_TYPE mapping | Ad-hoc string checks | Normalized set membership (`is_in`) | Handles 09/10 and ICD-9-CM/ICD-10-CM uniformly |
| Provider specialty matching | Manual substring loops | Polars `str.contains` with compiled regex | Vectorized, maintainable keyword list |
| Flag column persistence | Custom Parquet logic | Same write path as dedup/harmonize | Reuse `write_cleaned` pattern in clean_all.py |

**Key insight:** Existing patterns in cohort.py (normalize_dx, DX_TYPE checks), dedup.py (flag_duplicates, write_cleaned), and harmonize.py (add_partner_flags) should be followed. Extend, don't rebuild.

## Common Pitfalls

### Pitfall 1: DX_TYPE Value Heterogeneity

**What goes wrong:** FLAG_HL_DX or survivorship flags undercount because DX_TYPE contains "ICD-9-CM" or "ICD-10-CM" instead of "09" or "10".

**Why it happens:** PCORnet CDM value set uses numeric codes (09, 10) per specification, but some sites submit full labels. OneFlorida+ may vary by partner.

**How to avoid:** Support both forms. Define:

```python
ICD9_DX_TYPES = {"09", "ICD-9-CM"}
ICD10_DX_TYPES = {"10", "ICD-10-CM"}
```

Use `pl.col("DX_TYPE").cast(pl.String).str.strip_chars().is_in(ICD9_DX_TYPES)` (and similar for ICD10) for type checks.

**Warning signs:** HL or survivorship counts much lower than expected; DX_TYPE distribution shows non-numeric values.

### Pitfall 2: Survivorship Z08/Z85 Exact vs Prefix

**What goes wrong:** Z08.0, Z85.3, Z85.41, etc., are missed if only exact match on "Z08" or "Z85" is used.

**Why it happens:** ICD-10-CM uses hierarchical codes. Z08 and Z85 are category codes; Z08.x and Z85.xx are valid subcodes for history of malignancy / follow-up after treatment.

**How to avoid:** For Z08 and Z85, use prefix match: DX (normalized, dot-stripped) `starts_with("Z08")` or `starts_with("Z85")`. For specific codes (V87.41, Z92.21, etc.), use exact match after normalization.

**Warning signs:** Survivorship flag count near zero when Z85.x codes exist in data.

### Pitfall 3: PROVIDER Lacks SOURCE / Has No ENCOUNTERID

**What goes wrong:** PROVIDER table may not have SOURCE; ENCOUNTER links to PROVIDER via PROVIDERID, but PROVIDER is standalone.

**Why it happens:** Per PCORnet CDM and HEALTHCARE_DATA_RESEARCH.md, PROVIDER links through PATID or other keys — not all tables have ENCOUNTERID. PROVIDER is a lookup table.

**How to avoid:** Add FLAG_CANCER_PROVIDER directly to PROVIDER rows. No join required for the flag itself. ENCOUNTER.PROVIDERID can be used downstream to link encounters to cancer providers if needed.

**Warning signs:** PROVIDER has no SOURCE column; ENCOUNTER has PROVIDERID but PROVIDER may be sparse.

### Pitfall 4: Dotted vs Undotted DX in Survivorship Codes

**What goes wrong:** V87.41 in data stored as "V8741" (or vice versa) fails exact match.

**Why it happens:** Same format variation as HL cohort (Phase 3): detect via `detect_dx_format()` and normalize before matching.

**How to avoid:** Normalize DX (strip dots, uppercase) before comparing to survivorship code set. Use `normalize_dx()` pattern from cohort.py.

**Warning signs:** Survivorship flag undercounts when DX values lack dots.

## Code Examples

### DX_TYPE Normalization for HL and Survivorship

```python
# Source: cohort.py, Phase 4 values.py
ICD9_DX_TYPES = {"09", "ICD-9-CM", "9"}   # support variants
ICD10_DX_TYPES = {"10", "ICD-10-CM", "10-CM"}

def _is_icd9_type(dx_type: pl.Expr) -> pl.Expr:
    return pl.coalesce(
        pl.col("DX_TYPE").cast(pl.Utf8).str.strip_chars().str.to_uppercase(),
        pl.lit("")
    ).is_in({t.upper() for t in ICD9_DX_TYPES})

def _is_icd10_type(dx_type: pl.Expr) -> pl.Expr:
    return pl.coalesce(
        pl.col("DX_TYPE").cast(pl.Utf8).str.strip_chars().str.to_uppercase(),
        pl.lit("")
    ).is_in({t.upper() for t in ICD10_DX_TYPES})
```

### HL Flag Logic

```python
# (DX_TYPE in ICD9 AND DX starts with 201) OR (DX_TYPE in ICD10 AND DX starts with C81)
dx_norm = pl.col("DX").str.to_uppercase().str.replace_all(r"\.", "")
flag_hl = (
    pl.when(_is_icd9_type(pl.col("DX_TYPE")) & pl.col("DX").str.starts_with("201"))
    .then(pl.lit(1, dtype=pl.Int8))
    .when(_is_icd10_type(pl.col("DX_TYPE")) & dx_norm.str.starts_with("C81"))
    .then(pl.lit(1, dtype=pl.Int8))
    .otherwise(pl.lit(0, dtype=pl.Int8))
).alias("FLAG_HL_DX")
```

### Survivorship Code Set

```python
# Exact-match codes (ICD-10-CM unless noted)
SURVIVORSHIP_EXACT_ICD10 = {
    "V87.41", "V87.42", "V87.43", "V87.46",
    "Z92.21", "Z92.22", "Z92.23", "Z92.25", "Z92.3",
}
# ICD-9-CM
SURVIVORSHIP_EXACT_ICD9 = {"V15.3"}

# Prefix-match (Z08.x, Z85.xx = history of malignancy, follow-up)
SURVIVORSHIP_PREFIX_ICD10 = ("Z08", "Z85")
```

Apply: exact match for normalized codes in the exact sets; prefix match for DX starting with Z08 or Z85 (after normalizing). Use DX_TYPE to choose ICD-9 vs ICD-10 sets.

### Provider Cancer Flag

```python
ONCOLOGY_KEYWORDS = [
    r"oncology",
    r"medical oncology",
    r"radiation oncology",
    r"hematology[\-\s]*oncology",
    r"hematology/oncology",
    r"pediatric oncology",
]
pat = "|".join(ONCOLOGY_KEYWORDS)
is_cancer_provider = (
    pl.col("PROVIDER_SPECIALTY_PRIMARY")
    .fill_null("")
    .str.to_lowercase()
    .str.contains(pat)
)
df = df.with_columns(is_cancer_provider.cast(pl.Int8).alias("FLAG_CANCER_PROVIDER"))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| DX_TYPE only 09/10 | Support 09/10 and ICD-9-CM/ICD-10-CM | OneFlorida+ partner variation | Robust to site-specific submissions |
| Exact match for Z08/Z85 | Prefix match Z08*, Z85* | ICD-10 hierarchy | Catches Z08.0–Z08.9, Z85.0–Z85.9x |
| Fixed specialty value set | Keyword regex | PROVIDER_SPECIALTY free text | Handles "Hematology-Oncology", "Medical Oncology", etc. |

## Integration Point

**Where to add flags:** In `scripts/clean_all.py`, inside the main cleaning loop, after:
- `flag_duplicates()`
- `add_partner_flags()`
- `flag_events_outside_encounters()` (for event tables)
- `flag_encounters_outside_enrollment()` / `flag_no_enrollment()` (for ENCOUNTER)

Add:
- For DIAGNOSIS: `add_diagnosis_flags(df)` → FLAG_HL_DX, FLAG_SURVIVORSHIP_DX
- For PROVIDER: `add_provider_flags(df)` → FLAG_CANCER_PROVIDER

**Module:** `src/clean/flags_diagnosis_provider.py`

**Flag column naming:** Use `FLAG_*` as specified: FLAG_HL_DX, FLAG_SURVIVORSHIP_DX, FLAG_CANCER_PROVIDER. Existing pipeline uses IS_DUPLICATE, ICD_MAPPED (semantic names) and _con_* (consistency). FLAG_* aligns with user spec and is distinct.

**Idempotency:** Extend `drop_existing_clean_flags()` (or equivalent) to drop FLAG_HL_DX, FLAG_SURVIVORSHIP_DX, FLAG_CANCER_PROVIDER when re-running, so clean_all.py remains idempotent.

## Flag Column Naming Convention

| Column | Table | Values | Notes |
|--------|-------|--------|-------|
| FLAG_HL_DX | DIAGNOSIS | 0/1 Int8 | 1 = Hodgkin lymphoma diagnosis (ICD-9 201*, ICD-10 C81*) |
| FLAG_SURVIVORSHIP_DX | DIAGNOSIS | 0/1 Int8 | 1 = cancer survivorship code (V87.x, V15.3, Z92.x, Z08*, Z85*) |
| FLAG_CANCER_PROVIDER | PROVIDER | 0/1 Int8 | 1 = oncology-related specialty |

Existing conventions: IS_DUPLICATE, ICD_MAPPED (Phase 5); _con_outside_encounter (consistency); _val_* (Phase 4 validation). Phase 12 introduces FLAG_* for derived clinical categorization flags.

## Open Questions

1. **Survivorship code source:** The user-provided list (V87.41, V87.42, V87.43, V87.46, V15.3, Z92.21, Z92.22, Z92.23, Z92.25, Z92.3, Z08, Z85) — is this from a specific value set (e.g., NCCN, CDC, study protocol)? If so, cite it in code comments for reproducibility.
2. **ENCOUNTER–PROVIDER linkage:** Phase 12 flags PROVIDER only. If downstream analysis needs "encounter with cancer provider," that requires joining ENCOUNTER.PROVIDERID to PROVIDER and filtering FLAG_CANCER_PROVIDER=1. Document this in the module docstring.
3. **PROVIDER_SPECIALTY values in OneFlorida+:** A one-time profile of distinct PROVIDER_SPECIALTY_PRIMARY values would validate the oncology keyword list. Recommend adding a small validation step or report snippet to log unmatched oncology-like terms.

## Sources

### Primary (HIGH confidence)
- `src/validate/cohort.py` — DX format detection, normalize_dx, DX_TYPE checks (09/10), HL code sets
- `src/clean/dedup.py` — CLEAN_FLAG_COLS, drop_existing_clean_flags, flag_duplicates, write_cleaned
- `src/clean/harmonize.py` — add_partner_flags, PARTNER_FLAGS
- `scripts/clean_all.py` — main loop structure, report generation
- `.planning/research/HEALTHCARE_DATA_RESEARCH.md` — ENCOUNTER.PROVIDERID, PROVIDER.PROVIDER_SPECIALTY_PRIMARY

### Secondary (MEDIUM confidence)
- PCORnet CDM: DX_TYPE 09 = ICD-9-CM, 10 = ICD-10-CM (WebSearch)
- ICD10data.com — Z08, Z85 category structure (prefix match for subcodes)
- AAPC/SEER — survivorship coding (Z85, Z92.21, Z08)

### Tertiary (LOW confidence)
- OneFlorida+ DX_TYPE exact values — not verified in data; recommend supporting both 09/10 and ICD-9-CM/ICD-10-CM

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Polars, existing patterns, no new deps
- Architecture: HIGH — clean_all.py loop, dedup/harmonize integration well established
- Pitfalls: HIGH — DX_TYPE and format issues documented in Phase 3/4; survivorship hierarchy from ICD-10 spec

**Research date:** 2026-03-09
**Valid until:** ~30 days (stable pipeline; survivorship code set may evolve with protocol)
