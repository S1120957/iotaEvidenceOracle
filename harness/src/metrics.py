"""
metrics.py — Latency recording, aggregation, and CSV output.

Metrics recorded per window (Section V.4 of the paper):
  1. write_latency_ms        — t_confirmed - t_submit per sensor (p50, p95)
  2. finalization_latency_ms — t_finalized - window_end
  3. oracle_readiness_delay_ms — t_finalized - t_last_confirmed_slot
  4. retry_count             — failed/retried transactions per window
  5. batch_completeness      — bool: |B| >= k
  6. batch_valid             — bool: ValidBatch(B) == true
  7. writes_per_second       — confirmed writes / window_duration_s
"""

import os
import time
import statistics
import csv
from dataclasses import dataclass, field
from typing import List, Optional
from config import RESULTS_DIR


@dataclass
class SensorWriteRecord:
    """One sensor write transaction."""
    sensor_index:    int
    t_submit_ms:     float   # wall-clock at submission
    t_confirmed_ms:  Optional[float] = None   # wall-clock at confirmation
    retries:         int = 0
    success:         bool = False

    @property
    def latency_ms(self) -> Optional[float]:
        if self.t_confirmed_ms is None:
            return None
        return self.t_confirmed_ms - self.t_submit_ms


@dataclass
class WindowRecord:
    """All metrics for one window execution."""
    design:              str      # "A" or "B"
    sensor_count:        int      # N
    window_index:        int
    window_end_ms:       float
    writes:              List[SensorWriteRecord] = field(default_factory=list)
    t_finalized_ms:      Optional[float] = None
    batch_status:        Optional[str] = None   # finalized|expired|invalid
    fault_scenario:      str = "baseline"       # baseline|F1|F2|F3

    # ── Derived metrics ────────────────────────────────────────────────────

    def write_latencies(self) -> List[float]:
        return [w.latency_ms for w in self.writes if w.latency_ms is not None]

    def write_p50(self) -> Optional[float]:
        lats = self.write_latencies()
        return statistics.median(lats) if lats else None

    def write_p95(self) -> Optional[float]:
        lats = sorted(self.write_latencies())
        if not lats:
            return None
        idx = int(len(lats) * 0.95)
        return lats[min(idx, len(lats) - 1)]

    def finalization_latency_ms(self) -> Optional[float]:
        if self.t_finalized_ms is None:
            return None
        return self.t_finalized_ms - self.window_end_ms

    def oracle_readiness_delay_ms(self) -> Optional[float]:
        """Elapsed from last confirmed slot to ValidBatch(B) = true."""
        confirmed = [w.t_confirmed_ms for w in self.writes
                     if w.t_confirmed_ms is not None]
        if not confirmed or self.t_finalized_ms is None:
            return None
        if self.batch_status != "finalized":
            return None
        return self.t_finalized_ms - max(confirmed)

    def retry_count(self) -> int:
        return sum(w.retries for w in self.writes)

    def retry_rate_pct(self) -> float:
        total = len(self.writes)
        if total == 0:
            return 0.0
        return (self.retry_count() / total) * 100.0

    def completeness(self) -> bool:
        """True if |B| >= k (k == sensor_count for baseline)."""
        return sum(1 for w in self.writes if w.success) >= self.sensor_count

    def is_valid(self) -> bool:
        return self.batch_status == "finalized"

    def writes_per_second(self) -> Optional[float]:
        successful = sum(1 for w in self.writes if w.success)
        dur_s = self.sensor_count  # window_duration_s is fixed at 5 s
        # Use actual window duration from config to avoid circular import
        return successful / 5.0


# ── Aggregation ──────────────────────────────────────────────────────────────

def aggregate(records: List[WindowRecord]) -> dict:
    """Aggregate 50-window records into the values needed for Table 1/2."""
    write_p50s  = [r.write_p50() for r in records if r.write_p50() is not None]
    write_p95s  = [r.write_p95() for r in records if r.write_p95() is not None]
    fin_lats    = [r.finalization_latency_ms() for r in records
                   if r.finalization_latency_ms() is not None]
    or_delays   = [r.oracle_readiness_delay_ms() for r in records
                   if r.oracle_readiness_delay_ms() is not None]
    retry_rates = [r.retry_rate_pct() for r in records]

    def med(xs): return statistics.median(xs) if xs else None

    return {
        "write_p50_median_ms":       med(write_p50s),
        "write_p95_median_ms":       med(write_p95s),
        "finalization_latency_ms":   med(fin_lats),
        "oracle_readiness_delay_ms": med(or_delays),
        "retry_rate_pct":            med(retry_rates),
        "completeness_rate_pct":     sum(r.completeness() for r in records)
                                     / len(records) * 100,
        "validity_rate_pct":         sum(r.is_valid() for r in records)
                                     / len(records) * 100,
        "n_windows":                 len(records),
    }


# ── CSV output ────────────────────────────────────────────────────────────────

def save_window_records(records: List[WindowRecord], filename: str):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, filename)
    fields = [
        "design", "sensor_count", "window_index", "fault_scenario",
        "write_p50_ms", "write_p95_ms", "finalization_latency_ms",
        "oracle_readiness_delay_ms", "retry_rate_pct",
        "completeness", "batch_valid", "batch_status",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({
                "design":                    r.design,
                "sensor_count":              r.sensor_count,
                "window_index":              r.window_index,
                "fault_scenario":            r.fault_scenario,
                "write_p50_ms":              r.write_p50(),
                "write_p95_ms":              r.write_p95(),
                "finalization_latency_ms":   r.finalization_latency_ms(),
                "oracle_readiness_delay_ms": r.oracle_readiness_delay_ms(),
                "retry_rate_pct":            r.retry_rate_pct(),
                "completeness":              r.completeness(),
                "batch_valid":               r.is_valid(),
                "batch_status":              r.batch_status,
            })
    print(f"Saved {len(records)} records → {path}")
