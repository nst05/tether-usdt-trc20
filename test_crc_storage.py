#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты и примеры работы с CRC-16 CCITT хранилищем
"""

import struct
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
#  Константы и функции (скопированы для теста)
# ═══════════════════════════════════════════════════════════════════════════

SCALE = 100
BLOCK_SIZE = 0x28
CRC_SIZE = 2
INIT_CRC = 0xFFFF
POLY_CRC = 0x1021


def crc16_ccitt(data):
    """CRC-16 CCITT"""
    crc = INIT_CRC
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc <<= 1
            if crc & 0x10000:
                crc ^= POLY_CRC
            crc &= 0xFFFF
    return crc


def encode_value(value: float) -> bytes:
    """Значение → fixed-point big-endian"""
    raw = int(round(value * SCALE))
    if not 0 <= raw <= 0xFFFFFFFF:
        raise ValueError(f"Диапазон: 0.00 – 42949672.95")
    return raw.to_bytes(4, "big", signed=False)


def decode_value(data: bytes) -> float:
    """Fixed-point big-endian → значение"""
    if len(data) != 4:
        raise ValueError("Неверная длина данных")
    return int.from_bytes(data, "big", signed=False) / SCALE


def make_block(value: float) -> tuple:
    """Создаёт блок и вычисляет CRC"""
    val_bytes = encode_value(value)
    block = val_bytes + val_bytes + b'\x00' * 32
    crc = crc16_ccitt(block)
    return block, crc


# ═══════════════════════════════════════════════════════════════════════════
#  ТЕСТЫ
# ═══════════════════════════════════════════════════════════════════════════

def test_crc_calculation():
    """Тест: вычисление CRC для известных значений"""
    print("\n" + "="*70)
    print("ТЕСТ 1: Вычисление CRC")
    print("="*70)

    test_cases = [
        (9442.36, 0xAC55),
        (9440.38, 0x8748),
        (12.34, 0xC7D9),
        (50.00, 0x3798),
        (99.99, 0x98F2),
        (100.00, 0xF17A),
        (1.00, 0x74B7),
        (0.01, 0xA7AF),
    ]

    passed = 0
    failed = 0

    for value, expected_crc in test_cases:
        block, calculated_crc = make_block(value)

        status = "✓ PASS" if calculated_crc == expected_crc else "✗ FAIL"
        symbol = "✓" if calculated_crc == expected_crc else "✗"

        print(f"{symbol} {value:10.2f} → 0x{calculated_crc:04X} (ожидалось 0x{expected_crc:04X}) {status}")

        if calculated_crc == expected_crc:
            passed += 1
        else:
            failed += 1

    print(f"\nРезультат: {passed} пройдено, {failed} не пройдено")
    return failed == 0


def test_encoding_decoding():
    """Тест: кодирование и декодирование значений"""
    print("\n" + "="*70)
    print("ТЕСТ 2: Кодирование/Декодирование")
    print("="*70)

    test_values = [0.01, 1.23, 99.99, 1234.56, 9999.99, 42949672.95]

    passed = 0
    failed = 0

    for original in test_values:
        encoded = encode_value(original)
        decoded = decode_value(encoded)

        # Допускаем погрешность из-за округления
        error = abs(decoded - original)
        is_ok = error < 0.01

        status = "✓ PASS" if is_ok else "✗ FAIL"
        symbol = "✓" if is_ok else "✗"

        print(f"{symbol} {original:.2f} → {encoded.hex()} → {decoded:.2f} (ошибка: {error:.4f}) {status}")

        if is_ok:
            passed += 1
        else:
            failed += 1

    print(f"\nРезультат: {passed} пройдено, {failed} не пройдено")
    return failed == 0


def test_block_structure():
    """Тест: структура блока"""
    print("\n" + "="*70)
    print("ТЕСТ 3: Структура блока")
    print("="*70)

    value = 9442.36
    block, crc = make_block(value)

    print(f"Значение: {value}")
    print(f"Размер блока: {len(block)} байт (ожидается 40)")
    print(f"CRC-16: 0x{crc:04X}")

    # Проверяем структуру
    val1 = block[0:4]
    val2 = block[4:8]
    padding = block[8:40]

    print(f"\n  Значение 1: {val1.hex()}")
    print(f"  Значение 2: {val2.hex()}")
    print(f"  Паддинг:    {padding.hex()}")

    # Проверяем дубль
    is_duplicate_ok = val1 == val2
    print(f"\n  Дубль совпадает: {'✓' if is_duplicate_ok else '✗'}")

    # Проверяем паддинг
    is_padding_ok = padding == b'\x00' * 32
    print(f"  Паддинг всё нули: {'✓' if is_padding_ok else '✗'}")

    return len(block) == 40 and is_duplicate_ok and is_padding_ok


def test_file_creation():
    """Тест: создание тестового файла"""
    print("\n" + "="*70)
    print("ТЕСТ 4: Создание тестового файла")
    print("="*70)

    test_file = Path("test_storage.bin")

    try:
        # Создаём файл с несколькими значениями
        values = [
            (9442.36, "Первое значение"),
            (9440.38, "Второе значение"),
            (12.34, "Третье значение"),
        ]

        data = bytearray(2048)  # 2 КБ файл

        pos = 0x100  # Начинаем со смещения 0x100
        file_values = []

        print(f"\nСоздание файла: {test_file}")
        print(f"Размер: 2048 байт")

        for value, desc in values:
            block, crc = make_block(value)

            # Проверяем, есть ли место
            if pos + len(block) + CRC_SIZE > len(data):
                print(f"✗ Недостаточно места в файле")
                break

            # Записываем блок
            data[pos:pos+len(block)] = block
            data[pos+len(block):pos+len(block)+CRC_SIZE] = struct.pack('>H', crc)

            file_values.append({
                'value': value,
                'pos': pos,
                'crc': crc,
                'desc': desc
            })

            print(f"  ✓ {desc:20s} на 0x{pos:04X}: {value:.2f} (CRC: 0x{crc:04X})")

            pos += len(block) + CRC_SIZE + 0x10  # +0x10 отступ между значениями

        # Сохраняем файл
        with open(test_file, 'wb') as f:
            f.write(data)

        print(f"\n✓ Файл создан: {test_file}")

        # Теперь читаем и проверяем
        print(f"\nПроверка файла:")
        with open(test_file, 'rb') as f:
            file_data = f.read()

        all_ok = True
        for fv in file_values:
            pos = fv['pos']
            block = file_data[pos:pos+BLOCK_SIZE]
            stored_crc = struct.unpack('>H', file_data[pos+BLOCK_SIZE:pos+BLOCK_SIZE+2])[0]
            calc_crc = crc16_ccitt(block)

            is_ok = stored_crc == calc_crc
            symbol = "✓" if is_ok else "✗"

            print(f"  {symbol} {fv['desc']:20s}: {fv['value']:.2f} (CRC: 0x{stored_crc:04X} vs 0x{calc_crc:04X})")

            if not is_ok:
                all_ok = False

        return all_ok

    except Exception as e:
        print(f"✗ Ошибка: {e}")
        return False
    finally:
        if test_file.exists():
            test_file.unlink()
            print(f"\n  Тестовый файл удалён")


def test_boundary_values():
    """Тест: граничные значения"""
    print("\n" + "="*70)
    print("ТЕСТ 5: Граничные значения")
    print("="*70)

    boundary_values = [
        0.00,
        0.01,
        99.99,
        100.00,
        999.99,
        1000.00,
        9999.99,
        10000.00,
        99999.99,
        100000.00,
        999999.99,
        1000000.00,
        42949672.95,
    ]

    print(f"\n{'Значение':<15} {'HEX':<12} {'CRC-16':<10}")
    print("-" * 50)

    passed = 0
    failed = 0

    for value in boundary_values:
        try:
            block, crc = make_block(value)
            raw = int(value * SCALE)
            hex_str = f"0x{raw:08X}"
            print(f"{value:14.2f}  {hex_str:<11} 0x{crc:04X}")
            passed += 1
        except Exception as e:
            print(f"{value:14.2f}  ✗ {e}")
            failed += 1

    print(f"\nРезультат: {passed} пройдено, {failed} не пройдено")
    return failed == 0


def print_header():
    """Печатает заголовок"""
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║        CRC-16 CCITT Storage Format — Test Suite                  ║
╚═══════════════════════════════════════════════════════════════════╝

Алгоритм: CRC-16 CCITT
Полином:  0x1021
Init:     0xFFFF
Формат:   Fixed-Point (value × 100, big-endian)
    """)


def main():
    """Запускает все тесты"""
    print_header()

    results = {
        "CRC вычисление": test_crc_calculation(),
        "Кодирование/декодирование": test_encoding_decoding(),
        "Структура блока": test_block_structure(),
        "Создание файла": test_file_creation(),
        "Граничные значения": test_boundary_values(),
    }

    print("\n" + "="*70)
    print("ИТОГОВЫЙ РЕЗУЛЬТАТ")
    print("="*70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        symbol = "✓" if result else "✗"
        print(f"{symbol} {name}")

    print(f"\nВсего: {passed}/{total} тестов пройдено")

    if passed == total:
        print("\n✓ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return 0
    else:
        print(f"\n✗ {total - passed} ТЕСТОВ НЕ ПРОЙДЕНО")
        return 1


if __name__ == "__main__":
    sys.exit(main())
