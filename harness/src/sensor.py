"""
sensor.py — Concurrent sensor simulation.

Each sensor is modelled as an async task that:
  Design A: calls submit_reading (shared-object transaction)
  Design B: calls create_slot   (owned-object creation, fast path)

Records t_submit_ms and t_confirmed_ms for every write attempt.
Fault modes F1 (silent), F2 (late), F3 (duplicate) are supported.
"""

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Optional

from config import (
    WINDOW_DURATION_MS, GRACE_INTERVAL_MS, JITTER_MAX_MS,
    LATE_OFFSET_MS, PACKAGE_ID_A, PACKAGE_ID_B,
)
from metrics import SensorWriteRecord
import iota_client


@dataclass
class SensorConfig:
    sensor_index:      int
    signer_alias:      str          # iota client alias for this sensor address
    device_address:    str          # on-chain device_id (address type)
    device_object_id:  str          # MedicalDevice object ID (Design A only)
    sensor_type:       int          # 1-based sensor type index
    window_id:         int
    window_start_ms:   int
    window_end_ms:     int
    nonce:             int
    design:            str          # "A" or "B"
    fault:             str = "baseline"  # baseline | F1 | F2 | F3

    # Design A specific
    batch_object_id:   str = ""

    # Design B: populated after create_slot returns
    slot_object_id:    Optional[str] = None


async def run_sensor(cfg: SensorConfig) -> SensorWriteRecord:
    """
    Execute one sensor write and return timing measurements.
    """
    record = SensorWriteRecord(sensor_index=cfg.sensor_index)

    # F1: silenced — no submission
    if cfg.fault == "F1":
        record.success = False
        return record

    # Compute submission timestamp with jitter
    jitter_ms     = random.randint(0, JITTER_MAX_MS)
    timestamp_ms  = cfg.window_start_ms + jitter_ms

    # F2: late arrival — submit after grace interval
    if cfg.fault == "F2":
        timestamp_ms = cfg.window_end_ms + GRACE_INTERVAL_MS + LATE_OFFSET_MS

    # Wait until window_start before firing
    now_ms = time.time() * 1000
    if now_ms < cfg.window_start_ms:
        await asyncio.sleep((cfg.window_start_ms - now_ms) / 1000.0)

    max_retries = 5
    for attempt in range(max_retries):
        try:
            if cfg.design == "A":
                t_sub, t_conf, digest, success = await iota_client.submit_reading_design_a(
                    package_id       = PACKAGE_ID_A,
                    batch_object_id  = cfg.batch_object_id,
                    device_object_id = cfg.device_object_id,
                    device_addr      = cfg.device_address,
                    sensor_type      = cfg.sensor_type,
                    timestamp_ms     = timestamp_ms,
                    nonce            = cfg.nonce,
                    window_id        = cfg.window_id,
                    signer_alias     = cfg.signer_alias,
                )
            else:
                t_sub, t_conf, digest, slot_id, success = await iota_client.create_slot_design_b(
                    package_id   = PACKAGE_ID_B,
                    device_addr  = cfg.device_address,
                    sensor_type  = cfg.sensor_type,
                    timestamp_ms = timestamp_ms,
                    nonce        = cfg.nonce,
                    window_id    = cfg.window_id,
                    signer_alias = cfg.signer_alias,
                )
                if slot_id:
                    cfg.slot_object_id = slot_id

            record.t_submit_ms    = t_sub
            record.t_confirmed_ms = t_conf
            record.success        = success
            record.retries        = attempt

            # F3: fire duplicate after first success
            if cfg.fault == "F3" and success and cfg.design == "B":
                await iota_client.create_slot_design_b(
                    package_id   = PACKAGE_ID_B,
                    device_addr  = cfg.device_address,
                    sensor_type  = cfg.sensor_type,   # same type = conflict
                    timestamp_ms = timestamp_ms + 50,
                    nonce        = cfg.nonce + 1000,   # different nonce
                    window_id    = cfg.window_id,
                    signer_alias = cfg.signer_alias,
                )

            return record

        except Exception as e:
            record.retries = attempt + 1
            if attempt == max_retries - 1:
                print(f"[Sensor {cfg.sensor_index}] Failed after {max_retries}: {e}")
                return record
            await asyncio.sleep(0.1 * (attempt + 1))

    return record
