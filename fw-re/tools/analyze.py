"""Рекурсивный анализ прошивки MSP430: обход кода, функции, перекрёстные ссылки.

Точки входа — таблица векторов прерываний (0xFFE0..0xFFFF). Далее выполняется
рекурсивный обход по CALL/JMP/условным переходам. Дополнительно распознаются
таблицы адресов (косвенные переходы) и обращения к периферии.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from typing import Dict, List, Set

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import ihex
import msp430

VECT_BASE = 0xFFE0
VECT_TOP = 0x10000

# Таблица векторов MSP430F249. Назначение подтверждено экспериментально —
# по регистрам периферии, к которым обращается тело каждого обработчика
# (см. отчёт, раздел «Обработчики прерываний»).
VECTOR_NAMES = {
    0xFFFE: "RESET",          # -> 1100  начальная инициализация
    0xFFFC: "NMI",            # -> 2532  IFG1.OFIFG + BCSCTL2  (отказ генератора)
    0xFFFA: "TIMERB0",        # -> 445E  заглушка RETI
    0xFFF8: "TIMERB1",        # -> 2570  TBCCTL1/TBCCTL6
    0xFFF6: "COMPARATOR_A",   # -> 4460  заглушка RETI
    0xFFF4: "WDT",            # -> 2560  WDTCTL, IFG1.WDTIFG
    0xFFF2: "TIMERA0",        # -> 2DC6  TACCTL0/TACCTL2
    0xFFF0: "TIMERA1",        # -> 2F12  ADD &TAIV,PC
    0xFFEE: "USCI_A0B0_RX",   # -> 2E32  UCA0RXBUF
    0xFFEC: "USCI_A0B0_TX",   # -> 2E72  UCA0TXBUF
    0xFFEA: "ADC12",          # -> 3CC2  ADC12CTL0/ADC12MEMx
    0xFFE8: "RESERVED_DMA",   # -> 4464  заглушка RETI
    0xFFE6: "PORT2",          # -> 4412  P2IFG.6  (кнопка)
    0xFFE4: "PORT1",          # -> 4462  заглушка RETI
    0xFFE2: "USCI_A1B1_RX",   # -> 2EA2  UCA1RXBUF
    0xFFE0: "USCI_A1B1_TX",   # -> 2EE2  UCA1TXBUF
}

CODE_LO = 0x1100
CODE_HI = 0xFFDF


class Analysis:
    def __init__(self, img: ihex.Image):
        self.img = img
        self.symbols: Dict[int, str] = {}
        self.dis = msp430.Disassembler(img, self.symbols)
        self.insns: Dict[int, msp430.Insn] = {}
        self.code: Set[int] = set()
        self.func_entries: Set[int] = set()
        self.call_xrefs: Dict[int, Set[int]] = defaultdict(set)   # цель -> вызывающие
        self.jump_xrefs: Dict[int, Set[int]] = defaultdict(set)
        self.data_xrefs: Dict[int, Set[int]] = defaultdict(set)   # адрес данных -> код
        self.vectors: Dict[int, int] = {}

    # ------------------------------------------------------------------
    def read_vectors(self):
        for a in range(VECT_BASE, VECT_TOP, 2):
            self.vectors[a] = self.img.word(a)
        return self.vectors

    def in_code(self, a: int) -> bool:
        return CODE_LO <= a <= CODE_HI and self.img.has_range(a, 2)

    # ------------------------------------------------------------------
    def sweep(self):
        """Рекурсивный обход от векторов прерываний."""
        worklist: List[int] = []
        for va, target in self.read_vectors().items():
            if self.in_code(target):
                name = VECTOR_NAMES.get(va, f"vec_{va:04X}")
                self.symbols.setdefault(target, f"ISR_{name}"
                                        if va != 0xFFFE else "_reset")
                self.func_entries.add(target)
                worklist.append(target)

        seen_starts: Set[int] = set()
        while worklist:
            pc = worklist.pop()
            if pc in seen_starts:
                continue
            seen_starts.add(pc)
            while True:
                if not self.in_code(pc) or pc in self.insns:
                    break
                ins = self.dis.decode(pc)
                self.insns[pc] = ins
                for off in range(ins.size):
                    self.code.add(pc + off)

                if ins.kind == "invalid":
                    break
                if ins.kind == "call":
                    if ins.target is not None and self.in_code(ins.target):
                        self.call_xrefs[ins.target].add(pc)
                        self.func_entries.add(ins.target)
                        worklist.append(ins.target)
                    elif ins.src_abs is not None:
                        self.data_xrefs[ins.src_abs].add(pc)
                elif ins.kind == "cjump":
                    if ins.target is not None and self.in_code(ins.target):
                        self.jump_xrefs[ins.target].add(pc)
                        worklist.append(ins.target)
                elif ins.kind == "jump":
                    if ins.target is not None and self.in_code(ins.target):
                        self.jump_xrefs[ins.target].add(pc)
                        worklist.append(ins.target)
                    elif ins.src_abs is not None:
                        self.data_xrefs[ins.src_abs].add(pc)
                    break
                elif ins.kind in ("ret", "reti"):
                    break

                for a in (ins.src_abs, ins.dst_abs):
                    if a is not None:
                        self.data_xrefs[a].add(pc)
                pc += ins.size

    # ------------------------------------------------------------------
    def linear_fill(self):
        """Линейная досборка нераспознанных участков кода между функциями."""
        added = 0
        a = CODE_LO
        while a <= CODE_HI:
            if a in self.code:
                a += 1
                continue
            # пропуск заполнителей
            if self.img.has_range(a, 2) and self.img.word(a) in (0xFFFF, 0x0000):
                a += 2
                continue
            ins = self.dis.decode(a)
            if ins.kind == "invalid":
                a += 2
                continue
            self.insns.setdefault(a, ins)
            for off in range(ins.size):
                self.code.add(a + off)
            added += 1
            a += ins.size
        return added

    # ------------------------------------------------------------------
    def name_functions(self):
        for i, ea in enumerate(sorted(self.func_entries)):
            self.symbols.setdefault(ea, f"sub_{ea:04X}")

    def stats(self):
        return {
            "instructions": len(self.insns),
            "code_bytes": len(self.code),
            "functions": len(self.func_entries),
        }


def build(path: str) -> Analysis:
    img = ihex.load(path)
    an = Analysis(img)
    an.sweep()
    an.linear_fill()
    an.name_functions()
    return an


def main():
    an = build(sys.argv[1])
    s = an.stats()
    print("=== Таблица векторов прерываний ===")
    for a in sorted(an.vectors, reverse=True):
        t = an.vectors[a]
        nm = VECTOR_NAMES.get(a, "?")
        mark = "" if an.in_code(t) else "  <- вне кода"
        print(f"  0x{a:04X}  {nm:<16} -> 0x{t:04X}{mark}")
    print()
    print("=== Статистика обхода ===")
    print(f"  распознано команд : {s['instructions']}")
    print(f"  байт кода         : {s['code_bytes']}")
    print(f"  найдено функций   : {s['functions']}")

    print("\n=== 25 самых вызываемых функций ===")
    tops = sorted(an.call_xrefs.items(), key=lambda kv: -len(kv[1]))[:25]
    for tgt, callers in tops:
        print(f"  0x{tgt:04X}  вызовов: {len(callers)}")

    print("\n=== Обращения к периферии (SFR) ===")
    per = defaultdict(int)
    for a, srcs in an.data_xrefs.items():
        nm = msp430.sfr_name(a)
        if nm:
            per[nm] += len(srcs)
    for nm, n in sorted(per.items(), key=lambda kv: -kv[1]):
        print(f"  {nm:<12} {n}")


if __name__ == "__main__":
    main()
