#!/usr/bin/env python3
"""Разворачивает Intel HEX прошивки в плоский образ fw.bin (заполнение 0xFF).

Использование: python3 hex2bin.py [путь_к_hex] [выходной_bin]
По умолчанию: ../firmware.hex -> fw.bin
"""
import sys


def hex_to_image(path: str, size: int = 0x10000) -> bytearray:
    img = bytearray(b"\xFF" * size)
    base = 0
    for line in open(path):
        line = line.strip()
        if not line or line[0] != ":":
            continue
        b = bytes.fromhex(line[1:])
        n, addr, rectype = b[0], (b[1] << 8) | b[2], b[3]
        if (sum(b) & 0xFF) != 0:
            raise ValueError(f"ошибка контрольной суммы: {line}")
        data = b[4:4 + n]
        if rectype == 0:
            for i, v in enumerate(data):
                img[base + addr + i] = v
        elif rectype == 4:
            base = int.from_bytes(data, "big") << 16
        elif rectype == 2:
            base = int.from_bytes(data, "big") << 4
        elif rectype == 1:
            break
    return img


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "../firmware.hex"
    dst = sys.argv[2] if len(sys.argv) > 2 else "fw.bin"
    open(dst, "wb").write(hex_to_image(src))
    print(f"{src} -> {dst}")
