# Phase 5: Deduplication, Cross-Table Consistency & Partner Harmonization - Research

**Researched:** 2026-02-28
**Domain:** Record deduplication, multi-table data consistency, partner-level harmonization, insurance coverage alignment
**Confidence:** HIGH

## Summary

Phase 5 adds four layers of data quality flags to the existing Parquet files: (1) exact-match duplicate detection per table using composite keys, (2) cross-table consistency checks ensuring demographic agreement and event-encounter temporal alignment, (3) partner-level harmonization flags encoding known data provenance characteristics (ICD mapping, claims-only, death-only), and (4) insurance consistency flags verifying encounter coverage by enrollment periods. All operations produce additive flag columns — no records are deleted.

The technical approach builds directly on Phase 4's established patterns: Polars for DataFrame manipulation, binary Int8 flag columns, `write_validated()`-style Parquet write-back with snappy compression, and a script entry point following the `PROJECT_ROOT / sys.path` pattern. The primary new technique is `pl.struct(key_cols).is_duplicated()` for composite-key duplicate detection, which creates a struct of the key columns and tests for duplicated tuples across the DataFrame. Cross-table consistency requires loading reference tables (DEMOGRAPHIC, ENCOUNTER, DEATH, ENROLLMENT, TUMOR_REGISTRY) into memory and joining them against event tables — a pattern already established in Phase 4's `_load_birth_death_lookup()` and `_validate_against_birth()` functions.

The architecture splits into two new modules (`src/clean/dedup.py` for deduplication and cross-table consistency, `src/clean/harmonize.py` for partner harmonization and insurance consistency) plus a new entry-point script (`scripts/clean_all.py`). This follows the existing pattern of `src/validate/*.py` + `scripts/validate_*.py` but uses a `clean/` namespace to distinguish cleaning operations from validation. Three markdown reports are generated: `dedup_report.md`, `consistency_report.md`, and `partner_harmonization.md`.

**Primary recommendation:** Use `pl.struct(key_cols).is_duplicated().cast(pl.Int8)` for exact-match dedup flagging per table, join-based consistency checks against DEMOGRAPHIC/ENCOUNTER/ENROLLMENT reference tables, and simple `SOURCE`-based conditional expressions for partner harmonization flags. Follow the Phase 4 pattern exactly: flags are Int8 columns added to existing Parquet files, idempotent via `drop_existing_flags()` equivalent for Phase 5 flag prefixes.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Polars | 1.22.0+ | DataFrame manipulation, struct-based dedup, cross-table joins, flag column creation | Already installed; `pl.struct().is_duplicated()` for composite-key dedup; lazy evaluation for memory-efficient cross-table joins |
| Python | 3.11 | Runtime | Already in hl-eda env; stdlib `pathlib`, `datetime`, `dataclasses` |

### Supporting (already installed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tomllib | stdlib | Config loading | Load `config/paths.toml` via existing `load_config()` |

### Not Needed

| Library | Why Not |
|---------|---------|
| DuckDB | Cross-table joins are straightforward in Polars; no SQL needed for this phase |
| fuzzywuzzy / rapidfuzz | Roadmap explicitly specifies exact-match dedup only — no fuzzy matching |

**Installation:** No new packages needed. All dependencies already installed from Phases 1–4.

## Architecture Patterns

### Recommended Project Structure

```
src/
├── clean/
│   ├── __init__.py          # empty
│   ├── dedup.py             # dedup functions + cross-table consistency
│   └── harmonize.py         # partner harmonization + insurance consistency
├── load/
│   ├── config.py            # existing — reuse load_config()
│   └── schema.py            # existing — reuse parse_datastructure()
└── validate/
    ├── structural.py         # existing — reuse PATID_COL, constants
    └── values.py             # existing — reuse drop_existing_flags(), write_validated()
scripts/
└── clean_all.py              # Phase 5 entry point
reports/
├── dedup_report.md
├── consistency_report.md
└── partner_harmonization.md
```

### Pattern 1: Composite-Key Duplicate Detection with pl.struct

**What:** Detect exact duplicates on a subset of columns using Polars struct-based `is_duplicated()`.
**When to use:** Every table that needs deduplication on a composite key.
**Why:** `pl.struct()` combines multiple columns into a single struct so `is_duplicated()` evaluates the tuple, not individual columns.

```python
DEDUP_KEYS: dict[str, list[str]] = {
    "DIAGNOSIS":    ["ID", "DX_DATE", "DX"],
    "PROCEDURES":   ["ID", "PX_DATE", "PX"],
    "LAB_RESULT_CM":["ID", "SPECIMEN_DATE", "LAB_LOINC"],
    "ENCOUNTER":    ["ID", "ADMIT_DATE", "ENC_TYPE", "FACILITYID"],
    "VITAL":        ["ID", "MEASURE_DATE"],
    "PRESCRIBING":  ["ID", "RX_ORDER_DATE", "RXNORM_CUI"],
}

def flag_duplicates(df: pl.DataFrame, table_name: str) -> pl.DataFrame:
    keys = DEDUP_KEYS.get(table_name)
    if not keys:
        return df
    available_keys = [k for k in keys if k in df.columns]
    if len(available_keys) < 2:
        return df
    # Null keys should not match — fill with sentinel or skip nulls
    df = df.with_columns(
        pl.struct(available_keys)
        .is_duplicated()
        .cast(pl.Int8)
        .alias("IS_DUPLICATE")
    )
    return df
```

**Critical detail:** `pl.struct().is_duplicated()` treats two rows with null keys as NOT duplicates (struct equality semantics — null != null). This is correct behavior for dedup: a row with null DX_DATE should not be flagged as a duplicate of another row with null DX_DATE. Verified from Polars docs: null values in structs do not compare as equal.

### Pattern 2: Cross-Table Consistency via Reference Joins

**What:** Load reference tables (DEMOGRAPHIC, ENCOUNTER) once, join against event tables to check consistency.
**When to use:** Checking that demographic attributes are consistent across tables, or that events fall within encounter windows.
**Already established:** Phase 4's `_load_birth_death_lookup()` and `_validate_against_birth()` follow this exact pattern.

```python
def check_demographic_consistency(
    table_map: dict[str, Path],
) -> pl.DataFrame:
    demo = pl.read_parquet(table_map["DEMOGRAPHIC"])
    id_col = "ID"
    # Single BIRTH_DATE per ID
    birth_counts = (
        demo.group_by(id_col)
        .agg(pl.col("BIRTH_DATE").n_unique().alias("n_birth_dates"))
        .filter(pl.col("n_birth_dates") > 1)
    )
    return birth_counts
```

### Pattern 3: Partner Harmonization Flags via SOURCE Column

**What:** Add boolean flag columns based on the SOURCE (partner) column value.
**When to use:** Tables where SOURCE identifies the data-contributing partner.

```python
PARTNER_FLAGS = {
    "ICD_MAPPED": {"AMS", "UMI"},
    "CLAIMS_ONLY": {"FLM"},
    "DEATH_ONLY": {"VRT"},
}

def add_partner_flags(df: pl.DataFrame, partner_col: str = "SOURCE") -> pl.DataFrame:
    if partner_col not in df.columns:
        return df
    for flag_name, partners in PARTNER_FLAGS.items():
        df = df.with_columns(
            pl.col(partner_col).is_in(partners)
            .cast(pl.Int8)
            .alias(flag_name)
        )
    return df
```

### Pattern 4: Insurance Consistency via Enrollment Window Check

**What:** Join ENROLLMENT periods with ENCOUNTER dates to flag encounters outside enrollment windows.
**When to use:** Insurance consistency validation.

```python
def flag_encounters_outside_enrollment(
    encounter_df: pl.DataFrame,
    enrollment_df: pl.DataFrame,
) -> pl.DataFrame:
    # For each encounter, check if ANY enrollment period covers it
    # Expand enrollment to per-patient date ranges
    enr = enrollment_df.select("ID", "ENR_START_DATE", "ENR_END_DATE")
    
    # Cross join encounter with enrollment on ID, then check date coverage
    merged = (
        encounter_df.lazy()
        .join(enr.lazy(), on="ID", how="left")
        .with_columns(
            pl.when(
                pl.col("ENR_START_DATE").is_not_null()
                & pl.col("ENR_END_DATE").is_not_null()
                & (pl.col("ADMIT_DATE") >= pl.col("ENR_START_DATE"))
                & (pl.col("ADMIT_DATE") <= pl.col("ENR_END_DATE"))
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .alias("_covered")
        )
        .group_by(encounter_df.columns)
        .agg(pl.col("_covered").max().alias("_any_covered"))
        .collect()
    )
    
    return merged.with_columns(
        pl.when(pl.col("_any_covered") == 0)
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .cast(pl.Int8)
        .alias("_dup_outside_enrollment")
    ).drop("_any_covered")
```

### Pattern 5: Phase 5 Flag Naming Convention

Phase 4 uses `_val_` infix for validation flags. Phase 5 needs distinct prefixes to avoid collision with `drop_existing_flags()`:

| Flag Type | Naming Convention | Examples |
|-----------|-------------------|----------|
| Deduplication | `IS_DUPLICATE` | Single column per table |
| Cross-table consistency | `_con_` infix | `BIRTH_DATE_con_mismatch`, `_con_outside_encounter` |
| Partner harmonization | Direct name | `ICD_MAPPED`, `CLAIMS_ONLY`, `DEATH_ONLY` |
| Insurance consistency | `_con_` infix | `_con_outside_enrollment`, `_con_no_enrollment` |

This keeps Phase 5 flags distinguishable from Phase 4's `_val_` flags.

### Anti-Patterns to Avoid

- **Deleting duplicates:** Phase 5 flags only — never remove rows. The `IS_DUPLICATE` flag allows downstream consumers to decide.
- **Loading all tables at once:** Process one table at a time (same as Phase 4), with reference tables loaded once upfront.
- **Using join_asof for tolerance:** The ±1 day tolerance for events-within-encounters is simpler with explicit date arithmetic (`ADMIT_DATE - timedelta(days=1)`) than `join_asof(tolerance="1d")`, which only returns nearest matches (one-to-one), not all matches within window.
- **Fuzzy matching:** The roadmap explicitly excludes fuzzy matching. Stick to exact composite keys only.
- **Checking dedup across partners:** Duplicates should be detected within each table's full dataset, not per-partner. A patient appearing at two partners is NOT a duplicate — they have different records.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Composite-key duplicate detection | Custom row hashing or nested loops | `pl.struct(keys).is_duplicated()` | Polars optimizes struct equality checks vectorized; hand-rolled hashing is slower and error-prone |
| Date window containment | Manual date comparison loops | Polars vectorized `pl.col("date").is_between(start, end)` | Vectorized is 100x faster; handles nulls correctly |
| Cross-table joins | Reading tables repeatedly per check | Load reference tables once, join lazily | Memory and I/O efficiency; established Phase 4 pattern |
| Parquet write-back with stats | Custom writer | Extend `write_validated()` from Phase 4 or create equivalent | Consistent snappy compression, stats collection, flag counting |

**Key insight:** All Phase 5 operations are combinations of joins, group-by aggregations, and conditional expressions — standard Polars operations that don't require custom algorithms.

## Common Pitfalls

### Pitfall 1: Null Key Values in Dedup

**What goes wrong:** If a composite key column (e.g., DX_DATE) is null, Polars `pl.struct().is_duplicated()` treats nulls as unequal. Two rows with `(ID=1, DX_DATE=null, DX="C81.10")` will NOT be flagged as duplicates.
**Why it happens:** SQL/Polars null semantics: NULL != NULL.
**How to avoid:** This is actually the CORRECT behavior for dedup — a record with missing date should not be auto-flagged as duplicate of another record with missing date. Document this in the report so users understand.
**Warning signs:** Dedup rates that seem surprisingly low on tables with many null date values.

### Pitfall 2: Enrollment Join Explosion

**What goes wrong:** Joining ENCOUNTER with ENROLLMENT on ID creates a many-to-many explosion (each patient has multiple encounters AND multiple enrollment periods).
**Why it happens:** No unique key between the two tables — the join is ID-only.
**How to avoid:** Use a two-step approach: (1) expand the join, (2) aggregate back to one row per encounter using `group_by(encounter_columns).agg(max("_covered"))`. Alternatively, pre-compute per-patient enrollment ranges (min start, max end) if only checking overall coverage.
**Warning signs:** DataFrame size explodes 10-100x after join; out-of-memory on HPC.

### Pitfall 3: Numeric Columns Still String from Phase 2

**What goes wrong:** Some columns expected to be numeric (FACILITYID, RXNORM_CUI) may still be stored as strings from Phase 2 conversion.
**Why it happens:** Phase 2 inferred types but may not have cast all columns.
**How to avoid:** Cast dedup key columns to String before struct creation so comparisons are consistent. This matches Phase 4's pattern of `pl.col(PATID_COL).cast(pl.String)`.
**Warning signs:** Type mismatch errors during struct creation or join operations.

### Pitfall 4: TUMOR_REGISTRY Date Columns as Strings

**What goes wrong:** TUMOR_REGISTRY date columns may be stored as strings in formats like MM/DD/YYYY or YYYY.MM.DD, not proper Date types.
**Why it happens:** Discovered during Phase 4 HPC execution — these columns were not fully converted in Phase 2.
**How to avoid:** When comparing DEATH_DATE from DEATH table vs TUMOR_REGISTRY, parse TR date strings first using the Phase 4 fallback chain: `str.to_date("%m/%d/%Y", strict=False).fill_null(str.to_date("%d%b%Y", strict=False))`.
**Warning signs:** All TR date comparisons return null or zero matches.

### Pitfall 5: Deprecated Polars is_in with Series

**What goes wrong:** `pl.col("SOURCE").is_in(some_series)` may fail with deprecation warning.
**Why it happens:** Polars deprecated `is_in` with same-dtype Series — requires `.implode()` or a plain Python list.
**How to avoid:** Always pass a Python `set` or `list` to `is_in()`, not a Polars Series. E.g., `pl.col("SOURCE").is_in({"AMS", "UMI"})`.
**Warning signs:** DeprecationWarning or TypeError at runtime.

### Pitfall 6: CHP Has No ENCOUNTERID in LAB_RESULT_CM

**What goes wrong:** Events-within-encounter checks for LAB_RESULT_CM will fail for CHP records.
**Why it happens:** Known data limitation — CHP doesn't provide ENCOUNTERID linkage for labs.
**How to avoid:** Skip encounter-window checks for LAB_RESULT_CM rows where ENCOUNTERID is null, or skip CHP specifically (same as Phase 3's approach).
**Warning signs:** 100% of CHP LAB_RESULT_CM flagged as "outside encounter window."

### Pitfall 7: Memory Explosion on Enrollment-Encounter Cross Join

**What goes wrong:** Naive left join of ENCOUNTER (millions of rows) × ENROLLMENT (millions of rows) on ID creates billions of intermediate rows.
**Why it happens:** Each patient may have 10-50 encounters and 5-20 enrollment periods.
**How to avoid:** Process in chunks by partner or by patient batch. Or pre-aggregate enrollment into per-patient coverage ranges (union of periods) before joining. For the ±1 day encounter check, process one event table at a time and use lazy evaluation.
**Warning signs:** HPC job killed by OOM (>64GB memory).

## Code Examples

### Example 1: Exact-Match Dedup with IS_DUPLICATE Flag

```python
import polars as pl

DEDUP_KEYS = {
    "DIAGNOSIS":     ["ID", "DX_DATE", "DX"],
    "PROCEDURES":    ["ID", "PX_DATE", "PX"],
    "LAB_RESULT_CM": ["ID", "SPECIMEN_DATE", "LAB_LOINC"],
    "ENCOUNTER":     ["ID", "ADMIT_DATE", "ENC_TYPE", "FACILITYID"],
    "VITAL":         ["ID", "MEASURE_DATE"],
    "PRESCRIBING":   ["ID", "RX_ORDER_DATE", "RXNORM_CUI"],
}

def flag_duplicates(df: pl.DataFrame, table_name: str) -> pl.DataFrame:
    keys = DEDUP_KEYS.get(table_name)
    if not keys:
        return df
    available = [k for k in keys if k in df.columns]
    if len(available) < 2:
        return df
    # Cast all key columns to string for consistent comparison
    cast_exprs = [pl.col(k).cast(pl.String).alias(k) for k in available]
    df_cast = df.with_columns(cast_exprs)
    is_dup = (
        pl.struct([pl.col(k) for k in available])
        .is_duplicated()
        .cast(pl.Int8)
    )
    # Restore original types by using original df with new column
    df = df.with_columns(
        df_cast.select(is_dup.alias("IS_DUPLICATE"))["IS_DUPLICATE"]
    )
    return df
```

**Simpler approach (recommended):** Since we only need the boolean mask, compute it on a temporary view:

```python
def flag_duplicates(df: pl.DataFrame, table_name: str) -> pl.DataFrame:
    keys = DEDUP_KEYS.get(table_name)
    if not keys:
        return df
    available = [k for k in keys if k in df.columns]
    if len(available) < 2:
        return df
    mask = df.select(available).is_duplicated()
    df = df.with_columns(mask.cast(pl.Int8).alias("IS_DUPLICATE"))
    return df
```

This uses `DataFrame.is_duplicated()` on a column subset — simpler and avoids struct overhead.

### Example 2: Single BIRTH_DATE per Patient Check

```python
def check_single_birth_date(demo_df: pl.DataFrame) -> pl.DataFrame:
    """Return patients with multiple distinct BIRTH_DATE values."""
    return (
        demo_df
        .group_by("ID")
        .agg(
            pl.col("BIRTH_DATE").n_unique().alias("n_birth_dates"),
            pl.col("BIRTH_DATE").unique().alias("birth_dates"),
        )
        .filter(pl.col("n_birth_dates") > 1)
    )
```

### Example 3: Events Within Encounter Window (±1 day)

```python
def flag_events_outside_encounters(
    event_df: pl.DataFrame,
    encounter_df: pl.DataFrame,
    event_date_col: str,
) -> pl.DataFrame:
    """Flag event rows whose date falls outside all encounter windows (±1 day)."""
    if "ENCOUNTERID" not in event_df.columns:
        return event_df
    
    enc = encounter_df.select(
        pl.col("ENCOUNTERID").cast(pl.String),
        "ADMIT_DATE",
        "DISCHARGE_DATE",
    )
    
    merged = (
        event_df.lazy()
        .with_columns(pl.col("ENCOUNTERID").cast(pl.String))
        .join(enc.lazy(), on="ENCOUNTERID", how="left")
        .with_columns(
            pl.when(
                pl.col("ADMIT_DATE").is_null()
                | pl.col(event_date_col).is_null()
            )
            .then(pl.lit(0))  # can't assess — don't flag
            .when(
                (pl.col(event_date_col) >= (pl.col("ADMIT_DATE") - pl.duration(days=1)))
                & (
                    pl.col("DISCHARGE_DATE").is_null()
                    | (pl.col(event_date_col) <= (pl.col("DISCHARGE_DATE") + pl.duration(days=1)))
                )
            )
            .then(pl.lit(0))
            .otherwise(pl.lit(1))
            .cast(pl.Int8)
            .alias("_con_outside_encounter")
        )
        .drop(["ADMIT_DATE", "DISCHARGE_DATE"])
        .collect()
    )
    return merged
```

### Example 4: Enrollment Coverage Check

```python
def flag_no_enrollment(
    encounter_df: pl.DataFrame,
    enrollment_df: pl.DataFrame,
) -> pl.DataFrame:
    """Flag patients in ENCOUNTER who have no ENROLLMENT records at all."""
    enr_ids = enrollment_df.select(pl.col("ID").cast(pl.String).unique())
    
    enc = encounter_df.with_columns(pl.col("ID").cast(pl.String))
    has_enr = enc.select("ID").unique().join(enr_ids, on="ID", how="left", suffix="_enr")
    
    # Patients with encounters but no enrollment
    no_enr_ids = (
        enc.select("ID").unique()
        .join(enr_ids, on="ID", how="anti")
    )
    
    enc = enc.with_columns(
        pl.col("ID").is_in(no_enr_ids["ID"].to_list())
        .cast(pl.Int8)
        .alias("_con_no_enrollment")
    )
    return enc
```

### Example 5: Entry Point Script Pattern (follow Phase 4)

```python
"""Phase 5: Deduplication, cross-table consistency, partner harmonization.
Usage: python scripts/clean_all.py [config/paths.toml]
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.load.config import load_config
from src.load.schema import parse_datastructure
from src.clean.dedup import flag_duplicates, DEDUP_KEYS
from src.clean.harmonize import add_partner_flags

def _build_table_map(table_filenames, parquet_dir):
    table_map = {}
    for filename in table_filenames:
        stem = Path(filename).stem
        table_name = stem.split("_Mailhot_V1")[0]
        table_map[table_name] = parquet_dir / (stem + ".parquet")
    return table_map

def main(config_path=None):
    paths = load_config(config_path)
    _, table_filenames = parse_datastructure(paths.datastructure_path)
    table_map = _build_table_map(table_filenames, paths.parquet_dir)
    # ... process tables ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| HL-EDA `dedup.py`: drops duplicate rows entirely | Phase 5: flag with IS_DUPLICATE, preserve all rows | This project | Reversible; downstream can choose to exclude |
| `pl.col(cols).is_duplicated()` (per-column) | `df.select(subset).is_duplicated()` or `pl.struct(cols).is_duplicated()` | Polars 0.19+ | Correct composite-key duplicate detection |
| `is_in(series)` with same-dtype Series | `is_in(list)` or `is_in(set)` | Polars 1.0+ | Deprecated same-dtype Series path; use Python collections |

**Deprecated/outdated:**
- `drop_duplicates()` (pandas name): Does not exist in Polars — use `unique()` or `is_duplicated()`
- `is_in()` with Polars Series argument: Deprecated in recent Polars; pass Python list/set instead

## Open Questions

1. **Should IS_DUPLICATE keep='first' semantics?**
   - What we know: `df.select(subset).is_duplicated()` marks ALL duplicate rows as True (both first and subsequent occurrences). The Phase 4 approach adds flags but doesn't distinguish first occurrence from subsequent.
   - What's unclear: Should the first occurrence of a duplicate group be unflagged (keep='first') or should all occurrences be flagged?
   - Recommendation: Flag ALL occurrences (both first and subsequent) with IS_DUPLICATE=1. If downstream needs keep='first', they can use `df.unique(subset=keys, keep='first')`. Flagging all makes the flag meaning unambiguous: "this row has identical key values to at least one other row."

2. **Encounter-event window check: how to handle tables with no ENCOUNTERID?**
   - What we know: CHP LAB_RESULT_CM has no ENCOUNTERID. Some tables (ENROLLMENT, DEMOGRAPHIC) don't link to encounters.
   - What's unclear: Should we attempt date-only matching for tables missing ENCOUNTERID?
   - Recommendation: Only check encounter-event alignment for rows with non-null ENCOUNTERID. Skip the check entirely for tables/rows without ENCOUNTERID. Document skip reason in report.

3. **Memory footprint of enrollment cross join**
   - What we know: ENCOUNTER × ENROLLMENT on ID could produce huge intermediate results.
   - What's unclear: Actual row counts and whether 64GB HPC memory suffices.
   - Recommendation: Process enrollment check in per-patient-batch or per-partner-batch chunks if memory is an issue. Start with lazy evaluation and monitor. Pre-aggregate enrollment into merged intervals per patient as a fallback.

4. **Partner harmonization: should flags go on ALL tables or only relevant ones?**
   - What we know: ICD_MAPPED is relevant for DIAGNOSIS. CLAIMS_ONLY and DEATH_ONLY affect what tables to expect.
   - What's unclear: Should ICD_MAPPED be added only to DIAGNOSIS, or to all tables from AMS/UMI?
   - Recommendation: Add partner harmonization flags to ALL tables that have the SOURCE column. The flag means "this row comes from a partner with characteristic X" — it's informational for any downstream analysis, not just diagnosis-specific.

## Sources

### Primary (HIGH confidence)
- Polars official docs: `DataFrame.is_duplicated()` — https://docs.pola.rs/py-polars/html/reference/dataframe/api/polars.DataFrame.is_duplicated.html
- Polars official docs: `polars.struct` — https://docs.pola.rs/api/python/stable/reference/expressions/api/polars.struct.html
- Polars official docs: `DataFrame.join_asof` — https://docs.pola.rs/py-polars/html/reference/dataframe/api/polars.DataFrame.join_asof.html
- Polars user guide: Window functions — https://docs.pola.rs/user-guide/expressions/window/

### Secondary (MEDIUM confidence)
- Stack Overflow: Polars struct-based duplicate detection pattern — https://stackoverflow.com/questions/75730853
- Stack Overflow: Polars deduplication methods — https://stackoverflow.com/questions/71196661

### Codebase (HIGH confidence)
- `src/validate/values.py` — Phase 4 flag pattern: Int8 binary flags with `_val_` infix, `write_validated()`, `drop_existing_flags()`
- `src/validate/structural.py` — Constants: `PATID_COL="ID"`, `ENCOUNTER_LINKED_TABLES`, `PATID_LINKED_TABLES`, table lists
- `scripts/validate_values.py` — Phase 4 entry point pattern: `PROJECT_ROOT`, `sys.path`, `_build_table_map()`, `_load_birth_death_lookup()`
- `src/validate/cohort.py` — Cross-table join patterns, ID casting to String, lazy evaluation
- `src/load/config.py` — `load_config()` returning `Paths` dataclass with `parquet_dir`
- Roadmap Phase 5 section — composite keys, flag strategy, partner nuances

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Polars already proven across Phases 2-4; no new libraries needed
- Architecture: HIGH — follows established Phase 4 patterns exactly; module/script structure mirrors existing code
- Deduplication: HIGH — `pl.struct().is_duplicated()` and `df.select(subset).is_duplicated()` verified in official docs
- Cross-table consistency: HIGH — join patterns already used in Phase 4 (`_validate_against_birth()`, `_validate_against_death()`)
- Partner harmonization: HIGH — simple conditional expressions on SOURCE column; partner identities known from roadmap
- Insurance consistency: MEDIUM — enrollment join may have memory implications on HPC; pattern is straightforward but scale untested
- Pitfalls: HIGH — based on documented Phase 4 HPC execution learnings plus verified Polars API behavior

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable — no new libraries, established patterns)
