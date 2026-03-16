# Phase 15: Insurance Summary Tables and Figures — Execution Summary

**Plan:** 15-01-PLAN.md  
**Executed:** Phase 15 implementation complete

---

## Implemented

### Script

- **`scripts/build_insurance_summary.py`**
  - Entry point: `python scripts/build_insurance_summary.py [config/paths.toml]`
  - Loads `load_config()`; reads `paths.derived_dir` and writes to `PROJECT_ROOT / "reports"` and `reports/figures`.
  - Reads `derived/encounter_payer_summary.parquet`; exits with message (no traceback) if missing or empty.
  - Builds four summary tables with `flag_small_cell` (markdown) and `_suppress` (CSV).
  - Generates two bar charts (matplotlib) with categories 1–10 excluded; saves PNGs to `reports/figures/`.

### Outputs

| Output | Path |
|--------|------|
| Insurance summary report | `reports/insurance_summary.md` |
| Payer at first DX (counts) | `reports/payer_at_first_dx.csv` |
| Payer at first chemo (counts) | `reports/payer_at_first_chemo.csv` |
| Cross-tab first DX vs first chemo | `reports/payer_crosstab_first_dx_first_chemo.csv` |
| Payer transition prevalence | `reports/payer_transition_prevalence.csv` |
| Bar chart: payer at first DX | `reports/figures/insurance_payer_at_first_dx.png` |
| Bar chart: payer at first chemo | `reports/figures/insurance_payer_at_first_chemo.png` |

### Tables

1. **Counts by payer at first HL diagnosis** — one row per payer category, N with suppression.
2. **Counts by payer at first chemotherapy** — same for first chemo.
3. **Cross-tab: Payer at first diagnosis vs payer at first chemotherapy** — two-way table with row/column totals; all cells suppressed.
4. **Payer transition prevalence** — N with transition, total N, % with transition.

### Figures

- Bar charts for payer at first DX and at first chemo.
- Categories with count in 1–10 are excluded from the chart (HIPAA); if all excluded, a placeholder note is shown.

### Optional (not in scope)

- SITE stratification (join to `build_site_table(table_map)` on ID) can be added later; see 15-RESEARCH.md.

---

## Verification

- Run with missing/empty `encounter_payer_summary.parquet`: script exits with message, no exception.
- Run with valid parquet: all four table sections in `insurance_summary.md`, four CSVs, two PNGs produced; counts 1–10 show "⚠" in markdown and "-" in CSV.
