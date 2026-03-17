"""PCORnet CDM table schema definitions for checkpoint validation.

This module defines expected schemas for critical PCORnet Common Data Model (CDM)
tables using plain Python dicts mapping column names to Polars dtypes. These
schemas support checkpoint validation at pipeline phase boundaries.

**Design Philosophy:**
- Plain dicts, not Pandera: Keeps validation lightweight and dependency-free
- Non-strict: Only validates listed columns exist with correct dtypes; extra columns allowed
- Dtype flexibility: Columns may accept multiple dtypes (Date or String) to handle detection variance

**Why Plain Dicts Instead of Pandera:**
Checkpoint validation needs to check "do these critical columns exist with the
right types?" This is a simple dtype comparison problem. Pandera adds 10+ MB of
dependencies for features we don't need (value constraints, statistical checks,
complex transformations). For Phase 2 checkpoint validation, plain Polars dtype
dicts are sufficient and maintainable.

If Phase 3 requires deep value validation (range checks, statistical profiling,
cross-column constraints), Pandera can be added then as an optional enhancement.

**PCORnet CDM Context:**
PCORnet CDM defines a standard schema for multi-site clinical data networks.
Core tables include DEMOGRAPHIC (patient attributes), ENROLLMENT (insurance),
ENCOUNTER (visits), DIAGNOSIS (conditions), PROCEDURES, LAB_RESULT_CM, VITAL, etc.

The schemas defined here capture the subset of columns required for HL cohort
identification and outcome ascertainment. Not all PCORnet columns are listed -
only those used by this pipeline.

**Column Naming:**
PCORnet CDM uses uppercase snake_case (PATID, ENCOUNTERID, DX_DATE).
This pipeline aliases PATID -> ID for brevity in derived outputs.

References:
- PCORnet CDM Specification: https://pcornet.org/data/
- HL cohort ICD code definitions: .planning/phases/02-validation-suppression-hardening/02-RESEARCH.md
"""

import polars as pl

# DIAGNOSIS table: Diagnosis codes from encounters
# Core HL cohort identification depends on ICD-9/ICD-10 codes in DX column
DIAGNOSIS_EXPECTED = {
    "ID": pl.Utf8,  # PATID in PCORnet CDM (patient identifier)
    "ENCOUNTERID": pl.Utf8,  # Links to ENCOUNTER table
    "DX": pl.Utf8,  # Diagnosis code (ICD-9-CM or ICD-10-CM)
    "DX_TYPE": pl.Utf8,  # Code type: "09" (ICD-9), "10" (ICD-10), etc.
    "DX_DATE": (pl.Date, pl.Utf8),  # Date flexibility: may be Date or String depending on parsing
}

# ENCOUNTER table: Clinical encounters (ED, inpatient, outpatient)
# HL outcome ascertainment tracks ED visits and hospitalizations post-index
ENCOUNTER_EXPECTED = {
    "ENCOUNTERID": pl.Utf8,  # Primary key
    "ID": pl.Utf8,  # PATID (patient identifier)
    "ADMIT_DATE": (pl.Date, pl.Utf8),  # Encounter start date (date detection may vary)
    "ENC_TYPE": pl.Utf8,  # Encounter type: "ED", "IP", "AV", "OA", etc.
}

# ENROLLMENT table: Insurance enrollment periods
# Used to verify patients have continuous coverage during observation windows
ENROLLMENT_EXPECTED = {
    "ID": pl.Utf8,  # PATID (patient identifier)
    "ENR_START_DATE": (pl.Date, pl.Utf8),  # Enrollment period start
    "ENR_END_DATE": (pl.Date, pl.Utf8),  # Enrollment period end (may be null for ongoing)
}

# DEMOGRAPHIC table: Patient demographic attributes
# Age, sex, race/ethnicity used for cohort stratification and confounding adjustment
DEMOGRAPHIC_EXPECTED = {
    "ID": pl.Utf8,  # PATID (patient identifier)
    "BIRTH_DATE": (pl.Date, pl.Utf8),  # Date of birth (for age calculation)
    "SEX": pl.Utf8,  # "M", "F", "UN", "NI", "OT"
    "RACE": pl.Utf8,  # PCORnet race codes: "01" (American Indian), "02" (Asian), etc.
    "HISPANIC": pl.Utf8,  # "Y", "N", "UN", "NI", "OT"
}

# CRITICAL_SCHEMAS: Registry of all critical table schemas
# Used by checkpoint validation to look up expected schema by table name
CRITICAL_SCHEMAS: dict[str, dict] = {
    "DIAGNOSIS": DIAGNOSIS_EXPECTED,
    "ENCOUNTER": ENCOUNTER_EXPECTED,
    "ENROLLMENT": ENROLLMENT_EXPECTED,
    "DEMOGRAPHIC": DEMOGRAPHIC_EXPECTED,
}
