# Phase 15: Insurance Summary Tables and Figures — Research

**Researched:** 2026-03-16  
**Domain:** HL payer-stratified reporting, small-cell suppression, Polars aggregation  
**Confidence:** HIGH (codebase); MEDIUM (figures — no existing figure pipeline)

---

## Summary

Phase 15 adds summary tables and figures stratified by the Phase 14 payer variables in `derived/encounter_payer_summary.parquet`. The codebase already provides: (1) `flag_small_cell` and `_suppress` for HIPAA; (2) report patterns in `assemble_clean.py` (DQ report, cleaning decisions) and `build_site_table.py` (site-stratified CSV/MD/HTML); (3) encounter_payer_summary schema (ID plus N_ENCOUNTERS, payer category at first DX/first chemo/last chemo/most frequent at chemo, PAYER_TRANSITION). No figure generation exists yet; reports go under `reports/` and `reports/figures/` is created but empty.

**Primary recommendation:** Add a dedicated script `scripts/build_insurance_summary.py` that reads `derived/encounter_payer_summary.parquet`, optionally joins to site (via `build_site_table` in memory or a shared derived table), produces markdown/CSV tables with `flag_small_cell`/`_suppress`, and generates bar-chart figures (e.g. matplotlib) with suppression applied (mask or exclude 1–10).

---

## User Constraints

*(No CONTEXT.md found for this phase; no locked decisions or deferred ideas to copy.)*

---

## Summary Tables

| Table | Description | Source columns | Suppression |
|-------|-------------|----------------|-------------|
| **Counts by PAYER_CATEGORY_AT_FIRST_DX** | One row per payer category; count of patients with that payer at first HL diagnosis. | `encounter_payer_summary.PAYER_CATEGORY_AT_FIRST_DX` | Apply `flag_small_cell` (MD) or `_suppress` (CSV) to each count. |
| **Counts by PAYER_CATEGORY_AT_FIRST_CHEMO** | One row per payer category; count at first chemo. | `PAYER_CATEGORY_AT_FIRST_CHEMO` | Same. |
| **Cross-tab: first DX vs first chemo** | Two-way table: rows = payer at first DX, columns = payer at first chemo; cell = patient count. | `PAYER_CATEGORY_AT_FIRST_DX`, `PAYER_CATEGORY_AT_FIRST_CHEMO` | Suppress each cell count; optionally suppress row/column margins. |
| **PAYER_TRANSITION prevalence** | Count (and %) of patients with PAYER_TRANSITION=1; optionally by payer category at first DX or first chemo. | `PAYER_TRANSITION` | Suppress counts 1–10. |
| **Optional: by site/partner** | Same tables stratified by SITE (e.g. UFH, ORL, TM). | Join to site-assigned patient table (see Data Sources and Joins). | Per-cell suppression; site_table pattern in `build_site_summary_table` (variable \| category \| Site1 \| Site2 \| …). |

**Category order (consistent with CODEBOOK and site_table):** Medicare, Medicaid, Private, Other government, No payment / Self-pay, Other, Unavailable, Unknown. Include "Unknown" / null as a row so totals match.

**Reference:** `src/report/site_table.py` — `build_site_summary_table()` builds variable \| category \| Site1 \| Site2 \| … with `flag_small_cell(n)` per cell; `_add_counts()` pattern.

---

## Figures

| Figure | Description | Data | Suppression |
|--------|-------------|------|-------------|
| **Bar chart: Payer at first DX** | Bar per payer category, height = patient count. | Counts by `PAYER_CATEGORY_AT_FIRST_DX`. | Either (a) exclude categories with count 1–10 from the chart and footnote, or (b) show bar but mask label (e.g. "≤10" or no value). Option (a) is safer for HIPAA. |
| **Bar chart: Payer at first chemo** | Same for first chemo. | Counts by `PAYER_CATEGORY_AT_FIRST_CHEMO`. | Same as above. |
| **Optional: by site** | Grouped or faceted bars (e.g. payer × site). | Counts by (SITE, payer at first DX or first chemo). | Suppress any bar representing 1–10 (do not draw or label with exact n). |

**Implementation:** No existing figure code in repo. Use **matplotlib** (or seaborn) for static PNGs under `reports/figures/`. Polars for aggregation; then pass counts to plotting (after applying suppression logic so that 1–10 are not displayed as exact values).

**Reference:** `reports/figures/` is created in `scripts/assemble_clean.py` (`figures_dir.mkdir(parents=True, exist_ok=True)`); no PNGs written yet.

---

## Output Paths and Naming

| Output | Path | Format |
|--------|------|--------|
| Insurance summary report (tables) | `reports/insurance_summary.md` | Markdown: sections per table, markdown tables with `flag_small_cell`. |
| Insurance summary table (machine-readable) | `reports/insurance_summary_tables.csv` or per-table CSVs (e.g. `reports/payer_at_first_dx.csv`) | CSV with `_suppress` for counts 1–10. |
| Figures | `reports/figures/insurance_payer_at_first_dx.png`, `reports/figures/insurance_payer_at_first_chemo.png` | PNG. Optional: `insurance_payer_at_first_dx_by_site.png` if by-site figures added. |

Existing convention: `reports/DATA_QUALITY_REPORT.md`, `reports/CLEANING_DECISIONS.md`, `reports/site_stratified_table.csv` / `.md` / `.html`. Keep insurance outputs under `reports/` and `reports/figures/` with an `insurance_*` prefix for clarity.

---

## Small-Cell Suppression

| Use case | Function | Source | Behavior |
|----------|----------|--------|----------|
| Markdown / human-facing counts | `flag_small_cell(value)` | `src/validate/structural.py` | Returns `"N"` for N outside 1–10; returns `"N ⚠"` for 1 ≤ N ≤ 10 (SMALL_CELL_THRESHOLD=10). |
| CSV / publishable tabular | `_suppress(value)` | `src/report/quality_report.py` | Returns `"-"` for 1 ≤ value ≤ 10; else `str(value)`. |

**Tables:** Apply to every cell count in summary tables (including margins/totals). If a total is 1–10, show "⚠" or "-" as well.

**Figures:** Do not display exact counts 1–10. Options: (1) Omit category from chart and add footnote "Categories with 1–10 patients omitted for privacy"; (2) Show bar but no numeric label, or label as "≤10". Prefer omitting or masking over publishing exact small counts.

**Reference:** `structural.py` lines 20–21 (SMALL_CELL_THRESHOLD), 492–499 (flag_small_cell); `quality_report.py` 487–491 (_suppress); `site_table.py` 409–410, 458–459 (flag_small_cell in summary table and HTML).

---

## Data Sources and Joins

| Data | Location | Use in Phase 15 |
|------|----------|-----------------|
| **encounter_payer_summary** | `derived/encounter_payer_summary.parquet` | Primary: ID, PAYER_CATEGORY_AT_FIRST_DX, PAYER_CATEGORY_AT_FIRST_CHEMO, PAYER_CATEGORY_AT_LAST_CHEMO, PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO, PAYER_TRANSITION, PAYER_CATEGORY_PRIMARY. Built by `build_encounter_payer_summary(table_map)` in assemble_clean; one row per enrolled patient with encounters. |
| **patient_level** | `derived/patient_level.parquet` | Does not contain SITE. Use for demographics only if needed (e.g. age/region); not required for payer-only tables. |
| **Site (SOURCE) stratification** | Not in patient_level. Site comes from `src/report/site_table.py`: `build_site_table(table_map)` returns a patient-level Polars DataFrame with SITE (predominant SOURCE; TMA/TMC→TM). That function is used by `build_site_table.py` to build the site-stratified summary; it does not write the patient-level SITE table to disk. |

**How to stratify by site:**  
Option A — In `build_insurance_summary.py`, load config and table_map, call `build_site_table(table_map)` to get `patient_df` with ID and SITE, then join `encounter_payer_summary` to `patient_df` on ID. Produce payer-by-site tables/figures using the same suppression rules.  
Option B — Add a derived output from the site_table pipeline (e.g. `derived/patient_site.parquet` with ID, SITE) and have build_insurance_summary read it. Option A avoids new derived artifacts and reuses existing API.

**Quality report / partner aggregation:** `aggregate_dq_metrics` in `quality_report.py` uses `completeness_by_partner` and ENCOUNTER with SOURCE for persistence (by year). Partner/site in DQ is per-table SOURCE; site_table’s SITE is patient-level predominant SOURCE. For insurance summaries, use the same patient-level SITE as site_stratified_table for consistency.

---

## Script Design

| Approach | Pros | Cons |
|----------|------|------|
| **New script: `scripts/build_insurance_summary.py`** | Single responsibility; mirrors `build_site_table.py`; can run after assemble_clean (reads derived/encounter_payer_summary.parquet). | One more entry point. |
| **Extend assemble_clean.py** | One script for all reports. | assemble_clean already does copy, patient_level, encounter_payer_summary, DQ, cleaning decisions, figures dir; adding payer tables/figures would bloat it. |
| **Extend build_site_table.py** | Site and insurance both "stratified reports." | Site table is site-centric (variable \| category \| sites); insurance summary is payer-centric (payer tables + optional site stratification). Different outputs and file names; mixing can be confusing. |

**Recommendation:** New script **`scripts/build_insurance_summary.py`**.

**Behavior:**  
1. Load paths (e.g. `load_config`); resolve `derived_dir` and `reports_dir`.  
2. Read `derived/encounter_payer_summary.parquet` (Polars). Exit gracefully if missing or empty.  
3. Optional: build site assignment via `build_site_table(table_map)` and join to encounter_payer_summary for by-site tables/figures (requires table_map from datastructure; same as build_site_table).  
4. Build summary tables (counts by payer at first DX, at first chemo, cross-tab, PAYER_TRANSITION) using Polars; apply `flag_small_cell` when writing markdown and `_suppress` when writing CSV.  
5. Write `reports/insurance_summary.md` and chosen CSV path(s).  
6. If figures requested: aggregate counts, apply suppression (exclude or mask 1–10), generate PNGs to `reports/figures/insurance_*.png`.  
7. Dependencies: Polars, `src.load.config`, `src.report.quality_report._suppress`, `src.validate.structural.flag_small_cell`; for site: `src.report.site_table.build_site_table` and schema/datastructure for table_map.

**Reference:** `scripts/build_site_table.py` (config load, table_map from datastructure, reports_dir, build_site_table → build_site_summary_table → CSV/MD/HTML). `scripts/assemble_clean.py` (derived_dir, reports_dir, encounter_payer_summary written to derived, figures_dir created).

---

## Standard Stack

| Library | Purpose | Version / note |
|---------|---------|----------------|
| Polars | Read parquet, group_by, counts, joins | Already used project-wide. |
| matplotlib | Bar charts for figures | Standard for static PNG; no existing usage in repo. |
| Pathlib / load_config | Paths | Same as assemble_clean, build_site_table. |

---

## Common Pitfalls

1. **Publishing unsuppressed counts:** Every count in tables and every bar value in figures must go through `flag_small_cell` or `_suppress` (or be omitted/masked). Cross-tabs and totals are no exception.  
2. **Null / Unknown handling:** Ensure null or "Unknown" payer category is a distinct category in tables so row/column totals match total N.  
3. **Site join key:** encounter_payer_summary uses `ID` (PATID_COL); site_table’s patient DataFrame uses `ID` (PATID_COL). Join on `ID`.  
4. **Empty encounter_payer_summary:** Phase 14 only includes patients with ENROLLMENT; if no ENCOUNTER or no PAYER_TYPE_PRIMARY, summary can be empty. Script should check and exit or write "No data" instead of failing.

---

## Code References (existing)

| Item | Location |
|------|----------|
| flag_small_cell, SMALL_CELL_THRESHOLD | `src/validate/structural.py` (lines 20–21, 492–499) |
| _suppress | `src/report/quality_report.py` (487–491) |
| build_encounter_payer_summary | `src/report/encounter_payer_summary.py` |
| build_site_table, build_site_summary_table | `src/report/site_table.py` |
| assemble_clean (derived + reports) | `scripts/assemble_clean.py` |
| build_site_table script | `scripts/build_site_table.py` |
| Encounter-payer schema and CODEBOOK | `docs/CODEBOOK.md` § 6a |

---

## Metadata

**Confidence breakdown:**  
- Summary tables and suppression: HIGH (existing patterns and code).  
- Figures: MEDIUM (no current figure code; approach is standard).  
- Script placement and data joins: HIGH (clear from codebase).

**Research date:** 2026-03-16  
**Valid until:** ~30 days; revisit if new report or figure standards are adopted.
