#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CRC Storage Dump — просмотр и прямое редактирование дампа
Открытие дампа, hex-просмотр, прямая запись байт по смещению.
"""

import argparse
import struct
import sys
from pathlib import Path

SCALE = 100
BLOCK_SIZE = 0x28
CRC_SIZE = 2
INIT_CRC = 0xFFFF
POLY_CRC = 0x1021

ROW_WIDTH = 16


def crc16_ccitt(data):
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
    raw = int(round(value * SCALE))
    if not 0 <= raw <= 0xFFFFFFFF:
        raise ValueError("Диапазон: 0.00 – 42949672.95")
    return raw.to_bytes(4, "big", signed=False)


def decode_value(data: bytes) -> float:
    return int.from_bytes(data, "big", signed=False) / SCALE


def parse_offset(text) -> int:
    """'0x1C1', '1C1h', '449' → int"""
    text = str(text).strip().lower().replace("_", "")
    if text.endswith("h"):
        text = text[:-1]
        return int(text, 16)
    if text.startswith("0x"):
        return int(text, 16)
    return int(text, 10)


def parse_hex_bytes(text: str) -> bytes:
    """'00 0E 68 6C', '000E686C', '00-0e-68-6c' → bytes"""
    cleaned = "".join(c for c in text if c not in " \t\r\n,-:")
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]
    if not cleaned:
        raise ValueError("Пустая последовательность байт")
    if len(cleaned) % 2:
        raise ValueError("Нечётное количество hex-символов")
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        raise ValueError(f"Некорректные hex-данные: {text}")


def hex_dump(data: bytes, start: int = 0, length: int = None,
             base: int = 0, highlight=None) -> str:
    """
    Классический hex-дамп.
    highlight — (offset, size) абсолютного диапазона, отмечается символом '*'.
    """
    end = len(data) if length is None else min(len(data), start + length)
    hl_start, hl_end = (-1, -1)
    if highlight:
        hl_start = highlight[0]
        hl_end = highlight[0] + highlight[1]

    lines = []
    header = "Смещение  " + " ".join(f"{i:02X}" for i in range(ROW_WIDTH)) + "  ASCII"
    lines.append(header)
    lines.append("-" * len(header))

    for row in range(start - (start % ROW_WIDTH), end, ROW_WIDTH):
        chunk = data[max(row, 0):min(row + ROW_WIDTH, end)]
        if not chunk:
            continue
        pad_left = max(0, start - row) if row < start else 0

        hex_cells = []
        ascii_cells = []
        for i in range(ROW_WIDTH):
            abs_pos = row + i
            if abs_pos < start or abs_pos >= end:
                hex_cells.append("  ")
                ascii_cells.append(" ")
                continue
            byte = data[abs_pos]
            hex_cells.append(f"{byte:02X}")
            ascii_cells.append(chr(byte) if 32 <= byte < 127 else ".")

        mark = "*" if hl_start <= row + ROW_WIDTH - 1 and row < hl_end and hl_start >= 0 else " "
        lines.append(f"{base + row:08X}{mark} " + " ".join(hex_cells) + "  " + "".join(ascii_cells))

    return "\n".join(lines)


class DumpFile:
    """Дамп с прямой записью байт"""

    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.original = b""
        self.data = bytearray()
        self.writes = []

    def load(self):
        if not self.filepath.exists():
            raise FileNotFoundError(f"Файл не найден: {self.filepath}")
        self.original = self.filepath.read_bytes()
        self.data = bytearray(self.original)
        self.writes = []
        return self

    @property
    def dirty(self):
        return bytes(self.data) != self.original

    def read_bytes(self, offset: int, size: int) -> bytes:
        if offset < 0 or offset + size > len(self.data):
            raise ValueError(
                f"Диапазон 0x{offset:X}..0x{offset + size:X} вне файла "
                f"(размер 0x{len(self.data):X})"
            )
        return bytes(self.data[offset:offset + size])

    def write_bytes(self, offset: int, payload: bytes):
        """Прямая запись: меняются ровно len(payload) байт, размер файла не меняется."""
        if offset < 0:
            raise ValueError("Отрицательное смещение")
        if offset + len(payload) > len(self.data):
            raise ValueError(
                f"Запись выходит за пределы файла: 0x{offset:X} + {len(payload)} "
                f"> 0x{len(self.data):X}"
            )
        old = bytes(self.data[offset:offset + len(payload)])
        self.data[offset:offset + len(payload)] = payload
        self.writes.append({'offset': offset, 'old': old, 'new': bytes(payload)})
        return old

    def write_value(self, offset: int, value: float):
        """Записывает значение как блок 40 байт + CRC 2 байта."""
        val_bytes = encode_value(value)
        block = val_bytes + val_bytes + b"\x00" * 32
        crc = crc16_ccitt(block)
        self.write_bytes(offset, block + struct.pack(">H", crc))
        return crc

    def check_crc(self, offset: int):
        """Возвращает (значение, сохранённый CRC, вычисленный CRC)."""
        block = self.read_bytes(offset, BLOCK_SIZE)
        stored = struct.unpack(">H", self.read_bytes(offset + BLOCK_SIZE, CRC_SIZE))[0]
        return decode_value(block[:4]), stored, crc16_ccitt(block)

    def find(self, pattern: bytes):
        offsets = []
        pos = self.data.find(pattern)
        while pos != -1:
            offsets.append(pos)
            pos = self.data.find(pattern, pos + 1)
        return offsets

    def diff(self):
        """Список изменившихся байт: [(offset, old, new), ...]"""
        return [(i, self.original[i], self.data[i])
                for i in range(min(len(self.original), len(self.data)))
                if self.original[i] != self.data[i]]

    def save(self, backup=True):
        if backup:
            bak = self.filepath.with_suffix(self.filepath.suffix + ".bak")
            bak.write_bytes(self.original)
        self.filepath.write_bytes(bytes(self.data))
        self.original = bytes(self.data)
        return self.filepath


# ═══════════════════════════════════════════════════════════════════════════
#  Интерактивный режим
# ═══════════════════════════════════════════════════════════════════════════

INTERACTIVE_HELP = """
Команды дамп-редактора:
  d [смещение] [длина]     Показать дамп (по умолчанию с 0, 256 байт)
  w <смещение> <hex>       Прямая запись байт  (w 0x1C1 00 0E 68 6C)
  v <смещение> <значение>  Записать значение + CRC (v 0x1C1 9442.36)
  c <смещение>             Проверить CRC блока по смещению
  f <hex>                  Найти последовательность байт
  diff                     Показать все изменённые байты
  undo                     Отменить последнюю запись
  save                     Сохранить (создаётся .bak)
  q                        Выход
"""


def interactive(dumpfile: DumpFile):
    print(f"\n✓ Дамп открыт: {dumpfile.filepath} ({len(dumpfile.data)} байт)")
    print(INTERACTIVE_HELP)

    while True:
        try:
            line = input("dump> ").strip()
        except EOFError:
            print()
            break
        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        try:
            if cmd in ("q", "quit", "exit"):
                if dumpfile.dirty:
                    ans = input("Есть несохранённые изменения. Выйти? (y/n): ").strip().lower()
                    if ans != "y":
                        continue
                break

            elif cmd in ("h", "help", "?"):
                print(INTERACTIVE_HELP)

            elif cmd == "d":
                off = parse_offset(parts[1]) if len(parts) > 1 else 0
                length = parse_offset(parts[2]) if len(parts) > 2 else 256
                print(hex_dump(bytes(dumpfile.data), off, length))

            elif cmd == "w":
                off = parse_offset(parts[1])
                payload = parse_hex_bytes(" ".join(parts[2:]))
                old = dumpfile.write_bytes(off, payload)
                print(f"✓ 0x{off:06X}: {old.hex(' ').upper()} → {payload.hex(' ').upper()} "
                      f"({len(payload)} байт)")

            elif cmd == "v":
                off = parse_offset(parts[1])
                value = float(parts[2].replace(",", "."))
                crc = dumpfile.write_value(off, value)
                print(f"✓ 0x{off:06X}: значение {value:.2f}, CRC 0x{crc:04X} "
                      f"({BLOCK_SIZE + CRC_SIZE} байт)")

            elif cmd == "c":
                off = parse_offset(parts[1])
                value, stored, calc = dumpfile.check_crc(off)
                ok = "✓ OK" if stored == calc else "✗ НЕ СОВПАДАЕТ"
                print(f"0x{off:06X}: {value:.2f} | сохранён 0x{stored:04X} | "
                      f"вычислен 0x{calc:04X} | {ok}")

            elif cmd == "f":
                pattern = parse_hex_bytes(" ".join(parts[1:]))
                hits = dumpfile.find(pattern)
                if hits:
                    print(f"Найдено {len(hits)}: " +
                          ", ".join(f"0x{h:06X}" for h in hits[:50]))
                else:
                    print("Не найдено")

            elif cmd == "diff":
                changes = dumpfile.diff()
                if not changes:
                    print("Изменений нет")
                else:
                    print(f"Изменено байт: {len(changes)}")
                    for off, old, new in changes[:64]:
                        print(f"  0x{off:06X}: {old:02X} → {new:02X}")
                    if len(changes) > 64:
                        print(f"  ... ещё {len(changes) - 64}")

            elif cmd == "undo":
                if not dumpfile.writes:
                    print("Нечего отменять")
                else:
                    last = dumpfile.writes.pop()
                    dumpfile.data[last['offset']:last['offset'] + len(last['old'])] = last['old']
                    print(f"✓ Отменена запись на 0x{last['offset']:06X}")

            elif cmd == "save":
                path = dumpfile.save()
                print(f"✓ Сохранено: {path} (резервная копия: {path.name}.bak)")

            else:
                print(f"Неизвестная команда: {cmd}. Введите 'h' для справки.")

        except IndexError:
            print("✗ Недостаточно аргументов. Введите 'h' для справки.")
        except Exception as e:
            print(f"✗ Ошибка: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        prog="crc_storage_dump",
        description="Просмотр и прямое редактирование дампа",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_dump = sub.add_parser("dump", help="Показать hex-дамп")
    p_dump.add_argument("file")
    p_dump.add_argument("-o", "--offset", default="0")
    p_dump.add_argument("-n", "--length", default="256")

    p_write = sub.add_parser("write", help="Прямая запись байт по смещению")
    p_write.add_argument("file")
    p_write.add_argument("offset")
    p_write.add_argument("hex", nargs="+", help="Байты: 00 0E 68 6C")
    p_write.add_argument("--no-backup", action="store_true")

    p_val = sub.add_parser("value", help="Записать значение + CRC по смещению")
    p_val.add_argument("file")
    p_val.add_argument("offset")
    p_val.add_argument("value", type=float)
    p_val.add_argument("--no-backup", action="store_true")

    p_check = sub.add_parser("check", help="Проверить CRC блока")
    p_check.add_argument("file")
    p_check.add_argument("offset")

    p_find = sub.add_parser("find", help="Найти байты в дампе")
    p_find.add_argument("file")
    p_find.add_argument("hex", nargs="+")

    p_edit = sub.add_parser("edit", help="Интерактивный дамп-редактор")
    p_edit.add_argument("file")

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return 0

    try:
        df = DumpFile(args.file).load()

        if args.cmd == "dump":
            print(f"Файл: {df.filepath} ({len(df.data)} байт)\n")
            print(hex_dump(bytes(df.data), parse_offset(args.offset),
                           parse_offset(args.length)))

        elif args.cmd == "write":
            off = parse_offset(args.offset)
            payload = parse_hex_bytes(" ".join(args.hex))
            old = df.write_bytes(off, payload)
            df.save(backup=not args.no_backup)
            print(f"✓ 0x{off:06X}: {old.hex(' ').upper()} → {payload.hex(' ').upper()}")
            print(f"✓ Изменено {len(payload)} байт, сохранено: {df.filepath}")

        elif args.cmd == "value":
            off = parse_offset(args.offset)
            crc = df.write_value(off, args.value)
            df.save(backup=not args.no_backup)
            print(f"✓ 0x{off:06X}: {args.value:.2f}, CRC 0x{crc:04X}")
            print(f"✓ Изменено {BLOCK_SIZE + CRC_SIZE} байт, сохранено: {df.filepath}")

        elif args.cmd == "check":
            off = parse_offset(args.offset)
            value, stored, calc = df.check_crc(off)
            ok = stored == calc
            print(f"0x{off:06X}: {value:.2f}")
            print(f"  CRC сохранён:  0x{stored:04X}")
            print(f"  CRC вычислен:  0x{calc:04X}")
            print(f"  {'✓ Совпадает' if ok else '✗ НЕ совпадает'}")
            return 0 if ok else 1

        elif args.cmd == "find":
            pattern = parse_hex_bytes(" ".join(args.hex))
            hits = df.find(pattern)
            if not hits:
                print("Не найдено")
                return 1
            print(f"Найдено {len(hits)}:")
            for h in hits:
                print(f"  0x{h:06X}")

        elif args.cmd == "edit":
            interactive(df)

        return 0

    except Exception as e:
        print(f"✗ Ошибка: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n✗ Прервано")
        sys.exit(1)
