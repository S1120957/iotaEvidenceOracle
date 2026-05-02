"""
debug_submit.py - Diagnose submit_reading PTB call.

Runs a single Design A submit_reading transaction and prints
the full stdout and stderr so the exact PTB error can be identified.

Usage:
    cd C:\\Users\\tariq\\Downloads\\TUWien\\HIEMI2026\\iotaEvidenceOracle
    python harness\\src\\debug_submit.py
"""

import hashlib
import json
import os
import random
import subprocess
import time

PKG_A  = "0x1e84478d9b09ca5b8f7bc0508ad4e80d19628250ec13517680ceae67e9d2b47a"
WALLET = "0xd0e7976a242007d7ce49087578e46f93ae9b5bbfd8288240c39691905a5572b3"
GAS    = "10000000"

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "..", "results")

d    = json.load(open(os.path.join(RESULTS_DIR, "object_ids.json")))
n2   = d["by_n"]["2"]
batch_id = n2["batch_object_id_a"]
dev_obj  = n2["device_object_ids"][0]
dev_addr = n2["device_addresses"][0]
wid      = str(n2["window_id"])

ts  = int(time.time() * 1000)
n   = random.randint(10000, 99999)
rh  = list(hashlib.sha256(f"{dev_addr}:1:{n}:{ts}".encode()).digest())
sh  = list(hashlib.sha256(bytes(rh)).digest())
rh_v = "vector[" + ",".join(str(b) for b in rh) + "]"
sh_v = "vector[" + ",".join(str(b) for b in sh) + "]"

print("batch_id :", batch_id)
print("dev_obj  :", dev_obj)
print("dev_addr :", dev_addr)
print("window_id:", wid)
print("ts_ms    :", ts)
print("nonce    :", n)
print()

cmd = [
    "iota", "client", "ptb",
    "--move-call", PKG_A + "::types::new_slot",
    "@" + dev_addr,
    "1",
    rh_v,
    str(ts),
    str(n),
    wid,
    sh_v,
    "--assign", "slot0",
    "--move-call", PKG_A + "::accumulator::submit_reading",
    "@" + batch_id,
    "@" + dev_obj,
    "slot0",
    "--gas-budget", GAS,
    "--json",
]

print("Command:")
print(" ".join(cmd[:10]) + " ...")
print()

r = subprocess.run(cmd, capture_output=True, text=True)

print("STDOUT:")
print(r.stdout[:2000] if r.stdout else "(empty)")
print()
print("STDERR:")
print(r.stderr[:2000] if r.stderr else "(empty)")
