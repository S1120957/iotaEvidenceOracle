/// predicate_tests.move — Design B
///
/// Tests for finalize_from_slots covering all ValidBatch(B) conditions.
/// Uses DeviceRegistry wrapper to correctly consume vector<MedicalDevice>.
/// Abort codes: 2=WRONG_WINDOW 3=TIMESTAMP_OUTSIDE 4=NONCE_REUSE
///              5=CONFLICT 7=COUNT_NOT_MET 8=SPREAD_EXCEEDED

#[test_only]
module design_b::predicate_tests {
    use iota::test_scenario::{Self as ts};
    use design_b::types::{Self, MedicalDevice, EvidenceSlot, BatchConfig, DeviceRegistry};
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
        scenario: &mut ts::Scenario, addr: address, s_type: u8,
        ts_ms: u64, nonce: u64, wid: u64,
    ): EvidenceSlot {
        ts::next_tx(scenario, addr);
        types::create_slot(addr, s_type, b"hash", ts_ms, nonce, wid, b"sig", ts::ctx(scenario))
    }

    fun make_device(scenario: &mut ts::Scenario, addr: address, s_type: u8): MedicalDevice {
        ts::next_tx(scenario, ADMIN);
        types::new_device(addr, s_type, ts::ctx(scenario))
    }

    fun make_registry(scenario: &mut ts::Scenario, devices: vector<MedicalDevice>): DeviceRegistry {
        ts::next_tx(scenario, ADMIN);
        types::new_registry(devices, ts::ctx(scenario))
    }

    // ── Baseline ─────────────────────────────────────────────────────────────

    #[test]
    fun test_valid_batch_finalizes() {
        let mut scenario = ts::begin(ADMIN);
        let config   = make_config(&mut scenario);
        let d1       = make_device(&mut scenario, SENSOR_1, 1);
        let d2       = make_device(&mut scenario, SENSOR_2, 2);
        let s1       = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);
        let s2       = make_slot(&mut scenario, SENSOR_2, 2, 1200, 2, WID);
        let registry = make_registry(&mut scenario, vector[d1, d2]);

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            vector[s1, s2], &config, types::registry_devices(&registry),
            WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(registry, ADMIN);
        ts::end(scenario);
    }

    // ── C1: count not met ────────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = 7)]
    fun test_c1_count_not_met() {
        let mut scenario = ts::begin(ADMIN);
        let config   = make_config(&mut scenario);
        let d1       = make_device(&mut scenario, SENSOR_1, 1);
        let s1       = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);
        let registry = make_registry(&mut scenario, vector[d1]);

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            vector[s1], &config, types::registry_devices(&registry),
            WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(registry, ADMIN);
        ts::end(scenario);
    }

    // ── C2: wrong window_id ──────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = 2)]
    fun test_c2_wrong_window() {
        let mut scenario = ts::begin(ADMIN);
        let config   = make_config(&mut scenario);
        let d1       = make_device(&mut scenario, SENSOR_1, 1);
        let d2       = make_device(&mut scenario, SENSOR_2, 2);
        let s1       = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);
        let s2       = make_slot(&mut scenario, SENSOR_2, 2, 1200, 2, 999);
        let registry = make_registry(&mut scenario, vector[d1, d2]);

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            vector[s1, s2], &config, types::registry_devices(&registry),
            WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(registry, ADMIN);
        ts::end(scenario);
    }

    // ── C3: timestamp outside window ─────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = 3)]
    fun test_c3_late_timestamp() {
        let mut scenario = ts::begin(ADMIN);
        let config   = make_config(&mut scenario);
        let d1       = make_device(&mut scenario, SENSOR_1, 1);
        let d2       = make_device(&mut scenario, SENSOR_2, 2);
        let s1       = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);
        let s2       = make_slot(&mut scenario, SENSOR_2, 2, WE + DG + 1, 2, WID);
        let registry = make_registry(&mut scenario, vector[d1, d2]);

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            vector[s1, s2], &config, types::registry_devices(&registry),
            WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(registry, ADMIN);
        ts::end(scenario);
    }

    // ── C4: spread exceeded ───────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = 8)]
    fun test_c4_spread_exceeded() {
        let mut scenario = ts::begin(ADMIN);
        let config   = make_config(&mut scenario);
        let d1       = make_device(&mut scenario, SENSOR_1, 1);
        let d2       = make_device(&mut scenario, SENSOR_2, 2);
        let s1       = make_slot(&mut scenario, SENSOR_1, 1, WS, 1, WID);
        let s2       = make_slot(&mut scenario, SENSOR_2, 2, WS + DW + 100, 2, WID);
        let registry = make_registry(&mut scenario, vector[d1, d2]);

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            vector[s1, s2], &config, types::registry_devices(&registry),
            WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(registry, ADMIN);
        ts::end(scenario);
    }

    // ── C6: nonce reuse ───────────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = 4)]
    fun test_c6_nonce_reuse() {
        let mut scenario = ts::begin(ADMIN);
        let config   = make_config(&mut scenario);
        let d1       = make_device(&mut scenario, SENSOR_1, 1);
        let s1       = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);
        let s2       = make_slot(&mut scenario, SENSOR_1, 2, 1200, 1, WID);
        let registry = make_registry(&mut scenario, vector[d1]);

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            vector[s1, s2], &config, types::registry_devices(&registry),
            WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(registry, ADMIN);
        ts::end(scenario);
    }

    // ── C7: conflict ─────────────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = 5)]
    fun test_c7_conflict() {
        let mut scenario = ts::begin(ADMIN);
        let config   = make_config(&mut scenario);
        let d1       = make_device(&mut scenario, SENSOR_1, 1);
        let s1       = make_slot(&mut scenario, SENSOR_1, 1, 1100, 1, WID);
        let s2       = make_slot(&mut scenario, SENSOR_1, 1, 1200, 2, WID);
        let registry = make_registry(&mut scenario, vector[d1]);

        ts::next_tx(&mut scenario, CLOSER);
        accumulator::finalize_from_slots(
            vector[s1, s2], &config, types::registry_devices(&registry),
            WE + DG + 1, ts::ctx(&mut scenario),
        );

        iota::transfer::public_transfer(config, CLOSER);
        iota::transfer::public_transfer(registry, ADMIN);
        ts::end(scenario);
    }
}
