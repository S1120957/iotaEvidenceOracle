/// accumulator.move — Design A (Shared Accumulator)
///
/// Implements submit_reading and finalize.
/// Every sensor write mutates the shared EvidenceBatch directly.
/// Enforces the Oracle-Readiness Predicate ValidBatch(B) atomically
/// at finalization.

module design_a::accumulator {
    use std::hash;
    use iota::bcs;
    use design_a::types::{
        Self, MedicalDevice, EvidenceSlot, EvidenceBatch,
    };

    // ── submit_reading ───────────────────────────────────────────────────────
    //
    // Per-reading predicate checks enforced here (conditions 2,3,5,6,7):
    //   (2) slot.window_id == batch.window_id
    //   (3) slot.timestamp in [ws, we + delta_g]
    //   (5) device is registered and active
    //   (6) nonce not reused by same device in this batch
    //   (7) no prior reading from same device+sensor_type in this batch
    //
    // Condition (1), (4), and (8) are checked at finalization, not here,
    // because they depend on the full set of accepted readings.

    public entry fun submit_reading(
        batch:  &mut EvidenceBatch,
        device: &MedicalDevice,
        slot:   EvidenceSlot,
    ) {
        // Batch must still be open
        assert!(
            types::batch_status(batch) == types::status_open(),
            types::err_batch_not_open()
        );

        // (5) Device active
        assert!(types::device_active(device), types::err_device_inactive());

        // (2) Slot belongs to this window
        assert!(
            types::slot_window_id(&slot) == types::batch_window_id(batch),
            types::err_wrong_window()
        );

        // (3) Timestamp within [ws, we + delta_g]
        let ts      = types::slot_timestamp(&slot);
        let ws      = types::batch_window_start(batch);
        let we      = types::batch_window_end(batch);
        let delta_g = types::batch_grace(batch);
        assert!(
            ts >= ws && ts <= we + delta_g,
            types::err_timestamp_outside()
        );

        // (6) Nonce uniqueness for this device
        let device_addr = types::slot_device_id(&slot);
        let nonce       = types::slot_nonce(&slot);
        let existing_devices = types::accepted_device_ids(batch);
        let existing_nonces  = types::accepted_nonces(batch);
        let mut i = 0u64;
        let len = vector::length(existing_devices);
        while (i < len) {
            if (*vector::borrow(existing_devices, i) == device_addr) {
                assert!(
                    *vector::borrow(existing_nonces, i) != nonce,
                    types::err_nonce_reuse()
                );
            };
            i = i + 1;
        };

        // (7) No prior reading from same device + sensor_type
        let sensor_type      = types::slot_sensor_type(&slot);
        let existing_sensors = types::accepted_sensor_types(batch);
        let mut j = 0u64;
        while (j < len) {
            if (*vector::borrow(existing_devices, j) == device_addr) {
                assert!(
                    *vector::borrow(existing_sensors, j) != sensor_type,
                    types::err_conflict()
                );
            };
            j = j + 1;
        };

        // All per-reading checks passed — record the slot
        let slot_id = types::slot_id(&slot);
        types::push_accepted(batch, slot_id, device_addr, sensor_type, ts, nonce);

        // Consume the slot object (transfer to zero address or drop)
        // In IOTA Move, objects with key+store must be transferred or deleted.
        // We transfer to @0x0 (burn address) to represent consumption.
        iota::transfer::public_transfer(slot, @0x0);
    }

    // ── finalize ─────────────────────────────────────────────────────────────
    //
    // Batch-level predicate checks (conditions 1, 4, 8):
    //   (1) |B| >= k
    //   (4) max_ts - min_ts <= Delta W
    //   (8) status transitions to finalized, expired, or invalid
    //
    // Condition (8) is enforced by making finalized the only terminal state
    // reachable when (1) and (4) both hold.
    //
    // current_time_ms must be passed by the caller (read from iota::clock::Clock
    // in a production call) to determine expired vs invalid status.

    public entry fun finalize(
        batch:           &mut EvidenceBatch,
        current_time_ms: u64,
    ) {
        assert!(
            types::batch_status(batch) == types::status_open(),
            types::err_batch_not_open()
        );

        let count = types::batch_count(batch);
        let k     = types::batch_min_count(batch);
        let we    = types::batch_window_end(batch);
        let dg    = types::batch_grace(batch);

        // If called before grace interval ends, mark invalid (premature call)
        if (current_time_ms < we + dg) {
            types::set_status(batch, types::status_invalid());
            return
        };

        // (1) Minimum count
        if (count < k) {
            types::set_status(batch, types::status_expired());
            return
        };

        // (4) Timestamp spread
        let timestamps   = types::accepted_timestamps(batch);
        let mut min_ts   = *vector::borrow(timestamps, 0);
        let mut max_ts   = *vector::borrow(timestamps, 0);
        let mut idx      = 1u64;
        while (idx < count) {
            let t = *vector::borrow(timestamps, idx);
            if (t < min_ts) { min_ts = t };
            if (t > max_ts) { max_ts = t };
            idx = idx + 1;
        };
        if (max_ts - min_ts > types::batch_max_spread(batch)) {
            types::set_status(batch, types::status_invalid());
            return
        };

        // All conditions hold — compute batch_hash and finalize
        // batch_hash = SHA3-256( window_id || accepted_slot_ids )
        let mut preimage = bcs::to_bytes(&types::batch_window_id(batch));
        let ids = types::batch_accepted_ids(batch);
        let mut h_idx = 0u64;
        let id_count = vector::length(ids);
        while (h_idx < id_count) {
            let id_bytes = bcs::to_bytes(vector::borrow(ids, h_idx));
            vector::append(&mut preimage, id_bytes);
            h_idx = h_idx + 1;
        };
        let h = hash::sha3_256(preimage);
        types::set_batch_hash(batch, h);
        types::set_status(batch, types::status_finalized());
    }
}
