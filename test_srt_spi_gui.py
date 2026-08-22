#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест вкладок srt_mod_spi на эмуляторе SPI FRAM.

Программатор подменяется эмулятором микросхемы, поэтому проверяется весь
путь: чтение из памяти → разбор записей → правка полей → запись обратно →
проверка чтением. Без железа.
"""

import sys

from PyQt5 import QtWidgets

import spi_memory
from test_spi_memory import FramEmulator

import srt_mod_spi as G
from srt_mod_spi import (
    read_record, write_record, crc_xor_16, encode_raw_u32_weird,
    T1_REC_STsrtS, T2_REC_STsrtS, TOT_REC_STsrtS,
    BASE_OFF, DUP_OFF, REC_LEN,
    SRT29_T1_OFFS, SRT29_T2_OFFS, SRT29_SUM_OFFS,
    SRT29_BLK_T1, SRT29_BLK_T2, MIRROR_STRIDE, MIRROR_COUNT,
)

CHIP_STATE = {}


class FakeTransport:
    """Подставляется вместо CH341SPI и держит эмулятор нужного размера"""

    def __init__(self, index=0, dll_path=None):
        self.emu = None

    def open(self):
        chip = CHIP_STATE["chip"]
        profile = spi_memory.CHIPS[chip]
        # Один и тот же эмулятор между сессиями: микросхема не забывает
        # содержимое между открытиями программатора.
        key = ("emu", chip)
        if key not in CHIP_STATE:
            CHIP_STATE[key] = FramEmulator(
                profile["size"], profile["addr_bytes"],
                profile["a8_in_opcode"], profile["has_rdid"])
        self.emu = CHIP_STATE[key]

    def close(self):
        self.emu = None

    def transfer(self, payload):
        return self.emu.transfer(payload)


def seed(chip, records):
    """Залить в эмулятор записи: {смещение: (P, Q)} при заданном коэф."""
    profile = spi_memory.CHIPS[chip]
    emu = FramEmulator(profile["size"], profile["addr_bytes"],
                       profile["a8_in_opcode"], profile["has_rdid"])
    data = bytearray(profile["size"])
    for offset, (p, q, coef) in records.items():
        write_record(data, offset, p, q, coef)
    emu.mem[:] = data
    CHIP_STATE[("emu", chip)] = emu
    return emu


def check(label, condition, detail=""):
    print(f"[{'OK' if condition else 'FAIL'}] {label}"
          + (f" — {detail}" if detail else ""))
    return condition


def main():
    spi_memory.CH341SPI = FakeTransport
    G.CH341SPI = FakeTransport

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    passed = True

    # ── Вкладка 1: art03 на MB85RS256 ────────────────────────────────
    print("=" * 72)
    print("1. Вкладка art03 — MB85RS256")
    print("=" * 72)

    CHIP_STATE.clear()
    CHIP_STATE["chip"] = "MB85RS256"
    coef = 1000
    emu = seed("MB85RS256", {
        T1_REC_STsrtS[0]: (1000.00, 236.60, coef),
        T1_REC_STsrtS[1]: (1000.00, 236.60, coef),
        T2_REC_STsrtS[0]: (500.00, 118.30, coef),
        T2_REC_STsrtS[1]: (500.00, 118.30, coef),
        TOT_REC_STsrtS[0]: (1500.00, 354.90, coef),
    })

    tab = G.srt03Tab()
    passed &= check("предлагаются нужные микросхемы",
                    [tab.mem.chip_box.itemData(i)
                     for i in range(tab.mem.chip_box.count())]
                    == ["MB85RS256", "MB85RS128", "MB85RS64"])

    tab.mem.read_chip()
    app.processEvents()
    passed &= check("прочитано 32768 байт",
                    tab.mem.buf is not None and len(tab.mem.buf) == 32768,
                    str(len(tab.mem.buf) if tab.mem.buf else 0))
    passed &= check("T1 P разобран", abs(tab.in_t1p.value() - 1000.00) < 0.01,
                    f"{tab.in_t1p.value():.2f}")
    passed &= check("общие P разобраны",
                    abs(tab.out_totp.value() - 1500.00) < 0.01,
                    f"{tab.out_totp.value():.2f}")

    tab.out_totp.setValue(2000.00)
    tab.in_t1p.setValue(1200.00)
    app.processEvents()
    passed &= check("T2 P досчитался",
                    abs(tab.in_t2p.value() - 800.00) < 0.01,
                    f"{tab.in_t2p.value():.2f}")

    tab.apply_patch()
    app.processEvents()

    back = bytes(emu.mem)
    t1p, t1q, ok1 = read_record(back, T1_REC_STsrtS[0], coef)
    t2p, _, ok2 = read_record(back, T2_REC_STsrtS[0], coef)
    totp, _, ok3 = read_record(back, TOT_REC_STsrtS[0], coef)
    passed &= check("в память легло T1=1200", abs(t1p - 1200.00) < 0.01, f"{t1p:.2f}")
    passed &= check("в память легло T2=800", abs(t2p - 800.00) < 0.01, f"{t2p:.2f}")
    passed &= check("в память легло Tot=2000", abs(totp - 2000.00) < 0.01, f"{totp:.2f}")
    passed &= check("CRC пересчитан во всех трёх", ok1 and ok2 and ok3)

    dup1 = read_record(back, T1_REC_STsrtS[1], coef)[0]
    passed &= check("дубль T1 обновлён", abs(dup1 - 1200.00) < 0.01, f"{dup1:.2f}")
    passed &= check("статус говорит об успехе",
                    "проверка чтением пройдена" in tab.lbl_status.text(),
                    tab.lbl_status.text().splitlines()[-1])

    untouched = back[0x0300:0x0400]
    passed &= check("посторонние области не тронуты",
                    untouched == bytes(0x100))

    # ── Вкладка 2: AR на FM25L04B ────────────────────────────────────
    print()
    print("=" * 72)
    print("2. Вкладка AR01/AR02 — FM25L04B (512 байт, A8 в команде)")
    print("=" * 72)

    CHIP_STATE.clear()
    CHIP_STATE["chip"] = "FM25L04B"
    coef = 1000
    emu = seed("FM25L04B", {
        BASE_OFF: (6384.36, 1445.71, coef),
        DUP_OFF: (6384.36, 1445.71, coef),
    })

    tab2 = G.srtotalsTab()
    passed &= check("предлагается только FM25L04B",
                    [tab2.mem.chip_box.itemData(i)
                     for i in range(tab2.mem.chip_box.count())] == ["FM25L04B"])

    tab2.mem.read_chip()
    app.processEvents()
    passed &= check("прочитано 512 байт",
                    len(tab2.mem.buf) == 512, str(len(tab2.mem.buf)))
    passed &= check("текущее P разобрано",
                    tab2.ed_cur_p.text() == "6384.36", tab2.ed_cur_p.text())
    passed &= check("дубль по 0x0100 прочитан верно",
                    "дубль совпадает" in tab2.lbl_status.text())

    tab2.ed_new_p.setText("7000.00")
    app.processEvents()
    tab2.write_back()
    app.processEvents()

    back = bytes(emu.mem)
    parsed = G.parse_record(back, BASE_OFF)
    parsed_dup = G.parse_record(back, DUP_OFF)
    p_new = parsed.p_raw / coef
    passed &= check("в память легло P=7000", abs(p_new - 7000.00) < 0.01,
                    f"{p_new:.2f}")
    passed &= check("CRC основной записи сходится", parsed.ok)
    passed &= check("дубль по 0x0100 обновлён и сходится",
                    parsed_dup.ok
                    and back[BASE_OFF:BASE_OFF + REC_LEN]
                    == back[DUP_OFF:DUP_OFF + REC_LEN])
    passed &= check("верхняя половина писалась через бит A8",
                    any((c & ~0x08) == spi_memory.CMD_WRITE and (c & 0x08)
                        for c in emu.commands),
                    "команд с A8: %d" % sum(
                        1 for c in emu.commands
                        if (c & ~0x08) == spi_memory.CMD_WRITE and (c & 0x08)))

    # ── Вкладка 3: srt29 на FM25V02 ──────────────────────────────────
    print()
    print("=" * 72)
    print("3. Вкладка 231 at-01 — FM25V02 (4 зеркала по 0x2000)")
    print("=" * 72)

    CHIP_STATE.clear()
    CHIP_STATE["chip"] = "FM25V02"
    coef = 2000
    records = {}
    for m in range(MIRROR_COUNT):
        base = m * MIRROR_STRIDE
        for off in SRT29_T1_OFFS:
            records[base + off] = (100.00, 25.00, coef)
        for off in SRT29_T2_OFFS:
            records[base + off] = (50.00, 12.50, coef)
        for blk in SRT29_SUM_OFFS:
            records[base + blk] = (150.00, 37.50, coef)
            records[base + blk + SRT29_BLK_T1] = (100.00, 25.00, coef)
            records[base + blk + SRT29_BLK_T2] = (50.00, 12.50, coef)
    emu = seed("FM25V02", records)

    tab3 = G.srt29Tab()
    passed &= check("предлагается только FM25V02",
                    [tab3.mem.chip_box.itemData(i)
                     for i in range(tab3.mem.chip_box.count())] == ["FM25V02"])

    tab3.mem.read_chip()
    app.processEvents()
    passed &= check("прочитано 32768 байт", len(tab3.mem.buf) == 32768)
    passed &= check("T1 разобран", abs(tab3.in_t1.value() - 100.00) < 0.01)
    passed &= check("зеркала признаны совпадающими",
                    "совпадают с базой: да" in tab3.lbl_status.text())

    tab3.in_t1.setValue(300.00)
    tab3.in_t2.setValue(200.00)
    app.processEvents()
    passed &= check("сумма досчиталась", tab3.out_sum.text() == "500.00",
                    tab3.out_sum.text())

    tab3.apply_patch()
    app.processEvents()

    back = bytes(emu.mem)
    all_ok = True
    for m in range(MIRROR_COUNT):
        base = m * MIRROR_STRIDE
        t1 = read_record(back, base + SRT29_T1_OFFS[0], coef)
        t2 = read_record(back, base + SRT29_T2_OFFS[0], coef)
        sm = read_record(back, base + SRT29_SUM_OFFS[0], coef)
        if not (abs(t1[0] - 300) < 0.01 and abs(t2[0] - 200) < 0.01
                and abs(sm[0] - 500) < 0.01 and t1[2] and t2[2] and sm[2]):
            all_ok = False
    passed &= check("все 4 зеркала обновлены и CRC сходятся", all_ok)

    # Q должно сохраниться
    q_after = read_record(back, SRT29_T1_OFFS[0], coef)[1]
    passed &= check("Q сохранено неизменным", abs(q_after - 25.00) < 0.01,
                    f"{q_after:.2f}")

    blk_t1 = read_record(back, SRT29_SUM_OFFS[0] + SRT29_BLK_T1, coef)[0]
    blk_t2 = read_record(back, SRT29_SUM_OFFS[0] + SRT29_BLK_T2, coef)[0]
    passed &= check("внутри итогового блока T1/T2 обновлены",
                    abs(blk_t1 - 300) < 0.01 and abs(blk_t2 - 200) < 0.01,
                    f"T1={blk_t1:.2f} T2={blk_t2:.2f}")

    # ── Повторная запись без изменений ───────────────────────────────
    print()
    print("=" * 72)
    print("4. Повторная запись без изменений ничего не пишет")
    print("=" * 72)

    emu.commands.clear()
    tab3.apply_patch()
    app.processEvents()
    writes = sum(1 for c in emu.commands if c == spi_memory.CMD_WRITE)
    passed &= check("команд записи не было", writes == 0, str(writes))
    passed &= check("статус это сообщает",
                    "Изменений нет" in tab3.lbl_status.text(),
                    tab3.lbl_status.text().splitlines()[0])

    # ── Запись без чтения ────────────────────────────────────────────
    print()
    print("=" * 72)
    print("5. Запись до чтения не проходит")
    print("=" * 72)

    CHIP_STATE.clear()
    CHIP_STATE["chip"] = "MB85RS256"
    seed("MB85RS256", {})
    fresh = G.srt03Tab()
    fresh.apply_patch()
    passed &= check("кнопка записи выключена до чтения",
                    not fresh.mem.btn_write.isEnabled())
    passed &= check("статус просит сначала прочитать",
                    "Сначала прочитайте память" in fresh.lbl_status.text(),
                    fresh.lbl_status.text())

    print()
    print("=" * 72)
    print("ИТОГ:", "ВСЕ ТЕСТЫ ПРОЙДЕНЫ" if passed else "ЕСТЬ ПРОВАЛЫ")
    print("=" * 72)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
