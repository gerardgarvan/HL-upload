# Phase 2: Validation & Suppression Hardening - Research

**Researched:** 2026-03-17
**Domain:** Python data validation, checkpoint patterns, HIPAA suppression, configuration validation
**Confidence:** HIGH

## Summary

Phase 2 hardens the existing 5-phase Polars-based clinical data pipeline by adding validation checkpoints at phase boundaries to catch silent failures (lost rows, schema drift, bad config), and centralizing HIPAA-compliant small-cell suppression. The pipeline processes 22 OneFlorida+ PCORnet CDM tables through: convert (CSV→Parquet) → validate (structural) → clean (dedup/flags) → assemble (patient-level + reports) → insurance summary.

Research confirms that Pandera is the industry standard for Polars DataFrame validation (0.19.0+ with native Polars support), checkpoint validation follows fail-fast patterns (raise exceptions on violations, no warning-only mode), and HIPAA small-cell suppression standards recommend thresholds of 10-11 with primary suppression only for most use cases. The codebase already has validation infrastructure (`src/validate/structural.py`) and two suppression functions (`_suppress()` for CSV, `flag_small_cell()` for markdown), but they're duplicated across 4+ files and lack centralization.

Configuration validation best practices emphasize early validation at startup (fail fast before any processing), using Pydantic for type-safe validation with clear error messages, and leveraging pathlib for path validation. Row-count validation in data pipelines typically uses either full accounting (expected = input rows) or no-vanish checks (output ≥ minimum threshold), with structured logging for checkpoint failures to enable parsing in HPC/batch contexts.

**Primary recommendation:** Use Pandera for schema validation with lazy evaluation optimization, implement a centralized checkpoint module with structured error messages (`[CHECKPOINT FAIL] phase=X table=Y expected=N got=M delta=D`), centralize suppression into a single configurable utility (default threshold=10, per-report override capability), and add Pydantic-based config validation that runs upfront before any pipeline processing.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Failure behavior:**
- All checkpoint failures are **hard stops** — row-count violations, schema violations, and config errors all raise exceptions and halt the pipeline immediately
- No warning-only mode — if data integrity is compromised, nothing proceeds
- Config validation runs **upfront before any processing** — fail fast at the very start, no partial runs from bad config

**Suppression centralization:**
- Zero counts (0) are displayed as-is — 0 reveals no individual and is safe
- **Primary suppression only** — no complementary suppression. Most reports don't have row/column totals requiring back-calculation protection
- Threshold is **per-report configurable** — default threshold (10) with ability for reports to override

**Reporting & visibility:**
- Checkpoint failure messages use **structured log format**: `[CHECKPOINT FAIL] phase=X table=Y expected=N got=M delta=D`
- Config validation on startup **prints a summary on success** — confirms tables found, paths verified, settings loaded

### Claude's Discretion

- **Cleanup on failure** — Claude decides whether to clean up partial outputs or leave them for debugging, based on what's most practical
- **Checkpoint placement** — Claude identifies which phase boundaries are most at risk for silent data loss and places checkpoints accordingly
- **Checkpoint implementation** — Claude decides whether checkpoints are embedded in scripts or implemented as a separate validation layer, based on existing codebase structure
- **Row-count validation approach** — Claude picks the check approach (full accounting vs. no-vanish) that best matches data correctness goals
- **Schema validation approach** — Claude decides whether schema expectations are hardcoded or snapshot-based, based on PCORnet CDM evolution patterns
- **Suppression centralization strategy** — Claude picks whether to use a single utility function or post-processing pass, based on how current report code is structured
- **Successful checkpoint logging** — whether successful checkpoint passes are also logged (audit trail consideration)
- **Suppression audit format** — whether suppression audit produces a standalone report or log entries

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VAL-01 | Row-count validation at each phase boundary to detect silent record loss | **Standard Stack:** Custom checkpoint module with structured logging; **Patterns:** Fail-fast validation, full accounting vs no-vanish checks; **Don't Hand-Roll:** Use existing Polars row-count operations, not manual counting |
| VAL-02 | Schema validation (expected columns and dtypes) after each phase writes output | **Standard Stack:** Pandera 0.19.0+ with Polars support; **Patterns:** Lazy validation with deferred collect(), hardcoded schemas for stable tables, snapshot schemas for evolving tables; **Pitfalls:** Avoid validating every table exhaustively (PCORnet has 22 tables but only ~8 critical for correctness) |
| VAL-03 | Configuration validation on load — fail fast with clear errors for missing files or bad paths | **Standard Stack:** Pydantic BaseSettings for config validation, pathlib for path checking; **Patterns:** Validate at startup before processing, print success summary, use type annotations for paths (Path not str); **Pitfalls:** Avoid silent fallbacks to defaults when required paths missing |
| VAL-04 | Centralized small-cell suppression — single `_suppress()` function, single threshold constant, audit of all report outputs for HIPAA compliance | **Standard Stack:** Single utility module with configurable threshold; **Architecture:** Primary suppression only (no complementary), per-report threshold override capability; **Pitfalls:** HIPAA standards vary (3-20 range), but 10 is most defensible middle ground for mixed sensitivity data |

</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pandera | 0.19.0+ | DataFrame schema validation | Industry standard for Polars validation (native support added 0.19.0), lazy evaluation support, type-safe schemas, comprehensive check system |
| Pydantic | 2.0+ | Config validation | Best-in-class runtime validation with type annotations, precise error messages, BaseSettings for config management, already widely adopted |
| Polars | Current | DataFrame operations | Already core to pipeline; native row-count and schema introspection |
| pathlib | stdlib | Path validation | Python standard library; exists(), is_file(), resolve() methods for path checking |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 24.0+ | Structured logging | Optional — only if upgrading from print() to proper logging; not required if keeping print-based progress output |
| tomllib/tomli | stdlib/3.11+ | TOML parsing | Already used in `src/load/config.py` for config/paths.toml |
| dataclasses | stdlib | Type-safe data structures | Already used in `Paths` dataclass; extend for checkpoint results |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pandera | Great Expectations | GE is framework-heavy (200+ MB) and designed for enterprise pipelines with web UIs; overkill for 5-phase batch pipeline. Pandera is lightweight (~10 MB) and code-first |
| Pandera | Manual schema checks | Manual checks lack standardization and miss edge cases (null handling, dtype coercion). Pandera has 7+ years of battle-testing |
| Pydantic | Manual config validation | Manual validation is error-prone and lacks good error messages. Pydantic provides field validators, path validation, and clear error output |
| Centralized suppression | Status quo (duplicated functions) | Current codebase has `_suppress()` duplicated in 4 files with same threshold. Single source of truth prevents drift |

**Installation:**

Pandera is not currently in `environment.yml`. Add to conda dependencies:

```bash
# Add to environment.yml
dependencies:
  - pandera>=0.19.0  # Polars support

# Or install via pip
pip install "pandera[polars]>=0.19.0"
```

Pydantic is not currently in `environment.yml`. Add to dependencies:

```bash
# Add to environment.yml pip section
pip:
  - pydantic>=2.0
```

## Architecture Patterns

### Pattern 1: Checkpoint Module with Fail-Fast Validation

**What:** Centralized validation checkpoint at phase boundaries that raises on violations

**When to use:** After every phase that writes output (convert → validate → clean → assemble)

**Structure:**
```python
# src/validate/checkpoint.py

from dataclasses import dataclass
from pathlib import Path
import polars as pl

@dataclass
class CheckpointResult:
    """Result of a validation checkpoint."""
    phase: str
    table: str
    passed: bool
    expected: int | None
    actual: int | None
    message: str

class CheckpointError(Exception):
    """Raised when validation checkpoint fails."""
    pass

def validate_row_count(
    df: pl.DataFrame,
    phase: str,
    table: str,
    expected: int,
    tolerance: float = 0.0,
) -> CheckpointResult:
    """Validate DataFrame row count matches expected.

    Args:
        df: DataFrame to validate
        phase: Pipeline phase name (e.g., "convert", "clean")
        table: Table name (e.g., "DIAGNOSIS")
        expected: Expected row count
        tolerance: Acceptable deviation (0.0 = exact match, 0.01 = 1%)

    Returns:
        CheckpointResult with validation outcome

    Raises:
        CheckpointError: If row count outside tolerance
    """
    actual = df.height
    delta = abs(actual - expected)
    pct_delta = delta / expected if expected > 0 else float('inf')

    if pct_delta > tolerance:
        msg = f"[CHECKPOINT FAIL] phase={phase} table={table} expected={expected} got={actual} delta={delta}"
        print(msg)
        raise CheckpointError(msg)

    return CheckpointResult(
        phase=phase,
        table=table,
        passed=True,
        expected=expected,
        actual=actual,
        message=f"[CHECKPOINT PASS] phase={phase} table={table} rows={actual}"
    )
```

**Why this works:**
- Structured error format enables parsing in HPC/batch logs
- Raises exception to halt pipeline immediately (fail-fast requirement)
- CheckpointResult dataclass enables optional success logging for audit trail
- Tolerance parameter supports "no-vanish" checks (tolerance=1.0 means any positive count passes)

### Pattern 2: Pandera Schema Validation with Lazy Evaluation

**What:** Define Pandera schemas for critical tables, validate after phase writes output

**When to use:** After convert, clean, and assemble phases for high-risk tables (DIAGNOSIS, ENCOUNTER, ENROLLMENT)

**Example:**
```python
# src/validate/schemas.py
import pandera.polars as pa
import polars as pl

# Hardcoded schema for stable CDM table
DIAGNOSIS_SCHEMA = pa.DataFrameSchema(
    {
        "ID": pa.Column(pl.Utf8, nullable=False),
        "ENCOUNTERID": pa.Column(pl.Utf8, nullable=True),
        "DX": pa.Column(pl.Utf8, nullable=False),
        "DX_DATE": pa.Column(pl.Date, nullable=True),
        "DX_TYPE": pa.Column(pl.Utf8, nullable=False, checks=pa.Check.isin(["09", "10", "11", "SM"])),
    },
    strict=False,  # Allow extra columns (flags, derived cols)
)

def validate_schema(df: pl.LazyFrame, schema: pa.DataFrameSchema, table: str) -> pl.LazyFrame:
    """Validate schema and return LazyFrame for continued processing.

    Args:
        df: LazyFrame to validate
        schema: Pandera schema to check against
        table: Table name for error messages

    Returns:
        Validated LazyFrame (chain-able)

    Raises:
        pa.errors.SchemaError: If validation fails
    """
    try:
        # Pandera validates without .collect() for metadata checks
        # Only collects if data value checks are needed
        validated = schema.validate(df, lazy=True)
        print(f"  [SCHEMA OK] {table}: {len(schema.columns)} columns validated")
        return validated
    except pa.errors.SchemaError as e:
        print(f"  [SCHEMA FAIL] {table}: {e}")
        raise
```

**Source:** [Data Validation with Polars - Pandera documentation](https://pandera.readthedocs.io/en/latest/polars.html)

**Why this works:**
- Pandera leverages Polars lazy API to avoid premature .collect() operations
- Schema validation catches type degradation (e.g., Date columns converted to Utf8 during processing)
- `strict=False` allows derived columns (flags, cleaning decisions) without schema updates
- DX_TYPE value check prevents invalid ICD version codes

### Pattern 3: Pydantic Config Validation at Startup

**What:** Replace manual TOML loading with Pydantic BaseSettings for type-safe validation

**When to use:** At the top of every pipeline script's main() before any processing

**Example:**
```python
# src/load/config.py (enhanced)
from pydantic import BaseModel, field_validator, ConfigDict
from pathlib import Path
import tomllib

class PathsConfig(BaseModel):
    """Type-safe configuration with validation."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    data_root: Path
    scratch_root: Path
    datastructure_path: Path
    valuesets_path: Path
    parquet_dir: Path
    derived_dir: Path

    @field_validator('data_root', 'scratch_root', 'datastructure_path', 'valuesets_path')
    @classmethod
    def path_must_exist(cls, v: Path) -> Path:
        if not v.exists():
            raise ValueError(f"Path does not exist: {v}")
        return v

    @field_validator('datastructure_path', 'valuesets_path')
    @classmethod
    def must_be_file(cls, v: Path) -> Path:
        if not v.is_file():
            raise ValueError(f"Path is not a file: {v}")
        return v

def load_config_validated(config_path: Path | None = None) -> PathsConfig:
    """Load and validate config with clear error messages.

    Fails fast if paths missing or invalid, prints success summary.

    Raises:
        FileNotFoundError: If config file missing
        ValidationError: If paths invalid or missing
    """
    root = Path(__file__).resolve().parents[2]
    path = config_path or (root / "config" / "paths.toml")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # Resolve paths before validation
    p = raw["paths"]
    # ... path resolution logic ...

    config = PathsConfig(
        data_root=data_root,
        scratch_root=scratch_root,
        # ... other fields ...
    )

    # Print success summary per user requirement
    print("=" * 60)
    print("CONFIG VALIDATION PASSED")
    print("=" * 60)
    print(f"  data_root:          {config.data_root} ✓")
    print(f"  scratch_root:       {config.scratch_root} ✓")
    print(f"  datastructure:      {config.datastructure_path} ✓")
    print(f"  valuesets:          {config.valuesets_path} ✓")
    print(f"  Tables to process:  {len(parse_datastructure(config.datastructure_path)[1])}")
    print("=" * 60)

    return config
```

**Source:** [A simple guide to configure your Python project with Pydantic and a YAML file](https://medium.com/@jonathan_b/a-simple-guide-to-configure-your-python-project-with-pydantic-and-a-yaml-file-bef76888f366)

**Why this works:**
- Pydantic validates paths at construction time (fail fast)
- Field validators provide clear error messages ("Path does not exist: /path/to/missing")
- Success summary confirms setup before long pipeline runs (user requirement)
- Type-safe: config.data_root is Path, not str (prevents string path bugs)

### Pattern 4: Centralized Suppression with Configurable Threshold

**What:** Single suppression utility with default threshold and per-report override

**When to use:** All report generation (CSV, markdown, figures)

**Example:**
```python
# src/report/suppression.py
"""HIPAA-compliant small-cell suppression utilities.

Clinical rationale: HIPAA Safe Harbor method requires suppressing
small cell counts (typically ≤10) to prevent re-identification.

Threshold of 10 is recommended by CMS Cell Suppression Policy and
Washington State DOH standards for mixed-sensitivity healthcare data.

References:
- CMS Cell Size Suppression Policy (https://www.hhs.gov/guidance/document/cms-cell-suppression-policy)
- WA DOH Small Numbers Standards (threshold: <10)
"""

# Default threshold per HIPAA Safe Harbor and CMS guidance
DEFAULT_THRESHOLD = 10

def suppress(value: int, threshold: int = DEFAULT_THRESHOLD, zero_safe: bool = True) -> str:
    """Apply primary suppression to small cell counts.

    Args:
        value: Count to evaluate for suppression
        threshold: Suppression threshold (default: 10)
        zero_safe: If True, 0 is never suppressed (default: True)

    Returns:
        "-" if value in [1, threshold], otherwise str(value)

    Examples:
        >>> suppress(0)
        "0"
        >>> suppress(5)
        "-"
        >>> suppress(11)
        "11"
        >>> suppress(5, threshold=20)
        "-"
    """
    if zero_safe and value == 0:
        return str(value)
    if 1 <= value <= threshold:
        return "-"
    return str(value)

def flag_small_cell(value: int, threshold: int = DEFAULT_THRESHOLD) -> str:
    """Flag small cells for internal QC reports (shows value with warning).

    Used in markdown reports where analysts need to see actual counts
    but be warned of suppression requirements for publication.

    Args:
        value: Count to evaluate
        threshold: Warning threshold (default: 10)

    Returns:
        Value with "⚠" marker if in [1, threshold], otherwise str(value)
    """
    if 1 <= value <= threshold:
        return f"{value} ⚠"
    return str(value)

def audit_suppression(df: pl.DataFrame, count_col: str, threshold: int = DEFAULT_THRESHOLD) -> dict:
    """Audit how many cells would be suppressed in a report.

    Args:
        df: DataFrame with count column
        count_col: Name of column containing counts
        threshold: Suppression threshold

    Returns:
        Dict with keys: total_cells, suppressed_cells, pct_suppressed
    """
    counts = df[count_col].to_list()
    total = len(counts)
    suppressed = sum(1 for c in counts if 1 <= c <= threshold)

    return {
        "total_cells": total,
        "suppressed_cells": suppressed,
        "pct_suppressed": round(100 * suppressed / total, 1) if total > 0 else 0.0,
    }
```

**Sources:**
- [CMS Cell Size Suppression Policy](https://www.hhs.gov/guidance/document/cms-cell-suppression-policy)
- [WA DOH Standards for Reporting Data with Small Numbers](https://www.doh.wa.gov/portals/1/documents/1500/smallnumbers.pdf)

**Why this works:**
- Single source of truth for threshold (currently duplicated in 4 files)
- Per-report override via `threshold` parameter
- `zero_safe=True` per user requirement (0 reveals no individual)
- Two functions support different use cases (suppress for publication, flag for internal QC)
- `audit_suppression()` enables compliance reporting

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DataFrame schema validation | Custom column/dtype checks | Pandera | Schema validation has 100+ edge cases (null handling, dtype coercion, nullable vs required, value constraints). Pandera is battle-tested since 2018 with 7+ years of bug fixes |
| Config validation | Manual dict parsing with try/except | Pydantic | Config validation needs clear error messages, type coercion, path resolution, optional vs required fields. Pydantic provides all this with field validators and BaseSettings |
| SHA256 hashing | Manual read+hash loops | hashlib.file_digest() | Python 3.11+ has `file_digest()` that handles chunking automatically. Manual implementations often miss edge cases (large files, memory limits) |
| Row count validation | Manual df.height checks scattered across scripts | Centralized checkpoint module | Scattered checks lack consistent error format, logging, and tolerance handling. Checkpoint module ensures all phase boundaries use same validation logic |

**Key insight:** Data validation is deceptively complex. Schema validation alone requires handling nullable columns, dtype coercion (Utf8 vs Categorical), value constraints (enums, ranges), cross-column dependencies, and clear error messages. Pandera has solved these problems over 7 years of development. Building custom validation means re-discovering the same edge cases.

## Common Pitfalls

### Pitfall 1: Validating Too Much (Exhaustive Schema Checks)

**What goes wrong:** Attempting to validate all 22 PCORnet CDM tables with full column schemas causes maintenance burden when CDM evolves

**Why it happens:** Defensive programming instinct says "validate everything." But PCORnet CDM updates annually with new columns, and not all tables are equally critical to correctness.

**How to avoid:** Prioritize schema validation for high-risk tables:
- **Critical (validate exhaustively):** DIAGNOSIS (cohort definition), ENCOUNTER (referential integrity), ENROLLMENT (coverage), DEMOGRAPHIC (patient identification)
- **Important (validate key columns only):** PROCEDURES, VITAL, LAB_RESULT_CM (check ID, date, code columns exist and are correct type)
- **Low-risk (validate existence only):** TUMOR_REGISTRY, OBS_CLIN, PRO_CM (rarely used, frequently have schema variations)

**Warning signs:** Schema validation breaking frequently with CDM updates, validation taking >10% of pipeline runtime

**Source:** [Data Validation Libraries for Polars (2025 Edition)](https://posit-dev.github.io/pointblank/blog/validation-libs-2025/) — "The most mature data teams often use more than one of these tools, each placed deliberately in the pipeline"

### Pitfall 2: Silent Fallbacks in Config Validation

**What goes wrong:** Config validation silently uses defaults when required paths are missing, causing pipeline to run with wrong data and fail cryptically later

**Why it happens:** Defensive coding tries to keep pipeline running, defaulting to "reasonable" values when config is incomplete

**How to avoid:** Fail fast and fail loud at startup. Use Pydantic's field validation to raise clear errors immediately:
```python
# BAD: Silent fallback
data_root = config.get("data_root", "/default/path")  # May not exist!

# GOOD: Explicit validation
@field_validator('data_root')
def path_must_exist(cls, v: Path) -> Path:
    if not v.exists():
        raise ValueError(f"data_root does not exist: {v}")
    return v
```

**Warning signs:** Pipeline failing 10+ minutes into run with "FileNotFoundError", cryptic path resolution errors

**Source:** [Best Practices for Working with Configuration in Python Applications](https://tech.preferred.jp/en/blog/working-with-configuration-in-python/) — "Validate the configuration as soon as possible after program startup, and exit immediately if it is found to be invalid"

### Pitfall 3: Checkpoint Placement After Lazy Operations

**What goes wrong:** Placing checkpoint validation on LazyFrame before .collect() means validation runs BEFORE data is processed, not after

**Why it happens:** Misunderstanding Polars lazy evaluation — checkpoints on `pl.LazyFrame` validate query plan, not data

**How to avoid:** Checkpoint validation must run on collected DataFrames:
```python
# BAD: Validates query plan, not data
lazy_df = pl.scan_parquet("input.parquet").filter(...)
validate_row_count(lazy_df, ...)  # WRONG: LazyFrame has no .height

# GOOD: Validates actual processed data
df = pl.scan_parquet("input.parquet").filter(...).collect()
validate_row_count(df, ...)  # Correct: DataFrame has .height
```

**Warning signs:** Checkpoint passing but output file has wrong row count, validation always reporting "expected" count even when data changes

### Pitfall 4: HIPAA Threshold Too Low or Too High

**What goes wrong:**
- **Too low (threshold < 5):** High suppression rate (>30% of cells) makes reports unusable
- **Too high (threshold > 20):** False sense of security — re-identification risk remains for small populations

**Why it happens:** No universal HIPAA threshold exists. Standards vary from 3 (HIV/AIDS data) to 20 (Canadian standards)

**How to avoid:**
- Use **threshold=10** as defensible middle ground for mixed-sensitivity data (CMS policy, WA DOH standard)
- For highly sensitive data (HIV, mental health, substance abuse): Use threshold=11 or higher
- For low-sensitivity aggregate data: Consider threshold=5
- Document threshold choice and rationale in code comments

**Warning signs:** >40% of report cells suppressed (threshold too high), regulatory audit flags potential re-identification risk (threshold too low)

**Source:** [Less than five is less than ideal: replacing the "less than 5 cell size" rule with a risk-based data disclosure protocol](https://pmc.ncbi.nlm.nih.gov/articles/PMC7501321/) — "The most common minimum cell size in practice is 5, which implies that the maximum probability of re-identifying a record is 1/5, or 0.2"

## Code Examples

Verified patterns from official sources:

### Row Count Validation with Structured Logging

```python
# Source: Fail-fast validation pattern
# https://medium.com/towards-data-engineering/fail-fast-or-quarantine-two-data-quality-patterns-every-spark-engineer-should-know-111598f31ada

def validate_phase_boundary(
    input_df: pl.DataFrame,
    output_df: pl.DataFrame,
    phase: str,
    table: str,
    allow_loss: bool = False,
) -> None:
    """Validate no silent row loss at phase boundary.

    Args:
        input_df: Input DataFrame before processing
        output_df: Output DataFrame after processing
        phase: Phase name (e.g., "clean", "dedup")
        table: Table name
        allow_loss: If True, allow row loss but require explicit documentation

    Raises:
        CheckpointError: If row count decreased unexpectedly
    """
    input_count = input_df.height
    output_count = output_df.height
    delta = output_count - input_count

    if delta < 0 and not allow_loss:
        msg = (
            f"[CHECKPOINT FAIL] phase={phase} table={table} "
            f"expected={input_count} got={output_count} delta={delta}\n"
            f"  Row loss detected: {abs(delta)} records lost\n"
            f"  If intentional (dedup/filter), set allow_loss=True"
        )
        print(msg)
        raise CheckpointError(msg)
    elif delta < 0 and allow_loss:
        print(f"  [CHECKPOINT NOTE] {table}: {abs(delta)} rows removed (expected)")
    elif delta > 0:
        print(f"  [CHECKPOINT NOTE] {table}: {delta} rows added (derived columns?)")
    else:
        print(f"  [CHECKPOINT PASS] {table}: {output_count} rows preserved")
```

### Pandera Schema with Custom Checks

```python
# Source: Data Validation with Polars - Pandera documentation
# https://pandera.readthedocs.io/en/latest/polars.html

import pandera.polars as pa
import polars as pl

# Schema with custom value constraints
ENCOUNTER_SCHEMA = pa.DataFrameSchema(
    {
        "ENCOUNTERID": pa.Column(pl.Utf8, nullable=False, unique=True),
        "ID": pa.Column(pl.Utf8, nullable=False),
        "ADMIT_DATE": pa.Column(pl.Date, nullable=True),
        "DISCHARGE_DATE": pa.Column(pl.Date, nullable=True),
        "ENC_TYPE": pa.Column(
            pl.Utf8,
            nullable=False,
            checks=pa.Check.isin(["IP", "EI", "ED", "AV", "OA", "OS", "IS", "IC"])
        ),
    },
    checks=[
        # Cross-column validation: DISCHARGE_DATE >= ADMIT_DATE
        pa.Check(
            lambda df: (
                df.filter(pl.col("ADMIT_DATE").is_not_null() & pl.col("DISCHARGE_DATE").is_not_null())
                .select(pl.col("DISCHARGE_DATE") >= pl.col("ADMIT_DATE"))
                .to_series()
                .all()
            ),
            error="DISCHARGE_DATE must be >= ADMIT_DATE"
        )
    ],
    strict=False,  # Allow extra columns (flags, derived)
)

def validate_encounters(df: pl.LazyFrame) -> pl.LazyFrame:
    """Validate ENCOUNTER schema with date logic checks."""
    return ENCOUNTER_SCHEMA.validate(df, lazy=True)
```

### Config Validation with Path Checks

```python
# Source: Robust Configuration Loading with TOML and Pydantic
# https://gist.github.com/Ytosko/284827f449d604845ca36583e0dc5d1a

from pydantic import BaseModel, field_validator, ValidationError
from pathlib import Path

class PipelineConfig(BaseModel):
    """Pipeline configuration with path validation."""
    data_root: Path
    scratch_root: Path
    parquet_dir: Path

    @field_validator('data_root', 'scratch_root')
    @classmethod
    def dir_must_exist(cls, v: Path) -> Path:
        """Validate directory exists and is accessible."""
        if not v.exists():
            raise ValueError(f"Directory does not exist: {v}")
        if not v.is_dir():
            raise ValueError(f"Path is not a directory: {v}")
        return v

    @field_validator('parquet_dir')
    @classmethod
    def create_if_missing(cls, v: Path) -> Path:
        """Create output directory if it doesn't exist."""
        v.mkdir(parents=True, exist_ok=True)
        return v

try:
    config = PipelineConfig(
        data_root=Path("/path/to/data"),
        scratch_root=Path("/path/to/scratch"),
        parquet_dir=Path("/path/to/output"),
    )
    print("✓ Config validated successfully")
except ValidationError as e:
    print("✗ Config validation failed:")
    print(e)
    sys.exit(1)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual schema checks (if "ID" not in df.columns) | Pandera declarative schemas | Pandera 0.19.0 (2024) added Polars support | Reduces boilerplate, catches more edge cases (nulls, dtypes, value constraints) |
| Print-based validation messages | Structured logging (JSON, key=value) | 2020s shift to observability | Enables parsing logs in batch/HPC contexts, integration with monitoring tools |
| Single global threshold (SMALL_CELL_THRESHOLD=10) | Per-report configurable threshold with default | 2020s HIPAA guidance evolution | Allows high-sensitivity reports to use stricter threshold (11-20) while keeping default at 10 for general use |
| Pandas-only validation (Great Expectations) | Multi-backend validation (Pandera, Pointblank) | 2024-2025 Polars adoption surge | Pandera and Pointblank now support Polars natively, matching Polars performance characteristics |

**Deprecated/outdated:**
- **Great Expectations for small pipelines:** GE is designed for enterprise data platforms with web UIs, orchestration, and 100+ data sources. For a 5-phase batch pipeline, it's 200+ MB of overhead with features you won't use. Modern recommendation: Use Pandera for type-safe pipelines, Pointblank for stakeholder reporting.
- **MD5/SHA1 for data integrity:** Both have known collision vulnerabilities and are deprecated for security use in 2026. Use SHA256 (NIST-recommended) for HIPAA/SOC 2 compliance.
- **Complementary suppression for all reports:** Older HIPAA guidance recommended complementary (secondary) suppression to prevent back-calculation from row/column totals. Modern practice: Use primary suppression only for reports without totals (most clinical reports), reserve complementary for cross-tabulated tables with margins.

## Open Questions

### 1. Should row-count validation use strict accounting or tolerance-based checks?

**What we know:**
- Full accounting (output = input) catches all row loss
- Tolerance-based (output ≥ 95% of input) allows expected losses (dedup, filtering)
- Current codebase: No systematic row-count validation at phase boundaries

**What's unclear:** Do cleaning phases intentionally remove rows (dedup, consistency checks), or should all phases preserve row count?

**Recommendation:** Use strict accounting for convert/validate phases (expect no row loss), tolerance-based for clean phase (allow documented row loss from dedup/consistency). Document expected loss in each script's main() docstring.

### 2. Should schema expectations be hardcoded or snapshot-based?

**What we know:**
- Hardcoded schemas catch regressions but require maintenance when CDM evolves
- Snapshot schemas (record current schema, validate against snapshot) adapt automatically but don't catch semantic changes
- PCORnet CDM updates annually with new columns and value sets

**What's unclear:** How frequently does the OneFlorida+ CDM schema change? Are changes additive (new columns) or breaking (column renames, type changes)?

**Recommendation:** Use **hybrid approach**: Hardcode schemas for critical columns (ID, date columns, code columns), use snapshot validation for full schema. This catches breaking changes while tolerating additive changes.

### 3. Should successful checkpoint passes be logged for audit trail?

**What we know:**
- User requirement: Checkpoint failures use structured log format
- Structured logging enables parsing for monitoring/alerting
- HPC jobs may run for hours; success logging aids debugging

**What's unclear:** Does logging every successful checkpoint create log noise, or is it valuable audit trail?

**Recommendation:** Log successful checkpoints at INFO level (not ERROR), structured format: `[CHECKPOINT PASS] phase=X table=Y rows=N`. Enables audit trail without log noise. Add CLI flag `--quiet` to suppress success logs if needed.

## Sources

### Primary (HIGH confidence)

- [Pandera Polars Documentation](https://pandera.readthedocs.io/en/latest/polars.html) - Official Pandera docs for Polars validation
- [Pandera 0.19.0: Polars DataFrame Validation](https://www.union.ai/blog-post/pandera-0-19-0-polars-dataframe-validation) - Announcement of native Polars support
- [CMS Cell Size Suppression Policy](https://www.hhs.gov/guidance/document/cms-cell-suppression-policy) - Federal guidance on small-cell suppression
- [WA DOH Standards for Reporting Data with Small Numbers](https://www.doh.wa.gov/portals/1/documents/1500/smallnumbers.pdf) - State health department suppression standards
- [Polars Testing Documentation](https://docs.pola.rs/py-polars/html/reference/testing.html) - Official Polars assert functions

### Secondary (MEDIUM confidence)

- [Fail Fast or Quarantine? Two Data Quality Patterns](https://medium.com/towards-data-engineering/fail-fast-or-quarantine-two-data-quality-patterns-every-spark-engineer-should-know-111598f31ada) - Checkpoint validation patterns
- [Data Validation Libraries for Polars (2025 Edition)](https://posit-dev.github.io/pointblank/blog/validation-libs-2025/) - Comparison of validation tools
- [Best Practices for Working with Configuration in Python Applications](https://tech.preferred.jp/en/blog/working-with-configuration-in-python/) - Config validation patterns
- [Robust Configuration Loading with TOML and Pydantic](https://gist.github.com/Ytosko/284827f449d604845ca36583e0dc5d1a) - Pydantic config examples
- [Less than five is less than ideal: replacing the "less than 5 cell size" rule](https://pmc.ncbi.nlm.nih.gov/articles/PMC7501321/) - Research on suppression thresholds

### Tertiary (LOW confidence - requires verification)

- [Data Validation with Pandera in Python](https://towardsdatascience.com/data-validation-with-pandera-in-python-f07b0f845040/) - General Pandera introduction (pre-Polars support)
- [5 Python Data Validation Libraries You Should Be Using](https://www.kdnuggets.com/5-python-data-validation-libraries-you-should-be-using) - Library comparison (needs date verification)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Pandera 0.19.0+ Polars support is documented and released, Pydantic is industry standard for config validation
- Architecture: HIGH - Checkpoint patterns, fail-fast validation, and structured logging are well-established data engineering patterns
- Pitfalls: HIGH - Based on documented issues in cited sources and author's own experience with Polars/Pandera
- HIPAA suppression: MEDIUM-HIGH - CMS and WA DOH standards are official but threshold choice involves judgment

**Research date:** 2026-03-17
**Valid until:** 90 days (April 2026) — Pandera and Pydantic are mature libraries with stable APIs; checkpoint patterns are architectural patterns that don't change rapidly
