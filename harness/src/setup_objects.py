import json
import os
import subprocess
import sys
import time


PACKAGE_ID_A_DEFAULT = "0x1e84478d9b09ca5b8f7bc0508ad4e80d19628250ec13517680ceae67e9d2b47a"
PACKAGE_ID_B_DEFAULT = "0x7a29c93f655f8c3ec8f985c36110fb0a1b874d31f50c34058b25c5252976d8f3"
WALLET_DEFAULT = "0xd0e7976a242007d7ce49087578e46f93ae9b5bbfd8288240c39691905a5572b3"

SENSOR_COUNTS = [2, 4, 8, 16]
WINDOW_DURATION_MS = 3_600_000
GRACE_INTERVAL_MS = 60_000
MAX_SPREAD_MS = 3_600_000
GAS_BUDGET = 20_000_000

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "results"))


def load_env():
    env = {}
    candidates = [
        os.path.join(SCRIPT_DIR, "..", "..", ".env"),
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.getcwd(), "experiments.env"),
    ]
    for candidate in candidates:
        path = os.path.abspath(candidate)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
        print("Loaded environment from " + path)
        break
    return env


def run_cli(args):
    result = subprocess.run(["iota"] + args, capture_output=True, text=True, shell=False)
    return result.stdout, result.stderr, result.returncode


def extract_first_object_id(stdout):
    try:
        data = json.loads(stdout)
        for change in data.get("objectChanges", []):
            if change.get("type") == "created":
                object_id = change.get("objectId", "")
                if object_id:
                    return object_id
    except Exception:
        pass
    for line in stdout.splitlines():
        line = line.strip()
        if "ObjectID:" in line:
            return line.split("ObjectID:")[-1].strip()
    return ""


def clean_error(stderr, stdout=""):
    lines = []
    for line in (stderr or "").splitlines():
        if "mismatch" in line.lower():
            continue
        if line.strip():
            lines.append(line.strip())
    if lines:
        return "\n".join(lines)
    if stdout and stdout.strip():
        return stdout.strip()
    return ""


def create_device(package_id, wallet, device_addr, sensor_type):
    stdout, stderr, _ = run_cli([
        "client", "ptb", "--move-call", package_id + "::types::new_device",
        "@" + device_addr, str(sensor_type), "--assign", "dev",
        "--transfer-objects", "[dev]", "@" + wallet,
        "--gas-budget", str(GAS_BUDGET), "--json",
    ])
    object_id = extract_first_object_id(stdout)
    if not object_id:
        error = clean_error(stderr, stdout)
        print("    PTB error: " + error[:500] if error else "    No object ID returned")
    return object_id


def create_batch_a(package_id, wallet, window_id, window_start, window_end, n):
    stdout, stderr, _ = run_cli([
        "client", "ptb", "--move-call", package_id + "::types::new_batch",
        str(window_id), str(window_start), str(window_end),
        str(GRACE_INTERVAL_MS), str(n), str(MAX_SPREAD_MS),
        "--assign", "batch", "--transfer-objects", "[batch]", "@" + wallet,
        "--gas-budget", str(GAS_BUDGET), "--json",
    ])
    object_id = extract_first_object_id(stdout)
    if not object_id:
        error = clean_error(stderr, stdout)
        print("    Batch PTB error: " + error[:500] if error else "    No batch object ID returned")
    return object_id


def create_config_b(package_id, wallet, window_id, window_start, window_end, n):
    stdout, stderr, _ = run_cli([
        "client", "ptb", "--move-call", package_id + "::types::new_config",
        str(window_id), str(window_start), str(window_end),
        str(GRACE_INTERVAL_MS), str(n), str(MAX_SPREAD_MS),
        "--assign", "cfg", "--transfer-objects", "[cfg]", "@" + wallet,
        "--gas-budget", str(GAS_BUDGET), "--json",
    ])
    object_id = extract_first_object_id(stdout)
    if not object_id:
        error = clean_error(stderr, stdout)
        print("    Config PTB error: " + error[:500] if error else "    No config object ID returned")
    return object_id


def main():
    env = load_env()
    package_id_a = env.get("PACKAGE_ID_A") or PACKAGE_ID_A_DEFAULT
    package_id_b = env.get("PACKAGE_ID_B") or PACKAGE_ID_B_DEFAULT
    wallet = env.get("WALLET_ADDRESS") or WALLET_DEFAULT

    print("Wallet : " + wallet)
    print("Pkg A  : " + package_id_a)
    print("Pkg B  : " + package_id_b)
    print()

    stdout, stderr, _ = run_cli(["client", "active-address"])
    active_address = stdout.strip()
    print("Active address: " + active_address)
    if not active_address.startswith("0x"):
        print("ERROR: iota client active-address did not return an address.")
        print("Run: iota client switch --env testnet")
        if stderr:
            print(stderr)
        sys.exit(1)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    object_ids = {"wallet": wallet, "package_a": package_id_a, "package_b": package_id_b, "by_n": {}}

    for n in SENSOR_COUNTS:
        print("\nCreating objects for N=" + str(n) + " ...")
        now_ms = int(time.time() * 1000)
        window_start = now_ms + 10_000
        window_end = window_start + WINDOW_DURATION_MS
        window_id = n
        device_ids_a, device_ids_b, device_addrs = [], [], []

        for i in range(n):
            sensor_addr = "0xdead" + format(i + 1, "060x")
            sensor_type = i + 1
            device_addrs.append(sensor_addr)

            print("  Device A " + str(i + 1) + "/" + str(n) + " ...", end=" ", flush=True)
            obj_id_a = create_device(package_id_a, wallet, sensor_addr, sensor_type)
            print("OK (" + obj_id_a[:12] + "...)" if obj_id_a else "FAILED")
            device_ids_a.append(obj_id_a)
            time.sleep(0.5)

            print("  Device B " + str(i + 1) + "/" + str(n) + " ...", end=" ", flush=True)
            obj_id_b = create_device(package_id_b, wallet, sensor_addr, sensor_type)
            print("OK (" + obj_id_b[:12] + "...)" if obj_id_b else "FAILED")
            device_ids_b.append(obj_id_b)
            time.sleep(0.5)

        print("  EvidenceBatch (Design A) ...", end=" ", flush=True)
        batch_id_a = create_batch_a(package_id_a, wallet, window_id, window_start, window_end, n)
        print("OK (" + batch_id_a[:12] + "...)" if batch_id_a else "FAILED")
        time.sleep(0.5)

        print("  BatchConfig (Design B) ...", end=" ", flush=True)
        config_id_b = create_config_b(package_id_b, wallet, window_id, window_start, window_end, n)
        print("OK (" + config_id_b[:12] + "...)" if config_id_b else "FAILED")
        time.sleep(0.5)

        object_ids["by_n"][str(n)] = {
            "window_id": window_id,
            "window_start_ms": window_start,
            "window_end_ms": window_end,
            "device_object_ids_a": device_ids_a,
            "device_object_ids_b": device_ids_b,
            "device_addresses": device_addrs,
            "batch_object_id_a": batch_id_a,
            "config_object_id_b": config_id_b,
            "signer_alias": "default",
        }

    out_path = os.path.join(RESULTS_DIR, "object_ids.json")
    with open(out_path, "w", encoding="utf-8") as file:
        json.dump(object_ids, file, indent=2)
    print("\nObject IDs written to " + out_path)

    failures = []
    for n_str, ids in object_ids["by_n"].items():
        missing_a = sum(1 for x in ids["device_object_ids_a"] if not x)
        missing_b = sum(1 for x in ids["device_object_ids_b"] if not x)
        if missing_a:
            failures.append("N=" + n_str + ": " + str(missing_a) + " Design A device(s) failed")
        if missing_b:
            failures.append("N=" + n_str + ": " + str(missing_b) + " Design B device(s) failed")
        if not ids["batch_object_id_a"]:
            failures.append("N=" + n_str + ": EvidenceBatch creation failed")
        if not ids["config_object_id_b"]:
            failures.append("N=" + n_str + ": BatchConfig creation failed")

    if failures:
        print("\nWARNING - some objects were not created:")
        for failure in failures:
            print("  " + failure)
        sys.exit(2)

    print("\nAll objects created successfully.")
    print("Next: python harness\\src\\run_baseline.py --windows 10 --designs A B --sensor-counts 2 4 8 16 32")


if __name__ == "__main__":
    main()
