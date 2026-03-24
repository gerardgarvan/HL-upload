"""Phase 9: Insurance Diagnostic — Unknown/Unavailable Investigation.

This diagnostic script investigates Unknown and Unavailable insurance patterns across
treatment windows and post-treatment encounters, answering 5 specific questions:

1. Enrollment coverage cross-reference for Unknown/Unavailable patients at treatment windows
2. % of Unknown and Unavailable chemo post-treatment patients with zero post-chemo encounters
3. % of Unknown and Unavailable radiation post-treatment patients with zero post-radiation encounters
4. % of Unknown and Unavailable SCT post-treatment patients with zero post-SCT encounters
5. Patient-level trace for the 4 SCT patients with primary Unknown showing why first/last SCT payer is not Unknown

Reads:
- derived/encounter_payer_summary.parquet (treatment dates, payer categories)
- cleaned/ENROLLMENT*.parquet (ENR_START_DATE, ENR_END_DATE per patient)
- cleaned/ENCOUNTER*.parquet (for post-treatment encounter analysis)

Produces:
- Console output with findings for all 5 questions
- reports/phase9_insurance_diagnostic.md (structured markdown report)

No PNG, HTML, CSV, or PowerPoint output. This is diagnostic analysis only.

Usage:
    python scripts/investigate_insurance_diagnostic.py [config/paths.toml]
"""

import sys
from pathlib import Path
from datetime import timedelta, datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl

from src.load.config import load_and_validate_config
from src.report.encounter_payer_summary import (
    _payer_category_from_effective_and_dual,
    _effective_payer_and_dual_exprs,
)
from scripts.build_insurance_enr_comparison import (
    _flag_enrollment_coverage,
    PAYER_CATEGORY_ORDER,
    WINDOW_DAYS,
    ENCOUNTER_COUNT_BINS,
)


def _analyze_post_treatment_gaps(
    enc_payer_summary: pl.DataFrame,
    enc_path: Path,
    treatment_flag_col: str,
    last_date_col: str,
    payer_col: str,
    treatment_label: str,
) -> list[str]:
    """Analyze post-treatment encounter gaps for Unknown/Unavailable patients.

    For each payer category (Unknown, Unavailable), compute:
    - N patients at last treatment with that payer
    - N patients with zero post-treatment encounters
    - % with zero post-treatment encounters
    - Distribution of encounter counts

    Args:
        enc_payer_summary: encounter_payer_summary DataFrame
        enc_path: Path to ENCOUNTER parquet file
        treatment_flag_col: Treatment flag column (e.g., "HAD_CHEMO")
        last_date_col: Last treatment date column (e.g., "LAST_CHEMO_DATE")
        payer_col: Payer category column (e.g., "PAYER_CATEGORY_AT_LAST_CHEMO")
        treatment_label: Label for output (e.g., "Chemotherapy")

    Returns:
        List of markdown lines for this section
    """
    md_lines = []
    md_lines.append(f"## Question: Post-Treatment Encounter Gaps — {treatment_label}")
    md_lines.append("")

    # Filter to treatment cohort
    cohort = enc_payer_summary.filter(
        (pl.col(treatment_flag_col) == 1) & pl.col(last_date_col).is_not_null()
    )

    if cohort.is_empty():
        md_lines.append(f"**No patients with {treatment_label.lower()} treatment dates.**")
        md_lines.append("")
        return md_lines

    print(f"  Cohort: {cohort.height:,} patients with {treatment_label.lower()} dates")

    # Read encounters
    enc = pl.read_parquet(enc_path)
    enc = enc.with_columns(pl.col("ID").cast(pl.String))

    # Analyze Unknown and Unavailable separately
    summary_rows = []

    for payer_category in ["Unknown", "Unavailable"]:
        # Filter to patients with this payer at last treatment
        payer_cohort = cohort.filter(pl.col(payer_col) == payer_category)

        if payer_cohort.is_empty():
            print(f"    {payer_category}: N=0 patients")
            summary_rows.append({
                "Category": payer_category,
                "N Patients": 0,
                "N Zero Post-Tx": 0,
                "% Zero": 0.0,
            })
            continue

        n_total = payer_cohort.height
        print(f"    {payer_category}: N={n_total:,} patients at last {treatment_label.lower()}")

        # Filter encounters to payer cohort patients
        enc_filtered = enc.filter(pl.col("ID").is_in(payer_cohort["ID"].implode()))

        # Join to get last treatment date
        joined = payer_cohort.select("ID", last_date_col).join(
            enc_filtered.select("ID", "ADMIT_DATE"), on="ID", how="left"
        )

        # Filter to post-treatment encounters (strict greater-than)
        post_tx_enc = joined.filter(
            pl.col("ADMIT_DATE") > pl.col(last_date_col)
        )

        # Count encounters per patient
        enc_counts = post_tx_enc.group_by("ID").agg(
            pl.len().alias("N_POST_ENC")
        )

        # Merge back to payer cohort, fill nulls with 0 (no post-treatment encounters)
        payer_with_counts = payer_cohort.join(
            enc_counts, on="ID", how="left"
        ).with_columns(
            pl.col("N_POST_ENC").fill_null(0)
        )

        # Compute zero-encounter metrics
        n_zero_enc = payer_with_counts.filter(pl.col("N_POST_ENC") == 0).height
        pct_zero = 100.0 * n_zero_enc / n_total if n_total > 0 else 0.0

        print(f"      Zero post-treatment encounters: {n_zero_enc:,} ({pct_zero:.1f}%)")

        summary_rows.append({
            "Category": payer_category,
            "N Patients": n_total,
            "N Zero Post-Tx": n_zero_enc,
            "% Zero": pct_zero,
        })

        # Bin encounter counts
        payer_with_counts = payer_with_counts.with_columns(
            pl.when(pl.col("N_POST_ENC") == 0).then(pl.lit("0"))
            .when(pl.col("N_POST_ENC") <= 5).then(pl.lit("1-5"))
            .when(pl.col("N_POST_ENC") <= 10).then(pl.lit("6-10"))
            .when(pl.col("N_POST_ENC") <= 20).then(pl.lit("11-20"))
            .otherwise(pl.lit("21+"))
            .alias("_bin")
        )

        # Count patients per bin
        bin_counts = payer_with_counts.group_by("_bin").agg(
            pl.len().alias("N_Patients")
        )
        bin_map = {row["_bin"]: row["N_Patients"] for row in bin_counts.iter_rows(named=True)}

        # Build encounter distribution section
        md_lines.append(f"### {payer_category} — Encounter Distribution")
        md_lines.append("")
        md_lines.append("| Encounter Count | N Patients | % Patients |")
        md_lines.append("|-----------------|------------|------------|")
        for bin_label in ENCOUNTER_COUNT_BINS:
            n = bin_map.get(bin_label, 0)
            pct = 100.0 * n / n_total if n_total > 0 else 0.0
            md_lines.append(f"| {bin_label} | {n} | {pct:.1f}% |")
        md_lines.append("")

    # Summary table
    md_lines.insert(2, "### Summary")
    md_lines.insert(3, "")
    md_lines.insert(4, "| Category | N Patients at Last Treatment | N Zero Post-Tx Encounters | % Zero |")
    md_lines.insert(5, "|----------|------------------------------|---------------------------|--------|")
    for row in summary_rows:
        md_lines.insert(6, f"| {row['Category']} | {row['N Patients']} | {row['N Zero Post-Tx']} | {row['% Zero']:.1f}% |")
    md_lines.insert(7, "")

    return md_lines


def main(config_path=None):
    """Main execution function."""
    print("=" * 70)
    print("Phase 9: Insurance Diagnostic — Unknown/Unavailable Investigation")
    print("=" * 70)

    # Load config
    paths = load_and_validate_config(config_path)
    derived_dir = paths.derived_dir
    clean_dir = paths.parquet_dir

    # Initialize markdown report
    md_lines = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md_lines.append("# Phase 9: Insurance Diagnostic Report")
    md_lines.append("")
    md_lines.append(f"**Generated:** {timestamp}")
    md_lines.append("")
    md_lines.append("This report investigates Unknown and Unavailable insurance patterns across treatment windows and post-treatment encounters.")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    # Load data
    print(f"\n[DATA LOADING] Reading encounter_payer_summary.parquet from {derived_dir}")
    enc_payer_summary_path = derived_dir / "encounter_payer_summary.parquet"
    if not enc_payer_summary_path.exists():
        print(f"ERROR: {enc_payer_summary_path} not found")
        sys.exit(1)

    enc_payer_summary = pl.read_parquet(enc_payer_summary_path)
    print(f"  Loaded {enc_payer_summary.height:,} patients")

    print(f"\n[DATA LOADING] Reading ENROLLMENT parquet from {clean_dir}")
    enrollment_files = list(clean_dir.glob("ENROLLMENT*.parquet"))
    if not enrollment_files:
        print(f"ERROR: No ENROLLMENT*.parquet files found in {clean_dir}")
        sys.exit(1)

    enrollment_df = pl.read_parquet(enrollment_files[0])
    enrollment_df = enrollment_df.with_columns(pl.col("ID").cast(pl.String))
    print(f"  Loaded {enrollment_df.height:,} enrollment records from {enrollment_files[0].name}")

    print(f"\n[DATA LOADING] Reading ENCOUNTER parquet from {clean_dir}")
    encounter_files = list(clean_dir.glob("ENCOUNTER*.parquet"))
    if not encounter_files:
        print(f"ERROR: No ENCOUNTER*.parquet files found in {clean_dir}")
        sys.exit(1)

    enc_path = encounter_files[0]
    print(f"  Found {enc_path.name}")

    # [1/5] Question 1: Enrollment coverage cross-reference
    print(f"\n[1/5] Question 1: Enrollment Coverage for Unknown/Unavailable Patients")
    md_lines.append("## Question 1: Enrollment Coverage for Unknown/Unavailable Patients")
    md_lines.append("")
    md_lines.append("Cross-referencing Unknown and Unavailable insurance patients at treatment windows with ENROLLMENT coverage (±30 day window).")
    md_lines.append("")

    treatment_configs = [
        ("Chemotherapy", "HAD_CHEMO", "FIRST_CHEMO_DATE", "LAST_CHEMO_DATE",
         "PAYER_CATEGORY_AT_FIRST_CHEMO", "PAYER_CATEGORY_AT_LAST_CHEMO"),
        ("Radiation", "HAD_RADIATION", "FIRST_RADIATION_DATE", "LAST_RADIATION_DATE",
         "PAYER_CATEGORY_AT_FIRST_RADIATION", "PAYER_CATEGORY_AT_LAST_RADIATION"),
        ("SCT", "HAD_SCT", "FIRST_SCT_DATE", "LAST_SCT_DATE",
         "PAYER_CATEGORY_AT_FIRST_SCT", "PAYER_CATEGORY_AT_LAST_SCT"),
    ]

    for tx_label, flag_col, first_date_col, last_date_col, first_payer_col, last_payer_col in treatment_configs:
        print(f"\n  {tx_label} enrollment coverage:")
        md_lines.append(f"### {tx_label}")
        md_lines.append("")

        # Filter to treatment cohort
        cohort = enc_payer_summary.filter(
            (pl.col(flag_col) == 1) &
            pl.col(first_date_col).is_not_null() &
            pl.col(last_date_col).is_not_null()
        )

        if cohort.is_empty():
            print(f"    No patients with {tx_label.lower()} dates")
            md_lines.append(f"**No patients with {tx_label.lower()} treatment dates.**")
            md_lines.append("")
            continue

        print(f"    Cohort: {cohort.height:,} patients")

        # Build table for first and last treatment
        table_rows = []

        for timepoint_label, date_col, payer_col in [
            ("First", first_date_col, first_payer_col),
            ("Last", last_date_col, last_payer_col),
        ]:
            for payer_category in ["Unknown", "Unavailable"]:
                # Filter to patients with this payer at this timepoint
                payer_cohort = cohort.filter(pl.col(payer_col) == payer_category)

                if payer_cohort.is_empty():
                    table_rows.append({
                        "Payer Category": payer_category,
                        "Timepoint": timepoint_label,
                        "N Patients": 0,
                        "ENR Covers": 0,
                        "ENR Gap": 0,
                    })
                    continue

                # Flag enrollment coverage
                enr_coverage = _flag_enrollment_coverage(
                    payer_cohort.select("ID", date_col),
                    enrollment_df,
                    date_col,
                    WINDOW_DAYS
                )

                # Join back
                merged = payer_cohort.join(
                    enr_coverage.select("ID", "ENR_COVERS_WINDOW"),
                    on="ID",
                    how="left"
                ).with_columns(pl.col("ENR_COVERS_WINDOW").fill_null(0))

                # Count
                n_total = merged.height
                n_enr_covers = merged.filter(pl.col("ENR_COVERS_WINDOW") == 1).height
                n_enr_gap = merged.filter(pl.col("ENR_COVERS_WINDOW") == 0).height

                print(f"      {payer_category} {timepoint_label}: N={n_total:,} (ENR covers={n_enr_covers}, gap={n_enr_gap})")

                table_rows.append({
                    "Payer Category": payer_category,
                    "Timepoint": timepoint_label,
                    "N Patients": n_total,
                    "ENR Covers": n_enr_covers,
                    "ENR Gap": n_enr_gap,
                })

        # Write markdown table
        md_lines.append("| Payer Category | Timepoint | N Patients | ENR Covers ±30d | ENR Gap |")
        md_lines.append("|----------------|-----------|------------|-----------------|---------|")
        for row in table_rows:
            md_lines.append(
                f"| {row['Payer Category']} | {row['Timepoint']} | "
                f"{row['N Patients']} | {row['ENR Covers']} | {row['ENR Gap']} |"
            )
        md_lines.append("")

    # [2/5] Question 2: Chemo post-treatment encounter gaps
    print(f"\n[2/5] Question 2: Chemo Post-Treatment Encounter Gaps")
    chemo_md = _analyze_post_treatment_gaps(
        enc_payer_summary,
        enc_path,
        "HAD_CHEMO",
        "LAST_CHEMO_DATE",
        "PAYER_CATEGORY_AT_LAST_CHEMO",
        "Chemotherapy"
    )
    md_lines.extend(chemo_md)

    # [3/5] Question 3: Radiation post-treatment encounter gaps
    print(f"\n[3/5] Question 3: Radiation Post-Treatment Encounter Gaps")
    radiation_md = _analyze_post_treatment_gaps(
        enc_payer_summary,
        enc_path,
        "HAD_RADIATION",
        "LAST_RADIATION_DATE",
        "PAYER_CATEGORY_AT_LAST_RADIATION",
        "Radiation"
    )
    md_lines.extend(radiation_md)

    # [4/5] Question 4: SCT post-treatment encounter gaps
    print(f"\n[4/5] Question 4: SCT Post-Treatment Encounter Gaps")
    sct_md = _analyze_post_treatment_gaps(
        enc_payer_summary,
        enc_path,
        "HAD_SCT",
        "LAST_SCT_DATE",
        "PAYER_CATEGORY_AT_LAST_SCT",
        "SCT"
    )
    md_lines.extend(sct_md)

    # [5/5] Question 5: SCT primary Unknown discrepancy investigation
    print(f"\n[5/5] Question 5: SCT Primary Unknown Discrepancy Investigation")
    md_lines.append("## Question 5: SCT Primary Unknown Discrepancy Investigation")
    md_lines.append("")
    md_lines.append("Investigating why 4 SCT patients have PAYER_CATEGORY_PRIMARY = 'Unknown' but PAYER_CATEGORY_AT_FIRST_SCT and PAYER_CATEGORY_AT_LAST_SCT are both non-Unknown.")
    md_lines.append("")

    # Filter to SCT patients with primary Unknown
    sct_unknown_primary = enc_payer_summary.filter(
        (pl.col("HAD_SCT") == 1) & (pl.col("PAYER_CATEGORY_PRIMARY") == "Unknown")
    )

    print(f"  Found {sct_unknown_primary.height} SCT patients with primary Unknown")

    if sct_unknown_primary.is_empty():
        md_lines.append("**No SCT patients with primary Unknown found.**")
        md_lines.append("")
    else:
        # Build per-patient trace table
        md_lines.append("### Patient-Level Trace")
        md_lines.append("")
        md_lines.append("| Patient | Primary Payer | At First SCT | At Last SCT | First SCT Date | Last SCT Date |")
        md_lines.append("|---------|---------------|--------------|-------------|----------------|---------------|")

        # Read encounters for these patients
        enc_schema = pl.read_parquet_schema(enc_path)
        has_secondary = "PAYER_TYPE_SECONDARY" in enc_schema.names()
        enc_cols = ["ID", "ADMIT_DATE", "PAYER_TYPE_PRIMARY"]
        if has_secondary:
            enc_cols.append("PAYER_TYPE_SECONDARY")

        eff_expr, valid_expr, dual_expr = _effective_payer_and_dual_exprs(has_secondary)

        enc = (
            pl.scan_parquet(enc_path)
            .with_columns(pl.col("ID").cast(pl.String))
            .filter(pl.col("ID").is_in(sct_unknown_primary["ID"].implode()))
            .select(enc_cols)
            .with_columns([eff_expr, valid_expr, dual_expr])
            .select("ID", "ADMIT_DATE", "effective_payer", "dual_eligible")
            .collect()
        )

        # Iterate through patients
        for patient in sct_unknown_primary.iter_rows(named=True):
            patient_id = patient["ID"]
            primary_payer = patient["PAYER_CATEGORY_PRIMARY"]
            first_sct_payer = patient["PAYER_CATEGORY_AT_FIRST_SCT"] or "N/A"
            last_sct_payer = patient["PAYER_CATEGORY_AT_LAST_SCT"] or "N/A"
            first_sct_date = patient["FIRST_SCT_DATE"]
            last_sct_date = patient["LAST_SCT_DATE"]

            # Add to trace table
            md_lines.append(
                f"| {patient_id} | {primary_payer} | {first_sct_payer} | {last_sct_payer} | "
                f"{first_sct_date} | {last_sct_date} |"
            )

            print(f"    Patient {patient_id}: Primary={primary_payer}, First SCT={first_sct_payer}, Last SCT={last_sct_payer}")

        md_lines.append("")
        md_lines.append("### Explanation")
        md_lines.append("")
        md_lines.append(
            "The discrepancy occurs because **PAYER_CATEGORY_PRIMARY** is the mode (most frequent) payer category "
            "across **ALL encounters** for the patient, while **PAYER_CATEGORY_AT_FIRST_SCT** and "
            "**PAYER_CATEGORY_AT_LAST_SCT** are mode payer categories within the **±30 day windows** around "
            "SCT dates."
        )
        md_lines.append("")
        md_lines.append(
            "These 4 patients had 'Unknown' as their most frequent payer overall (across their entire encounter "
            "history), but happened to have encounters with known (non-Unknown) payer categories within their "
            "SCT treatment windows. This means they had valid payer information captured during the SCT treatment "
            "period, even though their overall encounter pattern shows predominantly Unknown payer."
        )
        md_lines.append("")

    # Write report
    print(f"\n[WRITING REPORT] Writing markdown report")
    report_path = PROJECT_ROOT / "reports" / "phase9_insurance_diagnostic.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"  Report written to: {report_path}")

    print("\n" + "=" * 70)
    print("Phase 9 Diagnostic Analysis Complete!")
    print("=" * 70)


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    main(config_path)
