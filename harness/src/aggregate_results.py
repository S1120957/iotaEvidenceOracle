from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

def pct(x):
    return 100.0 * float(np.mean(x))

def aggregate_baseline():
    raw = pd.read_csv(RESULTS / "raw_baseline.csv")

    rows = []
    for (design, n), g in raw.groupby(["design", "N"]):
        rows.append({
            "design": design,
            "N": int(n),
            "write_p50_ms": round(float(g["write_latency_ms"].median()), 2),
            "write_p95_ms": round(float(g["write_latency_ms"].quantile(0.95)), 2),
            "valid_batch_rate": round(pct(g["valid_batch"].astype(bool)), 2),
            "retry_rate": round(pct(g["retry_count"].fillna(0) > 0), 2),
            "success_rate": round(pct(g["success"].astype(bool)), 2),
        })

    out = pd.DataFrame(rows).sort_values(["design", "N"])
    out.to_csv(RESULTS / "table_write_latency.csv", index=False)

def aggregate_finalization():
    raw = pd.read_csv(RESULTS / "raw_finalization.csv")

    rows = []
    for (design, n), g in raw.groupby(["design", "N"]):
        rows.append({
            "design": design,
            "N": int(n),
            "finalize_p50_ms": round(float(g["finalization_latency_ms"].median()), 2),
            "finalize_p95_ms": round(float(g["finalization_latency_ms"].quantile(0.95)), 2),
            "valid_batch_rate": round(pct(g["valid_batch"].astype(bool)), 2),
            "success_rate": round(pct(g["success"].astype(bool)), 2),
        })

    out = pd.DataFrame(rows).sort_values(["design", "N"])
    out.to_csv(RESULTS / "table_finalization_latency.csv", index=False)

def aggregate_faults():
    raw = pd.read_csv(RESULTS / "raw_faults.csv")

    rows = []
    for (fault_type, design), g in raw.groupby(["fault_type", "design"]):
        status = g["batch_status"].astype(str).str.lower()
        rows.append({
            "fault_type": fault_type,
            "design": design,
            "finalized_rate": round(pct(status == "finalized"), 2),
            "expired_rate": round(pct(status == "expired"), 2),
            "invalid_rate": round(pct(status == "invalid"), 2),
            "false_valid_rate": round(pct(g["false_valid"].astype(bool)), 2),
        })

    out = pd.DataFrame(rows).sort_values(["fault_type", "design"])
    out.to_csv(RESULTS / "table_validity.csv", index=False)

if __name__ == "__main__":
    aggregate_baseline()
    aggregate_finalization()
    aggregate_faults()
    print("Aggregated CSVs written to harness/results/")