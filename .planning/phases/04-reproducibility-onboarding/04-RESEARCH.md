# Phase 4: Reproducibility & Onboarding - Research

**Researched:** 2026-03-18
**Domain:** Scientific computing reproducibility, HPC onboarding, Python environment management
**Confidence:** HIGH

## Summary

This phase focuses on creating documentation that enables a collaborator with HyperGator access to clone the repository, set up their environment, and reproduce all pipeline outputs. The research domain is well-established: Python scientific computing reproducibility, conda environment management on HPC systems, and onboarding documentation for research pipelines. The pipeline already has strong infrastructure (config/paths.toml, capture_golden.py for baseline verification, pytest test suite), which significantly simplifies documentation requirements.

**Key findings:**
- Modern reproducibility standard: environment.yml + lock file approach for both flexibility and exact reproduction
- HPC-specific setup: module load conda, conda init, environment activation workflow
- Two-tier verification already implemented: quick spot-checks (row counts, file existence) via pipeline scripts + golden baseline comparison via capture_golden.py
- Documentation best practice: step-by-step cookbook format for technical collaborators, with clear success criteria at each step
- Testing infrastructure complete: pytest with markers, conftest.py fixtures, make test target

**Primary recommendation:** Create a single comprehensive docs/SETUP.md following cookbook format (prerequisite check → environment setup → configuration → pipeline execution → verification → testing), with clear success criteria after each major step to enable self-service onboarding.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
**Guide structure & depth**
- Audience is a co-author/collaborator who knows Python, clinical data, and HyperGator basics — needs repo-specific setup only, not general HPC tutorials
- Guide covers the full scope: pipeline execution + running tests + generating reports
- No expected runtimes — scripts have progress output already

**Environment setup**
- Use conda/mamba for environment management (HPC standard)
- Create an environment.yml from current dependencies as part of this phase
- HyperGator-only — no local development instructions needed
- Document required HyperGator module load commands

**Path & config approach**
- Raw input CSVs live in a shared location on HyperGator (e.g., /orange/research/...)
- Document the config in SETUP.md rather than creating a separate template file

**Verification & troubleshooting**
- Two-tier verification: quick spot-checks first (row counts, file existence), then golden baseline comparison for full verification
- No expected runtimes section

### Claude's Discretion
- Guide format: step-by-step cookbook vs reference style — pick best for this audience
- Single SETUP.md vs split docs — decide based on content length
- Path config approach: config file variables vs symlinks vs whatever the pipeline currently uses
- Whether to document output paths (depends on if they need explaining)
- Troubleshooting depth: common errors section vs minimal based on what's likely to trip people up
- Whether to document individual stage re-runs (depends on script independence)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DOC-04 | Setup and reproducibility guide (docs/SETUP.md) enabling a collaborator to clone, configure, and run the pipeline | Cookbook-style documentation pattern with prerequisite checks, environment setup via conda/mamba, config/paths.toml editing, pipeline execution steps, two-tier verification (row counts + golden baseline), and test running with pytest |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| conda/mamba | Latest from HPC module | Environment management | Standard for HPC Python environments; handles non-Python dependencies like compilers, system libraries |
| environment.yml | N/A | Dependency specification | Standard conda format; supports both conda-forge and pip packages |
| conda-lock | Optional | Lock file generation | Industry standard for reproducible environments (transitively pinned dependencies) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| mamba | Latest | Faster dependency resolution | Always prefer over conda for installs/updates (10-50x faster) |
| conda env export | Built-in | Capture exact resolved versions | Generate lock file after successful environment creation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| conda/mamba | pip + venv | Conda handles non-Python dependencies (polars, pyarrow require system libraries); pip-only would fail on HPC |
| environment.yml | requirements.txt | environment.yml supports conda channels + pip packages in single file; requirements.txt is pip-only |
| Single SETUP.md | Split docs (SETUP.md + RUNNING.md + TESTING.md) | Single doc works well for ~200-300 line guides; split when exceeds ~500 lines or has distinct audiences |

**Installation:**
```bash
# On HyperGator, conda/mamba provided via module system
module load conda
conda init bash
# Logout and login for init to take effect
```

---

## Architecture Patterns

### Recommended Documentation Structure

**Single-file cookbook format** (best for collaborator audience with technical background):
```markdown
docs/SETUP.md
├── Prerequisites (HyperGator account, SSH keys, git basics)
├── Initial Setup (one-time)
│   ├── Clone repository
│   ├── Load conda module
│   ├── Create environment from environment.yml
│   └── Verify environment (python --version, import test)
├── Configuration (edit config/paths.toml)
│   ├── Verify source data path (/orange/...)
│   ├── Verify scratch path (/blue/...)
│   └── Test config loading (python -c "from src.load.config import load_and_validate_config; load_and_validate_config()")
├── Running the Pipeline
│   ├── Full pipeline (5 phases in order)
│   ├── Quick smoke test (scripts/pipeline_smoke_test.py)
│   └── Individual phase re-runs (if scripts support it)
├── Verification
│   ├── Quick spot-checks (row counts, file existence from script output)
│   └── Golden baseline comparison (python scripts/capture_golden.py, diff manifest)
├── Running Tests
│   ├── Full test suite (make test or pytest)
│   ├── Specific markers (pytest -m payer)
│   └── Expected output (all tests pass or known failures documented)
└── Troubleshooting
    ├── Common config errors (paths don't exist, permission denied)
    ├── Module/import errors (conda environment not activated)
    └── Memory/compute errors (use srun, not login node)
```

**Success criteria pattern** (insert after each major section):
```markdown
**Success criteria:**
- [ ] Command X produces output Y
- [ ] File Z exists at path W
- [ ] No error messages in stdout/stderr
```

This enables self-verification without needing to ask the author.

### Pattern 1: HPC Module + Conda Initialization

**What:** Standard HPC workflow for setting up conda in user environment
**When to use:** First-time setup on HyperGator or any HPC cluster with module system
**Source:** [NC State HPC Conda Documentation](https://hpc.ncsu.edu/Software/Apps.php?app=Conda), [NCAR HPC Conda Setup](https://ncar-hpc-docs.readthedocs.io/en/stable/environment-and-software/user-environment/conda/)

**Example:**
```bash
# Load conda module (makes conda command available)
module load conda

# Initialize conda for bash shell (one-time setup)
# This adds conda initialization to ~/.bashrc
conda init bash

# IMPORTANT: After conda init, must logout and login for changes to take effect
# After relogin, (base) environment automatically activates

# Create project environment from environment.yml
conda env create -f environment.yml

# Activate project environment
conda activate hl-eda

# Verify setup
python --version  # Should show Python 3.11
python -c "import polars; print(polars.__version__)"  # Should succeed
```

### Pattern 2: Two-File Environment Specification

**What:** Separate human-editable spec (environment.yml) from machine-generated lock file (environment_lock.yml)
**When to use:** Projects requiring both reproducibility (exact versions) and maintainability (ability to upgrade)
**Source:** [Python Speed: Reproducible Conda Environments](https://pythonspeed.com/articles/conda-dependency-management/), [Hydroinformatics: Reproducible Python Environments](https://medium.com/hydroinformatics/how-to-make-your-python-environment-reproducible-common-practices-conda-environment-de28195b74de)

**Example environment.yml (human-editable):**
```yaml
# environment.yml - Edit this to add/update dependencies
name: hl-eda
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - pandas>=2.2
  - pyarrow>=18.0
  - polars
  - duckdb
  - pip
  - pip:
    - pytest
    - ruff
```

**Generate lock file (machine-generated):**
```bash
# After successful environment creation, capture exact versions
mamba env export --no-builds > environment_lock.yml

# Or for maximum reproducibility (includes build strings):
mamba env export > environment_lock.yml.full
```

**Usage:**
- **Development:** Create from environment.yml, allows flexibility for upgrades
- **Production/Reproduction:** Create from environment_lock.yml, ensures exact versions
- **Both committed to git** for transparency

### Pattern 3: Configuration Validation with Fail-Fast

**What:** Validate all paths exist before pipeline execution begins
**When to use:** Any pipeline with external dependencies (data files, shared storage)
**Source:** Project already implements this pattern in src/load/config.py:validate_config()

**Example:**
```python
# src/load/config.py already implements this
from src.load.config import load_and_validate_config

# Script entry point
def main():
    # Fail-fast: catches config errors before pipeline starts
    paths = load_and_validate_config()  # Raises ValueError if paths invalid

    # If we reach here, all paths verified
    # ... pipeline logic ...
```

**For SETUP.md, document the validation command:**
```bash
# Test configuration without running full pipeline
python -c "from src.load.config import load_and_validate_config; load_and_validate_config()"

# Expected output:
============================================================
CONFIG VALIDATION PASSED
============================================================
  data_root:          /orange/erin.mobley-hl.bcu/Mailhot_V1_20250915 [OK]
  scratch_root:       /blue/erin.mobley-hl.bcu [OK]
  ...
```

### Pattern 4: Golden Baseline Verification

**What:** Capture checksums + schemas of pipeline outputs for regression detection
**When to use:** Scientific pipelines where data correctness is critical and outputs should be stable
**Source:** [Golden Tests in AI](https://www.shaped.ai/blog/golden-tests-in-ai), [ETL Testing Best Practices](https://www.integrate.io/blog/etl-testing-best-practices-tools-frameworks/)

**Example (project already implements scripts/capture_golden.py):**
```bash
# After successful pipeline run, capture baseline
python scripts/capture_golden.py

# Output: .golden/manifest.json (checksums, schemas, row counts - no PHI)

# After making changes and rerunning pipeline, verify no regressions
python scripts/capture_golden.py
# Script compares with existing manifest and reports:
#   - Added files
#   - Removed files
#   - Modified files (different checksum)
```

**For SETUP.md:**
```markdown
### Verification: Golden Baseline Comparison

After running the full pipeline, verify outputs match expected results:

\`\`\`bash
python scripts/capture_golden.py
\`\`\`

**Expected output:**
- If first run: "X files captured" (creates baseline)
- If subsequent run: "No changes detected" (outputs match baseline)
- If outputs changed: List of modified files with old/new checksums

**Interpreting results:**
- "No changes detected" → Pipeline reproduced correctly
- "Modified files" → Outputs differ from baseline (may indicate environment differences or legitimate data changes)
```

### Anti-Patterns to Avoid

- **Tutorial overload:** Don't explain basic Python/HPC concepts to audience who already knows them. Focus on repo-specific setup only.
- **Expected runtimes without progress output:** User decided against this because scripts already print progress. Don't document "this should take X minutes" since runtime varies by system.
- **Separate config template files:** User decided to document config inline in SETUP.md rather than create config/paths.toml.template. Keep it simple.
- **Local development instructions:** HyperGator-only per user decision. Don't document local conda setup on Windows/Mac.
- **Separate lock file before testing:** User already has environment.yml as draft. Generate lock file after successful HPC environment creation, not before.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Environment reproducibility | Manual dependency lists, version tracking in comments | conda environment.yml + conda env export | Conda handles transitive dependencies, system libraries, multi-platform compatibility; manual tracking always drifts |
| Regression detection | Ad-hoc checksum scripts, manual file comparisons | Project's capture_golden.py (already built) | Handles parquet schemas, row counts, binary files; structured JSON manifest for git; comparison logic built-in |
| Path validation | Try/except around file operations, cryptic "file not found" errors | Project's validate_config() (already built) | Fail-fast with structured error messages; distinguishes between missing files vs wrong type; creates output dirs automatically |
| Test organization | Loose test files, no grouping | pytest markers (already configured in pytest.ini) | Enables selective test runs (pytest -m payer); documents requirement coverage; integrates with CI |

**Key insight:** For reproducibility infrastructure (environments, validation, verification), using proven tools and patterns saves enormous debugging time. The cost of "just writing a quick script" is paid repeatedly as edge cases emerge (cross-platform differences, transitive dependency conflicts, data format evolution). This project already made good choices (conda, pathlib validation, pytest) - documentation should showcase these rather than rebuild them.

---

## Common Pitfalls

### Pitfall 1: conda init Not Taking Effect
**What goes wrong:** User runs `conda init bash`, immediately tries `conda activate hl-eda`, gets "conda: command not found" or "activate: no such command"
**Why it happens:** conda init modifies ~/.bashrc, but current shell hasn't sourced the updated file
**How to avoid:** Document that logout/login is required after conda init, not just "source ~/.bashrc"
**Warning signs:** "conda: command not found" after conda init, or "activate" not recognized as command

**Documentation solution:**
```markdown
### Initial Setup: Conda Environment

1. Load conda module:
   \`\`\`bash
   module load conda
   \`\`\`

2. Initialize conda for your shell (ONE-TIME SETUP):
   \`\`\`bash
   conda init bash
   \`\`\`

3. **IMPORTANT: Logout and login to HyperGator for changes to take effect**

   After relogin, you should see `(base)` in your prompt:
   \`\`\`
   (base) [username@login1 ~]$
   \`\`\`

4. Create project environment:
   \`\`\`bash
   conda env create -f environment.yml
   \`\`\`
```

### Pitfall 2: Running Pipeline on Login Node
**What goes wrong:** User runs memory-intensive pipeline scripts on login node, processes killed by HPC admin, user confused why "it just stopped"
**Why it happens:** Login nodes are shared resource for navigation/editing; compute should use interactive nodes (srun) or batch jobs
**How to avoid:** Document srun requirement upfront, before pipeline commands
**Warning signs:** "Killed" messages, mysterious process termination, angry emails from HPC admins

**Documentation solution:**
```markdown
### Running the Pipeline

**IMPORTANT:** Do not run pipeline scripts on the login node. Use an interactive compute node:

\`\`\`bash
# Request interactive session (adjust resources as needed)
srun --pty --mem=16gb --time=2:00:00 bash

# After srun starts, you'll see prompt change to compute node:
(hl-eda) [username@c0123a-s45 ~]$

# Now run pipeline scripts
python scripts/convert_all.py
python scripts/validate_all.py
# ... etc
\`\`\`

**Why:** Pipeline processes large clinical datasets (100K+ rows per table, 22 tables). Login nodes have strict memory limits and are shared resources.
```

### Pitfall 3: config/paths.toml Points to Wrong Data
**What goes wrong:** Pipeline fails with "FileNotFoundError: /orange/erin.mobley-hl.bcu/Mailhot_V1_20250915/DEMOGRAPHIC.csv" because user has different data location
**Why it happens:** config/paths.toml contains author's specific HyperGator paths, not generic placeholders
**How to avoid:** Document config file editing as explicit step with verification command
**Warning signs:** FileNotFoundError during convert_all.py, especially if path contains author's username

**Documentation solution:**
```markdown
### Configuration: Edit config/paths.toml

The config file contains paths specific to the original author's HyperGator setup. You MUST edit these paths to match your environment:

\`\`\`bash
nano config/paths.toml
# or
vim config/paths.toml
\`\`\`

**Required changes:**

1. **data_root**: Path to OneFlorida+ extract CSVs (usually /orange/...)
   ```toml
   data_root = "/orange/YOUR.GROUP/YOUR_DATA_LOCATION"
   ```

2. **scratch_root**: Path to your scratch/output space (usually /blue/...)
   ```toml
   scratch_root = "/blue/YOUR.GROUP"
   ```

**Verify configuration:**
\`\`\`bash
python -c "from src.load.config import load_and_validate_config; load_and_validate_config()"
\`\`\`

**Expected output:**
- "CONFIG VALIDATION PASSED" with all paths showing [OK]

**If validation fails:**
- "data_root=... Path does not exist" → Verify data location, check spelling, check permissions
- "scratch_root=... Failed to create directory" → Verify you have write permissions to /blue/YOUR.GROUP
```

### Pitfall 4: Environment Not Activated
**What goes wrong:** User installs dependencies, runs pipeline script, gets "ModuleNotFoundError: No module named 'polars'"
**Why it happens:** Installed packages into hl-eda environment but currently in (base) or no environment
**How to avoid:** Show conda activate in every code block that runs Python scripts; mention checking prompt
**Warning signs:** ImportError for packages that should be installed, wrong Python version

**Documentation solution:**
```markdown
**Before running any pipeline scripts, verify environment is activated:**

\`\`\`bash
# Your prompt should show the environment name:
(hl-eda) [username@c0123a-s45 project-dir]$
       ^^^
       This indicates hl-eda environment is active

# If you see (base) or no environment, activate:
conda activate hl-eda

# Verify Python version and key packages:
python --version  # Should show Python 3.11.x
python -c "import polars; print(polars.__version__)"  # Should succeed
\`\`\`
```

### Pitfall 5: Mamba vs Conda Confusion
**What goes wrong:** Documentation says "use mamba" but user doesn't have mamba installed, tries conda instead, gets slower installs or slightly different results
**Why it happens:** Mamba is optional accelerator, not always pre-installed; needs explicit installation or availability check
**How to avoid:** Document conda as baseline, mamba as optional speedup; show how to install mamba if desired
**Warning signs:** User asks "where is mamba?", slow environment creation, impatience

**Documentation solution:**
```markdown
### Environment Creation

Create the environment using conda (mamba is faster but optional):

\`\`\`bash
# Standard approach (always works):
conda env create -f environment.yml

# Faster alternative if mamba available (10-50x faster dependency resolution):
mamba env create -f environment.yml

# To install mamba (optional):
conda install -n base mamba
\`\`\`

**Note:** Both commands produce identical environments; mamba only affects installation speed.
```

---

## Code Examples

### Example 1: Complete Setup Verification Checklist

**Source:** Synthesis from [MSI Best Practices](https://msi.umn.edu/our-resources/knowledge-base/best-practices-conda) and project structure

```bash
#!/bin/bash
# setup_verification.sh - Run after completing SETUP.md steps
# Verifies environment and configuration before pipeline execution

echo "=== HyperGator Setup Verification ==="

# Check 1: Conda environment exists and is activated
if [[ $CONDA_DEFAULT_ENV == "hl-eda" ]]; then
    echo "✓ hl-eda environment activated"
else
    echo "✗ hl-eda environment not activated (current: $CONDA_DEFAULT_ENV)"
    echo "  Run: conda activate hl-eda"
    exit 1
fi

# Check 2: Python version
PYTHON_VERSION=$(python --version)
if [[ $PYTHON_VERSION == *"3.11"* ]] || [[ $PYTHON_VERSION == *"3.12"* ]] || [[ $PYTHON_VERSION == *"3.14"* ]]; then
    echo "✓ Python version: $PYTHON_VERSION"
else
    echo "✗ Unexpected Python version: $PYTHON_VERSION"
    exit 1
fi

# Check 3: Key dependencies importable
python -c "import polars, pandas, pyarrow, pytest" 2>/dev/null
if [[ $? -eq 0 ]]; then
    echo "✓ Core dependencies importable"
else
    echo "✗ Import failed - environment may be incomplete"
    exit 1
fi

# Check 4: Config validation
python -c "from src.load.config import load_and_validate_config; load_and_validate_config()" 2>/dev/null
if [[ $? -eq 0 ]]; then
    echo "✓ Configuration validated"
else
    echo "✗ Config validation failed - check config/paths.toml"
    exit 1
fi

# Check 5: On compute node (not login node)
if [[ $(hostname) == *"login"* ]]; then
    echo "⚠ Warning: Currently on login node - use 'srun --pty bash' for pipeline execution"
else
    echo "✓ On compute node: $(hostname)"
fi

echo "=== Setup verification complete ==="
```

### Example 2: Quick Pipeline Smoke Test

**Source:** Project already has scripts/pipeline_smoke_test.py

```markdown
### Quick Verification: Pipeline Smoke Test

Before running the full pipeline, verify setup with a smoke test:

\`\`\`bash
# Activate environment
conda activate hl-eda

# Request compute node
srun --pty --mem=4gb --time=30:00 bash

# Run smoke test (uses small subset of data)
python scripts/pipeline_smoke_test.py
\`\`\`

**Expected output:**
- "Config validation passed"
- "Testing Phase 1: convert..." (processes 1-2 small tables)
- "Testing Phase 2: validate..."
- "Smoke test passed"

**If smoke test passes:** Proceed to full pipeline
**If smoke test fails:** Review error messages, check config/paths.toml, verify data accessibility
```

### Example 3: Selective Test Execution

**Source:** pytest.ini already configured with markers

```bash
# Run full test suite
pytest tests/ -v

# Run only payer logic tests (TEST-01)
pytest tests/ -m payer -v

# Run only date parsing tests (TEST-02)
pytest tests/ -m dates -v

# Run tests for specific module
pytest tests/test_clean/ -v

# Run with coverage (if pytest-cov installed)
pytest tests/ --cov=src --cov-report=term-missing

# Expected output:
# - All tests should pass (or known failures documented)
# - Test markers shown in output (TEST-01, TEST-02, etc.)
# - Coverage report shows >80% for critical modules
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| requirements.txt only | environment.yml + conda/mamba | ~2018-2020 | Conda handles system dependencies (compilers, libraries) that pip cannot; critical for scientific Python (numpy, pandas, polars) |
| Manual version pinning | conda env export for lock files | ~2020-2022 | Captures transitive dependencies automatically; reproducible across platforms |
| Single environment.yml | Two-file pattern (loose spec + lock file) | ~2022-2024 | Balances maintainability (can upgrade) with reproducibility (exact versions) |
| conda only | mamba as accelerator | 2020-present | 10-50x faster dependency resolution; same lock file format |
| Ad-hoc verification scripts | Golden baseline testing pattern | AI era 2023+ | Structured approach to regression detection; borrowed from ML model testing |

**Deprecated/outdated:**
- **pip + virtualenv for scientific Python:** Still works for pure-Python packages, but fails for packages with C extensions or system library dependencies (polars, pyarrow, numpy, pandas all need system libraries). Conda remains superior for scientific computing environments.
- **Single global conda environment:** Older HPC tutorials suggested one shared environment per user. Modern best practice: one environment per project for isolation and reproducibility.
- **conda env export --from-history:** This flag was promoted for cross-platform compatibility but loses transitive dependencies. Current recommendation: export full environment for exact reproduction, maintain separate loose spec for cross-platform development.

---

## Open Questions

1. **Exact HyperGator module name for conda in 2026**
   - What we know: Generic HPC pattern is `module load conda` or `module load anaconda3`
   - What's unclear: UF HyperGator may have specific module name (conda, anaconda, anaconda3, miniconda3)
   - Recommendation: Document generic pattern, add note "If 'module load conda' fails, try 'module avail conda' to see available names"

2. **Whether to generate lock file as part of Phase 4 or defer**
   - What we know: Project has environment.yml with loose pins (pandas>=2.2, polars without version)
   - What's unclear: Should Phase 4 tasks include "run mamba env export > environment_lock.yml on HPC" or just document the process?
   - Recommendation: Include lock file generation as a task - it's one-time action that greatly improves reproducibility, and Phase 4 is the right time to do it

3. **Whether pipeline scripts support individual phase re-runs**
   - What we know: Scripts exist for each phase (convert_all.py, validate_all.py, clean_all.py, etc.)
   - What's unclear: Can you safely run clean_all.py without rerunning convert_all.py? Are there dependency assumptions?
   - Recommendation: Document full pipeline sequence as primary path, add note "Individual phase re-runs may be possible if intermediate outputs exist, but full pipeline run recommended for reproducibility"

4. **Estimated time for full pipeline run on typical HyperGator node**
   - What we know: User explicitly decided against documenting expected runtimes
   - What's unclear: This decision might be reconsidered if collaborator feedback suggests value
   - Recommendation: Follow user decision - do not document runtimes in Phase 4, revisit in future if collaborators request it

---

## Sources

### Primary (HIGH confidence)
- [University of Florida Research Computing Documentation](https://docs.rc.ufl.edu/) - Official HyperGator setup guide (accessed 2026-03-18)
- [NC State HPC Conda Documentation](https://hpc.ncsu.edu/Software/Apps.php?app=Conda) - HPC conda initialization patterns
- [NCAR HPC Conda Setup](https://ncar-hpc-docs.readthedocs.io/en/stable/environment-and-software/user-environment/conda/) - Module load + conda init workflow
- Project codebase (src/load/config.py, scripts/capture_golden.py, pytest.ini) - Existing infrastructure analysis

### Secondary (MEDIUM confidence)
- [Python Speed: Reproducible Conda Environments with conda-lock](https://pythonspeed.com/articles/conda-dependency-management/) - Two-file pattern (loose spec + lock file)
- [Hydroinformatics: Reproducible Python Environments](https://medium.com/hydroinformatics/how-to-make-your-python-environment-reproducible-common-practices-conda-environment-de28195b74de) - Best practices for environment.yml
- [Golden Tests in AI](https://www.shaped.ai/blog/golden-tests-in-ai) - Baseline verification pattern
- [Integrate.io: ETL Testing Best Practices](https://www.integrate.io/blog/etl-testing-best-practices-tools-frameworks/) - Pipeline verification strategies
- [Software Documentation Best Practices 2026](https://techlasi.com/savvy/software-documentation-best-practices/) - 63% faster onboarding with high-quality docs
- [Developer Onboarding Documentation Must-Haves](https://www.multiplayer.app/blog/developer-onboarding-documentation/) - Step-by-step setup guide patterns

### Tertiary (LOW confidence - verification recommended)
- [Minnesota Supercomputing Institute: Best Practices for Conda](https://msi.umn.edu/our-resources/knowledge-base/best-practices-conda) - General conda practices, not HyperGator-specific
- [Mamba User Guide](https://mamba.readthedocs.io/en/latest/user_guide/mamba.html) - Mamba vs conda performance claims (10-50x faster - not independently verified for this use case)

---

## Metadata

**Confidence breakdown:**
- **Standard stack:** HIGH - Conda/mamba for HPC scientific Python is industry standard with extensive documentation
- **Architecture patterns:** HIGH - HPC module system, conda init workflow, golden baseline testing all verified across multiple authoritative sources
- **Pitfalls:** HIGH - Common HPC/conda onboarding issues well-documented across multiple HPC centers
- **Lock file approach:** MEDIUM - Two-file pattern is emerging best practice but not yet universal; project already uses single environment.yml successfully

**Research date:** 2026-03-18
**Valid until:** 2026-09-18 (6 months - conda ecosystem stable, HPC practices evolve slowly)

**What might I have missed:**
- HyperGator-specific quirks (firewall issues, storage quotas, specific module names) - would need access to actual UF RC documentation or testing on HyperGator to verify
- Whether project has any undocumented setup steps that author does automatically (PATH modifications, additional config files, data preprocessing)
- Potential differences between HyperGator's conda version and documented best practices (older HPC clusters may have older conda versions with different behavior)
