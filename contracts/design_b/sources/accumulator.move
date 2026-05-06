/// accumulator.move — Design B (Owned-Slot Staging)
///
/// create_slot: sensor write path — creates an owned EvidenceSlot.
/// No shared EvidenceBatch object is touched during ingestion.
///
/// finalize_from_slots: internal validation logic (public fun).
/// finalize:            PTB-callable entry point (public entry fun).

module design_b::accumulator {
    use std::hash;
    use iota::bcs;
    use iota::object::ID;
    use iota::transfer;
    use iota::tx_context::{Self, TxContext};

    use design_b::types::{
        Self,
        EvidenceSlot,
        BatchConfig,
    };

    // ── Sensor write path ────────────────────────────────────────────────────

    public entry fun create_slot(
        device_id: address,
        sensor_type: u8,
        reading_hash: vector<u8>,
        timestamp: u64,
        nonce: u64,
        window_id: u64,
        signature_hash: vector<u8>,
        ctx: &mut TxContext,
    ) {
        let slot = types::create_slot(
            device_id,
            sensor_type,
            reading_hash,
            timestamp,
            nonce,
            window_id,
            signature_hash,
            ctx,
        );

        transfer::public_transfer(slot, tx_context::sender(ctx));
    }

    // ── Window-close path ────────────────────────────────────────────────────

    /// Public entry point for PTB invocation.
    /// The CLI passes ctx implicitly for entry funs — this thin wrapper
    /// delegates to the internal public fun so both paths are available.
    public entry fun finalize(
        slots: vector<EvidenceSlot>,
        config: &BatchConfig,
        current_time_ms: u64,
        ctx: &mut TxContext,
    ) {
        finalize_from_slots(slots, config, current_time_ms, ctx)
    }

    /// Core validation and batch creation logic.
    /// Callable from Move and from the entry wrapper above.
    public fun finalize_from_slots(
        mut slots: vector<EvidenceSlot>,
        config: &BatchConfig,
        current_time_ms: u64,
        ctx: &mut TxContext,
    ) {
        let ws        = types::config_window_start(config);
        let we        = types::config_window_end(config);
        let dg        = types::config_grace(config);
        let min_count = types::config_min_count(config);
        let max_spread = types::config_max_spread(config);
        let window_id = types::config_window_id(config);

        assert!(
            current_time_ms >= we + dg,
            types::err_premature_finalize()
        );

        let n = vector::length(&slots);

        assert!(
            (n as u64) >= min_count,
            types::err_count_not_met()
        );

        let mut accepted_ids:        vector<ID>      = vector::empty();
        let mut accepted_devices:    vector<address>  = vector::empty();
        let mut accepted_types:      vector<u8>       = vector::empty();
        let mut accepted_timestamps: vector<u64>      = vector::empty();
        let mut accepted_nonces:     vector<u64>      = vector::empty();

        let mut i = 0u64;

        while (i < (n as u64)) {
            let slot = vector::borrow(&slots, i);

            assert!(
                types::slot_window_id(slot) == window_id,
                types::err_wrong_window()
            );

            let timestamp   = types::slot_timestamp(slot);

            assert!(
                timestamp >= ws && timestamp <= we + dg,
                types::err_timestamp_outside()
            );

            let device_id   = types::slot_device_id(slot);
            let sensor_type = types::slot_sensor_type(slot);
            let nonce       = types::slot_nonce(slot);
            let slot_id     = types::slot_id(slot);

            let seen  = vector::length(&accepted_devices);
            let mut j = 0u64;

            while (j < seen) {
                if (*vector::borrow(&accepted_devices, j) == device_id) {
                    assert!(
                        *vector::borrow(&accepted_nonces, j) != nonce,
                        types::err_nonce_reuse()
                    );
                    assert!(
                        *vector::borrow(&accepted_types, j) != sensor_type,
                        types::err_conflict()
                    );
                };
                j = j + 1;
            };

            vector::push_back(&mut accepted_ids,        slot_id);
            vector::push_back(&mut accepted_devices,    device_id);
            vector::push_back(&mut accepted_types,      sensor_type);
            vector::push_back(&mut accepted_timestamps, timestamp);
            vector::push_back(&mut accepted_nonces,     nonce);

            i = i + 1;
        };

        let mut min_ts   = *vector::borrow(&accepted_timestamps, 0);
        let mut max_ts   = *vector::borrow(&accepted_timestamps, 0);
        let mut t_idx    = 1u64;
        let     ts_count = vector::length(&accepted_timestamps);

        while (t_idx < ts_count) {
            let ts = *vector::borrow(&accepted_timestamps, t_idx);
            if (ts < min_ts) { min_ts = ts };
            if (ts > max_ts) { max_ts = ts };
            t_idx = t_idx + 1;
        };

        assert!(
            max_ts - min_ts <= max_spread,
            types::err_spread_exceeded()
        );

        let mut preimage = bcs::to_bytes(&window_id);
        let mut h_idx    = 0u64;
        let     id_count = vector::length(&accepted_ids);

        while (h_idx < id_count) {
            let id_bytes = bcs::to_bytes(vector::borrow(&accepted_ids, h_idx));
            vector::append(&mut preimage, id_bytes);
            h_idx = h_idx + 1;
        };

        let batch_hash = hash::sha3_256(preimage);

        let mut s_idx = 0u64;
        while (s_idx < n) {
            let slot = vector::pop_back(&mut slots);
            transfer::public_transfer(slot, @0x0);
            s_idx = s_idx + 1;
        };
        vector::destroy_empty(slots);

        let batch = types::new_batch_internal(
            window_id,
            ws,
            we,
            dg,
            min_count,
            max_spread,
            accepted_ids,
            batch_hash,
            ctx,
        );

        transfer::public_share_object(batch);
    }
}
