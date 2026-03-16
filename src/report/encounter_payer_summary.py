# HL data loading & cleaning — encounter patient-level summary (payer focus)
"""Build one row per patient with encounter-derived, payer-focused variables.

Scope: Only patients with ENROLLMENT records.
Output: N_ENCOUNTERS, N_ENCOUNTERS_WITH_PAYER, N_DISTINCT_PAYER_CATEGORIES,
PAYER_CATEGORY_PRIMARY, PAYER_CATEGORY_AT_FIRST_DX, PAYER_CATEGORY_AT_FIRST_CHEMO,
PAYER_CATEGORY_AT_LAST_CHEMO, PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO, PAYER_TRANSITION.

Payer categories: Medicare, Medicaid, Private, Other government,
No payment / Self-pay, Other, Unavailable, Unknown (PCORnet typology prefix mapping).
Any future CSV or report export must use _suppress for counts 1–10 (HIPAA).
"""

from pathlib import Path

import polars as pl

from src.validate.cohort import (
    ALL_HL_CODES,
    ALL_HL_NORMALIZED,
    detect_dx_format,
)
from src.validate.structural import PATID_COL, TUMOR_REGISTRY_TABLES

INVALID_PAYER: set[str] = {"NI", "UN", "OT"}
# Sentinel = values that trigger fallback to secondary when used as primary (null, "", NI, UN, OT).
# Optional: 99/9999 — set True to treat as sentinel; document in CODEBOOK/PAYER_VARIABLES_AND_CATEGORIES.
INCLUDE_99_AS_SENTINEL: bool = False

DUAL_ELIGIBLE_CODES: tuple[str, ...] = ("14", "141", "142")  # PCORnet; 41 = Corrections Federal, not dual-eligible

# Payer code → category (PCORnet typology: 1=Medicare, 2=Medicaid, 5/6=Private, etc.)
def _collapse_payer_category(code: str) -> str:
    """Map PAYER_TYPE_PRIMARY to collapsed category for analysis."""
    c = str(code).strip() if code is not None else ""
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


def _payer_category_from_effective_and_dual(effective_payer: str | None, dual_eligible: int) -> str:
    """Payer category for one encounter: 'Dual eligible' when dual_eligible else _collapse_payer_category."""
    if dual_eligible == 1:
        return "Dual eligible"
    return _collapse_payer_category(effective_payer)


def _sentinel_set() -> set[str]:
    """Values treated as sentinel (invalid) for effective payer; triggers fallback to secondary."""
    s = set(INVALID_PAYER)
    if INCLUDE_99_AS_SENTINEL:
        s = s | {"99", "9999"}
    return s


def _valid_payer_expr(col: str) -> pl.Expr:
    """True when the payer column is usable (non-null, non-empty, not in sentinel set)."""
    sentinel = list(_sentinel_set())
    return (
        pl.col(col).is_not_null()
        & (pl.col(col).cast(pl.Utf8) != "")
        & ~pl.col(col).cast(pl.Utf8).is_in(sentinel)
    )


def _get_first_hl_dx_dates(table_map: dict[str, Path], ids: pl.Series) -> pl.DataFrame | None:
    """First HL diagnosis date per patient. Returns None if no DIAGNOSIS/HL data."""
    diag_path = table_map.get("DIAGNOSIS")
    if not diag_path or not diag_path.exists():
        return None
    dx_format = detect_dx_format(diag_path)
    code_set = ALL_HL_CODES if dx_format == "dotted" else ALL_HL_NORMALIZED
    dx_match = pl.col("DX") if dx_format == "dotted" else pl.col("DX").str.to_uppercase().str.replace_all(r"\.", "")
    diag = (
        pl.scan_parquet(diag_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(ids.implode()))
        .with_columns(dx_match.alias("_DX_MATCH"))
        .filter(pl.col("_DX_MATCH").is_in(code_set))
        .filter(pl.col("DX_DATE").is_not_null())
        .group_by(PATID_COL)
        .agg(pl.col("DX_DATE").min().alias("FIRST_HL_DX_DATE"))
        .collect()
    )
    return diag if not diag.is_empty() else None


def _get_chemo_dates(table_map: dict[str, Path], ids: pl.Series) -> pl.DataFrame | None:
    """First and last chemo date per patient. Sources: TR DT_CHEMO, CHEMO_START_DATE_SUMMARY, PRESCRIBING RX_ORDER_DATE."""
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
            .filter(pl.col(PATID_COL).is_in(ids.implode()))
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
            tc = tr.filter(pl.col("_d").is_not_null()).select(PATID_COL, pl.col("_d").alias("_chemo_d"))
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
                .select(PATID_COL, pl.col("RX_ORDER_DATE").alias("_chemo_d"))
                .collect()
            )
            if not rx.is_empty():
                chemo_frames.append(rx)
    if not chemo_frames:
        return None
    all_chemo = pl.concat(chemo_frames)
    return all_chemo.group_by(PATID_COL).agg(
        pl.col("_chemo_d").min().alias("FIRST_CHEMO_DATE"),
        pl.col("_chemo_d").max().alias("LAST_CHEMO_DATE"),
    )


def _effective_payer_and_dual_exprs(
    has_secondary: bool,
) -> tuple[pl.Expr, pl.Expr, pl.Expr]:
    """Build effective_payer, _valid, and dual_eligible expressions for ENCOUNTER scan."""
    valid_primary = _valid_payer_expr("PAYER_TYPE_PRIMARY")
    if has_secondary:
        valid_secondary = _valid_payer_expr("PAYER_TYPE_SECONDARY")
        effective_payer = (
            pl.when(valid_primary)
            .then(pl.col("PAYER_TYPE_PRIMARY").cast(pl.Utf8))
            .when(valid_secondary)
            .then(pl.col("PAYER_TYPE_SECONDARY").cast(pl.Utf8))
            .otherwise(pl.lit(None).cast(pl.Utf8))
        )
        p = pl.col("PAYER_TYPE_PRIMARY").cast(pl.Utf8).fill_null("")
        s = pl.col("PAYER_TYPE_SECONDARY").cast(pl.Utf8).fill_null("")
        primary_medicare = p.str.starts_with("1")
        primary_medicaid = p.str.starts_with("2")
        secondary_medicare = s.str.starts_with("1")
        secondary_medicaid = s.str.starts_with("2")
        primary_dual = p.is_in(list(DUAL_ELIGIBLE_CODES))
        secondary_dual = s.is_in(list(DUAL_ELIGIBLE_CODES))
        dual_eligible = (
            (primary_medicare & secondary_medicaid)
            | (primary_medicaid & secondary_medicare)
            | primary_dual
            | secondary_dual
        ).cast(pl.Int8).fill_null(0)
    else:
        effective_payer = (
            pl.when(valid_primary)
            .then(pl.col("PAYER_TYPE_PRIMARY").cast(pl.Utf8))
            .otherwise(pl.lit(None).cast(pl.Utf8))
        )
        dual_eligible = pl.lit(0).cast(pl.Int8)
    sentinel = list(_sentinel_set())
    _valid = (
        effective_payer.is_not_null()
        & (effective_payer != "")
        & ~effective_payer.is_in(sentinel)
    )
    return effective_payer.alias("effective_payer"), _valid.alias("_valid"), dual_eligible.alias("dual_eligible")


def _payer_at_date(
    enc_path: Path,
    patients: pl.DataFrame,
    date_col: str,
    window_days: int = 90,
) -> pl.DataFrame:
    """Effective payer and dual_eligible from encounter closest to patients[date_col] within ±window_days."""
    enc_schema = pl.read_parquet_schema(enc_path)
    if "ADMIT_DATE" not in enc_schema.names() or "PAYER_TYPE_PRIMARY" not in enc_schema.names():
        return patients.select(PATID_COL).with_columns(
            pl.lit(None).cast(pl.String).alias("_raw_payer"),
            pl.lit(0).cast(pl.Int8).alias("_dual_eligible"),
        )
    has_secondary = "PAYER_TYPE_SECONDARY" in enc_schema.names()
    enc_cols = [PATID_COL, "ADMIT_DATE", "PAYER_TYPE_PRIMARY"]
    if has_secondary:
        enc_cols.append("PAYER_TYPE_SECONDARY")
    eff_expr, valid_expr, dual_expr = _effective_payer_and_dual_exprs(has_secondary)
    enc = (
        pl.scan_parquet(enc_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .filter(pl.col(PATID_COL).is_in(patients[PATID_COL].implode()))
        .select(enc_cols)
        .with_columns([eff_expr, dual_expr])
        .select(PATID_COL, "ADMIT_DATE", "effective_payer", "dual_eligible")
        .collect()
    )
    if enc.is_empty():
        return patients.select(PATID_COL).with_columns(
            pl.lit(None).cast(pl.String).alias("_raw_payer"),
            pl.lit(0).cast(pl.Int8).alias("_dual_eligible"),
        )
    joined = patients.select(PATID_COL, date_col).join(enc, on=PATID_COL, how="inner")
    joined = joined.with_columns(
        (pl.col("ADMIT_DATE") - pl.col(date_col)).dt.total_days().alias("_days_diff")
    )
    within = joined.filter(
        (pl.col("_days_diff") >= -window_days) & (pl.col("_days_diff") <= window_days)
    )
    if within.is_empty():
        return patients.select(PATID_COL).with_columns(
            pl.lit(None).cast(pl.String).alias("_raw_payer"),
            pl.lit(0).cast(pl.Int8).alias("_dual_eligible"),
        )
    closest = (
        within.with_columns(pl.col("_days_diff").abs().alias("_abs"))
        .sort("_abs")
        .group_by(PATID_COL)
        .first()
    )
    return patients.select(PATID_COL).join(
        closest.select(
            PATID_COL,
            pl.col("effective_payer").alias("_raw_payer"),
            pl.col("dual_eligible").alias("_dual_eligible"),
        ),
        on=PATID_COL,
        how="left",
    ).with_columns(pl.col("_dual_eligible").fill_null(0).cast(pl.Int8))


def build_encounter_payer_summary(table_map: dict[str, Path]) -> pl.DataFrame:
    """Summarize ENCOUNTER at patient level with payer-focused variables.

    Only includes patients with at least one ENROLLMENT record.
    Payer is classified into categories: Medicare, Medicaid, Private, etc.

    Returns one row per patient with:
    - N_ENCOUNTERS: total encounter count
    - N_ENCOUNTERS_WITH_PAYER: encounters with valid PAYER_TYPE_PRIMARY
    - N_DISTINCT_PAYER_CATEGORIES: distinct payer categories per patient
    - PAYER_CATEGORY_PRIMARY: most frequent payer category; null if none
    - PAYER_TRANSITION: 1 if N_DISTINCT_PAYER_CATEGORIES > 1, else 0

    Returns empty DataFrame with schema if ENCOUNTER not found.
    """
    empty_schema = {
        PATID_COL: pl.String,
        "N_ENCOUNTERS": pl.Int64,
        "N_ENCOUNTERS_WITH_PAYER": pl.Int64,
        "N_DISTINCT_PAYER_CATEGORIES": pl.Int64,
        "PAYER_CATEGORY_PRIMARY": pl.String,
        "PAYER_CATEGORY_AT_FIRST_DX": pl.String,
        "PAYER_CATEGORY_AT_FIRST_CHEMO": pl.String,
        "PAYER_CATEGORY_AT_LAST_CHEMO": pl.String,
        "PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO": pl.String,
        "PAYER_TRANSITION": pl.Int8,
        "DUAL_ELIGIBLE": pl.Int8,
    }

    enc_path = table_map.get("ENCOUNTER")
    if not enc_path or not enc_path.exists():
        return pl.DataFrame(schema=empty_schema)

    schema = pl.read_parquet_schema(enc_path)
    if "PAYER_TYPE_PRIMARY" not in schema.names() or PATID_COL not in schema.names():
        return pl.DataFrame(schema=empty_schema)
    has_secondary = "PAYER_TYPE_SECONDARY" in schema.names()

    # Enrolled IDs only
    enr_path = table_map.get("ENROLLMENT")
    if enr_path and enr_path.exists():
        enr_schema = pl.read_parquet_schema(enr_path)
        if PATID_COL in enr_schema:
            enrolled_ids = (
                pl.scan_parquet(enr_path)
                .select(pl.col(PATID_COL).cast(pl.String).unique())
                .collect()
            )
            filter_ids = enrolled_ids.to_series()
        else:
            filter_ids = None
    else:
        filter_ids = None

    enc_cols = [PATID_COL, "ADMIT_DATE", "PAYER_TYPE_PRIMARY"]
    if has_secondary:
        enc_cols.append("PAYER_TYPE_SECONDARY")
    eff_expr, valid_expr, dual_expr = _effective_payer_and_dual_exprs(has_secondary)
    enc = (
        pl.scan_parquet(enc_path)
        .with_columns(pl.col(PATID_COL).cast(pl.String))
        .select(enc_cols)
        .with_columns([eff_expr, valid_expr, dual_expr])
    )
    if filter_ids is not None:
        enc = enc.filter(pl.col(PATID_COL).is_in(filter_ids))

    # Base counts and patient-level DUAL_ELIGIBLE (max of encounter-level dual_eligible)
    base = (
        enc.group_by(PATID_COL)
        .agg(
            pl.len().alias("N_ENCOUNTERS"),
            pl.col("_valid").sum().cast(pl.Int64).alias("N_ENCOUNTERS_WITH_PAYER"),
            pl.col("dual_eligible").max().alias("DUAL_ELIGIBLE"),
        )
        .collect()
    )

    # Add PAYER_CATEGORY from effective_payer and dual_eligible (valid rows only); "Dual eligible" when dual_eligible
    valid_enc = (
        enc.filter(pl.col("_valid"))
        .select(PATID_COL, "effective_payer", "dual_eligible")
        .collect()
    )

    if valid_enc.is_empty():
        base = base.with_columns(
            pl.lit(0).cast(pl.Int64).alias("N_DISTINCT_PAYER_CATEGORIES"),
            pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_PRIMARY"),
        )
    else:
        valid_enc = valid_enc.with_columns(
            pl.Series(
                "PAYER_CATEGORY",
                [
                    _payer_category_from_effective_and_dual(
                        r["effective_payer"],
                        r.get("dual_eligible", 0) or 0,
                    )
                    for r in valid_enc.iter_rows(named=True)
                ],
                dtype=pl.String,
            )
        )

        distinct = (
            valid_enc.group_by(PATID_COL)
            .agg(
                pl.col("PAYER_CATEGORY")
                .n_unique()
                .alias("N_DISTINCT_PAYER_CATEGORIES")
            )
        )

        payer_counts = (
            valid_enc.group_by(PATID_COL, "PAYER_CATEGORY")
            .agg(pl.len().alias("_n"))
            .sort("_n", descending=True)
            .group_by(PATID_COL)
            .first()
        )
        payer_primary = payer_counts.select(
            PATID_COL,
            pl.col("PAYER_CATEGORY").alias("PAYER_CATEGORY_PRIMARY"),
        )

        base = (
            base.join(distinct, on=PATID_COL, how="left")
            .with_columns(pl.col("N_DISTINCT_PAYER_CATEGORIES").fill_null(0))
            .join(payer_primary, on=PATID_COL, how="left")
        )

    base = base.with_columns(
        (pl.col("N_DISTINCT_PAYER_CATEGORIES") > 1)
        .cast(pl.Int8)
        .alias("PAYER_TRANSITION")
    )

    # Payer at first diagnosis, first chemo, last chemo, most frequent at chemo
    ids = base[PATID_COL]
    first_dx = _get_first_hl_dx_dates(table_map, ids)
    chemo = _get_chemo_dates(table_map, ids)

    if first_dx is not None:
        payer_dx = _payer_at_date(enc_path, first_dx, "FIRST_HL_DX_DATE")
        payer_dx = payer_dx.with_columns(
            pl.Series(
                "PAYER_CATEGORY_AT_FIRST_DX",
                [
                    _payer_category_from_effective_and_dual(
                        r["_raw_payer"],
                        r.get("_dual_eligible", 0) or 0,
                    )
                    for r in payer_dx.iter_rows(named=True)
                ],
                dtype=pl.String,
            )
        )
        base = base.join(
            payer_dx.select(PATID_COL, "PAYER_CATEGORY_AT_FIRST_DX"),
            on=PATID_COL,
            how="left",
        )
    else:
        base = base.with_columns(pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_AT_FIRST_DX"))

    if chemo is not None:
        payer_first = _payer_at_date(enc_path, chemo, "FIRST_CHEMO_DATE")
        payer_first = payer_first.with_columns(
            pl.Series(
                "PAYER_CATEGORY_AT_FIRST_CHEMO",
                [
                    _payer_category_from_effective_and_dual(
                        r["_raw_payer"],
                        r.get("_dual_eligible", 0) or 0,
                    )
                    for r in payer_first.iter_rows(named=True)
                ],
                dtype=pl.String,
            )
        )
        base = base.join(
            payer_first.select(PATID_COL, "PAYER_CATEGORY_AT_FIRST_CHEMO"),
            on=PATID_COL,
            how="left",
        )

        payer_last = _payer_at_date(enc_path, chemo, "LAST_CHEMO_DATE")
        payer_last = payer_last.with_columns(
            pl.Series(
                "PAYER_CATEGORY_AT_LAST_CHEMO",
                [
                    _payer_category_from_effective_and_dual(
                        r["_raw_payer"],
                        r.get("_dual_eligible", 0) or 0,
                    )
                    for r in payer_last.iter_rows(named=True)
                ],
                dtype=pl.String,
            )
        )
        base = base.join(
            payer_last.select(PATID_COL, "PAYER_CATEGORY_AT_LAST_CHEMO"),
            on=PATID_COL,
            how="left",
        )

        # Most frequent payer at chemo visits: encounters with ADMIT_DATE in [first_chemo, last_chemo]; category = "Dual eligible" when dual_eligible
        enc_chemo_cols = [PATID_COL, "ADMIT_DATE", "PAYER_TYPE_PRIMARY"]
        if has_secondary:
            enc_chemo_cols.append("PAYER_TYPE_SECONDARY")
        enc_chemo = (
            pl.scan_parquet(enc_path)
            .with_columns(pl.col(PATID_COL).cast(pl.String))
            .filter(pl.col(PATID_COL).is_in(chemo[PATID_COL].implode()))
            .select(enc_chemo_cols)
            .with_columns([eff_expr, valid_expr, dual_expr])
            .select(PATID_COL, "ADMIT_DATE", "effective_payer", "dual_eligible", "_valid")
            .collect()
        )
        enc_chemo = enc_chemo.join(
            chemo.select(PATID_COL, "FIRST_CHEMO_DATE", "LAST_CHEMO_DATE"),
            on=PATID_COL,
            how="inner",
        )
        enc_chemo = enc_chemo.filter(
            (pl.col("ADMIT_DATE") >= pl.col("FIRST_CHEMO_DATE"))
            & (pl.col("ADMIT_DATE") <= pl.col("LAST_CHEMO_DATE"))
            & pl.col("_valid")
        )
        if enc_chemo.is_empty():
            base = base.with_columns(
                pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO")
            )
        else:
            enc_chemo = enc_chemo.with_columns(
                pl.Series(
                    "PAYER_CATEGORY",
                    [
                        _payer_category_from_effective_and_dual(
                            r["effective_payer"],
                            r.get("dual_eligible", 0) or 0,
                        )
                        for r in enc_chemo.iter_rows(named=True)
                    ],
                    dtype=pl.String,
                )
            )
            mode_chemo = (
                enc_chemo.group_by(PATID_COL, "PAYER_CATEGORY")
                .agg(pl.len().alias("_n"))
                .sort("_n", descending=True)
                .group_by(PATID_COL)
                .first()
                .select(PATID_COL, pl.col("PAYER_CATEGORY").alias("PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO"))
            )
            base = base.join(mode_chemo, on=PATID_COL, how="left")
    else:
        base = base.with_columns(
            pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_AT_FIRST_CHEMO"),
            pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_AT_LAST_CHEMO"),
            pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO"),
        )

    base = base.with_columns(pl.col("DUAL_ELIGIBLE").fill_null(0).cast(pl.Int8))
    return base.select(
        PATID_COL,
        "N_ENCOUNTERS",
        "N_ENCOUNTERS_WITH_PAYER",
        "N_DISTINCT_PAYER_CATEGORIES",
        "PAYER_CATEGORY_PRIMARY",
        "PAYER_CATEGORY_AT_FIRST_DX",
        "PAYER_CATEGORY_AT_FIRST_CHEMO",
        "PAYER_CATEGORY_AT_LAST_CHEMO",
        "PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO",
        "PAYER_TRANSITION",
        "DUAL_ELIGIBLE",
    )
