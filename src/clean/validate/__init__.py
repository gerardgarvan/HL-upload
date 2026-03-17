"""Clean-layer validation subpackage for HL pipeline.

This package provides validation helpers used during Phase 5 (clean) by scripts/clean_all.py,
as opposed to src/validate/ which is used during Phase 3-4 (validate) by scripts/validate_all.py.

**Pipeline Position:** Phase 5 (Clean/Assembly)

**Input:** Cleaned Parquet files with deduplication and flags

**Output:** Validation results for clean-layer quality checks

**Orchestrated by:** scripts/clean_all.py

**Key modules:**
- structural: Schema and integrity checks (clean-layer context)
- cohort: HL cohort verification (clean-layer context)
- values: Value validation and flag generation (clean-layer context)

**TODO(audit): Near-duplication with src/validate/**
These modules are near-copies of src/validate/ with minor parameter differences.
This duplication is a refactoring opportunity for Phase 2/3 — consider consolidating
shared validation logic into a common library or parameterizing the phase context.
"""
