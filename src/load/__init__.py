"""Data loading layer for HL pipeline.

This package handles Phase 2 of the pipeline: CSV-to-Parquet conversion with
automatic date detection and type coercion. Converts raw OneFlorida+ PCORnet
CDM CSV files to typed Parquet for efficient downstream processing.

**Pipeline Position:** Phase 2 (Loading)

**Input:** Raw CSV files from data_root (OneFlorida+ extracts)

**Output:** Typed Parquet files in parquet_dir with date columns properly converted

**Orchestrated by:** scripts/convert_all.py

**Key modules:**
- config: Path configuration loader (reads config/paths.toml)
- schema: Manifest parser and file verification
- convert: CSV-to-Parquet conversion with date detection (3 format support)
"""
