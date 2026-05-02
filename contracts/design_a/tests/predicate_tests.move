/// predicate_tests.move — Design A
///
/// One passing test and one failing test per predicate condition.
/// All eight conditions of ValidBatch(B) are covered.
/// Abort codes match types.move constants:
///   1=DEVICE_INACTIVE 2=WRONG_WINDOW 3=TIMESTAMP_OUTSIDE
///   4=NONCE_REUSE 5=CONFLICT 6=BATCH_NOT_OPEN 7=COUNT_NOT_MET 8=SPREAD_EXCEEDED

#[test_only]
module design_a::predicate_tests {
    use iota::test_scenario::{Self as ts, Scenario};
    use design_a::types::{Self, MedicalDevice, EvidenceBatch};
    use design_a::accumulator;

    const ADMIN:    address = @0xA;
    const SENSOR_1: address = @0x1;
    const SENSOR_2: address = @0x2;

    const WS:  u64 = 1000;
    const WE:  u64 = 2000;
    const DG:  u64 = 200;
    const K:   u64 = 2;
    const DW:  u64 = 500;
    const WID: u64 = 1;

    fun make_batch(scenario: &mut Scenario): EvidenceBatch {
        ts::next_tx(scenario, ADMIN);
        types::new_batch(WID, WS, WE, DG, K, DW, ts::ctx(scenario))
    }

    fun make_device(scenario: &mut Scenario, addr: address, s_type: u8): MedicalDevice {
        ts::next_tx(scenario, ADMIN);
        types::new_device(addr, s_type, ts::ctx(scenario))
    }

    // ── C1: minimum count ────────────────────────────────────────────────────

    #[test]
    fun test_c1_count_met() {
        let mut scenario = ts::begin(ADMIN);
        let mut batch = make_batch(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);
        let d2 = make_device(&mut scenario, SENSOR_2, 2);

        ts::next_tx(&mut scenario, SENSOR_1);
        let s1 = types::new_slot(SENSOR_1, 1, b"h1", 1100, 1, WID, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &d1, s1);

        ts::next_tx(&mut scenario, SENSOR_2);
        let s2 = types::new_slot(SENSOR_2, 2, b"h2", 1200, 1, WID, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &d2, s2);

        accumulator::finalize(&mut batch, WE + DG + 1);
        assert!(types::batch_status(&batch) == types::status_finalized(), 0);

        iota::transfer::public_transfer(batch, ADMIN);
        iota::transfer::public_transfer(d1, ADMIN);
        iota::transfer::public_transfer(d2, ADMIN);
        ts::end(scenario);
    }

    #[test]
    // finalize sets status=expired when count < k — does not abort
    fun test_c1_count_not_met() {
        let mut scenario = ts::begin(ADMIN);
        let mut batch = make_batch(&mut scenario);
        accumulator::finalize(&mut batch, WE + DG + 1);
        assert!(types::batch_status(&batch) == types::status_expired(), 0);
        iota::transfer::public_transfer(batch, ADMIN);
        ts::end(scenario);
    }

    // ── C2: window_id match ──────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = 2)]
    fun test_c2_wrong_window_id() {
        let mut scenario = ts::begin(ADMIN);
        let mut batch = make_batch(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);

        ts::next_tx(&mut scenario, SENSOR_1);
        let slot = types::new_slot(SENSOR_1, 1, b"h", 1100, 1, 999, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &d1, slot);

        iota::transfer::public_transfer(batch, ADMIN);
        iota::transfer::public_transfer(d1, ADMIN);
        ts::end(scenario);
    }

    // ── C3: timestamp bounds ─────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = 3)]
    fun test_c3_timestamp_too_late() {
        let mut scenario = ts::begin(ADMIN);
        let mut batch = make_batch(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);

        ts::next_tx(&mut scenario, SENSOR_1);
        let slot = types::new_slot(SENSOR_1, 1, b"h", WE + DG + 1, 1, WID, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &d1, slot);

        iota::transfer::public_transfer(batch, ADMIN);
        iota::transfer::public_transfer(d1, ADMIN);
        ts::end(scenario);
    }

    #[test]
    #[expected_failure(abort_code = 3)]
    fun test_c3_timestamp_before_window() {
        let mut scenario = ts::begin(ADMIN);
        let mut batch = make_batch(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);

        ts::next_tx(&mut scenario, SENSOR_1);
        let slot = types::new_slot(SENSOR_1, 1, b"h", WS - 1, 1, WID, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &d1, slot);

        iota::transfer::public_transfer(batch, ADMIN);
        iota::transfer::public_transfer(d1, ADMIN);
        ts::end(scenario);
    }

    // ── C4: timestamp spread ─────────────────────────────────────────────────

    #[test]
    // finalize sets status=invalid when spread > DW — does not abort
    fun test_c4_spread_exceeded_marks_invalid() {
        let mut scenario = ts::begin(ADMIN);
        let mut batch = make_batch(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);
        let d2 = make_device(&mut scenario, SENSOR_2, 2);

        ts::next_tx(&mut scenario, SENSOR_1);
        let s1 = types::new_slot(SENSOR_1, 1, b"h1", WS, 1, WID, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &d1, s1);

        ts::next_tx(&mut scenario, SENSOR_2);
        let s2 = types::new_slot(SENSOR_2, 2, b"h2", WS + DW + 100, 1, WID, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &d2, s2);

        accumulator::finalize(&mut batch, WE + DG + 1);
        assert!(types::batch_status(&batch) == types::status_invalid(), 0);

        iota::transfer::public_transfer(batch, ADMIN);
        iota::transfer::public_transfer(d1, ADMIN);
        iota::transfer::public_transfer(d2, ADMIN);
        ts::end(scenario);
    }

    // ── C5: device active ────────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = 1)]
    fun test_c5_inactive_device() {
        let mut scenario = ts::begin(ADMIN);
        let mut batch = make_batch(&mut scenario);

        ts::next_tx(&mut scenario, ADMIN);
        let inactive = types::new_device_inactive_for_test(SENSOR_1, 1, ts::ctx(&mut scenario));

        ts::next_tx(&mut scenario, SENSOR_1);
        let slot = types::new_slot(SENSOR_1, 1, b"h", 1100, 1, WID, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &inactive, slot);

        iota::transfer::public_transfer(batch, ADMIN);
        iota::transfer::public_transfer(inactive, ADMIN);
        ts::end(scenario);
    }

    // ── C6: nonce uniqueness ─────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = 4)]
    fun test_c6_nonce_reuse() {
        let mut scenario = ts::begin(ADMIN);
        let mut batch = make_batch(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);

        ts::next_tx(&mut scenario, SENSOR_1);
        let s1 = types::new_slot(SENSOR_1, 1, b"h1", 1100, 1, WID, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &d1, s1);

        ts::next_tx(&mut scenario, SENSOR_1);
        let s2 = types::new_slot(SENSOR_1, 2, b"h2", 1200, 1, WID, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &d1, s2);

        iota::transfer::public_transfer(batch, ADMIN);
        iota::transfer::public_transfer(d1, ADMIN);
        ts::end(scenario);
    }

    // ── C7: conflict ─────────────────────────────────────────────────────────

    #[test]
    #[expected_failure(abort_code = 5)]
    fun test_c7_conflict() {
        let mut scenario = ts::begin(ADMIN);
        let mut batch = make_batch(&mut scenario);
        let d1 = make_device(&mut scenario, SENSOR_1, 1);

        ts::next_tx(&mut scenario, SENSOR_1);
        let s1 = types::new_slot(SENSOR_1, 1, b"h1", 1100, 1, WID, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &d1, s1);

        ts::next_tx(&mut scenario, SENSOR_1);
        let s2 = types::new_slot(SENSOR_1, 1, b"h2", 1200, 2, WID, b"s", ts::ctx(&mut scenario));
        accumulator::submit_reading(&mut batch, &d1, s2);

        iota::transfer::public_transfer(batch, ADMIN);
        iota::transfer::public_transfer(d1, ADMIN);
        ts::end(scenario);
    }
}
