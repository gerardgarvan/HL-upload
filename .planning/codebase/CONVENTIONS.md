# Coding Conventions

**Analysis Date:** 2026-03-17

## Naming Patterns

**Files:**
- Module files: `lowercase_with_underscores.py` (e.g., `dedup.py`, `harmonize.py`, `quality_report.py`)
- Test files: `test_<module_name>.py` (e.g., `test_cohort.py`, `test_structural.py`, `test_suppress.py`)
- Constants/manifest files: descriptive lowercase names with underscores
- Scripts in `scripts/`: command-case names (e.g., `build_insurance_summary.py`, `clean_all.py`)

**Functions:**
- All lowercase with underscores: `verify_hl_cohort()`, `flag_duplicates()`, `check_demographic_consistency()`
- Private helper functions: prefix with single underscore `_normalize_dx()`, `_project_root()`, `_dx_type_upper()`
- Factory/builder functions: use `_` prefix (e.g., `_compute_hl_timeline()`, `_first_hl_dx_and_code()`)

**Variables:**
- Local variables: lowercase with underscores (`total_patients`, `diag_path`, `has_dx_type`, `flag_cols`)
- Constants: UPPERCASE_WITH_UNDERSCORES
- Private module variables: single leading underscore (rarely used)
- Temporary/intermediate variables: simple lowercase names (`df`, `diag`, `demo`, `enc`, `result`)

**Types:**
- Class names: PascalCase (e.g., `Paths` in `src/load/config.py`)
- Type hints: use standard Python type hints and Union (e.g., `dict[str, Path]`, `tuple[pl.DataFrame, pl.DataFrame] | None`)

**Constants by Purpose:**
- Lookup tables/sets: `ALL_HL_CODES`, `ICD10_HL_NORMALIZED`, `DEDUP_KEYS`, `ONCOLOGY_KEYWORDS`
- Thresholds: `SMALL_CELL_THRESHOLD = 10`
- Configuration: `PAYER_CATEGORY_ORDER`, `TUMOR_REGISTRY_TABLES`, `ENCOUNTER_LINKED_TABLES`
- Prefix/suffix markers: `CLEAN_FLAG_PREFIX = "_con_"`, `CLEAN_FLAG_COLS`

## Code Style

**Formatting:**
- Tool: `ruff format` (auto-formatting)
- Line length: 140 characters (set in `pyproject.toml`)
- Quote style: double quotes (`"string"` not `'string'`)
- Indentation: 4 spaces (Python standard)

**Linting:**
- Tool: `ruff` (configured in `pyproject.toml`)
- Rules enabled: `["E", "F", "I", "W"]` (Error, pyFlakes, isort, Warnings)
- Per-file ignores: Scripts allow `E402` (module level import not at top) in `scripts/*.py`
- Target version: Python 3.11+

**Command references:**
```bash
ruff check .              # Check style/lint issues
ruff format --check .    # Check formatting
ruff format .            # Auto-format code
```

## Import Organization

**Order (enforced by ruff isort):**
1. Standard library imports (e.g., `from pathlib import Path`, `import re`, `from datetime import date`)
2. Third-party library imports (e.g., `import polars as pl`, `import pandas as pd`)
3. Local/relative imports (e.g., `from src.load.config import load_config`)

**Pattern examples from codebase:**
```python
# Standard library first
from pathlib import Path
from datetime import date
import re
import sys

# Third-party
import polars as pl
import pandas as pd

# Local imports
from src.load.config import load_config
from src.validate.cohort import verify_hl_cohort, ICD10_HL_CODES
from src.validate.structural import PATID_COL, flag_small_cell
```

**Path Aliases:**
- No path aliases configured in this codebase
- Projects use explicit `from src.<module>` imports
- Entry points add project root to `sys.path`: `sys.path.insert(0, str(PROJECT_ROOT))`

## Error Handling

**Patterns:**
- Explicit exception handling with descriptive messages (see `src/load/schema.py`):
  ```python
  try:
      text = path.read_text(encoding="utf-8-sig")
  except Exception as exc:
      print(f"  [WARN] Could not read file: {exc}")
      return {}
  ```
- Fallback chains: return `{}` or empty DataFrames when resources unavailable
- Validation via `if not path.exists()`: check file existence before reading
- Early exit in scripts: `sys.exit(0)` for missing/empty dependencies
- Raise `FileNotFoundError` with complete missing file list (e.g., `src/load/schema.py`)

**Data handling:**
- Null/None checks before operations: `if value is None or value == ""`
- Empty DataFrame checks: `if df.is_empty()` or `if diag.is_empty()`
- Coalesce/fallback with Polars: `.fill_null()` chains for multi-format parsing

## Logging

**Framework:** `print()` statements (no structured logging framework)

**Patterns:**
- Section headers with equals signs: `print("=" * 60)` then `print("TITLE")`
- Status messages: `print(f"  derived_dir: {derived_dir}")` (2-space indent for details)
- Warning format: `print(f"  [WARN] Could not read file: {exc}")`
- Counts and metrics: `print(f"  Rows: {df.height:,}")` (use `:,` for thousands separator)
- Execution milestones: `print("\nOperationName")` with blank line separator

**Example structure:**
```python
print("=" * 60)
print("HL DATA SUMMARY")
print("=" * 60)
print(f"\n  data_root: {paths.data_root}")
print(f"  records: {total:,}")
```

## Comments

**When to Comment:**
- Module docstring: always present at top (triple-quoted, describes purpose/scope)
- Function docstrings: present for all public functions (one-liner + details)
- Inline comments: used for non-obvious logic, algorithm explanations, or business rules
- Section headers: `# ---[dashes]---` separators for major sections in longer files (see `src/clean/dedup.py`)

**JSDoc/TSDoc:**
- Not used (Python codebase)
- Use Python docstrings with triple quotes:
  ```python
  def flag_duplicates(df: pl.DataFrame, table_name: str) -> pl.DataFrame:
      """Mark ALL rows sharing composite key values as IS_DUPLICATE=1.

      Uses ``DataFrame.is_duplicated()`` on a column subset — marks both
      first and subsequent occurrences. Null keys do NOT match each other.
      """
  ```

**Doc style:**
- One-liner summary on first line
- Blank line, then detailed explanation
- Parameter types in function signature (use type hints)
- Returns section optional if obvious from signature
- Emphasis with backticks for code references: `` `IS_DUPLICATE` ``

## Function Design

**Size:**
- Functions typically 20-80 lines
- Longer functions (100+ lines) acceptable when processing multiple related steps in one operation
- Examples: `check_death_consistency()` (~90 lines), `flag_events_outside_encounters()` (~50 lines)

**Parameters:**
- Use specific types: `df: pl.DataFrame`, `path: Path | None`, `table_name: str`
- Default parameters for optional configuration (e.g., `code_col: str = "DX"`)
- Dictionaries for grouping related params: `table_map: dict[str, Path]`

**Return Values:**
- Single values: direct return (`return total_patients`)
- Multiple related values: tuple with type hint (`tuple[pl.DataFrame, pl.DataFrame] | None`)
- Collections: return dict with descriptive keys (`{"multi_birth_date": [...], "multi_sex": [...], "total_patients": 500}`)
- Empty result fallback: `return {}` or `return pl.DataFrame(...)`
- Status dicts: include `"status"` key with values like `"ok"`, `"warn"`, `"error"`

## Module Design

**Exports:**
- All public functions exported implicitly (no `__all__`)
- Private functions prefixed with `_` (not re-exported from modules)
- Constants (like `ICD10_HL_CODES`) available at module level for importing

**Barrel Files:**
- No barrel/index files (`__init__.py` is mostly empty)
- Direct imports from specific modules: `from src.validate.cohort import verify_hl_cohort`
- `src/clean/__init__.py`, `src/load/__init__.py`, `src/validate/__init__.py` are empty

**Module structure example (`src/clean/dedup.py`):**
1. Module docstring (purpose + behavior)
2. Imports (std lib, third-party, local)
3. Constants section with clear structure
4. Functions organized by logical grouping with section headers
5. No trailing utility helpers at end

## Polars-Specific Conventions

**DataFrame operations:**
- Use method chaining: `.filter().select().with_columns()`
- Prefer lazy evaluation for large files: `pl.scan_parquet().filter().collect()`
- Column operations: use `pl.col()` expressions in `.with_columns()` and `.select()`
- Type casting: `.cast(pl.Int8)`, `.cast(pl.String)`, `.cast(pl.Date)`

**Null/Missing handling:**
- Explicit checks: `.is_null()`, `.is_not_null()`
- Fallback values: `.fill_null()` with literal or expression
- Coalesce: `pl.coalesce()` for multiple fallback columns

**String operations:**
- Normalization: `.str.to_uppercase().str.replace_all(r"\.", "")`
- Pattern matching: `.str.contains(r"\.")`, `.str.starts_with("C81")`
- Format parsing: `.str.to_date("%Y-%m-%d", strict=False)`

---

*Convention analysis: 2026-03-17*
