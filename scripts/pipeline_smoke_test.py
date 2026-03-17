"""Pipeline smoke test: run convert_all → validate_all → clean_all → assemble_clean in sequence.

Verifies the full pipeline runs and produces expected outputs. Requires config and source data.
Run: python scripts/pipeline_smoke_test.py [config/paths.toml]

Note: Full run may take several minutes on real data. For CI, config may point to minimal/sample data.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.load.config import load_config


def main(config_path: Path | None = None) -> None:
    """Full pipeline integration test: convert_all → validate_all → clean_all → assemble_clean.

    Runs the complete 4-stage pipeline in sequence via subprocess calls, verifying each stage
    completes successfully (exit code 0) before proceeding. Checks that expected outputs exist:
    parquet files, reports/structural_validation.md, parquet_clean/, derived/patient_level.parquet.

    Designed for CI or pre-deployment validation. Requires complete config and source data.
    May take several minutes on real datasets. For CI, config can point to minimal sample data.

    Prints progress for each stage and verification checks to stdout. Exits with code 0 if
    all stages pass, 1 if any stage fails or outputs missing.

    Args:
        config_path: Optional path to config/paths.toml (uses default if None)

    Raises:
        SystemExit: If any pipeline stage fails (non-zero exit code) or required outputs missing
    """
    print("=" * 60)
    print("HL PIPELINE SMOKE TEST")
    print("=" * 60)

    paths = load_config(config_path)
    print(f"\n  parquet_dir: {paths.parquet_dir}")
    print(f"  reports:     {PROJECT_ROOT / 'reports'}")

    scripts = [
        ("convert_all", "scripts/convert_all.py", "Parquet files in parquet_dir"),
        ("validate_all", "scripts/validate_all.py", "reports/structural_validation.md"),
        ("clean_all", "scripts/clean_all.py", "Flagged Parquet in parquet_dir"),
        ("assemble_clean", "scripts/assemble_clean.py", "parquet_clean, derived/patient_level.parquet"),
    ]

    cfg_arg = [str(config_path)] if config_path and config_path.exists() else []

    for name, script_rel, desc in scripts:
        print(f"\n--- {name} ---")
        script_path = PROJECT_ROOT / script_rel
        if not script_path.exists():
            print(f"  SKIP: {script_path} not found")
            continue

        result = subprocess.run(
            [sys.executable, str(script_path)] + cfg_arg,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"  FAIL: {name} exited {result.returncode}")
            if result.stderr:
                print(result.stderr[-2000:])
            sys.exit(result.returncode)

        print(f"  OK: {desc}")

    # Verify outputs
    print("\n--- Verify outputs ---")
    parquet_files = list(paths.parquet_dir.glob("*.parquet")) if paths.parquet_dir.exists() else []
    struct_rpt = PROJECT_ROOT / "reports" / "structural_validation.md"
    parquet_clean = paths.parquet_dir.parent / "parquet_clean"
    patient_level = paths.derived_dir / "patient_level.parquet"

    checks = [
        (parquet_files, "At least one Parquet in parquet_dir"),
        (struct_rpt.exists(), "reports/structural_validation.md exists"),
        (parquet_clean.exists(), "parquet_clean/ exists"),
        (patient_level.exists(), "derived/patient_level.parquet exists"),
    ]

    all_ok = True
    for cond, msg in checks:
        ok = len(cond) > 0 if isinstance(cond, list) else cond
        status = "OK" if ok else "MISSING"
        print(f"  [{status}] {msg}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\n  Some outputs missing (may be expected if data/config incomplete)")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("=== PIPELINE SMOKE TEST PASSED ===")
    print("=" * 60)


if __name__ == "__main__":
    try:
        cfg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
        main(cfg)
        sys.exit(0)
    except Exception as exc:
        print("\n=== PIPELINE SMOKE TEST FAILED ===")
        print(f"Error: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
