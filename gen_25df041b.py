#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор дампа внешней памяти счётчика СЕ208.
Микросхема: AT25DF041B  (SPI serial flash, 4 Mbit = 512 KiB).

Воспроизводит образ ровно так, как его формирует МК при инициализации архива:
  1) стирание всего чипа в 0xFF (erased state);
  2) запись 128-байтной сигнатуры в начало каждой из 5 архивных секций.

Сигнатура (128 байт):
    off 0x00..0x7D (126 б): линейный тест-паттерн  byte[i] = (3*i) & 0xFF
    off 0x7E..0x7F (2 б):    маркер секции 0x12D0  (little-endian: D0 12)
Секции расположены с шагом STEP, начиная с 0.
"""

CHIP_SIZE   = 512 * 1024      # 0x80000 — полный объём AT25DF041B
ERASED      = 0xFF            # состояние стёртой NOR-флеши
STEP        = 0x19000         # шаг между секциями (102400 байт)
N_SECTIONS  = 5              # число архивных секций
RAMP_LEN    = 0x7E            # 126 байт линейного паттерна
RAMP_K      = 3              # шаг паттерна: byte[i] = (K*i) & 0xFF
MARKER      = 0x12D0          # 16-битный маркер секции (LE)

def section_signature() -> bytes:
    """128-байтный заголовок секции: рампа + маркер."""
    body = bytes((RAMP_K * i) & 0xFF for i in range(RAMP_LEN))   # 126 байт
    return body + MARKER.to_bytes(2, "little")                   # +2 = 128 байт

def build_image() -> bytearray:
    img = bytearray([ERASED]) * CHIP_SIZE          # шаг 1: весь чип = 0xFF
    sig = section_signature()
    for s in range(N_SECTIONS):                     # шаг 2: init секций
        off = s * STEP
        img[off:off + len(sig)] = sig
    return img

if __name__ == "__main__":
    import sys, hashlib
    out = sys.argv[1] if len(sys.argv) > 1 else "25DF041B_gen.bin"
    img = build_image()
    with open(out, "wb") as f:
        f.write(img)
    print("written %s  size=%d" % (out, len(img)))
    print("md5    :", hashlib.md5(img).hexdigest())
    print("sha1   :", hashlib.sha1(img).hexdigest())
    print("секции :", ", ".join("0x%06x" % (s*STEP) for s in range(N_SECTIONS)))
