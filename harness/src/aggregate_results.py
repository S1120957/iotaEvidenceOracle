from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def pct(x):
    return 100.0 * float(np.mean(x))


def find_first_existing(candidates):
    for name in candidates:
        path = RESULTS / name
        if path.exists():
            return path
    return None


def normalize_design(value):
    s = str(value).strip()
    if s.lower() in {"a", "design_a", "shared", "shared_accumulator"}:
        return "A"
    if s.lower() in {"b", "design_b", "owned", "owned_slot", "owned_slot_staging"}:
        return "B"
    return s


def aggregate_baseline():
    path = find_first_existing([
        "raw_baseline.csv",
        "raw_baseline_testnet.csv",
        "baseline_testnet.csv",
        "table1_testnet.csv",
        "table2_testnet.csv",
    ])

    if path is None:
        print("Skipping baseline aggregation: no baseline CSV found.")
        return

    raw = pd.read_csv(path)
    print(f"Using baseline file: {path.name}")
    print(f"Columns: {list(raw.columns)}")

    # Normalize common column names.
    rename_map = {
        "Design": "design",
        "design_name": "design",
        "sensor_count": "N",
        "n_sensors": "N",
        "write_p50": "write_p50_ms",
        "write_p50_ms": "write_p50_ms",
        "write_p95": "write_p95_ms",
        "write_p95_ms": "write_p95_ms",
        "latency_ms": "write_latency_ms",
        "valid_rate": "valid_batch_rate",
        "valid_percent": "valid_batch_rate",
        "valid_batch_percent": "valid_batch_rate",
        "valid_batches": "valid_batch_rate",
    }
    raw = raw.rename(columns={k: v for k, v in rename_map.items() if k in raw.columns})

    if "design" in raw.columns:
        raw["design"] = raw["design"].apply(normalize_design)

    # Case 1: file is already aggregated.
    already_aggregated = {"design", "N", "write_p50_ms", "write_p95_ms"}.issubset(raw.columns)
    if already_aggregated:
        out = raw.copy()

        if "valid_batch_rate" not in out.columns:
            if "valid_batch" in out.columns:
                out["valid_batch_rate"] = out["valid_batch"].astype(float) * 100
            elif "Valid.%" in out.columns:
                out["valid_batch_rate"] = out["Valid.%"]
            else:
                out["valid_batch_rate"] = np.nan

        keep = ["design", "N", "write_p50_ms", "write_p95_ms", "valid_batch_rate"]
        out = out[[c for c in keep if c in out.columns]].sort_values(["design", "N"])
        out.to_csv(RESULTS / "table_write_latency.csv", index=False)
        print("Wrote table_write_latency.csv")
        return

    # Case 2: file is raw transaction-level.
    required = {"design", "N", "write_latency_ms"}
    if not required.issubset(raw.columns):
        print("Cannot aggregate baseline. Missing required columns:")
        print("Required:", required)
        print("Found:", set(raw.columns))
        return

    rows = []
    for (design, n), g in raw.groupby(["design", "N"]):
        valid_rate = np.nan
        if "valid_batch" in g.columns:
            valid_rate = pct(g["valid_batch"].astype(bool))
        elif "success" in g.columns:
            valid_rate = pct(g["success"].astype(bool))

        rows.append({
            "design": design,
            "N": int(n),
            "write_p50_ms": round(float(g["write_latency_ms"].median()), 2),
            "write_p95_ms": round(float(g["write_latency_ms"].quantile(0.95)), 2),
            "valid_batch_rate": round(valid_rate, 2) if not np.isnan(valid_rate) else np.nan,
        })

    out = pd.DataFrame(rows).sort_values(["design", "N"])
    out.to_csv(RESULTS / "table_write_latency.csv", index=False)
    print("Wrote table_write_latency.csv")


def aggregate_finalization():
    path = find_first_existing([
        "raw_finalization.csv",
        "raw_finalization_testnet.csv",
        "finalization_testnet.csv",
        "table_finalization_testnet.csv",
    ])

    if path is None:
        print("Skipping finalization aggregation: no finalization CSV found.")
        return

    raw = pd.read_csv(path)
    print(f"Using finalization file: {path.name}")
    print(f"Columns: {list(raw.columns)}")

    rename_map = {
        "Design": "design",
        "sensor_count": "N",
        "n_sensors": "N",
        "finalize_latency_ms": "finalization_latency_ms",
        "finalization_ms": "finalization_latency_ms",
    }
    raw = raw.rename(columns={k: v for k, v in rename_map.items() if k in raw.columns})

    if "design" in raw.columns:
        raw["design"] = raw["design"].apply(normalize_design)

    required = {"design", "N", "finalization_latency_ms"}
    if not required.issubset(raw.columns):
        print("Cannot aggregate finalization. Missing required columns:")
        print("Required:", required)
        print("Found:", set(raw.columns))
        return

    rows = []
    for (design, n), g in raw.groupby(["design", "N"]):
        rows.append({
            "design": design,
            "N": int(n),
            "finalize_p50_ms": round(float(g["finalization_latency_ms"].median()), 2),
            "finalize_p95_ms": round(float(g["finalization_latency_ms"].quantile(0.95)), 2),
        })

    out = pd.DataFrame(rows).sort_values(["design", "N"])
    out.to_csv(RESULTS / "table_finalization_latency.csv", index=False)
    print("Wrote table_finalization_latency.csv")


def aggregate_faults():
    path = find_first_existing([
        "raw_faults.csv",
        "raw_fault_testnet.csv",
        "fault_testnet.csv",
        "table_validity.csv",
        "table2_testnet.csv",
    ])

    if path is None:
        print("Skipping fault aggregation: no fault CSV found.")
        return

    raw = pd.read_csv(path)
    print(f"Using fault file: {path.name}")
    print(f"Columns: {list(raw.columns)}")

    rename_map = {
        "Design": "design",
        "fault": "fault_type",
        "Fault": "fault_type",
        "status": "batch_status",
        "finalized_rate": "finalized_rate",
        "expired_rate": "expired_rate",
        "invalid_rate": "invalid_rate",
        "false_valid": "false_valid",
    }
    raw = raw.rename(columns={k: v for k, v in rename_map.items() if k in raw.columns})

    if "design" in raw.columns:
        raw["design"] = raw["design"].apply(normalize_design)

    # Case 1: already aggregated fault table.
    already_aggregated = {"fault_type", "design"}.issubset(raw.columns) and (
        {"finalized_rate", "expired_rate", "invalid_rate"}.intersection(raw.columns)
    )
    if already_aggregated:
        out = raw.copy()
        if "false_valid_rate" not in out.columns:
            if "false_valid" in out.columns:
                out["false_valid_rate"] = out["false_valid"].astype(float) * 100
            else:
                out["false_valid_rate"] = 0.0

        keep = ["fault_type", "design", "finalized_rate", "expired_rate", "invalid_rate", "false_valid_rate"]
        out = out[[c for c in keep if c in out.columns]].sort_values(["fault_type", "design"])
        out.to_csv(RESULTS / "table_validity.csv", index=False)
        print("Wrote table_validity.csv")
        return

    # Case 2: raw fault-level data.
    required = {"fault_type", "design", "batch_status"}
    if not required.issubset(raw.columns):
        print("Cannot aggregate faults. Missing required columns:")
        print("Required:", required)
        print("Found:", set(raw.columns))
        return

    rows = []
    for (fault_type, design), g in raw.groupby(["fault_type", "design"]):
        status = g["batch_status"].astype(str).str.lower()

        if "false_valid" in g.columns:
            false_valid_rate = pct(g["false_valid"].astype(bool))
        else:
            false_valid_rate = pct(status == "false_valid")

        rows.append({
            "fault_type": fault_type,
            "design": design,
            "finalized_rate": round(pct(status == "finalized"), 2),
            "expired_rate": round(pct(status == "expired"), 2),
            "invalid_rate": round(pct(status == "invalid"), 2),
            "false_valid_rate": round(false_valid_rate, 2),
        })

    out = pd.DataFrame(rows).sort_values(["fault_type", "design"])
    out.to_csv(RESULTS / "table_validity.csv", index=False)
    print("Wrote table_validity.csv")


if __name__ == "__main__":
    aggregate_baseline()
    aggregate_finalization()
    aggregate_faults()
    print("Done.")