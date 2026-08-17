"""Дизассемблер MSP430 (базовый набор команд, 16-битное адресное пространство).

Реализованы все три формата команд MSP430:
  * формат I   — двухоперандные (MOV, ADD, ... AND);
  * формат II  — однооперандные (RRC, SWPB, RRA, SXT, PUSH, CALL, RETI);
  * формат III — условные переходы (JNE ... JMP).

Поддерживаются генератор констант (R2/R3), все режимы адресации и
распознавание эмулируемых команд (RET, POP, BR, CLR, INC, TST, ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# --------------------------------------------------------------------------
# Регистры и карта периферии MSP430F2xx
# --------------------------------------------------------------------------

REG_NAMES = {0: "PC", 1: "SP", 2: "SR", 3: "CG"}


def reg(n: int) -> str:
    return REG_NAMES.get(n, f"R{n}")


DOUBLE_OPS = {
    0x4: "MOV", 0x5: "ADD", 0x6: "ADDC", 0x7: "SUBC",
    0x8: "SUB", 0x9: "CMP", 0xA: "DADD", 0xB: "BIT",
    0xC: "BIC", 0xD: "BIS", 0xE: "XOR", 0xF: "AND",
}

SINGLE_OPS = {0: "RRC", 1: "SWPB", 2: "RRA", 3: "SXT", 4: "PUSH", 5: "CALL", 6: "RETI"}

JUMP_OPS = {0: "JNZ", 1: "JZ", 2: "JNC", 3: "JC", 4: "JN", 5: "JGE", 6: "JL", 7: "JMP"}

# Регистры специальных функций и периферии (x2xx family)
SFR: Dict[int, str] = {
    0x0000: "IE1", 0x0001: "IE2", 0x0002: "IFG1", 0x0003: "IFG2",
    0x0056: "DCOCTL", 0x0057: "BCSCTL1", 0x0058: "BCSCTL2", 0x0053: "BCSCTL3",
    0x0120: "WDTCTL",
    0x0128: "ADC12_unused",
    # Порты ввода-вывода
    0x0020: "P1IN", 0x0021: "P1OUT", 0x0022: "P1DIR", 0x0023: "P1IFG",
    0x0024: "P1IES", 0x0025: "P1IE", 0x0026: "P1SEL", 0x0041: "P1SEL2",
    0x0028: "P2IN", 0x0029: "P2OUT", 0x002A: "P2DIR", 0x002B: "P2IFG",
    0x002C: "P2IES", 0x002D: "P2IE", 0x002E: "P2SEL", 0x0042: "P2SEL2",
    0x0018: "P3IN", 0x0019: "P3OUT", 0x001A: "P3DIR", 0x001B: "P3SEL",
    0x0043: "P3SEL2",
    0x001C: "P4IN", 0x001D: "P4OUT", 0x001E: "P4DIR", 0x001F: "P4SEL",
    0x0044: "P4SEL2",
    0x0030: "P5IN", 0x0031: "P5OUT", 0x0032: "P5DIR", 0x0033: "P5SEL",
    0x0045: "P5SEL2",
    0x0034: "P6IN", 0x0035: "P6OUT", 0x0036: "P6DIR", 0x0037: "P6SEL",
    0x0046: "P6SEL2",
    # USCI_A0 / USCI_B0
    0x0060: "UCA0CTL0", 0x0061: "UCA0CTL1", 0x0062: "UCA0BR0", 0x0063: "UCA0BR1",
    0x0064: "UCA0MCTL", 0x0065: "UCA0STAT", 0x0066: "UCA0RXBUF", 0x0067: "UCA0TXBUF",
    0x005D: "UCA0ABCTL", 0x005E: "UCA0IRTCTL", 0x005F: "UCA0IRRCTL",
    0x0068: "UCB0CTL0", 0x0069: "UCB0CTL1", 0x006A: "UCB0BR0", 0x006B: "UCB0BR1",
    0x006C: "UCB0I2CIE", 0x006D: "UCB0STAT", 0x006E: "UCB0RXBUF", 0x006F: "UCB0TXBUF",
    0x0118: "UCB0I2COA", 0x011A: "UCB0I2CSA",
    # USCI_A1 / USCI_B1
    0x00D0: "UCA1CTL0", 0x00D1: "UCA1CTL1", 0x00D2: "UCA1BR0", 0x00D3: "UCA1BR1",
    0x00D4: "UCA1MCTL", 0x00D5: "UCA1STAT", 0x00D6: "UCA1RXBUF", 0x00D7: "UCA1TXBUF",
    0x00CD: "UCA1ABCTL", 0x00CE: "UCA1IRTCTL", 0x00CF: "UCA1IRRCTL",
    0x00D8: "UCB1CTL0", 0x00D9: "UCB1CTL1", 0x00DA: "UCB1BR0", 0x00DB: "UCB1BR1",
    0x00DC: "UCB1I2CIE", 0x00DD: "UCB1STAT", 0x00DE: "UCB1RXBUF", 0x00DF: "UCB1TXBUF",
    0x0006: "UC1IE", 0x0007: "UC1IFG",
    # Timer_A
    0x0160: "TACTL", 0x0162: "TACCTL0", 0x0164: "TACCTL1", 0x0166: "TACCTL2",
    0x0170: "TAR", 0x0172: "TACCR0", 0x0174: "TACCR1", 0x0176: "TACCR2",
    0x012E: "TAIV",
    # Timer_B
    0x0180: "TBCTL", 0x0182: "TBCCTL0", 0x0184: "TBCCTL1", 0x0186: "TBCCTL2",
    0x0188: "TBCCTL3", 0x018A: "TBCCTL4", 0x018C: "TBCCTL5", 0x018E: "TBCCTL6",
    0x0190: "TBR", 0x0192: "TBCCR0", 0x0194: "TBCCR1", 0x0196: "TBCCR2",
    0x0198: "TBCCR3", 0x019A: "TBCCR4", 0x019C: "TBCCR5", 0x019E: "TBCCR6",
    0x011E: "TBIV",
    # ADC12
    0x01A0: "ADC12CTL0", 0x01A2: "ADC12CTL1", 0x01A4: "ADC12IFG",
    0x01A6: "ADC12IE", 0x01A8: "ADC12IV",
    **{0x0140 + 2 * i: f"ADC12MEM{i}" for i in range(16)},
    **{0x0080 + i: f"ADC12MCTL{i}" for i in range(16)},
    # ADC10
    0x01B0: "ADC10CTL0", 0x01B2: "ADC10CTL1", 0x01B4: "ADC10MEM",
    0x01B8: "ADC10DTC0", 0x01B9: "ADC10DTC1", 0x004A: "ADC10AE0",
    # Flash / компаратор / умножитель
    0x0128: "FCTL1", 0x012A: "FCTL2", 0x012C: "FCTL3",
    0x0059: "CACTL1", 0x005A: "CACTL2", 0x005B: "CAPD",
    0x0130: "MPY", 0x0132: "MPYS", 0x0134: "MAC", 0x0136: "MACS",
    0x0138: "OP2", 0x013A: "RESLO", 0x013C: "RESHI", 0x013E: "SUMEXT",
    # DMA
    0x0122: "DMACTL0", 0x0124: "DMACTL1", 0x0126: "DMAIV",
}


def sfr_name(addr: int) -> Optional[str]:
    return SFR.get(addr & 0xFFFF)


# --------------------------------------------------------------------------
# Результат дизассемблирования
# --------------------------------------------------------------------------

@dataclass
class Insn:
    addr: int
    size: int
    words: List[int]
    mnem: str
    ops: List[str] = field(default_factory=list)
    # Семантика для анализатора потока управления
    kind: str = "normal"      # normal | jump | cjump | call | ret | reti | invalid
    target: Optional[int] = None   # адрес перехода/вызова, если известен
    src_imm: Optional[int] = None  # непосредственный операнд-источник
    dst_abs: Optional[int] = None  # абсолютный адрес приёмника
    src_abs: Optional[int] = None  # абсолютный адрес источника
    bw: bool = False               # операция над байтом

    @property
    def text(self) -> str:
        return f"{self.mnem}\t{', '.join(self.ops)}" if self.ops else self.mnem

    @property
    def hexwords(self) -> str:
        return " ".join(f"{w:04X}" for w in self.words)


class Operand:
    """Декодированный операнд."""

    def __init__(self, text: str, imm: Optional[int] = None,
                 abs_addr: Optional[int] = None, is_reg: bool = False,
                 regno: Optional[int] = None, mode: str = ""):
        self.text = text
        self.imm = imm
        self.abs_addr = abs_addr
        self.is_reg = is_reg
        self.regno = regno
        self.mode = mode


class Disassembler:
    def __init__(self, img, symbols: Optional[Dict[int, str]] = None):
        self.img = img
        self.symbols = symbols or {}

    # -- вспомогательное ---------------------------------------------------
    def _sym(self, addr: int) -> str:
        addr &= 0xFFFF
        if addr in self.symbols:
            return self.symbols[addr]
        name = sfr_name(addr)
        if name:
            return name
        return f"0x{addr:04X}"

    def _fetch(self, addr: int) -> Optional[int]:
        if not self.img.has_range(addr, 2):
            return None
        return self.img.word(addr)

    # -- декодирование операндов ------------------------------------------
    def _src_operand(self, regno: int, As: int, pc: int, words: List[int],
                     bw: bool):
        """Возвращает (Operand, новый pc). pc указывает на следующее слово."""
        if regno == 3:  # генератор констант CG2
            const = {0: 0, 1: 1, 2: 2, 3: 0xFFFF}[As]
            txt = "#-1" if As == 3 else f"#{const}"
            return Operand(txt, imm=const, mode="const"), pc
        if regno == 2 and As in (2, 3):  # CG1
            const = {2: 4, 3: 8}[As]
            return Operand(f"#{const}", imm=const, mode="const"), pc
        if regno == 2 and As == 1:  # абсолютная адресация &ADDR
            ext = self._fetch(pc)
            if ext is None:
                return None, pc
            words.append(ext)
            return Operand(f"&{self._sym(ext)}", abs_addr=ext, mode="abs"), pc + 2

        if As == 0:
            return Operand(reg(regno), is_reg=True, regno=regno, mode="reg"), pc
        if As == 1:
            ext = self._fetch(pc)
            if ext is None:
                return None, pc
            words.append(ext)
            if regno == 0:  # символьная (PC-относительная)
                tgt = (pc + 2 + s16(ext)) & 0xFFFF
                return Operand(self._sym(tgt), abs_addr=tgt, mode="sym"), pc + 2
            return Operand(f"{s16(ext)}({reg(regno)})", mode="idx",
                           regno=regno, imm=s16(ext)), pc + 2
        if As == 2:
            return Operand(f"@{reg(regno)}", regno=regno, mode="ind"), pc
        # As == 3
        if regno == 0:  # непосредственная
            ext = self._fetch(pc)
            if ext is None:
                return None, pc
            words.append(ext)
            val = ext & 0xFF if bw else ext
            return Operand(f"#0x{val:04X}", imm=val, mode="imm"), pc + 2
        return Operand(f"@{reg(regno)}+", regno=regno, mode="indinc"), pc

    def _dst_operand(self, regno: int, Ad: int, pc: int, words: List[int]):
        if Ad == 0:
            return Operand(reg(regno), is_reg=True, regno=regno, mode="reg"), pc
        ext = self._fetch(pc)
        if ext is None:
            return None, pc
        words.append(ext)
        if regno == 2:
            return Operand(f"&{self._sym(ext)}", abs_addr=ext, mode="abs"), pc + 2
        if regno == 0:
            tgt = (pc + 2 + s16(ext)) & 0xFFFF
            return Operand(self._sym(tgt), abs_addr=tgt, mode="sym"), pc + 2
        return Operand(f"{s16(ext)}({reg(regno)})", mode="idx",
                       regno=regno, imm=s16(ext)), pc + 2

    # -- основной декодер --------------------------------------------------
    def decode(self, addr: int) -> Insn:
        w = self._fetch(addr)
        if w is None:
            return Insn(addr, 2, [], ".word", ["???"], kind="invalid")
        words = [w]
        pc = addr + 2

        # --- формат III: переходы ---
        if 0x2000 <= w < 0x4000:
            cond = (w >> 10) & 7
            off = w & 0x3FF
            if off & 0x200:
                off -= 0x400
            tgt = (addr + 2 + off * 2) & 0xFFFF
            mnem = JUMP_OPS[cond]
            return Insn(addr, 2, words, mnem, [self._sym(tgt)],
                        kind="jump" if cond == 7 else "cjump", target=tgt)

        # --- формат II: однооперандные ---
        if 0x1000 <= w < 0x2000:
            op = (w >> 7) & 7
            if op == 7 or (w & 0xFF80) not in (
                    0x1000, 0x1080, 0x1100, 0x1180, 0x1200, 0x1280, 0x1300):
                return Insn(addr, 2, words, ".word", [f"0x{w:04X}"], kind="invalid")
            bw = bool((w >> 6) & 1)
            As = (w >> 4) & 3
            rn = w & 0xF
            mnem = SINGLE_OPS[op]
            if mnem == "RETI":
                return Insn(addr, 2, words, "RETI", [], kind="reti")
            if mnem in ("SWPB", "SXT", "CALL") and bw:
                return Insn(addr, 2, words, ".word", [f"0x{w:04X}"], kind="invalid")
            o, pc = self._src_operand(rn, As, pc, words, bw)
            if o is None:
                return Insn(addr, 2, words, ".word", [f"0x{w:04X}"], kind="invalid")
            suffix = ".B" if bw and mnem in ("RRC", "RRA", "PUSH") else ""
            ins = Insn(addr, pc - addr, words, mnem + suffix, [o.text], bw=bw)
            if mnem == "CALL":
                ins.kind = "call"
                if o.mode == "imm":
                    ins.target = o.imm
                elif o.mode in ("abs", "sym"):
                    ins.src_abs = o.abs_addr
            elif mnem == "PUSH":
                ins.src_imm = o.imm
            return ins

        # --- формат I: двухоперандные ---
        opc = (w >> 12) & 0xF
        if opc < 4:
            return Insn(addr, 2, words, ".word", [f"0x{w:04X}"], kind="invalid")
        mnem = DOUBLE_OPS[opc]
        sreg = (w >> 8) & 0xF
        Ad = (w >> 7) & 1
        bw = bool((w >> 6) & 1)
        As = (w >> 4) & 3
        dreg = w & 0xF

        src, pc = self._src_operand(sreg, As, pc, words, bw)
        if src is None:
            return Insn(addr, 2, words, ".word", [f"0x{w:04X}"], kind="invalid")
        dst, pc = self._dst_operand(dreg, Ad, pc, words)
        if dst is None:
            return Insn(addr, 2, words, ".word", [f"0x{w:04X}"], kind="invalid")

        suffix = ".B" if bw else ""
        ins = Insn(addr, pc - addr, words, mnem + suffix, [src.text, dst.text],
                   bw=bw, src_imm=src.imm, src_abs=src.abs_addr,
                   dst_abs=dst.abs_addr)

        # переходы, реализованные через MOV в PC
        if mnem == "MOV" and dst.is_reg and dreg == 0:
            if sreg == 1 and As == 3:          # MOV @SP+,PC == RET
                return Insn(addr, pc - addr, words, "RET", [], kind="ret")
            ins.kind = "jump"
            ins.mnem = "BR"
            ins.ops = [src.text]
            if src.mode == "imm":
                ins.target = src.imm
            elif src.mode in ("abs", "sym"):
                ins.src_abs = src.abs_addr
            else:
                ins.target = None
            return ins

        self._emulate(ins, mnem, src, dst, sreg, As, dreg, Ad, bw, suffix)
        return ins

    @staticmethod
    def _emulate(ins: Insn, mnem: str, src: Operand, dst: Operand,
                 sreg: int, As: int, dreg: int, Ad: int, bw: bool, suffix: str):
        """Замена базовых команд эмулируемыми мнемониками (как в TI asm430)."""
        imm = src.imm if src.mode in ("const", "imm") else None

        if mnem == "MOV":
            if imm == 0:
                ins.mnem, ins.ops = "CLR" + suffix, [dst.text]
            elif sreg == 1 and As == 3:
                ins.mnem, ins.ops = "POP" + suffix, [dst.text]
            elif src.mode == "reg" and dst.mode == "reg" and sreg == 3 and dreg == 3:
                ins.mnem, ins.ops = "NOP", []
        elif mnem == "ADD":
            if imm == 1:
                ins.mnem, ins.ops = "INC" + suffix, [dst.text]
            elif imm == 2:
                ins.mnem, ins.ops = "INCD" + suffix, [dst.text]
            elif src.mode == "reg" and dst.mode == "reg" and sreg == dreg:
                ins.mnem, ins.ops = "RLA" + suffix, [dst.text]
        elif mnem == "ADDC":
            if imm == 0:
                ins.mnem, ins.ops = "ADC" + suffix, [dst.text]
            elif src.mode == "reg" and dst.mode == "reg" and sreg == dreg:
                ins.mnem, ins.ops = "RLC" + suffix, [dst.text]
        elif mnem == "SUB":
            if imm == 1:
                ins.mnem, ins.ops = "DEC" + suffix, [dst.text]
            elif imm == 2:
                ins.mnem, ins.ops = "DECD" + suffix, [dst.text]
        elif mnem == "SUBC" and imm == 0:
            ins.mnem, ins.ops = "SBC" + suffix, [dst.text]
        elif mnem == "DADD" and imm == 0:
            ins.mnem, ins.ops = "DADC" + suffix, [dst.text]
        elif mnem == "CMP" and imm == 0:
            ins.mnem, ins.ops = "TST" + suffix, [dst.text]
        elif mnem == "XOR" and imm == 0xFFFF:
            ins.mnem, ins.ops = "INV" + suffix, [dst.text]
        elif mnem == "BIC" and dst.mode == "reg" and dreg == 2 and imm is not None:
            ins.mnem, ins.ops = {1: "CLRC", 2: "CLRZ", 4: "CLRN",
                                 8: "DINT"}.get(imm, ins.mnem), \
                ([] if imm in (1, 2, 4, 8) else ins.ops)
        elif mnem == "BIS" and dst.mode == "reg" and dreg == 2 and imm is not None:
            ins.mnem, ins.ops = {1: "SETC", 2: "SETZ", 4: "SETN",
                                 8: "EINT"}.get(imm, ins.mnem), \
                ([] if imm in (1, 2, 4, 8) else ins.ops)


def s16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v
