# HL data loading & cleaning config loader
"""Load and expose paths from config/paths.toml.

This module provides centralized path configuration for the entire pipeline,
resolving relative paths against the project root and exposing them via a
typed dataclass. All pipeline scripts import load_config() to get consistent
path configuration.

**Pipeline Position:** Foundation layer (used by all phases)

**Input:** config/paths.toml (TOML configuration file)

**Output:** Paths dataclass with resolved absolute paths

**Key functions:**
- load_config(): Main entry point for path configuration
- _project_root(): Internal helper to locate project root
"""

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # Python < 3.11
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Paths:
    """Resolved path configuration for data, scratch, and output directories.

    This dataclass holds all critical pipeline paths after resolution against
    the project root. Paths are absolute and verified accessible before use
    by downstream scripts.

    Attributes:
        data_root: Source data directory (OneFlorida+ CSV extracts, read-only on HPC orange filesystem)
        scratch_root: Scratch workspace (HPC blue filesystem for intermediate outputs)
        datastructure_path: Path to datastructure.txt manifest (lists expected tables)
        valuesets_path: Path to valuesets.csv (PCORnet value-set definitions for validation)
        parquet_dir: Output directory for typed Parquet files (scratch_root/hl-clean/parquet by default)
        derived_dir: Output directory for derived datasets (patient_level.parquet, reports)
    """

    data_root: Path
    scratch_root: Path
    datastructure_path: Path
    valuesets_path: Path
    parquet_dir: Path
    derived_dir: Path


def _project_root() -> Path:
    """Locate project root directory containing config/ subdirectory.

    Uses Python file introspection to navigate up two parent directories from
    this module's location (__file__). Assumes this module is at
    src/load/config.py relative to project root.

    Returns:
        Path: Absolute path to project root directory

    Example:
        If __file__ is /path/to/project/src/load/config.py, returns /path/to/project
    """
    return Path(__file__).resolve().parents[2]


def load_config(config_path: Path | None = None) -> Paths:
    """Load and resolve paths from config/paths.toml TOML configuration file.

    Reads TOML configuration file, extracts [paths] section, and resolves all
    relative paths against project root to produce absolute paths. Provides
    fallback defaults for optional [paths.output] subsection. This is the main
    entry point for all pipeline scripts to get consistent path configuration.

    The configuration enables the pipeline to work across different HPC
    environments (orange vs blue filesystems) and local development setups.

    Args:
        config_path: Optional override path to config file. If None, defaults to
            project_root/config/paths.toml

    Returns:
        Paths: Dataclass with all resolved absolute paths ready for use

    Raises:
        FileNotFoundError: If config file doesn't exist at expected location
        KeyError: If required [paths] section or mandatory keys are missing from TOML

    Expected TOML structure:
        [paths]
        data_root = "/path/to/data"  # Can be absolute or relative
        scratch_root = "/path/to/scratch"
        datastructure_path = "path/to/datastructure.txt"
        valuesets_path = "path/to/valuesets.csv"

        [paths.output]  # Optional subsection
        parquet_dir = "hl-clean/parquet"  # Defaults to this if missing
        derived_dir = "derived"  # Defaults to this if missing
    """
    root = _project_root()
    path = config_path or (root / "config" / "paths.toml")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    p = raw["paths"]

    def resolve(value: str) -> Path:
        path_val = Path(value)
        if not path_val.is_absolute():
            path_val = root / path_val
        return path_val.resolve()

    scratch_root = Path(p["scratch_root"])
    output = p.get("output", {})
    parquet_rel = output.get("parquet_dir", "hl-clean/parquet")
    derived_rel = output.get("derived_dir", "derived")
    derived_path = Path(derived_rel)
    if not derived_path.is_absolute():
        derived_dir = (root / derived_rel).resolve()
    else:
        derived_dir = derived_path.resolve()

    return Paths(
        data_root=Path(p["data_root"]),
        scratch_root=scratch_root,
        datastructure_path=resolve(p["datastructure_path"]),
        valuesets_path=resolve(p["valuesets_path"]),
        parquet_dir=scratch_root / parquet_rel,
        derived_dir=derived_dir,
    )


def validate_config(paths: Paths) -> None:
    """Validate that all configured paths exist and are accessible.

    Performs explicit filesystem checks on all paths in the Paths dataclass to
    catch configuration errors at pipeline startup rather than mid-execution.
    Input paths (data_root, datastructure, valuesets) must exist. Output paths
    (scratch_root, parquet_dir, derived_dir) are created if missing.

    On success, prints a structured validation summary showing all paths verified.
    On failure, prints structured error message and raises ValueError with clear
    guidance on which path failed and why.

    **Design Decision: Plain pathlib validation, not Pydantic**
    Research suggested Pydantic for path validation, but adding Pydantic as a
    runtime dependency for 6 path checks is over-engineering. The existing
    Paths dataclass + explicit pathlib checks provides the same validation
    capability with zero new dependencies. Pydantic would be valuable if we
    needed complex validation logic (regex patterns, custom validators, nested
    models), but for "does this file exist?" checks, pathlib.exists() is
    sufficient and more maintainable.

    Args:
        paths: Paths dataclass with resolved path configuration

    Returns:
        None (validation success indicated by lack of exception)

    Raises:
        ValueError: If any required path doesn't exist or is wrong type (file vs directory)

    Example:
        paths = load_config()
        validate_config(paths)  # Raises ValueError if any path invalid
        # Pipeline proceeds knowing all paths are valid...
    """
    errors = []

    # Validate input paths (must exist)
    if not paths.data_root.exists():
        errors.append(f"data_root={paths.data_root} — Path does not exist")
    elif not paths.data_root.is_dir():
        errors.append(f"data_root={paths.data_root} — Path exists but is not a directory")

    if not paths.datastructure_path.exists():
        errors.append(f"datastructure_path={paths.datastructure_path} — File does not exist")
    elif not paths.datastructure_path.is_file():
        errors.append(f"datastructure_path={paths.datastructure_path} — Path exists but is not a file")

    if not paths.valuesets_path.exists():
        errors.append(f"valuesets_path={paths.valuesets_path} — File does not exist")
    elif not paths.valuesets_path.is_file():
        errors.append(f"valuesets_path={paths.valuesets_path} — Path exists but is not a file")

    # Validate/create output paths (create if missing)
    for output_path, field_name in [
        (paths.scratch_root, "scratch_root"),
        (paths.parquet_dir, "parquet_dir"),
        (paths.derived_dir, "derived_dir"),
    ]:
        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"{field_name}={output_path} — Failed to create directory: {e}")

    # Report errors if any
    if errors:
        print("[CONFIG FAIL] Path validation errors:")
        for error in errors:
            print(f"  - {error}")
        raise ValueError(f"Config validation failed with {len(errors)} error(s). See above for details.")

    # Success - print validation summary
    print("============================================================")
    print("CONFIG VALIDATION PASSED")
    print("============================================================")
    print(f"  data_root:          {paths.data_root} [OK]")
    print(f"  scratch_root:       {paths.scratch_root} [OK]")
    print(f"  datastructure:      {paths.datastructure_path} [OK]")
    print(f"  valuesets:          {paths.valuesets_path} [OK]")
    print(f"  parquet_dir:        {paths.parquet_dir} [OK]")
    print(f"  derived_dir:        {paths.derived_dir} [OK]")
    print("============================================================")


def load_and_validate_config(config_path: Path | None = None) -> Paths:
    """Load configuration and validate all paths in a single call.

    Convenience function that combines load_config() and validate_config() for
    typical pipeline usage. This is the recommended entry point for pipeline
    scripts that want fail-fast path validation at startup.

    Equivalent to:
        paths = load_config(config_path)
        validate_config(paths)
        return paths

    Args:
        config_path: Optional override path to config file. If None, defaults to
            project_root/config/paths.toml

    Returns:
        Paths: Validated dataclass with all resolved absolute paths

    Raises:
        FileNotFoundError: If config file doesn't exist at expected location
        KeyError: If required [paths] section or mandatory keys are missing from TOML
        ValueError: If any required path doesn't exist or is wrong type

    Example:
        from src.load.config import load_and_validate_config

        # Startup validation in pipeline script
        paths = load_and_validate_config()
        # Pipeline proceeds knowing config is valid...
    """
    paths = load_config(config_path)
    validate_config(paths)
    return paths
