/// types.move — Design A (Shared Accumulator)
///
/// Defines MedicalDevice, EvidenceSlot, and EvidenceBatch exactly as
/// specified in the paper (Section IV, Listing 1).
/// Raw physiological values are NOT stored on-chain.
/// The chain stores reading commitments and metadata required to evaluate
/// the Oracle-Readiness Predicate ValidBatch(B).

module design_a::types {
    use iota::object::{Self, UID, ID};
    use iota::tx_context::TxContext;

    // ── Status constants ────────────────────────────────────────────────────
    const STATUS_OPEN:      u8 = 0;
    const STATUS_FINALIZED: u8 = 1;
    const STATUS_EXPIRED:   u8 = 2;
    const STATUS_INVALID:   u8 = 3;

    // ── Error codes ─────────────────────────────────────────────────────────
    // One constant per predicate condition so test failures are precise.
    const E_DEVICE_INACTIVE:    u64 = 1; // condition (5)
    const E_WRONG_WINDOW:       u64 = 2; // condition (2)
    const E_TIMESTAMP_OUTSIDE:  u64 = 3; // condition (3)
    const E_NONCE_REUSE:        u64 = 4; // condition (6)
    const E_CONFLICT:           u64 = 5; // condition (7)
    const E_BATCH_NOT_OPEN:     u64 = 6;
    const E_COUNT_NOT_MET:      u64 = 7; // condition (1)
    const E_SPREAD_EXCEEDED:    u64 = 8; // condition (4)

    // ── Core object types ───────────────────────────────────────────────────

    /// Represents a registered Medical IoT sensor or gateway.
    /// Owned by the device operator; passed as a reference into submit_reading
    /// to prove the device is known and active at transaction time.
    public struct MedicalDevice has key, store {
        id:          UID,
        device_id:   address,
        sensor_type: u8,
        active:      bool,
    }

    /// Represents one sensor reading submitted for a window.
    /// In Design A this is consumed directly by submit_reading and its
    /// metadata is recorded in the shared EvidenceBatch.
    public struct EvidenceSlot has key, store {
        id:             UID,
        device_id:      address,
        sensor_type:    u8,
        reading_hash:   vector<u8>,  // commitment to raw payload
        timestamp:      u64,         // milliseconds since Unix epoch
        nonce:          u64,         // device-local monotonic counter
        window_id:      u64,         // links this slot to its window
        signature_hash: vector<u8>,  // commitment to device signature
        consumed:       bool,
    }

    /// Represents a time-windowed evidence unit.
    /// Shared object: all sensor writes in Design A mutate this object.
    /// grace_interval stores delta_g; finalization reads it from here
    /// so all validators apply the same bound.
    public struct EvidenceBatch has key, store {
        id:                   UID,
        window_id:            u64,
        window_start:         u64,   // ws  (ms)
        window_end:           u64,   // we  (ms)
        grace_interval:       u64,   // delta_g (ms)
        required_min_count:   u64,   // k
        max_timestamp_spread: u64,   // Delta W (ms)
        accepted_slot_ids:    vector<ID>,
        accepted_device_ids:  vector<address>,  // parallel to accepted_slot_ids
        accepted_sensor_types: vector<u8>,      // parallel to accepted_slot_ids
        accepted_timestamps:  vector<u64>,      // parallel to accepted_slot_ids
        accepted_nonces:      vector<u64>,      // parallel to accepted_slot_ids
        batch_hash:           vector<u8>,
        status:               u8,
    }

    // ── Constructor functions ────────────────────────────────────────────────

    public fun new_device(
        device_id:   address,
        sensor_type: u8,
        ctx:         &mut TxContext,
    ): MedicalDevice {
        MedicalDevice {
            id: object::new(ctx),
            device_id,
            sensor_type,
            active: true,
        }
    }

    public fun new_slot(
        device_id:      address,
        sensor_type:    u8,
        reading_hash:   vector<u8>,
        timestamp:      u64,
        nonce:          u64,
        window_id:      u64,
        signature_hash: vector<u8>,
        ctx:            &mut TxContext,
    ): EvidenceSlot {
        EvidenceSlot {
            id: object::new(ctx),
            device_id,
            sensor_type,
            reading_hash,
            timestamp,
            nonce,
            window_id,
            signature_hash,
            consumed: false,
        }
    }

    public fun new_batch(
        window_id:            u64,
        window_start:         u64,
        window_end:           u64,
        grace_interval:       u64,
        required_min_count:   u64,
        max_timestamp_spread: u64,
        ctx:                  &mut TxContext,
    ): EvidenceBatch {
        EvidenceBatch {
            id: object::new(ctx),
            window_id,
            window_start,
            window_end,
            grace_interval,
            required_min_count,
            max_timestamp_spread,
            accepted_slot_ids:     vector::empty(),
            accepted_device_ids:   vector::empty(),
            accepted_sensor_types: vector::empty(),
            accepted_timestamps:   vector::empty(),
            accepted_nonces:       vector::empty(),
            batch_hash:            vector::empty(),
            status: STATUS_OPEN,
        }
    }

    // ── Accessors ───────────────────────────────────────────────────────────

    public fun device_id(d: &MedicalDevice): address   { d.device_id }
    public fun device_active(d: &MedicalDevice): bool  { d.active }
    public fun device_sensor_type(d: &MedicalDevice): u8 { d.sensor_type }

    public fun slot_device_id(s: &EvidenceSlot): address   { s.device_id }
    public fun slot_sensor_type(s: &EvidenceSlot): u8      { s.sensor_type }
    public fun slot_timestamp(s: &EvidenceSlot): u64       { s.timestamp }
    public fun slot_nonce(s: &EvidenceSlot): u64           { s.nonce }
    public fun slot_window_id(s: &EvidenceSlot): u64       { s.window_id }
    public fun slot_id(s: &EvidenceSlot): ID               { object::id(s) }

    public fun batch_status(b: &EvidenceBatch): u8         { b.status }
    public fun batch_window_id(b: &EvidenceBatch): u64     { b.window_id }
    public fun batch_window_start(b: &EvidenceBatch): u64  { b.window_start }
    public fun batch_window_end(b: &EvidenceBatch): u64    { b.window_end }
    public fun batch_grace(b: &EvidenceBatch): u64         { b.grace_interval }
    public fun batch_min_count(b: &EvidenceBatch): u64     { b.required_min_count }
    public fun batch_max_spread(b: &EvidenceBatch): u64    { b.max_timestamp_spread }
    public fun batch_count(b: &EvidenceBatch): u64 {
        vector::length(&b.accepted_slot_ids) as u64
    }
    public fun batch_hash(b: &EvidenceBatch): &vector<u8>  { &b.batch_hash }
    public fun batch_accepted_ids(b: &EvidenceBatch): &vector<ID> {
        &b.accepted_slot_ids
    }

    // ── Status helpers ───────────────────────────────────────────────────────

    public fun status_open(): u8      { STATUS_OPEN }
    public fun status_finalized(): u8 { STATUS_FINALIZED }
    public fun status_expired(): u8   { STATUS_EXPIRED }
    public fun status_invalid(): u8   { STATUS_INVALID }

    // ── Error code accessors (for tests) ────────────────────────────────────

    public fun err_device_inactive(): u64   { E_DEVICE_INACTIVE }
    public fun err_wrong_window(): u64      { E_WRONG_WINDOW }
    public fun err_timestamp_outside(): u64 { E_TIMESTAMP_OUTSIDE }
    public fun err_nonce_reuse(): u64       { E_NONCE_REUSE }
    public fun err_conflict(): u64          { E_CONFLICT }
    public fun err_batch_not_open(): u64    { E_BATCH_NOT_OPEN }
    public fun err_count_not_met(): u64     { E_COUNT_NOT_MET }
    public fun err_spread_exceeded(): u64   { E_SPREAD_EXCEEDED }

    // ── Internal mutators (used only by accumulator.move) ───────────────────

    public(package) fun set_status(b: &mut EvidenceBatch, s: u8) {
        b.status = s;
    }

    public(package) fun set_batch_hash(b: &mut EvidenceBatch, h: vector<u8>) {
        b.batch_hash = h;
    }

    public(package) fun push_accepted(
        b:           &mut EvidenceBatch,
        slot_id:     ID,
        device_id:   address,
        sensor_type: u8,
        timestamp:   u64,
        nonce:       u64,
    ) {
        vector::push_back(&mut b.accepted_slot_ids,     slot_id);
        vector::push_back(&mut b.accepted_device_ids,   device_id);
        vector::push_back(&mut b.accepted_sensor_types, sensor_type);
        vector::push_back(&mut b.accepted_timestamps,   timestamp);
        vector::push_back(&mut b.accepted_nonces,       nonce);
    }

    public(package) fun accepted_device_ids(b: &EvidenceBatch): &vector<address> {
        &b.accepted_device_ids
    }

    public(package) fun accepted_sensor_types(b: &EvidenceBatch): &vector<u8> {
        &b.accepted_sensor_types
    }

    public(package) fun accepted_timestamps(b: &EvidenceBatch): &vector<u64> {
        &b.accepted_timestamps
    }

    public(package) fun accepted_nonces(b: &EvidenceBatch): &vector<u64> {
        &b.accepted_nonces
    }

    #[test_only]
    public fun new_device_inactive_for_test(
        device_id:   address,
        sensor_type: u8,
        ctx:         &mut iota::tx_context::TxContext,
    ): MedicalDevice {
        MedicalDevice {
            id: iota::object::new(ctx),
            device_id,
            sensor_type,
            active: false,
        }
    }
}
