#!/usr/bin/env bash
# run_all_experiments.sh — Run the full experiment campaign.
# Phase 1: Baseline sweep on localnet (Table 1)
# Phase 2: Fault injection on localnet (Table 2)
# Phase 3: Testnet confirmation for N=4 and N=16

set -euo pipefail

cd "$(dirname "$0")/.."

echo "============================================"
echo " IOTA Evidence Oracle — Full Experiment Run"
echo "============================================"
echo ""

# Confirm prerequisites
if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run scripts/setup_addresses.sh and scripts/deploy.sh first."
    exit 1
fi

if [ -z "$(grep 'PACKAGE_ID_A' .env | grep -v '^#')" ]; then
    echo "ERROR: PACKAGE_ID_A not set in .env. Run scripts/deploy.sh first."
    exit 1
fi

echo "Phase 1: Baseline sweep (localnet)..."
python3 harness/src/run_baseline.py --env localnet
echo ""

echo "Phase 2: Fault injection sweep (localnet)..."
python3 harness/src/run_fault_injection.py --env localnet
echo ""

echo "Phase 3: Testnet confirmation (N=4, N=16)..."
# Override sensor counts for testnet run via env var
IOTA_ENV=testnet python3 harness/src/run_baseline.py --env testnet
echo ""

echo "============================================"
echo " All experiments complete."
echo " Results written to harness/results/"
echo "  table1_localnet.csv  → Table 1 (paper)"
echo "  table2_localnet.csv  → Table 2 (paper)"
echo "  table1_testnet.csv   → Testnet confirmation"
echo "============================================"
