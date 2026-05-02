"""
window_closer.py — Window finalization for Design A and Design B.

Design A: calls design_a::accumulator::finalize on the shared EvidenceBatch.
Design B: collects owned EvidenceSlot object IDs and calls
          design_b::accumulator::finalize_from_slots via PTB.

Records t_finalized and the terminal batch status.
"""

import asyncio
import time
from typing import List, Optional

from config import PACKAGE_ID_A, PACKAGE_ID_B, GRACE_INTERVAL_MS


async def finalize_window(
    design:          str,
    client,
    keypair,
    window_end_ms:   float,
    batch_object_id: Optional[str],    # Design A only
    slot_object_ids: Optional[List[str]],  # Design B only
    config_object_id: Optional[str],   # Design B only
    device_object_ids: Optional[List[str]],  # Design B only
) -> dict:
    """
    Wait until window_end + grace_interval, then trigger finalization.
    Returns: { t_finalized_ms, batch_status }
    """
    deadline_ms = window_end_ms + GRACE_INTERVAL_MS
    now_ms = time.time() * 1000
    if now_ms < deadline_ms:
        await asyncio.sleep((deadline_ms - now_ms) / 1000.0)

    current_time_ms = int(time.time() * 1000)

    if design == "A":
        tx = _build_finalize_a(batch_object_id, current_time_ms)
    else:
        tx = _build_finalize_b(
            slot_object_ids, config_object_id,
            device_object_ids, current_time_ms,
        )

    try:
        t_start = time.time() * 1000
        digest = await _execute_tx(client, keypair, tx)
        t_finalized = time.time() * 1000

        # Query batch status from the chain
        batch_status = await _query_batch_status(
            client, design, batch_object_id, digest
        )

        return {
            "t_finalized_ms": t_finalized,
            "batch_status":   batch_status,
        }
    except Exception as e:
        return {
            "t_finalized_ms": None,
            "batch_status":   "error",
        }


def _build_finalize_a(batch_object_id: str, current_time_ms: int) -> dict:
    return {
        "package":   PACKAGE_ID_A,
        "module":    "accumulator",
        "function":  "finalize",
        "arguments": [batch_object_id, current_time_ms],
        "gas_budget": 10_000_000,
    }


def _build_finalize_b(
    slot_ids: List[str],
    config_id: str,
    device_ids: List[str],
    current_time_ms: int,
) -> dict:
    """
    Programmable Transaction Block: pass all owned slot objects to
    finalize_from_slots in a single transaction.
    """
    return {
        "package":   PACKAGE_ID_B,
        "module":    "accumulator",
        "function":  "finalize_from_slots",
        "arguments": [
            slot_ids,           # vector<EvidenceSlot> (owned objects)
            config_id,          # &BatchConfig
            device_ids,         # &vector<MedicalDevice>
            current_time_ms,    # current_time_ms: u64
        ],
        "gas_budget": 50_000_000,   # higher: PTB merging N slots
    }


async def _execute_tx(client, keypair, tx_data: dict) -> str:
    """Stub — replace with actual iota_sdk call."""
    raise NotImplementedError(
        "Replace _execute_tx in window_closer.py with actual iota_sdk call."
    )


async def _query_batch_status(
    client, design: str, batch_id: Optional[str], digest: str
) -> str:
    """
    Query the terminal status of the EvidenceBatch after finalization.
    Returns one of: finalized | expired | invalid | unknown
    Status codes: 0=open 1=finalized 2=expired 3=invalid
    """
    # TODO: query the batch object's `status` field using iota_sdk
    # Example:
    #   obj = await client.get_object(batch_id)
    #   status_code = obj.data.content.fields["status"]
    #   return {1: "finalized", 2: "expired", 3: "invalid"}.get(status_code, "unknown")
    raise NotImplementedError(
        "Replace _query_batch_status with actual iota_sdk object query."
    )
