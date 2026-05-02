"""
setup_objects.py — Pre-experiment object creation.

Creates all on-chain objects needed for the benchmark:
  - N MedicalDevice objects (one per sensor)
  - One EvidenceBatch per N (Design A)
  - One BatchConfig per N (Design B)

Object IDs are written to harness/results/object_ids.json
Run once before the benchmark sweep.

Usage:
    cd C:\Users\tariq\Downloads\TUWien\HIEMI2026\iotaEvidenceOracle
    python harness\src\setup_objects.py
"""

import json
import os
import subprocess
import sys
import time

# ── Hardcoded deployment values (from testnet deploy) ────────────────────────
# These are the deployed package IDs from the testnet deployment.
# They override any .env values if .env is not found or is empty.

PACKAGE_ID_A_DEFAULT = "0x1e84478d9b09ca5b8f7bc0508ad4e80d19628250ec13517680ceae67e9d2b47a"
PACKAGE_ID_B_DEFAULT = "0xcde5399d72f19436e5c9b8e6c60be94645ee2e5ec23daeae9bfcadfb44b32174"
WALLET_DEFAULT       = "0xd0e7976a242007d7ce49087578e46f93ae9b5bbfd8288240c39691905a5572b3"

# ── Parameters ───────────────────────────────────────────────────────────────
SENSOR_COUNTS      = [2, 4, 8, 16, 32]
WINDOW_DURATION_MS = 5_000
GRACE_INTERVAL_MS  =   500
MAX_SPREAD_MS      = 3_000   # accommodate full window
GAS_BUDGET         = 10_000_000

# ── Results directory ─────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "..", "results")


def load_env() -> dict:
    """Load .env from project root (two levels above this script)."""
    env = {}
    # Try project root first
    for candidate in [
        os.path.join(SCRIPT_DIR, "..", "..", ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]:
        path = os.path.abspath(candidate)
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip()
            print(f"Loaded .env from {path}")
            break
    return env


def run_cli(args: list) -> tuple:
    """Run iota CLI and return (stdout, stderr)."""
    result = subprocess.run(
        ["iota"] + args,
        capture_output=True,
        text=True,
    )
    return result.stdout, result.stderr


def extract_first_object_id(stdout: str) -> str:
    """Extract the first ObjectID from CLI output."""
    for line in stdout.splitlines():
        line = line.strip()
        if "ObjectID:" in line:
            return line.split("ObjectID:")[-1].strip()
    return ""


def create_device(package_id: str, device_addr: str, sensor_type: int) -> str:
    """
    Create a MedicalDevice on-chain and return its object ID.
    Uses PTB pattern: --assign captures the returned object,
    --transfer-objects sends it to the active address.
    """
    stdout, stderr = run_cli([
        "client", "ptb",
        "--assign", "dev",
        "--move-call",
        f"{package_id}::types::new_device",
        f'"{device_addr}"',
        str(sensor_type),
        "--transfer-objects", "[dev]", "@sender",
        "--gas-budget", str(GAS_BUDGET),
        "--json",
    ])

    obj_id = extract_first_object_id(stdout)
    if not obj_id:
        # Print first 300 chars of stderr for diagnosis
        err_preview = (stderr or "").strip()[:300]
        print(f"    PTB error: {err_preview}")
    return obj_id


def create_batch_a(
    package_id: str, window_id: int,
    window_start: int, window_end: int, n: int,
) -> str:
    """Create an EvidenceBatch (Design A shared object)."""
    stdout, stderr = run_cli([
        "client", "ptb",
        "--assign", "batch",
        "--move-call",
        f"{package_id}::types::new_batch",
        str(window_id),
        str(window_start),
        str(window_end),
        str(GRACE_INTERVAL_MS),
        str(n),             # k = number of sensors
        str(MAX_SPREAD_MS), # max spread
        "--transfer-objects", "[batch]", "@sender",
        "--gas-budget", str(GAS_BUDGET),
        "--json",
    ])
    obj_id = extract_first_object_id(stdout)
    if not obj_id:
        err_preview = (stderr or "").strip()[:200]
        print(f"    Batch PTB error: {err_preview}")
    return obj_id


def create_config_b(
    package_id: str, window_id: int,
    window_start: int, window_end: int, n: int,
) -> str:
    """Create a BatchConfig (Design B)."""
    stdout, stderr = run_cli([
        "client", "ptb",
        "--assign", "cfg",
        "--move-call",
        f"{package_id}::types::new_config",
        str(window_id),
        str(window_start),
        str(window_end),
        str(GRACE_INTERVAL_MS),
        str(n),
        str(MAX_SPREAD_MS),
        "--transfer-objects", "[cfg]", "@sender",
        "--gas-budget", str(GAS_BUDGET),
        "--json",
    ])
    obj_id = extract_first_object_id(stdout)
    if not obj_id:
        err_preview = (stderr or "").strip()[:200]
        print(f"    Config PTB error: {err_preview}")
    return obj_id


def main():
    env = load_env()

    package_id_a = env.get("PACKAGE_ID_A") or PACKAGE_ID_A_DEFAULT
    package_id_b = env.get("PACKAGE_ID_B") or PACKAGE_ID_B_DEFAULT
    wallet       = env.get("WALLET_ADDRESS") or WALLET_DEFAULT

    print(f"Wallet : {wallet}")
    print(f"Pkg A  : {package_id_a}")
    print(f"Pkg B  : {package_id_b}")
    print()

    # Verify CLI is working
    stdout, _ = run_cli(["client", "active-address"])
    active = stdout.strip()
    print(f"Active address: {active}")
    if not active.startswith("0x"):
        print("ERROR: iota client active-address did not return an address.")
        print("Run: iota client switch --env testnet")
        sys.exit(1)
    print()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    object_ids = {
        "wallet":    wallet,
        "package_a": package_id_a,
        "package_b": package_id_b,
        "by_n":      {},
    }

    for n in SENSOR_COUNTS:
        print(f"Creating objects for N={n} ...")
        now_ms       = int(time.time() * 1000)
        window_start = now_ms + 10_000   # 10 s from now
        window_end   = window_start + WINDOW_DURATION_MS
        window_id    = n

        # Create N device objects
        device_ids   = []
        device_addrs = []
        for i in range(n):
            # Use deterministic addresses that won't collide with real wallets
            # but are valid as the `device_id: address` field value
            sensor_addr = f"0xdead{(i + 1):060x}"
            print(f"  Device {i+1}/{n} ...", end=" ", flush=True)
            obj_id = create_device(package_id_a, sensor_addr, i + 1)
            if obj_id:
                print(f"OK ({obj_id[:12]}...)")
            else:
                print("FAILED")
            device_ids.append(obj_id)
            device_addrs.append(sensor_addr)
            time.sleep(0.5)

        # Create EvidenceBatch for Design A
        print(f"  EvidenceBatch (Design A) ...", end=" ", flush=True)
        batch_id_a = create_batch_a(package_id_a, window_id, window_start, window_end, n)
        print(f"OK ({batch_id_a[:12]}...)" if batch_id_a else "FAILED")
        time.sleep(0.5)

        # Create BatchConfig for Design B
        print(f"  BatchConfig (Design B) ...", end=" ", flush=True)
        config_id_b = create_config_b(package_id_b, window_id, window_start, window_end, n)
        print(f"OK ({config_id_b[:12]}...)" if config_id_b else "FAILED")
        time.sleep(0.5)

        object_ids["by_n"][str(n)] = {
            "window_id":          window_id,
            "window_start_ms":    window_start,
            "window_end_ms":      window_end,
            "device_object_ids":  device_ids,
            "device_addresses":   device_addrs,
            "batch_object_id_a":  batch_id_a,
            "config_object_id_b": config_id_b,
            "signer_alias":       "default",
        }
        print()

    out_path = os.path.join(RESULTS_DIR, "object_ids.json")
    with open(out_path, "w") as f:
        json.dump(object_ids, f, indent=2)
    print(f"Object IDs written to {out_path}")

    # Report any failures
    failures = []
    for n, ids in object_ids["by_n"].items():
        missing_devs = sum(1 for x in ids["device_object_ids"] if not x)
        if missing_devs:
            failures.append(f"N={n}: {missing_devs} device(s) failed")
        if not ids["batch_object_id_a"]:
            failures.append(f"N={n}: EvidenceBatch creation failed")
        if not ids["config_object_id_b"]:
            failures.append(f"N={n}: BatchConfig creation failed")

    if failures:
        print("\nWARNING — some objects were not created:")
        for f in failures:
            print(f"  {f}")
        print("Check the PTB errors above and re-run after fixing.")
    else:
        print("\nAll objects created successfully.")
        print("Next: python harness\\src\\run_baseline.py")


if __name__ == "__main__":
    main()
