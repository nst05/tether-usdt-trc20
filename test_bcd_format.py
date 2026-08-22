#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты формата S (BCD) — второго формата хранения, найденного в дампе.

Поле S: упакованный BCD с обратным порядком байт, значение продублировано
четыре раза внутри 65-байтовой записи. CRC у формата нет.
"""

import sys

from crc_storage_i2c import (
    encode_bcd, decode_bcd, find_bcd_records, patch_bcd_record,
    find_records, crc16_ccitt,
    BCD_RECORD_SIZE, BCD_VALUE_SIZE, BCD_COPY_OFFSETS,
)

# Записи формата S, реально присутствующие в дампе.
DUMP_BCD = [
    (0x11BC, 9066.64), (0x11FD, 9126.74), (0x123E, 9127.35),
    (0x127F, 9179.60), (0x12C0, 9226.71), (0x1301, 9263.06),
    (0x1342, 9288.82), (0x1383, 9308.45), (0x13C4, 9320.94),
    (0x1405, 9328.87), (0x1446, 9399.56), (0x14C8, 9008.40),
    (0x1509, 9054.48),
]

# Записи формата T.
DUMP_FIXED = [(0x01C1, 9442.36), (0x0201, 9440.38), (0x03E8, 9441.38)]

TARGET = 9399.56
TARGET_OFFSET = 0x1446


def build_dump() -> bytes:
    """Собрать синтетический дамп с записями обоих форматов"""
    data = bytearray(b"\x00" * 32768)

    for offset, value in DUMP_FIXED:
        payload = int(round(value * 100)).to_bytes(4, "big")
        block = payload + payload + b"\x00" * 32
        data[offset:offset + 40] = block
        crc = crc16_ccitt(block)
        data[offset + 40:offset + 42] = crc.to_bytes(2, "big")

    for offset, value in DUMP_BCD:
        data[offset:offset + 3] = b"\x01\x01\x44"
        payload = encode_bcd(value)
        for copy in BCD_COPY_OFFSETS:
            data[offset + copy:offset + copy + BCD_VALUE_SIZE] = payload

    return bytes(data)


def check(label, condition, detail=""):
    print(f"[{'OK' if condition else 'FAIL'}] {label}"
          + (f" — {detail}" if detail else ""))
    return condition


def main():
    passed = True

    print("=" * 72)
    print("1. Кодирование и декодирование BCD")
    print("=" * 72)

    passed &= check("9399.56 → 56 99 93 00",
                    encode_bcd(TARGET) == bytes.fromhex("56999300"),
                    encode_bcd(TARGET).hex(" ").upper())
    passed &= check("56 99 93 00 → 9399.56",
                    decode_bcd(bytes.fromhex("56999300")) == TARGET)

    for value in (0.01, 1.00, 99.99, 9399.56, 9442.36, 123456.78, 999999.99):
        roundtrip = decode_bcd(encode_bcd(value))
        passed &= check(f"туда-обратно {value}", roundtrip == value,
                        f"получили {roundtrip}")

    passed &= check("не-BCD байты отвергаются",
                    decode_bcd(bytes.fromhex("FFEE1200")) is None)
    passed &= check("0x3E — недопустимая цифра",
                    decode_bcd(bytes.fromhex("0D3E0000")) is None)

    print()
    print("=" * 72)
    print("2. Поиск записей формата S в дампе")
    print("=" * 72)

    data = build_dump()
    records = find_bcd_records(data, 1000, 100000)

    passed &= check(f"найдено {len(records)} записей",
                    len(records) == len(DUMP_BCD),
                    f"ожидали {len(DUMP_BCD)}")

    found = {r['offset']: r['value'] for r in records}
    for offset, value in DUMP_BCD:
        passed &= check(f"0x{offset:04X} = {value}",
                        found.get(offset) == value,
                        f"получили {found.get(offset)}")

    target = [r for r in records if r['offset'] == TARGET_OFFSET]
    passed &= check(f"искомое {TARGET} на 0x{TARGET_OFFSET:04X}",
                    len(target) == 1 and target[0]['value'] == TARGET)
    if target:
        passed &= check("четыре копии значения",
                        len(target[0]['copies']) == 4,
                        ", ".join(f"0x{c:04X}" for c in target[0]['copies']))

    print()
    print("=" * 72)
    print("3. Форматы не мешают друг другу")
    print("=" * 72)

    fixed = find_records(data)
    passed &= check(f"формат T найден отдельно: {len(fixed)} записей",
                    len(fixed) == len(DUMP_FIXED))
    passed &= check("поиск T не цепляет записи S",
                    all(r['offset'] in dict(DUMP_FIXED) for r in fixed))
    passed &= check("поиск S не цепляет записи T",
                    all(r['offset'] in dict(DUMP_BCD) for r in records))

    print()
    print("=" * 72)
    print("4. Точечность правки: пишутся ровно 16 байт, вне их — ничего")
    print("=" * 72)

    buffer = bytearray(data)
    written = patch_bcd_record(buffer, TARGET_OFFSET, 9500.00)
    changed = [i for i in range(len(data)) if data[i] != buffer[i]]

    # Пишется 16 байт (4 копии × 4 байта), но отличаться могут не все:
    # у 9399.56 и 9500.00 старший байт одинаковый (00), поэтому реально
    # меняются 12. Гарантия точечности — не число изменившихся байт, а то,
    # что ЗА пределами четырёх копий не изменилось ничего.
    touched = {position + i for position in written
               for i in range(BCD_VALUE_SIZE)}

    passed &= check("записано 16 байт", len(touched) == 16,
                    f"позиций {len(touched)}")
    passed &= check("изменения только внутри копий",
                    set(changed) <= touched,
                    f"изменилось {len(changed)} из {len(touched)} записанных")
    passed &= check("копии легли по своим адресам",
                    written == [TARGET_OFFSET + c for c in BCD_COPY_OFFSETS],
                    ", ".join(f"0x{w:04X}" for w in written))
    passed &= check("заголовок не тронут",
                    buffer[TARGET_OFFSET:TARGET_OFFSET + 3]
                    == data[TARGET_OFFSET:TARGET_OFFSET + 3])
    passed &= check("нули между копиями не тронуты",
                    buffer[TARGET_OFFSET + 11:TARGET_OFFSET + 23]
                    == b"\x00" * 12)
    passed &= check("соседние записи не тронуты",
                    all(r['value'] == dict(DUMP_BCD)[r['offset']]
                        for r in find_bcd_records(bytes(buffer), 1000, 100000)
                        if r['offset'] != TARGET_OFFSET))
    passed &= check("записи формата T не тронуты",
                    find_records(bytes(buffer)) == fixed)

    print()
    print("=" * 72)
    print("5. Правка читается обратно")
    print("=" * 72)

    reread = find_bcd_records(bytes(buffer), 1000, 100000)
    updated = [r for r in reread if r['offset'] == TARGET_OFFSET]
    passed &= check("значение стало 9500.00",
                    len(updated) == 1 and updated[0]['value'] == 9500.00,
                    f"получили {updated[0]['value'] if updated else 'нет записи'}")

    print()
    print("=" * 72)
    print("6. Границы диапазона")
    print("=" * 72)

    for bad in (-0.01, 1000000.00):
        try:
            encode_bcd(bad)
            passed &= check(f"{bad} отвергнуто", False, "исключения не было")
        except ValueError:
            passed &= check(f"{bad} отвергнуто", True)

    print()
    print("=" * 72)
    print("ИТОГ:", "ВСЕ ТЕСТЫ ПРОЙДЕНЫ" if passed else "ЕСТЬ ПРОВАЛЫ")
    print("=" * 72)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
