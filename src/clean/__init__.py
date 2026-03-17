"""Phase 5: Cleaning — data quality flags and cross-table consistency checks.

This package adds binary flag columns to DataFrames during the cleaning phase. Flags
include deduplication markers, partner provenance indicators, clinical diagnosis/provider
flags, and cross-table consistency checks.

**Pipeline position:** Phase 5 (Cleaning)
**Input:** Raw Parquet tables from Phase 4 (Loading)
**Output:** Cleaned Parquet tables with flag columns added
**Orchestrated by:** scripts/clean_all.py

**Key modules:**
- dedup: Composite-key duplicate detection and cross-table consistency
- harmonize: Partner provenance flags and enrollment coverage checks
- flags_diagnosis_provider: HL diagnosis, survivorship, and cancer provider flags
- outcomes_flags: Treatment modality flags from Outcomes.csv code lookup
"""
