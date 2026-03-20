---
phase: 07-present-insurance-tables-in-nice-powerpoint
plan: 01
subsystem: reporting
tags: [powerpoint, python-pptx, insurance, UF-branding, presentation]

# Dependency graph
requires:
  - phase: 05-insurance-by-treatment-analysis
    provides: CSV tables for 4 treatment cohorts (overview, chemo, radiation, SCT)
  - phase: 06-post-treatment-insurance-most-prevalent-payer-after-last-chemo-radiation-or-sct-date
    provides: CSV tables for post-treatment insurance (combined + 3 cohorts)
provides:
  - PowerPoint generation script (build_insurance_presentation.py)
  - UF Health-branded presentation template with native editable tables
  - 9-slide presentation structure (title + 8 table slides)
affects: [presentation-workflow, reporting]

# Tech tracking
tech-stack:
  added:
    - python-pptx: PowerPoint generation library for native table creation
  patterns:
    - UF Health color branding (blue #003087, orange #FA4616)
    - Alternating row colors for visual clarity (light blue/orange tints)
    - Native PowerPoint tables (not embedded images) for editability
    - Graceful CSV reading with error handling for missing files

key-files:
  created:
    - scripts/build_insurance_presentation.py
  modified: []

key-decisions:
  - "UF Health branding: Blue #003087 and orange #FA4616 with alternating light tints for table rows"
  - "Native PowerPoint tables (add_table) instead of embedded PNG images for editability"
  - "16:9 aspect ratio (Inches(10) x Inches(5.625)) for modern presentation displays"
  - "Slide order follows treatment grouping: Title, Overview, Combined Post, then paired Phase 5/6 tables per treatment type"
  - "Cohort size N=X in subtitle (not title) for cleaner slide headers"
  - "Blank slide layout (index 6) for full control - no template placeholders"

patterns-established:
  - "python-pptx pitfall avoidance: fill.solid() before fill.fore_color.rgb, cell.vertical_anchor (not text_frame), Pt()/Inches() wrappers"
  - "Graceful degradation: script continues with available CSV files, only fails if ALL missing"
  - "Date-stamped output: insurance_tables_YYYY-MM-DD.pptx for version tracking"

requirements-completed: []

# Metrics
duration: 6min
completed: 2026-03-20
---

# Phase 07 Plan 01: PowerPoint Presentation Generation Summary

**One-liner:** UF Health-branded PowerPoint generation script assembling 8 insurance summary tables into 9-slide presentation with native editable tables and consistent blue/orange color scheme

## Performance

- **Duration:** 6 minutes
- **Started:** 2026-03-20T16:36:59Z
- **Completed:** 2026-03-20T16:42:59Z
- **Tasks:** 2
- **Files created:** 1

## Accomplishments

- Created `build_insurance_presentation.py` (520 lines) generating 9-slide PowerPoint presentation
- Implemented UF Health branding with hex colors #003087 (blue) and #FA4616 (orange)
- Native PowerPoint tables with alternating light blue/orange row colors for visual clarity
- Title slide with cohort sizes (total, chemo, radiation, SCT)
- 8 table slides following treatment grouping: Overview → Combined Post → Chemo → Chemo Post → Radiation → Radiation Post → SCT → SCT Post
- Graceful error handling for missing CSV files with informative warnings
- Date-stamped output: reports/insurance_tables_YYYY-MM-DD.pptx

## Task Commits

1. **Task 1: Create build_insurance_presentation.py with complete slide generation** - `17fcd2d` (feat)
2. **Task 2: Verify script structure and PowerPoint correctness via code review** - No commit (verification only, all checks passed)

## Files Created/Modified

- `scripts/build_insurance_presentation.py` - PowerPoint generation script reading Phase 5/6 CSVs, creating 9-slide UF-branded presentation with native tables

## Decisions Made

**UF Health color branding:** Used exact UF brand colors (blue #003087, orange #FA4616) with RGBColor.from_string() (no # prefix). Header rows use solid UF_BLUE background with white text. Data rows alternate between LIGHT_BLUE and LIGHT_ORANGE tints for visual clarity.

**Native tables over embedded images:** Used pptx add_table() to create editable PowerPoint tables instead of embedding PNG images. This allows collaborators to edit table content, adjust formatting, and copy cells directly in PowerPoint without returning to Python.

**Slide organization:** Followed CONTEXT.md locked decision to group by treatment type: Title slide, then Overview (all patients), then Combined Post-Treatment (all patients), then paired Phase 5/6 tables for each treatment (Chemo, Radiation, SCT). Each pair shows insurance at treatment dates (Phase 5) followed by post-treatment insurance (Phase 6).

**Cohort size placement:** Placed N=X in subtitle (not title) per CONTEXT.md decision. Keeps titles clean and descriptive ("Chemotherapy Insurance") while providing essential context in subtitle ("Insurance at primary, first, and last chemotherapy — N = 1,234").

**Blank slide layout:** Used prs.slide_layouts[6] (blank layout) instead of layout[0] (title layout) to avoid unpredictable template placeholders and maintain full control over positioning.

**16:9 aspect ratio:** Set slide dimensions to Inches(10) x Inches(5.625) for modern widescreen displays (standard for most projectors and screens).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing python-pptx dependency**
- **Found during:** Task 1 verification
- **Issue:** ModuleNotFoundError: No module named 'pptx' - python-pptx library not installed in environment
- **Fix:** Ran `python -m pip install python-pptx` (installed v1.0.2 + XlsxWriter dependency)
- **Rationale:** Required dependency for script execution (Rule 3: blocking issue preventing task completion)
- **Files modified:** None (system-level package installation)
- **Verification:** Import check passed after installation

## Issues Encountered

**Data execution blocked by missing prerequisite CSVs:** Phase 5 and Phase 6 scripts (build_insurance_by_treatment.py, build_post_treatment_insurance.py) were created and committed but never executed on HPC with real data. The required CSV input files (8 tables in reports/insurance_by_treatment/ and reports/post_treatment_insurance/) do not exist in the current environment. This is expected per SETUP.md - scripts are designed for HPC execution with access to /orange and /blue filesystems.

**Consequence:** Script cannot be fully tested until prerequisite scripts are run on HPC to generate CSV files. Verification completed via code inspection, syntax checking, and pattern analysis (same pattern used for Phase 5 and 6 completion).

**Workaround for local development:** Script includes graceful error handling with _read_csv_safe() function - warns about missing files but continues with available data. Fatal error only if ALL 8 CSVs missing.

## User Setup Required

**Before first execution:**
1. Run Phase 5 script on HPC: `python scripts/build_insurance_by_treatment.py`
2. Run Phase 6 script on HPC: `python scripts/build_post_treatment_insurance.py`
3. Verify 8 CSV files created in reports/insurance_by_treatment/ (4 files) and reports/post_treatment_insurance/ (4 files)
4. Then run Phase 7 script: `python scripts/build_insurance_presentation.py`

**Note:** python-pptx library now installed in current environment. If running on HPC, may need to install in conda environment: `conda install -c conda-forge python-pptx`

## Next Phase Readiness

**Phase 7 complete:** PowerPoint generation script ready for execution once prerequisite CSV files are generated. Script follows established project patterns (PROJECT_ROOT, sys.path, load_and_validate_config) and integrates cleanly into existing pipeline.

**Script is re-runnable:** Reads only from CSV files, no side effects. Can be re-executed any time source data updates to generate fresh date-stamped presentations.

**Native table format enables collaboration:** PowerPoint output uses native editable tables (not images), allowing collaborators to adjust formatting, add annotations, or copy data directly in PowerPoint without Python expertise.

## Verification Summary

**All CONTEXT.md locked decisions verified correct:**

1. ✅ **Slide organization:** Title → Overview → Combined Post → Chemo → Chemo Post → Radiation → Radiation Post → SCT → SCT Post (9 slides, no dividers, no summary slide)
2. ✅ **Visual design:** UF blue #003087, orange #FA4616, native tables (add_table), no Pastel1, no template
3. ✅ **Content:** Title + subtitle on each table slide, N=X in subtitle, 4 cohort sizes on title slide, no key findings callouts
4. ✅ **Output:** Date-stamped filename insurance_tables_YYYY-MM-DD.pptx in reports/ directory, re-runnable
5. ✅ **Technical correctness:** All 8 CSVs referenced, N_Pct columns used, 16:9 dimensions, cell.vertical_anchor (not text_frame), Pt()/Inches() wrappers

**python-pptx pitfalls avoided:**
- ✅ fill.solid() before fill.fore_color.rgb (5 of each, matched 1:1)
- ✅ cell.vertical_anchor (not text_frame.vertical_anchor) - 0 wrong patterns found
- ✅ RGBColor.from_string() without # prefix
- ✅ Pt() for all font sizes, Inches() for all positioning
- ✅ Blank layout (index 6) for full control

**Syntax and imports:**
- ✅ Python syntax check passed
- ✅ python-pptx imports resolved after installation
- ✅ All required constants defined (UF_BLUE, UF_ORANGE, colors, PAYER_CATEGORY_ORDER)
- ✅ All 8 CSV filenames correctly referenced in code

## Self-Check: PASSED

Verified all claims before state updates:

**Created files:**
```bash
[ -f "scripts/build_insurance_presentation.py" ] && echo "FOUND: scripts/build_insurance_presentation.py" || echo "MISSING: scripts/build_insurance_presentation.py"
```
**Result:** FOUND: scripts/build_insurance_presentation.py

**Commits:**
```bash
git log --oneline --all | grep -q "17fcd2d" && echo "FOUND: 17fcd2d" || echo "MISSING: 17fcd2d"
```
**Result:** FOUND: 17fcd2d

**Line count:**
```bash
wc -l scripts/build_insurance_presentation.py
```
**Result:** 531 scripts/build_insurance_presentation.py (meets min_lines: 200 requirement)

---
*Phase: 07-present-insurance-tables-in-nice-powerpoint*
*Completed: 2026-03-20*
