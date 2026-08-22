#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Демонстрация: как подстраиваются поля 2 и 3 при вводе значения в поле 1
"""

import struct
from crc_storage_i2c import (
    encode_value, crc16_ccitt, SCALE
)

def show_auto_calc(value_str):
    """Показывает как подстраиваются поля 2 и 3 при вводе значения"""
    print()
    print("=" * 70)
    print(f"ВВОД В ПОЛЕ 1: {value_str}")
    print("=" * 70)

    try:
        # Парсим значение
        value = float(value_str.replace(",", "."))
        print(f"✓ Распарсено: {value}")
        print()

        # ПОЛЕ 2: Вычисляем HEX
        print("📊 ПОЛЕ 2 (HEX) — Вычисление:")
        print(f"   1. Значение: {value}")
        print(f"   2. Умножаем на SCALE (100): {value} × 100 = {value * SCALE}")

        raw = int(round(value * SCALE))
        print(f"   3. Округляем до целого: {raw}")

        if not 0 <= raw <= 0xFFFFFFFF:
            raise ValueError("Значение вне диапазона")

        hex_bytes = raw.to_bytes(4, "big", signed=False)
        hex_str = f"0x{hex_bytes.hex().upper()}"
        print(f"   4. Кодируем в 4 байта BIG-ENDIAN:")
        print(f"      {raw} (10) = 0x{raw:08X} (16)")
        print(f"      Байты: {' '.join(f'{b:02X}' for b in hex_bytes)}")
        print(f"   ➜ ПОЛЕ 2 ПОКАЗЫВАЕТ: {hex_str}")
        print()

        # ПОЛЕ 3: Вычисляем CRC-16
        print("🔐 ПОЛЕ 3 (CRC-16) — Вычисление:")
        print(f"   1. Берём HEX из поля 2: {hex_str}")
        print(f"   2. Создаём 40-байтовый блок:")
        print(f"      • Байты 0-3 (4):    {' '.join(f'{b:02X}' for b in hex_bytes)}")
        print(f"      • Байты 4-7 (4):    {' '.join(f'{b:02X}' for b in hex_bytes)} (дубль)")
        print(f"      • Байты 8-39 (32):  {'00 ' * 32}(паддинг)")

        block = hex_bytes + hex_bytes + b'\x00' * 32
        print(f"   3. Блок создан: {len(block)} байт")
        print(f"   4. Вычисляем CRC-16 CCITT:")
        print(f"      • Полином: 0x1021")
        print(f"      • Инициализация: 0xFFFF")
        print(f"      • Отражение: НЕТ")
        print(f"      • Final XOR: 0x0000")

        crc = crc16_ccitt(block)
        crc_str = f"0x{crc:04X}"
        print(f"   ➜ ПОЛЕ 3 ПОКАЗЫВАЕТ: {crc_str}")
        print()

        # Итоговый результат
        print("📋 ИТОГОВЫЙ РЕЗУЛЬТАТ:")
        print(f"   ┌─────────────────────────────┐")
        print(f"   │ Поле 1 (Значение):  {value:<18} │")
        print(f"   │ Поле 2 (HEX):       {hex_str:<18} │")
        print(f"   │ Поле 3 (CRC-16):    {crc_str:<18} │")
        print(f"   └─────────────────────────────┘")
        print()

        print("✅ Это ровно то, что будет записано в EEPROM!")
        print()

        return True

    except Exception as e:
        print(f"✗ Ошибка: {e}")
        print()
        return False


def main():
    print()
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║                 ДЕМОНСТРАЦИЯ AUTO-РАСЧЁТА ПОЛЕЙ 2 И 3          ║")
    print("║                  (как подстраиваются при вводе 1)              ║")
    print("╚════════════════════════════════════════════════════════════════╝")

    test_values = [
        "9442.36",    # Основной пример
        "1234.56",    # Другое значение
        "99.99",      # Малое значение
        "50000",      # Большое значение
        "0.01",       # Очень малое
    ]

    for val in test_values:
        show_auto_calc(val)

    print("=" * 70)
    print("ИТОГИ:")
    print("=" * 70)
    print("✓ Поле 1 (Значение) — введено пользователем")
    print("✓ Поле 2 (HEX) — автоматически считается из Поля 1")
    print("✓ Поле 3 (CRC-16) — автоматически считается из Поля 1 и 2")
    print()
    print("🎯 Сигнал: Когда меняется Поле 1, мгновенно пересчитываются 2 и 3")
    print("🔗 Сигнал-слот: textChanged() → on_i2c_value_changed()")
    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
