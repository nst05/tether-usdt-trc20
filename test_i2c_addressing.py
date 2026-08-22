#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест адресации и постраничной записи на эмуляторе EEPROM.

Воспроизводит баг «Проверка записи не пройдена» и подтверждает, что
исправленная адресация его снимает.
"""

import sys
import crc_storage_i2c as mod
from crc_storage_i2c import I2CWriter, encode_value, crc16_ccitt


class FakeEEPROM:
    """
    Эмулятор 24Cxx с честным поведением железа:
      • 16-битные чипы, опрошенные 8-битным адресом, берут мусорный адрес;
      • запись через границу страницы заворачивается внутри страницы.
    """

    def __init__(self, size, addrsize, page):
        self.mem = bytearray(b"\xFF" * size)
        self.addrsize = addrsize
        self.page = page
        self.size = size
        self.drift = 0

    def _ack(self, dev):
        """16-битные чипы держат один адрес; 24C16 — все восемь."""
        if self.addrsize == 16:
            return dev == 0x50
        return 0x50 <= dev <= 0x57

    def _resolve(self, dev, mem, addrsize):
        if not self._ack(dev):
            raise OSError(f"NAK от устройства 0x{dev:02X}")
        if addrsize != self.addrsize:
            # Чип ждёт другое число адресных байт → адрес «уезжает».
            self.drift = (self.drift + 0x37) % self.size
            return self.drift
        if self.addrsize == 8:
            return ((dev & 0x07) << 8) | (mem & 0xFF)
        return mem & (self.size - 1)

    def readfrom_mem(self, dev, mem, length, addrsize=8):
        base = self._resolve(dev, mem, addrsize)
        return bytes(self.mem[base:base + length])

    def writeto_mem(self, dev, mem, data, addrsize=8):
        base = self._resolve(dev, mem, addrsize)
        if len(data) > self.page:
            raise AssertionError(
                f"запись {len(data)} байт больше страницы {self.page}"
            )
        page_start = (base // self.page) * self.page
        for i, byte in enumerate(data):
            # Заворот внутри страницы — точное поведение железа.
            self.mem[page_start + (base - page_start + i) % self.page] = byte


def make_writer(chip, offset, fake):
    w = I2CWriter(offset=offset, chip=chip)
    w.i2c = fake
    w.open_programmer = lambda: None
    w.close_programmer = lambda: None
    return w


def run(name, chip, fake, offset, expect_ok):
    writer = make_writer(chip, offset, fake)
    res = writer.write_and_verify("1453", debug=True)
    ok = res["success"] == expect_ok
    print(f"[{'OK' if ok else 'FAIL'}] {name}: success={res['success']} "
          f"(ожидали {expect_ok}) — {res['message']}")
    return ok, res


def main():
    mod.PAGE_WRITE_DELAY = 0
    passed = True
    OFFSET = 0x01C1

    print("=" * 72)
    print("1. Чип 24C256, код настроен на 24C16 — воспроизводим баг")
    print("=" * 72)
    chip16bit = FakeEEPROM(32768, 16, 64)
    ok, res = run("неверная адресация", "24C16", chip16bit, OFFSET, False)
    passed &= ok
    print("   последние строки лога:")
    for line in res["debug"].splitlines()[-3:]:
        print("     " + line)

    print()
    print("=" * 72)
    print("2. Чип 24C256, код настроен верно — запись должна пройти")
    print("=" * 72)
    chip = FakeEEPROM(32768, 16, 64)
    ok, res = run("верная адресация", "24C256", chip, OFFSET, True)
    passed &= ok

    print()
    print("=" * 72)
    print("3. Постраничная запись: блок не должен рваться о границу страницы")
    print("=" * 72)
    # 0x01F0 + 42 пересекает границу страницы 0x0200 — раньше это ломалось.
    cross = FakeEEPROM(32768, 16, 64)
    w = make_writer("24C256", 0x01F0, cross)
    block, crc = w.make_block(1453.08)
    w.write_bytes(0x01F0, block)
    stored = bytes(cross.mem[0x01F0:0x01F0 + 42])
    ok = stored == block
    passed &= ok
    print(f"[{'OK' if ok else 'FAIL'}] запись через границу страницы 0x0200: "
          f"{'байты совпали' if ok else 'ДАННЫЕ ИСКАЖЕНЫ'}")
    print(f"   записано: {block[:8].hex(' ').upper()} ... "
          f"{block[-2:].hex(' ').upper()}")
    print(f"   в памяти: {stored[:8].hex(' ').upper()} ... "
          f"{stored[-2:].hex(' ').upper()}")

    print()
    print("=" * 72)
    print("4. Целостность: ровно 42 байта и корректный CRC")
    print("=" * 72)
    untouched = bytes(cross.mem[0x01F0 + 42:0x01F0 + 64])
    ok = untouched == b"\xFF" * 22
    passed &= ok
    print(f"[{'OK' if ok else 'FAIL'}] соседние байты не тронуты: "
          f"{untouched.hex(' ').upper()}")

    ok = crc16_ccitt(stored[:40]) == crc
    passed &= ok
    print(f"[{'OK' if ok else 'FAIL'}] CRC блока в памяти = 0x{crc:04X}")

    print()
    print("=" * 72)
    print("5. Автоопределение чипа")
    print("=" * 72)
    # Пустой 24C256: различить можно только по числу адресов на шине.
    probe_writer = make_writer("24C16", OFFSET, FakeEEPROM(32768, 16, 64))
    report = probe_writer.probe()
    ok = report["recommend"] == "24C256"
    passed &= ok
    print(f"[{'OK' if ok else 'FAIL'}] пустой 16-битный чип → "
          f"{report['recommend']}, откликнулось адресов: "
          f"{[hex(d) for d in report['devices']]}")

    # Пустой 24C16: откликаются все восемь адресов.
    probe_writer = make_writer("24C16", 0x0100, FakeEEPROM(2048, 8, 16))
    report = probe_writer.probe()
    ok = report["recommend"] == "24C16"
    passed &= ok
    print(f"[{'OK' if ok else 'FAIL'}] пустой 8-битный чип → "
          f"{report['recommend']}, откликнулось адресов: "
          f"{[hex(d) for d in report['devices']]}")

    # Чип с реальными данными — должен определиться так же.
    filled = FakeEEPROM(32768, 16, 64)
    filled.mem[OFFSET:OFFSET + 8] = bytes.fromhex("000E686C000E686C")
    probe_writer = make_writer("24C16", OFFSET, filled)
    report = probe_writer.probe()
    ok = report["recommend"] == "24C256"
    passed &= ok
    print(f"[{'OK' if ok else 'FAIL'}] 16-битный чип с данными → "
          f"{report['recommend']}, "
          f"прочитано 16 бит: {report['16'].hex(' ').upper()}")

    print()
    print("=" * 72)
    print("ИТОГ:", "ВСЕ ТЕСТЫ ПРОЙДЕНЫ" if passed else "ЕСТЬ ПРОВАЛЫ")
    print("=" * 72)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
