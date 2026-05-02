"""
run_fault_injection.py — Fault injection experiment driver.

Runs the three fault scenarios (F1, F2, F3) defined in Section V.4:
  F1: Missing sensor — one sensor silenced
  F2: Late arrival   — one sensor submits after we + delta_g + epsilon
  F3: Conflicting    — one sensor submits twice for the same sensor_type

Each scenario is run for all N values and both designs.
Writes results to results/table2_{env}.csv
"""

import asyncio
import argparse
import os
import sys
import csv

sys.path.insert(0, os.path.dirname(__file__))

from config import SENSOR_COUNTS, WINDOWS_PER_RUN, ENV, RESULTS_DIR
from metrics import WindowRecord, aggregate, save_window_records
from run_baseline import run_one_window


FAULT_SCENARIOS = ["F1", "F2", "F3"]


async def run_fault_sweep(env: str):
    print(f"Starting fault injection sweep on {env}")

    # TODO: initialise client, keypairs, object_ids (same as run_baseline.py)
    client     = None
    keypairs   = []
    object_ids = {}

    all_records = []

    for fault in FAULT_SCENARIOS:
        for design in ["A", "B"]:
            for n in SENSOR_COUNTS:
                print(f"  Fault={fault}, Design={design}, N={n} ...")
                run_records = []
                for w in range(WINDOWS_PER_RUN):
                    rec = await run_one_window(
                        design, n, w, client, keypairs, object_ids,
                        fault=fault,
                    )
                    run_records.append(rec)
                    all_records.append(rec)
                    await asyncio.sleep(0.2)

                agg = aggregate(run_records)
                print(f"    valid={agg['validity_rate_pct']:.0f}%  "
                      f"complete={agg['completeness_rate_pct']:.0f}%  "
                      f"status_counts={_status_counts(run_records)}")

    save_window_records(all_records, f"raw_fault_{env}.csv")
    _write_table2(all_records, env)


def _status_counts(records):
    from collections import Counter
    return dict(Counter(r.batch_status for r in records))


def _write_table2(records, env: str):
    """Write Table 2 structure: one row per (fault, design) pair."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"table2_{env}.csv")

    rows = []
    for fault in ["baseline"] + FAULT_SCENARIOS:
        for design in ["A", "B"]:
            subset = [r for r in records
                      if r.fault_scenario == fault and r.design == design]
            if not subset:
                continue
            agg = aggregate(subset)
            statuses = _status_counts(subset)
            rows.append({
                "fault_scenario":         fault,
                "design":                 design,
                "validity_rate_pct":      agg["validity_rate_pct"],
                "completeness_rate_pct":  agg["completeness_rate_pct"],
                "expired_pct":            statuses.get("expired", 0) / len(subset) * 100,
                "invalid_pct":            statuses.get("invalid", 0) / len(subset) * 100,
                "false_valid_pct":        _false_valid_rate(subset, fault),
            })

    with open(path, "w", newline="") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    print(f"Table 2 → {path}")


def _false_valid_rate(records, fault: str) -> float:
    """
    False-valid rate: batches marked 'finalized' that should not be.
    For F1: any finalized batch is a false valid (count not met).
    For F2/F3: depends on k adjustment; here we flag all finalized as suspect
    if the fault was applied — the harness caller should verify on-chain.
    """
    if fault == "baseline":
        return 0.0
    false_valids = sum(1 for r in records if r.batch_status == "finalized")
    return false_valids / len(records) * 100 if records else 0.0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=ENV)
    args = parser.parse_args()
    asyncio.run(run_fault_sweep(args.env))
