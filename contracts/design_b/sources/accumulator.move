/// accumulator.move — Design B (Owned-Slot Staging)
///
/// create_slot: sensor write path — creates an OWNED EvidenceSlot.
///   No shared object is touched. Fast path, no consensus.
///
/// finalize_from_slots: window-close path — validates a vector of owned
///   slots against ValidBatch(B), then creates a shared EvidenceBatch.
///   All consensus cost is concentrated here, once per window.

module design_b::accumulator {
    use std::hash;
    use iota::bcs;
    use iota::object::ID;
    use design_b::types::{
        Self, MedicalDevice, EvidenceSlot, BatchConfig, EvidenceBatch,
    };

    // ── create_slot ──────────────────────────────────────────────────────────
    //
    // The only operation a sensor performs during ingestion.
    // Returns an owned EvidenceSlot. No shared state mutated.
    // Per-reading validity is NOT checked here; it is checked at finalization.
    // This is by design: checking here would require reading the device
    // registry (a shared object), which would put the write on the
    // consensus path and defeat the purpose of Design B.

    public entry fun create_slot(
        device_id:      address,
        sensor_type:    u8,
        reading_hash:   vector<u8>,
        timestamp:      u64,
        nonce:          u64,
        window_id:      u64,
        signature_hash: vector<u8>,
        ctx:            &mut iota::tx_context::TxContext,
    ) {
        let slot = types::create_slot(
            device_id, sensor_type, reading_hash,
            timestamp, nonce, window_id, signature_hash, ctx,
        );
        // Transfer the owned slot to the sender (sensor/gateway address)
        iota::transfer::public_transfer(slot, iota::tx_context::sender(ctx));
    }

    // ── finalize_from_slots ──────────────────────────────────────────────────
    //
    // Window-closer collects owned EvidenceSlots via PTB and passes them here.
    // Full ValidBatch(B) predicate is enforced atomically.
    // On success:  creates a shared EvidenceBatch with status=finalized.
    // On failure:  aborts (slot objects are returned to caller by the VM).
    //
    // The window-closer is responsible for filtering slots by window_id
    // before calling this function. Slots for the wrong window abort at (2).

    public entry fun finalize_from_slots(
        mut slots:       vector<EvidenceSlot>,
        config:          &BatchConfig,
        devices:         &vector<MedicalDevice>,
        current_time_ms: u64,
        ctx:             &mut iota::tx_context::TxContext,
    ) {
        let ws      = types::config_window_start(config);
        let we      = types::config_window_end(config);
        let dg      = types::config_grace(config);
        let k       = types::config_min_count(config);
        let dw      = types::config_max_spread(config);
        let wid     = types::config_window_id(config);

        // Premature call guard
        assert!(current_time_ms >= we + dg, types::err_premature_finalize());

        let n = vector::length(&slots);

        // (1) Minimum count
        assert!((n as u64) >= k, types::err_count_not_met());

        // Per-slot checks and parallel array construction
        let mut accepted_ids:      vector<ID>      = vector::empty();
        let mut accepted_devices:  vector<address>  = vector::empty();
        let mut accepted_types:    vector<u8>        = vector::empty();
        let mut accepted_ts:       vector<u64>       = vector::empty();
        let mut accepted_nonces:   vector<u64>       = vector::empty();

        let mut i = 0u64;
        while (i < (n as u64)) {
            let slot = vector::borrow(&slots, i);

            // (2) Window ID
            assert!(
                types::slot_window_id(slot) == wid,
                types::err_wrong_window()
            );

            // (3) Timestamp bounds
            let ts = types::slot_timestamp(slot);
            assert!(
                ts >= ws && ts <= we + dg,
                types::err_timestamp_outside()
            );

            // (5) Device active — look up in devices vector by device_id
            let dev_addr = types::slot_device_id(slot);
            let mut dev_found = false;
            let mut d = 0u64;
            let dev_count = vector::length(devices);
            while (d < dev_count) {
                let dev = vector::borrow(devices, d);
                if (types::device_id(dev) == dev_addr) {
                    assert!(types::device_active(dev), types::err_device_inactive());
                    dev_found = true;
                    break
                };
                d = d + 1;
            };
            assert!(dev_found, types::err_device_inactive());

            let sensor_type = types::slot_sensor_type(slot);
            let nonce       = types::slot_nonce(slot);
            let slot_id     = types::slot_id(slot);

            // (6) Nonce uniqueness for this device
            let mut j = 0u64;
            let seen = vector::length(&accepted_devices);
            while (j < seen) {
                if (*vector::borrow(&accepted_devices, j) == dev_addr) {
                    assert!(
                        *vector::borrow(&accepted_nonces, j) != nonce,
                        types::err_nonce_reuse()
                    );
                };
                j = j + 1;
            };

            // (7) No conflict: same device + sensor_type
            let mut k_idx = 0u64;
            while (k_idx < seen) {
                if (*vector::borrow(&accepted_devices, k_idx) == dev_addr) {
                    assert!(
                        *vector::borrow(&accepted_types, k_idx) != sensor_type,
                        types::err_conflict()
                    );
                };
                k_idx = k_idx + 1;
            };

            vector::push_back(&mut accepted_ids,     slot_id);
            vector::push_back(&mut accepted_devices, dev_addr);
            vector::push_back(&mut accepted_types,   sensor_type);
            vector::push_back(&mut accepted_ts,      ts);
            vector::push_back(&mut accepted_nonces,  nonce);

            i = i + 1;
        };

        // (4) Timestamp spread
        let mut min_ts = *vector::borrow(&accepted_ts, 0);
        let mut max_ts = *vector::borrow(&accepted_ts, 0);
        let mut t_idx = 1u64;
        let ts_count = vector::length(&accepted_ts);
        while (t_idx < ts_count) {
            let t = *vector::borrow(&accepted_ts, t_idx);
            if (t < min_ts) { min_ts = t };
            if (t > max_ts) { max_ts = t };
            t_idx = t_idx + 1;
        };
        assert!(max_ts - min_ts <= dw, types::err_spread_exceeded());

        // Compute batch_hash = SHA3-256(window_id || slot_id_0 || ... || slot_id_n)
        let mut preimage = bcs::to_bytes(&wid);
        let mut h_idx = 0u64;
        let id_count = vector::length(&accepted_ids);
        while (h_idx < id_count) {
            let id_bytes = bcs::to_bytes(vector::borrow(&accepted_ids, h_idx));
            vector::append(&mut preimage, id_bytes);
            h_idx = h_idx + 1;
        };
        let batch_hash = hash::sha3_256(preimage);

        // Mark all slots consumed and transfer to zero address
        let mut s_idx = 0u64;
        while (s_idx < (n as u64)) {
            let slot = vector::pop_back(&mut slots);
            // Note: consumed flag is set but object is burned to @0x0
            iota::transfer::public_transfer(slot, @0x0);
            s_idx = s_idx + 1;
        };
        vector::destroy_empty(slots);

        // Create and share the finalized EvidenceBatch
        let batch = types::new_batch_internal(
            wid, ws, we, dg,
            types::config_min_count(config),
            dw,
            accepted_ids,
            batch_hash,
            ctx,
        );
        iota::transfer::public_share_object(batch);
    }
}
