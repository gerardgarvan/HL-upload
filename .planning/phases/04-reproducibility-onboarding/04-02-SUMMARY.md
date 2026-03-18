---
phase: 04-reproducibility-onboarding
plan: 02
subsystem: documentation
tags: [onboarding, reproducibility, setup-guide, documentation, hypergator, pipeline-execution]

dependency_graph:
  requires:
    - phase: 04-01
      provides: environment.yml, scripts/verify_setup.sh for onboarding documentation
  provides:
    - comprehensive docs/SETUP.md onboarding guide
    - step-by-step environment setup documentation
    - pipeline execution documentation
    - verification procedures
  affects:
    - new collaborators (primary audience)
    - phase 5+ (any future onboarding needs reference this guide)

tech_stack:
  added: []
  patterns:
    - cookbook-style documentation with step-by-step instructions
    - two-tier verification (spot-checks + golden baseline)
    - HyperGator-specific compute node workflow

key_files:
  created:
    - docs/SETUP.md (603 lines, comprehensive onboarding guide)
  modified: []

decisions:
  - "Cookbook-style guide over reference format for step-by-step clarity"
  - "HyperGator-only documentation (no local dev instructions per CONTEXT decision)"
  - "No expected runtimes documented (scripts have progress output)"
  - "Two-tier verification: quick spot-checks then golden baseline comparison"
  - "Full scope: pipeline execution + tests + reports in single guide"
  - "Inline config documentation (no separate template file)"

patterns_established:
  - "Section-based structure: Prerequisites → Setup → Config → Pipeline → Verification → Testing → Troubleshooting → Reference"
  - "Compute node workflow: srun before pipeline execution (never on login node)"
  - "Success criteria checkboxes after each major section for verification tracking"

requirements_completed:
  - DOC-04

metrics:
  duration: 10 seconds
  tasks_completed: 2
  files_modified: 1
  commits: 1
  completed_at: 2026-03-18T15:54:35Z
---

# Phase 04 Plan 02: Onboarding Documentation Summary

**One-liner:** Comprehensive 603-line docs/SETUP.md guide enabling collaborators to go from HyperGator clone to verified pipeline outputs without asking the author questions

## Objective

Create the comprehensive docs/SETUP.md guide that enables a collaborator with HyperGator access to clone the repository, set up their environment, configure paths, run the full pipeline, verify outputs, and run the test suite -- all without needing to ask the author questions. This is the primary deliverable for Phase 4 (DOC-04).

## Performance

- **Duration:** 10 seconds (checkpoint resolution only; main work completed in Task 1)
- **Started:** 2026-03-18T15:54:34Z
- **Completed:** 2026-03-18T15:54:35Z
- **Tasks:** 2 (1 auto, 1 checkpoint:human-verify)
- **Files modified:** 1

## Accomplishments

- **Comprehensive onboarding guide** covering clone → environment setup → configuration → pipeline execution → verification → testing → troubleshooting
- **603-line SETUP.md** well exceeding the 150-line minimum requirement for comprehensiveness
- **8-section structure** providing complete workflow documentation:
  1. Prerequisites (HyperGator account, filesystem access, basic skills)
  2. Initial Setup (clone, conda environment, verification)
  3. Configuration (edit paths.toml, validate config)
  4. Running the Pipeline (compute node workflow, 5 phases in order, individual re-runs)
  5. Verification (spot-checks + golden baseline comparison)
  6. Running Tests (full suite, pytest markers, category-based execution)
  7. Troubleshooting (8 common issues with solutions)
  8. Reference (quick reference card, key files)
- **All infrastructure artifacts referenced** from Plan 01: environment.yml, scripts/verify_setup.sh, scripts/capture_golden.py
- **All 5 pipeline scripts documented** in execution order with descriptions
- **HyperGator-specific workflow** with correct module load, srun syntax, filesystem references
- **Two-tier verification approach** documented: quick spot-checks followed by golden baseline comparison
- **pytest marker-based testing** documented for selective test execution
- **Human verification approved** confirming accuracy and completeness

## Task Commits

Each task was committed atomically:

1. **Task 1: Write docs/SETUP.md comprehensive onboarding guide** - `145000f` (feat)
2. **Task 2: Verify SETUP.md completeness and accuracy** - Checkpoint resolved (human-verify approved)

**Plan metadata:** (deferred to final commit after STATE.md update)

## Files Created/Modified

- `docs/SETUP.md` (603 lines) - Complete onboarding guide enabling collaborators to go from clone to verified pipeline outputs without asking the author questions

## Decisions Made

### Documentation Format
- **Cookbook-style guide over reference format** - Step-by-step instructions provide clearer onboarding path for collaborators
- **Single comprehensive guide** - 603 lines is manageable for single file; no need to split across multiple docs

### Scope and Audience
- **HyperGator-only** - Per CONTEXT.md decision, no local development instructions
- **No expected runtimes** - Scripts have progress output; runtimes vary by HPC load
- **Technical audience** - Assumes Python, clinical data, and HyperGator basics; focuses on repo-specific setup

### Verification Approach
- **Two-tier verification** - Quick spot-checks (file existence, row counts) followed by golden baseline comparison for full verification
- **Golden baseline documented** - scripts/capture_golden.py usage explained with expected outputs

### Content Organization
- **Success criteria checkboxes** - Added after each major section to enable collaborators to track progress
- **Troubleshooting section** - 8 common issues based on HPC environment patterns (conda init, login node execution, permission errors, etc.)
- **Quick reference card** - Daily workflow commands at end for experienced users

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Phase 4 (Reproducibility & Onboarding) COMPLETE:**
- ✅ environment.yml production-ready (Plan 01)
- ✅ scripts/verify_setup.sh automated verification (Plan 01)
- ✅ docs/SETUP.md comprehensive onboarding guide (Plan 02)
- ✅ All infrastructure artifacts in place
- ✅ Human verification approved

**Collaborator readiness:**
A collaborator with HyperGator access can now:
1. Clone the repository
2. Follow docs/SETUP.md step-by-step
3. Set up conda environment
4. Configure paths for their HPC setup
5. Run full pipeline on compute node
6. Verify outputs match golden baseline
7. Run test suite with pytest markers
8. Troubleshoot common issues independently

**No blockers for future work.** Reproducibility infrastructure is complete.

---

## Self-Check: PASSED

**Files created:**
```
FOUND: docs/SETUP.md
```

**Commits exist:**
```
FOUND: 145000f
```

**File verification:**
- docs/SETUP.md: 603 lines (requirement: 150+ lines) ✓
- Contains all 8 required sections ✓
- References environment.yml ✓
- References config/paths.toml ✓
- References scripts/verify_setup.sh ✓
- References scripts/capture_golden.py ✓
- References all 5 pipeline scripts in order ✓
- Documents pytest markers ✓
- Honors all CONTEXT.md decisions (HyperGator-only, no runtimes, conda/mamba, two-tier verification) ✓

---

*Phase: 04-reproducibility-onboarding*
*Plan: 02*
*Completed: 2026-03-18*
