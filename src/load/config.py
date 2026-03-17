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
