/// types.move — Design B (Owned-Slot Staging)
///
/// Same object model as Design A.
/// EvidenceSlot is created as an OWNED object during ingestion.
/// EvidenceBatch is created as a SHARED object only at finalization.
/// This file is structurally identical to design_a::types but lives in
/// a separate package so both can be deployed and benchmarked independently.

module design_b::types {
    use iota::object::{Self, UID, ID};
    use iota::tx_context::TxContext;

    const STATUS_OPEN:      u8 = 0;
    const STATUS_FINALIZED: u8 = 1;
    const STATUS_EXPIRED:   u8 = 2;
    const STATUS_INVALID:   u8 = 3;

    const E_DEVICE_INACTIVE:    u64 = 1;
    const E_WRONG_WINDOW:       u64 = 2;
    const E_TIMESTAMP_OUTSIDE:  u64 = 3;
    const E_NONCE_REUSE:        u64 = 4;
    const E_CONFLICT:           u64 = 5;
    const E_SLOT_ALREADY_USED:  u64 = 6;
    const E_COUNT_NOT_MET:      u64 = 7;
    const E_SPREAD_EXCEEDED:    u64 = 8;
    const E_PREMATURE_FINALIZE: u64 = 9;

    public struct MedicalDevice has key, store {
        id:          UID,
        device_id:   address,
        sensor_type: u8,
        active:      bool,
    }

    /// Owned object — created per sensor submission, no shared state touched.
    /// window_id links this slot to its intended batch window.
    public struct EvidenceSlot has key, store {
        id:             UID,
        device_id:      address,
        sensor_type:    u8,
        reading_hash:   vector<u8>,
        timestamp:      u64,
        nonce:          u64,
        window_id:      u64,
        signature_hash: vector<u8>,
        consumed:       bool,
    }

    /// BatchConfig holds window parameters; passed to finalize_from_slots.
    /// Stored as an owned object by the window-closer.
    public struct BatchConfig has key, store {
        id:                   UID,
        window_id:            u64,
        window_start:         u64,
        window_end:           u64,
        grace_interval:       u64,
        required_min_count:   u64,
        max_timestamp_spread: u64,
    }

    /// Shared object — created only at finalization.
    /// Does not exist during the ingestion phase.
    public struct EvidenceBatch has key, store {
        id:                  UID,
        window_id:           u64,
        window_start:        u64,
        window_end:          u64,
        grace_interval:      u64,
        required_min_count:  u64,
        max_timestamp_spread: u64,
        accepted_slot_ids:   vector<ID>,
        batch_hash:          vector<u8>,
        status:              u8,
    }

    // ── Constructors ─────────────────────────────────────────────────────────

    public fun new_device(
        device_id:   address,
        sensor_type: u8,
        ctx:         &mut TxContext,
    ): MedicalDevice {
        MedicalDevice { id: object::new(ctx), device_id, sensor_type, active: true }
    }

    /// create_slot — the ONLY write operation a sensor performs.
    /// Returns an owned EvidenceSlot to the caller.
    /// Does NOT touch any shared object.
    public fun create_slot(
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

    public fun new_config(
        window_id:            u64,
        window_start:         u64,
        window_end:           u64,
        grace_interval:       u64,
        required_min_count:   u64,
        max_timestamp_spread: u64,
        ctx:                  &mut TxContext,
    ): BatchConfig {
        BatchConfig {
            id: object::new(ctx),
            window_id,
            window_start,
            window_end,
            grace_interval,
            required_min_count,
            max_timestamp_spread,
        }
    }

    // ── Accessors ────────────────────────────────────────────────────────────

    public fun device_active(d: &MedicalDevice): bool    { d.active }
    public fun device_id(d: &MedicalDevice): address     { d.device_id }
    public fun device_sensor_type(d: &MedicalDevice): u8 { d.sensor_type }

    public fun slot_device_id(s: &EvidenceSlot): address   { s.device_id }
    public fun slot_sensor_type(s: &EvidenceSlot): u8      { s.sensor_type }
    public fun slot_timestamp(s: &EvidenceSlot): u64       { s.timestamp }
    public fun slot_nonce(s: &EvidenceSlot): u64           { s.nonce }
    public fun slot_window_id(s: &EvidenceSlot): u64       { s.window_id }
    public fun slot_id(s: &EvidenceSlot): ID               { object::id(s) }
    public fun slot_consumed(s: &EvidenceSlot): bool       { s.consumed }

    public fun config_window_id(c: &BatchConfig): u64    { c.window_id }
    public fun config_window_start(c: &BatchConfig): u64 { c.window_start }
    public fun config_window_end(c: &BatchConfig): u64   { c.window_end }
    public fun config_grace(c: &BatchConfig): u64        { c.grace_interval }
    public fun config_min_count(c: &BatchConfig): u64    { c.required_min_count }
    public fun config_max_spread(c: &BatchConfig): u64   { c.max_timestamp_spread }

    public fun batch_status(b: &EvidenceBatch): u8        { b.status }
    public fun batch_window_id(b: &EvidenceBatch): u64    { b.window_id }
    public fun batch_hash(b: &EvidenceBatch): &vector<u8> { &b.batch_hash }
    public fun batch_accepted_ids(b: &EvidenceBatch): &vector<ID> {
        &b.accepted_slot_ids
    }

    public fun status_open(): u8      { STATUS_OPEN }
    public fun status_finalized(): u8 { STATUS_FINALIZED }
    public fun status_expired(): u8   { STATUS_EXPIRED }
    public fun status_invalid(): u8   { STATUS_INVALID }

    public fun err_device_inactive(): u64   { E_DEVICE_INACTIVE }
    public fun err_wrong_window(): u64      { E_WRONG_WINDOW }
    public fun err_timestamp_outside(): u64 { E_TIMESTAMP_OUTSIDE }
    public fun err_nonce_reuse(): u64       { E_NONCE_REUSE }
    public fun err_conflict(): u64          { E_CONFLICT }
    public fun err_slot_already_used(): u64 { E_SLOT_ALREADY_USED }
    public fun err_count_not_met(): u64     { E_COUNT_NOT_MET }
    public fun err_spread_exceeded(): u64   { E_SPREAD_EXCEEDED }
    public fun err_premature_finalize(): u64{ E_PREMATURE_FINALIZE }

    public(package) fun mark_consumed(s: &mut EvidenceSlot) {
        s.consumed = true;
    }

    public(package) fun new_batch_internal(
        window_id:            u64,
        window_start:         u64,
        window_end:           u64,
        grace_interval:       u64,
        required_min_count:   u64,
        max_timestamp_spread: u64,
        accepted_slot_ids:    vector<ID>,
        batch_hash:           vector<u8>,
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
            accepted_slot_ids,
            batch_hash,
            status: STATUS_FINALIZED,
        }
    }

    #[test_only]
    public fun new_device_inactive_for_test(
        device_id:   address,
        sensor_type: u8,
        ctx:         &mut TxContext,
    ): MedicalDevice {
        MedicalDevice { id: object::new(ctx), device_id, sensor_type, active: false }
    }

    // ── DeviceRegistry (test helper) ────────────────────────────────────────
    // Wraps a vector<MedicalDevice> in a key+store object so the vector
    // can be properly consumed (transferred) after tests.

    public struct DeviceRegistry has key, store {
        id:      UID,
        devices: vector<MedicalDevice>,
    }

    public fun new_registry(
        devices: vector<MedicalDevice>,
        ctx:     &mut TxContext,
    ): DeviceRegistry {
        DeviceRegistry { id: object::new(ctx), devices }
    }

    public fun registry_devices(r: &DeviceRegistry): &vector<MedicalDevice> {
        &r.devices
    }
}
