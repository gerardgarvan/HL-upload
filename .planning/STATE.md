# Project State

## Current Position
- **Current Phase:** 02-csv-to-parquet-conversion
- **Current Plan:** 01 complete (1/1 plans done)
- **Status:** phase-complete
- **Last session:** 2026-02-27T16:53:00Z
- **Stopped at:** Completed 02-01-PLAN.md (CSV-to-Parquet conversion module + entry point)

## Progress

```
Phase 1: ████░░░░░░░░░░░░░░░░ 1/2 plans (50%)
Phase 2: ████████████████████ 1/1 plans (100%)
Overall: ████░░░░░░░░░░░░░░░░ 2/? plans
```

## Decisions
- Extended Paths dataclass with parquet_dir field; output section optional with sensible default
- Copied schema.py directly from HL-EDA without modification
- SLURM template uses 4 CPUs (up from 2) for Polars auto-parallelization
- environment.yml is a draft spec; real export generated on HPC after mamba install
- Single unified loop for all 22 tables; auto-detection handles TUMOR_REGISTRY format differences
- Three date formats: SAS DATE9. (%d%b%Y), SAS DATETIME (%d%b%Y:%H:%M:%S), NAACCR YYYYMMDD (%Y%m%d)
- No .str.to_uppercase() before %b parsing — chrono is case-insensitive
- encoding=utf8-lossy for CSV reads to handle non-UTF-8 characters

## Blockers
None.

## Performance Metrics

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 01    | 01   | ~8min    | 2     | 10    |
| 02    | 01   | ~6min    | 2     | 2     |
