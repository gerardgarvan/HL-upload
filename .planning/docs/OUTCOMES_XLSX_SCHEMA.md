# Outcomes CSV Schema

**Reference:** `src/clean/outcomes_flags.py` — `load_outcomes_code_lookup()`

**Source file:** `Outcomes.csv` at project root (UTF-8, quoted fields for commas in Description).

## Columns

| Column       | Type   | Notes                                                |
|--------------|--------|------------------------------------------------------|
| Modality     | string | Forward-filled (NaN = same as previous row)          |
| Code system  | string | CPT, HCPCS, ICD-10-PCS, ICD-10, LOINC; forward-filled |
| Code         | string | Actual code value                                    |
| Description  | string | Human-readable (not used by code)                    |

Column names are case-sensitive. Must match exactly as shown.

## Forward-fill rules

- **Modality** and **Code system** are forward-filled (`ffill`) for multi-row modality blocks.
- First row per modality block has explicit Modality value; subsequent rows may have NaN.
- When Code system is NaN, the previous row's Code system applies.

## load_outcomes_code_lookup expectations

1. **Source:** CSV file (no sheets; single table)
2. **Code system mapping:**
   - `"CPT"` or `"HCPCS"` → `cpt_hcpcs` set
   - `"LOINC"` or any value containing `"LOINC"` → `loinc` set
   - Any value containing `"ICD-10"` (e.g. `"ICD-10-PCS"`, `"ICD-10"`, `"ICD-10-CM/PCS: ..."`) → `icd10` set
3. **Modality → slug:** Must match `MODALITY_SLUG_MAP` keys (e.g. `"Stem cell transplant"` → `SCT`). Unknown modalities are skipped.
4. **Code normalization:** Codes are uppercased and stripped before storage. Empty codes are skipped.
5. **Output:** `{modality_slug: {"cpt_hcpcs": set, "loinc": set, "icd10": set}}`

## Warning

Layout changes will break `load_outcomes_code_lookup`:

- Renaming columns (Modality, Code system, Code)
- Changing Code system value spelling (e.g. `"LOINC"` vs `"loinc"`)
- Changing Modality display names (must match `MODALITY_SLUG_MAP` exactly)
