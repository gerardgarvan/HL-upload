#!/usr/bin/env python3
"""Capture golden output baselines for regression detection.

Generates a JSON manifest containing SHA256 checksums, schemas (column names +
dtypes), and row counts for all pipeline output files. Actual data files remain
local and gitignored (HIPAA compliance); only the manifest is committed to git.

This enables regression detection after pipeline changes: rerun the capture script
and compare manifests to identify unexpected output modifications. The manifest
contains NO patient data (PHI) - only file metadata safe for version control.

Usage:
    python scripts/capture_golden.py [config/paths.toml]

Output:
    .golden/manifest.json - Committed baseline for regression detection

Rerun this script after intentional pipeline changes to update the baseline.
Pipeline outputs do not need to exist (script handles missing files gracefully).
"""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl
from src.load.config import load_config


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA256 checksum using efficient chunked reading.

    Uses hashlib.file_digest() (Python 3.11+) for memory-efficient hashing
    of large Parquet files without loading entire file into memory. SHA256
    is NIST-recommended for data integrity verification and HIPAA compliance.

    Args:
        file_path: Path to file to hash

    Returns:
        Hexadecimal SHA256 checksum string (64 characters)
    """
    with open(file_path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def capture_parquet_metadata(file_path: Path) -> dict:
    """Capture Parquet file metadata without loading actual data.

    Reads schema (column names + dtypes) and row count using lazy evaluation
    to avoid loading patient data into memory. Critical for HIPAA compliance
    and memory efficiency with large clinical datasets.

    Args:
        file_path: Path to Parquet file

    Returns:
        Dict with keys: schema (dict of col->dtype), row_count (int)
    """
    # Read schema without loading data
    schema = pl.read_parquet_schema(file_path)

    # Row count using lazy scan (doesn't load data)
    row_count = pl.scan_parquet(file_path).select(pl.len()).collect()[0, 0]

    return {
        "schema": {col: str(dtype) for col, dtype in schema.items()},
        "row_count": int(row_count),
    }


def capture_csv_metadata(file_path: Path) -> dict:
    """Capture CSV file metadata (column names and row count).

    Reads CSV to get column names and count rows. For large CSVs, this loads
    data into memory - prefer Parquet for production pipelines. Used for
    report files which are typically small summary tables.

    Args:
        file_path: Path to CSV file

    Returns:
        Dict with keys: columns (list of str), row_count (int)
    """
    df = pl.read_csv(file_path, infer_schema_length=0)
    return {
        "columns": df.columns,
        "row_count": len(df),
    }


def _get_git_commit() -> str | None:
    """Get current git HEAD commit SHA if in a git repository.

    Returns:
        Short commit SHA (7 chars) or None if not in git repo or git unavailable
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def capture_golden_manifest(
    output_dirs: list[tuple[Path, str]],
    manifest_path: Path,
    existing_manifest: dict | None = None,
) -> dict:
    """Capture golden file manifest with checksums and schemas.

    Reads all Parquet and CSV files in output_dirs and generates a JSON manifest
    containing SHA256 checksums, schemas (column names + dtypes), and row counts.
    Actual data never written to manifest (HIPAA compliance). Writes manifest to
    manifest_path for git commit.

    Skips directories that don't exist (allows partial pipeline runs). Only
    captures files actually present on disk. If existing_manifest provided,
    reports changes (added/removed/modified files) for regression detection.

    Args:
        output_dirs: List of (directory_path, priority_level) tuples where
            priority_level is "HIGH", "MEDIUM", or "LOW"
        manifest_path: Path to write JSON manifest (e.g., .golden/manifest.json)
        existing_manifest: Optional existing manifest dict to compare against

    Returns:
        Dict with structure:
            {
                "manifest_version": "1.0",
                "captured": "ISO-8601 timestamp",
                "pipeline_commit": "git HEAD SHA or null",
                "files": {
                    "relative/path.parquet": {
                        "sha256": "hex digest",
                        "schema": {"col": "dtype", ...},
                        "row_count": 12345,
                        "size_bytes": 67890,
                        "priority": "HIGH|MEDIUM|LOW",
                        "captured": "ISO-8601 timestamp"
                    }
                }
            }
    """
    files_metadata = {}
    total_files = 0
    total_size = 0

    print(f"\n{'=' * 60}")
    print("CAPTURING PIPELINE OUTPUT BASELINES")
    print(f"{'=' * 60}\n")

    for output_dir, priority in output_dirs:
        if not output_dir.exists():
            # Display path relative to PROJECT_ROOT if possible, otherwise use absolute
            try:
                display_path = output_dir.relative_to(PROJECT_ROOT)
            except ValueError:
                display_path = output_dir
            print(f"Skipping {display_path} (not found)")
            continue

        # Display path relative to PROJECT_ROOT if possible, otherwise use absolute
        try:
            display_path = output_dir.relative_to(PROJECT_ROOT)
        except ValueError:
            display_path = output_dir
        print(f"\nProcessing {display_path}/ [{priority} priority]")

        # Capture Parquet files
        parquet_files = sorted(output_dir.rglob("*.parquet"))
        for parquet_file in parquet_files:
            # Store path relative to PROJECT_ROOT if possible, otherwise use absolute
            try:
                rel_path = str(parquet_file.relative_to(PROJECT_ROOT))
            except ValueError:
                rel_path = str(parquet_file)
            print(f"  {rel_path}")

            # SHA256 checksum (efficient chunked reading)
            file_hash = compute_file_sha256(parquet_file)

            # Schema and row count without loading data
            metadata = capture_parquet_metadata(parquet_file)

            files_metadata[rel_path] = {
                "sha256": file_hash,
                "schema": metadata["schema"],
                "row_count": metadata["row_count"],
                "size_bytes": parquet_file.stat().st_size,
                "priority": priority,
                "captured": datetime.now(timezone.utc).isoformat(),
            }

            total_files += 1
            total_size += parquet_file.stat().st_size

        # Capture CSV files (reports only, not raw data)
        csv_files = sorted(output_dir.glob("*.csv"))
        for csv_file in csv_files:
            try:
                rel_path = str(csv_file.relative_to(PROJECT_ROOT))
            except ValueError:
                rel_path = str(csv_file)
            print(f"  {rel_path}")

            # SHA256 checksum
            file_hash = compute_file_sha256(csv_file)

            # Column names and row count
            metadata = capture_csv_metadata(csv_file)

            files_metadata[rel_path] = {
                "sha256": file_hash,
                "columns": metadata["columns"],
                "row_count": metadata["row_count"],
                "size_bytes": csv_file.stat().st_size,
                "priority": priority,
                "captured": datetime.now(timezone.utc).isoformat(),
            }

            total_files += 1
            total_size += csv_file.stat().st_size

        # Capture PNG files (figures - binary, just checksum and size)
        png_files = sorted(output_dir.rglob("*.png"))
        for png_file in png_files:
            try:
                rel_path = str(png_file.relative_to(PROJECT_ROOT))
            except ValueError:
                rel_path = str(png_file)
            print(f"  {rel_path}")

            # SHA256 checksum only (binary file)
            file_hash = compute_file_sha256(png_file)

            files_metadata[rel_path] = {
                "sha256": file_hash,
                "size_bytes": png_file.stat().st_size,
                "priority": priority,
                "captured": datetime.now(timezone.utc).isoformat(),
            }

            total_files += 1
            total_size += png_file.stat().st_size

    # Build manifest
    manifest_content = {
        "manifest_version": "1.0",
        "captured": datetime.now(timezone.utc).isoformat(),
        "pipeline_commit": _get_git_commit(),
        "files": files_metadata,
    }

    # Compare with existing manifest if provided
    if existing_manifest:
        print(f"\n{'=' * 60}")
        print("COMPARING WITH EXISTING MANIFEST")
        print(f"{'=' * 60}\n")

        old_files = set(existing_manifest.get("files", {}).keys())
        new_files = set(files_metadata.keys())

        added = new_files - old_files
        removed = old_files - new_files
        common = old_files & new_files

        changed = []
        for file_path in common:
            old_hash = existing_manifest["files"][file_path].get("sha256")
            new_hash = files_metadata[file_path].get("sha256")
            if old_hash != new_hash:
                changed.append(file_path)

        if added:
            print(f"Added files ({len(added)}):")
            for f in sorted(added):
                print(f"  + {f}")

        if removed:
            print(f"\nRemoved files ({len(removed)}):")
            for f in sorted(removed):
                print(f"  - {f}")

        if changed:
            print(f"\nModified files ({len(changed)}):")
            for f in sorted(changed):
                print(f"  M {f}")

        if not added and not removed and not changed:
            print("No changes detected - manifest matches existing baseline")

    # Write manifest
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_content, indent=2))

    # Summary
    print(f"\n{'=' * 60}")
    print("CAPTURE SUMMARY")
    print(f"{'=' * 60}")
    print(f"Manifest written: {manifest_path.relative_to(PROJECT_ROOT)}")
    print(f"Files captured: {total_files}")
    print(f"Total size: {total_size / (1024 * 1024):.2f} MB")
    print(f"Git commit: {manifest_content['pipeline_commit'] or 'N/A'}")

    return manifest_content


def main(config_path: Path | None = None) -> None:
    """Capture golden baselines for all pipeline outputs.

    Loads configuration, identifies output directories, captures file metadata,
    and writes manifest to .golden/manifest.json. Handles missing pipeline
    outputs gracefully (empty manifest is valid).

    Args:
        config_path: Optional path to config/paths.toml (defaults to project config)
    """
    print(f"{'=' * 60}")
    print("GOLDEN BASELINE CAPTURE SCRIPT")
    print(f"{'=' * 60}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")

    # Load configuration
    try:
        paths = load_config(config_path)
    except Exception as e:
        print(f"\nError loading config: {e}")
        print("Cannot determine output directories without config.")
        sys.exit(1)

    # Define output directories with priority levels
    # HIGH: Core pipeline outputs (cleaned CDM tables, patient-level data)
    # MEDIUM: Summary reports (CSV tables)
    # LOW: Figures (binary images, harder to diff)
    output_dirs = [
        (paths.parquet_dir.parent / "parquet_clean", "HIGH"),
        (paths.derived_dir, "HIGH"),
        (PROJECT_ROOT / "reports", "MEDIUM"),
        (PROJECT_ROOT / "reports" / "figures", "LOW"),
    ]

    manifest_path = PROJECT_ROOT / ".golden" / "manifest.json"

    # Load existing manifest if present for comparison
    existing_manifest = None
    if manifest_path.exists():
        try:
            existing_manifest = json.loads(manifest_path.read_text())
            print(f"\nExisting manifest found: {manifest_path.relative_to(PROJECT_ROOT)}")
            print("Will compare changes after capture.")
        except json.JSONDecodeError:
            print(f"\nWarning: Existing manifest is invalid JSON, will overwrite")

    # Capture manifest
    manifest = capture_golden_manifest(output_dirs, manifest_path, existing_manifest)

    # Next steps
    print(f"\n{'=' * 60}")
    print("NEXT STEPS")
    print(f"{'=' * 60}")

    if not manifest["files"]:
        print("\nNo pipeline outputs found. This is expected if you haven't run")
        print("the pipeline yet. To capture actual baselines:")
        print("  1. Run the pipeline on HPC to generate outputs")
        print("  2. Rerun this script: python scripts/capture_golden.py")
        print("  3. Commit the populated manifest")
    else:
        print("\n1. Review manifest:")
        print(f"   cat .golden/manifest.json | head -50")
        print("\n2. Verify no PHI in manifest (only checksums, schemas, counts)")
        print("\n3. Commit manifest:")
        print("   git add .golden/manifest.json")
        print('   git commit -m "docs: capture golden baselines"')
        print("\n4. Verify actual files gitignored:")
        print("   git status  # Should NOT show .parquet/.csv files")
        print("\n5. After pipeline changes, rerun script to detect regressions:")
        print("   python scripts/capture_golden.py")


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(config_path)
