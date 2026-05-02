"""
window_closer.py — Window finalization for Design A and Design B.

Design A: calls finalize on the shared EvidenceBatch after we + delta_g.
Design B: collects owned EvidenceSlot IDs and calls finalize_from_slots.

Records t_finalized_ms and terminal batch status.
"""

import asyncio
import time
from typing import Optional

from config import GRACE_INTERVAL_MS, PACKAGE_ID_A, PACKAGE_ID_B
import iota_client


async def finalize_window(
    design:             str,
    window_end_ms:      float,
    signer_alias:       str,
    batch_object_id:    Optional[str]  = None,   # Design A
    slot_object_ids:    Optional[list] = None,   # Design B
    config_object_id:   Optional[str]  = None,   # Design B
    registry_object_id: Optional[str]  = None,   # Design B
) -> dict:
    """
    Wait until window_end + grace_interval, then trigger finalization.
    Returns { t_finalized_ms, batch_status }.
    """
    deadline_ms = window_end_ms + GRACE_INTERVAL_MS
    now_ms      = time.time() * 1000
    if now_ms < deadline_ms:
        await asyncio.sleep((deadline_ms - now_ms) / 1000.0)

    current_time_ms = int(time.time() * 1000)

    try:
        if design == "A":
            t_sub, t_conf, digest, success = iota_client.finalize_design_a(
                package_id      = PACKAGE_ID_A,
                batch_object_id = batch_object_id,
                current_time_ms = current_time_ms,
                signer_alias    = signer_alias,
            )
        else:
            t_sub, t_conf, digest, success = iota_client.finalize_design_b(
                package_id         = PACKAGE_ID_B,
                slot_object_ids    = slot_object_ids or [],
                config_object_id   = config_object_id,
                registry_object_id = registry_object_id,
                current_time_ms    = current_time_ms,
                signer_alias       = signer_alias,
            )

        t_finalized = t_conf

        # Query the batch status from chain
        batch_status = "unknown"
        if success and batch_object_id:
            await asyncio.sleep(0.5)  # brief pause for state to settle
            batch_status = await iota_client.get_batch_status(batch_object_id) or "unknown"
        elif success:
            batch_status = "finalized"  # Design B creates the batch on success

        return {
            "t_finalized_ms": t_finalized,
            "batch_status":   batch_status,
        }

    except Exception as e:
        print(f"[WindowCloser] finalize error: {e}")
        return {
            "t_finalized_ms": None,
            "batch_status":   "error",
        }
