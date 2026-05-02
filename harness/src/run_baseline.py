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

WINDOW_DURATION_MS = 10000   # base; scaled per N in run_design_a_window
GRACE_INTERVAL_MS  = 2000
MAX_SPREAD_MS      = 10000
WINDOWS_PER_RUN    = 50
SENSOR_COUNTS      = [2, 4, 8, 16, 32]

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


def create_batch_a(wid, ws, we, n):
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call", PKG_A + "::types::new_batch",
        str(wid), str(ws), str(we),
        str(GRACE_INTERVAL_MS), str(n), str(MAX_SPREAD_MS),
        "--assign", "batch",
        "--transfer-objects", "[batch]", "@" + WALLET,
        "--gas-budget", GAS, "--json",
    ])
    return parse_object_id(stdout)


def run_design_a_window(n, wid, ws, we, devices):
    batch_id = create_batch_a(wid, ws, we, n)
    if not batch_id:
        return None

    # Wait for window to open
    wait_ms = ws - int(time.time() * 1000) + 50
    if wait_ms > 0:
        time.sleep(wait_ms / 1000.0)

    write_records = []
    for i in range(n):
        dev_obj  = devices["device_object_ids"][i]
        dev_addr = devices["device_addresses"][i]
        ts_ms    = int(time.time() * 1000)
        nonce    = random.randint(10000, 99999)
        rh_v, sh_v = make_vecs(dev_addr, i + 1, nonce, ts_ms)

        t_sub = time.time() * 1000
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
        t_conf = time.time() * 1000
        digest = parse_digest(stdout)
        status = parse_status(stdout)
        write_records.append({
            "sensor": i,
            "t_submit_ms": t_sub,
            "t_confirmed_ms": t_conf,
            "latency_ms": t_conf - t_sub,
            "success": status == "success",
            "digest": digest,
        })

    # Wait for grace interval
    deadline = we + GRACE_INTERVAL_MS + 500
    wait_ms  = deadline - int(time.time() * 1000)
    if wait_ms > 0:
        time.sleep(wait_ms / 1000.0)

    t_fin_start = time.time() * 1000
    current_time = int(time.time() * 1000)
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call", PKG_A + "::accumulator::finalize",
        "@" + batch_id, str(current_time),
        "--gas-budget", GAS, "--json",
    ])
    t_fin_end  = time.time() * 1000
    fin_digest = parse_digest(stdout)
    fin_status = parse_status(stdout)

    return {
        "design": "A",
        "n": n,
        "window_id": wid,
        "batch_id": batch_id,
        "writes": write_records,
        "finalization_latency_ms": t_fin_end - t_fin_start,
        "fin_digest": fin_digest,
        "batch_status": "finalized" if fin_status == "success" else "failed",
        "window_end_ms": we,
        "t_finalized_ms": t_fin_end,
    }


def run_design_b_window(n, wid, ws, we, devices):
    # Wait for window to open
    wait_ms = ws - int(time.time() * 1000) + 50
    if wait_ms > 0:
        time.sleep(wait_ms / 1000.0)

    write_records = []
    slot_ids = []
    for i in range(n):
        dev_addr = devices["device_addresses"][i]
        ts_ms    = int(time.time() * 1000)
        nonce    = random.randint(10000, 99999)
        rh_v, sh_v = make_vecs(dev_addr, i + 1, nonce, ts_ms)

        t_sub = time.time() * 1000
        stdout, stderr = run_cli([
            "client", "ptb",
            "--move-call", PKG_B + "::accumulator::create_slot",
            "@" + dev_addr, str(i + 1), rh_v, str(ts_ms), str(nonce),
            str(wid), sh_v,
            "--gas-budget", GAS, "--json",
        ])
        t_conf = time.time() * 1000
        slot_id = parse_object_id(stdout)
        digest  = parse_digest(stdout)
        success = bool(digest)
        if slot_id:
            slot_ids.append(slot_id)
        elif digest:
            slot_ids.append(digest)
        write_records.append({
            "sensor": i,
            "t_submit_ms": t_sub,
            "t_confirmed_ms": t_conf,
            "latency_ms": t_conf - t_sub,
            "success": success,
            "digest": digest,
            "slot_id": slot_id,
        })

    return {
        "design": "B",
        "n": n,
        "window_id": wid,
        "writes": write_records,
        "slot_ids": slot_ids,
        "window_end_ms": we,
    }


def compute_metrics(window_record):
    writes = window_record["writes"]
    lats   = [w["latency_ms"] for w in writes if w["success"]]
    lats_sorted = sorted(lats)
    n = len(lats_sorted)
    p50 = lats_sorted[n // 2] if n else None
    p95 = lats_sorted[int(n * 0.95)] if n else None
    return {
        "write_p50_ms": p50,
        "write_p95_ms": p95,
        "success_count": sum(1 for w in writes if w["success"]),
        "retry_rate_pct": 0.0,
    }


def main():
    obj_path = os.path.join(RESULTS_DIR, "object_ids.json")
    if not os.path.exists(obj_path):
        print("ERROR: object_ids.json not found. Run setup_objects.py first.")
        sys.exit(1)

    with open(obj_path) as f:
        obj = json.load(f)

    print("Baseline sweep — testnet")
    print("Designs: A, B | N: " + str(SENSOR_COUNTS))
    print("Windows per config: " + str(WINDOWS_PER_RUN))
    print()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    all_rows = []

    for design in ["A", "B"]:
        for n in SENSOR_COUNTS:
            devices = obj["by_n"][str(n)]
            print("Design " + design + " N=" + str(n) + " ...")

            window_rows = []
            for w_idx in range(WINDOWS_PER_RUN):
                wid = random.randint(1000, 8999)
                now = int(time.time() * 1000)
                ws  = now + 2000
                we  = ws + max(WINDOW_DURATION_MS, n * 2000)

                if design == "A":
                    rec = run_design_a_window(n, wid, ws, we, devices)
                    if rec is None:
                        print("  Window " + str(w_idx) + ": batch creation failed, skipping")
                        continue
                    m = compute_metrics(rec)
                    row = {
                        "design": "A",
                        "N": n,
                        "window": w_idx,
                        "write_p50_ms": m["write_p50_ms"],
                        "write_p95_ms": m["write_p95_ms"],
                        "finalization_latency_ms": rec["finalization_latency_ms"],
                        "batch_status": rec["batch_status"],
                        "success_count": m["success_count"],
                    }
                else:
                    rec = run_design_b_window(n, wid, ws, we, devices)
                    m   = compute_metrics(rec)
                    row = {
                        "design": "B",
                        "N": n,
                        "window": w_idx,
                        "write_p50_ms": m["write_p50_ms"],
                        "write_p95_ms": m["write_p95_ms"],
                        "finalization_latency_ms": None,
                        "batch_status": "slots_created",
                        "success_count": m["success_count"],
                    }

                p50s = str(round(row["write_p50_ms"], 1)) if row["write_p50_ms"] else "N/A"
                print("  w" + str(w_idx) + ": p50=" + p50s + "ms  status=" + str(row["batch_status"]) + "  ok=" + str(row["success_count"]) + "/" + str(n))
                window_rows.append(row)
                all_rows.append(row)
                time.sleep(1.0)

    raw_path = os.path.join(RESULTS_DIR, "raw_baseline_testnet.csv")
    if all_rows:
        with open(raw_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_rows)
        print()
        print("Raw results -> " + raw_path)

    table1_path = os.path.join(RESULTS_DIR, "table1_testnet.csv")
    _write_table1(all_rows, table1_path)
    print("Table 1    -> " + table1_path)
    print()
    print("Baseline sweep complete.")


def _write_table1(rows, path):
    summary = {}
    for row in rows:
        key = (row["design"], row["N"])
        if key not in summary:
            summary[key] = {"p50s": [], "p95s": [], "fin_lats": [], "statuses": []}
        if row["write_p50_ms"]:
            summary[key]["p50s"].append(row["write_p50_ms"])
        if row["write_p95_ms"]:
            summary[key]["p95s"].append(row["write_p95_ms"])
        if row["finalization_latency_ms"]:
            summary[key]["fin_lats"].append(row["finalization_latency_ms"])
        summary[key]["statuses"].append(row["batch_status"])

    def med(xs):
        if not xs:
            return None
        xs = sorted(xs)
        return xs[len(xs) // 2]

    table_rows = []
    for (design, n), vals in sorted(summary.items()):
        valid = sum(1 for s in vals["statuses"] if s == "finalized")
        table_rows.append({
            "design": design,
            "N": n,
            "write_p50_median_ms": med(vals["p50s"]),
            "write_p95_median_ms": med(vals["p95s"]),
            "finalization_latency_median_ms": med(vals["fin_lats"]),
            "validity_rate_pct": round(valid / len(vals["statuses"]) * 100, 1),
            "n_windows": len(vals["statuses"]),
        })

    if table_rows:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(table_rows[0].keys()))
            writer.writeheader()
            writer.writerows(table_rows)


if __name__ == "__main__":
    main()