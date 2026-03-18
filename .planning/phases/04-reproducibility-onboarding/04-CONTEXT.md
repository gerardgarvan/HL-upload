# Phase 4: Reproducibility & Onboarding - Context

**Gathered:** 2026-03-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Enable a collaborator to clone the repo, follow setup documentation, and reproduce pipeline outputs on HyperGator. Covers environment setup, configuration, pipeline execution, test running, and report generation. Does NOT add new pipeline features or change existing behavior.

</domain>

<decisions>
## Implementation Decisions

### Guide structure & depth
- Audience is a co-author/collaborator who knows Python, clinical data, and HyperGator basics — needs repo-specific setup only, not general HPC tutorials
- Guide covers the full scope: pipeline execution + running tests + generating reports
- No expected runtimes — scripts have progress output already

### Environment setup
- Use conda/mamba for environment management (HPC standard)
- Create an environment.yml from current dependencies as part of this phase
- HyperGator-only — no local development instructions needed
- Document required HyperGator module load commands

### Path & config approach
- Raw input CSVs live in a shared location on HyperGator (e.g., /orange/research/...)
- Document the config in SETUP.md rather than creating a separate template file

### Verification & troubleshooting
- Two-tier verification: quick spot-checks first (row counts, file existence), then golden baseline comparison for full verification
- No expected runtimes section

### Claude's Discretion
- Guide format: step-by-step cookbook vs reference style — pick best for this audience
- Single SETUP.md vs split docs — decide based on content length
- Path config approach: config file variables vs symlinks vs whatever the pipeline currently uses
- Whether to document output paths (depends on if they need explaining)
- Troubleshooting depth: common errors section vs minimal based on what's likely to trip people up
- Whether to document individual stage re-runs (depends on script independence)

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-reproducibility-onboarding*
*Context gathered: 2026-03-17*
