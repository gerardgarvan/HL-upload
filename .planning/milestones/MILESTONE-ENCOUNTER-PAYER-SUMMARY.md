# Milestone: ENCOUNTER Patient-Level Summary (Payer Focus)

**Project:** HL Data Loading & Cleaning Pipeline  
**Study:** UFPTI 2405-HLX17A — Insurance Inequities in Hodgkin Lymphoma  
**Created:** 2026-02-27  
**Scope:** Extend patient-level outputs with ENCOUNTER-derived, payer-focused summaries  
**Prerequisites:** Phases 1–7 complete; `patient_level.parquet` and `assemble_clean` pipeline

---

## Milestone Goal

Summarize the ENCOUNTER table at the patient level, with emphasis on **payer** (PAYER_TYPE_PRIMARY), to support insurance inequities analysis. One row per patient, with derived variables capturing encounter counts, payer mix, and payer stability.

---

## Success Criteria

When this milestone completes, the following must be true:

1. **Patient-level ENCOUNTER summary exists** — one row per patient (HL cohort or all patients with encounters) with encounter-derived variables.
2. **Payer-focused variables are defined and implemented** — counts by payer type, primary payer, payer transitions.
3. **Output is consumable** — Parquet or CSV; small-cell suppression applied to any published aggregates.
4. **Codebook updated** — `docs/CODEBOOK.md` documents new variables.
5. **Integration** — summary can be joined to `patient_level.parquet` or output as `encounter_payer_summary.parquet` for downstream analysis.

---

## Phase/Task Breakdown

### Core Tasks

| # | Task | Description | Effort | Output |
|---|------|-------------|--------|--------|
| E1 | **Build encounter-payer summary module** | Aggregate ENCOUNTER by ID: N_ENCOUNTERS, N_ENCOUNTERS_WITH_PAYER, distinct payer count, primary payer (most frequent PAYER_TYPE_PRIMARY), payer transition flag (1 = >1 distinct payer) | 1 day | `src/report/encounter_payer_summary.py` |
| E2 | **Define payer-derived variables** | Per patient: N_ENCOUNTERS, N_ENCOUNTERS_WITH_PAYER, N_DISTINCT_PAYERS, PAYER_PRIMARY (mode), PAYER_TRANSITION (0/1). Exclude NI/UN/OT from payer mode. Optional: ENC_TYPE mix | 0.5 day | Module + CODEBOOK |
| E3 | **Integrate into pipeline** | Call encounter summary from assemble_clean or add separate script; write `derived/encounter_payer_summary.parquet`; join to patient_level if desired | 0.5 day | `scripts/assemble_clean.py` or `scripts/build_encounter_summary.py` |
| E4 | **Apply small-cell suppression** | Any report or CSV output uses `_suppress`; markdown uses `flag_small_cell` | 0.25 day | Reports / CSVs |
| E5 | **Update CODEBOOK** | Add section for encounter-payer summary variables: definition, source fields, creation logic | 0.25 day | `docs/CODEBOOK.md` |

---

## Variables to Create

| Variable | Type | Creation logic |
|----------|------|----------------|
| `N_ENCOUNTERS` | Int64 | Count of ENCOUNTER rows per patient |
| `N_ENCOUNTERS_WITH_PAYER` | Int64 | Count of rows where PAYER_TYPE_PRIMARY is non-null, non-empty, not in {NI, UN, OT} |
| `N_DISTINCT_PAYERS` | Int64 | Count of distinct PAYER_TYPE_PRIMARY values (excluding NI/UN/OT) |
| `PAYER_PRIMARY` | String | Most frequent PAYER_TYPE_PRIMARY; null if none valid |
| `PAYER_TRANSITION` | Int8 | 1 if N_DISTINCT_PAYERS > 1; 0 otherwise |

**Existing payer variables (unchanged):**

- `PAYER_AT_DX` — PAYER_TYPE_PRIMARY from encounter closest to FIRST_HL_DX_DATE (±90 days); in `patient_level.parquet`
- `INSURANCE` — first known PAYER_TYPE_PRIMARY from ENCOUNTER (site_table)

---

## Links to Existing Phases

| Phase | Relevance |
|-------|-----------|
| **Phase 3** | Structural validation; ENCOUNTER schema; completeness by SOURCE |
| **Phase 5** | Dedup flags on ENCOUNTER; partner flags (ICD_MAPPED, etc.) |
| **Phase 6** | `build_patient_level_derived`; `PAYER_AT_DX`; `patient_level.parquet` |
| **Phase 7** | Modality flags; `assemble_clean` entry point |

---

## Dependencies

- **Internal:** Phases 1–7 complete; ENCOUNTER Parquet available.
- **External:** None.
- **Task dependencies:**
  - E2 refines E1; E1 and E2 can be done together.
  - E3 depends on E1/E2.
  - E4 and E5 can run in parallel with E3.

---

## Estimated Effort

| Task | Effort |
|------|--------|
| E1 | 1 day |
| E2 | 0.5 day |
| E3 | 0.5 day |
| E4 | 0.25 day |
| E5 | 0.25 day |
| **Total** | **2.5 days** |

---

## Traceability: Goal → Tasks

| Goal | Addressed By |
|------|--------------|
| Summarize ENCOUNTER at patient level | E1, E3 |
| Focus on payer | E1, E2 |
| Payer mix, transitions | E2 |
| Integrate into pipeline | E3 |
| HIPAA compliance (suppression) | E4 |
| Documentation | E5 |

---

*Milestone created: 2026-02-27*
