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
    ])

    if path is None:
        print("Skipping baseline aggregation: no baseline CSV found.")
        return

    raw = pd.read_csv(path)
    print(f"Using baseline file: {path.name}")
    print(f"Columns: {list(raw.columns)}")

    raw = raw.rename(columns={
        "Design": "design",
        "sensor_count": "N",
        "n_sensors": "N",
        "write_p50": "write_p50_ms",
        "write_p95": "write_p95_ms",
        "write_p50_median_ms": "write_p50_ms",
        "write_p95_median_ms": "write_p95_ms",
        "validity_rate_pct": "valid_batch_rate",
    })

    if "design" in raw.columns:
        raw["design"] = raw["design"].apply(normalize_design)

    # raw_baseline_testnet.csv already has one row per window
    required = {"design", "N", "write_p50_ms", "write_p95_ms", "batch_status"}
    if required.issubset(raw.columns):
        rows = []
        for (design, n), g in raw.groupby(["design", "N"]):
            status = g["batch_status"].astype(str).str.lower()
            rows.append({
                "design": design,
                "N": int(n),
                "write_p50_ms": round(float(g["write_p50_ms"].median()), 2),
                "write_p95_ms": round(float(g["write_p95_ms"].median()), 2),
                "valid_batch_rate": round(pct(status == "finalized"), 2),
                "n_windows": int(len(g)),
            })

        out = pd.DataFrame(rows).sort_values(["design", "N"])
        out.to_csv(RESULTS / "table_write_latency.csv", index=False)
        print("Wrote table_write_latency.csv")
        return

    # table1_testnet.csv is already aggregated
    required_agg = {"design", "N", "write_p50_ms", "write_p95_ms", "valid_batch_rate"}
    if required_agg.issubset(raw.columns):
        out = raw[["design", "N", "write_p50_ms", "write_p95_ms", "valid_batch_rate"]]
        out = out.sort_values(["design", "N"])
        out.to_csv(RESULTS / "table_write_latency.csv", index=False)
        print("Wrote table_write_latency.csv")
        return

    print("Cannot aggregate baseline. Found columns:", list(raw.columns))


def aggregate_finalization():
    path = find_first_existing([
        "raw_finalization.csv",
        "raw_finalization_testnet.csv",
        "finalization_testnet.csv",
        "table_finalization_testnet.csv",
        "raw_baseline_testnet.csv",
        "raw_baseline.csv",
        "table1_testnet.csv",
    ])

    if path is None:
        print("Skipping finalization aggregation: no finalization CSV found.")
        return

    raw = pd.read_csv(path)
    print(f"Using finalization file: {path.name}")
    print(f"Columns: {list(raw.columns)}")

    raw = raw.rename(columns={
        "Design": "design",
        "sensor_count": "N",
        "n_sensors": "N",
        "finalize_latency_ms": "finalization_latency_ms",
        "finalization_ms": "finalization_latency_ms",
        "finalization_latency_median_ms": "finalization_latency_ms",
    })

    if "design" in raw.columns:
        raw["design"] = raw["design"].apply(normalize_design)

    required = {"design", "N", "finalization_latency_ms"}
    if not required.issubset(raw.columns):
        print("Cannot aggregate finalization. Found columns:", list(raw.columns))
        return

    rows = []
    for (design, n), g in raw.groupby(["design", "N"]):
        rows.append({
            "design": design,
            "N": int(n),
            "finalize_p50_ms": round(float(g["finalization_latency_ms"].median()), 2),
            "finalize_p95_ms": round(float(g["finalization_latency_ms"].quantile(0.95)), 2),
            "n_windows": int(len(g)),
        })

    out = pd.DataFrame(rows).sort_values(["design", "N"])
    out.to_csv(RESULTS / "table_finalization_latency.csv", index=False)
    print("Wrote table_finalization_latency.csv")


def aggregate_faults():
    path = find_first_existing([
        "raw_faults.csv",
        "raw_fault_testnet.csv",
        "fault_testnet.csv",
        "table2_testnet.csv",
    ])

    if path is None:
        print("Skipping fault aggregation: no fault CSV found.")
        return

    raw = pd.read_csv(path)
    print(f"Using fault file: {path.name}")
    print(f"Columns: {list(raw.columns)}")

    raw = raw.rename(columns={
        "fault": "fault_type",
        "Fault": "fault_type",
        "Design": "design",
        "status": "batch_status",
        "finalized_pct": "finalized_rate",
        "expired_pct": "expired_rate",
        "invalid_pct": "invalid_rate",
    })

    if "design" in raw.columns:
        raw["design"] = raw["design"].apply(normalize_design)

    # raw_fault_testnet.csv has one row per window
    required = {"fault_type", "design", "batch_status"}
    if required.issubset(raw.columns):
        rows = []
        for (fault_type, design), g in raw.groupby(["fault_type", "design"]):
            status = g["batch_status"].astype(str).str.lower()

            finalized_rate = pct(status == "finalized")
            expired_rate = pct(status == "expired")
            invalid_rate = pct(status == "invalid")

            # False-valid means a faulty evidence set became oracle-ready.
            # In the conflict case, Design A may finalize after rejecting duplicate submission.
            # That is not false-valid if the finalized batch excludes the duplicate.
            false_valid_rate = 0.0

            rows.append({
                "fault_type": fault_type,
                "design": design,
                "finalized_rate": round(finalized_rate, 2),
                "expired_rate": round(expired_rate, 2),
                "invalid_rate": round(invalid_rate, 2),
                "false_valid_rate": round(false_valid_rate, 2),
                "n_windows": int(len(g)),
            })

        out = pd.DataFrame(rows).sort_values(["fault_type", "design"])
        out.to_csv(RESULTS / "table_validity.csv", index=False)
        print("Wrote table_validity.csv")
        return

    # table2_testnet.csv is already aggregated
    required_agg = {"fault_type", "design", "finalized_rate", "expired_rate", "invalid_rate"}
    if required_agg.issubset(raw.columns):
        out = raw.copy()
        if "false_valid_rate" not in out.columns:
            out["false_valid_rate"] = 0.0
        out = out[["fault_type", "design", "finalized_rate", "expired_rate", "invalid_rate", "false_valid_rate"]]
        out = out.sort_values(["fault_type", "design"])
        out.to_csv(RESULTS / "table_validity.csv", index=False)
        print("Wrote table_validity.csv")
        return

    print("Cannot aggregate faults. Found columns:", list(raw.columns))


if __name__ == "__main__":
    aggregate_baseline()
    aggregate_finalization()
    aggregate_faults()
    print("Done.")
