---
phase: 10-ci-precommit-hardening
plan: 01
subsystem: infra
tags: [ci, pre-commit, ruff, pytest, makefile]

requires:
  - plan: 09-01
    provides: Concerns remediation complete
provides:
  - .pre-commit-config.yaml — ruff + ruff-format + pytest hooks
  - Makefile — make test, make lint, make lint-fix, make ci
  - .github/workflows/ci.yml — lint and test jobs on push/PR
  - CONCERNS.md with Phase 8–9 resolved markers (already present)
affects: [developer-workflow, CI-pipeline]

key-files:
  verified:
    - .pre-commit-config.yaml
    - Makefile
    - .github/workflows/ci.yml
  modified: []

key-decisions:
  - "ruff-pre-commit v0.8.4; ruff + ruff-format; local pytest hook"
  - "Makefile: ci depends on lint then test; lint-fix for auto-format"
  - "CI: separate lint and test jobs; Python 3.11; pip install pytest polars pyarrow pandas tomli"

requirements-completed: [REQ-05, REQ-06]
autonomous: true
completed: 2026-02-27
---

# Phase 10 Plan 01: CI, Pre-commit, Pipeline Hardening — Summary

**Pre-commit hooks (ruff + pytest), Makefile (test, lint, ci), GitHub Actions CI, CONCERNS resolved markers. Phase 10 complete.**

## Task 1: Pre-commit — COMPLETE

`.pre-commit-config.yaml` exists with:
- default_language_version: python3.11
- ruff (--fix) and ruff-format hooks (astral-sh/ruff-pre-commit v0.8.4)
- local pytest hook: `python -m pytest tests/ -v`

## Task 2: Makefile — COMPLETE

`Makefile` has:
- `make test` — python -m pytest tests/ -v
- `make lint` — ruff check . ; ruff format --check .
- `make lint-fix` — ruff check . --fix ; ruff format .
- `make ci` — lint then test

## Task 3: CI Workflow — COMPLETE

`.github/workflows/ci.yml`:
- Triggers: push, pull_request (main, master)
- lint job: ruff check ., ruff format --check .
- test job: pip install pytest polars pyarrow pandas tomli; python -m pytest tests/ -v

## Task 4: CONCERNS.md — COMPLETE

CONCERNS.md already contains Phase 8–9 resolved markers for: openpyxl, LAB_RESULT, path resolution, small-cell audit, Outcomes/date docs, pytest, ruff, incremental convert.

## Task 5: STATE and ROADMAP — COMPLETE

- STATE.md: Phase 10 shown 100%
- ROADMAP.md: Phase 10 success criteria marked [x]

## Verification

- [x] 22 tests passed (pytest)
- [x] Artifacts present: .pre-commit-config.yaml, Makefile, .github/workflows/ci.yml
- [x] make test / make lint require make and ruff in PATH (typical on Linux/macOS or conda env)
