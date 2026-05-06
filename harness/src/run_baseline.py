import argparse
import csv
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from math import ceil
from typing import Any, Dict, List, Optional, Tuple


PKG_A  = ""
PKG_B  = ""
WALLET = ""

GAS                      = "100000000"
WINDOW_DURATION_MS       = 10000
GRACE_INTERVAL_MS        = 2000
MAX_SPREAD_MS            = 60000
DEFAULT_WINDOWS_PER_RUN  = 20
DEFAULT_SENSOR_COUNTS    = [2, 4, 8, 16]

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "results"))


# ── CLI helpers ───────────────────────────────────────────────────────────────

def run_cli(args: List[str]) -> Tuple[str, str, int]:
    result = subprocess.run(
        ["iota"] + args, capture_output=True, text=True, shell=False)
    return result.stdout, result.stderr, result.returncode


def parse_json(stdout: str) -> Dict[str, Any]:
    try:
        return json.loads(stdout)
    except Exception:
        return {}


def parse_object_id_from_digest(stdout: str, expected_digest: str) -> str:
    """
    Parse the created object ID only from a transaction with the expected
    digest. This prevents accidentally picking up object IDs from cached
    or replayed transactions.
    """
    data = parse_json(stdout)
    tx_digest = data.get("digest", "")
    if expected_digest and tx_digest != expected_digest:
        return ""
    for change in data.get("objectChanges", []):
        if change.get("type") == "created":
            oid = change.get("objectId", "")
            if oid:
                return oid
    return ""


def parse_object_id(stdout: str) -> str:
    data = parse_json(stdout)
    for change in data.get("objectChanges", []):
        if change.get("type") == "created":
            oid = change.get("objectId", "")
            if oid:
                return oid
    for line in stdout.splitlines():
        if "ObjectID:" in line:
            return line.split("ObjectID:")[-1].strip()
    return ""


def parse_digest(stdout: str) -> str:
    data = parse_json(stdout)
    digest = data.get("digest", "")
    if digest:
        return digest
    for line in stdout.splitlines():
        if "Transaction Digest:" in line:
            return line.split("Transaction Digest:")[-1].strip()
    return ""


def parse_status(stdout: str) -> str:
    data = parse_json(stdout)
    try:
        return data.get("effects", {}).get("status", {}).get("status", "")
    except Exception:
        return ""


def build_debug(stderr: str, stdout: str) -> str:
    if not stderr:
        return ""
    clean = "\n".join(
        l for l in stderr.strip().splitlines()
        if "mismatch" not in l and l.strip())
    return clean


def make_vecs(device_addr: str, sensor_type: int,
              nonce: int, ts_ms: int) -> Tuple[str, str]:
    rh = list(hashlib.sha256(
        f"{device_addr}:{sensor_type}:{nonce}:{ts_ms}".encode()).digest())
    sh = list(hashlib.sha256(bytes(rh)).digest())
    rh_v = "vector[" + ",".join(str(b) for b in rh) + "]"
    sh_v = "vector[" + ",".join(str(b) for b in sh) + "]"
    return rh_v, sh_v


# ── Stats helpers ─────────────────────────────────────────────────────────────

def percentile(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, ceil(q * len(values)) - 1))
    return values[idx]


def median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    return values[len(values) // 2]


def safe_round(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


# ── Device ID lookup ──────────────────────────────────────────────────────────

def get_device_ids_a(devices: Dict[str, Any], n: int) -> List[str]:
    ids = (devices.get("device_object_ids_a")
           or devices.get("device_object_ids", []))
    return ids[:n]


# ── Design A ──────────────────────────────────────────────────────────────────

def create_batch_a(wid: int, ws: int, we: int, n: int) -> str:
    stdout, stderr, _ = run_cli([
        "client", "ptb",
        "--move-call", f"{PKG_A}::types::new_batch",
        str(wid), str(ws), str(we),
        str(GRACE_INTERVAL_MS), str(n), str(MAX_SPREAD_MS),
        "--assign", "batch",
        "--transfer-objects", "[batch]", "@" + WALLET,
        "--gas-budget", GAS, "--json",
    ])
    batch_id = parse_object_id(stdout)
    if not batch_id:
        err = build_debug(stderr, stdout)
        if err:
            print("  [A] batch creation error:", err[:400])
    return batch_id


def run_design_a_window(
        n: int, wid: int, ws: int, we: int,
        devices: Dict[str, Any]) -> Optional[Dict[str, Any]]:

    batch_id = create_batch_a(wid, ws, we, n)
    if not batch_id:
        return None

    device_object_ids = get_device_ids_a(devices, n)
    device_addresses  = devices["device_addresses"][:n]

    wait_ms = ws - int(time.time() * 1000) + 50
    if wait_ms > 0:
        time.sleep(wait_ms / 1000.0)

    write_records = []
    for i in range(n):
        dev_obj  = device_object_ids[i]
        dev_addr = device_addresses[i]
        ts_ms    = int(time.time() * 1000)
        nonce    = random.randint(10000, 99999)
        rh_v, sh_v = make_vecs(dev_addr, i + 1, nonce, ts_ms)
        t_sub = time.time() * 1000
        stdout, stderr, _ = run_cli([
            "client", "ptb",
            "--move-call", f"{PKG_A}::types::new_slot",
            "@" + dev_addr, str(i + 1), rh_v,
            str(ts_ms), str(nonce), str(wid), sh_v,
            "--assign", "slot",
            "--move-call", f"{PKG_A}::accumulator::submit_reading",
            "@" + batch_id, "@" + dev_obj, "slot",
            "--gas-budget", GAS, "--json",
        ])
        t_conf = time.time() * 1000
        write_records.append({
            "sensor": i,
            "t_submit_ms": t_sub,
            "t_confirmed_ms": t_conf,
            "latency_ms": t_conf - t_sub,
            "success": parse_status(stdout) == "success",
            "digest": parse_digest(stdout),
        })

    deadline = we + GRACE_INTERVAL_MS + 500
    wait_ms  = deadline - int(time.time() * 1000)
    if wait_ms > 0:
        time.sleep(wait_ms / 1000.0)

    current_time = int(time.time() * 1000)
    t_fin_start  = time.time() * 1000
    stdout, stderr, _ = run_cli([
        "client", "ptb",
        "--move-call", f"{PKG_A}::accumulator::finalize",
        "@" + batch_id, str(current_time),
        "--gas-budget", GAS, "--json",
    ])
    t_fin_end  = time.time() * 1000
    fin_status = parse_status(stdout)
    fin_digest = parse_digest(stdout)

    return {
        "design": "A", "n": n, "window_id": wid,
        "batch_id": batch_id,
        "writes": write_records,
        "slot_ids": "",
        "finalization_latency_ms": t_fin_end - t_fin_start,
        "fin_digest": fin_digest,
        "fin_status": fin_status,
        "batch_status": "finalized" if fin_status == "success" else "failed",
        "window_end_ms": we,
        "t_finalized_ms": t_fin_end,
        "finalization_stderr": build_debug(stderr, stdout)
            if fin_status != "success" else "",
    }


# ── Design B ──────────────────────────────────────────────────────────────────

def create_config_b(wid: int, ws: int, we: int, n: int) -> str:
    stdout, stderr, _ = run_cli([
        "client", "ptb",
        "--move-call", f"{PKG_B}::types::new_config",
        str(wid), str(ws), str(we),
        str(GRACE_INTERVAL_MS), str(n), str(MAX_SPREAD_MS),
        "--assign", "config",
        "--transfer-objects", "[config]", "@" + WALLET,
        "--gas-budget", GAS, "--json",
    ])
    config_id = parse_object_id(stdout)
    if not config_id:
        err = build_debug(stderr, stdout)
        if err:
            print("  [B] config creation error:", err[:400])
    return config_id


def create_slot_b(dev_addr: str, sensor_type: int,
                  ts_ms: int, nonce: int, wid: int) -> Tuple[str, str, float, float]:
    """
    Create a single owned EvidenceSlot for Design B.
    Returns (slot_id, digest, t_submit_ms, t_confirm_ms).
    Validates that the returned slot belongs to a fresh transaction.
    """
    rh_v, sh_v = make_vecs(dev_addr, sensor_type, nonce, ts_ms)
    t_sub = time.time() * 1000
    stdout, stderr, _ = run_cli([
        "client", "ptb",
        "--move-call", f"{PKG_B}::accumulator::create_slot",
        "@" + dev_addr, str(sensor_type), rh_v,
        str(ts_ms), str(nonce), str(wid), sh_v,
        "--gas-budget", GAS, "--json",
    ])
    t_conf  = time.time() * 1000
    digest  = parse_digest(stdout)
    status  = parse_status(stdout)

    if status != "success" or not digest:
        return "", "", t_sub, t_conf

    # Parse slot_id only from this specific transaction digest
    slot_id = parse_object_id_from_digest(stdout, digest)
    return slot_id, digest, t_sub, t_conf


def finalize_design_b_slots(
        slot_ids: List[str],
        config_id: str,
        current_time_ms: int) -> Tuple[str, str, str]:
    slot_type = f"<{PKG_B}::types::EvidenceSlot>"
    slot_vec  = "[" + ",".join("@" + s for s in slot_ids) + "]"
    stdout, stderr, _ = run_cli([
        "client", "ptb",
        "--make-move-vec", slot_type, slot_vec,
        "--assign", "myslots",
        "--move-call", f"{PKG_B}::accumulator::finalize",
        "myslots", "@" + config_id, str(current_time_ms),
        "--gas-budget", GAS, "--json",
    ])
    status = parse_status(stdout)
    digest = parse_digest(stdout)
    err    = build_debug(stderr, stdout)
    if not err and status != "success":
        err = stdout[:600]
    return status, digest, err


def run_design_b_window(
        n: int, wid: int, ws: int, we: int,
        devices: Dict[str, Any]) -> Optional[Dict[str, Any]]:

    # Create fresh config with this window's wid
    config_id = create_config_b(wid, ws, we, n)
    if not config_id:
        return None

    device_addresses = devices["device_addresses"][:n]

    # Wait for window start
    wait_ms = ws - int(time.time() * 1000) + 50
    if wait_ms > 0:
        time.sleep(wait_ms / 1000.0)

    write_records = []
    slot_ids      = []

    for i in range(n):
        dev_addr    = device_addresses[i]
        ts_ms       = int(time.time() * 1000)
        nonce       = random.randint(10000, 99999)
        sensor_type = i + 1

        slot_id, digest, t_sub, t_conf = create_slot_b(
            dev_addr, sensor_type, ts_ms, nonce, wid)

        # Only accept slot if it was freshly created with correct wid
        success = bool(slot_id) and bool(digest)
        if success:
            slot_ids.append(slot_id)

        write_records.append({
            "sensor": i,
            "t_submit_ms": t_sub,
            "t_confirmed_ms": t_conf,
            "latency_ms": t_conf - t_sub,
            "success": success,
            "digest": digest,
            "slot_id": slot_id,
        })

    # Wait for grace interval
    deadline = we + GRACE_INTERVAL_MS + 500
    wait_ms  = deadline - int(time.time() * 1000)
    if wait_ms > 0:
        time.sleep(wait_ms / 1000.0)

    current_time = int(time.time() * 1000)
    t_fin_start  = time.time() * 1000

    if len(slot_ids) == n:
        fin_status, fin_digest, fin_stderr = finalize_design_b_slots(
            slot_ids, config_id, current_time)
    elif slot_ids:
        # Partial slots — attempt finalize anyway, predicate will expire it
        fin_status, fin_digest, fin_stderr = finalize_design_b_slots(
            slot_ids, config_id, current_time)
    else:
        fin_status = "failed"
        fin_digest = ""
        fin_stderr = f"0/{n} slots created"

    t_fin_end = time.time() * 1000

    if fin_stderr and fin_status != "success":
        print(f"    fin_stderr: {fin_stderr[:400]}")

    return {
        "design": "B", "n": n, "window_id": wid,
        "config_id": config_id,
        "writes": write_records,
        "slot_ids": ";".join(slot_ids),
        "finalization_latency_ms": t_fin_end - t_fin_start,
        "fin_digest": fin_digest,
        "fin_status": fin_status,
        "batch_status": "finalized" if fin_status == "success" else "failed",
        "window_end_ms": we,
        "t_finalized_ms": t_fin_end,
        "finalization_stderr": fin_stderr,
    }


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(record: Dict[str, Any]) -> Dict[str, Any]:
    lats = [w["latency_ms"] for w in record["writes"] if w["success"]]
    return {
        "write_p50_ms":  median(lats),
        "write_p95_ms":  percentile(lats, 0.95),
        "success_count": sum(1 for w in record["writes"] if w["success"]),
    }


# ── Output ────────────────────────────────────────────────────────────────────

def write_raw(rows: List[Dict[str, Any]], path: str) -> None:
    if not rows:
        return
    fields = [
        "design", "N", "window",
        "write_p50_ms", "write_p95_ms",
        "finalization_latency_ms", "batch_status",
        "success_count", "slot_ids", "fin_digest",
        "finalization_stderr",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_table1(rows: List[Dict[str, Any]], path: str) -> None:
    summary: Dict[Tuple[str, int], Dict] = {}
    for row in rows:
        key = (row["design"], row["N"])
        if key not in summary:
            summary[key] = {
                "p50s": [], "p95s": [], "fin_lats": [],
                "statuses": [], "success_counts": []}
        if row["write_p50_ms"] is not None:
            summary[key]["p50s"].append(float(row["write_p50_ms"]))
        if row["write_p95_ms"] is not None:
            summary[key]["p95s"].append(float(row["write_p95_ms"]))
        if row["finalization_latency_ms"] is not None:
            summary[key]["fin_lats"].append(
                float(row["finalization_latency_ms"]))
        summary[key]["statuses"].append(row["batch_status"])
        summary[key]["success_counts"].append(row["success_count"])

    table_rows = []
    for (design, n), v in sorted(summary.items()):
        finalized = sum(1 for s in v["statuses"] if s == "finalized")
        complete  = sum(1 for c in v["success_counts"] if int(c) == int(n))
        table_rows.append({
            "design":                        design,
            "N":                             n,
            "write_p50_median_ms":           safe_round(median(v["p50s"])),
            "write_p95_median_ms":           safe_round(median(v["p95s"])),
            "finalization_latency_median_ms":safe_round(
                median(v["fin_lats"])),
            "finalization_latency_p95_ms":   safe_round(
                percentile(v["fin_lats"], 0.95)),
            "write_success_rate_pct":        round(
                complete / len(v["statuses"]) * 100.0, 1),
            "validity_rate_pct":             round(
                finalized / len(v["statuses"]) * 100.0, 1),
            "n_windows":                     len(v["statuses"]),
        })

    if table_rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=list(table_rows[0].keys()))
            writer.writeheader()
            writer.writerows(table_rows)


# ── Entry point ───────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IOTA testnet baseline benchmark — Design A and B")
    parser.add_argument("--designs", nargs="+",
                        default=["A", "B"], choices=["A", "B"])
    parser.add_argument("--windows", type=int,
                        default=DEFAULT_WINDOWS_PER_RUN)
    parser.add_argument("--sensor-counts", nargs="+", type=int,
                        default=DEFAULT_SENSOR_COUNTS)
    parser.add_argument("--out",
                        default=os.path.join(
                            RESULTS_DIR, "raw_baseline_testnet.csv"))
    parser.add_argument("--table-out",
                        default=os.path.join(
                            RESULTS_DIR, "table1_testnet.csv"))
    return parser.parse_args()


def load_object_ids() -> Dict[str, Any]:
    global PKG_A, PKG_B, WALLET
    path = os.path.join(RESULTS_DIR, "object_ids.json")
    if not os.path.exists(path):
        print("ERROR: object_ids.json not found.")
        print("Run: python harness\\src\\setup_objects.py")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    PKG_A  = obj.get("package_a", "")
    PKG_B  = obj.get("package_b", "")
    WALLET = obj.get("wallet", "")
    if not PKG_A or not PKG_B or not WALLET:
        print("ERROR: package_a, package_b, or wallet missing.")
        sys.exit(1)
    print("Package A :", PKG_A)
    print("Package B :", PKG_B)
    print("Wallet    :", WALLET)
    print()
    return obj


def main() -> None:
    args    = parse_args()
    objects = load_object_ids()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("Baseline sweep — IOTA testnet")
    print("Designs       :", ", ".join(args.designs))
    print("Sensor counts :", args.sensor_counts,
          "  (N=2 ideal -> N=16 stress)")
    print("Windows/config:", args.windows)
    print()

    all_rows: List[Dict[str, Any]] = []

    for design in args.designs:
        for n in args.sensor_counts:
            devices = objects["by_n"][str(n)]
            print(f"Design {design}  N={n} ...")

            for w_idx in range(args.windows):
                wid = random.randint(1000, 8999)
                now = int(time.time() * 1000)
                ws  = now + 2000
                we  = ws + max(WINDOW_DURATION_MS, n * 2000)

                if design == "A":
                    record = run_design_a_window(n, wid, ws, we, devices)
                else:
                    record = run_design_b_window(n, wid, ws, we, devices)

                if record is None:
                    print(f"  w{w_idx}: setup failed, skipping")
                    continue

                m = compute_metrics(record)
                row = {
                    "design":                  design,
                    "N":                       n,
                    "window":                  w_idx,
                    "write_p50_ms":            safe_round(m["write_p50_ms"]),
                    "write_p95_ms":            safe_round(m["write_p95_ms"]),
                    "finalization_latency_ms": safe_round(
                        record["finalization_latency_ms"]),
                    "batch_status":            record["batch_status"],
                    "success_count":           m["success_count"],
                    "slot_ids":                record.get("slot_ids", ""),
                    "fin_digest":              record.get("fin_digest", ""),
                    "finalization_stderr":     record.get(
                        "finalization_stderr", ""),
                }

                p50s = ("N/A" if row["write_p50_ms"] is None
                        else f"{row['write_p50_ms']:.1f}")
                fins = ("N/A" if row["finalization_latency_ms"] is None
                        else f"{row['finalization_latency_ms']:.1f}")
                print(f"  w{w_idx}: p50={p50s}ms  fin={fins}ms  "
                      f"status={row['batch_status']}  "
                      f"ok={row['success_count']}/{n}")

                all_rows.append(row)
                time.sleep(1.0)

    write_raw(all_rows, args.out)
    write_table1(all_rows, args.table_out)
    print()
    print("Raw results  ->", args.out)
    print("Table 1      ->", args.table_out)
    print("Baseline sweep complete.")


if __name__ == "__main__":
    main()