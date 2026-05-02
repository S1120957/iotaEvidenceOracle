"""
setup_objects.py — Pre-experiment object creation.

Before running benchmarks, this script:
  1. Creates N MedicalDevice objects and writes their IDs to .env
  2. Creates one EvidenceBatch (Design A) per run configuration
  3. Creates one BatchConfig (Design B) per run configuration

Run once before the benchmark sweep:
    python harness/src/setup_objects.py

Object IDs are written to harness/results/object_ids.json
"""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    PACKAGE_ID_A, PACKAGE_ID_B, SENSOR_COUNTS,
    WINDOW_DURATION_MS, GRACE_INTERVAL_MS, RESULTS_DIR,
)


def run_cli(args: list[str]) -> tuple[str, str]:
    result = subprocess.run(
        ["iota"] + args, capture_output=True, text=True
    )
    return result.stdout, result.stderr


def extract_object_id(stdout: str, obj_type_fragment: str = "") -> str:
    """Extract the first created ObjectID from CLI output."""
    for line in stdout.splitlines():
        if "ObjectID:" in line:
            return line.split("ObjectID:")[-1].strip()
    return ""


def create_device(
    package_id:   str,
    device_addr:  str,
    sensor_type:  int,
    signer_alias: str,
) -> str:
    """Call types::new_device and return the object ID."""
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call",
        f"{package_id}::types::new_device",
        f'"{device_addr}"',
        str(sensor_type),
        "--gas-budget", "5000000",
        "--sender",     signer_alias,
        "--json",
    ])
    obj_id = extract_object_id(stdout)
    if not obj_id:
        print(f"  WARNING: no ObjectID found for device {device_addr}")
        print("  stderr:", stderr[:200])
    return obj_id


def create_batch_a(
    package_id:   str,
    window_id:    int,
    window_start: int,
    window_end:   int,
    n_sensors:    int,
    signer_alias: str,
) -> str:
    """Create an EvidenceBatch (Design A shared object) and return its ID."""
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call",
        f"{package_id}::types::new_batch",
        str(window_id),
        str(window_start),
        str(window_end),
        str(GRACE_INTERVAL_MS),
        str(n_sensors),        # k = N (all sensors must submit)
        str(WINDOW_DURATION_MS),  # max spread = full window duration
        "--gas-budget", "5000000",
        "--sender",     signer_alias,
        "--json",
    ])
    return extract_object_id(stdout)


def create_config_b(
    package_id:   str,
    window_id:    int,
    window_start: int,
    window_end:   int,
    n_sensors:    int,
    signer_alias: str,
) -> str:
    """Create a BatchConfig (Design B) and return its ID."""
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call",
        f"{package_id}::types::new_config",
        str(window_id),
        str(window_start),
        str(window_end),
        str(GRACE_INTERVAL_MS),
        str(n_sensors),
        str(WINDOW_DURATION_MS),
        "--gas-budget", "5000000",
        "--sender",     signer_alias,
        "--json",
    ])
    return extract_object_id(stdout)


def load_env() -> dict:
    """Load .env file as a dict."""
    env = {}
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def main():
    env = load_env()

    wallet_address = env.get("WALLET_ADDRESS", "")
    signer_alias   = "default"   # use default iota client alias

    print(f"Wallet: {wallet_address}")
    print(f"Package A: {PACKAGE_ID_A}")
    print(f"Package B: {PACKAGE_ID_B}")
    print()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    object_ids = {
        "wallet": wallet_address,
        "package_a": PACKAGE_ID_A,
        "package_b": PACKAGE_ID_B,
        "by_n": {}
    }

    for n in SENSOR_COUNTS:
        print(f"Creating objects for N={n}...")
        now_ms        = int(time.time() * 1000)
        window_start  = now_ms + 5000   # starts 5 s from now
        window_end    = window_start + WINDOW_DURATION_MS
        window_id     = n  # use N as window_id for identification

        # Create N device objects (one per sensor) — shared for both designs
        device_ids   = []
        device_addrs = []
        for i in range(n):
            sensor_addr = f"0x{(i + 1):064x}"  # deterministic test addresses
            print(f"  Creating device {i+1}/{n} ...")
            obj_id = create_device(
                PACKAGE_ID_A, sensor_addr, i + 1, signer_alias
            )
            device_ids.append(obj_id)
            device_addrs.append(sensor_addr)
            time.sleep(0.3)  # avoid rate limiting

        # Create EvidenceBatch for Design A
        print(f"  Creating EvidenceBatch (Design A) ...")
        batch_id_a = create_batch_a(
            PACKAGE_ID_A, window_id, window_start, window_end, n, signer_alias
        )

        # Create BatchConfig for Design B
        print(f"  Creating BatchConfig (Design B) ...")
        config_id_b = create_config_b(
            PACKAGE_ID_B, window_id, window_start, window_end, n, signer_alias
        )

        object_ids["by_n"][str(n)] = {
            "window_id":      window_id,
            "window_start_ms": window_start,
            "window_end_ms":   window_end,
            "device_object_ids": device_ids,
            "device_addresses":  device_addrs,
            "batch_object_id_a": batch_id_a,
            "config_object_id_b": config_id_b,
            "signer_alias":     signer_alias,
        }

        print(f"  N={n}: devices={len(device_ids)} batch_a={batch_id_a[:16]}... config_b={config_id_b[:16]}...")
        print()

    out_path = os.path.join(RESULTS_DIR, "object_ids.json")
    with open(out_path, "w") as f:
        json.dump(object_ids, f, indent=2)
    print(f"Object IDs written to {out_path}")
    print("Run harness/src/run_baseline.py next.")


if __name__ == "__main__":
    main()
