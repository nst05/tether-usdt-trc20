from __future__ import annotations

import unittest
from datetime import datetime

from ce208_model import (
    AT25_SIZE,
    ENERGY_ARCHIVES,
    EVENT_LOGS,
    SMALL_SIZE,
    CE208State,
    ClockValue,
    EnergyBank,
    TimeCounterBlock,
    build_record,
    crc16_msp432,
    crc32_msb,
    decode_energy,
    encode_energy,
    pack_event_timestamp,
    record_crc,
    set_crc_scheme,
    unpack_event_timestamp,
    verify_record,
)


class CE208ModelTests(unittest.TestCase):
    def test_small_path_is_same_spi_image(self):
        state = CE208State()
        state.small[0x123] = 0x5A
        self.assertEqual(state.at25[0x123], 0x5A)
        state.at25[0x456] = 0xA5
        self.assertEqual(state.small[0x456], 0xA5)

    def test_factory_pattern_crc(self):
        body = bytes((index * 3) & 0xFF for index in range(0x7E))
        self.assertEqual(record_crc(body), 0x12D0)
        valid, stored, calculated = verify_record(body + b"\xD0\x12")
        self.assertTrue(valid)
        self.assertEqual(stored, calculated)

    def test_processor_crc_profiles_are_distinct(self):
        body = bytes(range(66))
        self.assertEqual(crc32_msb(body) & 0xFFFF, 0x1D77)
        self.assertEqual(crc16_msp432(body), 0xBB29)
        self.assertNotEqual(crc32_msb(body) & 0xFFFF, crc16_msp432(body))

    def test_direction_pair_uses_selected_processor_crc(self):
        try:
            for scheme, crc_function in (
                ("ce208", lambda body: crc32_msb(body) & 0xFFFF),
                ("msp432", crc16_msp432),
            ):
                state = CE208State(crc=scheme)
                state.synchronize_direction_pair(
                    1, 3, [10, 20, 30, 40, 50, 60, 70, 80], 0.0090121,
                    include_archives=False,
                )
                for bank in (1, 3):
                    for backup in (False, True):
                        address = state.current_energy_address(bank, backup)
                        record = bytes(state.small[address:address + 0x44])
                        self.assertEqual(
                            int.from_bytes(record[-2:], "little"),
                            crc_function(record[:-2]),
                        )
        finally:
            set_crc_scheme("ce208")

    def test_clock_primary_and_backup(self):
        state = CE208State(bytes([0xFF]) * SMALL_SIZE, bytes([0xFF]) * AT25_SIZE)
        value = ClockValue.from_datetime(datetime(2026, 8, 26, 13, 42, 17))
        state.write_clock(value)
        decoded, result = state.read_clock()
        self.assertEqual(decoded.year, 2026)
        self.assertEqual(decoded.month, 8)
        self.assertEqual(result.address, 0)
        self.assertEqual(state.small[0:10], state.small[0x19E0:0x19EA])

    def test_current_energy_layout_and_sum(self):
        state = CE208State()
        bank = EnergyBank.empty()
        bank.set_tariffs([100, 200, 300, 400, 500, 600, 700, 800])
        state.write_current_energy(0, bank)
        decoded, result = state.read_current_energy(0)
        self.assertEqual(decoded.tariffs[:2], [100, 200])
        self.assertEqual(decoded.total, 3600)
        self.assertEqual(result.address, 0x20)
        self.assertEqual(state.small[0x20:0x64], state.small[0x1A00:0x1A44])

    def test_active_tariff_preserves_control_flags(self):
        state = CE208State()
        state.write_active_tariff(6)
        tariff, result = state.read_active_tariff()
        self.assertEqual(tariff, 6)
        self.assertTrue(result.valid)
        self.assertEqual(state.small[0x0A:0x20], state.small[0x19EA:0x1A00])

    def test_time_counter_blocks(self):
        state = CE208State()
        timestamp = datetime(2026, 8, 26, 19, 0, 0)
        block = TimeCounterBlock([(timestamp, index * 100) for index in range(8)])
        state.write_time_counters(1, block)
        decoded, result = state.read_time_counters(1)
        self.assertEqual(result.address, 0x0F24)
        self.assertEqual(decoded.pairs[7], (timestamp, 700))
        self.assertTrue(result.valid)

    def test_archive_boundaries_and_reserved_gap(self):
        ordered = [ENERGY_ARCHIVES[index] for index in (0, 1, 2, 5)]
        first_end = ordered[0][0] + ordered[0][1] * 0x110
        self.assertEqual(first_end, 0x0C238)
        self.assertEqual(ordered[1][0] - first_end, 0x4400)
        for left, right in zip(ordered[1:], ordered[2:]):
            left_base, left_count, _ = left
            right_base, _, _ = right
            self.assertEqual(left_base + left_count * 0x110, right_base)
        self.assertEqual(ordered[-1][0] + ordered[-1][1] * 0x110, 0x15098)

    def test_archive_modulo_and_crc(self):
        state = CE208State()
        bank = EnergyBank.empty()
        bank.marker = 7
        bank.set_tariffs([1] * 8)
        state.write_archive_energy(2, 12, 3, bank)
        decoded, result = state.read_archive_energy(2, 2, 3)
        self.assertEqual(decoded.marker, 7)
        self.assertEqual(decoded.total, 8)
        self.assertTrue(result.valid)

    def test_synchronize_current_and_all_archives(self):
        state = CE208State()
        stats = state.synchronize_energy_everywhere([2], [100, 250], archive_marker=9)
        self.assertEqual(stats["archive_records"], 128 + 40 + 10 + 20)
        current, _ = state.read_current_energy(2)
        self.assertEqual(current.tariffs, [100, 250, 0, 0, 0, 0, 0, 0])
        self.assertEqual(current.total, 350)
        tariff, _ = state.read_active_tariff()
        self.assertEqual(tariff, 1)
        for archive_type, (_base, count, _name) in ENERGY_ARCHIVES.items():
            for slot in (0, count - 1):
                archived, result = state.read_archive_energy(archive_type, slot, 2)
                self.assertEqual(archived.tariffs, current.tariffs)
                self.assertEqual(archived.marker, 9)
                self.assertTrue(result.valid)

    def test_two_direction_groups_are_independent_and_pair_reactive(self):
        state = CE208State()
        first = state.synchronize_direction_pair(
            0, 2, [100, 200, 0, 0, 0, 0, 0, 0], 0.01, archive_marker=7
        )
        second = state.synchronize_direction_pair(
            1, 3, [900, 800, 0, 0, 0, 0, 0, 0], 0.02, archive_marker=8
        )
        self.assertEqual(first["archive_records"], (128 + 40 + 10 + 20) * 2)
        self.assertEqual(second["archive_records"], (128 + 40 + 10 + 20) * 2)

        bank0, _ = state.read_current_energy(0)
        bank1, _ = state.read_current_energy(1)
        bank2, _ = state.read_current_energy(2)
        bank3, _ = state.read_current_energy(3)
        self.assertEqual(bank0.tariffs[:2], [100, 200])
        self.assertEqual(bank2.tariffs[:2], [1, 2])
        self.assertEqual(bank1.tariffs[:2], [900, 800])
        self.assertEqual(bank3.tariffs[:2], [18, 16])

        archived0, _ = state.read_archive_energy(0, 0, 0)
        archived1, _ = state.read_archive_energy(0, 0, 1)
        archived2, _ = state.read_archive_energy(0, 0, 2)
        archived3, _ = state.read_archive_energy(0, 0, 3)
        self.assertEqual(archived0.tariffs[:2], [100, 200])
        self.assertEqual(archived2.tariffs[:2], [1, 2])
        self.assertEqual(archived1.tariffs[:2], [900, 800])
        self.assertEqual(archived3.tariffs[:2], [18, 16])
        self.assertEqual((archived0.marker, archived2.marker), (7, 7))
        self.assertEqual((archived1.marker, archived3.marker), (8, 8))

    def test_first_pair_update_does_not_touch_second_pair(self):
        state = CE208State()
        second_active = EnergyBank.empty()
        second_active.marker = 0x31
        second_active.set_tariffs([901, 802, 703, 604, 505, 406, 307, 208])
        second_reactive = EnergyBank.empty()
        second_reactive.marker = 0x42
        second_reactive.set_tariffs([91, 82, 73, 64, 55, 46, 37, 28])
        state.write_current_energy(1, second_active)
        state.write_current_energy(3, second_reactive)
        state.write_archive_energy(1, 7, 1, second_active)
        state.write_archive_energy(1, 7, 3, second_reactive)

        before_current_1 = bytes(state.small[0x0064:0x00A8])
        before_current_3 = bytes(state.small[0x00EC:0x0130])
        before_archive_1 = bytes(
            state.at25[state.archive_address(1, 7, 1):state.archive_address(1, 7, 1) + 0x44]
        )
        before_archive_3 = bytes(
            state.at25[state.archive_address(1, 7, 3):state.archive_address(1, 7, 3) + 0x44]
        )

        state.synchronize_direction_pair(
            0, 2, [10, 20, 30, 40, 50, 60, 70, 80], 0.0090121
        )

        self.assertEqual(bytes(state.small[0x0064:0x00A8]), before_current_1)
        self.assertEqual(bytes(state.small[0x00EC:0x0130]), before_current_3)
        self.assertEqual(
            bytes(state.at25[state.archive_address(1, 7, 1):state.archive_address(1, 7, 1) + 0x44]),
            before_archive_1,
        )
        self.assertEqual(
            bytes(state.at25[state.archive_address(1, 7, 3):state.archive_address(1, 7, 3) + 0x44]),
            before_archive_3,
        )

    def test_display_conversion(self):
        raw = encode_energy("149.62100", divisor=4, decimals=5)
        self.assertEqual(decode_energy(raw, 4, 5), decode_energy(raw + 3, 4, 5))
        self.assertEqual(str(decode_energy(raw, 4, 5)), "149.62100")

    def test_event_timestamp_codec(self):
        value = datetime(2026, 8, 26, 18, 7, 59)
        self.assertEqual(unpack_event_timestamp(pack_event_timestamp(value)), value)
        self.assertEqual(pack_event_timestamp(datetime(2000, 1, 1)), 0)

    def test_event_catalog_is_contiguous(self):
        self.assertEqual(len(EVENT_LOGS), 70)
        self.assertEqual(EVENT_LOGS[0].base, 0x47E70)
        for left_id in range(69):
            left = EVENT_LOGS[left_id]
            right = EVENT_LOGS[left_id + 1]
            self.assertEqual(left.base + left.record_length * left.capacity, right.base)
        last = EVENT_LOGS[69]
        self.assertEqual(last.base + last.record_length * last.capacity, 0x49DF0)

    def test_append_event_updates_both_memories_and_wraps(self):
        state = CE208State()
        timestamp = datetime(2026, 8, 26, 18, 10, 0)
        first, first_address, first_counter = state.append_event(0, timestamp, status=3, value=123456)
        self.assertEqual(first_counter, 1)
        self.assertEqual(first.sequence, 1)
        self.assertEqual(first_address, EVENT_LOGS[0].base + EVENT_LOGS[0].record_length)
        self.assertEqual(state.event_count(0), 1)
        decoded, result, counter = state.read_event(0)
        self.assertEqual((decoded.timestamp, decoded.status, decoded.value), (timestamp, 3, 123456))
        self.assertTrue(result.valid)
        self.assertEqual(counter, 1)
        self.assertEqual(state.small[0x308:0x310], state.small[0x1CE8:0x1CF0])
        self.assertEqual(state.small[0x310:0x334], state.small[0x1CF0:0x1D14])

        for value in range(2, 22):
            state.append_event(0, timestamp, status=value, value=value)
        newest, newest_result, newest_counter = state.read_event(0)
        self.assertEqual(newest_counter, 21)
        self.assertEqual(newest.status, 21)
        self.assertEqual(newest.value, 21)
        self.assertEqual(newest_result.address, first_address)


if __name__ == "__main__":
    unittest.main()
