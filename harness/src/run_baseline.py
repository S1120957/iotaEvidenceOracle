"""
run_baseline.py — Baseline experiment sweep.

Runs N_windows windows for each (design, sensor_count) combination.
Writes per-window records to results/raw_baseline_{env}.csv
Writes aggregated summary to results/table1_{env}.csv

Usage:
    python run_baseline.py
    python run_baseline.py --env testnet
"""

import asyncio
import argparse
import time
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    SENSOR_COUNTS, WINDOWS_PER_RUN, WINDOW_DURATION_MS,
    GRACE_INTERVAL_MS, ENV, RESULTS_DIR,
)
from metrics import WindowRecord, SensorWriteRecord, aggregate, save_window_records
from sensor import SensorConfig, submit_sensor_write
from window_closer import finalize_window


async def run_one_window(
    design:       str,
    n_sensors:    int,
    window_index: int,
    client,
    keypairs:     list,
    object_ids:   dict,
    fault:        str = "baseline",
) -> WindowRecord:
    """
    Execute one window: fire N concurrent sensor writes, then finalize.
    Returns a WindowRecord with all metrics populated.
    """
    now_ms        = time.time() * 1000
    window_start  = int(now_ms)
    window_end    = int(now_ms + WINDOW_DURATION_MS)
    window_id     = window_index

    record = WindowRecord(
        design=design,
        sensor_count=n_sensors,
        window_index=window_index,
        window_end_ms=window_end,
        fault_scenario=fault,
    )

    # Build per-sensor configs
    sensor_configs = []
    for i in range(n_sensors):
        cfg = SensorConfig(
            sensor_index=i,
            device_address=object_ids["sensor_addresses"][i],
            sensor_type=i + 1,
            window_id=window_id,
            window_start_ms=window_start,
            window_end_ms=window_end,
            nonce=window_index * 1000 + i,
            design=design,
            fault=fault if i == 0 else "baseline",  # apply fault to sensor 0 only
        )
        # Inject object IDs needed by the transaction builders
        cfg.device_object_id = object_ids["device_object_ids"][i]
        if design == "A":
            cfg.batch_object_id = object_ids.get("batch_object_id_a", "")
        sensor_configs.append(cfg)

    # Fire all sensors concurrently
    tasks = [
        submit_sensor_write(cfg, client, keypairs[cfg.sensor_index])
        for cfg in sensor_configs
    ]
    write_records: list[SensorWriteRecord] = await asyncio.gather(*tasks)
    record.writes = list(write_records)

    # Collect slot IDs for Design B finalization
    slot_ids = None
    if design == "B":
        slot_ids = object_ids.get("slot_object_ids", [])

    # Finalize after grace interval
    result = await finalize_window(
        design=design,
        client=client,
        keypair=keypairs[-1],   # window-closer keypair is last
        window_end_ms=window_end,
        batch_object_id=object_ids.get("batch_object_id_a") if design == "A" else None,
        slot_object_ids=slot_ids,
        config_object_id=object_ids.get("config_object_id_b"),
        device_object_ids=object_ids.get("device_object_ids"),
    )
    record.t_finalized_ms = result["t_finalized_ms"]
    record.batch_status   = result["batch_status"]

    return record


async def run_sweep(env: str):
    """Full baseline sweep: all designs × all N values × WINDOWS_PER_RUN."""
    print(f"Starting baseline sweep on {env}")
    print(f"Designs: A, B | N: {SENSOR_COUNTS} | Windows: {WINDOWS_PER_RUN}")

    # TODO: initialise iota_sdk.Client and load keypairs
    # client = iota_sdk.Client(nodes=[RPC_URL])
    # keypairs = load_keypairs_from_env()
    # object_ids = load_object_ids_from_env()
    client    = None   # replace
    keypairs  = []     # replace
    object_ids = {}    # replace

    all_records = []

    for design in ["A", "B"]:
        for n in SENSOR_COUNTS:
            print(f"  Design {design}, N={n} ...")
            run_records = []
            for w in range(WINDOWS_PER_RUN):
                rec = await run_one_window(
                    design, n, w, client, keypairs, object_ids
                )
                run_records.append(rec)
                all_records.append(rec)
                # Small pause between windows to avoid clock collisions
                await asyncio.sleep(0.2)

            agg = aggregate(run_records)
            print(f"    write_p50={agg['write_p50_median_ms']:.1f}ms "
                  f"finalize={agg['finalization_latency_ms']:.1f}ms "
                  f"valid={agg['validity_rate_pct']:.0f}%")

    save_window_records(all_records, f"raw_baseline_{env}.csv")
    _write_table1(all_records, env)


def _write_table1(records, env: str):
    """Write aggregated Table 1 structure to CSV."""
    import csv
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
            rows.append({
                "design": design,
                "N": n,
                **agg,
            })

    with open(path, "w", newline="") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    print(f"Table 1 → {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=ENV)
    args = parser.parse_args()
    asyncio.run(run_sweep(args.env))
