# HL data loading & cleaning — modality flags from Outcomes.xlsx
"""Load Outcomes sheet, build code-to-modality lookup, add MODALITY_* flags to patient-level.

Uses PROCEDURES.PX, LAB_RESULT_CM.LAB_LOINC, DIAGNOSIS.DX to detect modality codes.
"""

from pathlib import Path

import pandas as pd
import polars as pl

from src.validate.structural import PATID_COL

# Modality display name → slug
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
    """Normalize code for matching: strip whitespace, uppercase."""
    if pd.isna(code):
        return ""
    return str(code).strip().upper()


def load_outcomes_code_lookup(path: Path) -> dict[str, dict[str, set[str]]]:
    """Load Outcomes sheet from Outcomes.xlsx and build modality→code_sets lookup.

    Forward-fills Modality and Code system. Returns:
    {modality_slug: {"cpt_hcpcs": set, "loinc": set, "icd10": set}}

    Codes are normalized (uppercase, stripped) for matching.
    """
    df = pd.read_excel(path, sheet_name="Outcomes")
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
    """Add MODALITY_* flag columns to patient_df using Outcomes.xlsx code lookup.

    Scans PROCEDURES.PX, LAB_RESULT_CM.LAB_LOINC, DIAGNOSIS.DX for matching codes.
    MODALITY_{slug} = 1 if patient has ≥1 match in any table, else 0.
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
                    pl.col("DX")
                    .cast(pl.String)
                    .str.to_uppercase()
                    .str.replace_all(r"\.", "")
                    .str.strip_chars()
                    .alias("_DX_NORM")
                )
                .filter(pl.col("_DX_NORM").is_in(icd_codes))
                .select(PATID_COL)
                .unique()
                .collect()
            )
            matched_ids.update(dx_matched[PATID_COL].to_list())

        col_name = f"MODALITY_{slug}"
        if matched_ids:
            flag_df = pl.DataFrame({PATID_COL: list(matched_ids)}).with_columns(
                pl.lit(1, dtype=pl.Int8).alias(col_name)
            )
            result = result.join(flag_df, on=PATID_COL, how="left").with_columns(
                pl.col(col_name).fill_null(0).cast(pl.Int8)
            )
        else:
            result = result.with_columns(pl.lit(0, dtype=pl.Int8).alias(col_name))

    return result
