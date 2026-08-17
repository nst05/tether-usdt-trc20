"""Разбор Intel HEX: загрузка образа памяти, карта покрытия, базовая статистика."""
from __future__ import annotations

import sys
from typing import Dict, List, Tuple


class Image:
    """Разреженный образ памяти: адрес -> байт."""

    def __init__(self) -> None:
        self.mem: Dict[int, int] = {}
        self.start_addr: int | None = None

    def __contains__(self, addr: int) -> bool:
        return addr in self.mem

    def byte(self, addr: int) -> int:
        return self.mem[addr]

    def word(self, addr: int) -> int:
        """16-битное слово, little-endian (порядок MSP430)."""
        return self.mem[addr] | (self.mem[addr + 1] << 8)

    def has_range(self, addr: int, n: int) -> bool:
        return all(a in self.mem for a in range(addr, addr + n))

    def read(self, addr: int, n: int) -> bytes:
        return bytes(self.mem.get(a, 0xFF) for a in range(addr, addr + n))

    def segments(self, gap: int = 1) -> List[Tuple[int, int]]:
        """Непрерывные области как список (начало, конец включительно)."""
        if not self.mem:
            return []
        addrs = sorted(self.mem)
        segs = []
        start = prev = addrs[0]
        for a in addrs[1:]:
            if a - prev > gap:
                segs.append((start, prev))
                start = a
            prev = a
        segs.append((start, prev))
        return segs


def load(path: str) -> Image:
    img = Image()
    ext_lin = 0
    ext_seg = 0
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise ValueError(f"строка {lineno}: нет маркера ':'")
            data = bytes.fromhex(line[1:])
            count, hi, lo, rtype = data[0], data[1], data[2], data[3]
            payload = data[4:4 + count]
            checksum = data[4 + count]
            if (sum(data[:4 + count]) + checksum) & 0xFF:
                raise ValueError(f"строка {lineno}: неверная контрольная сумма")
            offset = (hi << 8) | lo
            if rtype == 0x00:
                base = ext_lin + ext_seg
                for i, b in enumerate(payload):
                    img.mem[base + offset + i] = b
            elif rtype == 0x01:
                break
            elif rtype == 0x02:
                ext_seg = int.from_bytes(payload, "big") << 4
            elif rtype == 0x04:
                ext_lin = int.from_bytes(payload, "big") << 16
            elif rtype in (0x03, 0x05):
                img.start_addr = int.from_bytes(payload, "big")
            else:
                raise ValueError(f"строка {lineno}: тип записи {rtype:02X} не поддерживается")
    return img


def main() -> None:
    img = load(sys.argv[1])
    total = len(img.mem)
    blank = sum(1 for v in img.mem.values() if v == 0xFF)
    print(f"Байт в образе      : {total} (0x{total:X})")
    print(f"Из них 0xFF (пусто): {blank}  ({100.0 * blank / total:.1f}%)")
    print(f"Содержательных     : {total - blank}")
    print(f"Диапазон адресов   : 0x{min(img.mem):04X} .. 0x{max(img.mem):04X}")
    if img.start_addr is not None:
        print(f"Start address rec  : 0x{img.start_addr:08X}")
    print("\nНепрерывные сегменты:")
    for s, e in img.segments():
        print(f"  0x{s:04X} .. 0x{e:04X}   ({e - s + 1} байт)")

    print("\nОбласти с непустым содержимым (пропуски 0xFF >= 32 байт):")
    addrs = sorted(a for a, v in img.mem.items() if v != 0xFF)
    if addrs:
        start = prev = addrs[0]
        for a in addrs[1:]:
            if a - prev > 32:
                print(f"  0x{start:04X} .. 0x{prev:04X}   ({prev - start + 1} байт)")
                start = a
            prev = a
        print(f"  0x{start:04X} .. 0x{prev:04X}   ({prev - start + 1} байт)")


if __name__ == "__main__":
    main()
