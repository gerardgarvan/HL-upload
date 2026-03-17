# HL data loading & cleaning — structural validation module (clean-layer)
"""Schema comparison, key integrity, completeness profiling functions for Phase 5.

This module provides structural validation during the clean phase (Phase 5), used by
scripts/clean_all.py, as opposed to src/validate/structural.py which is used during
Phase 3-4 validation by scripts/validate_all.py.

**Pipeline Position:** Phase 5 (Clean/Assembly) - clean-layer validation

**Input:** Cleaned Parquet files after deduplication and flagging

**Output:** Structural validation results for clean-layer quality checks

**Orchestrated by:** scripts/clean_all.py

**Key functions:** (near-copies of src/validate/structural.py)
- parse_cover_page(): DatasetCoverPage parser
- validate_table_schema(): Schema comparison vs expected columns
- check_patid_uniqueness(): DEMOGRAPHIC ID uniqueness check
- check_patid_integrity(): PATID referential integrity (anti-join)
- check_encounterid_integrity(): ENCOUNTERID referential integrity
- completeness_by_partner(): Per-partner completeness profiling
- classify_missing_values(): PCORnet missing-value code classification

**TODO(audit): Near-duplication with src/validate/structural.py**
This module is a near-copy of src/validate/structural.py with identical function
signatures and logic. Consider consolidating into shared validation library.
"""

import re
from pathlib import Path

import polars as pl

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Constants (identical to src/validate/structural.py)
PATID_COL = "ID"

# HIPAA small-cell suppression threshold
SMALL_CELL_THRESHOLD = 10

ENCOUNTER_LINKED_TABLES: list[str] = [
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

PATID_LINKED_TABLES: list[str] = [
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

TUMOR_REGISTRY_TABLES: set[str] = {
    "TUMOR_REGISTRY1",
    "TUMOR_REGISTRY2",
    "TUMOR_REGISTRY3",
}

TUMOR_REGISTRY_EXPECTED_COUNTS: dict[str, int] = {
    "TUMOR_REGISTRY1": 265,
    "TUMOR_REGISTRY2": 120,
    "TUMOR_REGISTRY3": 120,
}

TUMOR_REGISTRY_KEY_VARS: set[str] = {
    "ID",
    "DATE_OF_DIAGNOSIS",
    "HISTOLOGY",
    "PRIMARY_SITE",
    "STAGE_GROUP",
    "AGE_AT_DIAGNOSIS",
}

KNOWN_CDM_TABLES: list[str] = [
    "DEMOGRAPHIC",
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
    "PROVIDER",
    "HARVEST",
]

# ---------------------------------------------------------------------------
# 1. DatasetCoverPage parser
# ---------------------------------------------------------------------------


def parse_cover_page(path: Path) -> dict[str, list[str]]:
    """Parse DatasetCoverPage text file to extract expected columns per CDM table.

    Format-adaptive: tries tab-delimited table sections, falls back to pattern
    matching on known table names. Handles BOM via utf-8-sig encoding.

    Returns {table_name: [column_names]}.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except Exception as exc:
        print(f"  [WARN] Could not read DatasetCoverPage: {exc}")
        return {}

    lines = text.splitlines()
    tables: dict[str, list[str]] = {}

    all_table_names = set(KNOWN_CDM_TABLES) | TUMOR_REGISTRY_TABLES

    current_table: str | None = None
    current_cols: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        upper = stripped.upper()
        if upper in all_table_names:
            if current_table and current_cols:
                tables[current_table] = current_cols
            current_table = upper
            current_cols = []
            continue

        parts = re.split(r"\t+", stripped)
        for part in parts:
            clean = part.strip().upper()
            if clean in all_table_names:
                if current_table and current_cols:
                    tables[current_table] = current_cols
                current_table = clean
                current_cols = []
                break

        if current_table:
            cols_in_line = re.split(r"[\t,]+", stripped)
            for col in cols_in_line:
                col = col.strip()
                if col and col.upper() not in all_table_names:
                    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", col):
                        if col.upper() not in {c.upper() for c in current_cols}:
                            current_cols.append(col.upper())

    if current_table and current_cols:
        tables[current_table] = current_cols

    if not tables:
        print("  [WARN] DatasetCoverPage format unrecognized — no tables parsed")

    return tables


# ---------------------------------------------------------------------------
# 2. Schema validation
# ---------------------------------------------------------------------------


def validate_table_schema(
    parquet_path: Path,
    expected_cols: list[str] | None,
    table_name: str,
    is_tumor_registry: bool = False,
    expected_col_count: int | None = None,
) -> dict:
    """Compare Parquet schema against expected columns.

    For TUMOR_REGISTRY: checks column count (warns if >10 difference) and
    verifies key cancer staging variables are present.
    For CDM tables: computes extra/missing columns vs expected.
    """
    schema = pl.read_parquet_schema(parquet_path)
    actual_cols = list(schema.keys())

    result: dict = {
        "table": table_name,
        "actual_col_count": len(actual_cols),
        "expected_col_count": expected_col_count,
        "matched": 0,
        "extra": [],
        "missing": [],
        "status": "ok",
        "details": [],
    }

    if is_tumor_registry:
        if expected_col_count is not None:
            diff = len(actual_cols) - expected_col_count
            result["expected_col_count"] = expected_col_count
            if abs(diff) > 10:
                result["status"] = "warn"
                result["details"].append(f"Expected ~{expected_col_count} columns, got {len(actual_cols)} (diff={diff})")

        actual_upper = {c.upper() for c in actual_cols}
        missing_keys = TUMOR_REGISTRY_KEY_VARS - actual_upper
        present_keys = TUMOR_REGISTRY_KEY_VARS & actual_upper
        result["matched"] = len(present_keys)
        if missing_keys:
            result["status"] = "warn"
            result["details"].append(f"Missing key variables: {sorted(missing_keys)}")
        return result

    if expected_cols:
        expected_set = {c.upper() for c in expected_cols}
        actual_upper = {c.upper() for c in actual_cols}

        extra = sorted(actual_upper - expected_set)
        missing = sorted(expected_set - actual_upper)
        matched = actual_upper & expected_set

        result["expected_col_count"] = len(expected_cols)
        result["matched"] = len(matched)
        result["extra"] = extra
        result["missing"] = missing

        if extra:
            result["details"].append(f"Extra columns ({len(extra)}): {extra}")
        if missing:
            result["status"] = "warn"
            result["details"].append(f"Missing columns ({len(missing)}): {missing}")
    else:
        result["expected_col_count"] = None
        result["details"].append("No expected columns available (DatasetCoverPage not parsed)")

    return result


# ---------------------------------------------------------------------------
# 3. PATID uniqueness
# ---------------------------------------------------------------------------


def check_patid_uniqueness(demographic_path: Path) -> dict:
    """Verify ID is unique in DEMOGRAPHIC using lazy evaluation."""
    lf = pl.scan_parquet(demographic_path)
    total = lf.select(pl.len()).collect().item()
    unique = lf.select(pl.col(PATID_COL).n_unique()).collect().item()
    duplicates = total - unique

    return {
        "total_rows": total,
        "unique_ids": unique,
        "duplicate_ids": duplicates,
        "is_unique": duplicates == 0,
    }


# ---------------------------------------------------------------------------
# 4. PATID referential integrity
# ---------------------------------------------------------------------------


def check_patid_integrity(
    child_path: Path,
    demographic_path: Path,
    child_table: str,
) -> dict:
    """Anti-join to find orphan patient IDs in child table.

    Casts ID to String on both sides to prevent type mismatch errors.
    """
    demo_ids = pl.scan_parquet(demographic_path).select(pl.col(PATID_COL).cast(pl.String)).unique()
    child_ids = pl.scan_parquet(child_path).select(pl.col(PATID_COL).cast(pl.String)).unique()

    total_unique = child_ids.collect().height
    orphans = child_ids.join(demo_ids, on=PATID_COL, how="anti").collect()

    return {
        "table": child_table,
        "unique_ids": total_unique,
        "orphan_ids": orphans.height,
        "orphan_pct": round(orphans.height / max(total_unique, 1) * 100, 2),
    }


# ---------------------------------------------------------------------------
# 5. ENCOUNTERID referential integrity
# ---------------------------------------------------------------------------


def check_encounterid_integrity(
    child_path: Path,
    encounter_path: Path,
    child_table: str,
    skip_partner: str | None = None,
    partner_col: str = "SOURCE",
) -> dict:
    """Anti-join for orphan ENCOUNTERIDs in child table.

    Filters out skip_partner records (e.g. CHP for LAB_RESULT_CM) before
    checking. Skips tables without ENCOUNTERID column. Filters null
    ENCOUNTERIDs before anti-join.
    """
    child_schema = pl.read_parquet_schema(child_path)
    if "ENCOUNTERID" not in child_schema:
        return {
            "table": child_table,
            "skipped": True,
            "reason": "no ENCOUNTERID column",
            "unique_encounterids": 0,
            "orphan_encounterids": 0,
            "orphan_pct": 0.0,
            "skip_partner": skip_partner,
        }

    enc_ids = pl.scan_parquet(encounter_path).select(pl.col("ENCOUNTERID").cast(pl.String)).unique()

    child_lf = pl.scan_parquet(child_path)

    if skip_partner and partner_col in child_schema:
        child_lf = child_lf.filter(pl.col(partner_col) != skip_partner)

    child_enc = child_lf.select(pl.col("ENCOUNTERID").cast(pl.String)).filter(pl.col("ENCOUNTERID").is_not_null()).unique()

    total = child_enc.collect().height
    orphans = child_enc.join(enc_ids, on="ENCOUNTERID", how="anti").collect()

    return {
        "table": child_table,
        "unique_encounterids": total,
        "orphan_encounterids": orphans.height,
        "orphan_pct": round(orphans.height / max(total, 1) * 100, 2),
        "skip_partner": skip_partner,
        "skipped": False,
    }


# ---------------------------------------------------------------------------
# 6. Completeness by partner
# ---------------------------------------------------------------------------


def completeness_by_partner(
    parquet_path: Path,
    table_name: str,
    partner_col: str = "SOURCE",
) -> pl.DataFrame:
    """Compute per-column completeness (1 - null_count/len) grouped by partner.

    Falls back to SITE column if SOURCE not found. If neither exists, computes
    overall completeness without partner stratification. Returns long-form
    DataFrame: [partner_col, row_count, column, completeness, table].
    """
    lf = pl.scan_parquet(parquet_path)
    schema_names = lf.collect_schema().names()

    actual_partner_col = None
    if partner_col in schema_names:
        actual_partner_col = partner_col
    elif "SITE" in schema_names:
        actual_partner_col = "SITE"

    analysis_cols = [c for c in schema_names if c != actual_partner_col]

    if not analysis_cols:
        return pl.DataFrame()

    completeness_exprs = [(1 - pl.col(c).null_count() / pl.len()).alias(c) for c in analysis_cols]

    if actual_partner_col:
        result = lf.group_by(actual_partner_col).agg([pl.len().alias("row_count")] + completeness_exprs).collect()

        long = result.unpivot(
            index=[actual_partner_col, "row_count"],
            variable_name="column",
            value_name="completeness",
        ).with_columns(pl.lit(table_name).alias("table"))

        if actual_partner_col != partner_col:
            long = long.rename({actual_partner_col: partner_col})

        return long
    else:
        result = lf.select([pl.lit("ALL").alias("_partner"), pl.len().alias("row_count")] + completeness_exprs).collect()

        long = result.unpivot(
            index=["_partner", "row_count"],
            variable_name="column",
            value_name="completeness",
        ).with_columns(pl.lit(table_name).alias("table"))

        return long.rename({"_partner": partner_col})


# ---------------------------------------------------------------------------
# 7. Missing value classification
# ---------------------------------------------------------------------------


def classify_missing_values(
    parquet_path: Path,
    table_name: str,
    partner_col: str = "SOURCE",
) -> pl.DataFrame:
    """Count PCORnet missing value codes per string column.

    Counts NI (no information), UN (unknown), OT (other), empty string, and
    null for each string column. Returns DataFrame with columns:
    [table, column, ni_count, un_count, ot_count, empty_count, null_count, total_rows].
    """
    lf = pl.scan_parquet(parquet_path)
    schema = lf.collect_schema()

    string_cols = [name for name, dtype in schema.items() if dtype == pl.String or dtype == pl.Utf8]

    if not string_cols:
        return pl.DataFrame(
            schema={
                "table": pl.String,
                "column": pl.String,
                "ni_count": pl.UInt32,
                "un_count": pl.UInt32,
                "ot_count": pl.UInt32,
                "empty_count": pl.UInt32,
                "null_count": pl.UInt32,
                "total_rows": pl.UInt32,
            }
        )

    rows: list[dict] = []
    total_rows = lf.select(pl.len()).collect().item()

    for col in string_cols:
        counts = lf.select(
            pl.col(col).eq("NI").sum().alias("ni_count"),
            pl.col(col).eq("UN").sum().alias("un_count"),
            pl.col(col).eq("OT").sum().alias("ot_count"),
            pl.col(col).eq("").sum().alias("empty_count"),
            pl.col(col).is_null().sum().alias("null_count"),
        ).collect()
        rows.append(
            {
                "table": table_name,
                "column": col,
                "ni_count": counts["ni_count"][0],
                "un_count": counts["un_count"][0],
                "ot_count": counts["ot_count"][0],
                "empty_count": counts["empty_count"][0],
                "null_count": counts["null_count"][0],
                "total_rows": total_rows,
            }
        )

    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# 8. Completeness heatmap symbol
# ---------------------------------------------------------------------------


def completeness_heatmap_symbol(pct: float) -> str:
    """Map completeness percentage (0.0-1.0) to Unicode block character.

    ≥0.95→█, ≥0.75→▓, ≥0.50→▒, ≥0.25→░, >0→·, 0→○
    """
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


# ---------------------------------------------------------------------------
# 9. Small cell flagging
# ---------------------------------------------------------------------------
# DEPRECATED: Use src.report.suppression instead. Will be removed in Phase 3.


def flag_small_cell(value: int) -> str:
    """Flag counts that would need suppression if published.

    Shows actual count with warning marker for 1 ≤ value ≤ SMALL_CELL_THRESHOLD.
    """
    if 1 <= value <= SMALL_CELL_THRESHOLD:
        return f"{value} ⚠"
    return str(value)
