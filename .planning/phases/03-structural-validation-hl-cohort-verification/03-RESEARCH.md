# Phase 3: Structural Validation & HL Cohort Verification - Research

**Researched:** 2026-02-27
**Domain:** PCORnet CDM v6.1 schema validation, referential integrity, HL cohort definition, per-partner completeness profiling
**Confidence:** HIGH

## Summary

Phase 3 is purely diagnostic — it reads 22 Parquet files (Phase 2 output), compares their schemas against expected column lists parsed from the DatasetCoverPage, verifies PATID (`ID`) and ENCOUNTERID referential integrity, confirms the HL cohort definition (~9,331 patients with C81\*/201\* codes at 2+ encounters on different dates), and profiles per-column completeness stratified by partner (the `SOURCE` column present in all OneFlorida+ CDM tables). No data is modified.

The technical approach is straightforward: use `pl.read_parquet_schema()` for schema comparison without loading full data, `pl.scan_parquet()` with lazy evaluation for integrity and completeness checks, and explicit ICD code enumeration (not prefix matching) for cohort verification. All outputs are markdown reports and CSV files — no Parquet modifications.

The key complexity is in the HL cohort verification algorithm, which must check two parallel definitions (2+ distinct DX_DATEs vs 2+ distinct ADMIT_DATEs), investigate any count mismatch vs the expected 9,331, perform a deep enrollment cross-check, and flag each patient's ICD version profile (ICD9_ONLY, ICD10_ONLY, BOTH). The DatasetCoverPage parsing is also non-trivial — its format is a tab-delimited text file with table-by-table variable listings, but the exact structure must be probed at runtime since no standard parser exists.

**Primary recommendation:** Structure Phase 3 as four independent validation modules (schema, integrity, cohort, completeness) that each produce their own report section, then assemble into a single comprehensive markdown report. Use Polars lazy evaluation throughout to avoid loading all 22 tables simultaneously.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**CDM Schema Reference:**
- Source for expected columns: Parse from DatasetCoverPage variable lists that came with the data extract. Do not hardcode from the official CDM documentation.
- Extra columns (in data but not in CDM): Warn and keep — flag in the report but leave them in the Parquet files.
- Missing columns (expected but absent): Warn only — note in the report, do not add empty placeholder columns.
- TUMOR_REGISTRY schema: Do not validate against CDM spec (they follow NAACCR, not PCORnet). Just verify column counts match expectations (~265, ~120, ~120) and that key cancer staging variables are present.

**HL Cohort Verification:**
- Diagnosis code matching: Use an exact code list enumerating all valid C81.x and 201.x subcodes, not a loose prefix match.
- DX_TYPE filter: Match by code prefix alone — do not require DX_TYPE=10 for ICD-10 or DX_TYPE=09 for ICD-9. DX_TYPE may be missing for some partners. Report any DX_TYPE mismatches found (e.g., C81 code with DX_TYPE=09) but don't use them to exclude records.
- 2+ encounters rule: Check both ways — (1) 2+ distinct DX_DATE values with HL codes, and (2) 2+ distinct ADMIT_DATEs from ENCOUNTER where linked HL DX exists. Report any differences between the two methods.
- Count mismatch handling: Investigate if the verified count doesn't match 9,331. Break down where the discrepancy comes from (which partners, which ICD version, which date range). The user notes that the ENROLLMENT dataset already doesn't have 9,331 unique patients — investigate this too.
- Enrollment cross-check: Deep investigation — report how many HL patients have enrollment records and coverage periods, AND check if uncovered patients cluster in specific partners or time periods.
- ICD version flag: Add a flag column to the cohort summary — ICD9_ONLY, ICD10_ONLY, or BOTH — for each patient.

**Validation Report Format:**
- Report format: Markdown (.md) — readable in GitHub and editors, easy to generate.
- Per-partner detail: Heatmap-style — partners as rows, columns as columns, color-coded completeness. (In markdown, approximate with symbols like full/half/empty blocks or percentage coloring.)
- Small-cell suppression: Flag cells that would need suppression if published, but show actual counts. These are internal QC reports, not publishable outputs.

**Integrity Failure Handling:**
- Orphan patient IDs (clinical tables with IDs not in DEMOGRAPHIC): Flag and report — count orphans per table, list in report, but keep them in the data.
- Orphan encounter IDs (event tables with ENCOUNTERIDs not in ENCOUNTER): Flag and report — count per table, note in report.
- CHP LAB_RESULT_CM exception: Skip ENCOUNTERID check for CHP lab records — document as known limitation from DatasetCoverPage.
- Phase 3 is diagnostic only: Do NOT modify Parquet files or drop records. Report problems. Phases 4-5 handle data fixes.

### Claude's Discretion
- Completeness CSV row granularity (per table+column+partner vs per table+column)
- Internal report organization (single large report vs multiple focused reports)
- Heatmap symbols for markdown completeness display

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REQ-01 | Load 22 large CSV files as fast as possible (now Parquet — 10-100x faster reads) | `pl.scan_parquet()` for lazy reads; `pl.read_parquet_schema()` for schema-only reads without loading data; Parquet files already on `/blue` from Phase 2 |
| REQ-03 | Clean data for HL insurance inequities analysis (cohort verification, tumor registry, insurance/payer validation, partner-stratified quality) | HL cohort verification algorithm with exact ICD code lists; completeness profiling stratified by SOURCE (partner); enrollment cross-check; PAYER_TYPE_PRIMARY completeness highlighted |
| REQ-04 | Run on HiPerGator HPC | Same interactive session pattern as Phase 2; Polars auto-parallelizes; 64GB memory sufficient for lazy evaluation of 9,331-patient cohort |
| REQ-05 | HIPAA-compliant data handling | Reports contain aggregate counts only; small-cell values flagged but shown (internal QC); data stays on `/blue` and `/orange`; no patient-level exports |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Polars | 1.22.0+ | Lazy Parquet reads, schema comparison, group_by aggregation, completeness profiling | Already installed; `scan_parquet()` enables memory-efficient profiling; `read_parquet_schema()` for schema-only reads |
| Python | 3.11 | Runtime | Already in hl-eda env; stdlib `pathlib`, `re`, `csv` |

### Supporting (already installed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| DuckDB | 1.4.4+ | Optional cross-table SQL joins for integrity checks | Alternative to Polars joins for complex multi-table queries; already installed |

### No Additional Dependencies Needed

Phase 3 uses only Polars (already installed) plus Python stdlib. The DatasetCoverPage parser uses only stdlib `re` and text processing. Report generation uses stdlib string formatting.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Polars group_by for completeness | DuckDB SQL aggregation | DuckDB is more natural for multi-table joins but adds SQL string construction overhead; Polars is consistent with existing Phase 1-2 code |
| Python string formatting for markdown | Jinja2 templates | Jinja2 is in the conda env but adds complexity; markdown reports are simple enough for f-string/format generation |
| Manual completeness heatmap | matplotlib/seaborn image | User decision is markdown reports; images would require display environment; markdown approximation with symbols is more portable |

## Architecture Patterns

### Recommended Project Structure (Phase 3 additions)

```
src/
├── load/
│   ├── config.py          # existing — Paths dataclass
│   ├── schema.py          # existing — datastructure.txt parser
│   └── convert.py         # existing — Phase 2
└── validate/
    ├── __init__.py         # NEW — package init
    ├── structural.py       # NEW — schema comparison, integrity, completeness
    └── cohort.py           # NEW — HL cohort verification
scripts/
├── smoke_test.py           # existing
├── convert_all.py          # existing
└── validate_all.py         # NEW — Phase 3 entry point
reports/                    # NEW — output directory (on /blue)
├── structural_validation.md
├── completeness_by_partner.csv
└── cohort_summary.csv
```

### Discretion Recommendation: Report Organization

**Recommendation:** Single comprehensive markdown report (`structural_validation.md`) with clear section headers, plus two companion CSV files for machine-readable detail. The markdown report covers all four domains (schema, integrity, cohort, completeness) in one document for easy review, with the CSV files providing granular data for downstream use.

**Rationale:**
- A single report gives the user a complete picture without navigating multiple files
- Section headers with a table of contents make it navigable
- CSV companions enable programmatic consumption of completeness data
- The user's discretion note allows this organization

### Discretion Recommendation: Completeness CSV Granularity

**Recommendation:** Per table + column + partner (one row per combination). This is the most granular form and supports all downstream aggregations (roll up to table+column by averaging across partners, or table+partner by summarizing columns).

### Discretion Recommendation: Heatmap Symbols

**Recommendation:** Use Unicode block characters for markdown heatmap approximation:

| Completeness | Symbol | Description |
|-------------|--------|-------------|
| 95-100% | `█` (U+2588) | Full block — excellent |
| 75-94% | `▓` (U+2593) | Dark shade — good |
| 50-74% | `▒` (U+2592) | Medium shade — moderate |
| 25-49% | `░` (U+2591) | Light shade — poor |
| 1-24% | `·` (U+00B7) | Middle dot — very poor |
| 0% | `○` (U+25CB) | Circle — empty |
| N/A | `—` (U+2014) | Em dash — table not present for partner |

Include the actual percentage alongside the symbol for precision: `█ 98%`

### Pattern 1: DatasetCoverPage Parsing

**What:** Parse the DatasetCoverPage text file to extract expected column names per CDM table.
**Why:** User locked decision — expected columns come from DatasetCoverPage, not hardcoded CDM docs.
**Key Challenge:** The DatasetCoverPage format is specific to the OneFlorida+ data extract. It's a text/tab-delimited file at `/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915/DatasetCoverPage_Mailhot_V1_20251024.txt`. The exact format must be probed at runtime — there is no standard parser.

**Approach:** Read the file, identify table-by-table sections (look for table names like "DEMOGRAPHIC", "ENCOUNTER", etc. as section headers), and extract variable/column names from each section. The parser should be resilient to format variations (tab-delimited columns, varying whitespace, header rows).

```python
def parse_cover_page(path: Path) -> dict[str, list[str]]:
    """Parse DatasetCoverPage to get expected columns per table.

    Returns {table_name: [column_names]}.
    Format-adaptive: tries tab-delimited sections, falls back to
    pattern matching on known table names.
    """
    text = path.read_text(encoding="utf-8-sig")  # handle BOM
    tables: dict[str, list[str]] = {}
    current_table = None
    # Implementation depends on actual file format — probe at runtime
    # Look for lines that match known table names as section markers
    # Then collect column names from subsequent lines
    return tables
```

**Important:** The TUMOR_REGISTRY tables follow NAACCR, not PCORnet CDM. Per user decision, only verify column counts (~265, ~120, ~120) and key variables — don't validate against CDM spec.

**Fallback:** If the DatasetCoverPage format proves too complex or inconsistent, a secondary approach is to use the actual Parquet column lists from Phase 2 as the "expected" schema (i.e., self-consistent validation: are all tables internally consistent?). But the user decision says to use DatasetCoverPage, so this is a last resort.

### Pattern 2: Schema Comparison Without Loading Data

**What:** Compare actual Parquet columns against expected columns from DatasetCoverPage.
**Why:** `pl.read_parquet_schema()` returns column names and dtypes without loading any data — fast and memory-efficient.

```python
import polars as pl

def compare_schema(
    parquet_path: Path,
    expected_cols: list[str],
    table_name: str,
) -> dict:
    """Compare Parquet schema against expected columns."""
    actual_schema = pl.read_parquet_schema(parquet_path)
    actual_cols = set(actual_schema.keys())
    expected_set = set(expected_cols)

    extra = sorted(actual_cols - expected_set)
    missing = sorted(expected_set - actual_cols)
    matched = sorted(actual_cols & expected_set)

    return {
        "table": table_name,
        "expected_count": len(expected_cols),
        "actual_count": len(actual_cols),
        "matched": len(matched),
        "extra": extra,     # warn and keep
        "missing": missing,  # warn only
    }
```

### Pattern 3: Referential Integrity via Anti-Join

**What:** Find orphan IDs using Polars anti-join — records in child tables that have no match in the parent table.
**Why:** Polars `join(how="anti")` is the idiomatic way to find orphans without loading both full tables.

```python
def check_patid_integrity(
    child_path: Path,
    demographic_path: Path,
    child_table: str,
) -> dict:
    """Check that all IDs in child table exist in DEMOGRAPHIC."""
    demo_ids = pl.scan_parquet(demographic_path).select("ID").unique()
    child_ids = pl.scan_parquet(child_path).select("ID").unique()

    orphans = child_ids.join(demo_ids, on="ID", how="anti").collect()
    total_unique = child_ids.collect().height

    return {
        "table": child_table,
        "unique_ids": total_unique,
        "orphan_ids": orphans.height,
        "orphan_pct": round(orphans.height / max(total_unique, 1) * 100, 2),
    }


def check_encounterid_integrity(
    child_path: Path,
    encounter_path: Path,
    child_table: str,
    partner_col: str = "SOURCE",
    skip_partner: str | None = None,  # e.g. "CHP" for LAB_RESULT_CM
) -> dict:
    """Check that all ENCOUNTERIDs in child table exist in ENCOUNTER."""
    enc_ids = pl.scan_parquet(encounter_path).select("ENCOUNTERID").unique()

    child_lf = pl.scan_parquet(child_path)

    if skip_partner and partner_col in child_lf.collect_schema().names():
        child_lf = child_lf.filter(pl.col(partner_col) != skip_partner)

    if "ENCOUNTERID" not in child_lf.collect_schema().names():
        return {"table": child_table, "skipped": True, "reason": "no ENCOUNTERID column"}

    child_enc = child_lf.select("ENCOUNTERID").filter(
        pl.col("ENCOUNTERID").is_not_null()
    ).unique()

    orphans = child_enc.join(enc_ids, on="ENCOUNTERID", how="anti").collect()
    total = child_enc.collect().height

    return {
        "table": child_table,
        "unique_encounterids": total,
        "orphan_encounterids": orphans.height,
        "orphan_pct": round(orphans.height / max(total, 1) * 100, 2),
        "skip_partner": skip_partner,
    }
```

### Pattern 4: HL Cohort Verification Algorithm

**What:** Confirm the HL cohort definition with exact code matching, dual-date checking, and enrollment cross-check.
**Why:** Core Phase 3 deliverable — the cohort is the foundation of the entire study.

The algorithm has five stages:

**Stage 1: Extract HL diagnosis records using exact code list**
```python
ICD10_HL_CODES = {
    f"C81.{sub}{site}"
    for sub in ("0", "1", "2", "3", "4", "7", "9")
    for site in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "A")
}  # 77 codes: C81.00-C81.9A

ICD9_HL_CODES = {
    f"201.{sub}{site}"
    for sub in ("0", "1", "2", "4", "5", "6", "7", "9")
    for site in ("0", "1", "2", "3", "4", "5", "6", "7", "8")
}  # 72 codes: 201.00-201.98

ALL_HL_CODES = ICD10_HL_CODES | ICD9_HL_CODES
```

**Stage 2: Method A — 2+ distinct DX_DATEs per patient**
```python
hl_dx = (
    pl.scan_parquet(diagnosis_path)
    .filter(pl.col("DX").is_in(ALL_HL_CODES))
    .select("ID", "DX", "DX_DATE", "DX_TYPE")
)

method_a = (
    hl_dx
    .group_by("ID")
    .agg(pl.col("DX_DATE").n_unique().alias("distinct_dx_dates"))
    .filter(pl.col("distinct_dx_dates") >= 2)
    .collect()
)
```

**Stage 3: Method B — 2+ distinct ADMIT_DATEs from linked encounters**
```python
hl_with_enc = (
    hl_dx
    .join(
        pl.scan_parquet(encounter_path).select("ENCOUNTERID", "ADMIT_DATE"),
        on="ENCOUNTERID",
        how="inner",
    )
)

method_b = (
    hl_with_enc
    .group_by("ID")
    .agg(pl.col("ADMIT_DATE").n_unique().alias("distinct_admit_dates"))
    .filter(pl.col("distinct_admit_dates") >= 2)
    .collect()
)
```

**Stage 4: Compare methods and report differences**
```python
a_ids = set(method_a["ID"].to_list())
b_ids = set(method_b["ID"].to_list())
# a_only = patients with 2+ DX_DATEs but NOT 2+ ADMIT_DATEs
# b_only = patients with 2+ ADMIT_DATEs but NOT 2+ DX_DATEs
# both = intersection
```

**Stage 5: ICD version flag per patient**
```python
icd_flags = (
    hl_dx
    .with_columns(
        pl.when(pl.col("DX").str.starts_with("C81"))
        .then(pl.lit("ICD10"))
        .when(pl.col("DX").str.starts_with("201"))
        .then(pl.lit("ICD9"))
        .otherwise(pl.lit("UNKNOWN"))
        .alias("icd_version")
    )
    .group_by("ID")
    .agg(pl.col("icd_version").n_unique().alias("version_count"),
         pl.col("icd_version").unique().alias("versions"))
    .with_columns(
        pl.when(pl.col("version_count") > 1).then(pl.lit("BOTH"))
        .when(pl.col("versions").list.first() == "ICD10").then(pl.lit("ICD10_ONLY"))
        .when(pl.col("versions").list.first() == "ICD9").then(pl.lit("ICD9_ONLY"))
        .otherwise(pl.lit("UNKNOWN"))
        .alias("icd_flag")
    )
    .collect()
)
```

### Pattern 5: Completeness Profiling per Partner

**What:** Calculate per-column completeness (% non-null) for every table, stratified by the SOURCE column.
**Why:** User decision requires partner-stratified completeness heatmap.

```python
def completeness_by_partner(
    parquet_path: Path,
    table_name: str,
    partner_col: str = "SOURCE",
) -> pl.DataFrame:
    """Compute per-column completeness stratified by partner."""
    lf = pl.scan_parquet(parquet_path)
    schema = lf.collect_schema()

    if partner_col not in schema.names():
        return pl.DataFrame()  # table has no SOURCE column

    analysis_cols = [c for c in schema.names() if c != partner_col]

    result = (
        lf.group_by(partner_col)
        .agg(
            [pl.len().alias("row_count")]
            + [
                (1 - pl.col(c).null_count() / pl.len()).alias(c)
                for c in analysis_cols
            ]
        )
        .collect()
    )

    return result.unpivot(
        index=[partner_col, "row_count"],
        variable_name="column",
        value_name="completeness",
    ).with_columns(pl.lit(table_name).alias("table"))
```

### Pattern 6: Markdown Report Generation

**What:** Generate structured markdown report with sections, tables, and heatmap visualization.
**Why:** User locked decision on markdown format.

```python
def completeness_heatmap_symbol(pct: float) -> str:
    """Map completeness percentage to Unicode block character."""
    if pct >= 0.95:
        return "█"
    elif pct >= 0.75:
        return "▓"
    elif pct >= 0.50:
        return "▒"
    elif pct >= 0.25:
        return "░"
    elif pct > 0:
        return "·"
    else:
        return "○"


def format_heatmap_row(partner: str, completeness_dict: dict[str, float]) -> str:
    """Format a single row of the completeness heatmap."""
    cells = [f"| {partner} "]
    for col, pct in completeness_dict.items():
        sym = completeness_heatmap_symbol(pct)
        cells.append(f"| {sym} {pct:.0%} ")
    return "".join(cells) + "|"
```

### Pattern 7: Enrollment Cross-Check

**What:** Deep investigation of enrollment coverage for HL cohort patients.
**Why:** User noted ENROLLMENT doesn't have 9,331 unique patients — this needs investigation.

```python
def enrollment_crosscheck(
    cohort_ids: pl.DataFrame,  # ID column of confirmed HL patients
    enrollment_path: Path,
    partner_col: str = "SOURCE",
) -> dict:
    """Cross-check HL cohort against enrollment records."""
    enr = pl.scan_parquet(enrollment_path)

    # How many HL patients have ANY enrollment record?
    hl_with_enr = (
        cohort_ids.lazy()
        .join(enr.select("ID").unique(), on="ID", how="inner")
        .collect()
    )

    # How many have NO enrollment record?
    hl_without_enr = (
        cohort_ids.lazy()
        .join(enr.select("ID").unique(), on="ID", how="anti")
        .collect()
    )

    # Break down uncovered patients by partner
    # Join with DEMOGRAPHIC to get SOURCE for uncovered patients
    # ...

    # Coverage gap analysis: ENR_START_DATE to ENR_END_DATE periods
    # by partner and time period
    # ...

    return {
        "total_hl_patients": cohort_ids.height,
        "with_enrollment": hl_with_enr.height,
        "without_enrollment": hl_without_enr.height,
        "coverage_pct": round(hl_with_enr.height / cohort_ids.height * 100, 2),
    }
```

### Anti-Patterns to Avoid

- **Prefix matching for ICD codes:** User locked decision says exact code list, not `DX.str.starts_with("C81")`. Build the full set of 149 codes (77 ICD-10 + 72 ICD-9) and use `is_in()`.
- **Filtering by DX_TYPE:** User locked decision — do NOT require DX_TYPE=10/09 to match HL codes. Match by code value alone. Report DX_TYPE mismatches but don't exclude.
- **Modifying Parquet files:** Phase 3 is diagnostic only. No `write_parquet()`, no flag columns added, no record drops.
- **Hardcoding CDM column lists:** User locked decision — parse from DatasetCoverPage. The schema_comparison function must use runtime-parsed expected columns.
- **Loading all 22 tables eagerly:** Use `scan_parquet()` (lazy) and `read_parquet_schema()` (schema-only) to minimize memory footprint.
- **Suppressing small cell counts:** User decision says show actual counts — these are internal QC reports. Flag which counts would need suppression if published.
- **Skipping TUMOR_REGISTRY validation entirely:** User says verify column counts and key variables, just don't validate against CDM spec.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema extraction from Parquet | Manual column parsing | `pl.read_parquet_schema(path)` | Returns dict of col→dtype without loading data; handles all Parquet metadata |
| Anti-join for orphan detection | Manual set operations on collected IDs | `lf.join(parent, on="ID", how="anti")` | Polars anti-join is optimized and stays lazy until collect |
| Per-column null counts | Python loop over columns | `df.null_count()` or `lf.null_count().collect()` | Single vectorized operation across all columns |
| Group-by aggregation | Manual partition + loop | `lf.group_by("SOURCE").agg(...)` | Polars group_by is parallelized and handles arbitrary expressions |
| Unique value counting | `len(set(col.to_list()))` | `pl.col("DX_DATE").n_unique()` | Native Polars expression, stays in lazy plan |
| Set membership check | Python loop over code list | `pl.col("DX").is_in(ALL_HL_CODES)` | Polars hash-based is_in is O(1) per row |
| DataFrame unpivot for long-form completeness | Manual loops building rows | `df.unpivot(index=..., variable_name=..., value_name=...)` | Native Polars reshape operation |

**Key insight:** Phase 3 is entirely a read + aggregate + report phase. Polars lazy evaluation with `scan_parquet()` is ideal because it allows building complex query plans (joins, group_by, filter) that execute efficiently without materializing intermediate results.

## Common Pitfalls

### Pitfall 1: PATID is Called `ID`, Not `PATID`

**What goes wrong:** Code references `PATID` (the PCORnet CDM standard name), but this dataset uses `ID` as the patient identifier column name in all tables.
**Why it happens:** OneFlorida+ data extracts sometimes rename columns. The roadmap explicitly notes "PATID column is called `ID` in all tables."
**How to avoid:** Always use `"ID"` when referencing the patient identifier. Consider defining a constant: `PATID_COL = "ID"`.
**Warning signs:** `ColumnNotFoundError: 'PATID'` — the column doesn't exist.

### Pitfall 2: CHP LAB_RESULT_CM Has No ENCOUNTERID

**What goes wrong:** ENCOUNTERID integrity check fails or produces misleading orphan counts for LAB_RESULT_CM because CHP records have null/missing ENCOUNTERID.
**Why it happens:** CHP partner doesn't include ENCOUNTERID in their LAB_RESULT_CM data submission — documented in DatasetCoverPage.
**How to avoid:** When checking ENCOUNTERID integrity for LAB_RESULT_CM, filter out CHP records (identified by SOURCE column). Document the exception in the report.
**Warning signs:** LAB_RESULT_CM shows anomalously high orphan ENCOUNTERID rate.

### Pitfall 3: ICD-10 Code C81.xA ("In Remission") Extension

**What goes wrong:** The "in remission" extension code `C81.xA` (e.g., C81.0A, C81.1A) uses a letter rather than a digit as the site extension. If the code list only includes digit extensions 0-9, these patients are missed.
**Why it happens:** Most ICD-10 C81 codes use digits 0-9 for site, but "A" = in remission was added later and uses a non-numeric character.
**How to avoid:** Include the `A` extension in the code list: `for site in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "A")`. This yields 77 ICD-10 codes (7 subtypes × 11 extensions).
**Warning signs:** Small number of HL patients "missing" from cohort who have remission codes.

### Pitfall 4: AMS/UMI ICD-9→ICD-10 Mapping Inflates ICD10_ONLY Counts

**What goes wrong:** Patients from AMS and UMI are flagged as ICD10_ONLY even though their original historical codes were ICD-9. This is because these partners retrospectively mapped all ICD-9 codes to ICD-10.
**Why it happens:** AMS mapped ICD-9→ICD-10 for all diagnoses. UMI did the same.
**How to avoid:** In the ICD version flag output, note that AMS and UMI patients flagged as ICD10_ONLY may originally have been ICD-9. Report this as a known data characteristic, not an error. Consider adding a partner-stratified breakdown of the ICD version flag.
**Warning signs:** Surprisingly few ICD9_ONLY or BOTH patients from AMS/UMI partners.

### Pitfall 5: ENCOUNTERID Column May Be Missing or All-Null in Some Tables

**What goes wrong:** Some tables (especially from specific partners or for specific table types like ENROLLMENT, DEATH, DISPENSING) may not have ENCOUNTERID at all, or it may be present but 100% null.
**Why it happens:** Not all PCORnet CDM tables require ENCOUNTERID. ENROLLMENT, DEATH, DEATH_CAUSE, LDS_ADDRESS_HISTORY, PROVIDER, and DISPENSING link through PATID or other keys instead.
**How to avoid:** Check whether ENCOUNTERID exists in the schema before attempting integrity checks. Only check tables where ENCOUNTERID is expected per CDM specification.
**Warning signs:** `ColumnNotFoundError: 'ENCOUNTERID'` or 100% orphan rate.

### Pitfall 6: SOURCE Column Name May Differ

**What goes wrong:** The partner/site identifier column may not be named `SOURCE` in all tables, or it may be absent in some tables (like PROVIDER).
**Why it happens:** OneFlorida+ data extracts may use different column names across tables for the site identifier.
**How to avoid:** Probe for the partner column at runtime. Check for `SOURCE`, `SITE`, or similar names. If absent, skip partner stratification for that table.
**Warning signs:** `ColumnNotFoundError: 'SOURCE'` — need to adapt to actual column name.

### Pitfall 7: Null DX_DATE in DIAGNOSIS Table

**What goes wrong:** Some DIAGNOSIS records have null DX_DATE, which means they can't contribute to the "2+ distinct DX_DATEs" criterion. If many HL records have null DX_DATE, the cohort count may be lower than expected.
**Why it happens:** DX_DATE is not always populated in PCORnet CDM — some partners derive diagnoses from claims or problem lists where the date is approximate or missing.
**How to avoid:** Count HL patients with null DX_DATE separately. Report how many would qualify if null-date records are excluded vs included. Use ADMIT_DATE from the linked encounter as a fallback date.
**Warning signs:** Method A count (DX_DATE) is significantly lower than Method B count (ADMIT_DATE).

### Pitfall 8: Lazy Query Errors from Schema Mismatches in Joins

**What goes wrong:** Polars lazy joins fail with type mismatch errors when joining on columns that have different types across tables (e.g., `ID` is String in DEMOGRAPHIC but Int64 in another table).
**Why it happens:** Phase 2 used `infer_schema=False` for DEMOGRAPHIC (all String), but if some tables were parsed differently, types may not match.
**How to avoid:** Before joining, cast the join key to a common type (String is safest): `pl.col("ID").cast(pl.String)`.
**Warning signs:** `SchemaError: datatypes don't match` or `ComputeError: cannot compare` during join.

## Code Examples

### Complete Schema Validation for One Table

```python
import polars as pl
from pathlib import Path

def validate_table_schema(
    parquet_path: Path,
    expected_cols: list[str] | None,
    table_name: str,
    is_tumor_registry: bool = False,
    expected_col_count: int | None = None,
) -> dict:
    """Validate schema for one table.

    For TUMOR_REGISTRY tables, only checks column count and key variables.
    For CDM tables, compares against expected column list.
    """
    schema = pl.read_parquet_schema(parquet_path)
    actual_cols = list(schema.keys())

    result = {
        "table": table_name,
        "actual_col_count": len(actual_cols),
        "status": "ok",
        "details": [],
    }

    if is_tumor_registry:
        if expected_col_count:
            diff = len(actual_cols) - expected_col_count
            if abs(diff) > 10:
                result["status"] = "warn"
                result["details"].append(
                    f"Expected ~{expected_col_count} columns, got {len(actual_cols)} (diff={diff})"
                )
        key_vars = {"ID", "DATE_OF_DIAGNOSIS"}
        missing_keys = key_vars - set(actual_cols)
        if missing_keys:
            result["status"] = "warn"
            result["details"].append(f"Missing key variables: {missing_keys}")
    elif expected_cols:
        expected_set = set(expected_cols)
        actual_set = set(actual_cols)
        extra = sorted(actual_set - expected_set)
        missing = sorted(expected_set - actual_set)

        if extra:
            result["details"].append(f"Extra columns ({len(extra)}): {extra}")
        if missing:
            result["status"] = "warn"
            result["details"].append(f"Missing columns ({len(missing)}): {missing}")
        result["expected_col_count"] = len(expected_cols)
        result["matched"] = len(actual_set & expected_set)
        result["extra"] = extra
        result["missing"] = missing

    return result
```

### PATID Uniqueness Check in DEMOGRAPHIC

```python
def check_patid_uniqueness(demographic_path: Path) -> dict:
    """Verify ID is unique in DEMOGRAPHIC."""
    df = pl.scan_parquet(demographic_path)
    total = df.select(pl.len()).collect().item()
    unique = df.select(pl.col("ID").n_unique()).collect().item()
    duplicates = total - unique

    return {
        "total_rows": total,
        "unique_ids": unique,
        "duplicate_ids": duplicates,
        "is_unique": duplicates == 0,
    }
```

### Tables Requiring ENCOUNTERID Integrity Check

```python
ENCOUNTER_LINKED_TABLES = [
    "DIAGNOSIS",
    "PROCEDURES",
    "CONDITION",
    "VITAL",
    "LAB_RESULT_CM",
    "PRESCRIBING",
    "MED_ADMIN",
    "OBS_CLIN",
    "OBS_GEN",
    "IMMUNIZATION",
]

PATID_LINKED_TABLES = [
    "DEMOGRAPHIC",   # primary key table
    "ENROLLMENT",
    "ENCOUNTER",
    "DIAGNOSIS",
    "PROCEDURES",
    "CONDITION",
    "VITAL",
    "LAB_RESULT_CM",
    "PRESCRIBING",
    "DISPENSING",
    "MED_ADMIN",
    "DEATH",
    "DEATH_CAUSE",
    "LDS_ADDRESS_HISTORY",
    "IMMUNIZATION",
    "OBS_CLIN",
    "OBS_GEN",
    "PRO_CM",
    "TUMOR_REGISTRY1",
    "TUMOR_REGISTRY2",
    "TUMOR_REGISTRY3",
]
```

### Small-Cell Flagging (Without Suppression)

```python
SMALL_CELL_THRESHOLD = 10

def flag_small_cells(value: int) -> str:
    """Flag counts that would need suppression if published."""
    if 1 <= value <= SMALL_CELL_THRESHOLD:
        return f"{value} ⚠"  # flag but show actual value
    return str(value)
```

## ICD Code Reference

### ICD-10-CM C81.x — Hodgkin Lymphoma (77 codes)

7 histological subtypes × 11 site extensions (0-9, A):

| Subtype | Code Prefix | Description |
|---------|------------|-------------|
| C81.0x | C81.0 | Nodular lymphocyte predominant |
| C81.1x | C81.1 | Nodular sclerosis (classic) |
| C81.2x | C81.2 | Mixed cellularity (classic) |
| C81.3x | C81.3 | Lymphocyte depleted (classic) |
| C81.4x | C81.4 | Lymphocyte-rich (classic) |
| C81.7x | C81.7 | Other Hodgkin lymphoma (classic) |
| C81.9x | C81.9 | Unspecified |

Site extensions (5th character):

| Extension | Description |
|-----------|-------------|
| 0 | Unspecified site |
| 1 | Lymph nodes of head, face, and neck |
| 2 | Intrathoracic lymph nodes |
| 3 | Intra-abdominal lymph nodes |
| 4 | Lymph nodes of axilla and upper limb |
| 5 | Lymph nodes of inguinal region and lower limb |
| 6 | Intrapelvic lymph nodes |
| 7 | Spleen |
| 8 | Lymph nodes of multiple sites |
| 9 | Extranodal and solid organ sites |
| A | In remission |

**Note:** C81.5x and C81.6x do NOT exist — there is no ICD-10 subtype 5 or 6 for Hodgkin lymphoma.

### ICD-9-CM 201.x — Hodgkin's Disease (72 codes)

8 histological subtypes × 9 site extensions (0-8):

| Subtype | Code Prefix | Description |
|---------|------------|-------------|
| 201.0x | 201.0 | Hodgkin's paragranuloma |
| 201.1x | 201.1 | Hodgkin's granuloma |
| 201.2x | 201.2 | Hodgkin's sarcoma |
| 201.4x | 201.4 | Lymphocytic-histiocytic predominance |
| 201.5x | 201.5 | Nodular sclerosis |
| 201.6x | 201.6 | Mixed cellularity |
| 201.7x | 201.7 | Lymphocytic depletion |
| 201.9x | 201.9 | Unspecified type |

Site extensions (5th digit):

| Extension | Description |
|-----------|-------------|
| 0 | Unspecified site / extranodal |
| 1 | Lymph nodes of head, face, and neck |
| 2 | Intrathoracic lymph nodes |
| 3 | Intra-abdominal lymph nodes |
| 4 | Lymph nodes of axilla and upper limb |
| 5 | Lymph nodes of inguinal region and lower limb |
| 6 | Intrapelvic lymph nodes |
| 7 | Spleen |
| 8 | Lymph nodes of multiple sites |

**Note:** ICD-9 201.3x does NOT exist — there is no subtype 3 for Hodgkin's disease in ICD-9.

### Code Generation Pattern

```python
ICD10_HL_CODES: set[str] = {
    f"C81.{sub}{site}"
    for sub in ("0", "1", "2", "3", "4", "7", "9")
    for site in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "A")
}  # 77 codes

ICD9_HL_CODES: set[str] = {
    f"201.{sub}{site}"
    for sub in ("0", "1", "2", "4", "5", "6", "7", "9")
    for site in ("0", "1", "2", "3", "4", "5", "6", "7", "8")
}  # 72 codes

ALL_HL_CODES: set[str] = ICD10_HL_CODES | ICD9_HL_CODES  # 149 codes
```

### Code Matching Consideration: Truncated Codes

In practice, DIAGNOSIS.DX values may store codes without the dot separator (e.g., `"C8110"` instead of `"C81.10"`) or truncated to 3-4 characters (e.g., `"C81"` or `"C811"`). The implementation should:
1. First check the actual format of DX values in the data (sample a few)
2. Normalize both the code list and data values to the same format (strip dots, uppercase)
3. Match on the normalized form

```python
def normalize_dx(code: str) -> str:
    """Normalize diagnosis code: uppercase, remove dots."""
    return code.upper().replace(".", "")

ICD10_HL_NORMALIZED = {normalize_dx(c) for c in ICD10_HL_CODES}
ICD9_HL_NORMALIZED = {normalize_dx(c) for c in ICD9_HL_CODES}
ALL_HL_NORMALIZED = ICD10_HL_NORMALIZED | ICD9_HL_NORMALIZED
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Load full DataFrame to inspect columns | `pl.read_parquet_schema(path)` | Polars 0.18+ | Zero data loaded; returns {col: dtype} dict instantly |
| Manual set operations for orphan detection | `lf.join(parent, how="anti")` | Polars anti-join | Lazy, parallelized, memory-efficient |
| Loop over columns for null counts | `df.null_count()` or `lf.null_count()` | Polars native | Single vectorized operation |
| `df.melt()` for unpivot | `df.unpivot()` | Polars 1.0+ | `melt` renamed to `unpivot` in Polars 1.0 |
| Prefix match `str.startswith("C81")` | Exact set match `is_in(ALL_HL_CODES)` | User decision | More precise; avoids catching non-HL codes that might start with same prefix |

**Deprecated/outdated:**
- `polars.DataFrame.melt()`: Renamed to `unpivot()` in Polars 1.0+. Use `df.unpivot()`.
- `str.strptime()`: Deprecated in favor of `str.to_date()` / `str.to_datetime()`.

## Open Questions

1. **DatasetCoverPage format — what does it actually look like?**
   - What we know: It's at `/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915/DatasetCoverPage_Mailhot_V1_20251024.txt`. Referenced in `datastructure.txt`. Contains variable lists per table for the Mailhot_V1 extract.
   - What's unclear: Exact file format — tab-delimited? Fixed-width? Sections per table? Column headers? Encoding?
   - Recommendation: The implementation should probe the file format at runtime. Read the first 100 lines, identify patterns (table name markers, column delimiters), and adapt. This is a LOW-risk item because even if the parser needs adjustments, the file is small and the format is deterministic. **The planner should allocate a task specifically for DatasetCoverPage format exploration and parser development.**

2. **What is the SOURCE/partner column actually named?**
   - What we know: 15 partners (AMS, AVH, BND, CHP, etc.) are documented. Per-partner stratification is required. The column is likely named `SOURCE` (common in OneFlorida+ extracts).
   - What's unclear: Whether it's `SOURCE`, `SITE`, or something else. Whether it appears in ALL tables or only some.
   - Recommendation: Probe the actual column name at runtime from the first Parquet file. Define a constant and use it throughout. If the column doesn't exist in some tables, skip partner stratification for those tables.

3. **How are DX codes formatted in the DIAGNOSIS table?**
   - What we know: PCORnet CDM specifies DX as a string field. The code might include dots (C81.10) or not (C8110). It might be zero-padded or truncated.
   - What's unclear: Actual format in Mailhot_V1 data.
   - Recommendation: Sample a few DIAGNOSIS.DX values at runtime, check for dot presence, and normalize accordingly. Build the exact code set in both dotted and undotted forms.

4. **Does DIAGNOSIS have an ENCOUNTERID column for the Method B join?**
   - What we know: PCORnet CDM v6.1 includes ENCOUNTERID in the DIAGNOSIS table. It should be present.
   - What's unclear: Whether it's populated for all partners, especially after Phase 2 conversion.
   - Recommendation: Check that ENCOUNTERID exists and is non-null for the join. If null for many records, Method B will undercount — document this.

5. **Are there ICD codes stored without the decimal point?**
   - What we know: Different EHR systems store ICD codes with or without the decimal. OneFlorida+ CDM standardization should normalize this, but it's not guaranteed.
   - What's unclear: Whether codes are `"C81.10"` or `"C8110"` in the data.
   - Recommendation: LOW risk. Normalize both the code list and data to a common format (strip dots) before matching. This handles either format.

6. **Which tables should have their row counts reported?**
   - What we know: Phase 2 produces `file_inventory.csv` with per-table row counts. Phase 3 should cross-reference these.
   - Recommendation: Include row counts per table in the structural validation report as context. Read from `file_inventory.csv` if available; otherwise, use `pl.scan_parquet(path).select(pl.len()).collect()`.

## Sources

### Primary (HIGH confidence)
- ICD-10-CM C81 code list: eclaims.com and icd10data.com — verified complete list of 77 codes across 7 subtypes with 11 site extensions (0-9, A)
- ICD-9-CM 201 code list: icd9data.com — verified complete list of 72 codes across 8 subtypes with 9 site extensions (0-8)
- Polars `read_parquet_schema()`: docs.pola.rs — verified returns {col_name: dtype} dict without loading data
- Polars `LazyFrame.null_count()`: docs.pola.rs — verified aggregates null counts across all columns lazily
- Polars `unpivot()`: docs.pola.rs — confirmed rename from `melt()` in Polars 1.0+
- Existing Phase 1-2 code: `config.py`, `schema.py`, `convert.py` — verified module interfaces and patterns

### Secondary (MEDIUM confidence)
- PCORnet CDM v6.1/v7.0 table schemas: Healthcare research document in `.planning/research/HEALTHCARE_DATA_RESEARCH.md` — comprehensive table/column reference verified against official PCORnet docs
- PCORnet linking relationships: HEALTHCARE_DATA_RESEARCH.md — PATID/ENCOUNTERID relationship diagram verified
- DatasetCoverPage format: Based on typical OneFlorida+ data delivery practices — exact format needs runtime verification
- Partner data availability: From ROADMAP.md partner matrix — documented from DatasetCoverPage analysis

### Tertiary (LOW confidence)
- SOURCE column name assumption: Common OneFlorida+ convention but not verified against actual Parquet files
- DX code format (dotted vs undotted): Assumed standard PCORnet CDM format but needs runtime verification
- TUMOR_REGISTRY column counts (~265, ~120, ~120): From user context, not independently verified

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Polars APIs verified against official docs; same stack as Phase 2
- Architecture: HIGH — All patterns use standard Polars operations (scan_parquet, join, group_by, null_count); anti-join for orphan detection is textbook
- ICD code lists: HIGH — Verified against authoritative sources (icd10data.com, icd9data.com, eclaims.com); complete enumeration with site extensions
- Pitfalls: HIGH — CHP exception documented in project context; AMS/UMI mapping documented; ID vs PATID confirmed in roadmap
- DatasetCoverPage parsing: LOW — Format unknown until runtime; parser design is speculative
- SOURCE column naming: LOW — Assumed but unverified; needs runtime probing

**Research date:** 2026-02-27
**Valid until:** 2026-03-29 (30 days — Polars APIs stable; ICD codes don't change; project data is fixed extract)
