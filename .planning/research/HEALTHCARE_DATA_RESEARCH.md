# Healthcare Data Cleaning Research: PCORnet CDM & OneFlorida+

**Domain:** Healthcare / Biomedical Research Data Cleaning
**Researched:** 2026-02-27
**Overall Confidence:** HIGH (based on official PCORnet documentation, OneFlorida+ materials, and peer-reviewed literature)

---

## Table of Contents

1. [Healthcare Data Models Overview](#1-healthcare-data-models-overview)
2. [PCORnet CDM Table Structures](#2-pcornet-cdm-table-structures)
3. [Common Data Quality Issues](#3-common-data-quality-issues)
4. [Standard Data Cleaning Pipeline](#4-standard-data-cleaning-pipeline)
5. [HIPAA/PHI Considerations](#5-hipaa-phi-considerations)
6. [Data Quality Reporting Standards](#6-data-quality-reporting-standards)
7. [SAS Date Format Handling](#7-sas-date-format-handling)
8. [OneFlorida+ Specific Context](#8-oneflorida-specific-context)

---

## 1. Healthcare Data Models Overview

### Which Model is OneFlorida+ Using?

**OneFlorida+ uses the PCORnet Common Data Model (CDM).** This is confirmed by official OneFlorida+ documentation. The current version is **PCORnet CDM v7.0** (released January 23, 2025). Data is cleaned, transformed, and curated in a centralized warehouse with quarterly refreshes following PCORI data characterization.

### The Three Major Healthcare CDMs

| Feature | PCORnet CDM | OMOP CDM | i2b2 |
|---------|-------------|----------|------|
| **Maintained by** | PCORnet / PCORI | OHDSI collaborative | Individual institutions |
| **Primary use** | Multi-center patient-centered outcomes research | Longitudinal observational research & standardized analytics | Local cohort discovery |
| **Vocabulary** | PCORnet value sets + standard codes (ICD, CPT, LOINC) | Heavily standardized vocabulary mapping | Flexible ontology-driven |
| **Architecture** | Encounter-based, strong provenance | Person-centric, concept-based | Star schema, ontology-driven |
| **Network scope** | Distributed research network | Global collaborative | Institutional |
| **OneFlorida+ usage** | **Primary data model** | Not primary | Used for cohort discovery via OneFlorida+ Front Door |

**Key insight:** OneFlorida+ stores data in PCORnet CDM format but provides i2b2 as a query/cohort discovery tool on top. Researchers accessing flat file exports will be working with PCORnet CDM-structured data.

### Why PCORnet CDM Matters for This Project

- All CSV flat files from OneFlorida+ conform to PCORnet CDM table structures
- Column names, value sets, and data types follow the CDM specification
- Understanding the CDM is essential for correct data interpretation and cleaning
- Date fields may use SAS date format (numeric days since January 1, 1960)

---

## 2. PCORnet CDM Table Structures

### Complete Table List (PCORnet CDM v6.0/v7.0)

The CDM contains **24+ tables** organized into functional groups:

#### Core Patient Tables

| Table | Description | Key Fields |
|-------|-------------|------------|
| **DEMOGRAPHIC** | Patient demographics | `PATID`, `BIRTH_DATE`, `SEX`, `RACE`, `HISPANIC`, `GENDER_IDENTITY`, `SEXUAL_ORIENTATION`, `PAT_PREF_LANGUAGE_SPOKEN`, `BIOBANK_FLAG` |
| **ENROLLMENT** | Insurance/coverage periods | `PATID`, `ENR_START_DATE`, `ENR_END_DATE`, `ENR_BASIS`, `CHART` |

#### Clinical Event Tables

| Table | Description | Key Fields |
|-------|-------------|------------|
| **ENCOUNTER** | Healthcare visits/stays | `ENCOUNTERID`, `PATID`, `ADMIT_DATE`, `DISCHARGE_DATE`, `ENC_TYPE`, `FACILITY_TYPE`, `DISCHARGE_DISPOSITION`, `DISCHARGE_STATUS`, `DRG`, `PAYER_TYPE_PRIMARY`, `PROVIDERID` |
| **DIAGNOSIS** | Diagnosis codes | `DIAGNOSISID`, `PATID`, `ENCOUNTERID`, `DX`, `DX_TYPE`, `DX_SOURCE`, `DX_ORIGIN`, `DX_DATE`, `DX_POA`, `PDX`, `ENC_TYPE`, `ADMIT_DATE` |
| **PROCEDURES** | Clinical procedures | `PROCEDURESID`, `PATID`, `ENCOUNTERID`, `PX`, `PX_TYPE`, `PX_DATE`, `PX_SOURCE`, `PPX` |
| **CONDITION** | Problem list / medical history | `CONDITIONID`, `PATID`, `ENCOUNTERID`, `CONDITION`, `CONDITION_TYPE`, `CONDITION_STATUS`, `CONDITION_SOURCE`, `ONSET_DATE`, `REPORT_DATE`, `RESOLVE_DATE` |
| **VITAL** | Vital signs | `VITALID`, `PATID`, `ENCOUNTERID`, `MEASURE_DATE`, `HT`, `WT`, `DIASTOLIC`, `SYSTOLIC`, `ORIGINAL_BMI`, `BP_POSITION`, `SMOKING`, `TOBACCO`, `TOBACCO_TYPE` |
| **DEATH** | Mortality information | `PATID`, `DEATH_DATE`, `DEATH_DATE_IMPUTE`, `DEATH_SOURCE`, `DEATH_MATCH_CONFIDENCE` |
| **DEATH_CAUSE** | Causes of death | `PATID`, `DEATH_CAUSE`, `DEATH_CAUSE_CODE`, `DEATH_CAUSE_TYPE`, `DEATH_CAUSE_SOURCE` |

#### Medication Tables

| Table | Description | Key Fields |
|-------|-------------|------------|
| **PRESCRIBING** | Medication orders | `PRESCRIBINGID`, `PATID`, `ENCOUNTERID`, `RX_ORDER_DATE`, `RX_ORDER_TIME`, `RXNORM_CUI`, `RX_DAYS_SUPPLY`, `RX_REFILLS`, `RX_DOSE_ORDERED`, `RX_DOSE_ORDERED_UNIT`, `RX_FREQUENCY`, `RX_BASIS`, `RX_QUANTITY` |
| **DISPENSING** | Pharmacy dispensing | `DISPENSINGID`, `PATID`, `PRESCRIBINGID`, `DISPENSE_DATE`, `NDC`, `DISPENSE_SUP`, `DISPENSE_AMT`, `DISPENSE_DOSE_DISP`, `DISPENSE_DOSE_DISP_UNIT`, `DISPENSE_ROUTE` |
| **MED_ADMIN** | Medication administration | `MEDADMINID`, `PATID`, `ENCOUNTERID`, `MEDADMIN_CODE`, `MEDADMIN_TYPE`, `MEDADMIN_START_DATE`, `MEDADMIN_STOP_DATE`, `MEDADMIN_DOSE_ADMIN`, `MEDADMIN_DOSE_ADMIN_UNIT`, `MEDADMIN_ROUTE` |
| **EXTERNAL_MEDS** | External medications (new in v7.0) | Patient-reported or externally recorded medications |

#### Laboratory & Observations

| Table | Description | Key Fields |
|-------|-------------|------------|
| **LAB_RESULT_CM** | Lab results (common measures) | `LAB_RESULT_CM_ID`, `PATID`, `ENCOUNTERID`, `LAB_LOINC`, `LAB_LOINC_SOURCE`, `RESULT_NUM`, `RESULT_QUAL`, `RESULT_UNIT`, `RESULT_MODIFIER`, `NORM_RANGE_LOW`, `NORM_RANGE_HIGH`, `ABN_IND`, `SPECIMEN_DATE`, `SPECIMEN_SOURCE`, `RESULT_DATE`, `LAB_ORDER_DATE`, `LAB_PX`, `LAB_PX_TYPE`, `LAB_RESULT_SOURCE`, `RESULT_LOC` |
| **LAB_HISTORY** | Historical lab reference ranges | `LABHISTORYID`, `LAB_LOINC`, `LAB_FACILITYID`, `RESULT_UNIT`, `NORM_RANGE_LOW`, `NORM_RANGE_HIGH`, `PERIOD_START`, `PERIOD_END` |
| **OBS_CLIN** | Clinical observations | Non-standard clinical observations |
| **OBS_GEN** | General observations | General/non-clinical observations |
| **PRO_CM** | Patient-reported outcomes | Patient-reported outcome measures |

#### Other Tables

| Table | Description | Key Fields |
|-------|-------------|------------|
| **IMMUNIZATION** | Vaccination records | `IMMUNIZATIONID`, `PATID`, `ENCOUNTERID`, `VX_CODE`, `VX_CODE_TYPE`, `VX_ADMIN_DATE`, `VX_DOSE`, `VX_MANUFACTURER`, `VX_STATUS` |
| **PROVIDER** | Provider information | `PROVIDERID`, `PROVIDER_SEX`, `PROVIDER_SPECIALTY_PRIMARY`, `PROVIDER_NPI_FLAG` |
| **PCORNET_TRIAL** | Clinical trial enrollment | Trial participation records |
| **HARVEST** | Datamart metadata | CDM version, refresh dates, date management strategies, network identifiers |
| **HASH_TOKEN** | Privacy-preserving linkage | Encrypted tokens for cross-site matching |
| **LDS_ADDRESS_HISTORY** | Limited data set addresses | `ADDRESSID`, `PATID`, `ADDRESS_CITY`, `ADDRESS_STATE`, `ADDRESS_ZIP5`, `ADDRESS_ZIP9`, `ADDRESS_PERIOD_START`, `ADDRESS_PERIOD_END` |
| **PAT_RELATIONSHIP** | Patient relationships (new in v7.0) | Familial/caregiver relationships |

### Key Linking Relationships

```
DEMOGRAPHIC.PATID ──┬──> ENROLLMENT.PATID
                    ├──> ENCOUNTER.PATID ──┬──> DIAGNOSIS.ENCOUNTERID
                    ├──> DIAGNOSIS.PATID   ├──> PROCEDURES.ENCOUNTERID
                    ├──> PROCEDURES.PATID  ├──> VITAL.ENCOUNTERID
                    ├──> VITAL.PATID       ├──> LAB_RESULT_CM.ENCOUNTERID
                    ├──> LAB_RESULT_CM.PATID├──> PRESCRIBING.ENCOUNTERID
                    ├──> PRESCRIBING.PATID ├──> MED_ADMIN.ENCOUNTERID
                    ├──> DISPENSING.PATID  ├──> CONDITION.ENCOUNTERID
                    ├──> CONDITION.PATID   ├──> OBS_CLIN.ENCOUNTERID
                    ├──> DEATH.PATID       ├──> OBS_GEN.ENCOUNTERID
                    ├──> DEATH_CAUSE.PATID └──> IMMUNIZATION.ENCOUNTERID
                    ├──> MED_ADMIN.PATID
                    ├──> IMMUNIZATION.PATID
                    └──> LDS_ADDRESS_HISTORY.PATID

PRESCRIBING.PRESCRIBINGID ──> DISPENSING.PRESCRIBINGID
PRESCRIBING.PRESCRIBINGID ──> MED_ADMIN.PRESCRIBINGID
```

### PCORnet CDM Value Set Encoding

Most categorical fields use short coded values (typically 2 characters). Common patterns:

| Code | Meaning (typical) |
|------|--------------------|
| `NI` | No Information |
| `UN` | Unknown |
| `OT` | Other |
| `Y` | Yes |
| `N` | No |

**ENC_TYPE (Encounter Type):**
| Code | Meaning |
|------|---------|
| `AV` | Ambulatory Visit |
| `ED` | Emergency Department |
| `EI` | ED-to-Inpatient |
| `IP` | Inpatient Hospital Stay |
| `IS` | Non-Acute Institutional Stay |
| `OA` | Other Ambulatory Visit |
| `OS` | Observation Stay |
| `IC` | Institutional Professional Consult |
| `TH` | Telehealth |

**DX_TYPE (Diagnosis Code Type):**
| Code | Meaning |
|------|---------|
| `09` | ICD-9-CM |
| `10` | ICD-10-CM |
| `11` | ICD-11-CM |
| `SM` | SNOMED CT |
| `OT` | Other |

**PX_TYPE (Procedure Code Type):**
| Code | Meaning |
|------|---------|
| `09` | ICD-9-PCS |
| `10` | ICD-10-PCS |
| `CH` | CPT/HCPCS |
| `LC` | LOINC |
| `OT` | Other |

---

## 3. Common Data Quality Issues

### 3.1 Missing Data Patterns

Missing data in healthcare datasets is rarely random. Understanding the missingness mechanism is critical for valid analysis.

#### Types of Missingness

| Type | Description | Example in Healthcare Data | Impact |
|------|-------------|---------------------------|--------|
| **MCAR** (Missing Completely at Random) | Missingness unrelated to any variable | Random system glitches dropping records | Least biased; safe to exclude |
| **MAR** (Missing at Random) | Missingness depends on observed variables | Lab results missing because patient was too sick to come to outpatient visit (sickness observed via encounter type) | Can be addressed with imputation |
| **MNAR** (Missing Not at Random) | Missingness depends on the missing value itself | Extremely high BMI not recorded because nurse didn't measure; death date missing because death was unreported | Most dangerous; requires sensitivity analysis |

#### Common Missing Data Patterns in PCORnet CDM

| Field/Table | Expected Missingness | Likely Mechanism | Notes |
|-------------|---------------------|------------------|-------|
| `RACE`, `HISPANIC` | 10-30% | MAR/MNAR | Historically under-collected; varies by site; may be systematically missing for certain populations |
| `DISCHARGE_DATE` | Expected for AV/OA encounters | Structural | Ambulatory visits don't have discharge dates by design |
| `LAB_RESULT_CM.RESULT_NUM` | Variable | MAR | Qualitative results (POSITIVE/NEGATIVE) stored in `RESULT_QUAL` instead |
| `DX_POA` (Present on Admission) | Common for non-IP | Structural | Only relevant for inpatient encounters |
| `DEATH_DATE` | High | MNAR | Many deaths occur outside healthcare system; NDI linkage incomplete |
| `ONSET_DATE` in CONDITION | Very high | Structural | Rarely reliably captured; onset vs. report date confusion |
| `DISPENSING` records | Variable | MAR | Depends on payer data availability; cash-pay prescriptions typically missing |
| `GENDER_IDENTITY`, `SEXUAL_ORIENTATION` | Very high (>80%) | MNAR/Structural | Recently added to EHR systems; collection varies dramatically by site |

#### Sentinel Values for Missing Data

PCORnet CDM uses specific codes to distinguish types of missing data:

| Code | Meaning | How to Handle |
|------|---------|---------------|
| `NI` | No Information — data not available | Treat as missing |
| `UN` | Unknown — asked but not known | Treat as missing, but note it was collected |
| `OT` | Other — doesn't fit categories | May contain useful info in `RAW_*` fields |
| NULL / empty | Not populated | True missing |

**Critical cleaning step:** Do NOT conflate `NI`, `UN`, `OT`, and true NULL. They carry different meanings for missingness analysis.

### 3.2 Date Inconsistencies

Date errors are among the most impactful data quality issues because they affect temporal ordering, which is fundamental to clinical research (e.g., exposure must precede outcome).

#### Common Date Problems

| Issue | Detection Rule | Example | Severity |
|-------|---------------|---------|----------|
| **Discharge before admission** | `DISCHARGE_DATE < ADMIT_DATE` | Admit: 2023-05-15, Discharge: 2023-05-10 | Critical |
| **Future dates** | `DATE > current_date` | Lab result dated 2030-01-01 | Critical |
| **Dates before birth** | `EVENT_DATE < BIRTH_DATE` | Diagnosis recorded before patient was born | Critical |
| **Dates after death** | `EVENT_DATE > DEATH_DATE` | Encounter after death date | Critical (may indicate bad death date OR data entry after death) |
| **Impossible birth dates** | `BIRTH_DATE` implies age > 120 or < 0 | Birth in 1850 | Critical |
| **Zero-day admissions** | `DISCHARGE_DATE = ADMIT_DATE` for IP | Same-day inpatient discharge | Suspicious (may be valid for same-day surgery) |
| **Date truncation** | Month/day set to 01 | All dates in a period are YYYY-01-01 | Moderate (check `HARVEST` table date management strategy) |
| **SAS epoch issues** | Dates near 1960-01-01 or showing as large integers | Raw numeric value not converted | Critical |

#### Date Management Strategies (HARVEST Table)

The PCORnet CDM HARVEST table documents how each site manages dates. The `*_DATE_MGMT` fields indicate:

| Code | Strategy |
|------|----------|
| `01` | Complete date stored |
| `02` | Month and year only (day = 01) |
| `03` | Year only (month = 01, day = 01) |

**Always check the HARVEST table first** to understand whether apparent date issues are actually intentional date truncation for de-identification.

### 3.3 Code Validation

#### ICD-10-CM Diagnosis Codes

| Check | Rule | Example Invalid |
|-------|------|----------------|
| Format | Letter followed by 2+ digits, optional decimal | `123.45` (no leading letter), `Z.1` (incomplete) |
| Length | 3-7 characters (excluding decimal) | `A0` (too short) |
| Valid prefix | First character: A-Z (excluding U) | `U99.9` (reserved for provisional codes) |
| Valid code | Cross-reference against CMS ICD-10-CM code set | `Z99.99` (verify exists in reference table) |
| Version appropriateness | ICD-10 effective Oct 1, 2015; ICD-9 before | ICD-10 code with date before 2015-10-01 |
| Decimal placement | Should include decimal after 3rd character for >3 char codes | `E119` should be `E11.9` |

#### CPT/HCPCS Procedure Codes

| Check | Rule |
|-------|------|
| CPT format | 5 digits (Category I) or 4 digits + letter (Category III) |
| HCPCS format | Letter + 4 digits |
| Valid range | CPT: 00100-99499; HCPCS: A0000-V9999 |
| Modifier format | 2 characters appended |

#### NDC (National Drug Code)

| Check | Rule |
|-------|------|
| Format | 11 digits, no dashes (HIPAA standard) |
| Segment structure | 5-4-2 (labeler-product-package) |
| Leading zeros | Must be preserved |
| Cross-reference | Validate against FDA NDC Directory |

#### LOINC Codes

| Check | Rule |
|-------|------|
| Format | 3-7 characters, hyphen before check digit (e.g., `2345-7`) |
| Check digit | Last digit after hyphen is a Mod 10 check digit |
| No leading zeros | LOINC codes should NOT be zero-padded |
| Cross-reference | Validate against LOINC database from Regenstrief Institute |

#### RxNorm CUI

| Check | Rule |
|-------|------|
| Format | Numeric identifier |
| Cross-reference | Validate against NLM RxNorm database |
| Active status | Verify code is not retired/obsolete |

### 3.4 Duplicate Records

#### Types of Duplicates in Healthcare Data

| Type | Description | Detection Method |
|------|-------------|------------------|
| **Exact duplicates** | Identical rows across all fields | Hash all columns, find duplicate hashes |
| **Near-duplicates** | Same event, slight differences (e.g., different time stamps) | Match on `PATID` + date + key clinical field |
| **Cross-site duplicates** | Same patient at multiple institutions in the network | `HASH_TOKEN` table for privacy-preserving linkage |
| **Encounter fragmentation** | Single visit split into multiple encounter records | Same `PATID` + overlapping dates + same facility |

#### PCORnet-Specific Duplicate Patterns

| Table | Common Duplicate Pattern | Detection Key |
|-------|------------------------|---------------|
| DIAGNOSIS | Same DX code recorded multiple times per encounter | `PATID` + `ENCOUNTERID` + `DX` + `DX_TYPE` |
| LAB_RESULT_CM | Duplicate lab results from interface duplication | `PATID` + `LAB_LOINC` + `SPECIMEN_DATE` + `RESULT_NUM` |
| PRESCRIBING | Renewal vs. new order confusion | `PATID` + `RXNORM_CUI` + `RX_ORDER_DATE` |
| ENCOUNTER | ED + IP recorded separately AND as EI | `PATID` + `ADMIT_DATE` + facility overlap |

#### Deduplication Strategy

1. **Preserve original data** — never delete from source; flag duplicates
2. **Create dedup flags** — add `IS_DUPLICATE` column
3. **Priority rules** — when keeping one record from a duplicate set:
   - Prefer records with more complete data
   - Prefer records with encounter linkage
   - Prefer records from EHR source over claims source
4. **Document decisions** — record deduplication logic for reproducibility

### 3.5 Impossible/Implausible Values

#### Demographic Checks

| Check | Rule | Action |
|-------|------|--------|
| Negative age | `AGE < 0` (calculated from `BIRTH_DATE`) | Flag; likely date error |
| Extreme age | `AGE > 120` | Flag; likely date error |
| Sex-specific diagnoses | Male patient with pregnancy diagnosis | Flag; may indicate sex coding error or transgender patient |
| Deceased with future encounters | Active encounters after `DEATH_DATE` | Flag; review death date accuracy |

#### Vital Signs Plausibility

| Measure | Biologically Implausible Range | Suspicious Range |
|---------|-------------------------------|------------------|
| Height (HT) | < 0 or > 108 inches (274 cm) | < 20 or > 96 inches (for adults) |
| Weight (WT) | < 0 or > 1500 lbs (680 kg) | < 50 or > 700 lbs (for adults) |
| Systolic BP | < 40 or > 300 mmHg | < 70 or > 250 mmHg |
| Diastolic BP | < 20 or > 200 mmHg | < 40 or > 150 mmHg |
| BMI | < 5 or > 100 kg/m² | < 10 or > 80 kg/m² |
| Systolic < Diastolic | `SYSTOLIC < DIASTOLIC` | Always invalid |

#### Lab Results Plausibility

| Lab Test (LOINC) | Unit | Biologically Implausible | Notes |
|-------------------|------|------------------------|-------|
| Hemoglobin A1c (4548-4) | % | < 2 or > 25 | Normal: 4-6% |
| Serum Creatinine (2160-0) | mg/dL | < 0 or > 50 | Normal: 0.7-1.3 |
| Blood Glucose (2345-7) | mg/dL | < 0 or > 2000 | Normal: 70-100 fasting |
| Total Cholesterol (2093-3) | mg/dL | < 0 or > 1000 | Normal: < 200 |
| WBC Count (6690-2) | 10*3/uL | < 0 or > 500 | Normal: 4.5-11.0 |
| Hemoglobin (718-7) | g/dL | < 0 or > 30 | Normal: 12-17.5 |
| Platelet Count (777-3) | 10*3/uL | < 0 or > 2000 | Normal: 150-400 |
| Serum Sodium (2951-2) | mmol/L | < 100 or > 200 | Normal: 136-145 |
| Serum Potassium (2823-3) | mmol/L | < 1 or > 15 | Normal: 3.5-5.0 |
| ALT/SGPT (1742-6) | U/L | < 0 or > 20000 | Normal: 7-56 |
| eGFR (33914-3) | mL/min/1.73m² | < 0 or > 200 | Normal: > 90 |

**Important:** Unit mismatches cause many "implausible" values. A glucose of 5.5 is normal in mmol/L but extremely low in mg/dL. Always check `RESULT_UNIT` before flagging outliers.

---

## 4. Standard Data Cleaning Pipeline

### Phase 0: Pre-Processing & Intake

```
Step 0.1: File Inventory
  - Catalog all CSV files received
  - Map filenames to PCORnet CDM tables
  - Document file sizes, row counts, column counts
  - Verify expected tables are present

Step 0.2: Schema Validation
  - Compare column names against PCORnet CDM specification
  - Identify CDM version from HARVEST table
  - Check for unexpected extra columns (may be RAW_ fields)
  - Verify data types (string vs numeric vs date)

Step 0.3: SAS Date Conversion (if applicable)
  - Identify date columns stored as numeric SAS dates
  - Convert: actual_date = January 1, 1960 + numeric_value days
  - Validate converted dates fall in reasonable range
```

### Phase 1: Structural Validation

```
Step 1.1: Primary Key Integrity
  - Verify uniqueness of ID fields (PATID, ENCOUNTERID, DIAGNOSISID, etc.)
  - Check for NULL primary keys
  - Verify PATID exists in DEMOGRAPHIC for all tables

Step 1.2: Foreign Key Integrity
  - Verify ENCOUNTERID references exist in ENCOUNTER table
  - Verify PRESCRIBINGID links in DISPENSING/MED_ADMIN
  - Verify PROVIDERID references exist in PROVIDER table
  - Document orphan records (valid events without encounter linkage)

Step 1.3: Row-Level Completeness
  - Calculate % NULL for every column in every table
  - Compare against PCORnet CDM required/optional field specification
  - Flag columns with unexpected 100% missing or 100% populated
```

### Phase 2: Value-Level Validation

```
Step 2.1: Coded Field Validation
  - Validate ENC_TYPE values against PCORnet value sets
  - Validate DX_TYPE, PX_TYPE against allowed values
  - Validate SEX, RACE, HISPANIC against value sets
  - Check for values not in specification (may indicate older CDM version)

Step 2.2: Clinical Code Validation
  - Validate ICD-9/ICD-10 codes against reference code sets
  - Validate CPT/HCPCS codes against CMS reference
  - Validate NDC codes against FDA NDC Directory
  - Validate LOINC codes against Regenstrief LOINC database
  - Validate RxNorm CUIs against NLM RxNorm

Step 2.3: Numeric Range Checks
  - Apply vital signs plausibility ranges
  - Apply lab result plausibility ranges (LOINC-specific)
  - Check medication doses against typical ranges
  - Flag negative values in fields requiring positive numbers
```

### Phase 3: Temporal Validation

```
Step 3.1: Date Range Checks
  - No dates before data trust start (OneFlorida+: ~2012)
  - No dates in the future
  - No event dates before BIRTH_DATE
  - No event dates after DEATH_DATE (with tolerance window)

Step 3.2: Date Consistency Checks
  - DISCHARGE_DATE >= ADMIT_DATE
  - SPECIMEN_DATE <= RESULT_DATE (lab specimen before result)
  - RX_ORDER_DATE <= DISPENSE_DATE
  - ONSET_DATE <= REPORT_DATE (for conditions)
  - MEDADMIN_STOP_DATE >= MEDADMIN_START_DATE

Step 3.3: ICD Version-Date Concordance
  - ICD-9 codes should have dates before October 1, 2015
  - ICD-10 codes should have dates on/after October 1, 2015
  - Flag mismatches (may indicate mapping issues)

Step 3.4: Length of Stay Plausibility
  - Calculate LOS = DISCHARGE_DATE - ADMIT_DATE
  - Flag extremely long stays (> 365 days) for review
  - Flag zero-day IP stays (valid for some situations)
```

### Phase 4: Cross-Table Consistency

```
Step 4.1: Demographic Consistency
  - One DEMOGRAPHIC record per PATID
  - SEX consistent across all encounters for a patient
  - BIRTH_DATE consistent across all records for a patient
  - RACE/HISPANIC shouldn't change (if they do, investigate)

Step 4.2: Encounter-Event Alignment
  - Diagnosis dates should fall within encounter date range
  - Procedure dates should fall within encounter date range
  - Lab specimen dates should be near encounter date
  - Vital sign dates should match encounter date

Step 4.3: Clinical Plausibility
  - Sex-specific procedure/diagnosis alignment
  - Age-appropriate diagnoses (pediatric vs adult conditions)
  - Medication-diagnosis alignment (optional, complex)
  - Death record consistency with discharge disposition
```

### Phase 5: Duplicate Detection & Resolution

```
Step 5.1: Exact Duplicate Detection
  - Hash all non-ID columns per table
  - Identify and flag exact duplicate rows

Step 5.2: Near-Duplicate Detection
  - Per-table matching on clinical key (see Section 3.4)
  - Review and adjudicate near-duplicates

Step 5.3: Patient-Level Deduplication
  - Check for multiple PATIDs that may be same person
  - Use HASH_TOKEN if available for cross-site linkage
```

### Phase 6: Data Quality Reporting

```
Step 6.1: Generate Completeness Report
  - Per-table, per-field completeness percentages
  - Highlight fields below expected thresholds

Step 6.2: Generate Plausibility Report
  - Count and percentage of implausible values per field
  - Distribution summaries (min, max, mean, median, IQR)

Step 6.3: Generate Conformance Report
  - Invalid code counts per coded field
  - Date validation failure counts

Step 6.4: Generate Summary Dashboard
  - Overall data quality score
  - Table-by-table quality summary
  - Action items for issues requiring resolution
```

### Phase 7: Data Transformation & Output

```
Step 7.1: Apply Cleaning Rules
  - Set implausible values to NULL (with flag column)
  - Standardize date formats
  - Resolve duplicates (flag, don't delete)
  - Standardize units where possible

Step 7.2: Create Analytic Variables
  - Calculate AGE from BIRTH_DATE and reference date
  - Calculate LENGTH_OF_STAY from encounter dates
  - Create time-to-event variables as needed
  - Create categorical age groups

Step 7.3: Export Clean Dataset
  - Write cleaned data with quality flags
  - Maintain audit trail of all changes
  - Document exclusion criteria applied
```

---

## 5. HIPAA/PHI Considerations

### What is PHI?

Protected Health Information (PHI) includes any individually identifiable health information. HIPAA defines **18 identifiers** that constitute PHI:

| # | Identifier | PCORnet CDM Relevance |
|---|-----------|----------------------|
| 1 | Names | Not in standard CDM (only in PRIVATE tables) |
| 2 | Geographic data (smaller than state) | `FACILITY_LOCATION` (ZIP), `ADDRESS_*` fields |
| 3 | Dates (except year) | `BIRTH_DATE`, `ADMIT_DATE`, `DEATH_DATE`, all event dates |
| 4 | Telephone numbers | Not in CDM |
| 5 | Fax numbers | Not in CDM |
| 6 | Email addresses | Not in CDM |
| 7 | Social Security numbers | Not in CDM |
| 8 | Medical record numbers | `PATID` is a pseudoidentifier, not the real MRN |
| 9 | Health plan beneficiary numbers | Not in standard CDM |
| 10 | Account numbers | Not in CDM |
| 11 | Certificate/license numbers | Not in CDM |
| 12 | Vehicle identifiers | Not in CDM |
| 13 | Device identifiers | Not in CDM |
| 14 | Web URLs | Not in CDM |
| 15 | IP addresses | Not in CDM |
| 16 | Biometric identifiers | Not in CDM |
| 17 | Full-face photographs | Not in CDM |
| 18 | Any unique identifying number | `PATID` (pseudoidentifier), `ENCOUNTERID` |

### De-Identification Methods

#### Safe Harbor Method
Remove all 18 identifiers. For dates, only retain year. For geography, truncate ZIP to first 3 digits (or remove if population < 20,000). Simple but reduces data utility significantly.

#### Expert Determination Method
A qualified statistical expert determines re-identification risk is "very small." Allows retaining more granular data (month-level dates, sub-state geography). Preferred for research but requires formal risk assessment.

### Handling OneFlorida+ Data

**The data you receive from OneFlorida+ is likely a Limited Data Set (LDS) or de-identified dataset.** Key considerations:

1. **PATID is a pseudoidentifier** — has a consistent crosswalk to the true identifier retained by the data partner, but is not the real MRN. Still treat it as sensitive.

2. **Dates are retained** — LDS data retains full dates (unlike Safe Harbor). This is critical for longitudinal analysis but means the data contains PHI under HIPAA.

3. **Geographic data** — `FACILITY_LOCATION` and `LDS_ADDRESS_HISTORY` may contain ZIP codes. The CDM separates sensitive geographic data into LDS-specific tables vs. PRIVATE tables.

4. **PRIVATE tables** (`PRIVATE_DEMOGRAPHIC`, `PRIVATE_ADDRESS_HISTORY`) contain more identifying information and require higher security.

### Practical Requirements for Researchers

| Requirement | Action |
|-------------|--------|
| **Data Use Agreement (DUA)** | Must be in place before receiving data |
| **IRB Approval** | Must have active IRB protocol |
| **Secure Storage** | Use HiPerGator secure research partition; no local copies |
| **Access Control** | Only authorized team members access data |
| **No Re-identification** | Never attempt to link PATID back to real identifiers |
| **Minimum Necessary** | Only request/use data elements needed for research |
| **Small Cell Suppression** | Suppress counts < 11 (OneFlorida+ policy) in reports/publications |
| **Secure Disposal** | Delete data when study concludes per DUA terms |
| **Encryption** | Encrypt data at rest and in transit |
| **Audit Trail** | Log who accessed data and when |
| **No Sharing** | Do not share raw data outside approved team |

### HiPerGator-Specific Security

- Use the `/blue` or `/orange` secure storage partitions
- Do NOT store PHI on `/home` directories (backed up, potentially accessible)
- Use SLURM job submissions rather than interactive sessions when possible
- Ensure HIPAA security training is current for all team members
- Follow UF IRB and Privacy Office requirements

---

## 6. Data Quality Reporting Standards

### PCORnet's Four-Dimension Framework

PCORnet evaluates data quality across four dimensions in a two-stage curation process:

#### Stage 1: Foundational Checks

| Dimension | What It Measures | Examples |
|-----------|-----------------|----------|
| **Conformance** | Does data adhere to CDM standards? | Column names match spec, value sets are valid, data types correct |
| **Completeness** | Are expected data elements populated? | % NULL per field, diagnosis code alignment, expected record counts |
| **Plausibility** | Do values make logical sense? | No negative ages, vitals in range, dates in order |
| **Persistence** | Are records stable across refreshes? | Records don't disappear between quarterly data loads |

#### Stage 2: Study-Specific Assessment

The PCORnet Coordinating Center examines data patterns for key variables within specific studies or populations. This targets fitness-for-use rather than generic quality.

### Recommended Data Quality Report Structure

```markdown
# Data Quality Report: [Study Name]
## Date: [Date]
## Data Source: OneFlorida+ PCORnet CDM v[X]

### 1. Data Overview
- Total patients: [N]
- Date range: [start] to [end]
- Tables received: [list]
- CDM version: [from HARVEST]

### 2. Completeness Summary
| Table | Total Records | Key Field | % Complete |
|-------|--------------|-----------|------------|
| DEMOGRAPHIC | N | RACE | X% |
| ENCOUNTER | N | ENC_TYPE | X% |
| ... | ... | ... | ... |

### 3. Conformance Summary
| Table | Field | Invalid Values | % Invalid |
|-------|-------|---------------|-----------|
| DIAGNOSIS | DX_TYPE | N | X% |
| ... | ... | ... | ... |

### 4. Plausibility Summary
| Check | Records Flagged | % of Total |
|-------|----------------|------------|
| Future dates | N | X% |
| Discharge before admission | N | X% |
| Negative age | N | X% |
| Implausible vitals | N | X% |
| Implausible lab values | N | X% |

### 5. Duplicate Summary
| Table | Exact Duplicates | Near Duplicates |
|-------|-----------------|-----------------|
| DIAGNOSIS | N | N |
| LAB_RESULT_CM | N | N |

### 6. Cross-Table Consistency
| Check | Issues Found | % of Records |
|-------|-------------|--------------|
| Orphan encounters | N | X% |
| Date-code version mismatch | N | X% |
| Sex-diagnosis mismatch | N | X% |

### 7. Recommendations
- [List of action items]
- [Exclusion criteria to apply]
- [Variables requiring caution in analysis]
```

### Kahn Framework (Widely Adopted)

The Kahn et al. harmonized data quality framework (used by both PCORnet and OHDSI) defines:

| Category | Subcategory | Definition |
|----------|-------------|------------|
| **Conformance** | Value | Values conform to specified standards |
| | Relational | Data maintain specified relational constraints |
| | Computational | Computed values conform to expectations |
| **Completeness** | — | Expected data are present |
| **Plausibility** | Uniqueness | Expected unique values are indeed unique |
| | Atemporal | Values, distributions, and densities agree with expectations |
| | Temporal | Time-varying values change as expected over time |

### Metrics to Track

| Metric | Formula | Target |
|--------|---------|--------|
| Field completeness | `(non-null count / total count) × 100` | Varies by field |
| Value conformance | `(valid values / total non-null values) × 100` | > 95% |
| Referential integrity | `(valid FK references / total FK values) × 100` | > 99% |
| Temporal consistency | `(logically ordered dates / total date pairs) × 100` | > 99% |
| Duplicate rate | `(duplicate records / total records) × 100` | < 1% |
| Plausibility pass rate | `(values in range / total values) × 100` | > 99% |

---

## 7. SAS Date Format Handling

### How SAS Dates Work

SAS stores dates as **integer values representing the number of days since January 1, 1960** (the SAS epoch).

| SAS Numeric Value | Actual Date |
|-------------------|-------------|
| 0 | January 1, 1960 |
| 1 | January 2, 1960 |
| -1 | December 31, 1959 |
| 365 | December 31, 1960 |
| 22280 | December 31, 2020 |
| 23741 | December 31, 2024 |
| 24106 | December 31, 2025 |

### Converting SAS Dates in Python

```python
import pandas as pd
from datetime import datetime, timedelta

SAS_EPOCH = datetime(1960, 1, 1)

def sas_date_to_datetime(sas_numeric):
    """Convert SAS numeric date to Python datetime."""
    if pd.isna(sas_numeric):
        return pd.NaT
    return SAS_EPOCH + timedelta(days=int(sas_numeric))

# For a pandas DataFrame column:
df['BIRTH_DATE'] = df['BIRTH_DATE_RAW'].apply(sas_date_to_datetime)

# Vectorized approach (faster for large datasets):
df['BIRTH_DATE'] = pd.to_timedelta(df['BIRTH_DATE_RAW'], unit='D') + pd.Timestamp('1960-01-01')
```

### Converting SAS Dates in R

```r
# SAS dates are days since 1960-01-01
sas_to_date <- function(sas_numeric) {
  as.Date(sas_numeric, origin = "1960-01-01")
}

df$BIRTH_DATE <- sas_to_date(df$BIRTH_DATE_RAW)
```

### SAS Datetime Values

SAS datetimes are stored as **seconds since midnight, January 1, 1960**. If you see very large numbers (>100,000), the field may be a datetime rather than a date.

```python
def sas_datetime_to_datetime(sas_numeric):
    """Convert SAS numeric datetime to Python datetime."""
    if pd.isna(sas_numeric):
        return pd.NaT
    return SAS_EPOCH + timedelta(seconds=int(sas_numeric))
```

### How to Detect SAS Date Columns

1. **Column is numeric** but CDM spec says it should be a date
2. **Values are in the range ~18,000-25,000** for recent healthcare data (2009-2028)
3. **No decimal points** (dates are integers; datetimes may have decimals)
4. **Column name ends in `_DATE`** but dtype is int/float

### Validation After Conversion

After converting SAS dates, verify:
- No dates before the data trust start (~2012 for OneFlorida+)
- No dates in the far future
- Dates make clinical sense (BIRTH_DATE is before all other dates for the patient)
- Converted dates align with known anchor points (if available)

---

## 8. OneFlorida+ Specific Context

### Scale of Data

| Metric | Approximate Value |
|--------|-------------------|
| Patient records | ~26 million |
| Data history | From 2012 to present |
| Dispensed medications | ~960 million |
| Procedures | ~2.3 billion |
| Diagnoses | ~2 billion |
| Geographic coverage | Florida (primary), plus AL, GA, CA, AR, MN |
| Data sources | EHR + Medicaid claims |
| Refresh cadence | Quarterly |

### Data Sources

OneFlorida+ integrates data from:
- **Electronic Health Records (EHR)** — from University of Florida Health, AdventHealth, and other health systems
- **Medicaid claims** — Florida Medicaid data providing insurance encounter data
- **Exposome data** — natural, built, and social environmental data linked to patient records

### Known Data Quality Characteristics

1. **Medications and lab results** are the primary sources of data quality issues across PCORnet sites
2. **Cross-site variability** is significant — different health systems have different EHR configurations, coding practices, and data capture completeness
3. **Medicaid claims data** has different completeness patterns than EHR data (e.g., claims may have better prescription coverage, EHR may have better clinical detail)
4. **Demographic data corrections** may take 4-7 days to stabilize after initial entry
5. **Discharge information** may also take several days to be finalized in the source system
6. **Small cell suppression** — any reported cell with count < 11 must be suppressed per OneFlorida+ policy

### HiPerGator Computing Environment

For processing large OneFlorida+ datasets on UF's HiPerGator:

| Consideration | Recommendation |
|---------------|----------------|
| **Memory** | Request sufficient RAM for large CSVs; use chunked reading for files > available RAM |
| **Storage** | Use `/blue` partition for working data; follow HIPAA requirements |
| **Processing** | Use pandas with `chunksize` parameter or Dask/Polars for datasets that exceed memory |
| **File format** | Consider converting CSV to Parquet after initial cleaning for faster subsequent reads |
| **Job scheduling** | Use SLURM batch jobs for long-running cleaning pipelines |
| **Python environment** | Use conda environments to manage dependencies; HiPerGator has module system |

---

## Sources and References

### Official Documentation
- PCORnet Common Data Model v7.0 Specification: https://pcornet.org/data/common-data-model/
- PCORnet CDM v6.0 Table Schemas: https://data-models-service.research.chop.edu/models/pcornet/6.0.0
- PCORnet CDM Data Quality Validation Guide: https://pcornet.org/news/resources-common-data-model-cdm-data-quality-validation/
- OneFlorida+ Clinical Research Network: https://onefloridaconsortium.org/
- OneFlorida+ Data Trust: http://onefl.net/data/
- OneFlorida+ Data Quality Statement: https://onefl.net/data/data-quality-statement/

### HIPAA & De-Identification
- HHS HIPAA De-Identification Guidance: https://www.hhs.gov/hipaa/for-professionals/privacy/special-topics/de-identification/index.html
- 45 CFR § 164.514: https://ecfr.io/cgi-bin/text-idx?mc=true&node=se45.2.164_1514&rgn=div8

### Data Quality Frameworks
- Kahn et al. "A Harmonized Data Quality Assessment Terminology and Framework" (EGEMS, 2016)
- PCORnet Data Curation Query Package: https://github.com/PCORnet-DRN-OC/PCORnet-Data-Curation
- Sentinel Data Quality Metrics: https://sentinelinitiative.org/

### Clinical Coding Standards
- LOINC (Regenstrief Institute): https://loinc.org/
- ICD-10-CM (CMS): https://www.cms.gov/medicare/coding-billing/icd-10-codes
- NDC Directory (FDA): https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory
- RxNorm (NLM): https://www.nlm.nih.gov/research/umls/rxnorm/

### SAS Date Handling
- SAS Date, Time, and Datetime Values: https://support.sas.com/documentation/cdl/en/lrcon/62955/HTML/default/a002200738.htm

### Peer-Reviewed Literature
- "Evaluating Foundational Data Quality in PCORnet" (JAMIA, 2018): https://ncbi.nlm.nih.gov/pmc/articles/PMC5983028/
- "Challenges for Data Quality in the Clinical Data Life Cycle" (JMIR, 2025): https://www.jmir.org/2025/1/e60709
- "Common data models and data standards for tabular health data" (BMC Med Inform, 2025): https://link.springer.com/article/10.1186/s12911-025-03267-2
- "Data quality assessment in healthcare: dimensions, methods and tools" (BMC Med Inform, 2025): https://link.springer.com/article/10.1186/s12911-025-03136-y
