# IOTA Evidence Oracle — Oracle-Ready Evidence Batching for Medical IoT

This repository contains all artefacts for the paper:

> **Oracle-Ready Evidence Batching Under Concurrent Medical IoT Sensor Writes
> in a Move Object Model**

---

## Repository layout

```
iota-evidence-oracle/
├── contracts/
│   ├── design_a/          # Shared-accumulator design (Design A)
│   │   ├── Move.toml
│   │   ├── sources/
│   │   │   ├── types.move         # MedicalDevice, EvidenceSlot, EvidenceBatch
│   │   │   ├── registry.move      # Device registration and lookup
│   │   │   └── accumulator.move   # submit_reading, finalize
│   │   └── tests/
│   │       └── predicate_tests.move
│   └── design_b/          # Owned-slot staging design (Design B)
│       ├── Move.toml
│       ├── sources/
│       │   ├── types.move
│       │   ├── registry.move
│       │   └── accumulator.move   # create_slot, finalize_from_slots
│       └── tests/
│           └── predicate_tests.move
├── harness/               # Python benchmark harness
│   ├── requirements.txt
│   ├── src/
│   │   ├── config.py      # Experiment parameters
│   │   ├── sensor.py      # Concurrent sensor simulation
│   │   ├── window_closer.py
│   │   ├── metrics.py     # Latency recording and aggregation
│   │   ├── run_baseline.py
│   │   └── run_fault_injection.py
│   └── results/           # CSVs written here (git-ignored)
├── scripts/
│   ├── setup_addresses.sh      # Fund N+1 addresses from faucet
│   ├── deploy.sh               # Publish both packages
│   └── run_all_experiments.sh  # Full experiment sweep
└── docs/
    └── experiment_log.md       # Record hardware spec and run notes here
```

---

## Quick start

**Do not begin until you have read `docs/experiment_log.md`
and completed the hardware spec section.**

```bash
# 1. Install IOTA CLI (see docs/experiment_log.md for exact version)
# 2. Clone this repo
git clone https://github.com/<your-org>/iota-evidence-oracle.git
cd iota-evidence-oracle

# 3. Start local devnet
iota start --with-faucet

# 4. Fund addresses and deploy contracts
bash scripts/setup_addresses.sh 33   # 32 sensors + 1 window-closer
bash scripts/deploy.sh localnet

# 5. Install Python dependencies
pip install -r harness/requirements.txt

# 6. Run full experiment sweep
bash scripts/run_all_experiments.sh
```

Results are written to `harness/results/` as CSV files, one per
configuration.

---

## Experiment phases

| Phase | Script | Produces |
|-------|--------|---------|
| Baseline (N=2..32, both designs) | `run_baseline.py` | `table1_latency.csv` |
| Fault injection F1/F2/F3 | `run_fault_injection.py` | `table2_validity.csv` |
| Testnet confirmation (N=4,16) | `run_baseline.py --env testnet` | `table1_testnet.csv` |

---

## Paper tables

Once experiments are complete, populate:
- **Table 1** (`tab:latency` in the paper) from `table1_latency.csv`
- **Table 2** (`tab:validity` in the paper) from `table2_validity.csv`

---

## Hypotheses under test

| ID | Claim |
|----|-------|
| H1 | Design A write latency increases with N; Design B remains flat |
| H2 | Design B finalization latency exceeds Design A at large N |
| H3 | Design A has higher retry rate at large N |
| H4 | Both designs enforce ValidBatch(B) correctly under all fault scenarios |
