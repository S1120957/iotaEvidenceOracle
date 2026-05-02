"""
smoke_test.py - End-to-end smoke test for both designs.

Self-contained: creates its own short-lived batch (10s window) so it
does not depend on object_ids.json window timing and completes in ~15s.

Tests:
  1. Design B create_slot   (owned object, no shared state)
  2. Design A submit_reading (shared object write, 2 sensors)
  3. Design A finalize       (after grace interval)

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

PKG_A  = "0x1e84478d9b09ca5b8f7bc0508ad4e80d19628250ec13517680ceae67e9d2b47a"
PKG_B  = "0xcde5399d72f19436e5c9b8e6c60be94645ee2e5ec23daeae9bfcadfb44b32174"
WALLET = "0xd0e7976a242007d7ce49087578e46f93ae9b5bbfd8288240c39691905a5572b3"
GAS    = "20000000"

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "..", "results")


def run_cli(args):
    r = subprocess.run(["iota"] + args, capture_output=True, text=True)
    return r.stdout, r.stderr


def parse_object_id(stdout):
    try:
        data = json.loads(stdout)
        for c in data.get("objectChanges", []):
            if c.get("type") == "created":
                oid = c.get("objectId", "")
                if oid:
                    return oid
    except Exception:
        pass
    for line in stdout.splitlines():
        if "ObjectID:" in line:
            return line.split("ObjectID:")[-1].strip()
    return ""


def parse_digest(stdout):
    try:
        return json.loads(stdout).get("digest", "")
    except Exception:
        pass
    for line in stdout.splitlines():
        if "Transaction Digest:" in line:
            return line.split("Transaction Digest:")[-1].strip()
    return ""


def parse_status(stdout):
    try:
        return json.loads(stdout).get("effects", {}).get("status", {}).get("status", "")
    except Exception:
        return ""


def make_vecs(device_addr, sensor_type, nonce, ts_ms):
    rh = list(hashlib.sha256(f"{device_addr}:{sensor_type}:{nonce}:{ts_ms}".encode()).digest())
    sh = list(hashlib.sha256(bytes(rh)).digest())
    rh_v = "vector[" + ",".join(str(b) for b in rh) + "]"
    sh_v = "vector[" + ",".join(str(b) for b in sh) + "]"
    return rh_v, sh_v


def ok(msg):   print("  [OK]   " + msg)
def fail(msg): print("  [FAIL] " + msg)
def section(t):
    print()
    print("=" * 58)
    print(" " + t)
    print("=" * 58)


def main():
    print("IOTA Evidence Oracle - Smoke Test")
    print("Self-contained pipeline test (~15 seconds)")

    obj_path = os.path.join(RESULTS_DIR, "object_ids.json")
    if not os.path.exists(obj_path):
        print("ERROR: harness/results/object_ids.json not found.")
        print("Run python harness\\src\\setup_objects.py first.")
        sys.exit(1)

    with open(obj_path) as f:
        obj = json.load(f)

    n2        = obj["by_n"]["2"]
    dev_obj_0 = n2["device_object_ids"][0]
    dev_obj_1 = n2["device_object_ids"][1]
    dev_addr_0 = n2["device_addresses"][0]
    dev_addr_1 = n2["device_addresses"][1]

    results = {}

    # ── Create a fresh short-lived batch for this test ───────────────────────
    section("Setup: create fresh 10-second EvidenceBatch")
    now_ms = int(time.time() * 1000)
    ws = now_ms + 2000      # starts in 2 seconds
    we = ws + 10000         # 10-second window
    dg = 2000               # 2-second grace
    wid = random.randint(9000, 9999)
    n_sensors = 2
    max_spread = 10000

    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call",
        PKG_A + "::types::new_batch",
        str(wid), str(ws), str(we), str(dg),
        str(n_sensors), str(max_spread),
        "--assign", "batch",
        "--transfer-objects", "[batch]",
        "@" + WALLET,
        "--gas-budget", GAS,
        "--json",
    ])
    batch_id = parse_object_id(stdout)
    if batch_id:
        ok("Fresh batch created: " + batch_id[:20] + "...")
        ok("Window: " + str(ws) + " to " + str(we) + " (grace " + str(dg) + "ms)")
    else:
        fail("Could not create batch")
        err = "\n".join(l for l in (stderr or "").splitlines() if "mismatch" not in l and l.strip())
        if err:
            print("  " + err[:300])
        sys.exit(1)

    # Wait for window to open
    wait_ms = ws - int(time.time() * 1000) + 100
    if wait_ms > 0:
        print("  Waiting " + str(wait_ms) + "ms for window to open...")
        time.sleep(wait_ms / 1000.0)

    # ── Test 1: Design B create_slot ─────────────────────────────────────────
    section("Test 1: Design B — create_slot (owned object)")

    ts1   = int(time.time() * 1000)
    n1    = random.randint(10000, 99999)
    rh1, sh1 = make_vecs(dev_addr_0, 1, n1, ts1)

    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call",
        PKG_B + "::accumulator::create_slot",
        "@" + dev_addr_0, "1", rh1, str(ts1), str(n1), str(wid), sh1,
        "--gas-budget", GAS,
        "--json",
    ])

    slot_id = parse_object_id(stdout)
    digest  = parse_digest(stdout)
    if slot_id:
        ok("Slot: " + slot_id[:20] + "...")
        ok("Digest: " + digest)
        results["design_b_create_slot"] = "PASS"
    else:
        fail("create_slot failed")
        err = "\n".join(l for l in (stderr or "").splitlines() if "mismatch" not in l and l.strip())
        print("  " + (err or stdout)[:300])
        results["design_b_create_slot"] = "FAIL"

    # ── Test 2: Design A submit_reading ──────────────────────────────────────
    section("Test 2: Design A — submit_reading (shared object, 2 sensors)")

    ts2 = int(time.time() * 1000)
    n2a = random.randint(10000, 99999)
    n2b = random.randint(10000, 99999)
    rh2a, sh2a = make_vecs(dev_addr_0, 1, n2a, ts2)
    rh2b, sh2b = make_vecs(dev_addr_1, 2, n2b, ts2 + 200)

    # Sensor 0
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call", PKG_A + "::types::new_slot",
        "@" + dev_addr_0, "1", rh2a, str(ts2), str(n2a), str(wid), sh2a,
        "--assign", "s0",
        "--move-call", PKG_A + "::accumulator::submit_reading",
        "@" + batch_id, "@" + dev_obj_0, "s0",
        "--gas-budget", GAS, "--json",
    ])
    d0 = parse_digest(stdout)
    st0 = parse_status(stdout)
    if d0 and st0 == "success":
        ok("Sensor 0 submitted: " + d0)
    else:
        fail("Sensor 0 failed")
        err = "\n".join(l for l in (stderr or "").splitlines() if "mismatch" not in l and l.strip())
        out_preview = stdout[:300] if stdout else ""
        print("  " + (err or out_preview)[:300])

    # Sensor 1
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call", PKG_A + "::types::new_slot",
        "@" + dev_addr_1, "2", rh2b, str(ts2 + 200), str(n2b), str(wid), sh2b,
        "--assign", "s1",
        "--move-call", PKG_A + "::accumulator::submit_reading",
        "@" + batch_id, "@" + dev_obj_1, "s1",
        "--gas-budget", GAS, "--json",
    ])
    d1 = parse_digest(stdout)
    st1 = parse_status(stdout)
    if d1 and st1 == "success":
        ok("Sensor 1 submitted: " + d1)
        results["design_a_submit_reading"] = "PASS"
    else:
        fail("Sensor 1 failed")
        err = "\n".join(l for l in (stderr or "").splitlines() if "mismatch" not in l and l.strip())
        print("  " + (err or stdout[:300])[:300])
        results["design_a_submit_reading"] = "FAIL"

    # ── Test 3: Design A finalize ─────────────────────────────────────────────
    section("Test 3: Design A — finalize (after grace interval)")

    deadline = we + dg + 500
    wait_ms  = deadline - int(time.time() * 1000)
    if wait_ms > 0:
        print("  Waiting " + str(wait_ms) + "ms for grace interval to pass...")
        time.sleep(wait_ms / 1000.0)

    current_time = int(time.time() * 1000)
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call", PKG_A + "::accumulator::finalize",
        "@" + batch_id, str(current_time),
        "--gas-budget", GAS, "--json",
    ])
    digest = parse_digest(stdout)
    status = parse_status(stdout)
    if digest and status == "success":
        ok("Finalized: " + digest)
        results["design_a_finalize"] = "PASS"
    else:
        fail("finalize failed")
        err = "\n".join(l for l in (stderr or "").splitlines() if "mismatch" not in l and l.strip())
        print("  " + (err or stdout[:300])[:300])
        results["design_a_finalize"] = "FAIL"

    # ── Summary ───────────────────────────────────────────────────────────────
    section("Smoke Test Summary")
    all_pass = all(v == "PASS" for v in results.values())
    for test, result in results.items():
        marker = "[OK]  " if result == "PASS" else "[FAIL]"
        print("  " + marker + " " + test)

    print()
    if all_pass:
        print("All tests passed.")
        print("Ready to run: python harness\\src\\run_baseline.py")
    else:
        print("Some tests failed. Review errors above.")

    out_path = os.path.join(RESULTS_DIR, "smoke_test_results.json")
    with open(out_path, "w") as f:
        json.dump({"timestamp_ms": int(time.time()*1000), "results": results}, f, indent=2)
    print("Results saved to " + out_path)


if __name__ == "__main__":
    main()
