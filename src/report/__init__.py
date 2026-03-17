"""Phase 6+: Assembly and Reporting — derived variables and data quality reporting.

Assembles patient-level derived variables, encounter-payer summaries, data quality metrics,
and site-level HL summary tables. These modules support analysis-ready outputs and HIPAA-
compliant reporting with small-cell suppression.

**Pipeline position:** Phase 6 (Assembly) and Phase 7+ (Reporting)
**Input:** Cleaned Parquet tables from Phase 5, Outcomes.csv code definitions
**Output:** Patient-level derived DataFrames, DQ metric aggregations, site summary tables
**Orchestrated by:** scripts/build_*.py, scripts/assemble_clean.py

**Key modules:**
- quality_report: Patient-level derived variables (age, HL subtype, region, insurance),
  DQ metric aggregation (completeness, conformance, plausibility), cleaning decisions
- encounter_payer_summary: One-row-per-patient payer summary with effective payer
  derivation, dual-eligible detection, and payer-at-treatment windows
- site_table: Per-site HL summary tables with outcomes cross-tabs and small-cell suppression
"""
