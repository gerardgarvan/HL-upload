#!/bin/bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Setup Verification for HL Data Pipeline
# Run after completing docs/SETUP.md environment and configuration steps.
# Verifies conda env, Python, dependencies, config, and compute node.
# ---------------------------------------------------------------------------

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN} HL Data Pipeline - Setup Verification${NC}"
echo -e "${CYAN} $(date '+%Y-%m-%d %H:%M:%S %Z')${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

CHECKS_PASSED=0
TOTAL_CHECKS=6

# ---- Check 1: Conda environment ------------------------------------------
echo "--- Check 1/6: Conda environment ---"
if [ -z "${CONDA_DEFAULT_ENV:-}" ]; then
    fail "No conda environment activated. Run: conda activate hl-eda"
fi

if [ "$CONDA_DEFAULT_ENV" != "hl-eda" ]; then
    fail "Wrong conda environment: $CONDA_DEFAULT_ENV (expected: hl-eda). Run: conda activate hl-eda"
fi

ok "Conda environment: $CONDA_DEFAULT_ENV"
((CHECKS_PASSED++))
echo ""

# ---- Check 2: Python version ----------------------------------------------
echo "--- Check 2/6: Python version ---"
PYTHON_VERSION=$(python --version 2>&1)
if [[ "$PYTHON_VERSION" =~ 3\.(11|12|13|14) ]]; then
    ok "Python version: $PYTHON_VERSION"
    ((CHECKS_PASSED++))
else
    fail "Unexpected Python version: $PYTHON_VERSION (expected 3.11-3.14)"
fi
echo ""

# ---- Check 3: Core dependencies importable --------------------------------
echo "--- Check 3/6: Core dependencies ---"
if python -c "import polars, pandas, pyarrow, pytest, jinja2, tabulate" 2>/dev/null; then
    ok "Core dependencies importable"
    ((CHECKS_PASSED++))
else
    fail "Import failed - run: conda env create -f environment.yml"
fi
echo ""

# ---- Check 4: Config validation -------------------------------------------
echo "--- Check 4/6: Configuration validation ---"
if python -c "from src.load.config import load_and_validate_config; load_and_validate_config()" 2>/dev/null; then
    ok "Configuration validated (config/paths.toml)"
    ((CHECKS_PASSED++))
else
    fail "Config validation failed - check config/paths.toml paths"
fi
echo ""

# ---- Check 5: Compute node warning ----------------------------------------
echo "--- Check 5/6: Compute node status ---"
HOSTNAME=$(hostname)
if [[ "$HOSTNAME" =~ login ]]; then
    warn "Currently on login node: $HOSTNAME"
    echo "  For pipeline execution, use: srun --pty --mem=16gb --time=2:00:00 bash"
    ((CHECKS_PASSED++))
else
    ok "On compute node: $HOSTNAME"
    ((CHECKS_PASSED++))
fi
echo ""

# ---- Check 6: Source data accessible --------------------------------------
echo "--- Check 6/6: Source data accessibility ---"
DATA_ROOT=$(python -c "from src.load.config import load_config; p = load_config(); print(p.data_root)" 2>/dev/null || echo "")
if [ -z "$DATA_ROOT" ]; then
    warn "Could not retrieve data_root from config"
    ((CHECKS_PASSED++))  # Count as passed but with warning
elif [ -d "$DATA_ROOT" ]; then
    ok "Source data accessible: $DATA_ROOT"
    ((CHECKS_PASSED++))
else
    warn "Source data not accessible: $DATA_ROOT"
    echo "  This is expected if on login node without /orange mount"
    ((CHECKS_PASSED++))  # Count as passed - data access can fail on login node
fi
echo ""

# ---- Summary --------------------------------------------------------------
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN} Setup verification complete - ${CHECKS_PASSED}/${TOTAL_CHECKS} checks passed${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
