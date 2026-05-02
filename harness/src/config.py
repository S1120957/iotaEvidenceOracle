"""
config.py — Experiment parameters
All values that appear in the paper are defined here.
Edit this file before running experiments; do not scatter constants.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Network ────────────────────────────────────────────────────────────────
ENV = os.getenv("IOTA_ENV", "localnet")   # localnet | testnet

RPC_URLS = {
    "localnet": "http://127.0.0.1:9000",
    "testnet":  "https://api.testnet.iota.cafe",
}
RPC_URL = RPC_URLS[ENV]

# ── Deployed package IDs (filled by deploy.sh) ────────────────────────────
PACKAGE_ID_A = os.getenv("PACKAGE_ID_A", "")   # Design A
PACKAGE_ID_B = os.getenv("PACKAGE_ID_B", "")   # Design B

# ── Window parameters (match the paper: Section V) ────────────────────────
WINDOW_DURATION_MS = 5_000     # W = 5 s
GRACE_INTERVAL_MS  =   500     # delta_g = 500 ms
MAX_SPREAD_MS      = 3_000     # Delta W = 3 s (accommodate full 5 s window)

# ── Baseline workload ──────────────────────────────────────────────────────
SENSOR_COUNTS  = [2, 4, 8, 16, 32]   # N values
WINDOWS_PER_RUN = 50                  # repetitions per configuration

# ── Jitter (simulates heterogeneous device clocks) ─────────────────────────
JITTER_MAX_MS = 200    # uniform random in [0, JITTER_MAX_MS]

# ── Fault injection parameters ────────────────────────────────────────────
# F2: late arrival offset beyond we + delta_g
LATE_OFFSET_MS = 100   # epsilon = 100 ms

# ── Results output ────────────────────────────────────────────────────────
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")

# ── Testnet subset (Section V.2) ─────────────────────────────────────────
TESTNET_SENSOR_COUNTS = [4, 16]
