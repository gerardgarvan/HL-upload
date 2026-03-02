# HL data loading & cleaning — quality report and derived variables
"""DQ aggregation, patient-level derived variables, and cleaning decisions content.

Reuses _compute_hl_timeline pattern from validate_values, flag_small_cell from
structural, and cohort/values constants. Produces structured data for Plan 02.
"""

from datetime import date
from pathlib import Path

import polars as pl

from src.validate.structural import (
    PATID_COL,
    SMALL_CELL_THRESHOLD,
    TUMOR_REGISTRY_TABLES,
    flag_small_cell,
)
from src.validate.cohort import (
    detect_dx_format,
    ALL_HL_CODES,
    ALL_HL_NORMALIZED,
)
from src.validate.values import MASKED_BIRTH_DATE

# ---------------------------------------------------------------------------
# Constants — HL subtype mapping (C81.x 4th character)
# ---------------------------------------------------------------------------

HL_SUBTYPE_MAP: dict[str, str] = {
    "0": "nodular lymphocyte predominant",
    "1": "nodular sclerosis",
    "2": "mixed cellularity",
    "3": "lymphocyte depleted",
    "4": "lymphocyte rich",
    "7": "other Hodgkin lymphoma",
    "9": "Hodgkin lymphoma, unspecified",
}

SOUTHEAST_STATES: set[str] = {
    "AL", "AR", "FL", "GA", "KY", "LA", "MS", "NC", "SC", "TN", "VA", "WV",
}

SCT_CPTS: set[str] = {
    "38240", "38241", "38242", "38230", "38232",
    "77401", "77402", "77407", "77412", "77427",
}


def _first_hl_dx_and_code(table_map: dict[str, Path]) -> tuple[pl.DataFrame, pl.DataFrame] | None:
    """Get first HL DX date and HL code per patient. Returns (first_dx, diag_with_code) or None."""
    diag_path = table_map.get("DIAGNOSIS")
    if not diag_path or not diag_path.exists():
        return None

    dx_format = detect_dx_format(diag_path)
    code_set = ALL_HL_CODES if dx_format == "dotted" else ALL_HL_NORMALIZED
    dx_match_col = (
        pl.col("DX") if dx_format == "dotted"
        else pl.col("DX").str.to_uppercase().str.replace_all(r"\.", "")
    )

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

    first_dx = (
        diag.group_by(PATID_COL)
        .agg(
            pl.col("DX_DATE").min().alias("FIRST_HL_DX_DATE"),
            pl.col("_DX_MATCH").first().alias("_HL_CODE"),
        )
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
                    pl.col(tc).str.to_date("%Y.%m.%d", strict=False)
                    .fill_null(pl.col(tc).str.to_date("%m/%d/%Y", strict=False))
                    .fill_null(pl.col(tc).str.to_date("%d%b%Y", strict=False))
                    .fill_null(pl.col(tc).str.to_date("%Y%m%d", strict=False))
                )
            tc_df = (
                tr.filter(pl.col(tc).is_not_null())
                .group_by(PATID_COL)
                .agg(pl.col(tc).min().alias("FIRST_TX_DATE"))
            )
            if not tc_df.is_empty():
                tx_frames.append(tc_df)

    if not tx_frames:
        return pl.DataFrame(schema={PATID_COL: pl.String, "FIRST_HL_TX_DATE": pl.Date})

    all_tx = pl.concat(tx_frames)
    return (
        all_tx.group_by(PATID_COL)
        .agg(pl.col("FIRST_TX_DATE").min().alias("FIRST_HL_TX_DATE"))
    )


def _payer_at_dx(
    encounter_path: Path | None,
    patients: pl.DataFrame,
) -> pl.DataFrame:
    """PAYER_TYPE_PRIMARY from encounter closest to FIRST_HL_DX_DATE within ±90 days."""
    if not encounter_path or not encounter_path.exists():
        return patients.select(PATID_COL).with_columns(
            pl.lit(None).cast(pl.String).alias("PAYER_AT_DX")
        )

    enc_schema = pl.read_parquet_schema(encounter_path)
    if "ADMIT_DATE" not in enc_schema or "PAYER_TYPE_PRIMARY" not in enc_schema:
        return patients.select(PATID_COL).with_columns(
            pl.lit(None).cast(pl.String).alias("PAYER_AT_DX")
        )

    enc = (
        pl.scan_parquet(encounter_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(patients[PATID_COL].implode()))
        .select(PATID_COL, "ADMIT_DATE", "PAYER_TYPE_PRIMARY")
        .collect()
    )
    if enc.is_empty():
        return patients.select(PATID_COL).with_columns(
            pl.lit(None).cast(pl.String).alias("PAYER_AT_DX")
        )

    joined = (
        patients.select(PATID_COL, "FIRST_HL_DX_DATE")
        .join(enc, on=PATID_COL, how="inner")
    )
    joined = joined.with_columns(
        (pl.col("ADMIT_DATE") - pl.col("FIRST_HL_DX_DATE")).dt.total_days().alias("_days_diff")
    )
    within = joined.filter(
        (pl.col("_days_diff") >= -90) & (pl.col("_days_diff") <= 90)
    )
    if within.is_empty():
        return patients.select(PATID_COL).with_columns(
            pl.lit(None).cast(pl.String).alias("PAYER_AT_DX")
        )

    closest = (
        within.with_columns(pl.col("_days_diff").abs().alias("_abs_diff"))
        .sort("_abs_diff")
        .group_by(PATID_COL)
        .first()
    )
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
        return patients.select(PATID_COL).with_columns(
            pl.lit(None).cast(pl.Int8).alias("INSURANCE_CONTINUITY")
        )

    enr_schema = pl.read_parquet_schema(enrollment_path)
    if "ENR_START_DATE" not in enr_schema or "ENR_END_DATE" not in enr_schema:
        return patients.select(PATID_COL).with_columns(
            pl.lit(None).cast(pl.Int8).alias("INSURANCE_CONTINUITY")
        )

    enr = (
        pl.scan_parquet(enrollment_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(patients[PATID_COL].implode()))
        .select(PATID_COL, "ENR_START_DATE", "ENR_END_DATE")
        .filter(pl.col("ENR_START_DATE").is_not_null() & pl.col("ENR_END_DATE").is_not_null())
        .collect()
    )
    if enr.is_empty():
        return patients.select(PATID_COL).with_columns(
            pl.lit(1).cast(pl.Int8).alias("INSURANCE_CONTINUITY")
        )

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
            .then(
                pl.when(pl.col("_last_enc") < pl.col("_window_end"))
                .then(pl.col("_last_enc"))
                .otherwise(pl.col("_window_end"))
            )
            .otherwise(pl.col("_window_end"))
            .alias("_window_end")
        )

    enr_pt = enr.join(
        pt.select(PATID_COL, "FIRST_HL_DX_DATE", "_window_end"),
        on=PATID_COL,
        how="inner",
    )
    overlapping = enr_pt.filter(
        (pl.col("ENR_END_DATE") >= pl.col("FIRST_HL_DX_DATE"))
        & (pl.col("ENR_START_DATE") <= pl.col("_window_end"))
    )
    if overlapping.is_empty():
        return patients.select(PATID_COL).with_columns(
            pl.lit(1).cast(pl.Int8).alias("INSURANCE_CONTINUITY")
        )

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
            (row["ENR_START_DATE"], row["ENR_END_DATE"])
            for row in sub.select("ENR_START_DATE", "ENR_END_DATE").iter_rows(named=True)
        ]
        periods = [(s, e) for s, e in periods if s is not None and e is not None]
        gap_flags.append((pid, 1 if has_gap_gt_30(periods) else 0))

    gap_df = pl.DataFrame({
        PATID_COL: [x[0] for x in gap_flags],
        "INSURANCE_CONTINUITY": pl.Series([x[1] for x in gap_flags], dtype=pl.Int8),
    })
    return patients.select(PATID_COL).join(gap_df, on=PATID_COL, how="left").with_columns(
        pl.col("INSURANCE_CONTINUITY").fill_null(1)
    )


def _region(
    address_path: Path | None,
    patients: pl.DataFrame,
) -> pl.DataFrame:
    """REGION: Southeast vs Other vs Unknown from LDS_ADDRESS_HISTORY.ADDRESS_STATE."""
    if not address_path or not address_path.exists():
        return patients.select(PATID_COL).with_columns(
            pl.lit("Unknown").alias("REGION")
        )

    adr_schema = pl.read_parquet_schema(address_path)
    if "ADDRESS_STATE" not in adr_schema:
        return patients.select(PATID_COL).with_columns(
            pl.lit("Unknown").alias("REGION")
        )

    adr = (
        pl.scan_parquet(address_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(patients[PATID_COL].implode()))
        .group_by(PATID_COL)
        .agg(pl.col("ADDRESS_STATE").first().alias("ADDRESS_STATE"))
        .collect()
    )
    if adr.is_empty():
        return patients.select(PATID_COL).with_columns(
            pl.lit("Unknown").alias("REGION")
        )

    adr = adr.with_columns(
        pl.when(
            pl.col("ADDRESS_STATE").is_null()
            | pl.col("ADDRESS_STATE").is_in(["NI", "UN", ""])
        )
        .then(pl.lit("Unknown"))
        .when(
            pl.col("ADDRESS_STATE").str.to_uppercase().is_in(
                list(SOUTHEAST_STATES)
            )
        )
        .then(pl.lit("Southeast"))
        .otherwise(pl.lit("Other"))
        .alias("REGION")
    )
    return patients.select(PATID_COL).join(
        adr.select(PATID_COL, "REGION"),
        on=PATID_COL,
        how="left",
    ).with_columns(pl.col("REGION").fill_null("Unknown"))


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
    """Build one row per HL patient with derived variables.

    Derived: AGE_AT_HL_DX, AGE_BAND, HL_SUBTYPE, FIRST_HL_DX_DATE, FIRST_HL_TX_DATE,
    DX_TO_TX_DAYS, PAYER_AT_DX, INSURANCE_CONTINUITY, REGION.
    Patients without FIRST_HL_DX_DATE are excluded.
    """
    out = _first_hl_dx_and_code(table_map)
    if out is None:
        return pl.DataFrame(schema={
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
        })

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
                pl.when(
                    pl.col("BIRTH_DATE").is_not_null()
                    & (pl.col("BIRTH_DATE") != pl.lit(MASKED_BIRTH_DATE))
                )
                .then(
                    (pl.col("FIRST_HL_DX_DATE") - pl.col("BIRTH_DATE")).dt.total_days()
                    / 365.25
                )
                .otherwise(None)
                .alias("AGE_AT_HL_DX")
            )
            base = base.with_columns(
                pl.when(
                    (pl.col("BIRTH_DATE") == pl.lit(MASKED_BIRTH_DATE))
                    | pl.col("BIRTH_DATE").is_null()
                )
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

    base = base.with_columns(
        pl.col("_HL_CODE").map_elements(_hl_subtype_from_code, return_dtype=pl.String).alias("HL_SUBTYPE")
    ).drop("_HL_CODE")

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
