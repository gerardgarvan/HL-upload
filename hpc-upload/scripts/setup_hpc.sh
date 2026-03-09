#!/bin/bash
set -euo pipefail

# ---------------------------------------------------------------------------
# HPC Setup Script for HL Data Loading & Cleaning
# Run on HiPerGator after SSH: bash scripts/setup_hpc.sh
# Idempotent — safe to run multiple times.
# ---------------------------------------------------------------------------

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }

BLUE_PROJECT="/blue/erin.mobley-hl.bcu/hl-clean"
ORANGE_DATA="/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915"
DEMO_CSV="DEMOGRAPHIC_Mailhot_V1.csv"

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN} HL Data Loading & Cleaning — HPC Setup${NC}"
echo -e "${CYAN} $(date '+%Y-%m-%d %H:%M:%S %Z')${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# ---- Step 1: Create project directories on /blue -------------------------
echo "--- Step 1: Create project directories on /blue ---"
mkdir -p "${BLUE_PROJECT}/parquet"
mkdir -p "${BLUE_PROJECT}/logs"
mkdir -p "${BLUE_PROJECT}/scripts"
mkdir -p "${BLUE_PROJECT}/config"
mkdir -p "${BLUE_PROJECT}/src/load"
ok "Project directories created under ${BLUE_PROJECT}"
echo ""

# ---- Step 2: Verify source data accessible --------------------------------
echo "--- Step 2: Verify source data on /orange ---"
if [ -d "${ORANGE_DATA}" ]; then
    ok "Source directory exists: ${ORANGE_DATA}"
    if [ -f "${ORANGE_DATA}/${DEMO_CSV}" ]; then
        CSV_SIZE=$(du -h "${ORANGE_DATA}/${DEMO_CSV}" | cut -f1)
        ok "${DEMO_CSV} found (${CSV_SIZE})"
    else
        fail "${DEMO_CSV} not found in ${ORANGE_DATA}"
        echo "  Available files:"
        ls -lh "${ORANGE_DATA}/" | head -20
        exit 1
    fi
else
    fail "Source directory not found: ${ORANGE_DATA}"
    echo "  Check that /orange is mounted and the path is correct."
    echo "  If the storage was recently migrated, contact UF Research Computing."
    exit 1
fi
echo ""

# ---- Step 3: Verify /blue has space ---------------------------------------
echo "--- Step 3: Check /blue storage quota ---"
if command -v blue_quota >/dev/null 2>&1; then
    blue_quota
elif command -v lfs >/dev/null 2>&1; then
    lfs quota -u "$(whoami)" /blue 2>/dev/null || warn "Could not check quota via lfs — verify manually"
else
    warn "Could not check quota — verify manually with: blue_quota"
fi
echo ""

# ---- Step 4: Conda environment setup -------------------------------------
echo "--- Step 4: Set up conda environment ---"
module load conda 2>/dev/null || { fail "Could not load conda module"; exit 1; }
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate hl-eda
ok "Activated conda env: hl-eda"

info "Installing polars and duckdb..."
if mamba install -y polars duckdb -c conda-forge; then
    ok "polars and duckdb installed successfully"
else
    warn "mamba install failed — possible dependency conflict."
    echo ""
    echo -e "  ${YELLOW}Fallback: create a new hl-clean env with all packages:${NC}"
    echo ""
    echo "    mamba create -n hl-clean python=3.11 pandas>=2.2 pyarrow>=18.0 polars duckdb \\"
    echo "        matplotlib>=3.9 seaborn>=0.13 jupyter ipykernel -c conda-forge"
    echo "    conda activate hl-clean"
    echo "    pip install 'jinja2>=3.1' tabulate 'tomli>=2.0'"
    echo ""
    echo "  Then re-run this script (it will detect the new env)."
    exit 1
fi
echo ""

# ---- Step 5: Verify installations ----------------------------------------
echo "--- Step 5: Verify library installations ---"
python -c "import polars as pl; print(f'  Polars {pl.__version__}')"
python -c "import duckdb; print(f'  DuckDB {duckdb.__version__}')"
python -c "import pyarrow; print(f'  PyArrow {pyarrow.__version__}')"
ok "All libraries importable"
echo ""

# ---- Step 6: Copy project files to /blue ----------------------------------
echo "--- Step 6: Project files on /blue ---"
echo ""
echo "  If you haven't already, copy project files from your local machine:"
echo ""
echo -e "    ${CYAN}# From your local machine (replace <local_path>):${NC}"
echo "    rsync -av --exclude='.planning' --exclude='.git' <local_path>/ hpg:${BLUE_PROJECT}/"
echo ""

if [ -f "${BLUE_PROJECT}/scripts/smoke_test.py" ]; then
    ok "smoke_test.py found in ${BLUE_PROJECT}/scripts/"
else
    warn "smoke_test.py not found — copy project files first (see above)"
fi
echo ""

# ---- Step 7: Run smoke test (if project files present) --------------------
echo "--- Step 7: Run smoke test ---"
if [ -f "${BLUE_PROJECT}/scripts/smoke_test.py" ]; then
    info "Running smoke test..."
    cd "${BLUE_PROJECT}"
    python scripts/smoke_test.py
    echo ""
    ok "Smoke test completed"
else
    warn "Skipping smoke test — scripts/smoke_test.py not found."
    echo "  After copying project files, run:"
    echo "    cd ${BLUE_PROJECT} && python scripts/smoke_test.py"
fi
echo ""

# ---- Step 8: Export environment -------------------------------------------
echo "--- Step 8: Export conda environment ---"
cd "${BLUE_PROJECT}"
mamba env export --no-builds > environment.yml
ok "environment.yml exported to ${BLUE_PROJECT}/environment.yml"
echo ""
echo "  Copy back to your local workspace:"
echo -e "    ${CYAN}scp hpg:${BLUE_PROJECT}/environment.yml .${NC}"
echo ""

# ---- Step 9: Summary -----------------------------------------------------
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN} Setup Complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  What was done:"
echo "    1. Created project directories on /blue"
echo "    2. Verified source data accessible on /orange"
echo "    3. Installed polars + duckdb in conda env"
echo "    4. Verified library imports"
if [ -f "${BLUE_PROJECT}/scripts/smoke_test.py" ]; then
    echo "    5. Ran smoke test (CSV → Parquet → DuckDB)"
else
    echo "    5. Smoke test skipped (copy project files first)"
fi
echo "    6. Exported environment.yml"
echo ""
echo "  Next steps:"
echo "    - If smoke test was skipped: copy project files and run it"
echo "    - Copy environment.yml back to local workspace"
echo "    - Phase 2: full 22-table CSV-to-Parquet conversion"
echo ""
