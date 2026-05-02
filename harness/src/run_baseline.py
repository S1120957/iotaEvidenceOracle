"""
run_baseline.py — Baseline experiment sweep.

Reads object_ids.json created by setup_objects.py.
Runs WINDOWS_PER_RUN windows for each (design, N) combination.
Writes results to harness/results/table1_{env}.csv
"""

import asyncio
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    SENSOR_COUNTS, WINDOWS_PER_RUN, WINDOW_DURATION_MS,
    GRACE_INTERVAL_MS, ENV, RESULTS_DIR,
)
from metrics import WindowRecord, SensorWriteRecord, aggregate, save_window_records
from sensor import SensorConfig, run_sensor
from window_closer import finalize_window
import csv


def load_object_ids() -> dict:
    path = os.path.join(RESULTS_DIR, "object_ids.json")
    if not os.path.exists(path):
        print("ERROR: harness/results/object_ids.json not found.")
        print("Run python harness/src/setup_objects.py first.")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


async def run_one_window(
    design:      str,
    n_sensors:   int,
    window_idx:  int,
    obj_ids:     dict,
    fault:       str = "baseline",
) -> WindowRecord:
    now_ms       = int(time.time() * 1000)
    window_start = now_ms
    window_end   = now_ms + WINDOW_DURATION_MS
    window_id    = window_idx

    ids_for_n    = obj_ids["by_n"][str(n_sensors)]
    signer_alias = ids_for_n["signer_alias"]

    record = WindowRecord(
        design       = design,
        sensor_count = n_sensors,
        window_index = window_idx,
        window_end_ms= window_end,
        fault_scenario=fault,
    )

    # Build per-sensor configs
    sensor_configs = []
    for i in range(n_sensors):
        fault_i = fault if i == 0 else "baseline"
        cfg = SensorConfig(
            sensor_index     = i,
            signer_alias     = signer_alias,
            device_address   = ids_for_n["device_addresses"][i],
            device_object_id = ids_for_n["device_object_ids"][i],
            sensor_type      = i + 1,
            window_id        = window_id,
            window_start_ms  = window_start,
            window_end_ms    = window_end,
            nonce            = window_idx * 1000 + i,
            design           = design,
            fault            = fault_i,
            batch_object_id  = ids_for_n.get("batch_object_id_a", ""),
        )
        sensor_configs.append(cfg)

    # Fire all sensors concurrently
    tasks  = [run_sensor(cfg) for cfg in sensor_configs]
    writes = await asyncio.gather(*tasks)
    record.writes = list(writes)

    # Collect slot IDs for Design B
    slot_ids = None
    if design == "B":
        slot_ids = [cfg.slot_object_id for cfg in sensor_configs
                    if cfg.slot_object_id is not None]

    # Finalize
    result = await finalize_window(
        design             = design,
        window_end_ms      = window_end,
        signer_alias       = signer_alias,
        batch_object_id    = ids_for_n.get("batch_object_id_a") if design == "A" else None,
        slot_object_ids    = slot_ids,
        config_object_id   = ids_for_n.get("config_object_id_b"),
        registry_object_id = None,
    )
    record.t_finalized_ms = result["t_finalized_ms"]
    record.batch_status   = result["batch_status"]
    return record


async def run_sweep(env: str):
    print(f"Baseline sweep — env={env}")
    print(f"Designs: A, B | N: {SENSOR_COUNTS} | Windows: {WINDOWS_PER_RUN}")

    obj_ids     = load_object_ids()
    all_records = []

    for design in ["A", "B"]:
        for n in SENSOR_COUNTS:
            print(f"  Design {design}, N={n} ...")
            run_records = []
            for w in range(WINDOWS_PER_RUN):
                rec = await run_one_window(design, n, w, obj_ids)
                run_records.append(rec)
                all_records.append(rec)
                await asyncio.sleep(0.5)

            agg = aggregate(run_records)
            p50 = agg["write_p50_median_ms"]
            fin = agg["finalization_latency_ms"]
            val = agg["validity_rate_pct"]
            p50s = f"{p50:.1f}" if p50 else "N/A"
            fins = f"{fin:.1f}" if fin else "N/A"
            print(f"    write_p50={p50s}ms  finalize={fins}ms  valid={val:.0f}%")

    save_window_records(all_records, f"raw_baseline_{env}.csv")
    _write_table1(all_records, env)
    print("Baseline sweep complete.")


def _write_table1(records, env: str):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"table1_{env}.csv")
    rows = []
    for design in ["A", "B"]:
        for n in SENSOR_COUNTS:
            subset = [r for r in records
                      if r.design == design and r.sensor_count == n]
            if not subset:
                continue
            agg = aggregate(subset)
            rows.append({"design": design, "N": n, **agg})

    if rows:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Table 1 → {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=ENV)
    args = parser.parse_args()
    asyncio.run(run_sweep(args.env))
