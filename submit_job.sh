#!/bin/bash
#SBATCH --job-name=hl-clean
#SBATCH --account=erin.mobley-hl.bcu
#SBATCH --qos=erin.mobley-hl.bcu
#SBATCH --mem=64gb
#SBATCH --time=2:00:00
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/hl-clean_%j.log

module load conda

source $(conda info --base)/etc/profile.d/conda.sh
conda activate hl-eda

cd /blue/erin.mobley-hl.bcu/hl-clean
python scripts/smoke_test.py
