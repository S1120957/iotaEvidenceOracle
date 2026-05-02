"""
sensor.py — Concurrent sensor simulation.

Each sensor is modelled as an async task that:
  1. Builds a signed EvidenceSlot payload
  2. Submits the transaction (Design A: shared write, Design B: owned slot)
  3. Polls for confirmation
  4. Records t_submit and t_confirmed

Jitter of [0, JITTER_MAX_MS] is applied to each submission timestamp
to simulate heterogeneous device clocks and network delay.
"""

import asyncio
import hashlib
import random
import time
from dataclasses import dataclass
from typing import Optional

from config import (
    JITTER_MAX_MS, PACKAGE_ID_A, PACKAGE_ID_B, RPC_URL,
    WINDOW_DURATION_MS, GRACE_INTERVAL_MS,
)
from metrics import SensorWriteRecord


@dataclass
class SensorConfig:
    sensor_index: int
    device_address: str          # funded address for this sensor
    sensor_type: int             # 1–N
    window_id: int
    window_start_ms: int
    window_end_ms: int
    nonce: int
    design: str                  # "A" or "B"
    fault: str = "baseline"      # baseline | F1 (silent) | F2 (late) | F3 (duplicate)


def _reading_hash(device_address: str, sensor_type: int, nonce: int) -> bytes:
    """SHA-256 commitment to the simulated reading payload."""
    payload = f"{device_address}:{sensor_type}:{nonce}:{time.time_ns()}"
    return hashlib.sha256(payload.encode()).digest()


def _sig_hash(reading_hash: bytes, device_address: str) -> bytes:
    """Simulated signature hash (software attestation for prototype)."""
    return hashlib.sha256(reading_hash + device_address.encode()).digest()


async def submit_sensor_write(
    cfg:     SensorConfig,
    client,                      # iota_sdk.Client instance
    keypair,                     # signing keypair for this sensor address
) -> SensorWriteRecord:
    """
    Execute one sensor write transaction and return timing measurements.

    Design A: calls design_a::accumulator::submit_reading
              (shared-object transaction, goes through consensus)
    Design B: calls design_b::accumulator::create_slot
              (owned-object creation, fast path)
    """
    record = SensorWriteRecord(sensor_index=cfg.sensor_index)

    # F1: silenced sensor — return immediately with no submission
    if cfg.fault == "F1":
        record.success = False
        return record

    # Compute submission timestamp with jitter
    jitter_ms = random.randint(0, JITTER_MAX_MS)
    ts_ms = cfg.window_start_ms + jitter_ms

    # F2: late arrival — submit after we + delta_g
    if cfg.fault == "F2":
        ts_ms = cfg.window_end_ms + GRACE_INTERVAL_MS + 100  # epsilon = 100 ms

    r_hash = _reading_hash(cfg.device_address, cfg.sensor_type, cfg.nonce)
    s_hash = _sig_hash(r_hash, cfg.device_address)

    # Build transaction based on design
    if cfg.design == "A":
        tx_data = _build_tx_design_a(cfg, ts_ms, r_hash, s_hash)
    else:
        tx_data = _build_tx_design_b(cfg, ts_ms, r_hash, s_hash)

    # F3: duplicate — submit twice with same sensor_type (different nonce)
    # The second submission is sent right after the first.
    submissions = [tx_data]
    if cfg.fault == "F3":
        nonce2 = cfg.nonce + 1000
        r_hash2 = _reading_hash(cfg.device_address, cfg.sensor_type, nonce2)
        s_hash2  = _sig_hash(r_hash2, cfg.device_address)
        if cfg.design == "A":
            tx_dup = _build_tx_design_a(cfg, ts_ms + 50, r_hash2, s_hash2,
                                        nonce_override=nonce2)
        else:
            tx_dup = _build_tx_design_b(cfg, ts_ms + 50, r_hash2, s_hash2,
                                        nonce_override=nonce2)
        submissions.append(tx_dup)

    # Wait until window_start before firing
    now_ms = time.time() * 1000
    if now_ms < cfg.window_start_ms:
        await asyncio.sleep((cfg.window_start_ms - now_ms) / 1000.0)

    max_retries = 5
    for attempt in range(max_retries):
        try:
            record.t_submit_ms = time.time() * 1000
            digest = await _execute_tx(client, keypair, tx_data)
            record.t_confirmed_ms = time.time() * 1000
            record.success = True
            record.retries = attempt

            # F3: fire duplicate (expected to be rejected by on-chain logic)
            if cfg.fault == "F3" and len(submissions) > 1:
                try:
                    await _execute_tx(client, keypair, submissions[1])
                except Exception:
                    pass  # rejection is the expected outcome

            return record
        except Exception as e:
            record.retries = attempt + 1
            if attempt == max_retries - 1:
                print(f"[Sensor {cfg.sensor_index}] Failed after {max_retries} attempts: {e}")
                return record
            await asyncio.sleep(0.1 * (attempt + 1))  # exponential backoff

    return record


def _build_tx_design_a(cfg, ts_ms, r_hash, s_hash, nonce_override=None) -> dict:
    """
    Build a Move call to design_a::accumulator::submit_reading.
    The shared EvidenceBatch object ID must be known at call time.
    It is injected via cfg at runtime by run_baseline.py.
    """
    nonce = nonce_override if nonce_override is not None else cfg.nonce
    return {
        "package":   PACKAGE_ID_A,
        "module":    "accumulator",
        "function":  "submit_reading",
        "arguments": [
            cfg.batch_object_id,          # &mut EvidenceBatch (shared)
            cfg.device_object_id,         # &MedicalDevice (owned by sensor)
            {                             # EvidenceSlot (inline construction)
                "device_id":      cfg.device_address,
                "sensor_type":    cfg.sensor_type,
                "reading_hash":   list(r_hash),
                "timestamp":      ts_ms,
                "nonce":          nonce,
                "window_id":      cfg.window_id,
                "signature_hash": list(s_hash),
            },
        ],
        "gas_budget": 10_000_000,
    }


def _build_tx_design_b(cfg, ts_ms, r_hash, s_hash, nonce_override=None) -> dict:
    """
    Build a Move call to design_b::accumulator::create_slot.
    No shared object in arguments — owned-slot creation only.
    """
    nonce = nonce_override if nonce_override is not None else cfg.nonce
    return {
        "package":   PACKAGE_ID_B,
        "module":    "accumulator",
        "function":  "create_slot",
        "arguments": [
            cfg.device_address,    # device_id: address
            cfg.sensor_type,       # sensor_type: u8
            list(r_hash),          # reading_hash: vector<u8>
            ts_ms,                 # timestamp: u64
            nonce,                 # nonce: u64
            cfg.window_id,         # window_id: u64
            list(s_hash),          # signature_hash: vector<u8>
        ],
        "gas_budget": 5_000_000,
    }


async def _execute_tx(client, keypair, tx_data: dict) -> str:
    """
    Execute a transaction using the IOTA SDK and return the digest.
    Replace the stub below with the actual iota_sdk call once the SDK
    API is confirmed against the installed version.
    """
    # TODO: replace with actual iota_sdk.Client.execute_move_call() syntax
    # Example (adjust to actual SDK):
    #
    # result = await client.move_call(
    #     signer=keypair.address,
    #     package_object_id=tx_data["package"],
    #     module=tx_data["module"],
    #     function=tx_data["function"],
    #     type_arguments=[],
    #     arguments=tx_data["arguments"],
    #     gas_budget=tx_data["gas_budget"],
    # )
    # await client.wait_for_transaction(result.digest)
    # return result.digest
    raise NotImplementedError(
        "Replace _execute_tx with actual iota_sdk.Client call. "
        "See harness/src/sensor.py TODO comment."
    )
