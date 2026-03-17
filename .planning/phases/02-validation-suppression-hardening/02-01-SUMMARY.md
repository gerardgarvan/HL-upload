---
phase: 02-validation-suppression-hardening
plan: 01
subsystem: validation-foundation
tags: [validation, checkpoint, config, schemas, foundation]
status: complete
completed: 2026-03-17T21:59:00Z

dependencies:
  requires: []
  provides:
    - CheckpointError exception for validation failures
    - validate_row_count, validate_no_vanish, validate_schema functions
    - CRITICAL_SCHEMAS registry for PCORnet CDM tables
    - validate_config, load_and_validate_config for path validation
  affects:
    - src/validate/ module gains checkpoint validation capability
    - src/load/config.py gains explicit path validation with startup summary
    - Future pipeline scripts can call checkpoints at phase boundaries

tech_stack:
  added:
    - "Polars native dtype checking for schema validation"
    - "pathlib-based path validation (no new dependencies)"
  patterns:
    - "Structured logging: [CHECKPOINT PASS/FAIL] phase=X table=Y"
    - "Fail-fast validation with CheckpointError exception"
    - "Strict vs tolerance validation modes (0.0 = strict, >0.0 = allow deviation)"
    - "Plain dataclass + explicit validation (avoiding over-engineering with Pydantic)"

key_files:
  created:
    - src/validate/checkpoint.py: "Checkpoint validation with row-count, no-vanish, schema checks"
    - src/validate/schemas.py: "CRITICAL_SCHEMAS registry for 4 core PCORnet tables"
  modified:
    - src/load/config.py: "Added validate_config() and load_and_validate_config()"
    - environment.yml: "Added notes for optional dependencies (pandera, pydantic)"

decisions:
  - choice: "Use plain Polars dtype dicts instead of Pandera for checkpoint validation"
    rationale: "Checkpoint validation only needs column existence and dtype checks. Pandera adds 10+ MB of dependencies for features we don't need (statistical checks, complex constraints). Plain Polars dtypes are sufficient and more maintainable for this use case."
    alternatives_considered:
      - "Pandera schemas: Too heavyweight for simple dtype checks"
      - "Pydantic for config: Over-engineering for 6 path checks"
    impact: "Zero new runtime dependencies. Pandera noted in environment.yml as optional for Phase 3 deep validation if needed."

  - choice: "Structured log format for all validation output"
    rationale: "Machine-parseable logs enable automated parsing of validation failures in CI/HPC environments. Format: [CHECKPOINT PASS/FAIL] phase=X table=Y expected=A got=B delta=C"
    impact: "All checkpoint functions print structured logs before raising exceptions. Enables log aggregation and monitoring."

  - choice: "Support both strict and tolerance modes for row-count validation"
    rationale: "Some phases (load, typing) should preserve exact row counts. Other phases (dedup) legitimately reduce rows. Tolerance parameter allows controlled loss checking."
    impact: "validate_row_count accepts tolerance parameter (0.0 = strict, >0.0 = allow deviation as fraction of expected)."

metrics:
  duration: "3 minutes"
  tasks: 2
  files_created: 2
  files_modified: 2
  commits: 2
  tests_passing: 22
---

# Phase 02 Plan 01: Validation Foundation Modules Summary

**One-liner:** Created checkpoint validation module with row-count/schema checks using plain Polars dtypes, added explicit config path validation with startup summary, zero new dependencies.

## Overview

This plan created the foundation modules for pipeline validation that Plan 03 will wire into pipeline scripts. Delivered:

1. **Checkpoint validation module** (`src/validate/checkpoint.py`) with:
   - `CheckpointError` exception for validation failures
   - `validate_row_count` with strict and tolerance modes
   - `validate_no_vanish` for catastrophic data loss detection
   - `validate_schema` with plain Polars dtype checking
   - Structured logging format for all validation output

2. **Schema registry** (`src/validate/schemas.py`) with:
   - `CRITICAL_SCHEMAS` dict for 4 core PCORnet CDM tables
   - DIAGNOSIS, ENCOUNTER, ENROLLMENT, DEMOGRAPHIC schemas
   - Dtype flexibility (Date or String for date columns)
   - Non-strict validation (extra columns allowed)

3. **Config validation** (enhanced `src/load/config.py`) with:
   - `validate_config()` for explicit path existence checking
   - `load_and_validate_config()` convenience function
   - Structured success summary block printed on validation pass
   - Clear error messages with field name and failure reason
   - Auto-creation of output directories if missing

4. **Dependency documentation** (updated `environment.yml`) with:
   - Notes for optional dependencies (pandera, pydantic)
   - Rationale for not adding them in Phase 2

## Tasks Completed

### Task 1: Create checkpoint module with row-count and schema validation

**Commit:** da3199c

**Files created:**
- `src/validate/checkpoint.py` (267 lines)
- `src/validate/schemas.py` (99 lines)

**Key implementations:**

1. **CheckpointError exception** - Raised on any validation failure. Signals that data has deviated from expected state at a phase boundary.

2. **CheckpointResult dataclass** - Captures validation metadata (phase, table, passed, expected, actual, message) for audit trail.

3. **validate_row_count()** - Primary checkpoint for detecting data loss or unexpected row count changes:
   - Strict mode (tolerance=0.0): Any difference raises error
   - Tolerance mode (tolerance>0.0): Allows deviation up to (tolerance * expected)
   - Structured log format: `[CHECKPOINT PASS/FAIL] phase=X table=Y expected=A got=B delta=C`

4. **validate_no_vanish()** - Sanity check for catastrophic data loss:
   - Ensures DataFrame has at least min_rows
   - Use when expected count unknown but baseline minimum exists

5. **validate_schema()** - Non-strict schema validation:
   - Checks expected columns exist with correct dtypes
   - Allows extra columns (for derived flags, intermediate columns)
   - Supports dtype flexibility: single type or tuple of allowed types
   - Uses plain Polars dtype comparison (pl.Utf8, pl.Date, etc.)

6. **CRITICAL_SCHEMAS registry** - Plain dict mapping table names to expected schemas:
   - DIAGNOSIS: ID, ENCOUNTERID, DX, DX_TYPE, DX_DATE
   - ENCOUNTER: ENCOUNTERID, ID, ADMIT_DATE, ENC_TYPE
   - ENROLLMENT: ID, ENR_START_DATE, ENR_END_DATE
   - DEMOGRAPHIC: ID, BIRTH_DATE, SEX, RACE, HISPANIC

**Verification:**
- All imports successful
- CheckpointError raised on validation failure (tested with invalid row count)
- CRITICAL_SCHEMAS contains 4 table schemas
- All 22 existing tests pass

### Task 2: Enhance config validation with path checking and startup summary

**Commit:** 75c393b

**Files modified:**
- `src/load/config.py` (+120 lines)
- `environment.yml` (+5 lines)

**Key implementations:**

1. **validate_config()** - Explicit filesystem checks on all paths:
   - Input paths (data_root, datastructure, valuesets): Must exist, raise ValueError if not
   - Output paths (scratch_root, parquet_dir, derived_dir): Auto-created if missing
   - Structured error format: `[CONFIG FAIL] field=path — reason`
   - Success summary block:
     ```
     ============================================================
     CONFIG VALIDATION PASSED
     ============================================================
       data_root:          /path/to/data [OK]
       scratch_root:       /path/to/scratch [OK]
       datastructure:      /path/to/datastructure.txt [OK]
       valuesets:          /path/to/valuesets.csv [OK]
       parquet_dir:        /path/to/parquet [OK]
       derived_dir:        /path/to/derived [OK]
     ============================================================
     ```

2. **load_and_validate_config()** - Single-call convenience function:
   - Combines load_config() + validate_config()
   - Recommended entry point for pipeline scripts
   - Fail-fast path validation at startup

3. **Design decision documentation** - Added inline comment explaining why plain pathlib validation chosen over Pydantic:
   - Pydantic would add runtime dependency for 6 path checks
   - Existing Paths dataclass + explicit checks sufficient
   - Avoids over-engineering

4. **Optional dependency notes** - Added to environment.yml:
   - Pandera for statistical profiling, value constraints (if Phase 3 needs it)
   - Pydantic for complex config validation (current pathlib checks sufficient)
   - Both commented out with rationale

**Verification:**
- All imports successful
- ValueError raised for invalid paths with structured error messages
- All 22 existing tests pass

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

All verification criteria from plan met:

1. CheckpointError, validate_row_count, validate_no_vanish, validate_schema importable and functional
2. CRITICAL_SCHEMAS contains 4 table schemas (DIAGNOSIS, ENCOUNTER, ENROLLMENT, DEMOGRAPHIC)
3. validate_config raises ValueError with structured message for invalid paths
4. load_and_validate_config prints success summary block when all paths valid
5. All structured log messages follow format: `[CHECKPOINT FAIL|PASS] phase=X table=Y ...`
6. No new runtime dependencies added to environment.yml (pandera and pydantic noted as optional)
7. Existing test suite passes without modification (22 tests pass)

## Impact Assessment

**Immediate:**
- Checkpoint validation module ready for use in pipeline scripts (Plan 03)
- Config validation provides fail-fast startup checking
- Zero new dependencies keeps environment simple

**Phase 02:**
- Plan 03 will wire these checkpoints into scripts/load_all.py and scripts/type_convert.py
- Plan 03 will update pipeline scripts to use load_and_validate_config()

**Future phases:**
- If Phase 3 requires deep value validation (range checks, statistical profiling), Pandera can be added then
- Checkpoint pattern established: validate_row_count, validate_no_vanish, validate_schema reusable across all phases

**Technical debt:**
- None introduced. Clean separation of concerns: checkpoint module for validation, schemas module for definitions, config module for path handling.

## Self-Check: PASSED

**Files created:**
- [x] src/validate/checkpoint.py exists
- [x] src/validate/schemas.py exists

**Files modified:**
- [x] src/load/config.py modified
- [x] environment.yml modified

**Commits exist:**
- [x] da3199c: feat(02-01): create checkpoint validation module
- [x] 75c393b: feat(02-01): add config validation with startup summary

**Imports work:**
- [x] `from src.validate.checkpoint import CheckpointError, validate_row_count, validate_no_vanish, validate_schema`
- [x] `from src.validate.schemas import CRITICAL_SCHEMAS`
- [x] `from src.load.config import validate_config, load_and_validate_config`

**Tests pass:**
- [x] All 22 existing tests pass
- [x] CheckpointError raised on validation failure (verified)
- [x] ValueError raised for invalid config paths (verified)

All artifacts present, all claims verified.
