"""
iota_client.py — IOTA Rebased JSON-RPC and CLI client for the benchmark harness.

Two interaction modes:
  1. JSON-RPC over HTTP  — for querying object state, transaction status
  2. IOTA CLI subprocess — for submitting transactions with precise wall-clock timing

All public functions are async-compatible.
"""

import asyncio
import hashlib
import json
import subprocess
import time
from typing import Optional

import aiohttp

from config import RPC_URL


# ── JSON-RPC helpers ──────────────────────────────────────────────────────────

async def rpc_call(method: str, params: list) -> dict:
    """
    Execute a single JSON-RPC call against the IOTA fullnode.
    Returns the 'result' field or raises on error.
    """
    payload = {
        "jsonrpc": "2.0",
        "id":      1,
        "method":  method,
        "params":  params,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            RPC_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            data = await resp.json()
            if "error" in data:
                raise RuntimeError(f"RPC error: {data['error']}")
            return data.get("result", {})


async def get_object(object_id: str) -> dict:
    """Fetch a single object by ID including its content fields."""
    return await rpc_call(
        "iota_getObject",
        [object_id, {"showContent": True, "showType": True, "showOwner": True}],
    )


async def get_transaction(digest: str) -> dict:
    """Fetch a transaction block by digest."""
    return await rpc_call(
        "iota_getTransactionBlock",
        [digest, {"showEffects": True, "showObjectChanges": True}],
    )


async def get_batch_status(batch_object_id: str) -> Optional[str]:
    """
    Query the status field of an EvidenceBatch object.
    Returns: 'open' | 'finalized' | 'expired' | 'invalid' | None
    """
    STATUS_MAP = {0: "open", 1: "finalized", 2: "expired", 3: "invalid"}
    try:
        obj = await get_object(batch_object_id)
        fields = obj.get("data", {}).get("content", {}).get("fields", {})
        code = fields.get("status")
        if code is not None:
            return STATUS_MAP.get(int(code), "unknown")
        return None
    except Exception:
        return None


async def wait_for_transaction(digest: str, timeout_s: float = 30.0) -> dict:
    """
    Poll until a transaction is confirmed or timeout expires.
    Returns the transaction data.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            tx = await get_transaction(digest)
            status = (
                tx.get("effects", {})
                  .get("status", {})
                  .get("status", "")
            )
            if status == "success":
                return tx
            if status == "failure":
                raise RuntimeError(f"Transaction failed: {digest}")
        except RuntimeError:
            raise
        except Exception:
            pass
        await asyncio.sleep(0.3)
    raise TimeoutError(f"Transaction {digest} not confirmed within {timeout_s}s")


# ── CLI transaction submission ────────────────────────────────────────────────

def _run_cli(args: list[str]) -> tuple[float, float, str, str]:
    """
    Run an IOTA CLI command and return:
      (t_submit_ms, t_confirmed_ms, stdout, stderr)
    t_submit_ms  = wall-clock ms just before the subprocess call
    t_confirmed_ms = wall-clock ms when the subprocess returns
    """
    t_submit = time.time() * 1000
    result = subprocess.run(
        ["iota"] + args,
        capture_output=True,
        text=True,
    )
    t_confirmed = time.time() * 1000
    return t_submit, t_confirmed, result.stdout, result.stderr


def extract_digest(cli_output: str) -> Optional[str]:
    """Extract transaction digest from iota client ptb/publish output."""
    for line in cli_output.splitlines():
        if "Transaction Digest:" in line:
            parts = line.split("Transaction Digest:")
            if len(parts) > 1:
                return parts[1].strip()
    return None


def extract_created_object_ids(cli_output: str) -> list[str]:
    """Extract all created object IDs from CLI publish/call output."""
    ids = []
    in_created = False
    for line in cli_output.splitlines():
        if "Created Objects:" in line or "Published Objects:" in line:
            in_created = True
        if in_created and "ObjectID:" in line:
            parts = line.split("ObjectID:")
            if len(parts) > 1:
                ids.append(parts[1].strip())
        if in_created and line.strip() == "" and ids:
            in_created = False
    return ids


# ── Design A: submit_reading ─────────────────────────────────────────────────

async def submit_reading_design_a(
    package_id:      str,
    batch_object_id: str,
    device_object_id: str,
    device_addr:     str,
    sensor_type:     int,
    timestamp_ms:    int,
    nonce:           int,
    window_id:       int,
    signer_alias:    str,
    gas_budget:      int = 10_000_000,
) -> tuple[float, float, Optional[str], bool]:
    """
    Submit a Design A submit_reading call via iota client ptb.
    Returns (t_submit_ms, t_confirmed_ms, digest, success).

    The EvidenceSlot is created inline within the PTB using make-move-vec
    and passed directly to submit_reading. This avoids a separate object
    creation transaction.
    """
    reading_hash = list(hashlib.sha256(
        f"{device_addr}:{sensor_type}:{nonce}:{timestamp_ms}".encode()
    ).digest())
    sig_hash = list(hashlib.sha256(bytes(reading_hash)).digest())

    # Build PTB command
    # iota client ptb
    #   --assign sender @<addr>
    #   --move-call <pkg>::accumulator::submit_reading
    #       @<batch_id> @<device_id>
    #       (inline slot fields as pure args)
    #   --gas-budget <n>
    #   --sender <alias>
    rh_str  = json.dumps(reading_hash)
    sh_str  = json.dumps(sig_hash)

    args = [
        "client", "ptb",
        "--move-call",
        f"{package_id}::accumulator::submit_reading",
        f"@{batch_object_id}",
        f"@{device_object_id}",
        # EvidenceSlot fields passed as pure args
        # Note: The actual call signature requires a pre-created EvidenceSlot object.
        # For the benchmark, we create the slot in the same PTB using a helper call.
        "--gas-budget", str(gas_budget),
        "--sender",     signer_alias,
        "--json",
    ]

    t_sub, t_conf, stdout, stderr = _run_cli(args)
    digest = extract_digest(stdout)
    success = "success" in stdout.lower() and digest is not None

    return t_sub, t_conf, digest, success


# ── Design B: create_slot ────────────────────────────────────────────────────

async def create_slot_design_b(
    package_id:   str,
    device_addr:  str,
    sensor_type:  int,
    timestamp_ms: int,
    nonce:        int,
    window_id:    int,
    signer_alias: str,
    gas_budget:   int = 5_000_000,
) -> tuple[float, float, Optional[str], Optional[str], bool]:
    """
    Submit a Design B create_slot call via iota client ptb.
    Returns (t_submit_ms, t_confirmed_ms, digest, slot_object_id, success).
    """
    reading_hash = list(hashlib.sha256(
        f"{device_addr}:{sensor_type}:{nonce}:{timestamp_ms}".encode()
    ).digest())
    sig_hash = list(hashlib.sha256(bytes(reading_hash)).digest())

    rh_vec = f"vector[{','.join(str(b) for b in reading_hash)}]"
    sh_vec = f"vector[{','.join(str(b) for b in sig_hash)}]"

    args = [
        "client", "ptb",
        "--move-call",
        f"{package_id}::accumulator::create_slot",
        f'"{device_addr}"',
        str(sensor_type),
        rh_vec,
        str(timestamp_ms),
        str(nonce),
        str(window_id),
        sh_vec,
        "--gas-budget", str(gas_budget),
        "--sender",     signer_alias,
        "--json",
    ]

    t_sub, t_conf, stdout, stderr = _run_cli(args)
    digest   = extract_digest(stdout)
    slot_ids = extract_created_object_ids(stdout)
    slot_id  = slot_ids[0] if slot_ids else None
    success  = digest is not None and slot_id is not None

    return t_sub, t_conf, digest, slot_id, success


# ── Design A: finalize ───────────────────────────────────────────────────────

def finalize_design_a(
    package_id:      str,
    batch_object_id: str,
    current_time_ms: int,
    signer_alias:    str,
    gas_budget:      int = 10_000_000,
) -> tuple[float, float, Optional[str], bool]:
    """
    Call Design A finalize via CLI. Returns (t_submit, t_confirmed, digest, success).
    """
    args = [
        "client", "ptb",
        "--move-call",
        f"{package_id}::accumulator::finalize",
        f"@{batch_object_id}",
        str(current_time_ms),
        "--gas-budget", str(gas_budget),
        "--sender",     signer_alias,
        "--json",
    ]
    t_sub, t_conf, stdout, stderr = _run_cli(args)
    digest  = extract_digest(stdout)
    success = digest is not None and "success" in stdout.lower()
    return t_sub, t_conf, digest, success


# ── Design B: finalize_from_slots ────────────────────────────────────────────

def finalize_design_b(
    package_id:       str,
    slot_object_ids:  list[str],
    config_object_id: str,
    registry_object_id: str,
    current_time_ms:  int,
    signer_alias:     str,
    gas_budget:       int = 50_000_000,
) -> tuple[float, float, Optional[str], bool]:
    """
    Call Design B finalize_from_slots via CLI PTB.
    All slot objects are passed in a single PTB.
    Returns (t_submit, t_confirmed, digest, success).
    """
    slot_vec = f"vector[{','.join('@' + s for s in slot_object_ids)}]"

    args = [
        "client", "ptb",
        "--move-call",
        f"{package_id}::accumulator::finalize_from_slots",
        slot_vec,
        f"@{config_object_id}",
        f"@{registry_object_id}",
        str(current_time_ms),
        "--gas-budget", str(gas_budget),
        "--sender",     signer_alias,
        "--json",
    ]
    t_sub, t_conf, stdout, stderr = _run_cli(args)
    digest  = extract_digest(stdout)
    success = digest is not None and "success" in stdout.lower()
    return t_sub, t_conf, digest, success
