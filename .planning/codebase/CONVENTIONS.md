# Coding Conventions

**Analysis Date:** 2026-03-09

## Naming Patterns

**Files:**
- `snake_case.py` for all Python modules and scripts

**Functions:**
- `snake_case` — e.g. `convert_table`, `flag_small_cell`, `parse_datastructure`

**Variables:**
- `snake_case` — e.g. `table_map`, `parquet_dir`
- Constants: `UPPER_SNAKE` — e.g. `PATID_COL`, `SMALL_CELL_THRESHOLD`, `DEDUP_KEYS`

**Types:**
- Type hints used: `Path`, `dict`, `list`, `tuple`, `pl.DataFrame`
- Dataclass: `Paths` in `config.py`

## Code Style

**Formatting:**
- 4-space indentation
- No explicit formatter (ruff, black) detected

**Linting:**
- No `.eslintrc`, `ruff.toml`, or `pyproject.toml` lint config found

## Import Organization

**Order:**
1. Standard library (`sys`, `pathlib`, `csv`, `re`, `time`, `datetime`)
2. Third-party (`polars`, `pandas`, `duckdb`)
3. Local (`from src.load.config import load_config`, etc.)

**Path setup:**
- Scripts use `sys.path.insert(0, str(PROJECT_ROOT))` where `PROJECT_ROOT = Path(__file__).resolve().parents[1]`

**No path aliases** — imports use `src.load`, `src.validate`, `src.clean`, `src.report`

## Error Handling

**Patterns:**
- Exceptions propagate; scripts catch at `if __name__ == "__main__"`, print traceback, `sys.exit(1)`
- No custom exception classes
- `convert_all.py` stops on first table failure
- Validation/clean modules return dicts/DataFrames; callers handle empty results

## Logging

**Approach:** Print to stdout (no `logging` module).

**Patterns:**
- Section headers: `print("=" * 60)`, `print("  SECTION 1: Schema Validation")`
- Progress: `print(f"  [OK] {table_name}")`, `print(f"  [SKIP] {table_name} — parquet not found")`
- Warnings: `print(f"  [WARN] ...")`
- Final summary block before exit

## Comments

**When to Comment:**
- Module docstrings (one-line purpose)
- Section separators: `# ---------------------------------------------------------------------------`
- Non-obvious logic (e.g. "AMS and UMI mapped ICD-9→ICD-10")
- Constants: brief inline when helpful

**Docstrings:**
- Functions have docstrings (Google-style or one-line)
- Args/returns not always documented

## Function Design

**Size:**
- Some report-section helpers are long (50–100+ lines) in scripts
- Core modules keep functions focused (20–80 lines typical)

**Parameters:**
- Prefer `Path` for file paths
- Optional config: `config_path: Path | None = None`

**Return Values:**
- Dicts for aggregated results (`{ "table": ..., "status": ... }`)
- `pl.DataFrame` for tabular output
- `None` for side-effect functions (write, print)

## Module Design

**Exports:**
- Functions and constants used by scripts are imported explicitly
- No `__all__`; modules expose public API implicitly

**Barrel Files:**
- `src/load/__init__.py`, `src/validate/__init__.py`, etc. — standard `__init__.py` (empty or minimal)

## Small-Cell Masking

**Rule:** Counts 1–10 must not be shown raw in publishable outputs (HIPAA).

**Implementation:**
- `flag_small_cell(value)` in `src/validate/structural.py`: returns `f"{value} ⚠"` for 1–10
- `_suppress(value)` in `scripts/clean_all.py` and report logic: returns `"-"` for 1–10
- Use `flag_small_cell` for markdown reports; use `_suppress` for CSVs
- Constant: `SMALL_CELL_THRESHOLD = 10`

---

*Convention analysis: 2026-03-09*
