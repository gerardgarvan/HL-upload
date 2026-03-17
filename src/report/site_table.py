"""Phase 7+: Reporting — site-level HL summary tables with cross-tabs and small-cell suppression.

Builds per-site demographic and treatment summary tables stratified by SOURCE (data partner site).
Each patient assigned to predominant site (most records). Supports HIPAA-compliant reporting
with small-cell suppression (counts 1-10 flagged).

**Pipeline position:** Phase 7+ (Reporting)
**Input:** Cleaned tables (DIAGNOSIS, DEMOGRAPHIC, ENCOUNTER, TUMOR_REGISTRY, PROCEDURES)
**Output:** Site-stratified summary DataFrames (Age × Site, Race × Site, Outcomes × Site, etc.)
**Orchestrated by:** scripts/build_site_table.py

**Key functions:**
- _predominant_site_per_patient: Assigns each patient to site with most records (TMA+TMC→TM)
- _build_age_by_site: Age at diagnosis × site cross-tab
- _build_race_ethnicity_by_site: Race/ethnicity × site cross-tabs
- _build_stage_by_site: Clinical stage × site cross-tab
- _build_insurance_by_site: First known payer × site cross-tab
- _build_outcomes_by_site: Treatment outcomes (CHEMO/RADIATION/SCT) × site cross-tabs

**Site assignment:** Patients assigned to predominant SOURCE (site contributing most records).
TMA and TMC collapsed to TM per stakeholder request.

**Small-cell handling:** All cross-tabs use flag_small_cell() to mark counts 1-10 with "[!]"
suffix for HIPAA compliance. Counts published without suppression in internal reports but
must be suppressed (→ "-") in external/published reports.
"""

from pathlib import Path

import polars as pl

from src.validate.cohort import ALL_HL_CODES, ALL_HL_NORMALIZED, detect_dx_format
from src.validate.structural import (
    PATID_COL,
    SMALL_CELL_THRESHOLD,
    TUMOR_REGISTRY_TABLES,
    flag_small_cell,
)
from src.validate.values import HL_HISTOLOGY_CODES, MASKED_BIRTH_DATE

# TMA and TMC → TM
SOURCE_COLLAPSE = {"TMA": "TM", "TMC": "TM"}

# Stage value → Stage_number (collapsed 1–4, Unknown)
STAGE_NUMBER_MAP: dict[str, str] = {
    "1": "1",
    "1A": "1",
    "1B": "1",
    "2": "2",
    "2A": "2",
    "2B": "2",
    "2 bulky": "2",
    "3": "3",
    "3A": "3",
    "3B": "3",
    "4": "4",
    "4A": "4",
    "4B": "4",
    "0": "Unknown",
    "0A": "Unknown",
    "1E": "Unknown",
    "2E": "Unknown",
    "3C": "Unknown",
    "4C": "Unknown",
    "88": "Unknown",
    "99": "Unknown",
    "5": "Unknown",
    "7": "Unknown",
    "8": "Unknown",
    "9": "Unknown",  # NAACCR in situ/NA/unknown
}


def _collapse_source(s: str | None) -> str | None:
    """Map TMA/TMC to TM."""
    if s is None or s == "":
        return s
    return SOURCE_COLLAPSE.get(str(s).strip().upper(), str(s).strip())


def _count_records_by_id_source(
    table_map: dict[str, Path],
    tables_with_source: list[str],
) -> pl.DataFrame:
    """Count records per (ID, SOURCE) across tables. Collapse TMA/TMC→TM."""
    frames: list[pl.DataFrame] = []
    for tbl in tables_with_source:
        path = table_map.get(tbl)
        if not path or not path.exists():
            continue
        schema = pl.read_parquet_schema(path)
        if "SOURCE" not in schema and "SITE" not in schema:
            continue
        src_col = "SOURCE" if "SOURCE" in schema else "SITE"
        df = (
            pl.scan_parquet(path)
            .with_columns(pl.col(PATID_COL).cast(pl.String))
            .select(PATID_COL, pl.col(src_col).alias("_src"))
            .filter(pl.col("_src").is_not_null() & (pl.col("_src") != ""))
            .group_by(PATID_COL, "_src")
            .agg(pl.len().alias("_n"))
            .collect()
        )
        if df.is_empty():
            continue
        df = df.with_columns(pl.col("_src").map_elements(_collapse_source, return_dtype=pl.String))
        frames.append(df)
    if not frames:
        return pl.DataFrame(schema={PATID_COL: pl.String, "_src": pl.String, "_n": pl.UInt32})
    combined = pl.concat(frames).group_by(PATID_COL, "_src").agg(pl.col("_n").sum())
    return combined


def _predominant_site_per_patient(
    table_map: dict[str, Path],
) -> pl.DataFrame:
    """Assign each patient to their predominant SOURCE. TMA+TMC→TM."""
    tables_with_source = [
        "DEMOGRAPHIC",
        "ENCOUNTER",
        "DIAGNOSIS",
        "PROCEDURES",
        "CONDITION",
        "VITAL",
        "LAB_RESULT_CM",
        "PRESCRIBING",
        "ENROLLMENT",
    ] + list(TUMOR_REGISTRY_TABLES)
    counts = _count_records_by_id_source(table_map, tables_with_source)
    if counts.is_empty():
        return pl.DataFrame(schema={PATID_COL: pl.String, "SITE": pl.String})
    ranked = counts.sort("_n", descending=True).group_by(PATID_COL).first().select(PATID_COL, pl.col("_src").alias("SITE"))
    return ranked


def _first_hl_dx(table_map: dict[str, Path]) -> pl.DataFrame | None:
    """First HL DX date per patient."""
    diag_path = table_map.get("DIAGNOSIS")
    if not diag_path or not diag_path.exists():
        return None
    dx_format = detect_dx_format(diag_path)
    code_set = ALL_HL_CODES if dx_format == "dotted" else ALL_HL_NORMALIZED
    dx_match = pl.col("DX") if dx_format == "dotted" else pl.col("DX").str.to_uppercase().str.replace_all(r"\.", "")
    first = (
        pl.scan_parquet(diag_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .with_columns(dx_match.alias("_m"))
        .filter(pl.col("_m").is_in(code_set))
        .filter(pl.col("DX_DATE").is_not_null())
        .group_by(PATID_COL)
        .agg(pl.col("DX_DATE").min().alias("FIRST_HL_DX_DATE"))
        .collect()
    )
    return first if not first.is_empty() else None


def _first_hl_from_condition(table_map: dict[str, Path]) -> pl.DataFrame | None:
    """First HL date per patient from CONDITION (ONSET_DATE or REPORT_DATE)."""
    cond_path = table_map.get("CONDITION")
    if not cond_path or not cond_path.exists():
        return None
    schema = pl.read_parquet_schema(cond_path)
    if "CONDITION" not in schema:
        return None
    # Need at least one date column
    date_cols = [c for c in ("ONSET_DATE", "REPORT_DATE") if c in schema]
    if not date_cols:
        return None
    cond_format = detect_dx_format(cond_path, code_col="CONDITION")
    code_set = ALL_HL_CODES if cond_format == "dotted" else ALL_HL_NORMALIZED
    cond_match = pl.col("CONDITION") if cond_format == "dotted" else pl.col("CONDITION").str.to_uppercase().str.replace_all(r"\.", "")
    # Use ONSET_DATE, fallback to REPORT_DATE when null
    if "ONSET_DATE" in schema and "REPORT_DATE" in schema:
        cond_date = pl.coalesce(pl.col("ONSET_DATE"), pl.col("REPORT_DATE"))
    else:
        cond_date = pl.col(date_cols[0])
    first = (
        pl.scan_parquet(cond_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .with_columns(cond_match.alias("_m"))
        .filter(pl.col("_m").is_in(code_set))
        .with_columns(cond_date.alias("_cond_date"))
        .filter(pl.col("_cond_date").is_not_null())
        .group_by(PATID_COL)
        .agg(pl.col("_cond_date").min().alias("FIRST_HL_COND_DATE"))
        .collect()
    )
    return first if not first.is_empty() else None


def _first_hl_dx_combined(table_map: dict[str, Path]) -> pl.DataFrame | None:
    """Earliest HL diagnosis date per patient from DIAGNOSIS and CONDITION."""
    first_dx = _first_hl_dx(table_map)
    first_cond = _first_hl_from_condition(table_map)
    if first_dx is None and first_cond is None:
        return None
    if first_dx is None:
        return first_cond.select(
            pl.col(PATID_COL),
            pl.col("FIRST_HL_COND_DATE").alias("FIRST_HL_DX_DATE"),
        )
    if first_cond is None:
        return first_dx
    combined = first_dx.join(first_cond, on=PATID_COL, how="full")
    combined = combined.with_columns(pl.min_horizontal("FIRST_HL_DX_DATE", "FIRST_HL_COND_DATE").alias("FIRST_HL_DX_DATE"))
    return combined.select(PATID_COL, "FIRST_HL_DX_DATE")


def _age_at_dx(
    table_map: dict[str, Path],
    hl_ids: pl.Expr,
) -> pl.DataFrame:
    """Age at first HL diagnosis. Prefer TUMOR_REGISTRY AGE_AT_DIAGNOSIS; else BIRTH_DATE + first HL date from DIAGNOSIS or CONDITION."""
    first_dx = _first_hl_dx_combined(table_map)
    if first_dx is None:
        return pl.DataFrame(schema={PATID_COL: pl.String, "AGE_BAND": pl.String})

    # Try TUMOR_REGISTRY first
    tr_ages: list[pl.DataFrame] = []
    for tr_name in sorted(TUMOR_REGISTRY_TABLES):
        tr_path = table_map.get(tr_name)
        if not tr_path or not tr_path.exists():
            continue
        schema = pl.read_parquet_schema(tr_path)
        if "AGE_AT_DIAGNOSIS" not in schema:
            continue
        tr = (
            pl.scan_parquet(tr_path)
            .with_columns(pl.col(PATID_COL).cast(pl.String))
            .filter(hl_ids)
            .select(PATID_COL, "AGE_AT_DIAGNOSIS")
            .filter(pl.col("AGE_AT_DIAGNOSIS").is_not_null())
            .group_by(PATID_COL)
            .first()
            .collect()
        )
        if not tr.is_empty():
            tr_ages.append(tr)
    if tr_ages:
        tr_df = pl.concat(tr_ages).unique(subset=[PATID_COL], keep="first")
        age_col = tr_df["AGE_AT_DIAGNOSIS"]
        if age_col.dtype in (pl.String, pl.Utf8):
            tr_df = tr_df.with_columns(pl.col("AGE_AT_DIAGNOSIS").cast(pl.Float64, strict=False))
        tr_df = tr_df.with_columns(
            pl.when((pl.col("AGE_AT_DIAGNOSIS") >= 0) & (pl.col("AGE_AT_DIAGNOSIS") <= 120))
            .then(
                pl.when(pl.col("AGE_AT_DIAGNOSIS") < 21)
                .then(pl.lit("<21"))
                .when(pl.col("AGE_AT_DIAGNOSIS") < 40)
                .then(pl.lit("21-39"))
                .when(pl.col("AGE_AT_DIAGNOSIS") < 65)
                .then(pl.lit("40-64"))
                .otherwise(pl.lit("65+"))
            )
            .when(pl.col("AGE_AT_DIAGNOSIS") == 200)  # masked
            .then(pl.lit("65+"))
            .otherwise(pl.lit("Unknown"))
            .alias("AGE_BAND")
        )
        return first_dx.select(PATID_COL).join(
            tr_df.select(PATID_COL, "AGE_BAND"),
            on=PATID_COL,
            how="left",
        )

    # Fallback: DEMOGRAPHIC BIRTH_DATE + FIRST_HL_DX_DATE
    demo_path = table_map.get("DEMOGRAPHIC")
    if not demo_path or not demo_path.exists():
        return first_dx.with_columns(pl.lit("Unknown").alias("AGE_BAND"))
    demo = (
        pl.scan_parquet(demo_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(first_dx[PATID_COL].implode()))
        .select(PATID_COL, "BIRTH_DATE")
        .collect()
    )
    base = first_dx.join(demo, on=PATID_COL, how="left")
    base = base.with_columns(
        pl.when(pl.col("BIRTH_DATE").is_not_null() & (pl.col("BIRTH_DATE") != pl.lit(MASKED_BIRTH_DATE)))
        .then((pl.col("FIRST_HL_DX_DATE") - pl.col("BIRTH_DATE")).dt.total_days() / 365.25)
        .otherwise(None)
        .alias("_age_years")
    )
    base = base.with_columns(
        pl.when(pl.col("BIRTH_DATE") == pl.lit(MASKED_BIRTH_DATE))
        .then(pl.lit("65+"))
        .when(pl.col("_age_years").is_null())
        .then(pl.lit("Unknown"))
        .when(pl.col("_age_years") < 21)
        .then(pl.lit("<21"))
        .when(pl.col("_age_years") < 40)
        .then(pl.lit("21-39"))
        .when(pl.col("_age_years") < 65)
        .then(pl.lit("40-64"))
        .otherwise(pl.lit("65+"))
        .alias("AGE_BAND")
    )
    return base.select(PATID_COL, "AGE_BAND")


def _first_chemo_date(table_map: dict[str, Path], hl_ids: pl.Expr, ids: pl.Series) -> pl.DataFrame:
    """Earliest chemo date per patient: TUMOR_REGISTRY DT_CHEMO/CHEMO_START_DATE_SUMMARY, else PRESCRIBING RX_ORDER_DATE."""
    chemo_frames: list[pl.DataFrame] = []

    tr_cols = ["DT_CHEMO", "CHEMO_START_DATE_SUMMARY"]
    for tr_name in sorted(TUMOR_REGISTRY_TABLES):
        tr_path = table_map.get(tr_name)
        if not tr_path or not tr_path.exists():
            continue
        schema = pl.read_parquet_schema(tr_path)
        available = [c for c in tr_cols if c in schema.names()]
        if not available:
            continue
        tr = (
            pl.scan_parquet(tr_path)
            .with_columns(pl.col(PATID_COL).cast(pl.String))
            .filter(hl_ids)
            .select([PATID_COL] + available)
            .collect()
        )
        if tr.is_empty():
            continue
        for col in available:
            if tr[col].dtype in (pl.String, pl.Utf8):
                tr = tr.with_columns(
                    pl.col(col)
                    .str.to_date("%Y.%m.%d", strict=False)
                    .fill_null(pl.col(col).str.to_date("%m/%d/%Y", strict=False))
                    .fill_null(pl.col(col).str.to_date("%d%b%Y", strict=False))
                    .fill_null(pl.col(col).str.to_date("%Y%m%d", strict=False))
                    .alias("_d")
                )
            else:
                tr = tr.with_columns(pl.col(col).alias("_d"))
            tc = tr.filter(pl.col("_d").is_not_null()).group_by(PATID_COL).agg(pl.col("_d").min().alias("FIRST_CHEMO_DATE"))
            if not tc.is_empty():
                chemo_frames.append(tc)
            tr = tr.drop("_d")

    rx_path = table_map.get("PRESCRIBING")
    if rx_path and rx_path.exists():
        rx_schema = pl.read_parquet_schema(rx_path)
        if "RX_ORDER_DATE" in rx_schema.names():
            rx = (
                pl.scan_parquet(rx_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(pl.col(PATID_COL).is_in(ids.implode()))
                .filter(pl.col("RX_ORDER_DATE").is_not_null())
                .group_by(PATID_COL)
                .agg(pl.col("RX_ORDER_DATE").min().alias("FIRST_CHEMO_DATE"))
                .collect()
            )
            if not rx.is_empty():
                chemo_frames.append(rx)

    if not chemo_frames:
        return pl.DataFrame(schema={PATID_COL: pl.String, "FIRST_CHEMO_DATE": pl.Date})
    all_chemo = pl.concat(chemo_frames)
    return all_chemo.group_by(PATID_COL).agg(pl.col("FIRST_CHEMO_DATE").min())


def _age_at_first_chemo(
    table_map: dict[str, Path],
    hl_ids: pl.Expr,
    ids: pl.Series,
) -> pl.DataFrame:
    """Age at first chemo. BIRTH_DATE + first chemo date -> bands. Returns row per id (Unknown when no chemo)."""
    all_ids = pl.DataFrame({PATID_COL: ids.unique().to_list()})
    chemo = _first_chemo_date(table_map, hl_ids, ids)
    if chemo.is_empty() or "FIRST_CHEMO_DATE" not in chemo.columns:
        return all_ids.with_columns(pl.lit("Unknown").alias("AGE_AT_CHEMO_BAND"))
    base = all_ids.join(chemo, on=PATID_COL, how="left")
    demo_path = table_map.get("DEMOGRAPHIC")
    if not demo_path or not demo_path.exists():
        return base.select(PATID_COL).with_columns(pl.lit("Unknown").alias("AGE_AT_CHEMO_BAND"))
    demo = (
        pl.scan_parquet(demo_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(ids.implode()))
        .select(PATID_COL, "BIRTH_DATE")
        .collect()
    )
    base = base.join(demo, on=PATID_COL, how="left")
    base = base.with_columns(
        pl.when(pl.col("BIRTH_DATE").is_not_null() & (pl.col("BIRTH_DATE") != pl.lit(MASKED_BIRTH_DATE)))
        .then((pl.col("FIRST_CHEMO_DATE") - pl.col("BIRTH_DATE")).dt.total_days() / 365.25)
        .otherwise(None)
        .alias("_age_years")
    )
    base = base.with_columns(
        pl.when(pl.col("BIRTH_DATE") == pl.lit(MASKED_BIRTH_DATE))
        .then(pl.lit("65+"))
        .when(pl.col("_age_years").is_null())
        .then(pl.lit("Unknown"))
        .when(pl.col("_age_years") < 21)
        .then(pl.lit("<21"))
        .when(pl.col("_age_years") < 40)
        .then(pl.lit("21-39"))
        .when(pl.col("_age_years") < 65)
        .then(pl.lit("40-64"))
        .otherwise(pl.lit("65+"))
        .alias("AGE_AT_CHEMO_BAND")
    )
    return base.select(PATID_COL, "AGE_AT_CHEMO_BAND")


def _first_known_insurance(table_map: dict[str, Path], ids: pl.Series) -> pl.DataFrame:
    """First known PAYER_TYPE_PRIMARY from ENCOUNTER (chronologically)."""
    enc_path = table_map.get("ENCOUNTER")
    if not enc_path or not enc_path.exists():
        return pl.DataFrame({PATID_COL: ids, "INSURANCE": pl.Series([None] * len(ids), dtype=pl.String)})
    schema = pl.read_parquet_schema(enc_path)
    if "PAYER_TYPE_PRIMARY" not in schema or "ADMIT_DATE" not in schema:
        return pl.DataFrame({PATID_COL: ids, "INSURANCE": pl.Series([None] * len(ids), dtype=pl.String)})
    enc = (
        pl.scan_parquet(enc_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(ids.implode()))
        .filter(
            pl.col("PAYER_TYPE_PRIMARY").is_not_null()
            & (pl.col("PAYER_TYPE_PRIMARY") != "")
            & ~pl.col("PAYER_TYPE_PRIMARY").is_in(["NI", "UN", "OT"])
        )
        .select(PATID_COL, "ADMIT_DATE", "PAYER_TYPE_PRIMARY")
        .sort("ADMIT_DATE")
        .group_by(PATID_COL)
        .first()
        .collect()
    )
    if enc.is_empty():
        return pl.DataFrame({PATID_COL: ids, "INSURANCE": pl.Series([None] * len(ids), dtype=pl.String)})
    return enc.select(PATID_COL, pl.col("PAYER_TYPE_PRIMARY").alias("INSURANCE"))


def _enrollment_status(table_map: dict[str, Path], ids: pl.Series) -> pl.DataFrame:
    """Whether each ID appears in ENROLLMENT. Returns PATID, ENROLLMENT_STATUS ('In ENROLLMENT' | 'Not in ENROLLMENT')."""
    enr_path = table_map.get("ENROLLMENT")
    if not enr_path or not enr_path.exists():
        return pl.DataFrame({PATID_COL: ids}).with_columns(pl.lit("Unknown").alias("ENROLLMENT_STATUS"))
    in_enr = (
        pl.scan_parquet(enr_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(ids.implode()))
        .select(PATID_COL)
        .unique()
        .with_columns(pl.lit("In ENROLLMENT").alias("ENROLLMENT_STATUS"))
        .collect()
    )
    all_ids = pl.DataFrame({PATID_COL: ids})
    return all_ids.join(in_enr, on=PATID_COL, how="left").with_columns(pl.col("ENROLLMENT_STATUS").fill_null("Not in ENROLLMENT"))


def build_site_table(table_map: dict[str, Path]) -> pl.DataFrame:
    """Build patient-level table with SITE, AGE_BAND, RACE, HISPANIC, STAGE_GROUP, INSURANCE."""
    pred = _predominant_site_per_patient(table_map)
    if pred.is_empty():
        return pl.DataFrame()

    first_dx = _first_hl_dx_combined(table_map)
    if first_dx is None:
        return pred
    hl_ids = pl.col(PATID_COL).is_in(first_dx[PATID_COL].implode())

    base = pred.join(first_dx, on=PATID_COL, how="inner")

    # Age at diagnosis (TUMOR_REGISTRY or BIRTH + first HL DX)
    age_df = _age_at_dx(table_map, hl_ids)
    base = base.join(age_df.select(PATID_COL, "AGE_BAND"), on=PATID_COL, how="left")

    # Age at first chemo (BIRTH + first chemo date from TR or PRESCRIBING)
    age_chemo_df = _age_at_first_chemo(table_map, hl_ids, base[PATID_COL])
    base = base.join(age_chemo_df.select(PATID_COL, "AGE_AT_CHEMO_BAND"), on=PATID_COL, how="left")

    # Race, Ethnicity from DEMOGRAPHIC
    demo_path = table_map.get("DEMOGRAPHIC")
    if demo_path and demo_path.exists():
        demo_schema = pl.read_parquet_schema(demo_path)
        demo_cols = [PATID_COL]
        if "RACE" in demo_schema:
            demo_cols.append("RACE")
        if "HISPANIC" in demo_schema:
            demo_cols.append("HISPANIC")
        demo = (
            pl.scan_parquet(demo_path)
            .with_columns(pl.col(PATID_COL).cast(pl.String))
            .filter(pl.col(PATID_COL).is_in(base[PATID_COL].implode()))
            .select(demo_cols)
            .collect()
        )
        base = base.join(demo, on=PATID_COL, how="left")
    else:
        base = base.with_columns(
            pl.lit(None).cast(pl.String).alias("RACE"),
            pl.lit(None).cast(pl.String).alias("HISPANIC"),
        )

    # Stage from TUMOR_REGISTRY — try HL histology first, fallback to any tumor
    STAGE_COLS = [
        "STAGE_GROUP",
        "COMBINED_STAGE_GROUP",
        "CLIN_STAGE",
        "AJCC_TNM_CLIN_STAGE_GROUP",
        "AJCC_TNM_PATH_STAGE_GROUP",
        "CS_STAGE_GRP_DISPLAY",
        "PATH_AJCC_STAGE_GROUP",
        "CLINICAL_AJCC_STAGE_GROUP",
        "DERIVED_AJCC6_STAGE_GRP",
        "DERIVED_AJCC7_STAGE_GRP",
        "COMBINED_STAGE",
        "AJCC_STAGE",
    ]
    tr_stage: list[pl.DataFrame] = []

    def _pull_stage(tr_path: Path, schema: dict, stage_col: str, hl_only: bool) -> pl.DataFrame | None:
        lf = (
            pl.scan_parquet(tr_path)
            .with_columns(pl.col(PATID_COL).cast(pl.String))
            .filter(pl.col(PATID_COL).is_in(base[PATID_COL].implode()))
            .filter(
                pl.col(stage_col).is_not_null()
                & (pl.col(stage_col).cast(pl.String).str.strip_chars() != "")
                & ~pl.col(stage_col).cast(pl.String).str.to_uppercase().str.strip_chars().is_in(["NULL"])
            )
        )
        if hl_only and "HISTOLOGY" in schema:
            lf = lf.with_columns(pl.col("HISTOLOGY").cast(pl.Float64, strict=False).cast(pl.Int64, strict=False).alias("_hist")).filter(
                pl.col("_hist").is_in(list(HL_HISTOLOGY_CODES))
            )
        cols = [PATID_COL, pl.col(stage_col).alias("STAGE_GROUP")]
        if "DATE_OF_DIAGNOSIS" in schema:
            cols.append(pl.col("DATE_OF_DIAGNOSIS"))
        lf = lf.select(cols)
        if "DATE_OF_DIAGNOSIS" in schema:
            lf = lf.sort("DATE_OF_DIAGNOSIS")
        tr = lf.group_by(PATID_COL).agg(pl.col("STAGE_GROUP").first().alias("STAGE_GROUP")).collect()
        return tr if not tr.is_empty() else None

    for tr_name in sorted(TUMOR_REGISTRY_TABLES):
        tr_path = table_map.get(tr_name)
        if not tr_path or not tr_path.exists():
            continue
        schema = pl.read_parquet_schema(tr_path)
        schema_names = set(schema.names())
        stage_col = next((c for c in STAGE_COLS if c in schema_names), None)
        if not stage_col:
            stage_col = next((c for c in schema_names if "STAGE" in c.upper()), None)
        if not stage_col:
            continue
        tr = _pull_stage(tr_path, schema, stage_col, hl_only=True)
        if tr is None and "HISTOLOGY" in schema:
            tr = _pull_stage(tr_path, schema, stage_col, hl_only=False)
        if tr is not None:
            tr_stage.append(tr)
    if tr_stage:
        st = pl.concat(tr_stage).unique(subset=[PATID_COL], keep="first")
        # Cast to string; remap to Stage_number (1, 2, 3, 4, Unknown)
        st = st.with_columns(
            pl.col("STAGE_GROUP")
            .cast(pl.Int64, strict=False)
            .cast(pl.String)
            .fill_null(pl.col("STAGE_GROUP").cast(pl.String))
            .str.strip_chars()
            .alias("_sg")
        )
        keys, vals = list(STAGE_NUMBER_MAP.keys()), list(STAGE_NUMBER_MAP.values())
        st = st.with_columns(pl.col("_sg").replace(keys, vals).fill_null(pl.lit("Unknown")).alias("STAGE_NUMBER"))
        # Unmapped values default to Unknown
        st = st.with_columns(
            pl.when(pl.col("STAGE_NUMBER").is_in(["1", "2", "3", "4", "Unknown"]))
            .then(pl.col("STAGE_NUMBER"))
            .otherwise(pl.lit("Unknown"))
            .alias("STAGE_NUMBER")
        ).select(PATID_COL, "STAGE_NUMBER")
        base = base.join(st, on=PATID_COL, how="left")
    else:
        base = base.with_columns(pl.lit("Unknown").alias("STAGE_NUMBER"))
    base = base.with_columns(pl.col("STAGE_NUMBER").fill_null("Unknown"))

    # Insurance
    ins = _first_known_insurance(table_map, base[PATID_COL])
    base = base.join(ins, on=PATID_COL, how="left")

    # Enrollment status (whether ID appears in ENROLLMENT)
    enr = _enrollment_status(table_map, base[PATID_COL])
    base = base.join(enr, on=PATID_COL, how="left")

    return base


def build_site_summary_table(patient_df: pl.DataFrame) -> pl.DataFrame:
    """Pivot to variable|category|Site1|Site2|... with counts. Apply small cell suppression.
    Column headers use actual site codes (e.g. UFH, ORL, TM)."""
    if patient_df.is_empty() or "SITE" not in patient_df.columns:
        return pl.DataFrame()

    sites = patient_df["SITE"].unique().sort().to_list()
    rows: list[dict] = []

    def _add_counts(var_name: str, col: str):
        if col not in patient_df.columns:
            return
        raw = pl.col(col).cast(pl.String).fill_null("")
        cat_expr = (
            pl.when(raw.str.strip_chars() == "")
            .then(pl.lit("Unknown"))
            .when(raw.str.to_uppercase().is_in(["NI", "UN", "OT"]))
            .then(pl.lit("Unknown"))
            .otherwise(raw.str.strip_chars())
        )
        df = patient_df.with_columns(cat_expr.alias("_cat"))
        for cat in df["_cat"].unique().sort().to_list():
            row: dict = {"variable": var_name, "category": str(cat)}
            for s in sites:
                n = df.filter((pl.col("SITE") == s) & (pl.col("_cat") == cat)).height
                row[s] = flag_small_cell(n) if 1 <= n <= SMALL_CELL_THRESHOLD else str(n)
            rows.append(row)

    _add_counts("Age (at diagnosis)", "AGE_BAND")
    _add_counts("Age (at first chemo)", "AGE_AT_CHEMO_BAND")
    _add_counts("Race", "RACE")
    _add_counts("Ethnicity", "HISPANIC")
    _add_counts("Stage_number", "STAGE_NUMBER")
    _add_counts("Insurance", "INSURANCE")
    _add_counts("Enrollment", "ENROLLMENT_STATUS")

    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows)


# Label mappings (PCORnet / NAACCR valuesets)
RACE_LABELS: dict[str, str] = {
    "01": "American Indian or Alaska Native",
    "02": "Asian",
    "03": "Black or African American",
    "04": "Native Hawaiian or Pacific Islander",
    "05": "White",
    "06": "Multiple race",
    "07": "Refuse to answer",
    "Unknown": "Unknown",
}
ETHNICITY_LABELS: dict[str, str] = {
    "N": "No (Not Hispanic/Latino)",
    "Y": "Yes (Hispanic/Latino)",
    "R": "Refuse to answer",
    "Unknown": "Unknown",
}
STAGE_NUMBER_LABELS: dict[str, str] = {
    "1": "Stage 1",
    "2": "Stage 2",
    "3": "Stage 3",
    "4": "Stage 4",
    "Unknown": "Unknown",
}


def _collapse_insurance(code: str) -> str:
    """Map payer code to collapsed category."""
    c = str(code).strip()
    if not c or c.upper() in ("UNKNOWN", "NI", "UN", "OT"):
        return "Unknown"
    if c in ("99", "9999"):
        return "Unavailable"
    if c.startswith("1"):
        return "Medicare"
    if c.startswith("2"):
        return "Medicaid"
    if c.startswith("5") or c.startswith("6"):
        return "Private"
    if c.startswith("3") or c.startswith("4"):
        return "Other government"
    if c.startswith("8"):
        return "No payment / Self-pay"
    if c.startswith("7") or c.startswith("9"):
        return "Other"
    return "Other"


def build_site_summary_html(summary_df: pl.DataFrame) -> str:
    """Build HTML report with labels and collapsed insurance."""
    if summary_df.is_empty():
        return "<html><body><p>No data.</p></body></html>"

    sites = [c for c in summary_df.columns if c not in ("variable", "category")]
    var_order = ["Age (at diagnosis)", "Age (at first chemo)", "Race", "Ethnicity", "Stage_number", "Insurance", "Enrollment"]

    def _label(var: str, cat: str) -> str:
        if var in ("Age (at diagnosis)", "Age (at first chemo)"):
            return cat
        if var == "Race":
            return RACE_LABELS.get(cat, cat)
        if var == "Ethnicity":
            return ETHNICITY_LABELS.get(cat, cat)
        if var == "Stage_number":
            return STAGE_NUMBER_LABELS.get(cat, cat)
        if var == "Insurance":
            return cat  # already collapsed
        return cat

    html_parts = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'>",
        "<title>Site-Stratified Demographic Table</title>",
        "<style>",
        "body { font-family: system-ui, sans-serif; margin: 2rem; }",
        "h1 { font-size: 1.5rem; }",
        "h2 { font-size: 1.1rem; margin-top: 2rem; }",
        "table { border-collapse: collapse; margin-bottom: 1rem; }",
        "th, td { border: 1px solid #ccc; padding: 0.35rem 0.6rem; text-align: right; }",
        "th { background: #f0f0f0; text-align: left; }",
        "th:first-child, td:first-child { text-align: left; min-width: 12em; }",
        "th:last-child, td:last-child { background: #f8f8f8; font-weight: 600; }",
        ".note { font-size: 0.85rem; color: #666; margin-top: 1rem; }",
        "</style></head><body>",
        "<h1>Site-Stratified Demographic Table</h1>",
        "<p class='note'>⚠ = small cell suppression (1–10)</p>",
    ]

    for var in var_order:
        subset = summary_df.filter(pl.col("variable") == var)
        if subset.is_empty():
            continue
        if var == "Insurance":
            # Collapse insurance: aggregate by collapsed category
            INSURANCE_ORDER = [
                "Medicare",
                "Medicaid",
                "Private",
                "Other government",
                "No payment / Self-pay",
                "Other",
                "Unavailable",
                "Unknown",
            ]
            collapsed: dict[str, dict[str, int]] = {}
            for row in subset.iter_rows(named=True):
                group = _collapse_insurance(row["category"])
                if group not in collapsed:
                    collapsed[group] = {s: 0 for s in sites}
                for s in sites:
                    val = str(row.get(s, "0")).replace(" ⚠", "").strip()
                    n = int(val) if val.isdigit() else 0
                    collapsed[group][s] += n
            sub_rows = []
            for group in INSURANCE_ORDER:
                if group not in collapsed:
                    continue
                r: dict = {"variable": var, "category": group}
                for s in sites:
                    n = collapsed[group][s]
                    r[s] = f"{n} ⚠" if 1 <= n <= 10 else str(n)
                sub_rows.append(r)
        else:
            sub_rows = [dict(row) for row in subset.iter_rows(named=True)]

        def _parse_count(val: str) -> int:
            return int(str(val).replace(" ⚠", "").strip()) if str(val).replace(" ⚠", "").strip().isdigit() else 0

        html_parts.append(f"<h2>{var}</h2>")
        html_parts.append("<table><thead><tr><th>Category</th>")
        for s in sites:
            html_parts.append(f"<th>{s}</th>")
        html_parts.append("<th>Overall</th></tr></thead><tbody>")
        for r in sub_rows:
            label = _label(var, r["category"])
            overall = sum(_parse_count(r.get(s, "0")) for s in sites)
            overall_str = flag_small_cell(overall) if 1 <= overall <= SMALL_CELL_THRESHOLD else str(overall)
            html_parts.append(f"<tr><td>{label}</td>")
            for s in sites:
                html_parts.append(f"<td>{r.get(s, '0')}</td>")
            html_parts.append(f"<td><strong>{overall_str}</strong></td></tr>")
        html_parts.append("</tbody></table>")

    html_parts.append("</body></html>")
    return "\n".join(html_parts)
