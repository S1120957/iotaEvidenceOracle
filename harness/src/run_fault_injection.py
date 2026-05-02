import csv
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

GRACE_INTERVAL_MS = 2000
MAX_SPREAD_MS     = 10000
WINDOWS_PER_RUN   = 10
SENSOR_COUNTS     = [2, 4, 8, 16, 32]
FAULT_SCENARIOS   = ["F1", "F2", "F3"]

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
    rh = list(hashlib.sha256(
        f"{device_addr}:{sensor_type}:{nonce}:{ts_ms}".encode()).digest())
    sh = list(hashlib.sha256(bytes(rh)).digest())
    rh_v = "vector[" + ",".join(str(b) for b in rh) + "]"
    sh_v = "vector[" + ",".join(str(b) for b in sh) + "]"
    return rh_v, sh_v


def create_batch(wid, ws, we, n, window_dur):
    stdout, _ = run_cli([
        "client", "ptb",
        "--move-call", PKG_A + "::types::new_batch",
        str(wid), str(ws), str(we),
        str(GRACE_INTERVAL_MS), str(n), str(MAX_SPREAD_MS),
        "--assign", "batch",
        "--transfer-objects", "[batch]", "@" + WALLET,
        "--gas-budget", GAS, "--json",
    ])
    return parse_object_id(stdout)


def run_fault_window(design, n, wid, ws, we, devices, fault):
    """
    Run one window with the given fault scenario applied to sensor 0.

    F1 — Missing sensor:    sensor 0 is silenced (skipped entirely)
    F2 — Late arrival:      sensor 0 submits with timestamp > we + grace
    F3 — Conflicting read:  sensor 0 submits twice with same sensor_type
    """
    window_dur = max(10000, n * 2000)
    batch_id = None

    if design == "A":
        batch_id = create_batch(wid, ws, we, n, window_dur)
        if not batch_id:
            return None

    wait_ms = ws - int(time.time() * 1000) + 50
    if wait_ms > 0:
        time.sleep(wait_ms / 1000.0)

    write_records = []

    for i in range(n):
        dev_obj  = devices["device_object_ids"][i]
        dev_addr = devices["device_addresses"][i]
        nonce    = random.randint(10000, 99999)
        ts_ms    = int(time.time() * 1000)

        # Apply fault to sensor 0 only
        if i == 0:
            if fault == "F1":
                # Silent — skip this sensor entirely
                write_records.append({
                    "sensor": i, "success": False,
                    "fault": "F1_silent", "latency_ms": 0,
                })
                continue
            elif fault == "F2":
                # Late timestamp — beyond we + grace
                ts_ms = we + GRACE_INTERVAL_MS + 500
            elif fault == "F3":
                # Will submit twice below
                pass

        rh_v, sh_v = make_vecs(dev_addr, i + 1, nonce, ts_ms)
        t_sub = time.time() * 1000

        if design == "A":
            stdout, stderr = run_cli([
                "client", "ptb",
                "--move-call", PKG_A + "::types::new_slot",
                "@" + dev_addr, str(i + 1), rh_v, str(ts_ms), str(nonce),
                str(wid), sh_v,
                "--assign", "slot",
                "--move-call", PKG_A + "::accumulator::submit_reading",
                "@" + batch_id, "@" + dev_obj, "slot",
                "--gas-budget", GAS, "--json",
            ])
        else:
            stdout, stderr = run_cli([
                "client", "ptb",
                "--move-call", PKG_B + "::accumulator::create_slot",
                "@" + dev_addr, str(i + 1), rh_v, str(ts_ms), str(nonce),
                str(wid), sh_v,
                "--gas-budget", GAS, "--json",
            ])

        t_conf  = time.time() * 1000
        digest  = parse_digest(stdout)
        status  = parse_status(stdout)
        success = status == "success" if design == "A" else bool(parse_object_id(stdout))

        write_records.append({
            "sensor": i, "success": success,
            "fault": fault if i == 0 else "none",
            "latency_ms": t_conf - t_sub,
        })

        # F3: submit duplicate for sensor 0 (same sensor_type = conflict)
        if i == 0 and fault == "F3":
            nonce2 = random.randint(10000, 99999)
            ts2    = int(time.time() * 1000)
            rh2, sh2 = make_vecs(dev_addr, i + 1, nonce2, ts2)
            if design == "A":
                run_cli([
                    "client", "ptb",
                    "--move-call", PKG_A + "::types::new_slot",
                    "@" + dev_addr, str(i + 1), rh2, str(ts2), str(nonce2),
                    str(wid), sh2,
                    "--assign", "slot2",
                    "--move-call", PKG_A + "::accumulator::submit_reading",
                    "@" + batch_id, "@" + dev_obj, "slot2",
                    "--gas-budget", GAS, "--json",
                ])
            else:
                run_cli([
                    "client", "ptb",
                    "--move-call", PKG_B + "::accumulator::create_slot",
                    "@" + dev_addr, str(i + 1), rh2, str(ts2), str(nonce2),
                    str(wid), sh2,
                    "--gas-budget", GAS, "--json",
                ])

    # Finalize for Design A
    batch_status = "slots_created"
    fin_latency  = None

    if design == "A" and batch_id:
        deadline = we + GRACE_INTERVAL_MS + 500
        wait_ms  = deadline - int(time.time() * 1000)
        if wait_ms > 0:
            time.sleep(wait_ms / 1000.0)

        current_time = int(time.time() * 1000)
        t_fin = time.time() * 1000
        stdout, _ = run_cli([
            "client", "ptb",
            "--move-call", PKG_A + "::accumulator::finalize",
            "@" + batch_id, str(current_time),
            "--gas-budget", GAS, "--json",
        ])
        fin_latency  = time.time() * 1000 - t_fin
        fin_status   = parse_status(stdout)
        success_count = sum(1 for w in write_records if w["success"])

        if fin_status == "success":
            if success_count >= n:
                batch_status = "finalized"
            else:
                batch_status = "expired"
        else:
            batch_status = "invalid"

    return {
        "design": design,
        "n": n,
        "fault": fault,
        "writes": write_records,
        "batch_status": batch_status,
        "finalization_latency_ms": fin_latency,
        "success_count": sum(1 for w in write_records if w["success"]),
    }


def main():
    obj_path = os.path.join(RESULTS_DIR, "object_ids.json")
    if not os.path.exists(obj_path):
        print("ERROR: object_ids.json not found.")
        sys.exit(1)

    with open(obj_path) as f:
        obj = json.load(f)

    print("Fault injection sweep — testnet")
    print("Faults: F1, F2, F3 | Designs: A, B | N: " + str(SENSOR_COUNTS))
    print("Windows per config: " + str(WINDOWS_PER_RUN))
    print()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    all_rows = []

    for fault in FAULT_SCENARIOS:
        for design in ["A", "B"]:
            for n in SENSOR_COUNTS:
                devices = obj["by_n"][str(n)]
                print("Fault=" + fault + " Design=" + design + " N=" + str(n) + " ...")

                for w_idx in range(WINDOWS_PER_RUN):
                    wid      = random.randint(1000, 8999)
                    now      = int(time.time() * 1000)
                    dur      = max(10000, n * 2000)
                    ws       = now + 2000
                    we       = ws + dur

                    rec = run_fault_window(design, n, wid, ws, we, devices, fault)
                    if rec is None:
                        continue

                    lats = [w["latency_ms"] for w in rec["writes"] if w["success"] and w["latency_ms"] > 0]
                    lats_s = sorted(lats)
                    p50 = lats_s[len(lats_s)//2] if lats_s else None

                    row = {
                        "fault": fault,
                        "design": design,
                        "N": n,
                        "window": w_idx,
                        "success_count": rec["success_count"],
                        "batch_status": rec["batch_status"],
                        "write_p50_ms": round(p50, 1) if p50 else None,
                        "finalization_latency_ms": round(rec["finalization_latency_ms"], 1) if rec["finalization_latency_ms"] else None,
                    }
                    all_rows.append(row)
                    time.sleep(0.5)

                    p50s = str(round(p50, 1)) if p50 else "N/A"
                    print("  w" + str(w_idx) + ": ok=" + str(rec["success_count"]) + "/" + str(n) + "  status=" + rec["batch_status"] + "  p50=" + p50s + "ms")

    raw_path = os.path.join(RESULTS_DIR, "raw_fault_testnet.csv")
    if all_rows:
        with open(raw_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_rows)
        print()
        print("Raw results -> " + raw_path)

    _write_table2(all_rows)


def _write_table2(rows):
    summary = {}
    for row in rows:
        key = (row["fault"], row["design"])
        if key not in summary:
            summary[key] = {
                "total": 0, "finalized": 0, "expired": 0,
                "invalid": 0, "complete": 0,
            }
        summary[key]["total"] += 1
        s = row["batch_status"]
        if s in summary[key]:
            summary[key][s] += 1
        n = row["N"]
        if row["success_count"] >= n:
            summary[key]["complete"] += 1

    path = os.path.join(RESULTS_DIR, "table2_testnet.csv")
    table_rows = []
    for (fault, design), v in sorted(summary.items()):
        t = v["total"]
        table_rows.append({
            "fault":            fault,
            "design":           design,
            "validity_pct":     round(v["finalized"] / t * 100, 1),
            "expired_pct":      round(v["expired"]   / t * 100, 1),
            "invalid_pct":      round(v["invalid"]    / t * 100, 1),
            "completeness_pct": round(v["complete"]   / t * 100, 1),
            "n_windows":        t,
        })

    if table_rows:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(table_rows[0].keys()))
            writer.writeheader()
            writer.writerows(table_rows)
        print("Table 2    -> " + path)
        print()
        print("Fault injection sweep complete.")


if __name__ == "__main__":
    main()