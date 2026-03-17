"""Quick check: do you have the right insurance/payer outputs and is DUAL_ELIGIBLE present?

Usage:
    python scripts/check_insurance_outputs.py [config/paths.toml]

Prints paths checked, columns in the parquet, and whether DUAL_ELIGIBLE appears in parquet and reports.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from src.load.config import load_config
    _has_config = True
except Exception as e:
    print("Config load failed:", e)
    _has_config = False

def main() -> None:
    """Quick diagnostic check for insurance/payer output files and DUAL_ELIGIBLE presence.

    Verifies that derived/encounter_payer_summary.parquet and reports/*.csv/md files exist,
    and confirms DUAL_ELIGIBLE column is present (added in Phase 16). Prints paths, status,
    and column checks to stdout.

    Used as a diagnostic tool after running assemble_clean.py or build_insurance_summary.py
    to verify insurance summary outputs are complete. Tolerates missing config (falls back to
    default project_root/derived and project_root/reports paths).

    Prints status for 4 checks: parquet source, CSV summary, markdown summary, dual-eligible prevalence CSV.
    """
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not _has_config:
        derived_dir = PROJECT_ROOT / "derived"
        reports_dir = PROJECT_ROOT / "reports"
        print("Using default paths: project_root/derived, project_root/reports")
    else:
        try:
            paths = load_config(config_path)
            derived_dir = paths.derived_dir
            print(f"derived_dir (config): {derived_dir}")
        except Exception as e:
            derived_dir = PROJECT_ROOT / "derived"
            print(f"Config failed ({e}); using {derived_dir}")
        reports_dir = PROJECT_ROOT / "reports"
    print(f"reports_dir: {reports_dir}")
    print()

    parquet_path = derived_dir / "encounter_payer_summary.parquet"
    csv_path = reports_dir / "encounter_payer_summary.csv"
    md_path = reports_dir / "insurance_summary.md"
    dual_csv_path = reports_dir / "dual_eligible_prevalence.csv"

    # 1. Parquet
    print("1. PARQUET (source for reports)")
    print(f"   Path: {parquet_path}")
    if not parquet_path.exists():
        print("   Status: FILE NOT FOUND")
        print("   Fix: run assemble_clean.py (needs ENCOUNTER data)")
    else:
        import polars as pl
        df = pl.read_parquet(parquet_path)
        cols = df.columns
        print(f"   Status: OK ({df.height} rows)")
        print(f"   Columns: {cols}")
        if "DUAL_ELIGIBLE" in cols:
            n1 = df.filter(pl.col("DUAL_ELIGIBLE") == 1).height
            n0 = df.filter(pl.col("DUAL_ELIGIBLE") == 0).height
            print(f"   DUAL_ELIGIBLE: YES (0: {n0}, 1: {n1})")
        else:
            print("   DUAL_ELIGIBLE: NO (parquet was built before Phase 16; re-run assemble_clean.py)")
    print()

    # 2. CSV summary
    print("2. ENCOUNTER PAYER SUMMARY CSV (reports)")
    print(f"   Path: {csv_path}")
    if not csv_path.exists():
        print("   Status: FILE NOT FOUND")
        print("   Fix: run build_insurance_summary.py")
    else:
        text = csv_path.read_text(encoding="utf-8")
        has_dual = "DUAL_ELIGIBLE" in text
        print(f"   Status: OK")
        print(f"   DUAL_ELIGIBLE in file: {'YES' if has_dual else 'NO'}")
    print()

    # 3. Insurance summary markdown
    print("3. INSURANCE SUMMARY MARKDOWN")
    print(f"   Path: {md_path}")
    if not md_path.exists():
        print("   Status: FILE NOT FOUND")
        print("   Fix: run build_insurance_summary.py")
    else:
        text = md_path.read_text(encoding="utf-8")
        has_dual = "Dual-eligible" in text or "DUAL_ELIGIBLE" in text
        print(f"   Status: OK")
        print(f"   Dual-eligible section: {'YES' if has_dual else 'NO'}")
    print()

    # 4. Dual-eligible prevalence CSV
    print("4. DUAL_ELIGIBLE PREVALENCE CSV")
    print(f"   Path: {dual_csv_path}")
    if not dual_csv_path.exists():
        print("   Status: FILE NOT FOUND")
        print("   Fix: run build_insurance_summary.py")
    else:
        print("   Status: OK")
    print()

    print("Done. If DUAL_ELIGIBLE is missing: run assemble_clean.py then build_insurance_summary.py.")

if __name__ == "__main__":
    main()
