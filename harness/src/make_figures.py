from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
FIGS = ROOT / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

baseline_path = RESULTS / "table_write_latency.csv"
final_path = RESULTS / "table_finalization_latency.csv"
validity_path = RESULTS / "table_validity.csv"

def save_write_latency():
    df = pd.read_csv(baseline_path)
    fig, ax = plt.subplots(figsize=(6.5, 4.0))

    for design in sorted(df["design"].unique()):
        d = df[df["design"] == design].sort_values("N")
        ax.plot(d["N"], d["write_p50_ms"], marker="o", label=f"Design {design} p50")
        ax.plot(d["N"], d["write_p95_ms"], marker="s", linestyle="--", label=f"Design {design} p95")

    ax.set_xlabel("Sensor count N")
    ax.set_ylabel("Write latency (ms)")
    ax.set_title("Write-path latency by design")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGS / "write_latency_by_design.pdf")
    fig.savefig(FIGS / "write_latency_by_design.png", dpi=300)
    plt.close(fig)

def save_finalization_latency():
    df = pd.read_csv(final_path)
    fig, ax = plt.subplots(figsize=(6.5, 4.0))

    for design in sorted(df["design"].unique()):
        d = df[df["design"] == design].sort_values("N")
        ax.plot(d["N"], d["finalize_p50_ms"], marker="o", label=f"Design {design} p50")
        ax.plot(d["N"], d["finalize_p95_ms"], marker="s", linestyle="--", label=f"Design {design} p95")

    ax.set_xlabel("Sensor count N")
    ax.set_ylabel("Finalization latency (ms)")
    ax.set_title("Finalization latency by design")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGS / "finalization_latency_by_design.pdf")
    fig.savefig(FIGS / "finalization_latency_by_design.png", dpi=300)
    plt.close(fig)

def save_valid_batch_rate():
    df = pd.read_csv(baseline_path)
    pivot = df.pivot(index="N", columns="design", values="valid_batch_rate")
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    pivot.plot(kind="bar", ax=ax)

    ax.set_xlabel("Sensor count N")
    ax.set_ylabel("Valid-batch formation rate (%)")
    ax.set_title("Valid-batch formation rate")
    ax.set_ylim(0, 105)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGS / "valid_batch_rate.pdf")
    fig.savefig(FIGS / "valid_batch_rate.png", dpi=300)
    plt.close(fig)

def save_false_valid_rate():
    df = pd.read_csv(validity_path)
    pivot = df.pivot(index="fault_type", columns="design", values="false_valid_rate")
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    pivot.plot(kind="bar", ax=ax)

    ax.set_xlabel("Fault scenario")
    ax.set_ylabel("False-valid rate (%)")
    ax.set_title("False-valid rate under fault injection")
    ax.set_ylim(0, 5)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGS / "false_valid_rate.pdf")
    fig.savefig(FIGS / "false_valid_rate.png", dpi=300)
    plt.close(fig)

if __name__ == "__main__":
    save_write_latency()
    save_finalization_latency()
    save_valid_batch_rate()
    save_false_valid_rate()
    print(f"Figures written to {FIGS}")