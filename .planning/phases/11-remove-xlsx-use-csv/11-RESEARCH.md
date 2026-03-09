# Phase 11: Remove XLSX/Excel Dependencies (Use CSV) — Research

**Researched:** 2026-03-09
**Domain:** Data format migration (Excel → CSV), dependency removal, loader refactor
**Confidence:** HIGH

## Summary

Phase 11 replaces `Outcomes.xlsx` with `Outcomes.csv` to eliminate the openpyxl dependency. The project already has an `Outcomes.csv` at the root with identical columns (Modality, Code system, Code, Description) and fully populated rows. Forward-fill semantics are preserved: `pd.read_csv` treats empty cells as NaN; `df.ffill()` behaves identically to the current Excel path. Use a **single CSV**, **pd.read_csv** (minimal code change), and a **clean cutover** (no dual .xlsx/.csv support) unless transition period is required. Tests switch from `df.to_excel()` to `df.to_csv()`; environment and CI drop openpyxl.

**Primary recommendation:** Replace `pd.read_excel(path, sheet_name="Outcomes")` with `pd.read_csv(path)` in `load_outcomes_code_lookup`, keep ffill logic, update path references to `Outcomes.csv`, remove openpyxl from environment.yml and CI, and convert/provide Outcomes.csv via one-time script or export steps.

---

## Standard Stack

### Core (unchanged)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | >=2.2 | CSV load via read_csv, ffill, iterrows | Already in env; minimal change from read_excel |
| polars | (existing) | Parquet I/O, modality flag joins | No change |
| pathlib | stdlib | Path resolution | No change |

### Removed

| Library | Purpose | Removal |
|---------|---------|---------|
| openpyxl | Engine for pd.read_excel on .xlsx | Remove from environment.yml, .github/workflows/ci.yml |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pd.read_csv | pl.read_csv | Polars would require refactoring iterrows/group-by logic; pandas is sufficient for small lookup table |
| Single CSV | Multiple CSVs | Outcomes sheet has one logical table; single CSV mirrors current structure |

**No new installation.** Removal only: `openpyxl` from pip deps.

---

## Architecture Patterns

### CSV Layout (Single File)

**Columns (match schema):**
```
Modality,Code system,Code,Description
```

- **Modality** — e.g. "Stem cell transplant"; forward-filled if empty (same as Excel)
- **Code system** — CPT, HCPCS, LOINC, ICD-10-PCS, ICD-10, ICD-10-CM/PCS...
- **Code** — actual code value
- **Description** — human-readable (not used by loader)

**Encoding:** UTF-8. Quoted fields for commas in Description (e.g. `"Cord blood harvesting for transplantation, allogeneic"`). Both pandas and polars handle this by default.

### Pattern 1: Load with Forward-Fill

**What:** Read CSV, forward-fill Modality and Code system, build lookup.
**When:** Always, for compatibility with sparse (Excel-style) or dense CSV.

```python
# Source: outcomes_flags.py (current), adapted for CSV
df = pd.read_csv(path)
df["Modality"] = df["Modality"].ffill()
df["Code system"] = df["Code system"].ffill()
# ... rest unchanged
```

**Note:** `pd.read_csv` treats empty cells as NaN by default. Do **not** use `keep_default_na=False` or ffill will not work on empty cells.

### Pattern 2: Path Resolution

**Current:** Hardcoded `PROJECT_ROOT / "Outcomes.xlsx"` in assemble_clean.py, add_modality_flags.py; `OUTCOMES_PATH` env overrides full path.

**Options:**
- **Clean cutover (recommended):** Resolve to `Outcomes.csv` only. No .xlsx support.
- **Transition period:** Try `Outcomes.csv` first, fall back to `Outcomes.xlsx` if missing. Requires keeping openpyxl temporarily.

### Anti-Patterns to Avoid

- **keep_default_na=False in read_csv:** Empty cells become `""` instead of NaN; ffill won't propagate.
- **Multiple CSVs for one Outcomes table:** Adds complexity; single file is sufficient.
- **Removing ffill:** Sparse CSV (exported from Excel with empty Modality/Code system) would break without it.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Excel parsing | Custom xlsx reader | pd.read_csv (CSV) | Standard, no openpyxl |
| Forward-fill | Manual loop | df.ffill() | Built-in, correct semantics |
| Path with/without extension | String splicing | Path.with_suffix(".csv") or explicit filename | Clear, cross-platform |

---

## Common Pitfalls

### Pitfall 1: Empty Cells and keep_default_na

**What goes wrong:** Empty Modality/Code system cells read as `""` instead of NaN; ffill does nothing.
**Why it happens:** `pd.read_csv(..., keep_default_na=False)` or similar overrides.
**How to avoid:** Use default `read_csv`; empty cells become NaN. ffill works.
**Warning signs:** Tests with sparse CSV fail; lookup missing codes for multi-row modality blocks.

### Pitfall 2: Quoted Commas in Description

**What goes wrong:** Misparsed columns if CSV not handled as quoted.
**Why it happens:** Description has commas; naive split breaks rows.
**How to avoid:** `pd.read_csv` and `pl.read_csv` handle quoted fields by default. Ensure export uses standard CSV quoting.
**Warning signs:** Wrong column alignment; "Code" column contains Description text.

### Pitfall 3: Encoding

**What goes wrong:** Non-ASCII (e.g. accented characters) cause decode errors.
**Why it happens:** Excel may export with different encoding.
**How to avoid:** Export as "CSV UTF-8" or "UTF-8" from Excel. If needed: `pd.read_csv(path, encoding="utf-8")` (default in pandas 2+).
**Warning signs:** `UnicodeDecodeError` on read.

### Pitfall 4: Trailing/Leading Whitespace in Headers

**What goes wrong:** Column names "Modality " vs "Modality" cause KeyError.
**How to avoid:** Normalize headers on read: `df.columns = df.columns.str.strip()` or ensure CSV has no extra spaces. Current schema uses exact names.
**Warning signs:** `KeyError: 'Modality'` when column is `" Modality"`.

---

## Migration Strategy

### One-Time Conversion Options

1. **Python script (recommended):**
   ```python
   # scripts/convert_outcomes_to_csv.py (one-time)
   import pandas as pd
   from pathlib import Path
   path_xlsx = Path("Outcomes.xlsx")
   path_csv = Path("Outcomes.csv")
   df = pd.read_excel(path_xlsx, sheet_name="Outcomes")
   df.to_csv(path_csv, index=False)
   ```
   Run once with openpyxl present; after migration, openpyxl can be removed.

2. **Excel export:** In Excel, File → Save As → CSV UTF-8 (Comma delimited). Select "Outcomes" sheet and save as Outcomes.csv. Ensure columns: Modality, Code system, Code, Description.

### Backward Compatibility

**Recommended: clean cutover.** No dual support.

- Simpler: single path, no fallback logic.
- Outcomes.csv already exists at project root.
- Migration: run conversion script (or export) once; delete Outcomes.xlsx; update all references.

**If transition period needed:** Implement `_resolve_outcomes_path(root: Path) -> Path` that returns `root / "Outcomes.csv"` if exists, else `root / "Outcomes.xlsx"`, and branch in loader (read_csv vs read_excel). Keep openpyxl until cutover complete.

---

## Code Examples

### load_outcomes_code_lookup (CSV variant)

```python
def load_outcomes_code_lookup(path: Path) -> dict[str, dict[str, set[str]]]:
    """Load Outcomes from CSV and build modality→code_sets lookup."""
    df = pd.read_csv(path)
    df["Modality"] = df["Modality"].ffill()
    df["Code system"] = df["Code system"].ffill()
    # ... rest identical to current implementation
```

### Test Fixture (CSV mock)

```python
# tests/test_load_outcomes_code_lookup.py
csv_path = tmp_path / "outcomes_mock.csv"
df = pd.DataFrame({
    "Modality": ["Stem cell transplant", "Stem cell transplant"],
    "Code system": ["CPT", "LOINC"],
    "Code": ["38205", "38206-3"],
    "Description": ["desc1", "desc2"],
})
df.to_csv(csv_path, index=False)
result = load_outcomes_code_lookup(csv_path)
```

### Sparse CSV (forward-fill test)

```python
# Optional: test sparse CSV (empty Modality/Code system)
df = pd.DataFrame({
    "Modality": ["Stem cell transplant", None],
    "Code system": ["CPT", "LOINC"],
    "Code": ["38205", "38206-3"],
    "Description": ["d1", "d2"],
})
df.to_csv(csv_path, index=False)
# After read_csv, row 2 Modality is NaN → ffill makes it "Stem cell transplant"
```

---

## Files to Update

| File | Change |
|------|--------|
| `src/clean/outcomes_flags.py` | `pd.read_excel(path, sheet_name="Outcomes")` → `pd.read_csv(path)`; docstrings |
| `scripts/assemble_clean.py` | `Outcomes.xlsx` → `Outcomes.csv` |
| `scripts/add_modality_flags.py` | Default `Outcomes.xlsx` → `Outcomes.csv` |
| `tests/test_load_outcomes_code_lookup.py` | `to_excel` → `to_csv`; mock file `.xlsx` → `.csv` |
| `tests/test_add_modality_flags.py` | Same fixture change |
| `environment.yml` | Remove `openpyxl` from pip |
| `.github/workflows/ci.yml` | Remove `openpyxl` from pip install |
| `.planning/docs/OUTCOMES_XLSX_SCHEMA.md` | Rename to OUTCOMES_CSV_SCHEMA.md or update to describe CSV |
| `.planning/docs/HPC_UPLOAD_SYNC.md` | `Outcomes.xlsx` → `Outcomes.csv` in sync commands and table |
| `reports/modality_flags.md` | Header/doc reference to Outcomes.csv |
| `scripts/assemble_clean.py` (print) | "Outcomes.xlsx" → "Outcomes.csv" in messages |
| ROADMAP, CONCERNS, STACK, ARCHITECTURE, STRUCTURE, INTEGRATIONS | Update references |

---

## Environment Changes

**Remove:**
- `openpyxl` from `environment.yml` pip section
- `openpyxl` from `.github/workflows/ci.yml` pip install

**Add (optional):**
- `scripts/convert_outcomes_to_csv.py` — one-time XLSX→CSV converter (run before removing openpyxl)

---

## Test Impact

| Test | Change |
|------|--------|
| `test_load_outcomes_code_lookup_mock` | Create CSV via `df.to_csv()` instead of `df.to_excel()`; no openpyxl |
| `test_add_modality_flags_integration` | Same fixture: CSV instead of xlsx |

**Verification:** `python -m pytest tests/test_load_outcomes_code_lookup.py tests/test_add_modality_flags.py -v` passes after migration. CI no longer installs openpyxl.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| pd.read_excel + openpyxl | pd.read_csv | Fewer deps, CSV is plain text, versionable, Excel-free |
| Excel for modality codes | CSV | Easier to edit in any editor; no Excel license needed |

---

## Open Questions

1. **Config for outcomes path:** paths.toml has no outcomes_path. Keep hardcoded `PROJECT_ROOT / "Outcomes.csv"` and `OUTCOMES_PATH` env, or add to config? Recommendation: keep current pattern; only change filename.
2. **Schema doc rename:** OUTCOMES_XLSX_SCHEMA.md → OUTCOMES_CSV_SCHEMA.md vs in-place update. Recommendation: update in place; document CSV as primary format.
3. **Transition period:** Is dual .xlsx/.csv support required? Recommendation: clean cutover; Outcomes.csv already exists.

---

## Sources

### Primary (HIGH confidence)
- Project `Outcomes.csv` — verified column layout, no sparse rows
- `src/clean/outcomes_flags.py` — current loader logic
- `.planning/docs/OUTCOMES_XLSX_SCHEMA.md` — schema spec
- pandas: read_csv default na handling (empty → NaN), ffill

### Secondary (MEDIUM confidence)
- Web search: pandas read_csv + ffill for empty cells
- Web search: polars forward_fill (for alternative loader)

### Tertiary (LOW confidence)
- Excel "Save As CSV" behavior — assume standard UTF-8 CSV with quoted fields

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pandas/polars already in use; CSV is standard
- Architecture: HIGH — single CSV, ffill, minimal loader change
- Pitfalls: HIGH — keep_default_na, quoting, encoding well-documented

**Research date:** 2026-03-09
**Valid until:** 30 days (stable domain)
