#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты протокола SPI FRAM на эмуляторе микросхемы.

Железа под рукой нет, но весь протокол — команды, адресация, WREN,
нарезка посылок — проверяется без него. Эмулятор ведёт себя как настоящая
микросхема: игнорирует запись без WREN, сбрасывает разрешение после
записи, заворачивает адрес по своему объёму и понимает девятый бит адреса
в команде так, как это делает FM25L04B.
"""

import sys

from spi_memory import (
    SPIFram, SPIError, CHIPS, probe_size,
    CMD_WREN, CMD_WRDI, CMD_RDSR, CMD_READ, CMD_WRITE, CMD_RDID, SR_WEL,
)


class FramEmulator:
    """Эмулятор SPI FRAM с честным поведением шины"""

    def __init__(self, size, addr_bytes, a8_in_opcode, has_rdid=True,
                 device_id=b"\x04\x7F\x03\x02"):
        self.mem = bytearray(size)
        self.size = size
        self.addr_bytes = addr_bytes
        self.a8_in_opcode = a8_in_opcode
        self.has_rdid = has_rdid
        self.device_id = device_id

        self.wel = False
        self.writes_without_wren = 0
        self.commands = []

    def transfer(self, payload: bytes) -> bytes:
        payload = bytes(payload)
        if not payload:
            return b""

        opcode = payload[0]
        self.commands.append(opcode)
        out = bytearray(len(payload))

        if opcode == CMD_WREN:
            self.wel = True
            return bytes(out)

        if opcode == CMD_WRDI:
            self.wel = False
            return bytes(out)

        if opcode == CMD_RDSR:
            out[1:] = bytes([SR_WEL if self.wel else 0x00]) * (len(payload) - 1)
            return bytes(out)

        if opcode == CMD_RDID:
            if not self.has_rdid:
                return bytes(out)
            ident = self.device_id
            for i in range(1, len(payload)):
                out[i] = ident[(i - 1) % len(ident)]
            return bytes(out)

        base = opcode & ~0x08 if self.a8_in_opcode else opcode

        if base in (CMD_READ, CMD_WRITE):
            if self.a8_in_opcode:
                address = ((opcode >> 3) & 0x01) << 8 | payload[1]
                header = 2
            else:
                address = int.from_bytes(payload[1:1 + self.addr_bytes], "big")
                header = 1 + self.addr_bytes

            count = len(payload) - header

            if base == CMD_READ:
                for i in range(count):
                    out[header + i] = self.mem[(address + i) % self.size]
                return bytes(out)

            if not self.wel:
                # Настоящая микросхема молча игнорирует запись без WREN.
                self.writes_without_wren += 1
                return bytes(out)

            for i in range(count):
                self.mem[(address + i) % self.size] = payload[header + i]
            self.wel = False       # разрешение сбрасывается аппаратно
            return bytes(out)

        return bytes(out)


def make(chip):
    profile = CHIPS[chip]
    emulator = FramEmulator(profile["size"], profile["addr_bytes"],
                            profile["a8_in_opcode"], profile["has_rdid"])
    return SPIFram(chip, emulator), emulator


def check(label, condition, detail=""):
    print(f"[{'OK' if condition else 'FAIL'}] {label}"
          + (f" — {detail}" if detail else ""))
    return condition


def main():
    passed = True

    print("=" * 72)
    print("1. Профили микросхем")
    print("=" * 72)
    for chip in ("MB85RS64", "MB85RS128", "MB85RS256", "FM25L04B", "FM25V02"):
        fram, _ = make(chip)
        print(f"  {chip:<11} {fram.size:>6} байт  адрес "
              f"{fram.addr_bytes} байт"
              + ("  + A8 в команде" if CHIPS[chip]["a8_in_opcode"] else ""))
    passed &= check("объёмы верные",
                    CHIPS["MB85RS64"]["size"] == 8192
                    and CHIPS["MB85RS128"]["size"] == 16384
                    and CHIPS["MB85RS256"]["size"] == 32768
                    and CHIPS["FM25L04B"]["size"] == 512
                    and CHIPS["FM25V02"]["size"] == 32768)

    print()
    print("=" * 72)
    print("2. Запись и чтение на всех микросхемах")
    print("=" * 72)
    for chip in CHIPS:
        fram, emu = make(chip)
        sample = bytes(range(256)) * 2
        sample = sample[:min(len(sample), fram.size)]
        fram.write(0, sample)
        back = fram.read(0, len(sample))
        passed &= check(f"{chip}: {len(sample)} байт туда-обратно",
                        back == sample)

    print()
    print("=" * 72)
    print("3. FM25L04B: девятый бит адреса в команде")
    print("=" * 72)

    fram, emu = make("FM25L04B")
    # Верхняя половина доступна только через бит 3 команды.
    fram.write(0x100, b"\xAA\xBB\xCC\xDD")
    passed &= check("запись по 0x100 легла в верхнюю половину",
                    bytes(emu.mem[0x100:0x104]) == b"\xAA\xBB\xCC\xDD",
                    emu.mem[0x100:0x104].hex(" ").upper())
    passed &= check("нижняя половина не затронута",
                    bytes(emu.mem[0x00:0x04]) == b"\x00\x00\x00\x00")
    passed &= check("чтение по 0x100 возвращает записанное",
                    fram.read(0x100, 4) == b"\xAA\xBB\xCC\xDD")

    frame_low = fram._frame(CMD_READ, 0x0FF)
    frame_high = fram._frame(CMD_READ, 0x100)
    passed &= check("команда для 0x0FF: 03 FF",
                    frame_low == bytes([0x03, 0xFF]),
                    frame_low.hex(" ").upper())
    passed &= check("команда для 0x100: 0B 00 (бит 3 взведён)",
                    frame_high == bytes([0x0B, 0x00]),
                    frame_high.hex(" ").upper())

    # Чтение через границу 0x100 должно резаться на две посылки.
    fram, emu = make("FM25L04B")
    fram.write(0x0FE, b"\x11\x22\x33\x44")
    passed &= check("запись через границу 0x100 не завернулась",
                    bytes(emu.mem[0x0FE:0x102]) == b"\x11\x22\x33\x44",
                    emu.mem[0x0FE:0x102].hex(" ").upper())
    passed &= check("чтение через границу 0x100 верное",
                    fram.read(0x0FE, 4) == b"\x11\x22\x33\x44")

    passed &= check("вся память 512 байт адресуема",
                    len(set(range(512))) == 512
                    and fram.read(0, 512) is not None)

    print()
    print("=" * 72)
    print("4. WREN перед каждой записью")
    print("=" * 72)

    fram, emu = make("MB85RS256")
    fram.write(0, b"\x01\x02\x03")
    passed &= check("записей, отвергнутых из-за отсутствия WREN: 0",
                    emu.writes_without_wren == 0,
                    str(emu.writes_without_wren))
    passed &= check("WREN был отправлен", CMD_WREN in emu.commands)
    passed &= check("после записи разрешение снято", emu.wel is False)

    # Несколько кусков подряд — WREN нужен на каждый.
    fram, emu = make("MB85RS256")
    fram.write(0, bytes(3000))          # 3 куска по 1024
    wren_count = emu.commands.count(CMD_WREN)
    write_count = emu.commands.count(CMD_WRITE)
    passed &= check("WREN на каждую посылку записи",
                    wren_count == write_count,
                    f"WREN={wren_count}, WRITE={write_count}")
    passed &= check("ни одна запись не потеряна",
                    emu.writes_without_wren == 0)

    print()
    print("=" * 72)
    print("5. Границы адресов")
    print("=" * 72)

    fram, _ = make("FM25L04B")
    for address, length, label in ((512, 1, "чтение с 512"),
                                   (0, 513, "чтение 513 байт"),
                                   (-1, 1, "отрицательный адрес")):
        try:
            fram.read(address, length)
            passed &= check(f"{label} отвергнуто", False, "исключения не было")
        except SPIError:
            passed &= check(f"{label} отвергнуто", True)

    try:
        fram.write(510, b"\x00\x00\x00")
        passed &= check("запись за границей отвергнута", False)
    except SPIError:
        passed &= check("запись за границей отвергнута", True)

    print()
    print("=" * 72)
    print("6. Точечная запись изменившегося")
    print("=" * 72)

    fram, emu = make("FM25V02")
    original = bytes(range(256)) * 128
    fram.write(0, original)
    emu.commands.clear()

    changed = bytearray(original)
    changed[0x100:0x104] = b"\xDE\xAD\xBE\xEF"
    changed[0x2000] = 0x55

    written = fram.write_changed(original, bytes(changed))
    passed &= check("записано мало байт", written < 64, f"{written} байт")
    passed &= check("содержимое совпало с ожидаемым",
                    fram.read(0, len(changed)) == bytes(changed))

    ok, bad = fram.verify(bytes(changed))
    passed &= check("verify подтверждает", ok, f"расхождений {len(bad)}")

    # Ничего не меняем — ни одной команды записи быть не должно.
    emu.commands.clear()
    written = fram.write_changed(bytes(changed), bytes(changed))
    passed &= check("без изменений не пишется ничего",
                    written == 0 and CMD_WRITE not in emu.commands)

    print()
    print("=" * 72)
    print("7. verify замечает расхождение")
    print("=" * 72)

    fram, emu = make("MB85RS64")
    fram.write(0, b"\x01\x02\x03\x04")
    emu.mem[2] = 0xFF                    # порча мимо протокола
    ok, bad = fram.verify(b"\x01\x02\x03\x04")
    passed &= check("расхождение найдено", not ok and len(bad) == 1,
                    str(bad))
    passed &= check("адрес расхождения верный", bad and bad[0][0] == 2)

    print()
    print("=" * 72)
    print("8. Идентификатор устройства")
    print("=" * 72)

    fram, _ = make("MB85RS256")
    passed &= check("MB85RS256 отвечает на 0x9F", len(fram.read_id()) == 9)
    fram, _ = make("FM25L04B")
    passed &= check("FM25L04B идентификатора не имеет",
                    fram.read_id() == b"")

    print()
    print("=" * 72)
    print("9. Определение объёма по завороту адреса")
    print("=" * 72)

    # Микросхема меньше выбранного профиля: адрес заворачивается.
    fram = SPIFram("MB85RS256", FramEmulator(8192, 2, False))
    detected = probe_size(fram)
    passed &= check("под профилем MB85RS256 стоит 8 КБ — определено",
                    detected == 8192, f"{detected} байт")

    emu = FramEmulator(32768, 2, False)
    fram = SPIFram("MB85RS256", emu)
    before = bytes(emu.mem[:4])
    detected = probe_size(fram)
    passed &= check("настоящий MB85RS256 определён",
                    detected == 32768, f"{detected} байт")
    passed &= check("содержимое после проверки восстановлено",
                    bytes(emu.mem[:4]) == before)

    print()
    print("=" * 72)
    print("ИТОГ:", "ВСЕ ТЕСТЫ ПРОЙДЕНЫ" if passed else "ЕСТЬ ПРОВАЛЫ")
    print("=" * 72)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
