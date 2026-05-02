"""
smoke_test.py - End-to-end smoke test before running the full baseline sweep.

Tests the complete transaction pipeline for both designs using N=2 objects:
  1. Design B: create_slot (owned-object write, fast path)
  2. Design A: submit_reading (shared-object write)
  3. Design A: finalize (batch finalization)

Run this before run_baseline.py to confirm the CLI calls work end-to-end.

Usage:
    cd C:\\Users\\tariq\\Downloads\\TUWien\\HIEMI2026\\iotaEvidenceOracle
    python harness\\src\\smoke_test.py
"""

import hashlib
import json
import os
import random
import subprocess
import sys
import time

PACKAGE_ID_A = "0x1e84478d9b09ca5b8f7bc0508ad4e80d19628250ec13517680ceae67e9d2b47a"
PACKAGE_ID_B = "0xcde5399d72f19436e5c9b8e6c60be94645ee2e5ec23daeae9bfcadfb44b32174"
WALLET       = "0xd0e7976a242007d7ce49087578e46f93ae9b5bbfd8288240c39691905a5572b3"
GAS_BUDGET   = 10000000

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR  = os.path.join(SCRIPT_DIR, "..", "results")
OBJECT_IDS   = os.path.join(RESULTS_DIR, "object_ids.json")


def run_cli(args):
    result = subprocess.run(["iota"] + args, capture_output=True, text=True)
    return result.stdout, result.stderr


def parse_created_object_id(stdout):
    try:
        data = json.loads(stdout)
        for change in data.get("objectChanges", []):
            if change.get("type") == "created":
                oid = change.get("objectId", "")
                if oid:
                    return oid
    except Exception:
        pass
    for line in stdout.splitlines():
        line = line.strip()
        if "ObjectID:" in line:
            return line.split("ObjectID:")[-1].strip()
    return ""


def parse_digest(stdout):
    try:
        data = json.loads(stdout)
        return data.get("digest", "")
    except Exception:
        pass
    for line in stdout.splitlines():
        if "Transaction Digest:" in line:
            return line.split("Transaction Digest:")[-1].strip()
    return ""


def parse_status(stdout):
    try:
        data = json.loads(stdout)
        return data.get("effects", {}).get("status", {}).get("status", "unknown")
    except Exception:
        return "unknown"


def make_hashes(device_addr, sensor_type, nonce, ts_ms):
    payload = f"{device_addr}:{sensor_type}:{nonce}:{ts_ms}"
    rh = list(hashlib.sha256(payload.encode()).digest())
    sh = list(hashlib.sha256(bytes(rh)).digest())
    rh_vec = "vector[" + ",".join(str(b) for b in rh) + "]"
    sh_vec = "vector[" + ",".join(str(b) for b in sh) + "]"
    return rh_vec, sh_vec


def section(title):
    print()
    print("=" * 60)
    print(" " + title)
    print("=" * 60)


def ok(msg):
    print("  [OK]  " + msg)


def fail(msg, detail=""):
    print("  [FAIL] " + msg)
    if detail:
        clean = "\n".join(
            l for l in detail.splitlines()
            if "mismatch" not in l and l.strip()
        )
        if clean:
            print("         " + clean[:300])


def main():
    print("IOTA Evidence Oracle - Smoke Test")
    print("Testnet end-to-end pipeline validation")

    if not os.path.exists(OBJECT_IDS):
        print("ERROR: harness/results/object_ids.json not found.")
        print("Run python harness\\src\\setup_objects.py first.")
        sys.exit(1)

    with open(OBJECT_IDS) as f:
        obj = json.load(f)

    n2 = obj["by_n"]["2"]
    batch_id_a   = n2["batch_object_id_a"]
    config_id_b  = n2["config_object_id_b"]
    dev_obj_0    = n2["device_object_ids"][0]
    dev_obj_1    = n2["device_object_ids"][1]
    dev_addr_0   = n2["device_addresses"][0]
    dev_addr_1   = n2["device_addresses"][1]
    window_id    = str(n2["window_id"])

    ts_ms   = int(time.time() * 1000)
    nonce_0 = random.randint(10000, 99999)
    nonce_1 = random.randint(10000, 99999)

    print()
    print("Using N=2 objects:")
    print("  Batch A  : " + batch_id_a[:20] + "...")
    print("  Config B : " + config_id_b[:20] + "...")
    print("  Device 0 : " + dev_obj_0[:20] + "...")
    print("  Device 1 : " + dev_obj_1[:20] + "...")
    print("  Window ID: " + window_id)

    results = {}

    # ── Test 1: Design B create_slot ─────────────────────────────────────────
    section("Test 1: Design B — create_slot (owned object, no shared state)")

    rh_vec, sh_vec = make_hashes(dev_addr_0, 1, nonce_0, ts_ms)
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call",
        PACKAGE_ID_B + "::accumulator::create_slot",
        "@" + dev_addr_0,
        "1",
        rh_vec,
        str(ts_ms),
        str(nonce_0),
        window_id,
        sh_vec,
        "--gas-budget", str(GAS_BUDGET),
        "--json",
    ])

    slot_id = parse_created_object_id(stdout)
    digest  = parse_digest(stdout)
    status  = parse_status(stdout)

    if slot_id:
        ok("Slot created: " + slot_id[:20] + "...")
        ok("Digest: " + digest)
        results["design_b_create_slot"] = "PASS"
    else:
        fail("create_slot failed", stderr)
        results["design_b_create_slot"] = "FAIL"

    # ── Test 2: Design A submit_reading ──────────────────────────────────────
    section("Test 2: Design A — submit_reading (shared object write)")

    rh_vec0, sh_vec0 = make_hashes(dev_addr_0, 1, nonce_0, ts_ms)

    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call",
        PACKAGE_ID_A + "::types::new_slot",
        "@" + dev_addr_0,
        "1",
        rh_vec0,
        str(ts_ms),
        str(nonce_0),
        window_id,
        sh_vec0,
        "--assign", "slot0",
        "--move-call",
        PACKAGE_ID_A + "::accumulator::submit_reading",
        "@" + batch_id_a,
        "@" + dev_obj_0,
        "slot0",
        "--gas-budget", str(GAS_BUDGET),
        "--json",
    ])

    digest = parse_digest(stdout)
    status = parse_status(stdout)

    if digest and status == "success":
        ok("submit_reading succeeded")
        ok("Digest: " + digest)
        results["design_a_submit_reading"] = "PASS"
    else:
        fail("submit_reading failed", stderr)
        results["design_a_submit_reading"] = "FAIL"

    # Submit second reading for finalization to work (needs k=2)
    rh_vec1, sh_vec1 = make_hashes(dev_addr_1, 2, nonce_1, ts_ms + 100)

    stdout2, stderr2 = run_cli([
        "client", "ptb",
        "--move-call",
        PACKAGE_ID_A + "::types::new_slot",
        "@" + dev_addr_1,
        "2",
        rh_vec1,
        str(ts_ms + 100),
        str(nonce_1),
        window_id,
        sh_vec1,
        "--assign", "slot1",
        "--move-call",
        PACKAGE_ID_A + "::accumulator::submit_reading",
        "@" + batch_id_a,
        "@" + dev_obj_1,
        "slot1",
        "--gas-budget", str(GAS_BUDGET),
        "--json",
    ])

    digest2 = parse_digest(stdout2)
    if digest2 and parse_status(stdout2) == "success":
        ok("Second reading submitted: " + digest2)
    else:
        fail("Second reading failed", stderr2)

    # ── Test 3: Design A finalize ─────────────────────────────────────────────
    section("Test 3: Design A — finalize")

    we    = n2["window_end_ms"]
    dg    = 500
    current_time = int(time.time() * 1000)

    if current_time < we + dg:
        wait_ms = (we + dg) - current_time + 100
        print("  Waiting " + str(wait_ms) + "ms for grace interval...")
        time.sleep(wait_ms / 1000.0)
        current_time = int(time.time() * 1000)

    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call",
        PACKAGE_ID_A + "::accumulator::finalize",
        "@" + batch_id_a,
        str(current_time),
        "--gas-budget", str(GAS_BUDGET),
        "--json",
    ])

    digest = parse_digest(stdout)
    status = parse_status(stdout)

    if digest and status == "success":
        ok("finalize succeeded")
        ok("Digest: " + digest)
        results["design_a_finalize"] = "PASS"
    else:
        fail("finalize failed", stderr)
        results["design_a_finalize"] = "FAIL"

    # ── Summary ───────────────────────────────────────────────────────────────
    section("Smoke Test Summary")

    all_pass = all(v == "PASS" for v in results.values())
    for test, result in results.items():
        marker = "[OK]  " if result == "PASS" else "[FAIL]"
        print("  " + marker + " " + test)

    print()
    if all_pass:
        print("All tests passed. Ready to run: python harness\\src\\run_baseline.py")
    else:
        print("Some tests failed. Review errors above before running the baseline.")

    out_path = os.path.join(RESULTS_DIR, "smoke_test_results.json")
    with open(out_path, "w") as f:
        json.dump({"timestamp": ts_ms, "results": results}, f, indent=2)
    print("Results saved to " + out_path)


if __name__ == "__main__":
    main()
