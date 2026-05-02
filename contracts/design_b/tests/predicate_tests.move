/// predicate_tests.move — Design B
///
/// Tests for finalize_from_slots covering all ValidBatch(B) conditions.

#[test_only]
module design_b::predicate_tests {
    use iota::test_scenario::{Self as ts};
    use design_b::types::{Self, MedicalDevice, EvidenceSlot, BatchConfig};
    use design_b::accumulator;

    const ADMIN:    address = @0xA;
    const SENSOR_1: address = @0x1;
    const SENSOR_2: address = @0x2;
    const CLOSER:   address = @0xC;

    const WS:  u64 = 1000;
    const WE:  u64 = 2000;
    const DG:  u64 = 200;
    const K:   u64 = 2;
    const DW:  u64 = 500;
    const WID: u64 = 1;

    fun make_config(scenario: &mut ts::Scenario): BatchConfig {
        ts::next_tx(scenario, CLOSER);
        types::new_config(WID, WS, WE, DG, K, DW, ts::ctx(scenario))
    }

    fun make_slot(
        scenario:    &mut ts::Scenario,
        device_addr: address,
        s_type:      u8,
        ts_ms:       u64,
        nonce:       u64,
        wid:         u64,
    ): EvidenceSlot {
        ts::next_tx(scenario, device_addr);
        types::create_slot(
            device_addr, s_type, b"hash",
            ts_ms, nonce, wid, b"sig",
            ts::ctx(scenario),
        )
    }

    fun make_device(
        scenario: &mut ts::Scenario,
        addr:     address,
        s_type:   u8,
    ): MedicalDevice {
        ts::next_tx(scenario, ADMIN);
        types::new_device(addr, s_type, ts::ctx(scenario))
    }

    // ── Baseline: valid batch finalizes correctly ─────────────────────────

    #[test]
    fun test_valid_batch_finalizes() {
        let mut scenario = ts::begin(ADMIN);
        let config = make_config(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);
        let d2 = make_device(&mut scenario, SENSOR_2, 2);
        let s1 = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);
        let s2 = make_slot(&mut scenario, SENSOR_2, 2, 1200, 2, WID);

        let slots  = vector[s1, s2];
        let devices = vector[d1, d2];

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            slots, &config, &devices, WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(d1, ADMIN);
        iota::transfer::public_transfer(d2, ADMIN);
        ts::end(scenario);
    }

    // ── C1: count not met ────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = design_b::types::E_COUNT_NOT_MET)]
    fun test_c1_count_not_met() {
        let mut scenario = ts::begin(ADMIN);
        let config = make_config(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);
        let s1 = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);

        // Only 1 slot but K=2
        let slots   = vector[s1];
        let devices = vector[d1];

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            slots, &config, &devices, WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(d1, ADMIN);
        ts::end(scenario);
    }

    // ── C2: wrong window_id ──────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = design_b::types::E_WRONG_WINDOW)]
    fun test_c2_wrong_window() {
        let mut scenario = ts::begin(ADMIN);
        let config = make_config(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);
        let d2 = make_device(&mut scenario, SENSOR_2, 2);
        let s1 = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);
        // Slot for wrong window
        let s2 = make_slot(&mut scenario, SENSOR_2, 2, 1200, 2, 999);

        let slots   = vector[s1, s2];
        let devices = vector[d1, d2];

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            slots, &config, &devices, WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(d1, ADMIN);
        iota::transfer::public_transfer(d2, ADMIN);
        ts::end(scenario);
    }

    // ── C3: timestamp outside window ─────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = design_b::types::E_TIMESTAMP_OUTSIDE)]
    fun test_c3_late_timestamp() {
        let mut scenario = ts::begin(ADMIN);
        let config = make_config(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);
        let d2 = make_device(&mut scenario, SENSOR_2, 2);
        let s1 = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);
        // Late: WE + DG + 1 = 2201 > 2200
        let s2 = make_slot(&mut scenario, SENSOR_2, 2, WE + DG + 1, 2, WID);

        let slots   = vector[s1, s2];
        let devices = vector[d1, d2];

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            slots, &config, &devices, WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(d1, ADMIN);
        iota::transfer::public_transfer(d2, ADMIN);
        ts::end(scenario);
    }

    // ── C4: spread exceeded ───────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = design_b::types::E_SPREAD_EXCEEDED)]
    fun test_c4_spread_exceeded() {
        let mut scenario = ts::begin(ADMIN);
        let config = make_config(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);
        let d2 = make_device(&mut scenario, SENSOR_2, 2);
        // Spread = 1600 - 1000 = 600 > DW=500
        let s1 = make_slot(&mut scenario, SENSOR_1, 1, WS, 1, WID);
        let s2 = make_slot(&mut scenario, SENSOR_2, 2, WS + DW + 100, 2, WID);

        let slots   = vector[s1, s2];
        let devices = vector[d1, d2];

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            slots, &config, &devices, WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(d1, ADMIN);
        iota::transfer::public_transfer(d2, ADMIN);
        ts::end(scenario);
    }

    // ── C6: nonce reuse ───────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = design_b::types::E_NONCE_REUSE)]
    fun test_c6_nonce_reuse() {
        let mut scenario = ts::begin(ADMIN);
        let config = make_config(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);
        // Two slots from SENSOR_1, different sensor_type, SAME nonce
        let s1 = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);
        let s2 = make_slot(&mut scenario, SENSOR_1, 2, 1200, 1, WID); // nonce=1 reused

        let slots   = vector[s1, s2];
        let devices = vector[d1];

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            slots, &config, &devices, WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(d1, ADMIN);
        ts::end(scenario);
    }

    // ── C7: conflict (same device + sensor_type) ──────────────────────────

    #[test]
    #[expected_failure(abort_code = design_b::types::E_CONFLICT)]
    fun test_c7_conflict() {
        let mut scenario = ts::begin(ADMIN);
        let config = make_config(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);
        // Two slots: same device, same sensor_type, different nonce
        let s1 = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);
        let s2 = make_slot(&mut scenario, SENSOR_1, 1, 1200, 2, WID);

        let slots   = vector[s1, s2];
        let devices = vector[d1];

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            slots, &config, &devices, WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(d1, ADMIN);
        ts::end(scenario);
    }
}
