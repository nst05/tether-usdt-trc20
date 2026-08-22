#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка главного требования: при записи трогаются ТОЛЬКО нужные байты.

Эмулятор запоминает каждый адрес, до которого дошла команда записи. Этого
недостаточно проверять сравнением содержимого: байт можно перезаписать тем
же значением, содержимое совпадёт, а ячейка будет затронута. Поэтому здесь
сверяется именно множество записанных адресов.
"""

import sys

from PyQt5 import QtWidgets

import spi_memory
from spi_memory import SPIFram
from test_spi_memory import FramEmulator

import srt_mod_spi as G
from srt_mod_spi import (
    write_record, read_record, REC_LEN,
    T1_REC_STsrtS, T2_REC_STsrtS, TOT_REC_STsrtS,
    BASE_OFF, DUP_OFF,
    SRT29_T1_OFFS, SRT29_T2_OFFS, SRT29_SUM_OFFS,
    SRT29_BLK_T1, SRT29_BLK_T2, MIRROR_STRIDE, MIRROR_COUNT,
)

CHIP_STATE = {}


class TrackingEmulator(FramEmulator):
    """Эмулятор, запоминающий каждый затронутый записью адрес"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.touched = set()

    def transfer(self, payload):
        payload = bytes(payload)
        if payload:
            opcode = payload[0]
            base = opcode & ~0x08 if self.a8_in_opcode else opcode
            if base == spi_memory.CMD_WRITE and self.wel:
                if self.a8_in_opcode:
                    address = ((opcode >> 3) & 0x01) << 8 | payload[1]
                    header = 2
                else:
                    address = int.from_bytes(payload[1:1 + self.addr_bytes], "big")
                    header = 1 + self.addr_bytes
                for i in range(len(payload) - header):
                    self.touched.add((address + i) % self.size)
        return super().transfer(payload)


class FakeTransport:
    def __init__(self, index=0, dll_path=None):
        self.emu = None

    def open(self):
        self.emu = CHIP_STATE["emu"]

    def close(self):
        self.emu = None

    def transfer(self, payload):
        return self.emu.transfer(payload)


def seed(chip, records):
    profile = spi_memory.CHIPS[chip]
    emu = TrackingEmulator(profile["size"], profile["addr_bytes"],
                           profile["a8_in_opcode"], profile["has_rdid"])
    data = bytearray(profile["size"])
    # Заполняем «посторонние» байты узнаваемым мусором: если что-то тронут
    # мимо записей, это сразу видно.
    for i in range(len(data)):
        data[i] = (i * 7 + 13) & 0xFF
    for offset, (p, q, coef) in records.items():
        write_record(data, offset, p, q, coef)
    emu.mem[:] = data
    CHIP_STATE["emu"] = emu
    return emu


def ranges_of(offsets, length=REC_LEN):
    """Множество адресов, которые вкладке разрешено трогать"""
    allowed = set()
    for off in offsets:
        allowed.update(range(off, off + length))
    return allowed


def check(label, condition, detail=""):
    print(f"[{'OK' if condition else 'FAIL'}] {label}"
          + (f" — {detail}" if detail else ""))
    return condition


def report(emu, allowed, before, after, label):
    """Свести проверку: тронутое внутри разрешённого, остальное не изменилось"""
    ok = True

    stray = sorted(emu.touched - allowed)
    ok &= check(f"{label}: команды записи не выходят за записи",
                not stray,
                "" if not stray else
                f"{len(stray)} лишних адресов, первый 0x{stray[0]:04X}")

    differ = [i for i in range(len(before)) if before[i] != after[i]]
    outside = [i for i in differ if i not in allowed]
    ok &= check(f"{label}: содержимое вне записей не изменилось",
                not outside,
                "" if not outside else
                f"{len(outside)} байт, первый 0x{outside[0]:04X}")

    ok &= check(f"{label}: изменения были", bool(differ),
                f"изменено {len(differ)} байт, затронуто {len(emu.touched)}")
    return ok


def main():
    spi_memory.CH341SPI = FakeTransport
    G.CH341SPI = FakeTransport

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    passed = True

    print("=" * 72)
    print("0. Точечность самого write_changed")
    print("=" * 72)

    emu = TrackingEmulator(1024, 2, False)
    fram = SPIFram("MB85RS64", emu)
    old = bytes(range(256)) * 4
    new = bytearray(old)
    new[100] = 0xFF
    new[500] = 0xFF          # между ними 399 неизменных байт
    new[501] = 0xFE

    fram.write_changed(old, bytes(new))
    passed &= check("тронуты ровно изменившиеся адреса",
                    emu.touched == {100, 500, 501},
                    sorted(emu.touched))

    ranges = fram.changed_ranges(old, bytes(new))
    passed &= check("участки не склеиваются через неизменные байты",
                    ranges == [(100, 101), (500, 502)], str(ranges))

    # Байт, который «меняется» на то же самое значение, писаться не должен.
    emu = TrackingEmulator(256, 2, False)
    fram = SPIFram("MB85RS64", emu)
    same = bytes(range(256))
    fram.write_changed(same, same)
    passed &= check("одинаковые буферы не трогают ничего",
                    emu.touched == set())

    print()
    print("=" * 72)
    print("1. ART — MB85RS256")
    print("=" * 72)

    coef = 1000
    emu = seed("MB85RS256", {
        T1_REC_STsrtS[0]: (1000.00, 236.60, coef),
        T1_REC_STsrtS[1]: (1000.00, 236.60, coef),
        T2_REC_STsrtS[0]: (500.00, 118.30, coef),
        T2_REC_STsrtS[1]: (500.00, 118.30, coef),
        TOT_REC_STsrtS[0]: (1500.00, 354.90, coef),
    })
    before = bytes(emu.mem)

    tab = G.srt03Tab()
    tab.mem.read_chip(); app.processEvents()
    emu.touched.clear()

    tab.out_totp.setValue(2000.00)
    tab.in_t1p.setValue(1200.00)
    app.processEvents()
    tab.apply_patch(); app.processEvents()

    allowed = ranges_of(T1_REC_STsrtS + T2_REC_STsrtS + TOT_REC_STsrtS)
    passed &= report(emu, allowed, before, bytes(emu.mem), "ART")

    print()
    print("=" * 72)
    print("2. AR — FM25L04B")
    print("=" * 72)

    emu = seed("FM25L04B", {
        BASE_OFF: (6384.36, 1445.71, coef),
        DUP_OFF: (6384.36, 1445.71, coef),
    })
    before = bytes(emu.mem)

    tab2 = G.srtotalsTab()
    tab2.mem.read_chip(); app.processEvents()
    emu.touched.clear()

    tab2.ed_new_p.setText("7000.00")
    app.processEvents()
    tab2.write_back(); app.processEvents()

    allowed = ranges_of([BASE_OFF, DUP_OFF])
    passed &= report(emu, allowed, before, bytes(emu.mem), "AR")

    print()
    print("=" * 72)
    print("3. 231-AT-01 — FM25V02, 4 зеркала")
    print("=" * 72)

    coef = 2000
    records = {}
    offsets = []
    for m in range(MIRROR_COUNT):
        base = m * MIRROR_STRIDE
        for off in SRT29_T1_OFFS:
            records[base + off] = (100.00, 25.00, coef); offsets.append(base + off)
        for off in SRT29_T2_OFFS:
            records[base + off] = (50.00, 12.50, coef); offsets.append(base + off)
        for blk in SRT29_SUM_OFFS:
            records[base + blk] = (150.00, 37.50, coef); offsets.append(base + blk)
            records[base + blk + SRT29_BLK_T1] = (100.00, 25.00, coef)
            offsets.append(base + blk + SRT29_BLK_T1)
            records[base + blk + SRT29_BLK_T2] = (50.00, 12.50, coef)
            offsets.append(base + blk + SRT29_BLK_T2)
    emu = seed("FM25V02", records)
    before = bytes(emu.mem)

    tab3 = G.srt29Tab()
    tab3.mem.read_chip(); app.processEvents()
    emu.touched.clear()

    tab3.in_t1.setValue(300.00)
    tab3.in_t2.setValue(200.00)
    app.processEvents()
    tab3.apply_patch(); app.processEvents()

    allowed = ranges_of(offsets)
    passed &= report(emu, allowed, before, bytes(emu.mem), "231-AT-01")

    # Q внутри записей обязано сохраниться — вкладка правит только P.
    q_before = read_record(before, SRT29_T1_OFFS[0], coef)[1]
    q_after = read_record(bytes(emu.mem), SRT29_T1_OFFS[0], coef)[1]
    passed &= check("231-AT-01: Q не изменилось",
                    abs(q_before - q_after) < 0.001,
                    f"{q_before:.2f} -> {q_after:.2f}")

    print()
    print("=" * 72)
    print("4. Повторная запись тех же значений не трогает ничего")
    print("=" * 72)

    emu.touched.clear()
    tab3.apply_patch(); app.processEvents()
    passed &= check("231-AT-01: повторная запись — ноль затронутых адресов",
                    emu.touched == set(), str(len(emu.touched)))

    print()
    print("=" * 72)
    print("ИТОГ:", "ВСЕ ТЕСТЫ ПРОЙДЕНЫ" if passed else "ЕСТЬ ПРОВАЛЫ")
    print("=" * 72)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
