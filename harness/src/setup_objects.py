import json
import os
import subprocess
import sys
import time

PACKAGE_ID_A_DEFAULT = "0x1e84478d9b09ca5b8f7bc0508ad4e80d19628250ec13517680ceae67e9d2b47a"
PACKAGE_ID_B_DEFAULT = "0xcde5399d72f19436e5c9b8e6c60be94645ee2e5ec23daeae9bfcadfb44b32174"
WALLET_DEFAULT       = "0xd0e7976a242007d7ce49087578e46f93ae9b5bbfd8288240c39691905a5572b3"

SENSOR_COUNTS      = [2, 4, 8, 16, 32]
WINDOW_DURATION_MS = 5000
GRACE_INTERVAL_MS  = 500
MAX_SPREAD_MS      = 3000
GAS_BUDGET         = 10000000

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "..", "results")


def load_env():
    env = {}
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
            print("Loaded .env from " + path)
            break
    return env


def run_cli(args):
    result = subprocess.run(["iota"] + args, capture_output=True, text=True)
    return result.stdout, result.stderr


def extract_first_object_id(stdout):
    try:
        data = json.loads(stdout)
        changes = data.get("objectChanges", [])
        for change in changes:
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


def create_device(package_id, device_addr, sensor_type):
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call",
        package_id + "::types::new_device",
        "@" + device_addr,
        str(sensor_type),
        "--assign", "dev",
        "--transfer-objects", "[dev]",
        "@" + WALLET_DEFAULT,
        "--gas-budget", str(GAS_BUDGET),
        "--json",
    ])
    obj_id = extract_first_object_id(stdout)
    if not obj_id:
        err = (stderr or "").strip()
        real_err = "\n".join(l for l in err.splitlines() if "mismatch" not in l and l.strip())
        if real_err:
            print("    PTB error: " + real_err[:300])
        else:
            print("    (no object ID returned)")
    return obj_id


def create_batch_a(package_id, window_id, window_start, window_end, n):
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call",
        package_id + "::types::new_batch",
        str(window_id), str(window_start), str(window_end),
        str(GRACE_INTERVAL_MS), str(n), str(MAX_SPREAD_MS),
        "--assign", "batch",
        "--transfer-objects", "[batch]",
        "@" + WALLET_DEFAULT,
        "--gas-budget", str(GAS_BUDGET),
        "--json",
    ])
    obj_id = extract_first_object_id(stdout)
    if not obj_id:
        err = (stderr or "").strip()
        real_err = "\n".join(l for l in err.splitlines() if "mismatch" not in l and l.strip())
        if real_err:
            print("    Batch PTB error: " + real_err[:300])
        else:
            print("    (no object ID returned)")
    return obj_id


def create_config_b(package_id, window_id, window_start, window_end, n):
    stdout, stderr = run_cli([
        "client", "ptb",
        "--move-call",
        package_id + "::types::new_config",
        str(window_id), str(window_start), str(window_end),
        str(GRACE_INTERVAL_MS), str(n), str(MAX_SPREAD_MS),
        "--assign", "cfg",
        "--transfer-objects", "[cfg]",
        "@" + WALLET_DEFAULT,
        "--gas-budget", str(GAS_BUDGET),
        "--json",
    ])
    obj_id = extract_first_object_id(stdout)
    if not obj_id:
        err = (stderr or "").strip()
        real_err = "\n".join(l for l in err.splitlines() if "mismatch" not in l and l.strip())
        if real_err:
            print("    Config PTB error: " + real_err[:300])
        else:
            print("    (no object ID returned)")
    return obj_id


def main():
    env = load_env()

    package_id_a = env.get("PACKAGE_ID_A") or PACKAGE_ID_A_DEFAULT
    package_id_b = env.get("PACKAGE_ID_B") or PACKAGE_ID_B_DEFAULT
    wallet       = env.get("WALLET_ADDRESS") or WALLET_DEFAULT

    print("Wallet : " + wallet)
    print("Pkg A  : " + package_id_a)
    print("Pkg B  : " + package_id_b)
    print()

    stdout, _ = run_cli(["client", "active-address"])
    active = stdout.strip()
    print("Active address: " + active)
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
        print("Creating objects for N=" + str(n) + " ...")
        now_ms       = int(time.time() * 1000)
        window_start = now_ms + 10000
        window_end   = window_start + WINDOW_DURATION_MS
        window_id    = n

        device_ids   = []
        device_addrs = []
        for i in range(n):
            sensor_addr = "0xdead" + format(i + 1, "060x")
            print("  Device " + str(i+1) + "/" + str(n) + " ...", end=" ", flush=True)
            obj_id = create_device(package_id_a, sensor_addr, i + 1)
            if obj_id:
                print("OK (" + obj_id[:12] + "...)")
            else:
                print("FAILED")
            device_ids.append(obj_id)
            device_addrs.append(sensor_addr)
            time.sleep(0.5)

        print("  EvidenceBatch (Design A) ...", end=" ", flush=True)
        batch_id_a = create_batch_a(package_id_a, window_id, window_start, window_end, n)
        print("OK (" + batch_id_a[:12] + "...)" if batch_id_a else "FAILED")
        time.sleep(0.5)

        print("  BatchConfig (Design B) ...", end=" ", flush=True)
        config_id_b = create_config_b(package_id_b, window_id, window_start, window_end, n)
        print("OK (" + config_id_b[:12] + "...)" if config_id_b else "FAILED")
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
    print("Object IDs written to " + out_path)

    failures = []
    for n_str, ids in object_ids["by_n"].items():
        missing = sum(1 for x in ids["device_object_ids"] if not x)
        if missing:
            failures.append("N=" + n_str + ": " + str(missing) + " device(s) failed")
        if not ids["batch_object_id_a"]:
            failures.append("N=" + n_str + ": EvidenceBatch creation failed")
        if not ids["config_object_id_b"]:
            failures.append("N=" + n_str + ": BatchConfig creation failed")

    if failures:
        print("")
        print("WARNING - some objects were not created:")
        for f in failures:
            print("  " + f)
    else:
        print("")
        print("All objects created successfully.")
        print("Next: python harness\\src\\run_baseline.py")


if __name__ == "__main__":
    main()