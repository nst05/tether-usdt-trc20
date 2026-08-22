#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CRC Storage I2C Writer — запись значений в EEPROM 24C256 с помощью CH341 программатора
Логика записи адаптирована из MT_Writer для работы с CRC-16 CCITT и BIG-ENDIAN кодированием.
"""

import gc
import time
import random
import struct
from pathlib import Path

try:
    from i2cpy import I2C
except ImportError:
    I2C = None

# ═══════════════════════════════════════════════════════════════════════════
#  Константы (BIG-ENDIAN для CRC Storage)
# ═══════════════════════════════════════════════════════════════════════════

SCALE = 100
BLOCK_SIZE = 0x28  # 40 bytes
CRC_SIZE = 2
VALUE_SIZE = 4
INIT_CRC = 0xFFFF
POLY_CRC = 0x1021

EEPROM_SIZE = 2048  # 24C256: 2 КБ, 8 блоков по 256 байт
BASE_I2C_ADDRESS = 0x50


def crc16_ccitt(data):
    """CRC-16 CCITT: poly=0x1021, init=0xFFFF, no reflection, xor_out=0x0000"""
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
    """Значение → fixed-point BIG-ENDIAN"""
    raw = int(round(value * SCALE))
    if not 0 <= raw <= 0xFFFFFFFF:
        raise ValueError(f"Диапазон: 0.00 – 42949672.95")
    return raw.to_bytes(4, "big", signed=False)


def decode_value(data: bytes) -> float:
    """Fixed-point BIG-ENDIAN → значение"""
    if len(data) != 4:
        raise ValueError("Неверная длина данных")
    return int.from_bytes(data, "big", signed=False) / SCALE


# ═══════════════════════════════════════════════════════════════════════════
#  I2C писатель
# ═══════════════════════════════════════════════════════════════════════════

class I2CWriter:
    """
    Запись значений в EEPROM 24C256 с проверкой.
    Структура блока:
      - Байты 0-3: значение (BIG-ENDIAN)
      - Байты 4-7: дубль (резервная копия)
      - Байты 8-39: паддинг нулями
      - Байты 40-41: CRC-16 CCITT (BIG-ENDIAN, 2 байта)
    """

    def __init__(self, offset: int = 0x0000):
        """
        offset: начальное смещение в EEPROM для блока (по умолчанию 0x0000)
        """
        self.offset = offset
        self.i2c = None

    def open_programmer(self):
        """Открыть соединение с CH341 программатором"""
        if I2C is None:
            raise RuntimeError("Не установлена библиотека i2cpy.")

        self.close_programmer()
        self.i2c = I2C(driver="ch341")

    def close_programmer(self):
        """Закрыть соединение с программатором"""
        obj = self.i2c
        self.i2c = None

        if obj is not None:
            for method_name in ("close", "deinit", "disconnect"):
                method = getattr(obj, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
                    break

        del obj
        gc.collect()
        time.sleep(0.08)

    @staticmethod
    def split_address(address: int) -> tuple:
        """
        Разбить адрес на блок и адрес в блоке (для 24C256).
        24C256: 8 блоков по 256 байт, адреса 0x50-0x57
        """
        if not 0 <= address < EEPROM_SIZE:
            raise ValueError(f"Адрес выходит за пределы 24C256 (0x0000-0x07FF).")
        block = (address >> 8) & 0x07
        device_address = BASE_I2C_ADDRESS | block
        memory_address = address & 0xFF
        return device_address, memory_address

    def read_bytes(self, address: int, length: int) -> bytes:
        """Прочитать length байт с адреса address"""
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")

        result = bytearray()
        current = address
        remaining = length

        while remaining > 0:
            dev_addr, mem_addr = self.split_address(current)
            chunk_len = min(remaining, 0x100 - mem_addr)
            chunk = self.i2c.readfrom_mem(dev_addr, mem_addr, chunk_len, addrsize=8)
            result.extend(bytes(chunk))
            current += chunk_len
            remaining -= chunk_len

        return bytes(result)

    def write_bytes(self, address: int, payload: bytes):
        """Записать байты payload по адресу address"""
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")

        dev_addr, mem_addr = self.split_address(address)
        self.i2c.writeto_mem(dev_addr, mem_addr, bytes(payload), addrsize=8)

    def make_block(self, value: float) -> tuple:
        """
        Создать 42-байтовый блок (40 байт + 2 CRC) из значения.
        Возвращает (block_data, crc_value)
        """
        val_bytes = encode_value(value)
        block = val_bytes + val_bytes + b"\x00" * 32
        crc = crc16_ccitt(block)
        return block + struct.pack(">H", crc), crc

    def parse_value(self, text: str) -> float:
        """
        Преобразовать введённое значение: добавить случайную дробную часть 01-99.
        Например: "3456" → 3456.XX (где XX = 01..99)
        """
        text = str(text).strip().replace(",", ".")
        if not text:
            raise ValueError("Введите целую часть.")

        base_value = float(text)
        if base_value < 0:
            raise ValueError("Значение не может быть отрицательным.")

        integer_part = int(base_value)
        fraction = random.randint(1, 99)
        value = integer_part + fraction / 100.0
        encode_value(value)

        return value

    def write_and_verify(self, value: str, progress_callback=None) -> dict:
        """
        Полный цикл записи и проверки:
        1. Открыть программатор
        2. Прочитать текущее значение
        3. Записать новое значение
        4. Закрыть программатор
        5. Ожидать цикл записи EEPROM
        6. Переоткрыть программатор
        7. Проверить значение (10 попыток)
        8. Закрыть программатор

        Возвращает словарь:
        {
            'success': bool,
            'message': str,
            'before': float or None,
            'after': float or None,
            'crc': int or None,
        }
        """
        result = {
            'success': False,
            'message': '',
            'before': None,
            'after': None,
            'crc': None,
        }

        def progress(percent: int, text: str = ''):
            if progress_callback:
                progress_callback(percent, text)

        try:
            progress(5, "Парсинг значения...")
            parsed_value = self.parse_value(value)

            progress(20, "Открытие программатора...")
            self.open_programmer()

            progress(30, "Чтение текущего значения...")
            before_bytes = self.read_bytes(self.offset, VALUE_SIZE)
            result['before'] = decode_value(before_bytes)

            progress(45, "Запись нового значения...")
            block_data, crc = self.make_block(parsed_value)
            self.write_bytes(self.offset, block_data)

            progress(60, "Закрытие программатора...")
            self.close_programmer()

            progress(65, "Ожидание цикла записи EEPROM (0.15s)...")
            time.sleep(0.15)

            progress(80, "Переоткрытие программатора...")
            self.open_programmer()

            progress(85, "Проверка записанного значения...")
            actual = None
            for attempt in range(10):
                try:
                    actual = self.read_bytes(self.offset, BLOCK_SIZE + CRC_SIZE)
                    actual_value = decode_value(actual[:4])
                    actual_crc = struct.unpack(">H", actual[BLOCK_SIZE:BLOCK_SIZE+CRC_SIZE])[0]

                    if actual[:4] == encode_value(parsed_value):
                        result['after'] = actual_value
                        result['crc'] = actual_crc
                        break
                except Exception:
                    pass

                if attempt < 9:
                    time.sleep(0.05)

            if result['after'] is None:
                raise RuntimeError("Проверка записи не пройдена (10 попыток).")

            result['success'] = True
            result['message'] = f"Успех: записано {result['after']:.2f} (CRC: 0x{result['crc']:04X})"

        except Exception as exc:
            result['message'] = f"Ошибка: {exc}"

        finally:
            progress(100, result['message'])
            self.close_programmer()

        return result
