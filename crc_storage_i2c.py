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

BASE_I2C_ADDRESS = 0x50

# ── Профили микросхем ──────────────────────────────────────────────────────
# 24C256 — 32 КБ, ОДИН адрес на шине (0x50), ДВУХБАЙТОВЫЙ адрес памяти,
#          страница записи 64 байта.
# 24C16  — 2 КБ, ВОСЕМЬ адресов (0x50..0x57), однобайтовый адрес памяти,
#          страница записи 16 байт. Именно эту схему использует MT_Writer.
CHIPS = {
    "24C256": {"size": 32768, "addrsize": 16, "page": 64,  "blocks": False},
    "24C128": {"size": 16384, "addrsize": 16, "page": 64,  "blocks": False},
    "24C64":  {"size": 8192,  "addrsize": 16, "page": 32,  "blocks": False},
    "24C32":  {"size": 4096,  "addrsize": 16, "page": 32,  "blocks": False},
    "24C16":  {"size": 2048,  "addrsize": 8,  "page": 16,  "blocks": True},
    "24C08":  {"size": 1024,  "addrsize": 8,  "page": 16,  "blocks": True},
}

DEFAULT_CHIP = "24C256"
EEPROM_SIZE = CHIPS[DEFAULT_CHIP]["size"]

# Внутренний цикл записи страницы EEPROM (tWR по даташиту ≈ 5 мс).
PAGE_WRITE_DELAY = 0.01


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

    def __init__(self, offset: int = 0x01C1, chip: str = DEFAULT_CHIP,
                 device_index: int = 0):
        """
        offset:       смещение блока в EEPROM (по умолчанию 0x01C1 — где
                      реально лежит запись в дампе)
        chip:         тип микросхемы, см. CHIPS
        device_index: биты A2..A0 на ножках микросхемы (обычно 0)
        """
        if chip not in CHIPS:
            raise ValueError(f"Неизвестная микросхема: {chip}")

        self.offset = offset
        self.chip = chip
        self.profile = CHIPS[chip]
        self.device_index = device_index & 0x07
        self.i2c = None

    @property
    def size(self) -> int:
        return self.profile["size"]

    @property
    def addrsize(self) -> int:
        return self.profile["addrsize"]

    @property
    def page_size(self) -> int:
        return self.profile["page"]

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

    def split_address(self, address: int) -> tuple:
        """
        Преобразовать линейный адрес в пару (адрес устройства, адрес памяти).

        24C256/128/64/32 — один адрес на шине, 16-битный адрес памяти:
            (0x50, address)
        24C16/08 — старшие биты адреса едут в адрес устройства:
            (0x50 | block, address & 0xFF)
        """
        if not 0 <= address < self.size:
            raise ValueError(
                f"Адрес 0x{address:04X} вне пределов {self.chip} "
                f"(0x0000-0x{self.size - 1:04X})."
            )

        if self.profile["blocks"]:
            block = (address >> 8) & 0x07
            return BASE_I2C_ADDRESS | block, address & 0xFF

        return BASE_I2C_ADDRESS | self.device_index, address

    def _chunk_limit(self, address: int) -> int:
        """Сколько байт можно прочитать одной транзакцией с этого адреса."""
        if self.profile["blocks"]:
            return 0x100 - (address & 0xFF)
        return self.size - address

    def read_bytes(self, address: int, length: int) -> bytes:
        """Прочитать length байт с адреса address"""
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")

        if address + length > self.size:
            raise ValueError(
                f"Чтение 0x{address:04X}+{length} выходит за пределы {self.chip}."
            )

        result = bytearray()
        current = address
        remaining = length

        while remaining > 0:
            dev_addr, mem_addr = self.split_address(current)
            chunk_len = min(remaining, self._chunk_limit(current))
            chunk = self.i2c.readfrom_mem(dev_addr, mem_addr, chunk_len,
                                          addrsize=self.addrsize)
            result.extend(bytes(chunk))
            current += chunk_len
            remaining -= chunk_len

        return bytes(result)

    def write_bytes(self, address: int, payload: bytes, log=None):
        """
        Записать payload по адресу address с разбивкой по страницам.

        КРИТИЧНО: EEPROM не умеет писать через границу страницы — адрес
        заворачивается внутри страницы и затирает уже записанные байты.
        Поэтому пишем постранично и ждём внутренний цикл записи (tWR).
        """
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")

        payload = bytes(payload)
        if address + len(payload) > self.size:
            raise ValueError(
                f"Запись 0x{address:04X}+{len(payload)} выходит за пределы {self.chip}."
            )

        page = self.page_size
        current = address
        pos = 0

        while pos < len(payload):
            room = page - (current % page)
            chunk = payload[pos:pos + min(room, len(payload) - pos)]
            dev_addr, mem_addr = self.split_address(current)
            self.i2c.writeto_mem(dev_addr, mem_addr, chunk,
                                 addrsize=self.addrsize)
            if log:
                log(f"  страница 0x{current:04X}: {len(chunk)} байт "
                    f"(dev 0x{dev_addr:02X}, mem 0x{mem_addr:04X})")
            time.sleep(PAGE_WRITE_DELAY)
            current += len(chunk)
            pos += len(chunk)

    def scan_devices(self) -> list:
        """
        Найти адреса, которые отвечают (ACK) на шине, в диапазоне 0x50-0x57.

        Это надёжный различитель семейств, не зависящий от содержимого:
          • 24C16/08 занимают НЕСКОЛЬКО адресов — старшие биты адреса памяти
            передаются через адрес устройства;
          • 24C256/128/64/32 занимают ОДИН адрес — адрес памяти 16-битный,
            а 0x51..0x57 задаются ножками A0..A2 и обычно молчат.
        """
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")

        found = []
        for dev in range(BASE_I2C_ADDRESS, BASE_I2C_ADDRESS + 8):
            for addrsize in (16, 8):
                try:
                    self.i2c.readfrom_mem(dev, 0, 1, addrsize=addrsize)
                    found.append(dev)
                    break
                except Exception:
                    continue
        return found

    def probe(self) -> dict:
        """
        Определить реальную схему адресации микросхемы.

        Два независимых признака:
          1. Сколько адресов отвечает на шине (главный, см. scan_devices).
          2. Стабильность чтения: чип, опрошенный неверным числом адресных
             байт, читает с «плавающего» адреса и выдаёт разное. Признак
             вспомогательный — на пустой памяти (сплошные FF) он не работает.

        Возвращает {'devices': list, '8': bytes|None, '16': bytes|None,
                    'stable8': bool, 'stable16': bool, 'varied8': bool,
                    'varied16': bool, 'recommend': str|None}
        """
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")

        report = {'devices': [], '8': None, '16': None,
                  'stable8': False, 'stable16': False,
                  'varied8': False, 'varied16': False, 'recommend': None}

        report['devices'] = self.scan_devices()

        for bits in (8, 16):
            reads = []
            for _ in range(3):
                try:
                    dev = BASE_I2C_ADDRESS | (self.device_index if bits == 16
                                              else ((self.offset >> 8) & 0x07))
                    mem = self.offset if bits == 16 else (self.offset & 0xFF)
                    reads.append(bytes(self.i2c.readfrom_mem(
                        dev, mem, 8, addrsize=bits)))
                except Exception:
                    reads.append(None)
                time.sleep(0.02)

            first = reads[0]
            report[str(bits)] = first
            report[f'stable{bits}'] = (
                first is not None and all(r == first for r in reads)
            )
            # Содержательный ответ (не сплошные FF/00) — значит признаку
            # стабильности можно верить.
            report[f'varied{bits}'] = (
                first is not None and len(set(first)) > 1
            )

        # Главный признак: число откликнувшихся адресов.
        if len(report['devices']) > 1:
            report['recommend'] = "24C16"
        elif len(report['devices']) == 1:
            report['recommend'] = "24C256"

        # Уточнение по стабильности — только если данные содержательные.
        if report['varied16'] and report['stable16'] and not report['stable8']:
            report['recommend'] = "24C256"
        elif report['varied8'] and report['stable8'] and not report['stable16']:
            report['recommend'] = "24C16"

        return report

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

    def write_and_verify(self, value: str, progress_callback=None, debug=False) -> dict:
        """
        Полный цикл записи и проверки с опциональным логированием:
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
            'debug': str (если debug=True)
        }
        """
        result = {
            'success': False,
            'message': '',
            'before': None,
            'after': None,
            'crc': None,
            'debug': '',
        }

        debug_log = []

        def progress(percent: int, text: str = ''):
            if progress_callback:
                progress_callback(percent, text)

        def log_debug(text):
            if debug:
                debug_log.append(text)

        try:
            progress(5, "Парсинг значения...")
            parsed_value = self.parse_value(value)
            log_debug(f"Распарсено значение: {parsed_value}")

            progress(20, "Открытие программатора...")
            self.open_programmer()
            log_debug(
                f"Программатор открыт | чип {self.chip}: {self.size} байт, "
                f"адрес памяти {self.addrsize} бит, страница {self.page_size} байт, "
                f"смещение блока 0x{self.offset:04X}"
            )

            progress(30, "Чтение текущего значения...")
            before_bytes = self.read_bytes(self.offset, VALUE_SIZE)
            result['before'] = decode_value(before_bytes)
            log_debug(f"Текущее значение: {result['before']:.2f} (байты: {before_bytes.hex().upper()})")

            progress(45, "Запись нового значения...")
            block_data, crc = self.make_block(parsed_value)
            log_debug(f"Блок создан: {len(block_data)} байт, CRC: 0x{crc:04X}")
            log_debug(f"Данные: {block_data[:8].hex().upper()}... (первые 8 байт)")
            self.write_bytes(self.offset, block_data, log=log_debug)
            log_debug(f"Записано по смещению 0x{self.offset:04X}")

            progress(60, "Закрытие программатора...")
            self.close_programmer()
            log_debug("Программатор закрыт")

            progress(65, "Ожидание цикла записи EEPROM (0.15s)...")
            time.sleep(0.15)
            log_debug("Ожидание завершено")

            progress(80, "Переоткрытие программатора...")
            self.open_programmer()
            log_debug("Программатор переоткрыт")

            progress(85, "Проверка записанного значения...")
            actual = None
            for attempt in range(10):
                try:
                    actual = self.read_bytes(self.offset, BLOCK_SIZE + CRC_SIZE)
                    actual_value = decode_value(actual[:4])
                    actual_crc = struct.unpack(">H", actual[BLOCK_SIZE:BLOCK_SIZE+CRC_SIZE])[0]

                    log_debug(f"Попытка {attempt+1}: Прочитано {actual_value:.2f}, CRC: 0x{actual_crc:04X}")
                    log_debug(f"  Байты: {actual[:8].hex().upper()}... (первые 8 байт)")

                    if actual[:4] == encode_value(parsed_value):
                        result['after'] = actual_value
                        result['crc'] = actual_crc
                        log_debug(f"✓ Проверка пройдена на попытке {attempt+1}")
                        break
                except Exception as e:
                    log_debug(f"Попытка {attempt+1}: Ошибка чтения - {e}")

                if attempt < 9:
                    time.sleep(0.05)

            if result['after'] is None:
                log_debug("✗ Все 10 попыток исчерпаны, проверка не пройдена")
                log_debug(f"Ожидали: {encode_value(parsed_value).hex().upper()}")
                log_debug(f"Прочитали: {actual[:4].hex().upper() if actual else 'ОШИБКА ЧТЕНИЯ'}")
                raise RuntimeError("Проверка записи не пройдена (10 попыток).")

            result['success'] = True
            result['message'] = f"Успех: записано {result['after']:.2f} (CRC: 0x{result['crc']:04X})"

        except Exception as exc:
            log_debug(f"ИСКЛЮЧЕНИЕ: {exc}")
            result['message'] = f"Ошибка: {exc}"

        finally:
            progress(100, result['message'])
            self.close_programmer()
            if debug:
                result['debug'] = '\n'.join(debug_log)

        return result
