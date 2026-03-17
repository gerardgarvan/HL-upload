"""Phase 6: Assembly — patient-level derived variables and data quality reporting.

Builds patient-level derived variables (age, HL subtype, treatment dates, payer, insurance
continuity, region) and aggregates data quality metrics across completeness, conformance,
plausibility, and persistence dimensions. Supports analysis-ready datasets and DQ reporting.

**Pipeline position:** Phase 6 (Assembly)
**Input:** Cleaned Parquet tables from Phase 5 (DIAGNOSIS, DEMOGRAPHIC, ENCOUNTER, etc.)
**Output:** Patient-level derived DataFrame, DQ metric aggregations, cleaning decisions content
**Orchestrated by:** scripts/assemble_clean.py, Plan 02 reporting

**Key functions:**
- build_patient_level_derived: Assembles one-row-per-patient with demographics, treatment,
  payer, and HL subtype
- aggregate_dq_metrics: Aggregates completeness, conformance, plausibility, persistence
- generate_cleaning_decisions_content: Documents cleaning logic for CLEANING_DECISIONS.md
- _suppress: HIPAA small-cell suppression (counts 1-10 → "-")
"""

from pathlib import Path

import polars as pl

from src.clean.dedup import DEDUP_KEYS
from src.clean.harmonize import PARTNER_FLAGS
from src.validate.cohort import (
    ALL_HL_CODES,
    ALL_HL_NORMALIZED,
    detect_dx_format,
)
from src.validate.structural import (
    PATID_COL,
    SMALL_CELL_THRESHOLD,
    TUMOR_REGISTRY_TABLES,
    completeness_by_partner,
)
from src.validate.values import (
    HL_LAB_RANGES,
    ICD10_TRANSITION,
    MASKED_BIRTH_DATE,
    VITAL_RANGES,
)

# ---------------------------------------------------------------------------
# Constants — HL subtype mapping (C81.x 4th character)
# ---------------------------------------------------------------------------

# ICD-10-CM HL subtype classification: C81.x uses 4th character to specify histologic subtype.
# Clinical rationale: HL subtype affects prognosis and treatment — nodular sclerosis (most common,
# ~70% of cases) vs other subtypes have different risk profiles and treatment response patterns.
#
# Mapping extracts 4th character from C81.x codes:
# - 0: nodular lymphocyte predominant (rare, indolent)
# - 1: nodular sclerosis (most common, young adults)
# - 2: mixed cellularity (older adults, HIV-associated)
# - 3: lymphocyte depleted (rare, aggressive)
# - 4: lymphocyte rich (rare, favorable prognosis)
# - 7: other specified HL subtypes
# - 9: unspecified (subtype not documented or unknown)
#
# ICD-9 codes (201.x) do not have subtype specificity — labeled "Hodgkin lymphoma (ICD-9)".
HL_SUBTYPE_MAP: dict[str, str] = {
    "0": "nodular lymphocyte predominant",
    "1": "nodular sclerosis",
    "2": "mixed cellularity",
    "3": "lymphocyte depleted",
    "4": "lymphocyte rich",
    "7": "other Hodgkin lymphoma",
    "9": "Hodgkin lymphoma, unspecified",
}

# Southeast U.S. states: used for REGION variable (Southeast vs Other vs Unknown).
# Clinical rationale: Geographic region may correlate with healthcare access, demographics,
# and treatment patterns. Southeast region selected based on study protocol / stakeholder interest.
SOUTHEAST_STATES: set[str] = {
    "AL",
    "AR",
    "FL",
    "GA",
    "KY",
    "LA",
    "MS",
    "NC",
    "SC",
    "TN",
    "VA",
    "WV",
}

# CPT codes for stem cell transplant (38xxx series) and radiation therapy (774xx series).
# Clinical rationale: Treatment modality identification — SCT and radiation are major HL
# treatments with different toxicity profiles and late effects. Used for first treatment
# date calculation.
#
# TODO(audit): This constant includes radiation CPTs (774xx) but is named SCT_CPTS. Consider
# renaming to TX_CPTS or splitting into SCT_CPTS and RADIATION_CPTS for clarity.
SCT_CPTS: set[str] = {
    "38240",
    "38241",
    "38242",
    "38230",
    "38232",
    "77401",
    "77402",
    "77407",
    "77412",
    "77427",
}


def _first_hl_dx_and_code(table_map: dict[str, Path]) -> tuple[pl.DataFrame, pl.DataFrame] | None:
    """Get first HL diagnosis date and HL code per patient from DIAGNOSIS table.

    Scans DIAGNOSIS for HL codes (ICD-9 201.x or ICD-10 C81.x), identifies earliest DX_DATE
    per patient, and captures the HL code for subtype classification. Auto-detects whether
    codes are dotted (C81.00) or normalized (C8100) format.

    Clinical rationale: First HL diagnosis date is the cohort anchor point for age at diagnosis,
    treatment timing, and survival analysis. HL code enables subtype stratification.

    Args:
        table_map: Dict mapping table names to Parquet file paths.

    Returns:
        Tuple of (first_dx DataFrame with PATID/FIRST_HL_DX_DATE/_HL_CODE,
                  full diag DataFrame with all HL rows).
        Returns None if DIAGNOSIS table unavailable or no HL codes found.
    """
    diag_path = table_map.get("DIAGNOSIS")
    if not diag_path or not diag_path.exists():
        return None

    dx_format = detect_dx_format(diag_path)
    code_set = ALL_HL_CODES if dx_format == "dotted" else ALL_HL_NORMALIZED
    dx_match_col = pl.col("DX") if dx_format == "dotted" else pl.col("DX").str.to_uppercase().str.replace_all(r"\.", "")

    diag = (
        pl.scan_parquet(diag_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .with_columns(dx_match_col.alias("_DX_MATCH"))
        .filter(pl.col("_DX_MATCH").is_in(code_set))
        .filter(pl.col("DX_DATE").is_not_null())
        .collect()
    )
    if diag.is_empty():
        return None

    first_dx = diag.group_by(PATID_COL).agg(
        pl.col("DX_DATE").min().alias("FIRST_HL_DX_DATE"),
        pl.col("_DX_MATCH").first().alias("_HL_CODE"),
    )
    return first_dx, diag


def _first_tx_dates(
    table_map: dict[str, Path],
    hl_ids: pl.Expr,
) -> pl.DataFrame:
    """Aggregate first treatment date per patient from PROCEDURES, PRESCRIBING, TUMOR_REGISTRY."""
    tx_frames: list[pl.DataFrame] = []

    px_path = table_map.get("PROCEDURES")
    if px_path and px_path.exists():
        px_schema = pl.read_parquet_schema(px_path)
        if "PX_DATE" in px_schema and "PX" in px_schema:
            px = (
                pl.scan_parquet(px_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(pl.col("PX").is_in(SCT_CPTS))
                .filter(pl.col("PX_DATE").is_not_null())
                .group_by(PATID_COL)
                .agg(pl.col("PX_DATE").min().alias("FIRST_TX_DATE"))
                .collect()
            )
            if not px.is_empty():
                tx_frames.append(px)

    rx_path = table_map.get("PRESCRIBING")
    if rx_path and rx_path.exists():
        rx_schema = pl.read_parquet_schema(rx_path)
        if "RX_ORDER_DATE" in rx_schema:
            rx = (
                pl.scan_parquet(rx_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(hl_ids)
                .filter(pl.col("RX_ORDER_DATE").is_not_null())
                .group_by(PATID_COL)
                .agg(pl.col("RX_ORDER_DATE").min().alias("FIRST_TX_DATE"))
                .collect()
            )
            if not rx.is_empty():
                tx_frames.append(rx)

    tr_date_cols = ["DT_SURG", "DT_RAD", "DT_CHEMO"]
    for tr_name in sorted(TUMOR_REGISTRY_TABLES):
        tr_path = table_map.get(tr_name)
        if not tr_path or not tr_path.exists():
            continue
        tr_schema = pl.read_parquet_schema(tr_path)
        available_tx = [c for c in tr_date_cols if c in tr_schema]
        if not available_tx:
            continue
        tr = (
            pl.scan_parquet(tr_path)
            .with_columns(pl.col(PATID_COL).cast(pl.String))
            .filter(hl_ids)
            .select([PATID_COL] + available_tx)
            .collect()
        )
        if tr.is_empty():
            continue
        for tc in available_tx:
            if tr[tc].dtype in (pl.String, pl.Utf8):
                tr = tr.with_columns(
                    pl.col(tc)
                    .str.to_date("%Y.%m.%d", strict=False)
                    .fill_null(pl.col(tc).str.to_date("%m/%d/%Y", strict=False))
                    .fill_null(pl.col(tc).str.to_date("%d%b%Y", strict=False))
                    .fill_null(pl.col(tc).str.to_date("%Y%m%d", strict=False))
                )
            tc_df = tr.filter(pl.col(tc).is_not_null()).group_by(PATID_COL).agg(pl.col(tc).min().alias("FIRST_TX_DATE"))
            if not tc_df.is_empty():
                tx_frames.append(tc_df)

    if not tx_frames:
        return pl.DataFrame(schema={PATID_COL: pl.String, "FIRST_HL_TX_DATE": pl.Date})

    all_tx = pl.concat(tx_frames)
    return all_tx.group_by(PATID_COL).agg(pl.col("FIRST_TX_DATE").min().alias("FIRST_HL_TX_DATE"))


def _payer_at_dx(
    encounter_path: Path | None,
    patients: pl.DataFrame,
) -> pl.DataFrame:
    """PAYER_TYPE_PRIMARY from encounter closest to FIRST_HL_DX_DATE within ±90 days."""
    if not encounter_path or not encounter_path.exists():
        return patients.select(PATID_COL).with_columns(pl.lit(None).cast(pl.String).alias("PAYER_AT_DX"))

    enc_schema = pl.read_parquet_schema(encounter_path)
    if "ADMIT_DATE" not in enc_schema or "PAYER_TYPE_PRIMARY" not in enc_schema:
        return patients.select(PATID_COL).with_columns(pl.lit(None).cast(pl.String).alias("PAYER_AT_DX"))

    enc = (
        pl.scan_parquet(encounter_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(patients[PATID_COL].implode()))
        .select(PATID_COL, "ADMIT_DATE", "PAYER_TYPE_PRIMARY")
        .collect()
    )
    if enc.is_empty():
        return patients.select(PATID_COL).with_columns(pl.lit(None).cast(pl.String).alias("PAYER_AT_DX"))

    joined = patients.select(PATID_COL, "FIRST_HL_DX_DATE").join(enc, on=PATID_COL, how="inner")
    joined = joined.with_columns((pl.col("ADMIT_DATE") - pl.col("FIRST_HL_DX_DATE")).dt.total_days().alias("_days_diff"))
    within = joined.filter((pl.col("_days_diff") >= -90) & (pl.col("_days_diff") <= 90))
    if within.is_empty():
        return patients.select(PATID_COL).with_columns(pl.lit(None).cast(pl.String).alias("PAYER_AT_DX"))

    closest = within.with_columns(pl.col("_days_diff").abs().alias("_abs_diff")).sort("_abs_diff").group_by(PATID_COL).first()
    return patients.select(PATID_COL).join(
        closest.select(PATID_COL, pl.col("PAYER_TYPE_PRIMARY").alias("PAYER_AT_DX")),
        on=PATID_COL,
        how="left",
    )


def _insurance_continuity(
    enrollment_path: Path | None,
    patients: pl.DataFrame,
    encounter_path: Path | None,
) -> pl.DataFrame:
    """Flag=1 if gap >30 days in ENROLLMENT covering treatment window."""
    if not enrollment_path or not enrollment_path.exists():
        return patients.select(PATID_COL).with_columns(pl.lit(None).cast(pl.Int8).alias("INSURANCE_CONTINUITY"))

    enr_schema = pl.read_parquet_schema(enrollment_path)
    if "ENR_START_DATE" not in enr_schema or "ENR_END_DATE" not in enr_schema:
        return patients.select(PATID_COL).with_columns(pl.lit(None).cast(pl.Int8).alias("INSURANCE_CONTINUITY"))

    enr = (
        pl.scan_parquet(enrollment_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(patients[PATID_COL].implode()))
        .select(PATID_COL, "ENR_START_DATE", "ENR_END_DATE")
        .filter(pl.col("ENR_START_DATE").is_not_null() & pl.col("ENR_END_DATE").is_not_null())
        .collect()
    )
    if enr.is_empty():
        return patients.select(PATID_COL).with_columns(pl.lit(1).cast(pl.Int8).alias("INSURANCE_CONTINUITY"))

    pt = patients.select(
        PATID_COL,
        "FIRST_HL_DX_DATE",
        pl.when(pl.col("FIRST_HL_TX_DATE").is_not_null())
        .then(pl.col("FIRST_HL_TX_DATE") + pl.duration(days=365))
        .otherwise(pl.col("FIRST_HL_DX_DATE") + pl.duration(days=365))
        .alias("_window_end"),
    )

    last_enc: pl.DataFrame | None = None
    if encounter_path and encounter_path.exists():
        enc_schema = pl.read_parquet_schema(encounter_path)
        if "ADMIT_DATE" in enc_schema:
            last_enc = (
                pl.scan_parquet(encounter_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(pl.col(PATID_COL).is_in(patients[PATID_COL].implode()))
                .filter(pl.col("ADMIT_DATE").is_not_null())
                .group_by(PATID_COL)
                .agg(pl.col("ADMIT_DATE").max().alias("_last_enc"))
                .collect()
            )

    if last_enc is not None and not last_enc.is_empty():
        pt = pt.join(last_enc, on=PATID_COL, how="left")
        pt = pt.with_columns(
            pl.when(pl.col("_last_enc").is_not_null())
            .then(pl.when(pl.col("_last_enc") < pl.col("_window_end")).then(pl.col("_last_enc")).otherwise(pl.col("_window_end")))
            .otherwise(pl.col("_window_end"))
            .alias("_window_end")
        )

    enr_pt = enr.join(
        pt.select(PATID_COL, "FIRST_HL_DX_DATE", "_window_end"),
        on=PATID_COL,
        how="inner",
    )
    overlapping = enr_pt.filter(
        (pl.col("ENR_END_DATE") >= pl.col("FIRST_HL_DX_DATE")) & (pl.col("ENR_START_DATE") <= pl.col("_window_end"))
    )
    if overlapping.is_empty():
        return patients.select(PATID_COL).with_columns(pl.lit(1).cast(pl.Int8).alias("INSURANCE_CONTINUITY"))

    def has_gap_gt_30(periods: list[tuple]) -> bool:
        if not periods:
            return True  # no enrollment = discontinuity
        if len(periods) < 2:
            return False
        sorted_periods = sorted(periods, key=lambda x: x[0])
        for i in range(len(sorted_periods) - 1):
            _, end = sorted_periods[i]
            next_start, _ = sorted_periods[i + 1]
            if end is not None and next_start is not None:
                gap = (next_start - end).days
                if gap > 30:
                    return True
        return False

    gap_flags: list[tuple[str, int]] = []
    for pid in patients[PATID_COL].unique().to_list():
        sub = overlapping.filter(pl.col(PATID_COL) == pid)
        periods = [
            (row["ENR_START_DATE"], row["ENR_END_DATE"]) for row in sub.select("ENR_START_DATE", "ENR_END_DATE").iter_rows(named=True)
        ]
        periods = [(s, e) for s, e in periods if s is not None and e is not None]
        gap_flags.append((pid, 1 if has_gap_gt_30(periods) else 0))

    gap_df = pl.DataFrame(
        {
            PATID_COL: [x[0] for x in gap_flags],
            "INSURANCE_CONTINUITY": pl.Series([x[1] for x in gap_flags], dtype=pl.Int8),
        }
    )
    return patients.select(PATID_COL).join(gap_df, on=PATID_COL, how="left").with_columns(pl.col("INSURANCE_CONTINUITY").fill_null(1))


def _region(
    address_path: Path | None,
    patients: pl.DataFrame,
) -> pl.DataFrame:
    """REGION: Southeast vs Other vs Unknown from LDS_ADDRESS_HISTORY.ADDRESS_STATE."""
    if not address_path or not address_path.exists():
        return patients.select(PATID_COL).with_columns(pl.lit("Unknown").alias("REGION"))

    adr_schema = pl.read_parquet_schema(address_path)
    if "ADDRESS_STATE" not in adr_schema:
        return patients.select(PATID_COL).with_columns(pl.lit("Unknown").alias("REGION"))

    adr = (
        pl.scan_parquet(address_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(patients[PATID_COL].implode()))
        .group_by(PATID_COL)
        .agg(pl.col("ADDRESS_STATE").first().alias("ADDRESS_STATE"))
        .collect()
    )
    if adr.is_empty():
        return patients.select(PATID_COL).with_columns(pl.lit("Unknown").alias("REGION"))

    adr = adr.with_columns(
        pl.when(pl.col("ADDRESS_STATE").is_null() | pl.col("ADDRESS_STATE").is_in(["NI", "UN", ""]))
        .then(pl.lit("Unknown"))
        .when(pl.col("ADDRESS_STATE").str.to_uppercase().is_in(list(SOUTHEAST_STATES)))
        .then(pl.lit("Southeast"))
        .otherwise(pl.lit("Other"))
        .alias("REGION")
    )
    return (
        patients.select(PATID_COL)
        .join(
            adr.select(PATID_COL, "REGION"),
            on=PATID_COL,
            how="left",
        )
        .with_columns(pl.col("REGION").fill_null("Unknown"))
    )


def _hl_subtype_from_code(code: str) -> str:
    """Map C81.x or 201.x to HL subtype label. C81.x uses 4th character."""
    if code is None:
        return "Unknown"
    code = str(code).upper().replace(".", "")
    if code.startswith("C81") and len(code) >= 4:
        sub = code[3]
        return HL_SUBTYPE_MAP.get(sub, "other Hodgkin lymphoma")
    if code.startswith("201"):
        return "Hodgkin lymphoma (ICD-9)"
    return "Unknown"


def build_patient_level_derived(table_map: dict[str, Path]) -> pl.DataFrame:
    """Build one-row-per-patient DataFrame with derived demographics and treatment variables.

    Assembles patient-level variables from multiple tables: first HL diagnosis date and subtype
    (DIAGNOSIS), first treatment date (PROCEDURES/PRESCRIBING/TUMOR_REGISTRY), age at diagnosis
    (DEMOGRAPHIC), payer at diagnosis (ENCOUNTER), insurance continuity (ENROLLMENT), and
    geographic region (LDS_ADDRESS_HISTORY).

    **Derived variables:**
    - FIRST_HL_DX_DATE: Earliest HL diagnosis date (cohort anchor)
    - FIRST_HL_TX_DATE: Earliest treatment date (surgery/radiation/chemo from TR or SCT/RX)
    - DX_TO_TX_DAYS: Days from diagnosis to first treatment (treatment delay metric)
    - AGE_AT_HL_DX: Age in years at first HL diagnosis (BIRTH_DATE → FIRST_HL_DX_DATE)
    - AGE_BAND: Age categories (<21, 21-39, 40-64, 65+); 65+ for masked BIRTH_DATE (1900-01-01)
    - HL_SUBTYPE: Histologic subtype from ICD-10 4th character or "ICD-9" label
    - PAYER_AT_DX: PAYER_TYPE_PRIMARY from encounter closest to FIRST_HL_DX_DATE within ±90 days
    - INSURANCE_CONTINUITY: Binary flag (1=gap >30 days in enrollment during treatment window)
    - REGION: Southeast vs Other vs Unknown (from ADDRESS_STATE)

    **Exclusions:** Patients without FIRST_HL_DX_DATE are excluded from output (no HL diagnosis).

    Clinical rationale: Patient-level derived variables enable stratified analysis (age groups,
    subtypes, regions) and assess treatment access (DX_TO_TX_DAYS, insurance continuity).

    Args:
        table_map: Dict mapping table names to Parquet file paths.

    Returns:
        DataFrame with one row per HL patient (only patients with FIRST_HL_DX_DATE).
        Returns empty DataFrame with schema if no HL patients found.
    """
    out = _first_hl_dx_and_code(table_map)
    if out is None:
        return pl.DataFrame(
            schema={
                PATID_COL: pl.String,
                "FIRST_HL_DX_DATE": pl.Date,
                "FIRST_HL_TX_DATE": pl.Date,
                "DX_TO_TX_DAYS": pl.Int64,
                "AGE_AT_HL_DX": pl.Float64,
                "AGE_BAND": pl.String,
                "HL_SUBTYPE": pl.String,
                "PAYER_AT_DX": pl.String,
                "INSURANCE_CONTINUITY": pl.Int8,
                "REGION": pl.String,
            }
        )

    first_dx, _ = out
    hl_ids = pl.col(PATID_COL).is_in(first_dx[PATID_COL].implode())

    earliest_tx = _first_tx_dates(table_map, hl_ids)
    base = first_dx.join(earliest_tx, on=PATID_COL, how="left")
    base = base.with_columns(
        pl.when(pl.col("FIRST_HL_TX_DATE").is_not_null())
        .then((pl.col("FIRST_HL_TX_DATE") - pl.col("FIRST_HL_DX_DATE")).dt.total_days())
        .otherwise(None)
        .alias("DX_TO_TX_DAYS")
    )

    demo_path = table_map.get("DEMOGRAPHIC")
    if demo_path and demo_path.exists():
        demo_schema = pl.read_parquet_schema(demo_path)
        if "BIRTH_DATE" in demo_schema:
            demo = (
                pl.scan_parquet(demo_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(hl_ids)
                .select(PATID_COL, "BIRTH_DATE")
                .collect()
            )
            base = base.join(demo, on=PATID_COL, how="left")
            base = base.with_columns(
                pl.when(pl.col("BIRTH_DATE").is_not_null() & (pl.col("BIRTH_DATE") != pl.lit(MASKED_BIRTH_DATE)))
                .then((pl.col("FIRST_HL_DX_DATE") - pl.col("BIRTH_DATE")).dt.total_days() / 365.25)
                .otherwise(None)
                .alias("AGE_AT_HL_DX")
            )
            base = base.with_columns(
                pl.when((pl.col("BIRTH_DATE") == pl.lit(MASKED_BIRTH_DATE)) | pl.col("BIRTH_DATE").is_null())
                .then(pl.lit("65+"))
                .when(pl.col("AGE_AT_HL_DX").is_null())
                .then(pl.lit(None))
                .when(pl.col("AGE_AT_HL_DX") < 21)
                .then(pl.lit("<21"))
                .when(pl.col("AGE_AT_HL_DX") < 40)
                .then(pl.lit("21-39"))
                .when(pl.col("AGE_AT_HL_DX") < 65)
                .then(pl.lit("40-64"))
                .otherwise(pl.lit("65+"))
                .alias("AGE_BAND")
            )
        else:
            base = base.with_columns(
                pl.lit(None).cast(pl.Float64).alias("AGE_AT_HL_DX"),
                pl.lit(None).cast(pl.String).alias("AGE_BAND"),
            )
    else:
        base = base.with_columns(
            pl.lit(None).cast(pl.Float64).alias("AGE_AT_HL_DX"),
            pl.lit(None).cast(pl.String).alias("AGE_BAND"),
        )

    base = base.with_columns(pl.col("_HL_CODE").map_elements(_hl_subtype_from_code, return_dtype=pl.String).alias("HL_SUBTYPE")).drop(
        "_HL_CODE"
    )

    enc_path = table_map.get("ENCOUNTER")
    payer = _payer_at_dx(enc_path, base)
    base = base.join(payer, on=PATID_COL, how="left")

    enr_path = table_map.get("ENROLLMENT")
    ins = _insurance_continuity(enr_path, base, enc_path)
    base = base.join(ins, on=PATID_COL, how="left")

    adr_path = table_map.get("LDS_ADDRESS_HISTORY")
    reg = _region(adr_path, base)
    base = base.join(reg, on=PATID_COL, how="left")

    out_cols = [
        PATID_COL,
        "FIRST_HL_DX_DATE",
        "FIRST_HL_TX_DATE",
        "DX_TO_TX_DAYS",
        "AGE_AT_HL_DX",
        "AGE_BAND",
        "HL_SUBTYPE",
        "PAYER_AT_DX",
        "INSURANCE_CONTINUITY",
        "REGION",
    ]
    present = [c for c in out_cols if c in base.columns]
    return base.select(present)


# ---------------------------------------------------------------------------
# DQ aggregation
# ---------------------------------------------------------------------------


def _suppress(value: int) -> str:
    """Apply HIPAA small-cell suppression: return '-' for counts 1-10, otherwise str(value).

    Suppresses small cell counts to prevent re-identification of individuals in published reports.
    SMALL_CELL_THRESHOLD=10 per HIPAA Safe Harbor Method (counts ≤10 suppressed).

    Clinical rationale: HIPAA compliance for publishable reports — small cell counts enable
    individual identification. Dash ("-") indicates suppression in CSV/markdown outputs.

    Args:
        value: Count to potentially suppress.

    Returns:
        "-" if value in [1, 10], otherwise str(value).
    """
    if 1 <= value <= SMALL_CELL_THRESHOLD:
        return "-"
    return str(value)


def aggregate_dq_metrics(
    table_map: dict[str, Path],
    reports_dir: Path,
) -> dict:
    """Aggregate data quality metrics across four Kahn Framework dimensions.

    Scans cleaned Parquet tables and aggregates DQ issues across:
    - **Completeness:** Missing/null values per table/column/partner (from completeness CSV or Parquet)
    - **Conformance:** Invalid code values (_val_*code flags: valueset violations, code concordance failures)
    - **Plausibility:** Out-of-range values (_val_range, _val_future, temporal violations)
    - **Persistence:** Encounter distribution over time (by year/month/partner for continuity assessment)

    **Data sources:** Reads _val_* flag columns added during Phase 4 (Validation) and completeness
    reports from reports_dir. Aggregates by summing flag columns (1=flagged row).

    Clinical rationale: DQ metrics document pipeline-discovered issues and support data quality
    reporting. Kahn Framework provides standardized DQ categorization for clinical data networks.

    Args:
        table_map: Dict mapping table names to Parquet file paths.
        reports_dir: Path to reports directory (may contain completeness_by_partner.csv).

    Returns:
        Dict with keys:
        - "completeness": {source: "csv"|"parquet", df: completeness data}
        - "conformance": {invalid_counts: list of {table, check, count}}
        - "plausibility": {flagged_counts: list of {table, check, count}}
        - "persistence": {by_year/by_month: encounter counts, encounter_path: path}
    """
    result: dict = {
        "completeness": {},
        "conformance": {},
        "plausibility": {},
        "persistence": {},
    }

    # Completeness: read reports/completeness_by_partner.csv or compute from Parquet
    comp_csv = reports_dir / "completeness_by_partner.csv"
    if comp_csv.exists():
        comp_df = pl.read_csv(comp_csv)
        result["completeness"] = {"source": "csv", "df": comp_df}
    else:
        comp_tables: list[dict] = []
        for table_name, path in table_map.items():
            if path and path.exists():
                df = completeness_by_partner(path, table_name)
                if not df.is_empty():
                    comp_tables.append({"table": table_name, "df": df})
        result["completeness"] = {"source": "parquet", "tables": comp_tables}

    # Conformance: aggregate _val_*code invalid counts from Parquet
    conformance_rows: list[dict] = []
    for table_name, path in table_map.items():
        if not path or not path.exists():
            continue
        schema = pl.read_parquet_schema(path)
        flag_cols = [c for c in schema if "_val_" in c and ("code" in c or "concordance" in c)]
        if not flag_cols:
            continue
        for fc in flag_cols:
            df = pl.scan_parquet(path).select(pl.col(fc).sum().alias("_s")).collect()
            cnt = int(df["_s"][0] or 0)
            conformance_rows.append({"table": table_name, "check": fc, "count": cnt})
    result["conformance"] = {"invalid_counts": conformance_rows}

    # Plausibility: aggregate _val_range, _val_future, temporal violations
    plausibility_rows: list[dict] = []
    for table_name, path in table_map.items():
        if not path or not path.exists():
            continue
        schema = pl.read_parquet_schema(path)
        flag_cols = [
            c
            for c in schema
            if "_val_" in c
            and (
                "range" in c
                or "future" in c
                or "before_birth" in c
                or "after_death" in c
                or "admit_discharge" in c
                or "enr_dates" in c
                or "before_dx" in c
            )
        ]
        for fc in flag_cols:
            df = pl.scan_parquet(path).select(pl.col(fc).sum().alias("_s")).collect()
            cnt = int(df["_s"][0] or 0)
            plausibility_rows.append({"table": table_name, "check": fc, "count": cnt})
    result["plausibility"] = {"flagged_counts": plausibility_rows}

    # Persistence: encounter counts by year/month by SOURCE
    enc_path = table_map.get("ENCOUNTER")
    persistence_data: dict = {"by_year": {}, "by_month": {}, "encounter_path": str(enc_path) if enc_path else None}
    if enc_path and enc_path.exists():
        enc_schema = pl.read_parquet_schema(enc_path)
        if "ADMIT_DATE" in enc_schema:
            enc = pl.scan_parquet(enc_path)
            if "SOURCE" in enc_schema:
                by_yr = (
                    enc.with_columns(pl.col("ADMIT_DATE").dt.year().alias("year"))
                    .filter(pl.col("ADMIT_DATE").is_not_null())
                    .group_by("SOURCE", "year")
                    .agg(pl.len().alias("n"))
                    .collect()
                )
            else:
                by_yr = (
                    enc.with_columns(pl.col("ADMIT_DATE").dt.year().alias("year"))
                    .filter(pl.col("ADMIT_DATE").is_not_null())
                    .group_by("year")
                    .agg(pl.len().alias("n"))
                    .collect()
                )
            persistence_data["by_year"] = by_yr.to_dicts()
    result["persistence"] = persistence_data

    return result


def generate_cleaning_decisions_content() -> list[str]:
    """Generate markdown lines documenting cleaning decisions.

    Returns list of strings; Plan 02 will write to CLEANING_DECISIONS.md.
    """
    lines: list[str] = []
    lines.append("# Cleaning Decisions\n")
    lines.append("## 1. Value Set Validation")
    lines.append("- Coded fields validated against valuesets.csv")
    lines.append("- NI (No Information), UN (Unknown), OT (Other): treated as valid missing codes")
    lines.append("")

    lines.append("## 2. Plausibility Ranges")
    lines.append("### Vital Signs (VITAL_RANGES)")
    for var, (lo, hi) in VITAL_RANGES.items():
        lines.append(f"- {var}: {lo}–{hi}")
    lines.append("### HL Lab Ranges (HL_LAB_RANGES)")
    for loinc, info in list(HL_LAB_RANGES.items())[:5]:
        lines.append(f"- {info['name']} ({loinc}): {info['min']}–{info['max']} {info['unit']}")
    lines.append("- ... (20 LOINC codes total)")
    lines.append("")

    lines.append("## 3. Temporal Rules")
    lines.append(f"- ICD-10 transition: {ICD10_TRANSITION}; grace period Jul 2015–Jan 2016")
    lines.append("- DX_TO_TX_DAYS: 0–365 days considered plausible; outside flagged")
    lines.append("")

    lines.append("## 4. Deduplication Keys (DEDUP_KEYS)")
    for table, keys in DEDUP_KEYS.items():
        lines.append(f"- {table}: {', '.join(keys)}")
    lines.append("")

    lines.append("## 5. Partner Flags")
    for flag, partners in PARTNER_FLAGS.items():
        lines.append(f"- **{flag}**: {', '.join(sorted(partners))}")
    lines.append("")

    lines.append("## 6. Masked Values")
    lines.append("- BIRTH_DATE = 1900-01-01 → AGE_BAND folded into 65+")
    lines.append("- AGE_AT_DIAGNOSIS = 200 (implausible placeholder) → 65+ band")
    lines.append("")

    lines.append("## 7. TUMOR_REGISTRY Date Formats")
    lines.append("- Supported: MM/DD/YYYY, YYYY.MM.DD, %d%b%Y (DATE9), %Y%m%d (YYYYMMDD)")
    lines.append("")

    lines.append("## 8. INSURANCE_CONTINUITY")
    lines.append("- Flag = 1 when gap > 30 days in enrollment covering treatment window")
    lines.append("- Treatment window: FIRST_HL_DX_DATE to min(FIRST_HL_TX_DATE + 365, last encounter)")
    lines.append("")

    lines.append("## 9. Small Cell Suppression")
    lines.append(f"- SMALL_CELL_THRESHOLD = {SMALL_CELL_THRESHOLD}")
    lines.append("- Counts 1–10 suppressed in reports (dash in CSV, warning marker in markdown)")

    return lines
