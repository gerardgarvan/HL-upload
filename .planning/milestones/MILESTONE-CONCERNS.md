# Milestone: Codebase Concerns Remediation

**Project:** HL Data Loading & Cleaning Pipeline  
**Study:** UFPTI 2405-HLX17A — Insurance Inequities in Hodgkin Lymphoma  
**Created:** 2026-03-09  
**Scope:** Additive — addresses CONCERNS.md; does not duplicate Phases 1–7  
**Prerequisites:** Phases 1–7 complete (Phase 7 modality flags done)

---

## Milestone Goal

Resolve technical debt, configuration confusion, and quality gaps documented in [.planning/codebase/CONCERNS.md](../codebase/CONCERNS.md) so the pipeline is production-ready, maintainable, and HIPAA-compliant.

---

## Success Criteria

When this milestone completes, the following must be true:

1. **Pipeline runs end-to-end without failure** — openpyxl present; LAB_RESULT vs LAB_RESULT_CM resolved; paths resolve correctly on HPC.
2. **Path configuration is unambiguous** — orange/blue roots and parquet layout documented and verified; config supports both local dev and HPC.
3. **All report outputs use small-cell suppression** — every report path (markdown, CSV, site_table) applies `flag_small_cell` or `_suppress`; no raw counts 1–10.
4. **Fragile dependencies are documented or mitigated** — Outcomes.xlsx schema documented; date parsing fallbacks explicit.
5. **Test coverage improves** — pytest suite exists; critical functions (`flag_small_cell`, `add_modality_flags`, convert/validate entry points) have tests.
6. **Developer tooling in place** — ruff or black configured; pyproject.toml for consistency.

---

## Phase/Task Breakdown

Tasks are ordered by critical path (blockers first) and priority.

### Tier 1: Critical Path (Must Fix First)

| # | Task | Description | Effort | Links |
|---|------|-------------|--------|-------|
| T1 | **Add openpyxl to environment** | Add `openpyxl` to `environment.yml` pip section so `pd.read_excel` in `outcomes_flags.py` works; `assemble_clean.py` fails without it | 0.25 day | Phase 7, [CONCERNS.md § Dependencies](../codebase/CONCERNS.md) |
| T2 | **Resolve LAB_RESULT vs LAB_RESULT_CM** | Verify actual filename on HPC (`LAB_RESULT_Mailhot_V1.csv` vs `LAB_RESULT_CM_Mailhot_V1.csv`); add alias mapping in schema/convert if datastructure uses LAB_RESULT; update datastructure.txt if HPC uses LAB_RESULT_CM | 0.5 day | Phase 2, 3, 5, 7; [CONCERNS.md § Tech Debt](../codebase/CONCERNS.md) |
| T3 | **Verify and document path resolution** | Clarify `parquet_dir`: config uses `hpc-upload/parquet`; config.py resolves as `scratch_root / parquet_rel` (→ `/blue/.../hpc-upload/parquet`). Document intended layout (scratch_root/hl-clean/parquet vs project/hpc-upload/parquet) and fix config/defaults | 0.5 day | Phases 1, 2, 6; [CONCERNS.md § Data Paths](../codebase/CONCERNS.md) |

### Tier 2: Security & Integrity

| # | Task | Description | Effort | Links |
|---|------|-------------|--------|-------|
| T4 | **Audit all report paths for small-cell suppression** | Ensure every report script uses `flag_small_cell` (markdown) or `_suppress` (CSV) for counts 1–10. Checklist: `assemble_clean.py`, `clean_all.py`, `validate_all.py`, `validate_values.py`, `build_site_table.py`, `site_table.py` | 0.5 day | Phase 6, REQ-05; [CONCERNS.md § Security](../codebase/CONCERNS.md) |
| T5 | **Document hpc-upload sync strategy** | Treat `hpc-upload/` as deploy copy; add sync script or README step: copy scripts/src/config from project root before HPC runs; reduce divergence risk | 0.25 day | [CONCERNS.md § Duplicate code paths](../codebase/CONCERNS.md) |

### Tier 3: Fragile Areas & Documentation

| # | Task | Description | Effort | Links |
|---|------|-------------|--------|-------|
| T6 | **Document Outcomes.xlsx schema** | Add schema doc: columns (Modality, Code system, Code), forward-fill rules; `load_outcomes_code_lookup` expectations; warn on layout changes | 0.25 day | Phase 7; [CONCERNS.md § Outcomes.xlsx](../codebase/CONCERNS.md) |
| T7 | **Document date parsing fallbacks** | Consolidate date format handling: SAS DATE9., DATETIME, YYYYMMDD, MM/DD/YYYY; document in CLEANING_DECISIONS or code; >10% parse failure → keep as string | 0.25 day | Phase 2, 4, 5; [CONCERNS.md § Date parsing](../codebase/CONCERNS.md) |

### Tier 4: Test Coverage

| # | Task | Description | Effort | Links |
|---|------|-------------|--------|-------|
| T8 | **Add pytest and initial tests** | Add pytest to environment; create `tests/` dir; smoke test remains, add unit tests for: `flag_small_cell` (0, 1, 10, 11), `_suppress`, `load_outcomes_code_lookup` (mock Excel) | 1 day | [CONCERNS.md § Test Coverage](../codebase/CONCERNS.md); [TESTING.md](../codebase/TESTING.md) |
| T9 | **Test convert/validate entry points** | Tests for `validate_table_schema`, `check_patid_integrity`, `verify_hl_cohort` with minimal fixtures; `add_modality_flags` integration test with synthetic parquet | 1 day | Phases 2, 3, 7; [TESTING.md § Gaps](../codebase/TESTING.md) |

### Tier 5: Developer Tooling & Nice-to-Have

| # | Task | Description | Effort | Links |
|---|------|-------------|--------|-------|
| T10 | **Add ruff/black and pyproject.toml** | Configure ruff (lint) and black (format) or ruff format; pyproject.toml with tool config; pre-commit or CI suggestion | 0.5 day | [CONCERNS.md § Missing features](../codebase/CONCERNS.md) |
| T11 | **Incremental convert (optional)** | Add skip-existing to `convert_all.py`: if Parquet exists and CSV mtime ≤ Parquet mtime, skip; reduces re-run time | 0.5 day | Phase 2; [CONCERNS.md § Incremental convert](../codebase/CONCERNS.md) |

---

## Links to Existing ROADMAP Phases

| Phase | Relevance to Milestone |
|-------|------------------------|
| **Phase 1** | Path config, environment (openpyxl), hpc-upload layout |
| **Phase 2** | Convert logic; LAB_RESULT_CM filename; date parsing; incremental convert |
| **Phase 3** | Structural validation; LAB_RESULT_CM in ENCOUNTER_LINKED; path resolution |
| **Phase 4** | Value validation; date parsing; report suppression |
| **Phase 5** | Dedup; LAB_RESULT_CM in DEDUP_KEYS; report suppression |
| **Phase 6** | assemble_clean; report suppression; quality_report; path derivation |
| **Phase 7** | outcomes_flags; openpyxl; Outcomes.xlsx schema; add_modality_flags tests |

---

## Dependencies

- **Internal:** Phases 1–7 complete (assumed).
- **External:** None.
- **Task dependencies:**
  - T1 must complete before `assemble_clean.py` (and thus Phase 7 modality flags) runs reliably.
  - T2 blocks convert/validate if filename mismatch causes missing LAB_RESULT_CM.
  - T4 depends on T1 (assemble_clean must run to audit its output paths).
  - T8/T9 can run in parallel after T1–T3.

---

## Estimated Effort

| Tier | Tasks | Effort |
|------|-------|--------|
| Tier 1 (Critical) | T1–T3 | 1.25 days |
| Tier 2 (Security) | T4–T5 | 0.75 day |
| Tier 3 (Fragile) | T6–T7 | 0.5 day |
| Tier 4 (Tests) | T8–T9 | 2 days |
| Tier 5 (Tooling) | T10–T11 | 1 day |
| **Total** | 11 tasks | **5.5 days** |

**Recommended sequencing:** T1 → T2 → T3 (critical path); then T4–T5 (security); T6–T7 (docs); T8–T9 (tests); T10–T11 (nice-to-have).

---

## Traceability: CONCERNS → Tasks

| CONCERNS.md Section | Addressed By |
|---------------------|--------------|
| Tech Debt: LAB_RESULT vs LAB_RESULT_CM | T2 |
| Tech Debt: hpc-upload duplication | T5 |
| Tech Debt: parquet_dir config confusion | T3 |
| Data Paths: orange/blue HPC resolution | T3 |
| Data Paths: parquet_dir vs scratch_root | T3 |
| Dependencies: openpyxl missing | T1 |
| Security: small-cell suppression audit | T4 |
| Test coverage gaps | T8, T9 |
| Fragile: Outcomes.xlsx schema | T6 |
| Fragile: date parsing edge cases | T7 |
| Missing: ruff/black | T10 |
| Missing: incremental convert | T11 |

---

*Milestone created: 2026-03-09*
