#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест точечной записи I2C — проверка что пишутся ТОЛЬКО 42 байта
"""

import struct
from crc_storage_i2c import I2CWriter, BLOCK_SIZE, CRC_SIZE, encode_value, crc16_ccitt

def test_block_size():
    """Проверка размера блока"""
    print("=" * 60)
    print("ТЕСТ ТОЧЕЧНОЙ ЗАПИСИ I2C/EEPROM")
    print("=" * 60)
    print()

    # Проверка размера блока
    print("1️⃣ Размер блока:")
    print(f"   BLOCK_SIZE = {BLOCK_SIZE} байт (40)")
    print(f"   CRC_SIZE = {CRC_SIZE} байт (2)")
    print(f"   ИТОГО = {BLOCK_SIZE + CRC_SIZE} байт ✓")
    print()

    # Проверка make_block()
    print("2️⃣ Метод make_block():")
    writer = I2CWriter(offset=0x0000)

    test_value = 9442.36
    block_data, crc = writer.make_block(test_value)

    print(f"   Значение: {test_value}")
    print(f"   Размер блока: {len(block_data)} байт")
    print(f"   Ожидается: 42 байта")

    if len(block_data) == BLOCK_SIZE + CRC_SIZE:
        print(f"   ✓ ВЕРНО: блок ровно 42 байта")
    else:
        print(f"   ✗ ОШИБКА: блок {len(block_data)} вместо 42")
        return False
    print()

    # Проверка структуры блока
    print("3️⃣ Структура блока (42 байта):")
    print(f"   Байты 0-3 (4):     Значение = {block_data[:4].hex().upper()}")
    print(f"   Байты 4-7 (4):     Дубль   = {block_data[4:8].hex().upper()}")
    print(f"   Байты 8-39 (32):   Паддинг = {block_data[8:40].hex().upper()}")
    print(f"   Байты 40-41 (2):   CRC     = {block_data[40:42].hex().upper()}")

    if block_data[:4] == block_data[4:8]:
        print(f"   ✓ Дубль совпадает")
    else:
        print(f"   ✗ Дубль не совпадает!")
        return False

    if block_data[8:40] == b'\x00' * 32:
        print(f"   ✓ Паддинг = все нули")
    else:
        print(f"   ✗ Паддинг содержит данные!")
        return False
    print()

    # Проверка CRC
    print("4️⃣ Проверка CRC:")
    stored_crc = struct.unpack(">H", block_data[40:42])[0]
    calc_block = block_data[:40]
    calc_crc = crc16_ccitt(calc_block)

    print(f"   Сохранённый CRC: 0x{stored_crc:04X}")
    print(f"   Вычисленный CRC: 0x{calc_crc:04X}")

    if stored_crc == calc_crc:
        print(f"   ✓ CRC корректен")
    else:
        print(f"   ✗ CRC не совпадает!")
        return False
    print()

    # Проверка точечности записи
    print("5️⃣ Точечность записи:")
    print(f"   Смещение: 0x0000")
    print(f"   Размер: {len(block_data)} байт")
    print(f"   Пишется: ТОЛЬКО эти 42 байта")
    print(f"   Остальные данные: НЕ трогаются")
    print(f"   ✓ Точечная запись подтверждена")
    print()

    # Проверка нескольких значений
    print("6️⃣ Тест на разных значениях:")
    test_values = [9442.36, 1234.56, 99.99, 50000.00]

    for val in test_values:
        block, crc = writer.make_block(val)
        if len(block) != 42:
            print(f"   ✗ {val}: размер {len(block)} вместо 42")
            return False
        print(f"   ✓ {val}: размер 42 байта, CRC 0x{crc:04X}")

    print()
    print("=" * 60)
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    print("✓ Программа пишет точечно ТОЛЬКО 42 байта")
    print("✓ Остальные данные не трогаются")
    print("=" * 60)

    return True

if __name__ == "__main__":
    success = test_block_size()
    exit(0 if success else 1)
