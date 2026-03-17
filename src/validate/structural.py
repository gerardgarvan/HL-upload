# HL data loading & cleaning — structural validation module
"""Schema comparison, key integrity, completeness profiling functions.

Validates Parquet files against DatasetCoverPage expected columns,
checks PATID/ENCOUNTERID referential integrity, and computes per-partner
completeness with PCORnet missing value classification.
"""

import re
from pathlib import Path

import polars as pl

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# PATID column name (PCORnet CDM uses "ID" instead of "PATID")
PATID_COL = "ID"

# HIPAA small-cell suppression threshold (counts 1-10 must be masked in publications)
# Clinical rationale: HIPAA Safe Harbor method requires suppressing geographic
# subdivisions with <10 individuals to prevent re-identification
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

    The DatasetCoverPage is a tab-delimited or freeform text file provided by
    OneFlorida+ listing the expected columns for each CDM table in the extract.
    This function attempts format-adaptive parsing to handle both structured
    (tab-delimited) and unstructured formats.

    Clinical rationale: Schema validation against the DatasetCoverPage catches
    missing required columns (e.g., PATID, date fields) that would cause silent
    errors in downstream analyses.

    Args:
        path: Path to DatasetCoverPage file (typically in data_root)

    Returns:
        dict: {table_name: [column_names]} mapping for all parsed tables
            Returns empty dict if parsing fails (prints warning)

    Side effects:
        Prints warning to stdout if file cannot be read or format is unrecognized
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
    """Compare Parquet schema against expected columns from DatasetCoverPage.

    Two validation modes:
    - CDM tables: Exact column comparison (reports extra/missing columns)
    - Tumor registry tables: Fuzzy validation (column count ±10, key variables present)

    Tumor registry tables get lenient validation because their schemas vary
    significantly between cancer registries and include many rare/optional fields.

    Clinical rationale: Missing required columns (PATID, date fields, diagnosis
    codes) cause silent failures in joins and analyses. Extra columns are typically
    harmless but may indicate schema drift.

    Args:
        parquet_path: Path to Parquet file to validate
        expected_cols: List of expected column names from DatasetCoverPage (case-insensitive)
        table_name: Table name for reporting
        is_tumor_registry: True for TUMOR_REGISTRY1/2/3 tables (enables fuzzy mode)
        expected_col_count: Expected column count for tumor registry tables

    Returns:
        dict: Validation results with keys:
            * "table": table name
            * "actual_col_count": actual column count
            * "expected_col_count": expected count (may be None)
            * "matched": count of matched columns
            * "extra": list of extra columns (CDM mode)
            * "missing": list of missing columns (CDM mode)
            * "status": "ok" | "warn"
            * "details": list of warning/error messages

    Side effects:
        None (read-only schema inspection via pl.read_parquet_schema)
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
    """Verify ID column is unique in DEMOGRAPHIC table using lazy evaluation.

    Clinical rationale: PATID must be unique in DEMOGRAPHIC (one row per patient).
    Duplicate PATIDs indicate data extraction errors or missing deduplication.

    Args:
        demographic_path: Path to DEMOGRAPHIC Parquet file

    Returns:
        dict: {"total_rows": int, "unique_ids": int, "duplicate_ids": int, "is_unique": bool}
    """
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
    """Find orphan patient IDs in child table via anti-join against DEMOGRAPHIC.

    Clinical rationale: All patient IDs in encounter/diagnosis/procedure tables
    must exist in DEMOGRAPHIC. Orphan IDs indicate extraction errors or incomplete
    patient records that will cause join failures in downstream analyses.

    Args:
        child_path: Path to child table Parquet file (DIAGNOSIS, ENCOUNTER, etc.)
        demographic_path: Path to DEMOGRAPHIC Parquet file (master patient list)
        child_table: Table name for reporting

    Returns:
        dict: {"table": str, "unique_ids": int, "orphan_ids": int, "orphan_pct": float}

    Side effects:
        Casts ID columns to String on both sides to prevent type mismatch errors
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
    """Find orphan encounter IDs in child table via anti-join against ENCOUNTER.

    Clinical rationale: Encounter-linked tables (DIAGNOSIS, PROCEDURES, VITAL, LAB)
    should reference valid ENCOUNTERIDs. Orphan encounters indicate extraction errors
    or incomplete encounter records. Some partners (e.g., CHP for labs) legitimately
    lack encounter linkage and are skipped via skip_partner parameter.

    Args:
        child_path: Path to child table Parquet file
        encounter_path: Path to ENCOUNTER Parquet file
        child_table: Table name for reporting
        skip_partner: Optional partner code to exclude from check (e.g., "CHP")
        partner_col: Column name for partner/source (default "SOURCE")

    Returns:
        dict: {"table": str, "unique_encounterids": int, "orphan_encounterids": int,
               "orphan_pct": float, "skip_partner": str|None, "skipped": bool}

    Side effects:
        Filters out skip_partner records before anti-join (if specified)
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

    Clinical rationale: Data completeness varies by partner site (different EHR
    systems, data extraction practices). Per-partner completeness profiling enables
    partner-specific quality assessment and identifies systematic missingness patterns.

    Args:
        parquet_path: Path to Parquet file to analyze
        table_name: Table name for output column
        partner_col: Partner/source column name (default "SOURCE", fallback to "SITE")

    Returns:
        pl.DataFrame: Long-form completeness data with columns
            [partner_col, row_count, column, completeness, table]

    Side effects:
        None (read-only analysis using lazy evaluation)
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

    PCORnet defines standard missing-value codes: NI (no information), UN (unknown),
    OT (other). These are distinct from SQL NULL and empty string. Classifying them
    separately enables distinguishing "not collected" from "collected but unknown".

    Clinical rationale: Distinguishing NI/UN/OT from NULL helps assess data quality—
    systematic NI values may indicate collection issues, while UN values reflect
    legitimate clinical uncertainty.

    Args:
        parquet_path: Path to Parquet file to analyze
        table_name: Table name for output column
        partner_col: Partner/source column name (unused in this function but kept for API consistency)

    Returns:
        pl.DataFrame: Per-column missing-value counts with columns
            [table, column, ni_count, un_count, ot_count, empty_count, null_count, total_rows]
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
    """Map completeness percentage (0.0-1.0) to Unicode block character for visual heatmaps.

    Thresholds: ≥0.95→█ (excellent), ≥0.75→▓ (good), ≥0.50→▒ (moderate),
    ≥0.25→░ (poor), >0→· (sparse), 0→○ (empty)

    Args:
        pct: Completeness percentage as float (0.0-1.0)

    Returns:
        str: Single Unicode block character representing completeness tier
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
    """Flag counts that would need suppression if published under HIPAA Safe Harbor.

    Shows actual count with warning marker (⚠) for 1 ≤ value ≤ 10 (SMALL_CELL_THRESHOLD).
    Used in quality reports to identify counts that must be masked before publication.

    Clinical rationale: HIPAA Safe Harbor method requires suppressing counts 1-10
    to prevent re-identification of individuals in small geographic subdivisions.

    Args:
        value: Integer count to evaluate

    Returns:
        str: Value with "⚠" marker if in small-cell range, otherwise string of value
    """
    if 1 <= value <= SMALL_CELL_THRESHOLD:
        return f"{value} ⚠"
    return str(value)
