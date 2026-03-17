"""Validation layer for HL pipeline.

This package handles Phase 3-4 of the pipeline: structural and value validation
of typed Parquet files. Verifies schema conformance, referential integrity,
cohort inclusion, and value plausibility before cleaning and derivation.

**Pipeline Position:** Phase 3-4 (Validation)

**Input:** Typed Parquet files from parquet_dir (Phase 2 output)

**Output:** Validation reports (markdown, CSV), flag columns added to DataFrames

**Orchestrated by:** scripts/validate_all.py

**Key modules:**
- structural: Schema comparison, PATID/ENCOUNTERID integrity, completeness profiling
- cohort: HL cohort verification (149 ICD codes, dual-date methods, enrollment cross-check)
- values: Value-set conformance, vital/lab plausibility, ICD-date concordance, temporal checks
"""
