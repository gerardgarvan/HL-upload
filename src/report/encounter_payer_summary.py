"""Phase 6: Assembly — encounter-payer patient-level summary with effective payer derivation.

Builds one-row-per-patient summary with payer-focused variables derived from ENCOUNTER. Implements
effective payer logic (primary→secondary fallback), dual-eligible detection (Medicare+Medicaid),
and payer-at-treatment windows (±30 days around diagnosis/chemo/radiation/SCT). Only includes
patients with ENROLLMENT records.

**Pipeline position:** Phase 6 (Assembly)
**Input:** ENCOUNTER (with PAYER_TYPE_PRIMARY/SECONDARY), ENROLLMENT, DIAGNOSIS, PROCEDURES, PRESCRIBING, TUMOR_REGISTRY
**Output:** derived/encounter_payer_summary.parquet (one row per enrolled patient)
**Orchestrated by:** scripts/build_insurance_summary.py

**Key functions:**
- build_encounter_payer_summary: Main assembly function (N_ENCOUNTERS, payer categories, transitions)
- _effective_payer_and_dual_exprs: Effective payer logic (primary→secondary fallback) and dual-eligible detection
- _collapse_payer_category: PCORnet typology prefix→category mapping (1→Medicare, 2→Medicaid, etc.)
- _payer_mode_in_window: Mode payer category in ±N days window around treatment dates

**Output variables:**
- N_ENCOUNTERS, N_ENCOUNTERS_WITH_PAYER, N_DISTINCT_PAYER_CATEGORIES, PAYER_CATEGORY_PRIMARY
- PAYER_CATEGORY_AT_FIRST_DX/CHEMO/RADIATION/SCT, PAYER_CATEGORY_AT_LAST_CHEMO/RADIATION/SCT
- PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO, PAYER_TRANSITION, DUAL_ELIGIBLE
- HAD_CHEMO, HAD_RADIATION, HAD_SCT (treatment flags)

**Payer categories:** Medicare, Medicaid, Dual eligible, Private, Other government,
No payment / Self-pay, Other, Unavailable, Unknown (PCORnet typology-based).

TODO(audit): Payer logic complexity — effective payer fallback chain, dual-eligible codes,
sentinel value handling (99/9999), and 30-day treatment windows all introduce assumptions
that may not match clinical reality. Validate with stakeholder review.
"""

from pathlib import Path

import polars as pl

from src.validate.cohort import (
    ALL_HL_CODES,
    ALL_HL_NORMALIZED,
    detect_dx_format,
)
from src.validate.structural import PATID_COL, TUMOR_REGISTRY_TABLES

# Invalid payer codes: PCORnet sentinel values indicating missing/unknown payer information.
# NI = No Information, UN = Unknown, OT = Other (not elsewhere classified).
# Clinical rationale: These codes do not represent actual payer types and should not be used
# in payer analysis — they trigger fallback to PAYER_TYPE_SECONDARY when present as primary.
INVALID_PAYER: set[str] = {"NI", "UN", "OT"}

# Sentinel value configuration: Controls whether 99/9999 are treated as sentinel (invalid) values.
# **When False (current setting):** 99/9999 map to category "Unavailable" (valid but unknown payer).
# **When True:** 99/9999 trigger fallback to secondary (treated as sentinel like NI/UN/OT).
#
# Clinical rationale: 99/9999 semantics vary by data source — some partners use 99 for "Unknown",
# others use it as valid placeholder. Current setting (False) treats as valid to maximize data
# retention. INCLUDE_99_AS_SENTINEL behavior documented in PAYER_VARIABLES_AND_CATEGORIES.md.
#
# TODO(audit): Validate 99/9999 semantics with data partners. If partners use inconsistently,
# consider partner-specific handling or standardized data dictionary enforcement.
INCLUDE_99_AS_SENTINEL: bool = False

# PCORnet dual-eligible payer codes: 14, 141, 142 indicate dual Medicare-Medicaid eligibility.
# - 14: Dual Eligibility Medicare/Medicaid Organization (general dual-eligible)
# - 141: Dual-Eligible Special Needs Plan (D-SNP)
# - 142: Fully Integrated Dual-Eligible Special Needs Plan (FIDE-SNP)
#
# **NOT dual-eligible:** Code 41 = Corrections Federal (Other government category), not dual.
#
# Clinical rationale: Dual-eligible patients have complex payer status (Medicare + Medicaid) and
# different cost-sharing, which affects healthcare utilization and financial burden analysis.
DUAL_ELIGIBLE_CODES: tuple[str, ...] = ("14", "141", "142")

# Treatment window for payer-at-treatment variables: ±30 days around treatment dates.
# Clinical rationale: Payer at exact treatment date may be missing or misrecorded. 30-day window
# captures nearby encounters while remaining temporally specific. Mode (most frequent) payer
# category within window used to represent payer at treatment.
#
# Only encounters with valid (non-null, non-sentinel) effective payer counted in window. This
# avoids null/NI/UN encounters biasing the mode calculation.
#
# TODO(audit): 30-day window is arbitrary — no clinical standard. Consider sensitivity analysis
# with 7/14/60-day windows to assess impact on payer classification stability.
PAYER_AT_TREATMENT_WINDOW_DAYS: int = 30

# CPT codes for radiation therapy (CPT 774xx series: external beam radiation).
# Clinical rationale: Radiation is a major HL treatment modality. Identifying radiation procedures
# enables payer-at-radiation analysis and treatment cohort stratification.
RADIATION_CPTS: frozenset[str] = frozenset({"77401", "77402", "77407", "77412", "77427"})

# CPT codes for stem cell transplant (CPT 382xx series: bone marrow/stem cell procedures).
# - 38240: Bone marrow/stem cell transplant allogeneic
# - 38241: Bone marrow/stem cell transplant autologous
# - 38242: Bone marrow/stem cell transplant allogeneic donor lymphocyte infusion
# - 38230/38232: Bone marrow harvesting procedures
#
# Clinical rationale: SCT is high-intensity HL treatment for refractory/relapsed disease. Identifying
# SCT procedures enables high-cost treatment cohort analysis and late effects surveillance.
SCT_CPTS: frozenset[str] = frozenset({"38240", "38241", "38242", "38230", "38232"})


# Payer code → category mapping (PCORnet typology-based prefix matching)
def _collapse_payer_category(code: str) -> str:
    """Map PCORnet PAYER_TYPE_PRIMARY code to collapsed payer category.

    Uses prefix matching on PCORnet payer typology codes (1xx=Medicare, 2xx=Medicaid, etc.).
    Handles null/empty/sentinel values (NI, UN, OT, UNKNOWN) and special codes (99/9999).

    **Category mapping:**
    - null/""/NI/UN/OT/UNKNOWN → "Unknown"
    - 99/9999 → "Unavailable" (when INCLUDE_99_AS_SENTINEL=False)
    - 1xx → "Medicare" (includes Medicare Advantage, Medicare FFS, etc.)
    - 2xx → "Medicaid" (includes Medicaid managed care, Medicaid FFS)
    - 5xx/6xx → "Private" (commercial insurance, self-insured plans)
    - 3xx/4xx → "Other government" (VA, TriCare, Indian Health Service, Corrections)
    - 8xx → "No payment / Self-pay" (uninsured, self-pay)
    - 7xx/9xx → "Other" (other payers not elsewhere classified)
    - default → "Other" (unrecognized codes)

    **NOT used for dual-eligible:** Code 41 (Corrections Federal) maps to "Other government",
    NOT "Dual eligible". Dual-eligible handled separately in _payer_category_from_effective_and_dual.

    Clinical rationale: PCORnet payer typology enables standardized payer classification across
    data networks. Collapsed categories support stratified analysis while maintaining HIPAA-
    compliant small-cell thresholds.

    TODO(audit): Category "Unavailable" (99/9999) vs "Unknown" (NI/UN/OT) semantic distinction
    unclear — both represent missing payer information. Consider collapsing into single category.

    Args:
        code: PCORnet PAYER_TYPE_PRIMARY code (may be null).

    Returns:
        Payer category string (Medicare/Medicaid/Private/Other government/
        No payment / Self-pay/Other/Unavailable/Unknown).
    """
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
    """Determine payer category for one encounter, applying dual-eligible override.

    Applies dual-eligible override logic: when encounter is dual-eligible (Medicare+Medicaid
    or code 14/141/142), category = "Dual eligible" regardless of effective payer code.
    Otherwise maps effective payer via _collapse_payer_category.

    Clinical rationale: Dual-eligible patients are a distinct payer category with unique
    cost-sharing and access patterns. Overriding standard Medicare/Medicaid categorization
    enables dual-eligible cohort analysis.

    Args:
        effective_payer: Effective payer code (primary if valid, else secondary if valid).
        dual_eligible: Binary flag (1=dual-eligible, 0=not dual-eligible).

    Returns:
        "Dual eligible" if dual_eligible==1, otherwise payer category from _collapse_payer_category.
    """
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
    return pl.col(col).is_not_null() & (pl.col(col).cast(pl.Utf8) != "") & ~pl.col(col).cast(pl.Utf8).is_in(sentinel)


def _get_first_hl_dx_dates(table_map: dict[str, Path], ids: pl.Series) -> pl.DataFrame | None:
    """First HL diagnosis date per patient from DIAGNOSIS and tumor registry diagnosis dates.

    DIAGNOSIS contribution: earliest HL-coded DX_DATE.
    Tumor registry contribution: earliest DATE_OF_DIAGNOSIS across TUMOR_REGISTRY1/2/3.
    Final FIRST_HL_DX_DATE is the minimum of available sources per patient.
    """
    dx_frames: list[pl.DataFrame] = []

    diag_path = table_map.get("DIAGNOSIS")
    if diag_path and diag_path.exists():
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
            .select(PATID_COL, pl.col("DX_DATE").alias("_dx_d"))
            .collect()
        )
        if not diag.is_empty():
            dx_frames.append(diag)

    for tr_name in sorted(TUMOR_REGISTRY_TABLES):
        tr_path = table_map.get(tr_name)
        if not tr_path or not tr_path.exists():
            continue
        schema = pl.read_parquet_schema(tr_path)
        if "DATE_OF_DIAGNOSIS" not in schema.names():
            continue
        tr = (
            pl.scan_parquet(tr_path)
            .with_columns(pl.col(PATID_COL).cast(pl.String))
            .filter(pl.col(PATID_COL).is_in(ids.implode()))
            .select(PATID_COL, "DATE_OF_DIAGNOSIS")
            .collect()
        )
        if tr.is_empty():
            continue
        col = "DATE_OF_DIAGNOSIS"
        if tr[col].dtype in (pl.String, pl.Utf8):
            tr = tr.with_columns(
                pl.col(col)
                .str.to_date("%Y.%m.%d", strict=False)
                .fill_null(pl.col(col).str.to_date("%m/%d/%Y", strict=False))
                .fill_null(pl.col(col).str.to_date("%d%b%Y", strict=False))
                .fill_null(pl.col(col).str.to_date("%Y%m%d", strict=False))
                .alias("_dx_d")
            )
        else:
            tr = tr.with_columns(pl.col(col).alias("_dx_d"))
        tr_dx = tr.filter(pl.col("_dx_d").is_not_null()).select(PATID_COL, "_dx_d")
        if not tr_dx.is_empty():
            dx_frames.append(tr_dx)

    if not dx_frames:
        return None
    all_dx = pl.concat(dx_frames)
    return all_dx.group_by(PATID_COL).agg(pl.col("_dx_d").min().alias("FIRST_HL_DX_DATE"))


def _get_chemo_dates(table_map: dict[str, Path], ids: pl.Series) -> pl.DataFrame | None:
    """First and last chemo date per patient.

    Sources:
    - Tumor registry: DT_CHEMO, CHEMO_START_DATE_SUMMARY
    - Prescribing: RX_ORDER_DATE, RX_START_DATE (if present)
    """
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
        rx_cols = [c for c in ["RX_ORDER_DATE", "RX_START_DATE"] if c in rx_schema.names()]
        if rx_cols:
            rx = (
                pl.scan_parquet(rx_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(pl.col(PATID_COL).is_in(ids.implode()))
                .select([PATID_COL] + rx_cols)
                .collect()
            )
            if not rx.is_empty():
                for col in rx_cols:
                    rc = rx.filter(pl.col(col).is_not_null()).select(PATID_COL, pl.col(col).alias("_chemo_d"))
                    if not rc.is_empty():
                        chemo_frames.append(rc)
    if not chemo_frames:
        return None
    all_chemo = pl.concat(chemo_frames)
    return all_chemo.group_by(PATID_COL).agg(
        pl.col("_chemo_d").min().alias("FIRST_CHEMO_DATE"),
        pl.col("_chemo_d").max().alias("LAST_CHEMO_DATE"),
    )


def _get_radiation_dates(table_map: dict[str, Path], ids: pl.Series) -> pl.DataFrame | None:
    """First and last radiation date per patient.

    Sources:
    - Tumor registry: DT_RAD, RAD_START_DATE_SUMMARY
    - Procedures: radiation CPTs with PX_DATE
    """
    rad_frames: list[pl.DataFrame] = []
    tr_cols = ["DT_RAD", "RAD_START_DATE_SUMMARY"]
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
            tc = tr.filter(pl.col("_d").is_not_null()).select(PATID_COL, pl.col("_d").alias("_rad_d"))
            if not tc.is_empty():
                rad_frames.append(tc)
            tr = tr.drop("_d")
    px_path = table_map.get("PROCEDURES")
    if px_path and px_path.exists():
        px_schema = pl.read_parquet_schema(px_path)
        if "PX" in px_schema.names() and "PX_DATE" in px_schema.names():
            px = (
                pl.scan_parquet(px_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(pl.col(PATID_COL).is_in(ids.implode()))
                .filter(pl.col("PX").cast(pl.Utf8).is_in(list(RADIATION_CPTS)))
                .filter(pl.col("PX_DATE").is_not_null())
                .select(PATID_COL, pl.col("PX_DATE").alias("_rad_d"))
                .collect()
            )
            if not px.is_empty():
                rad_frames.append(px)
    if not rad_frames:
        return None
    all_rad = pl.concat(rad_frames)
    return all_rad.group_by(PATID_COL).agg(
        pl.col("_rad_d").min().alias("FIRST_RADIATION_DATE"),
        pl.col("_rad_d").max().alias("LAST_RADIATION_DATE"),
    )


def _get_sct_dates(table_map: dict[str, Path], ids: pl.Series) -> pl.DataFrame | None:
    """First and last stem cell transplant date per patient.

    Sources:
    - Procedures: SCT CPTs with PX_DATE
    - Tumor registry candidate columns (if present): DT_SCT, SCT_DATE, BMT_DATE, TRANSPLANT_DATE,
      HCT_DATE, DT_TRANSPLANT
    """
    sct_frames: list[pl.DataFrame] = []

    px_path = table_map.get("PROCEDURES")
    if px_path and px_path.exists():
        px_schema = pl.read_parquet_schema(px_path)
        if "PX" in px_schema.names() and "PX_DATE" in px_schema.names():
            px = (
                pl.scan_parquet(px_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(pl.col(PATID_COL).is_in(ids.implode()))
                .filter(pl.col("PX").cast(pl.Utf8).is_in(list(SCT_CPTS)))
                .filter(pl.col("PX_DATE").is_not_null())
                .select(PATID_COL, pl.col("PX_DATE").alias("_sct_d"))
                .collect()
            )
            if not px.is_empty():
                sct_frames.append(px)

    tr_sct_cols = ["DT_SCT", "SCT_DATE", "BMT_DATE", "TRANSPLANT_DATE", "HCT_DATE", "DT_TRANSPLANT"]
    for tr_name in sorted(TUMOR_REGISTRY_TABLES):
        tr_path = table_map.get(tr_name)
        if not tr_path or not tr_path.exists():
            continue
        schema = pl.read_parquet_schema(tr_path)
        available = [c for c in tr_sct_cols if c in schema.names()]
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
            tc = tr.filter(pl.col("_d").is_not_null()).select(PATID_COL, pl.col("_d").alias("_sct_d"))
            if not tc.is_empty():
                sct_frames.append(tc)
            tr = tr.drop("_d")

    if not sct_frames:
        return None
    all_sct = pl.concat(sct_frames)
    return all_sct.group_by(PATID_COL).agg(
        pl.col("_sct_d").min().alias("FIRST_SCT_DATE"),
        pl.col("_sct_d").max().alias("LAST_SCT_DATE"),
    )


def _effective_payer_and_dual_exprs(
    has_secondary: bool,
) -> tuple[pl.Expr, pl.Expr, pl.Expr]:
    """Build Polars expressions for effective payer logic and dual-eligible detection.

    Implements core payer derivation logic:
    1. **Effective payer:** Primary if valid, else secondary if valid, else null
    2. **Valid payer:** Non-null, non-empty, not in sentinel set (NI/UN/OT/99/9999 per config)
    3. **Dual-eligible:** Medicare+Medicaid combination OR code 14/141/142

    **When PAYER_TYPE_SECONDARY absent (has_secondary=False):**
    - Effective payer = primary only
    - Dual-eligible = 0 (cannot compute without secondary)

    **Dual-eligible detection logic:**
    - (Primary Medicare [1xx] AND Secondary Medicaid [2xx]) OR
    - (Primary Medicaid AND Secondary Medicare) OR
    - Primary in {14, 141, 142} OR
    - Secondary in {14, 141, 142}

    Clinical rationale: Primary payer captures most encounters, but secondary fallback handles
    cases where primary is sentinel/missing (common in EHR data). Dual-eligible detection
    identifies patients with complex payer status affecting cost and access.

    TODO(audit): When secondary is absent, dual-eligible forced to 0 even if primary is 14/141/142.
    Consider using primary codes for partial dual-eligible detection when secondary unavailable.

    Args:
        has_secondary: Whether PAYER_TYPE_SECONDARY column exists in ENCOUNTER table.

    Returns:
        Tuple of (effective_payer expression, _valid expression, dual_eligible expression).
    """
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
            ((primary_medicare & secondary_medicaid) | (primary_medicaid & secondary_medicare) | primary_dual | secondary_dual)
            .cast(pl.Int8)
            .fill_null(0)
        )
    else:
        effective_payer = pl.when(valid_primary).then(pl.col("PAYER_TYPE_PRIMARY").cast(pl.Utf8)).otherwise(pl.lit(None).cast(pl.Utf8))
        dual_eligible = pl.lit(0).cast(pl.Int8)
    sentinel = list(_sentinel_set())
    _valid = effective_payer.is_not_null() & (effective_payer != "") & ~effective_payer.is_in(sentinel)
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
    joined = joined.with_columns((pl.col("ADMIT_DATE") - pl.col(date_col)).dt.total_days().alias("_days_diff"))
    within = joined.filter((pl.col("_days_diff") >= -window_days) & (pl.col("_days_diff") <= window_days))
    if within.is_empty():
        return patients.select(PATID_COL).with_columns(
            pl.lit(None).cast(pl.String).alias("_raw_payer"),
            pl.lit(0).cast(pl.Int8).alias("_dual_eligible"),
        )
    closest = within.with_columns(pl.col("_days_diff").abs().alias("_abs")).sort("_abs").group_by(PATID_COL).first()
    return (
        patients.select(PATID_COL)
        .join(
            closest.select(
                PATID_COL,
                pl.col("effective_payer").alias("_raw_payer"),
                pl.col("dual_eligible").alias("_dual_eligible"),
            ),
            on=PATID_COL,
            how="left",
        )
        .with_columns(pl.col("_dual_eligible").fill_null(0).cast(pl.Int8))
    )


def _payer_mode_in_window(
    enc_path: Path,
    patients: pl.DataFrame,
    date_col: str,
    window_days: int = 30,
) -> pl.DataFrame:
    """Mode (most frequent) valid payer category among encounters within ±window_days of patients[date_col].

    Only encounters with valid (non-missing, non-sentinel) effective payer are counted; the most
    common such category per patient is returned. Returns PATID_COL and _mode_category (string).
    """
    enc_schema = pl.read_parquet_schema(enc_path)
    if "ADMIT_DATE" not in enc_schema.names() or "PAYER_TYPE_PRIMARY" not in enc_schema.names():
        return patients.select(PATID_COL).with_columns(pl.lit(None).cast(pl.String).alias("_mode_category"))
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
        .with_columns([eff_expr, valid_expr, dual_expr])
        .select(PATID_COL, "ADMIT_DATE", "effective_payer", "dual_eligible", "_valid")
        .collect()
    )
    if enc.is_empty():
        return patients.select(PATID_COL).with_columns(pl.lit(None).cast(pl.String).alias("_mode_category"))
    joined = patients.select(PATID_COL, date_col).join(enc, on=PATID_COL, how="inner")
    joined = joined.with_columns((pl.col("ADMIT_DATE") - pl.col(date_col)).dt.total_days().alias("_days_diff"))
    within = joined.filter((pl.col("_days_diff") >= -window_days) & (pl.col("_days_diff") <= window_days) & pl.col("_valid"))
    if within.is_empty():
        return patients.select(PATID_COL).with_columns(pl.lit(None).cast(pl.String).alias("_mode_category"))
    within = within.with_columns(
        pl.Series(
            "PAYER_CATEGORY",
            [
                _payer_category_from_effective_and_dual(
                    r["effective_payer"],
                    r.get("dual_eligible", 0) or 0,
                )
                for r in within.iter_rows(named=True)
            ],
            dtype=pl.String,
        )
    )
    mode_df = (
        within.group_by(PATID_COL, "PAYER_CATEGORY")
        .agg(pl.len().alias("_n"))
        .sort("_n", descending=True)
        .group_by(PATID_COL)
        .first()
        .select(PATID_COL, pl.col("PAYER_CATEGORY").alias("_mode_category"))
    )
    return patients.select(PATID_COL).join(mode_df, on=PATID_COL, how="left")


def build_encounter_payer_summary(table_map: dict[str, Path]) -> pl.DataFrame:
    """Build one-row-per-patient summary with payer-focused variables from ENCOUNTER.

    Assembles encounter-derived payer variables: encounter counts, effective payer categories,
    payer at diagnosis/treatment dates (±30 day windows), dual-eligible status, and treatment
    flags. Only includes patients with ≥1 ENROLLMENT record.

    **Effective payer logic:** Primary if valid, else secondary if valid, else null. Valid =
    non-null, non-empty, not in sentinel set (NI/UN/OT, optionally 99/9999).

    **Payer categories:** Medicare, Medicaid, Dual eligible, Private, Other government,
    No payment / Self-pay, Other, Unavailable, Unknown. Dual-eligible overrides standard
    Medicare/Medicaid when encounter is dual (Medicare+Medicaid or code 14/141/142).

    **Payer-at-treatment variables:** Mode (most frequent) payer category among encounters
    within ±30 days of treatment dates (first DX, first/last chemo/radiation/SCT). Only
    encounters with valid effective payer counted.

    **Treatment dates:**
    - Chemo: TUMOR_REGISTRY (DT_CHEMO, CHEMO_START_DATE_SUMMARY) + PRESCRIBING (RX_ORDER_DATE)
    - Radiation: TUMOR_REGISTRY (DT_RAD) + PROCEDURES (radiation CPTs)
    - SCT: PROCEDURES (SCT CPTs)

    **Output variables:**
    - N_ENCOUNTERS: Total encounters per patient
    - N_ENCOUNTERS_WITH_PAYER: Encounters with valid effective payer
    - N_DISTINCT_PAYER_CATEGORIES: Distinct payer categories (valid encounters only)
    - PAYER_CATEGORY_PRIMARY: Most frequent payer category (mode)
    - PAYER_CATEGORY_AT_FIRST_DX/CHEMO/RADIATION/SCT: Mode payer in ±30 day window
    - PAYER_CATEGORY_AT_LAST_CHEMO/RADIATION/SCT: Mode payer in ±30 day window
    - PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO: Mode payer between first/last chemo dates
    - PAYER_TRANSITION: 1 if N_DISTINCT_PAYER_CATEGORIES > 1 (payer switching), else 0
    - DUAL_ELIGIBLE: 1 if any encounter is dual-eligible, else 0
    - HAD_CHEMO/RADIATION/SCT: 1 if patient has ≥1 treatment date, else 0

    Clinical rationale: Payer information enables healthcare access, cost, and disparities
    analysis. Payer-at-treatment captures payer during active treatment (when costs highest).
    Dual-eligible identification supports analysis of vulnerable populations.

    Args:
        table_map: Dict mapping table names to Parquet file paths.

    Returns:
        DataFrame with one row per enrolled patient with encounters. Returns empty DataFrame
        with schema if ENCOUNTER table missing or no PAYER_TYPE_PRIMARY column.
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
        "PAYER_CATEGORY_AT_FIRST_RADIATION": pl.String,
        "PAYER_CATEGORY_AT_LAST_RADIATION": pl.String,
        "PAYER_CATEGORY_AT_FIRST_SCT": pl.String,
        "PAYER_CATEGORY_AT_LAST_SCT": pl.String,
        "PAYER_TRANSITION": pl.Int8,
        "DUAL_ELIGIBLE": pl.Int8,
        "HAD_CHEMO": pl.Int8,
        "HAD_RADIATION": pl.Int8,
        "HAD_SCT": pl.Int8,
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
            enrolled_ids = pl.scan_parquet(enr_path).select(pl.col(PATID_COL).cast(pl.String).unique()).collect()
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
    valid_enc = enc.filter(pl.col("_valid")).select(PATID_COL, "effective_payer", "dual_eligible").collect()

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

        distinct = valid_enc.group_by(PATID_COL).agg(pl.col("PAYER_CATEGORY").n_unique().alias("N_DISTINCT_PAYER_CATEGORIES"))

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

    base = base.with_columns((pl.col("N_DISTINCT_PAYER_CATEGORIES") > 1).cast(pl.Int8).alias("PAYER_TRANSITION"))

    # Payer at first diagnosis, first chemo, last chemo, most frequent at chemo
    ids = base[PATID_COL]
    first_dx = _get_first_hl_dx_dates(table_map, ids)
    chemo = _get_chemo_dates(table_map, ids)

    # Payer at first DX / first chemo / last chemo: ±PAYER_AT_TREATMENT_WINDOW_DAYS; mode of valid (non-missing) payer in window
    if first_dx is not None:
        payer_dx = _payer_mode_in_window(enc_path, first_dx, "FIRST_HL_DX_DATE", window_days=PAYER_AT_TREATMENT_WINDOW_DAYS)
        base = base.join(
            payer_dx.select(
                PATID_COL,
                pl.col("_mode_category").alias("PAYER_CATEGORY_AT_FIRST_DX"),
            ),
            on=PATID_COL,
            how="left",
        )
    else:
        base = base.with_columns(pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_AT_FIRST_DX"))

    if chemo is not None:
        payer_first = _payer_mode_in_window(enc_path, chemo, "FIRST_CHEMO_DATE", window_days=PAYER_AT_TREATMENT_WINDOW_DAYS)
        base = base.join(
            payer_first.select(
                PATID_COL,
                pl.col("_mode_category").alias("PAYER_CATEGORY_AT_FIRST_CHEMO"),
            ),
            on=PATID_COL,
            how="left",
        )

        payer_last = _payer_mode_in_window(enc_path, chemo, "LAST_CHEMO_DATE", window_days=PAYER_AT_TREATMENT_WINDOW_DAYS)
        base = base.join(
            payer_last.select(
                PATID_COL,
                pl.col("_mode_category").alias("PAYER_CATEGORY_AT_LAST_CHEMO"),
            ),
            on=PATID_COL,
            how="left",
        )

        # Most frequent payer at chemo visits: encounters with ADMIT_DATE in [first_chemo, last_chemo]
        # Category = "Dual eligible" when dual_eligible
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
            (pl.col("ADMIT_DATE") >= pl.col("FIRST_CHEMO_DATE")) & (pl.col("ADMIT_DATE") <= pl.col("LAST_CHEMO_DATE")) & pl.col("_valid")
        )
        if enc_chemo.is_empty():
            base = base.with_columns(pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO"))
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

    # Payer at first/last radiation: ±PAYER_AT_TREATMENT_WINDOW_DAYS; mode of valid payer in window
    radiation = _get_radiation_dates(table_map, ids)
    if radiation is not None:
        payer_first_rad = _payer_mode_in_window(enc_path, radiation, "FIRST_RADIATION_DATE", window_days=PAYER_AT_TREATMENT_WINDOW_DAYS)
        base = base.join(
            payer_first_rad.select(
                PATID_COL,
                pl.col("_mode_category").alias("PAYER_CATEGORY_AT_FIRST_RADIATION"),
            ),
            on=PATID_COL,
            how="left",
        )
        payer_last_rad = _payer_mode_in_window(enc_path, radiation, "LAST_RADIATION_DATE", window_days=PAYER_AT_TREATMENT_WINDOW_DAYS)
        base = base.join(
            payer_last_rad.select(
                PATID_COL,
                pl.col("_mode_category").alias("PAYER_CATEGORY_AT_LAST_RADIATION"),
            ),
            on=PATID_COL,
            how="left",
        )
    else:
        base = base.with_columns(
            pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_AT_FIRST_RADIATION"),
            pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_AT_LAST_RADIATION"),
        )

    # Payer at first/last SCT: ±PAYER_AT_TREATMENT_WINDOW_DAYS; mode of valid payer in window
    sct = _get_sct_dates(table_map, ids)
    if sct is not None:
        payer_first_sct = _payer_mode_in_window(enc_path, sct, "FIRST_SCT_DATE", window_days=PAYER_AT_TREATMENT_WINDOW_DAYS)
        base = base.join(
            payer_first_sct.select(
                PATID_COL,
                pl.col("_mode_category").alias("PAYER_CATEGORY_AT_FIRST_SCT"),
            ),
            on=PATID_COL,
            how="left",
        )
        payer_last_sct = _payer_mode_in_window(enc_path, sct, "LAST_SCT_DATE", window_days=PAYER_AT_TREATMENT_WINDOW_DAYS)
        base = base.join(
            payer_last_sct.select(
                PATID_COL,
                pl.col("_mode_category").alias("PAYER_CATEGORY_AT_LAST_SCT"),
            ),
            on=PATID_COL,
            how="left",
        )
    else:
        base = base.with_columns(
            pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_AT_FIRST_SCT"),
            pl.lit(None).cast(pl.String).alias("PAYER_CATEGORY_AT_LAST_SCT"),
        )

    # Treatment dates and flags: join date columns and derive HAD_* flags
    if first_dx is not None:
        base = base.join(
            first_dx.select(PATID_COL, "FIRST_HL_DX_DATE"),
            on=PATID_COL,
            how="left",
        )
    else:
        base = base.with_columns(
            pl.lit(None).cast(pl.Date).alias("FIRST_HL_DX_DATE"),
        )

    if chemo is not None:
        base = base.join(
            chemo.select(PATID_COL, "FIRST_CHEMO_DATE", "LAST_CHEMO_DATE"),
            on=PATID_COL,
            how="left",
        )
        base = base.with_columns(
            pl.col("LAST_CHEMO_DATE").is_not_null().cast(pl.Int8).alias("HAD_CHEMO")
        )
    else:
        base = base.with_columns(
            pl.lit(None).cast(pl.Date).alias("FIRST_CHEMO_DATE"),
            pl.lit(None).cast(pl.Date).alias("LAST_CHEMO_DATE"),
            pl.lit(0).cast(pl.Int8).alias("HAD_CHEMO"),
        )

    if radiation is not None:
        base = base.join(
            radiation.select(PATID_COL, "FIRST_RADIATION_DATE", "LAST_RADIATION_DATE"),
            on=PATID_COL,
            how="left",
        )
        base = base.with_columns(
            pl.col("LAST_RADIATION_DATE").is_not_null().cast(pl.Int8).alias("HAD_RADIATION")
        )
    else:
        base = base.with_columns(
            pl.lit(None).cast(pl.Date).alias("FIRST_RADIATION_DATE"),
            pl.lit(None).cast(pl.Date).alias("LAST_RADIATION_DATE"),
            pl.lit(0).cast(pl.Int8).alias("HAD_RADIATION"),
        )

    if sct is not None:
        base = base.join(
            sct.select(PATID_COL, "FIRST_SCT_DATE", "LAST_SCT_DATE"),
            on=PATID_COL,
            how="left",
        )
        base = base.with_columns(
            pl.col("LAST_SCT_DATE").is_not_null().cast(pl.Int8).alias("HAD_SCT")
        )
    else:
        base = base.with_columns(
            pl.lit(None).cast(pl.Date).alias("FIRST_SCT_DATE"),
            pl.lit(None).cast(pl.Date).alias("LAST_SCT_DATE"),
            pl.lit(0).cast(pl.Int8).alias("HAD_SCT"),
        )

    base = base.with_columns(pl.col("DUAL_ELIGIBLE").fill_null(0).cast(pl.Int8))
    return base.select(
        PATID_COL,
        "N_ENCOUNTERS",
        "N_ENCOUNTERS_WITH_PAYER",
        "N_DISTINCT_PAYER_CATEGORIES",
        "PAYER_CATEGORY_PRIMARY",
        "PAYER_CATEGORY_AT_FIRST_DX",
        "FIRST_HL_DX_DATE",
        "PAYER_CATEGORY_AT_FIRST_CHEMO",
        "PAYER_CATEGORY_AT_LAST_CHEMO",
        "PAYER_CATEGORY_MOST_FREQUENT_AT_CHEMO",
        "PAYER_CATEGORY_AT_FIRST_RADIATION",
        "PAYER_CATEGORY_AT_LAST_RADIATION",
        "PAYER_CATEGORY_AT_FIRST_SCT",
        "PAYER_CATEGORY_AT_LAST_SCT",
        "PAYER_TRANSITION",
        "DUAL_ELIGIBLE",
        "FIRST_CHEMO_DATE",
        "LAST_CHEMO_DATE",
        "FIRST_RADIATION_DATE",
        "LAST_RADIATION_DATE",
        "FIRST_SCT_DATE",
        "LAST_SCT_DATE",
        "HAD_CHEMO",
        "HAD_RADIATION",
        "HAD_SCT",
    )
