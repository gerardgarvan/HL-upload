"""Phase 5: Cleaning — treatment and surveillance modality flags from Outcomes.csv.

Reads Outcomes.csv code definitions, builds modality lookup tables, and adds MODALITY_*
binary flags to patient-level DataFrames. Scans PROCEDURES, LAB_RESULT_CM, and DIAGNOSIS
for matching CPT/HCPCS, LOINC, and ICD-10 codes.

**Pipeline position:** Phase 5 (Cleaning)
**Input:** Outcomes.csv (code definitions), PROCEDURES/LAB_RESULT_CM/DIAGNOSIS Parquet tables
**Output:** Patient-level DataFrame with MODALITY_* flag columns (SCT, MAMMO, ECHO, etc.)
**Orchestrated by:** scripts/build_patient_level.py or quality report assembly

**Key functions:**
- load_outcomes_code_lookup: Parse Outcomes.csv into modality→code sets
- add_modality_flags: Scan clinical tables and add MODALITY_* flags to patient DataFrame
"""

from pathlib import Path

import pandas as pd
import polars as pl

from src.validate.structural import PATID_COL

# Modality display name → output column slug mapping.
# Clinical rationale: Treatment modalities (SCT, CHEMO, RADIATION) and surveillance tests
# (cardiac, pulmonary, lab monitoring) are key outcomes for Hodgkin lymphoma survivorship
# studies. These flags identify patients receiving specific interventions or monitoring.
#
# Code systems used:
# - CPT/HCPCS: Procedures (stem cell transplant, imaging, cardiac tests)
# - LOINC: Lab tests (TSH, CBC)
# - ICD-10-PCS: Inpatient procedures
#
# TODO(audit): Outcomes.csv uses pandas for CSV parsing in an otherwise Polars codebase.
# Consider migrating to pl.read_csv() for consistency and to remove pandas dependency.
MODALITY_SLUG_MAP: dict[str, str] = {
    "Stem cell transplant": "SCT",
    "Mammogram": "MAMMO",
    "Breast MRI": "BREAST_MRI",
    "Echocardiogram": "ECHO",
    "Stress test": "STRESS",
    "Electrocardiogram": "ECG",
    "Multiple gated acquisition (MUGA)": "MUGA",
    "Pulmonary function test": "PFT",
    "Thyroid stimulating hormone": "TSH",
    "Complete blood count": "CBC",
}


def _normalize_code(code: str) -> str:
    """Normalize code for matching: strip whitespace, uppercase.

    Ensures consistent code representation across Outcomes.csv and clinical tables.

    Args:
        code: Raw code value (may be null).

    Returns:
        Normalized code string (uppercase, whitespace stripped). Empty string if null.
    """
    if pd.isna(code):
        return ""
    return str(code).strip().upper()


def load_outcomes_code_lookup(path: Path) -> dict[str, dict[str, set[str]]]:
    """Load Outcomes.csv and build modality→code_sets lookup.

    Reads Outcomes.csv (format: Modality, Code system, Code columns) and groups codes by
    modality and code system. Forward-fills Modality and Code system for multi-row entries.

    **Outcomes.csv format:** Hierarchical structure where Modality and Code system are
    forward-filled across rows. Each row has a single code. Multiple code systems per
    modality supported (e.g., CPT + LOINC for same modality).

    Clinical rationale: Centralized code definitions enable consistent modality detection
    across multiple clinical tables and support updates without code changes.

    TODO(audit): Uses pandas for CSV parsing. Migrate to pl.read_csv() to remove pandas
    dependency and improve consistency with rest of codebase.

    Args:
        path: Path to Outcomes.csv file.

    Returns:
        Nested dict: {modality_slug: {"cpt_hcpcs": set, "loinc": set, "icd10": set}}
        Codes are normalized (uppercase, whitespace stripped).
    """
    df = pd.read_csv(path)
    df["Modality"] = df["Modality"].ffill()
    df["Code system"] = df["Code system"].ffill()

    result: dict[str, dict[str, set[str]]] = {}
    for modality in df["Modality"].dropna().unique():
        slug = MODALITY_SLUG_MAP.get(modality)
        if slug is None:
            continue
        sub = df[df["Modality"] == modality]
        cpt_hcpcs: set[str] = set()
        loinc: set[str] = set()
        icd10: set[str] = set()

        for _, row in sub.iterrows():
            code = _normalize_code(row["Code"])
            if not code:
                continue
            cs = str(row["Code system"]).strip() if pd.notna(row["Code system"]) else ""
            if cs in ("CPT", "HCPCS"):
                cpt_hcpcs.add(code)
            elif "LOINC" in cs:
                loinc.add(code)
            elif "ICD-10" in cs:
                icd10.add(code)

        result[slug] = {
            "cpt_hcpcs": cpt_hcpcs,
            "loinc": loinc,
            "icd10": icd10,
        }

    return result


def add_modality_flags(
    patient_df: pl.DataFrame,
    table_map: dict[str, Path],
    outcomes_path: Path,
) -> pl.DataFrame:
    """Add MODALITY_* flag columns to patient DataFrame using Outcomes.csv code lookup.

    Scans PROCEDURES.PX (CPT/HCPCS), LAB_RESULT_CM.LAB_LOINC (LOINC), and DIAGNOSIS.DX
    (ICD-10) for matching codes. Creates binary Int8 flag per modality: MODALITY_{slug} = 1
    if patient has ≥1 matching code in any table, else 0.

    **Code matching:**
    - CPT/HCPCS → PROCEDURES.PX (procedures, imaging, therapies)
    - LOINC → LAB_RESULT_CM.LAB_LOINC (lab tests)
    - ICD-10-PCS → DIAGNOSIS.DX (inpatient procedures, dots stripped for matching)

    Uses lazy evaluation for memory efficiency when scanning large clinical tables.

    Clinical rationale: Modality flags identify patients receiving specific treatments
    (SCT, chemo, radiation) or surveillance (cardiac, pulmonary, lab monitoring) essential
    for survivorship outcomes analysis.

    Args:
        patient_df: Patient-level DataFrame with patient ID column.
        table_map: Dict mapping table names to Parquet file paths.
        outcomes_path: Path to Outcomes.csv code definition file.

    Returns:
        patient_df with MODALITY_* columns added (Int8 per modality: SCT, MAMMO, ECHO, etc.).
    """
    lookup = load_outcomes_code_lookup(outcomes_path)
    ids = patient_df.select(pl.col(PATID_COL).cast(pl.String))
    id_list = ids[PATID_COL].unique().to_list()

    proc_path = table_map.get("PROCEDURES")
    lab_path = table_map.get("LAB_RESULT_CM")
    diag_path = table_map.get("DIAGNOSIS")

    result = patient_df.clone()

    for slug, code_sets in lookup.items():
        matched_ids: set[str] = set()

        # CPT/HCPCS → PROCEDURES.PX
        if proc_path and proc_path.exists() and code_sets["cpt_hcpcs"]:
            cpt_codes = list(code_sets["cpt_hcpcs"])
            px_matched = (
                pl.scan_parquet(proc_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(pl.col(PATID_COL).is_in(id_list))
                .with_columns(pl.col("PX").cast(pl.String).str.to_uppercase().str.strip_chars())
                .filter(pl.col("PX").is_in(cpt_codes))
                .select(PATID_COL)
                .unique()
                .collect()
            )
            matched_ids.update(px_matched[PATID_COL].to_list())

        # LOINC → LAB_RESULT_CM.LAB_LOINC
        if lab_path and lab_path.exists() and code_sets["loinc"]:
            loinc_codes = list(code_sets["loinc"])
            lab_matched = (
                pl.scan_parquet(lab_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(pl.col(PATID_COL).is_in(id_list))
                .with_columns(pl.col("LAB_LOINC").cast(pl.String).str.to_uppercase().str.strip_chars())
                .filter(pl.col("LAB_LOINC").is_in(loinc_codes))
                .select(PATID_COL)
                .unique()
                .collect()
            )
            matched_ids.update(lab_matched[PATID_COL].to_list())

        # ICD-10 → DIAGNOSIS.DX (strip dots for matching)
        if diag_path and diag_path.exists() and code_sets["icd10"]:
            icd_codes = list(code_sets["icd10"])
            dx_matched = (
                pl.scan_parquet(diag_path)
                .with_columns(pl.col(PATID_COL).cast(pl.String))
                .filter(pl.col(PATID_COL).is_in(id_list))
                .with_columns(
                    pl.col("DX").cast(pl.String).str.to_uppercase().str.replace_all(r"\.", "").str.strip_chars().alias("_DX_NORM")
                )
                .filter(pl.col("_DX_NORM").is_in(icd_codes))
                .select(PATID_COL)
                .unique()
                .collect()
            )
            matched_ids.update(dx_matched[PATID_COL].to_list())

        col_name = f"MODALITY_{slug}"
        if matched_ids:
            flag_df = pl.DataFrame({PATID_COL: list(matched_ids)}).with_columns(pl.lit(1, dtype=pl.Int8).alias(col_name))
            result = result.join(flag_df, on=PATID_COL, how="left").with_columns(pl.col(col_name).fill_null(0).cast(pl.Int8))
        else:
            result = result.with_columns(pl.lit(0, dtype=pl.Int8).alias(col_name))

    return result
