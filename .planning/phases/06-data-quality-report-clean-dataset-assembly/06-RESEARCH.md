# Phase 6: Data Quality Report & Clean Dataset Assembly - Research

**Researched:** 2026-03-02
**Domain:** Data quality reporting, derived variable assembly, small cell suppression, Parquet assembly
**Confidence:** HIGH

## Summary

Phase 6 is the FINAL phase. It aggregates quality metrics from Phases 3–5 into a comprehensive data quality report, creates HL-specific and insurance-specific derived variables, assembles a patient-level Parquet file, applies small cell suppression to all aggregate outputs, and documents all cleaning decisions. The technical approach reuses established patterns: `flag_small_cell` from `structural.py` for HIPAA-compliant reporting; Polars for cross-table assembly; `write_parquet(compression="snappy")` for output; and report generation via string-building functions (same style as `clean_all.py` and `validate_values.py`).

The primary design decision is **parquet_clean vs in-place**: the roadmap lists `data/parquet_clean/*.parquet` as output but Phase 5 writes in-place to `parquet_dir`. Writing to a separate `parquet_clean/` directory preserves the original validated+flagged Parquet for rollback; in-place keeps a single source of truth. Both approaches are viable — recommend `parquet_clean/` for a clear "final analysis-ready" boundary.

**Primary recommendation:** Use `src/report/quality_report.py` to aggregate Phases 3–5 outputs into `DATA_QUALITY_REPORT.md` with four sections (completeness, conformance, plausibility, persistence); build `patient_level.parquet` via cross-table joins (DEMOGRAPHIC + DIAGNOSIS + PROCEDURES + PRESCRIBING + TUMOR_REGISTRY + ENCOUNTER + ENROLLMENT + LDS_ADDRESS_HISTORY) for derived variables; write clean Parquet to `parquet_clean/`; reuse `flag_small_cell` for all report counts.

## User Constraints

No CONTEXT.md — use roadmap defaults.

### Success Criteria (from roadmap)
- Data quality report covering completeness, conformance, plausibility, persistence
- Report stratified by SOURCE (partner)
- HL-derived variables: AGE_AT_HL_DX, AGE_BAND, HL_SUBTYPE, FIRST_HL_DX_DATE, FIRST_HL_TX_DATE, DX_TO_TX_DAYS, PAYER_AT_DX, INSURANCE_CONTINUITY, REGION
- Small cell suppression on all aggregate outputs (counts 1–10 → "-")
- Clean Parquet with all flags retained and derived variables added
- CLEANING_DECISIONS.md documenting rules, thresholds, rationale

### HPC Learnings (from prior phases)
- TUMOR_REGISTRY dates: MM/DD/YYYY or YYYY.MM.DD
- Valuesets: utf8-lossy
- PATID_COL = "ID"
- Snappy compression for Parquet

### Deferred (OUT OF SCOPE)
- RUCA/ADI geographic codes
- Chemotherapy regimen identification (ABVD, BEACOPP)
- Radiation therapy data integration
- Replace vs extend HL-EDA clean layer (this project produces standalone cleaned dataset)

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Polars | 1.22.0+ | Cross-table joins, derived variable computation, Parquet read/write | Already in use; Phase 4/5 patterns for assembly; `write_parquet(compression="snappy")` |
| Python | 3.11 | Runtime | Already in hl-eda env |

### Supporting (already installed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| matplotlib / seaborn | HL-EDA env | Quality visualizations (heatmap, temporal plots) | Completeness heatmap, temporal coverage plots per roadmap |
| tomllib | stdlib | Config | Load `config/paths.toml` via `load_config()` |

### Not Needed

| Library | Why Not |
|---------|---------|
| pandas | Polars used throughout; avoid mixed ecosystems |
| DuckDB | Cross-table assembly straightforward in Polars |
| jinja2 | Report generation uses string-building (established in clean_all.py, validate_values.py) |

**Installation:** No new packages. All dependencies from Phases 1–5.

## Architecture Patterns

### Recommended Project Structure

```
src/
├── load/
│   ├── config.py           # existing — load_config()
│   └── schema.py           # existing — parse_datastructure()
├── validate/
│   ├── structural.py       # existing — PATID_COL, flag_small_cell, SMALL_CELL_THRESHOLD
│   ├── values.py           # existing — validation flag patterns
│   └── cohort.py           # existing — ALL_HL_CODES, ALL_HL_NORMALIZED, detect_dx_format
├── clean/
│   ├── dedup.py            # existing — flag patterns
│   └── harmonize.py        # existing — partner flags
└── report/                  # NEW
    └── quality_report.py   # DQ aggregation, derived vars, report generation

scripts/
├── clean_all.py            # existing
├── validate_all.py         # existing
├── validate_values.py      # existing
└── assemble_clean.py       # NEW — Phase 6 entry point (or integrate into quality_report.py)

reports/
├── structural_validation.md    # Phase 3
├── value_validation.md         # Phase 4
├── dedup_report.md             # Phase 5
├── consistency_report.md       # Phase 5
├── partner_harmonization.md    # Phase 5
├── DATA_QUALITY_REPORT.md      # NEW — Phase 6 aggregated
├── CLEANING_DECISIONS.md       # NEW — Phase 6
└── figures/                    # NEW — completeness heatmap, temporal plots

data/
├── parquet/                    # or parquet_dir — Phase 2–5 in-place
└── parquet_clean/               # NEW — final analysis-ready (recommend separate dir)
    └── ...
data/derived/
└── patient_level.parquet       # NEW — one row per HL patient + derived vars
```

### Pattern 1: DQ Report Dimensions

**What:** Four dimensions from roadmap — completeness, conformance, plausibility, persistence.
**When to use:** Structuring DATA_QUALITY_REPORT.md.
**Mapping to Phase 3–5 outputs:**

| Dimension | Source | Example Metrics |
|-----------|--------|-----------------|
| Completeness | Phase 3 structural, Phase 4/5 flags | Per-field non-null rates by partner; missing value classification |
| Conformance | Phase 4 value validation | Invalid code counts per coded field; ICD concordance |
| Plausibility | Phase 4 plausibility, temporal | Out-of-range vital/lab counts; temporal violations; DX_TO_TX_DAYS flags |
| Persistence | Phase 3 + aggregation | Data volume over time by partner; coverage gaps; drop-offs |

Aggregate by reading existing report files (if markdown) or re-computing from Parquet (if metrics not persisted). Re-computing from Parquet is more reliable and enables partner stratification from raw data.

### Pattern 2: Patient-Level Derived Variables

**What:** One row per HL patient with derived variables. Requires cross-table assembly.
**When to use:** Building `patient_level.parquet`.

Derived variables and sources:

| Variable | Source | Logic |
|----------|--------|-------|
| AGE_AT_HL_DX | DEMOGRAPHIC.BIRTH_DATE, first HL DX_DATE | (FIRST_HL_DX_DATE - BIRTH_DATE) in years; masked ages → fold into 65+ band |
| AGE_BAND | AGE_AT_HL_DX | &lt;21, 21-39, 40-64, 65+ (masked → 65+) |
| HL_SUBTYPE | C81.x 4th character | C81.0 nodular LP, C81.1 nodular sclerosis, etc. |
| FIRST_HL_DX_DATE | DIAGNOSIS (C81*/201*) | min(DX_DATE) per ID |
| FIRST_HL_TX_DATE | PROCEDURES, PRESCRIBING, TUMOR_REGISTRY | min across PX_DATE, RX_ORDER_DATE, DT_CHEMO/DT_RAD/DT_SURG |
| DX_TO_TX_DAYS | FIRST_HL_TX_DATE - FIRST_HL_DX_DATE | days; null if no treatment |
| PAYER_AT_DX | ENCOUNTER.PAYER_TYPE_PRIMARY | from encounter closest to FIRST_HL_DX_DATE |
| INSURANCE_CONTINUITY | ENROLLMENT | Flag gaps in enrollment covering HL treatment period |
| REGION | LDS_ADDRESS_HISTORY.ADDRESS_STATE | Southeast vs other (AL, AR, FL, GA, KY, LA, MS, NC, SC, TN, VA, WV) |

**Existing code:** `validate_values.py` already computes FIRST_HL_DX_DATE, FIRST_TX_DATE, DX_TO_TX_DAYS for the HL timeline report (`_hl_timeline_summary`). Extract or replicate this logic for patient-level assembly.

### Pattern 3: Small Cell Suppression

**What:** Replace counts 1–10 with "-" in published reports (HIPAA).
**When to use:** Every aggregate count in reports.
**Existing:** `flag_small_cell(value)` in `structural.py` — returns `f"{value} ⚠"` for 1–10, `str(value)` otherwise. Use for markdown reports. For CSV/final publishable output, use `_suppress`-style: return "-" for 1–10.

```python
# From src/validate/structural.py
def flag_small_cell(value: int) -> str:
    if 1 <= value <= SMALL_CELL_THRESHOLD:  # 10
        return f"{value} ⚠"
    return str(value)

# For publishable output (dash instead of count)
def _suppress(value: int) -> str:
    if 1 <= value <= SMALL_CELL_THRESHOLD:
        return "-"
    return str(value)
```

**CMS policy:** Counts 1–10 must not be reported directly. SEER-MHOS uses &lt;11. This project uses threshold 10 (consistent with Phases 3–5).

### Pattern 4: Parquet Output — parquet_clean vs In-Place

**Options:**
1. **parquet_clean/** — Copy/transform from parquet_dir to parquet_clean; add derived vars only to patient_level.parquet; table Parquets retain flags, no schema change.
2. **In-place** — Write back to parquet_dir; overwrite. Simpler but loses pre-final state.

**Recommendation:** Use `parquet_clean/` for final analysis-ready table Parquets; keep `parquet_dir` as "validated + flagged" intermediate. `patient_level.parquet` lives in `data/derived/` (new aggregated table, not a CDM table). Config: add `parquet_clean_dir` and `derived_dir` to paths.toml or derive from scratch_root.

### Pattern 5: CLEANING_DECISIONS.md Structure

**What:** Document every rule, threshold, rationale.
**Sections:**
1. **Value set validation** — valuesets.csv; NI/UN/OT handling
2. **Plausibility ranges** — VITAL_RANGES, HL_LAB_RANGES, AGE_AT_DIAGNOSIS 0–120/200
3. **Temporal rules** — ICD10_TRANSITION 2015-10-01; DX_TO_TX 0–365 days
4. **Deduplication** — DEDUP_KEYS per table
5. **Partner flags** — ICD_MAPPED, CLAIMS_ONLY, DEATH_ONLY
6. **Masked values** — BIRTH_DATE=1900-01-01, AGE_AT_DIAGNOSIS=200; fold into 65+
7. **TUMOR_REGISTRY date formats** — MM/DD/YYYY, YYYY.MM.DD fallback

### Anti-Patterns to Avoid

- **Deleting flags:** Clean Parquet must retain all Phase 4/5 flag columns.
- **Recomputing from scratch:** Reuse existing report data or Parquet stats where possible.
- **Hand-rolling derived vars:** Follow validate_values `_hl_timeline_summary` logic; don't invent new treatment date sources.
- **Skipping small cell suppression:** Every count in reports must go through `flag_small_cell` or equivalent.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Small cell suppression | Custom masking logic | `flag_small_cell` from structural.py | CMS/HIPAA standard; already used in Phases 3–5 |
| HL diagnosis extraction | New ICD matching | `ALL_HL_CODES`, `ALL_HL_NORMALIZED`, `detect_dx_format` from cohort.py | 149 codes; format-adaptive |
| Treatment date aggregation | Custom logic | Extend `_hl_timeline_summary` pattern from validate_values | PROCEDURES + PRESCRIBING + TUMOR_REGISTRY already wired |
| Parquet write | Custom writer | `df.write_parquet(path, compression="snappy")` | Consistent with Phases 2–5 |
| Report generation | Template engine | String-building (lines.append) like clean_all.py | Simple; no new deps |

**Key insight:** Phase 6 is aggregation and assembly. All core logic exists in Phases 3–5.

## Common Pitfalls

### Pitfall 1: PAYER_AT_DX When BND/UCI/UMI Have No Payer

**What goes wrong:** PAYER_AT_DX is null for 3 partners (BND, UCI, UMI) — not a bug.
**Why it happens:** Known data gap from roadmap.
**How to avoid:** Document in CLEANING_DECISIONS.md; report completeness by partner; do not infer payer from other sources without explicit rule.
**Warning signs:** Attempting to fill PAYER_AT_DX from ENROLLMENT.ENR_BASIS — possible but needs documented mapping.

### Pitfall 2: TUMOR_REGISTRY Date Parsing

**What goes wrong:** TR date columns may be string (MM/DD/YYYY or YYYY.MM.DD).
**Why it happens:** HPC learnings; Phase 4 handles via fallback chain.
**How to avoid:** Use same fallback in derived var assembly: `str.to_date("%Y.%m.%d", strict=False).fill_null(str.to_date("%m/%d/%Y", strict=False)).fill_null(str.to_date("%d%b%Y", strict=False))`.
**Warning signs:** All TR-derived FIRST_HL_TX_DATE null.

### Pitfall 3: REGION When LDS_ADDRESS_HISTORY Missing

**What goes wrong:** Many partners lack LDS_ADDRESS_HISTORY or ADDRESS_STATE.
**Why it happens:** Geographic data availability varies (roadmap: UCI has no ZIP).
**How to avoid:** REGION = "Unknown" when ADDRESS_STATE is null/NI/UN; Southeast = {AL, AR, FL, GA, KY, LA, MS, NC, SC, TN, VA, WV}.
**Warning signs:** Empty REGION for most patients.

### Pitfall 4: Masked Age → AGE_BAND

**What goes wrong:** AGE_AT_HL_DX is undefined when BIRTH_DATE=1900-01-01.
**Why it happens:** Age masking per HIPAA.
**How to avoid:** Fold masked ages into 65+ band (HL-EDA approach); document in CLEANING_DECISIONS.
**Warning signs:** AGE_BAND null for many patients.

### Pitfall 5: Consistency of parquet_dir Path

**What goes wrong:** load_config() resolves parquet_dir relative to scratch_root; paths.toml may use relative "hpc-upload/parquet".
**Why it happens:** Config structure from Phase 1.
**How to avoid:** Use load_config() for all paths; add parquet_clean_dir and derived_dir to config or derive as `parquet_dir.parent / "parquet_clean"` and `parquet_dir.parent / "derived"`.
**Warning signs:** Script writes to wrong directory on HPC.

## Code Examples

### Example 1: Aggregate Completeness by Partner

```python
# Aggregate from Parquet — per-column non-null rate by SOURCE
def completeness_by_partner(table_path: Path, cols: list[str]) -> pl.DataFrame:
    df = pl.read_parquet(table_path)
    if "SOURCE" not in df.columns:
        return pl.DataFrame()
    return (
        df.group_by("SOURCE")
        .agg([(pl.col(c).is_not_null().sum() / pl.len()).alias(f"{c}_rate") for c in cols if c in df.columns])
        .collect()
    )
```

### Example 2: FIRST_HL_DX_DATE and AGE_AT_HL_DX

```python
# From validate_values _hl_timeline_summary pattern
dx_format = detect_dx_format(diag_path)
code_set = ALL_HL_CODES if dx_format == "dotted" else ALL_HL_NORMALIZED
dx_match_col = pl.col("DX") if dx_format == "dotted" else pl.col("DX").str.to_uppercase().str.replace_all(r"\.", "")

first_dx = (
    pl.scan_parquet(diag_path)
    .with_columns(dx_match_col.alias("_DX_MATCH"))
    .filter(pl.col("_DX_MATCH").is_in(code_set))
    .filter(pl.col("DX_DATE").is_not_null())
    .group_by(PATID_COL)
    .agg(pl.col("DX_DATE").min().alias("FIRST_HL_DX_DATE"))
    .collect()
)

# Join with DEMOGRAPHIC for BIRTH_DATE
demo = pl.read_parquet(demo_path).select(PATID_COL, "BIRTH_DATE")
merged = first_dx.join(demo, on=PATID_COL, how="left")
# AGE_AT_HL_DX = (FIRST_HL_DX_DATE - BIRTH_DATE) in years
# Masked BIRTH_DATE (1900-01-01) → AGE_BAND = "65+"
```

### Example 3: Southeast REGION

```python
SOUTHEAST_STATES = {"AL", "AR", "FL", "GA", "KY", "LA", "MS", "NC", "SC", "TN", "VA", "WV"}

def assign_region(address_df: pl.DataFrame) -> pl.DataFrame:
    return address_df.with_columns(
        pl.when(pl.col("ADDRESS_STATE").is_null() | pl.col("ADDRESS_STATE").is_in(["NI", "UN", ""]))
        .then(pl.lit("Unknown"))
        .when(pl.col("ADDRESS_STATE").is_in(SOUTHEAST_STATES))
        .then(pl.lit("Southeast"))
        .otherwise(pl.lit("Other"))
        .alias("REGION")
    )
```

### Example 4: Report Generation Pattern (from clean_all.py)

```python
def _generate_dq_report(metrics: dict, reports_dir: Path, paths) -> Path:
    lines = []
    lines.append("# Data Quality Report\n")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Parquet directory:** {paths.parquet_dir}\n")
    # ... sections ...
    for k, v in metrics.items():
        lines.append(f"| {k} | {flag_small_cell(v)} |")
    out_path = reports_dir / "DATA_QUALITY_REPORT.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| HL-EDA: drops duplicates | Phase 5: flags, no delete | Reversible; Phase 6 retains flags |
| Phase 2–5: in-place parquet_dir | Phase 6 option: parquet_clean/ | Clear final-output boundary |
| No patient-level derived file | patient_level.parquet | Downstream EDA/modeling consume single file |

**Deprecated/outdated:**
- None specific to Phase 6 — builds on current Phase 3–5 outputs.

## Open Questions

1. **parquet_clean vs in-place**
   - What we know: Roadmap lists parquet_clean; Phase 5 writes in-place.
   - What's unclear: User preference.
   - Recommendation: Use parquet_clean/ for final tables; document in CLEANING_DECISIONS.

2. **CLEANING_DECISIONS.md scope**
   - What we know: "Every rule, threshold, rationale."
   - What's unclear: Whether to include Phase 3–5 rule text verbatim or summarize.
   - Recommendation: Summarize with pointers to Phase 3–5 reports; include all thresholds (SMALL_CELL_THRESHOLD=10, VITAL_RANGES, etc.).

3. **Figures directory**
   - What we know: Roadmap mentions "completeness heatmap (tables × partners)", "temporal coverage plot."
   - What's unclear: PNG vs embedded markdown tables.
   - Recommendation: Generate PNGs via matplotlib/seaborn; save to reports/figures/; reference in DATA_QUALITY_REPORT.md.

4. **INSURANCE_CONTINUITY definition**
   - What we know: "Flag for gaps in enrollment covering HL treatment period."
   - What's unclear: Treatment period = FIRST_HL_DX_DATE to FIRST_HL_TX_DATE + N days? Or fixed window?
   - Recommendation: Treatment window = FIRST_HL_DX_DATE to min(FIRST_HL_TX_DATE + 365, last encounter in window). Flag = 1 if any gap &gt; 30 days within that window.

## Sources

### Primary (HIGH confidence)
- Codebase: `src/validate/structural.py` (flag_small_cell, SMALL_CELL_THRESHOLD)
- Codebase: `scripts/validate_values.py` (_hl_timeline_summary, FIRST_HL_DX_DATE, DX_TO_TX_DAYS)
- Codebase: `scripts/clean_all.py` (report generation pattern, _suppress)
- Codebase: `src/validate/cohort.py` (ALL_HL_CODES, detect_dx_format)
- ROADMAP.md Phase 6 section

### Secondary (MEDIUM confidence)
- WebSearch: CMS cell suppression policy (counts 1–10); HHS/ResDAC guidance
- WebSearch: SEER-MHOS small cell &lt;11

### Tertiary (LOW confidence)
- Data quality frameworks (completeness, conformance, plausibility, persistence) — standard DQ taxonomy; not PCORnet-specific

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Polars, structural.py, cohort.py already proven
- Architecture: HIGH — follows Phase 4/5 patterns exactly
- Derived variables: HIGH — validate_values has FIRST_HL_DX_DATE, DX_TO_TX_DAYS logic; PAYER_AT_DX, REGION, INSURANCE_CONTINUITY need net-new but straightforward
- Small cell suppression: HIGH — flag_small_cell established; CMS policy 1–10 verified
- Pitfalls: HIGH — from roadmap partner gaps, HPC learnings, Phase 4/5 verification reports

**Research date:** 2026-03-02
**Valid until:** 2026-04-02 (stable — no new libraries, established patterns)
