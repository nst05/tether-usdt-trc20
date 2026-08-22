#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CRC Storage CLI — утилита командной строки для работы с файлами
Работает с CRC-16 CCITT и fixed-point значениями (×100, big-endian)
"""

import struct
import sys
from pathlib import Path
from argparse import ArgumentParser

# ═══════════════════════════════════════════════════════════════════════════
#  Константы и функции
# ═══════════════════════════════════════════════════════════════════════════

SCALE = 100
BLOCK_SIZE = 0x28  # 40 байт
CRC_SIZE = 2
VALUE_SIZE = 4

INIT_CRC = 0xFFFF
POLY_CRC = 0x1021


def crc16_ccitt(data, init=INIT_CRC, poly=POLY_CRC):
    """CRC-16 CCITT"""
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc <<= 1
            if crc & 0x10000:
                crc ^= poly
            crc &= 0xFFFF
    return crc


def encode_value(value: float) -> bytes:
    """Кодирование значения в fixed-point big-endian"""
    raw = int(round(value * SCALE))
    if not 0 <= raw <= 0xFFFFFFFF:
        raise ValueError("Значение слишком большое (макс. 42949672.95).")
    return raw.to_bytes(4, "big", signed=False)


def decode_value(data: bytes) -> float:
    """Декодирование значения из fixed-point big-endian"""
    if len(data) != 4:
        raise ValueError("Неверная длина данных.")
    return int.from_bytes(data, "big", signed=False) / SCALE


def make_block(value: float) -> tuple:
    """Создаёт блок (40 байт) и вычисляет CRC"""
    val_bytes = encode_value(value)
    block = val_bytes + val_bytes + b'\x00' * 32
    crc = crc16_ccitt(block)
    return block, crc


# ═══════════════════════════════════════════════════════════════════════════
#  Работа с файлами
# ═══════════════════════════════════════════════════════════════════════════

class StorageFile:
    def __init__(self, filepath):
        self.path = Path(filepath)
        self.data = None
        self.values = []

    def load(self):
        """Загружает файл"""
        if not self.path.exists():
            raise FileNotFoundError(f"Файл не найден: {self.path}")

        with open(self.path, 'rb') as f:
            self.data = bytearray(f.read())

        self._scan()
        return len(self.data)

    def _scan(self):
        """Сканирует значения в файле"""
        self.values = []
        data = bytes(self.data)

        pos = 0
        while pos < len(data) - BLOCK_SIZE - CRC_SIZE:
            val1 = data[pos:pos+4]
            val2 = data[pos+4:pos+8]
            zeros = data[pos+8:pos+12]

            if val1 == val2 and zeros == b'\x00\x00\x00\x00':
                try:
                    block = data[pos:pos+BLOCK_SIZE]
                    crc_pos = pos + BLOCK_SIZE

                    if crc_pos + CRC_SIZE <= len(data):
                        stored_crc = struct.unpack('>H', data[crc_pos:crc_pos+2])[0]
                        calculated_crc = crc16_ccitt(block)

                        if stored_crc == calculated_crc:
                            value = decode_value(val1)
                            self.values.append({
                                'pos': pos,
                                'value': value,
                                'crc': stored_crc,
                                'valid': True
                            })
                            pos += BLOCK_SIZE + CRC_SIZE
                            continue
                except Exception:
                    pass

            pos += 1

    def write_value(self, position: int, new_value: float):
        """Записывает значение в позицию"""
        if position < 0 or position + BLOCK_SIZE + CRC_SIZE > len(self.data):
            raise ValueError("Позиция выходит за пределы файла.")

        block, crc = make_block(new_value)
        self.data[position:position+BLOCK_SIZE] = block
        self.data[position+BLOCK_SIZE:position+BLOCK_SIZE+CRC_SIZE] = struct.pack('>H', crc)

    def save(self):
        """Сохраняет файл"""
        backup = self.path.with_suffix('.bak')
        self.path.rename(backup)

        try:
            with open(self.path, 'wb') as f:
                f.write(self.data)
            print(f"✓ Файл сохранён: {self.path}")
            print(f"  Резервная копия: {backup}")
        except Exception as e:
            backup.rename(self.path)
            raise e

    def get_value(self, position: int) -> float:
        """Читает значение с позиции"""
        if position < 0 or position + VALUE_SIZE > len(self.data):
            raise ValueError("Позиция выходит за пределы файла.")

        val_bytes = self.data[position:position+VALUE_SIZE]
        return decode_value(val_bytes)


# ═══════════════════════════════════════════════════════════════════════════
#  Команды
# ═══════════════════════════════════════════════════════════════════════════

def cmd_list(filepath):
    """Показывает все значения в файле"""
    storage = StorageFile(filepath)
    size = storage.load()

    print(f"\n📄 Файл: {filepath}")
    print(f"   Размер: {size} байт ({size/1024:.1f} КБ)")
    print(f"\n{'Позиция':<12} {'Значение':<15} {'CRC-16':<12} {'Статус'}")
    print("-" * 60)

    if not storage.values:
        print("Значения не найдены.")
        return

    for item in storage.values:
        status = "✓ OK" if item['valid'] else "✗ ОШИБКА"
        print(f"0x{item['pos']:08X}  {item['value']:13.2f}  0x{item['crc']:04X}    {status}")

    print(f"\nВсего: {len(storage.values)} значений")


def cmd_get(filepath, position):
    """Читает значение с позиции"""
    storage = StorageFile(filepath)
    storage.load()

    try:
        pos = int(position, 0)  # поддерживает 0x префикс
        value = storage.get_value(pos)
        print(f"✓ Позиция 0x{pos:04X}: {value:.2f}")
    except Exception as e:
        print(f"✗ Ошибка: {e}")


def cmd_set(filepath, position, value):
    """Записывает новое значение"""
    storage = StorageFile(filepath)
    storage.load()

    try:
        pos = int(position, 0)
        new_value = float(value)

        old_value = storage.get_value(pos)
        storage.write_value(pos, new_value)

        # Обновляем список
        storage._scan()

        print(f"✓ Позиция 0x{pos:04X}:")
        print(f"  Старое значение: {old_value:.2f}")
        print(f"  Новое значение: {new_value:.2f}")

        # Показываем новый CRC
        for item in storage.values:
            if item['pos'] == pos:
                print(f"  Новый CRC-16: 0x{item['crc']:04X}")
                break

        storage.save()
    except Exception as e:
        print(f"✗ Ошибка: {e}")


def cmd_info():
    """Показывает информацию об алгоритме"""
    info = """
╔════════════════════════════════════════════════════════════════════╗
║           CRC-16 CCITT Storage Format Reference                   ║
╚════════════════════════════════════════════════════════════════════╝

АЛГОРИТМ CRC:
  Тип:           CRC-16 CCITT
  Полином:       0x1021
  Инициализ.:    0xFFFF
  Вход отраж.:   НЕТ
  Выход отраж.:  НЕТ
  Final XOR:     0x0000

ПРЕДСТАВЛЕНИЕ ЗНАЧЕНИЙ:
  Формат:        Fixed-Point
  Масштаб:       × 100 (умножаем на 100)
  Порядок:       Big-Endian (старший байт первым)
  Размер:        4 байта (32-бит)
  Диапазон:      0.00 – 42949672.95

СТРУКТУРА БЛОКА (40 байт):
  Байты 0–3:     Значение (4 байта, big-endian)
  Байты 4–7:     Дубль значения (резервная копия)
  Байты 8–39:    Паддинг нулями (32 байта заполнения)

CRC ХРАНЕНИЕ:
  Позиция:       После 40-байтового блока
  Размер:        2 байта (16-бит, big-endian)
  Вычисл.:       Для полного 40-байтового блока

ПРИМЕРЫ:

  Значение 9442.36:
    Целое число:   944236 (decimal)
    HEX:           0x000E686C
    Bytes (BE):    00 0E 68 6C
    CRC-16:        0xAC55

  Значение 9440.38:
    Целое число:   944038 (decimal)
    HEX:           0x000E67A6
    Bytes (BE):    00 0E 67 A6
    CRC-16:        0x8748

  Значение 12.34:
    Целое число:   1234 (decimal)
    HEX:           0x000004D2
    Bytes (BE):    00 00 04 D2
    CRC-16:        0xC7D9

ИСПОЛЬЗОВАНИЕ:

  Списать все значения:
    python3 crc_storage_cli.py list file.bin

  Прочитать значение на позиции 0x01C1:
    python3 crc_storage_cli.py get file.bin 0x01C1

  Написать значение на позиции 0x01C1:
    python3 crc_storage_cli.py set file.bin 0x01C1 9999.99

  Показать эту справку:
    python3 crc_storage_cli.py info
    """
    print(info)


# ═══════════════════════════════════════════════════════════════════════════
#  Главная функция
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = ArgumentParser(
        prog='crc_storage_cli',
        description='Работа с файлами CRC-16 CCITT Storage'
    )

    subparsers = parser.add_subparsers(dest='command', help='Команда')

    # list
    list_parser = subparsers.add_parser('list', help='Показать все значения')
    list_parser.add_argument('file', help='Файл')

    # get
    get_parser = subparsers.add_parser('get', help='Читать значение')
    get_parser.add_argument('file', help='Файл')
    get_parser.add_argument('position', help='Позиция (0xXXXX или десятичное)')

    # set
    set_parser = subparsers.add_parser('set', help='Записать значение')
    set_parser.add_argument('file', help='Файл')
    set_parser.add_argument('position', help='Позиция (0xXXXX или десятичное)')
    set_parser.add_argument('value', help='Новое значение (например 9442.36)')

    # info
    subparsers.add_parser('info', help='Справка об алгоритме')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == 'list':
            cmd_list(args.file)
        elif args.command == 'get':
            cmd_get(args.file, args.position)
        elif args.command == 'set':
            cmd_set(args.file, args.position, args.value)
        elif args.command == 'info':
            cmd_info()
        return 0
    except Exception as e:
        print(f"✗ Ошибка: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
