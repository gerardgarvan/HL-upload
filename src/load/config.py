# HL data loading & cleaning config loader
"""Load and expose paths from config/paths.toml."""

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # Python < 3.11
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Paths:
    """Resolved path configuration for data, scratch, and output."""

    data_root: Path
    scratch_root: Path
    datastructure_path: Path
    valuesets_path: Path
    parquet_dir: Path
    derived_dir: Path


def _project_root() -> Path:
    """Project root: directory containing config/."""
    return Path(__file__).resolve().parents[2]


def load_config(config_path: Path | None = None) -> Paths:
    """Load config from config/paths.toml and return resolved paths.

    Resolves relative paths against project root (directory containing config/).
    The [paths.output] section is optional; defaults to scratch_root / hl-clean / parquet.
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
