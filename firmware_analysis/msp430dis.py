#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
msp430dis.py — дизассемблер прошивок MSP430 (ядро MSP430, форматы I/II/Jump)
с загрузчиком Intel HEX, рекурсивным обходом кода от таблицы векторов
и символическими именами регистров периферии.

Использование:
    python3 msp430dis.py firmware/201.2_2.hex -o disasm.lst
    python3 msp430dis.py firmware/201.2_2.hex --map      # карта памяти / векторы
    python3 msp430dis.py firmware/201.2_2.hex --strings   # печатные строки
    python3 msp430dis.py firmware/201.2_2.hex --sfr       # какие регистры периферии используются
"""

import sys
import argparse
from collections import defaultdict

# ---------------------------------------------------------------- Intel HEX

def load_ihex(path):
    """Возвращает dict {address: byte}."""
    mem = {}
    seg = 0        # для записей типа 02 (segment)
    upper = 0      # для записей типа 04 (linear)
    with open(path, 'r') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            if not line.startswith(':'):
                raise ValueError('строка %d: нет двоеточия' % lineno)
            data = bytes.fromhex(line[1:])
            if (sum(data) & 0xFF) != 0:
                raise ValueError('строка %d: неверная контрольная сумма' % lineno)
            n, ah, al, rtype = data[0], data[1], data[2], data[3]
            payload = data[4:4 + n]
            addr = (ah << 8) | al
            if rtype == 0x00:
                base = (upper << 16) + (seg << 4)
                for i, b in enumerate(payload):
                    mem[base + addr + i] = b
            elif rtype == 0x01:
                break
            elif rtype == 0x02:
                seg = (payload[0] << 8) | payload[1]
            elif rtype == 0x04:
                upper = (payload[0] << 8) | payload[1]
                seg = 0
            elif rtype in (0x03, 0x05):
                pass   # стартовый адрес — для MSP430 не используется
            else:
                raise ValueError('строка %d: неизвестный тип записи %02X' % (lineno, rtype))
    return mem


def ranges(mem):
    """Непрерывные диапазоны занятой памяти."""
    out = []
    addrs = sorted(mem)
    if not addrs:
        return out
    start = prev = addrs[0]
    for a in addrs[1:]:
        if a != prev + 1:
            out.append((start, prev))
            start = a
        prev = a
    out.append((start, prev))
    return out


# ---------------------------------------------------------------- регистры

REGS = ['PC', 'SP', 'SR', 'CG2'] + ['R%d' % i for i in range(4, 16)]

# Периферия MSP430 1xx/2xx (общая карта; имена, встречающиеся в этой прошивке,
# уточнены по семейству MSP430F1xx с двумя USART).
SFR = {
    0x0000: 'IE1', 0x0001: 'IE2', 0x0002: 'IFG1', 0x0003: 'IFG2',
    0x0004: 'ME1', 0x0005: 'ME2',
    0x0020: 'P1IN', 0x0021: 'P1OUT', 0x0022: 'P1DIR', 0x0023: 'P1IFG',
    0x0024: 'P1IES', 0x0025: 'P1IE', 0x0026: 'P1SEL',
    0x0028: 'P2IN', 0x0029: 'P2OUT', 0x002A: 'P2DIR', 0x002B: 'P2IFG',
    0x002C: 'P2IES', 0x002D: 'P2IE', 0x002E: 'P2SEL',
    0x0018: 'P3IN', 0x0019: 'P3OUT', 0x001A: 'P3DIR', 0x001B: 'P3SEL',
    0x001C: 'P4IN', 0x001D: 'P4OUT', 0x001E: 'P4DIR', 0x001F: 'P4SEL',
    0x0030: 'P5IN', 0x0031: 'P5OUT', 0x0032: 'P5DIR', 0x0033: 'P5SEL',
    0x0034: 'P6IN', 0x0035: 'P6OUT', 0x0036: 'P6DIR', 0x0037: 'P6SEL',
    0x0038: 'P7IN', 0x0039: 'P7OUT', 0x003A: 'P7DIR', 0x003B: 'P7SEL',
    0x003C: 'P8IN', 0x003D: 'P8OUT', 0x003E: 'P8DIR', 0x003F: 'P8SEL',
    0x0053: 'DCOCTL', 0x0056: 'BCSCTL1', 0x0057: 'BCSCTL2', 0x0058: 'BCSCTL3',
    0x0059: 'DCOCTL2',
    0x0120: 'WDTCTL',
    # USART0
    0x0070: 'U0CTL', 0x0071: 'U0TCTL', 0x0072: 'U0RCTL',
    0x0073: 'U0MCTL', 0x0074: 'U0BR0', 0x0075: 'U0BR1',
    0x0076: 'U0RXBUF', 0x0077: 'U0TXBUF',
    # USART1
    0x0078: 'U1CTL', 0x0079: 'U1TCTL', 0x007A: 'U1RCTL',
    0x007B: 'U1MCTL', 0x007C: 'U1BR0', 0x007D: 'U1BR1',
    0x007E: 'U1RXBUF', 0x007F: 'U1TXBUF',
    # USCI_A0 / USCI_B0 (2xx) — те же адреса 0x60..0x6F/0x68..
    0x0060: 'UCA0CTL0', 0x0061: 'UCA0CTL1', 0x0062: 'UCA0BR0', 0x0063: 'UCA0BR1',
    0x0064: 'UCA0MCTL', 0x0065: 'UCA0STAT', 0x0066: 'UCA0RXBUF', 0x0067: 'UCA0TXBUF',
    0x0068: 'UCA0ABCTL', 0x0069: 'UCA0IRTCTL', 0x006A: 'UCA0IRRCTL',
    # Timer_A
    0x0160: 'TACTL', 0x0162: 'TACCTL0', 0x0164: 'TACCTL1', 0x0166: 'TACCTL2',
    0x0170: 'TAR', 0x0172: 'TACCR0', 0x0174: 'TACCR1', 0x0176: 'TACCR2',
    0x012E: 'TAIV',
    # Timer_B
    0x0180: 'TBCTL', 0x0182: 'TBCCTL0', 0x0184: 'TBCCTL1', 0x0186: 'TBCCTL2',
    0x0188: 'TBCCTL3', 0x018A: 'TBCCTL4', 0x018C: 'TBCCTL5', 0x018E: 'TBCCTL6',
    0x0190: 'TBR', 0x0192: 'TBCCR0', 0x0194: 'TBCCR1', 0x0196: 'TBCCR2',
    0x0198: 'TBCCR3', 0x019A: 'TBCCR4', 0x019C: 'TBCCR5', 0x019E: 'TBCCR6',
    0x011E: 'TBIV',
    # Flash controller
    0x0128: 'FCTL1', 0x012A: 'FCTL2', 0x012C: 'FCTL3',
    # Comparator_A
    0x0059: 'CACTL1', 0x005A: 'CACTL2', 0x005B: 'CAPD',
    # ADC12
    0x01A0: 'ADC12CTL0', 0x01A2: 'ADC12CTL1', 0x01A4: 'ADC12IFG',
    0x01A6: 'ADC12IE', 0x01A8: 'ADC12IV',
    # DMA
    0x0122: 'DMACTL0', 0x0124: 'DMACTL1', 0x0126: 'DMAIV',
    0x01D0: 'DMA0CTL', 0x01D2: 'DMA0SA', 0x01D4: 'DMA0DA', 0x01D6: 'DMA0SZ',
    0x01D8: 'DMA1CTL', 0x01DA: 'DMA1SA', 0x01DC: 'DMA1DA', 0x01DE: 'DMA1SZ',
    0x01E0: 'DMA2CTL', 0x01E2: 'DMA2SA', 0x01E4: 'DMA2DA', 0x01E6: 'DMA2SZ',
}

# Именованные ячейки ОЗУ и функции — восстановлены при анализе.
RAM_NAMES = {
    0x0200: 'bcd_a', 0x0208: 'clk_hh', 0x0209: 'clk_mm', 0x020A: 'clk_ss',
    0x0212: 'sec_frac',
    0x0218: 'status', 0x021A: 'flags2',
    0x0225: 'disp_page',
    0x022E: 'rx_timeout', 0x0230: 'frame_len', 0x0232: 'rx_ptr',
    0x0234: 'frame_buf', 0x0238: 'cmd_byte', 0x0239: 'resp_buf',
    0x024A: 'led_cnt', 0x024C: 'led_timer', 0x024E: 'loop_cnt',
    0x0255: 'dummy_reg', 0x0257: 'clk_tick', 0x025A: 'sys_ticks',
    0x025C: 'uart_enabled',
    0x0294: 'shadow_1000',
}
FUNC_NAMES = {
    0xEB7C: 'init_clock_io', 0xEC02: 'init_vars', 0xECBA: 'uart_enable',
    0xECE6: 'lcd_clear', 0xEE2E: 'reset',
    0xE000: 'proto_service', 0xE404: 'proto_dispatch', 0xE4A0: 'cmd_lookup',
    0xE5B8: 'crc16_modbus', 0xE3F6: 'shift_helper',
    0xF350: 'bcd_add', 0xF412: 'bcd_sub', 0xF610: 'bcd_cmp', 0xF554: 'bcd_inc',
    0xF682: 'memset', 0xF69C: 'memset_b',
    0xF98A: 'display_update', 0xFBFC: 'clk_advance',
}

VECTORS = [
    (0xFFE0, 'DAC12/DMA'),
    (0xFFE2, 'USART1_TX / USCI_A1_TX'),
    (0xFFE4, 'USART1_RX / USCI_A1_RX'),
    (0xFFE6, 'PORT2'),
    (0xFFE8, 'PORT1'),
    (0xFFEA, 'TIMERA1 (TAIV)'),
    (0xFFEC, 'TIMERA0 (TACCR0)'),
    (0xFFEE, 'ADC12'),
    (0xFFF0, 'USART0_TX / USCI_A0_TX'),
    (0xFFF2, 'USART0_RX / USCI_A0_RX'),
    (0xFFF4, 'WDT'),
    (0xFFF6, 'COMPARATOR_A'),
    (0xFFF8, 'TIMERB1 (TBIV)'),
    (0xFFFA, 'TIMERB0 (TBCCR0)'),
    (0xFFFC, 'NMI/OSC/FLASH'),
    (0xFFFE, 'RESET'),
]

# ---------------------------------------------------------------- ядро

DOUBLE_OPS = {0x4: 'MOV', 0x5: 'ADD', 0x6: 'ADDC', 0x7: 'SUBC', 0x8: 'SUB',
              0x9: 'CMP', 0xA: 'DADD', 0xB: 'BIT', 0xC: 'BIC', 0xD: 'BIS',
              0xE: 'XOR', 0xF: 'AND'}

SINGLE_OPS = {0: 'RRC', 1: 'SWPB', 2: 'RRA', 3: 'SXT',
              4: 'PUSH', 5: 'CALL', 6: 'RETI'}

JUMPS = {0: 'JNZ', 1: 'JZ', 2: 'JNC', 3: 'JC', 4: 'JN', 5: 'JGE', 6: 'JL', 7: 'JMP'}


class Insn(object):
    __slots__ = ('addr', 'size', 'words', 'mnem', 'ops', 'target', 'flow',
                 'raw', 'comment')

    def __init__(self, addr):
        self.addr = addr
        self.size = 2
        self.words = []
        self.mnem = '.word'
        self.ops = []
        self.target = None    # адрес перехода/вызова, если известен
        self.flow = 'seq'     # seq | jmp | cond | call | ret | invalid
        self.raw = ''         # неэмулированная форма
        self.comment = ''

    def text(self):
        if self.ops:
            return '%-6s %s' % (self.mnem, ', '.join(self.ops))
        return self.mnem


class Disassembler(object):
    def __init__(self, mem, symbols=None):
        self.mem = mem
        self.symbols = symbols or {}

    # --- доступ к памяти
    def byte(self, a):
        return self.mem.get(a, 0xFF)

    def word(self, a):
        return self.byte(a) | (self.byte(a + 1) << 8)

    def has(self, a):
        return a in self.mem

    def label(self, a, prefix='L'):
        if a in self.symbols:
            return self.symbols[a]
        if a in SFR:
            return SFR[a]
        return '0x%04X' % a

    def addrname(self, a):
        """Имя для абсолютного адреса (периферия/символ/число)."""
        if a in SFR:
            return SFR[a]
        if a in RAM_NAMES:
            return RAM_NAMES[a]
        if a in self.symbols:
            return self.symbols[a]
        return '0x%04X' % a

    # --- операнды
    def _src(self, reg, As, pc_next):
        """Возвращает (текст, съедено_слов, абсолютный_адрес_или_None)."""
        if reg == 3:                                    # CG2
            return ({0: '#0', 1: '#1', 2: '#2', 3: '#-1'}[As], 0, None)
        if reg == 2:                                    # SR / CG1
            if As == 0:
                return ('SR', 0, None)
            if As == 1:
                x = self.word(pc_next)
                return ('&' + self.addrname(x), 1, x)
            return ({2: '#4', 3: '#8'}[As], 0, None)
        if reg == 0:                                    # PC
            if As == 1:
                x = self.word(pc_next)
                t = (pc_next + to_signed(x)) & 0xFFFF   # символьный режим
                return (self.label(t), 1, t)
            if As == 3:
                x = self.word(pc_next)
                return ('#0x%04X' % x, 1, x)
        r = REGS[reg]
        if As == 0:
            return (r, 0, None)
        if As == 1:
            x = self.word(pc_next)
            return ('%s(%s)' % (signed_hex(x), r), 1, None)
        if As == 2:
            return ('@' + r, 0, None)
        return ('@%s+' % r, 0, None)

    def _dst(self, reg, Ad, pc_next):
        if Ad == 0:
            return (REGS[reg], 0, None)
        if reg == 0:
            x = self.word(pc_next)
            t = (pc_next + to_signed(x)) & 0xFFFF
            return (self.label(t), 1, t)
        if reg == 2:
            x = self.word(pc_next)
            return ('&' + self.addrname(x), 1, x)
        x = self.word(pc_next)
        return ('%s(%s)' % (signed_hex(x), REGS[reg]), 1, None)

    # --- декодирование одной инструкции
    def decode(self, addr):
        ins = Insn(addr)
        w = self.word(addr)
        ins.words = [w]

        if (w & 0xF800) == 0x1800:
            # префикс расширения MSP430X — данной прошивке не свойственно
            ins.mnem = '.word'
            ins.ops = ['0x%04X' % w]
            ins.comment = 'MSP430X extension word?'
            ins.flow = 'invalid'
            return ins

        top = (w >> 12) & 0xF

        # ---- формат II (одноместные)
        if (w & 0xFC00) == 0x1000:
            op = (w >> 7) & 7
            bw = (w >> 6) & 1
            Ad = (w >> 4) & 3
            reg = w & 0xF
            if op not in SINGLE_OPS:
                ins.mnem = '.word'
                ins.ops = ['0x%04X' % w]
                ins.flow = 'invalid'
                return ins
            mnem = SINGLE_OPS[op]
            if mnem == 'RETI':
                ins.mnem = 'RETI'
                ins.flow = 'ret'
                return ins
            # у одноместных операнд кодируется как источник (As == Ad)
            txt, extra, absaddr = self._src(reg, Ad, addr + 2)
            ins.size = 2 + 2 * extra
            for i in range(extra):
                ins.words.append(self.word(addr + 2 + 2 * i))
            suffix = '.B' if bw else ''
            ins.mnem = mnem + suffix
            ins.ops = [txt]
            ins.raw = ins.text()
            if mnem == 'CALL':
                ins.flow = 'call'
                if reg == 0 and Ad == 3:                # CALL #imm
                    ins.target = absaddr
            elif mnem == 'PUSH':
                ins.flow = 'seq'
            return ins

        # ---- переходы
        if top in (0x2, 0x3):
            cond = (w >> 10) & 7
            off = w & 0x3FF
            if off & 0x200:
                off -= 0x400
            t = (addr + 2 + off * 2) & 0xFFFF
            ins.mnem = JUMPS[cond]
            ins.ops = [self.label(t)]
            ins.target = t
            ins.flow = 'jmp' if cond == 7 else 'cond'
            ins.raw = ins.text()
            return ins

        # ---- формат I (двухместные)
        if top >= 0x4:
            sreg = (w >> 8) & 0xF
            Ad = (w >> 7) & 1
            bw = (w >> 6) & 1
            As = (w >> 4) & 3
            dreg = w & 0xF
            stxt, sx, sabs = self._src(sreg, As, addr + 2)
            dtxt, dx, dabs = self._dst(dreg, Ad, addr + 2 + 2 * sx)
            ins.size = 2 + 2 * (sx + dx)
            for i in range(sx + dx):
                ins.words.append(self.word(addr + 2 + 2 * i))
            suffix = '.B' if bw else ''
            mnem = DOUBLE_OPS[top] + suffix
            ins.mnem = mnem
            ins.ops = [stxt, dtxt]
            ins.raw = ins.text()

            # поток управления
            if dreg == 0 and Ad == 0:                   # запись в PC
                if top == 0x4:                          # MOV ...,PC == BR
                    ins.flow = 'jmp'
                    if sreg == 0 and As == 3:
                        ins.target = sabs
                    if sreg == 1 and As == 3:           # MOV @SP+,PC == RET
                        ins.flow = 'ret'
                else:
                    ins.flow = 'jmp'
            self._emulate(ins, top, bw, sreg, As, dreg, Ad, stxt, dtxt)
            return ins

        # ---- 0x0000..0x0FFF: в MSP430 (не X) не используется
        ins.mnem = '.word'
        ins.ops = ['0x%04X' % w]
        ins.flow = 'invalid'
        return ins

    def _emulate(self, ins, top, bw, sreg, As, dreg, Ad, stxt, dtxt):
        """Замена на эмулируемые мнемоники (RET/POP/BR/CLR/INC/...)."""
        sfx = '.B' if bw else ''
        is_const = (sreg == 3)                        # генератор констант CG2
        cval = {0: 0, 1: 1, 2: 2, 3: 0xFFFF}.get(As) if is_const else None

        def set(m, ops):
            ins.mnem = m
            ins.ops = ops

        if top == 0x4:                                 # MOV
            if sreg == 1 and As == 3:                  # @SP+
                if dreg == 0 and Ad == 0:
                    set('RET', [])
                    return
                set('POP' + sfx, [dtxt])
                return
            if dreg == 0 and Ad == 0:
                set('BR', [stxt])
                return
            if is_const and cval == 0:
                set('CLR' + sfx, [dtxt])
                return
        elif top == 0x5:                               # ADD
            if is_const and cval == 1:
                set('INC' + sfx, [dtxt]); return
            if is_const and cval == 2:
                set('INCD' + sfx, [dtxt]); return
            if stxt == dtxt and As == 0 and Ad == 0:
                set('RLA' + sfx, [dtxt]); return
        elif top == 0x6:                               # ADDC
            if is_const and cval == 0:
                set('ADC' + sfx, [dtxt]); return
            if stxt == dtxt and As == 0 and Ad == 0:
                set('RLC' + sfx, [dtxt]); return
        elif top == 0x7:                               # SUBC
            if is_const and cval == 0:
                set('SBC' + sfx, [dtxt]); return
        elif top == 0x8:                               # SUB
            if is_const and cval == 1:
                set('DEC' + sfx, [dtxt]); return
            if is_const and cval == 2:
                set('DECD' + sfx, [dtxt]); return
        elif top == 0x9:                               # CMP
            if is_const and cval == 0:
                set('TST' + sfx, [dtxt]); return
        elif top == 0xA:                               # DADD
            if is_const and cval == 0:
                set('DADC' + sfx, [dtxt]); return
        elif top == 0xC:                               # BIC
            if dreg == 2 and Ad == 0 and is_const:
                m = {1: 'CLRC', 2: 'CLRZ', 4: 'CLRN'}.get(cval)
                if m:
                    set(m, []); return
            if dtxt == 'SR' and stxt == '#8':
                set('DINT', []); return
        elif top == 0xD:                               # BIS
            if dreg == 2 and Ad == 0 and is_const:
                m = {1: 'SETC', 2: 'SETZ', 4: 'SETN'}.get(cval)
                if m:
                    set(m, []); return
            if dtxt == 'SR' and stxt == '#8':
                set('EINT', []); return
        elif top == 0xE:                               # XOR
            if is_const and cval == 0xFFFF:
                set('INV' + sfx, [dtxt]); return


def to_signed(x):
    return x - 0x10000 if x & 0x8000 else x


def signed_hex(x):
    s = to_signed(x)
    return ('-0x%X' % -s) if s < 0 else ('0x%X' % s)


# ---------------------------------------------------------------- обход кода

def trace(dis, entries):
    """Рекурсивный обход. Возвращает (insns, calls, xrefs)."""
    insns = {}
    calls = set()
    xrefs = defaultdict(set)
    work = list(entries)
    seen = set()
    while work:
        pc = work.pop()
        while True:
            if pc in seen or not dis.has(pc):
                break
            ins = dis.decode(pc)
            seen.add(pc)
            insns[pc] = ins
            if ins.flow == 'invalid':
                break
            if ins.target is not None:
                xrefs[ins.target].add(pc)
                if ins.flow in ('call', 'cond', 'jmp'):
                    if ins.flow == 'call':
                        calls.add(ins.target)
                    if dis.has(ins.target) and ins.target not in seen:
                        work.append(ins.target)
            if ins.flow in ('ret', 'jmp'):
                break
            pc += ins.size
    return insns, calls, xrefs


def find_pointer_tables(dis, mem, lo, hi, minlen=4):
    """Ищет таблицы 16-битных указателей внутри кодовой области.

    Такие таблицы генерирует компилятор для switch/case и для массивов
    обработчиков команд; без них рекурсивный обход не находит целые ветки.
    """
    tables = []
    a = lo
    while a < hi - 1:
        ptrs = []
        b = a
        while b < hi - 1:
            v = dis.word(b)
            if lo <= v <= hi and v % 2 == 0 and v in mem:
                ptrs.append(v)
                b += 2
            else:
                break
        if len(ptrs) >= minlen:
            tables.append((a, ptrs))
            a = b
        else:
            a += 2
    return tables


def sweep_gaps(dis, mem, insns, lo, hi):
    """Линейный доразбор участков, не покрытых рекурсивным обходом."""
    covered = set()
    for a, ins in insns.items():
        covered.update(range(a, a + ins.size))
    extra = {}
    a = lo
    while a <= hi:
        if a in covered or a not in mem:
            a += 1
            continue
        ins = dis.decode(a)
        if ins.flow != 'invalid' and all((a + k) not in covered
                                         for k in range(ins.size)):
            extra[a] = ins
            ins.comment = (ins.comment + ' ').strip() + '[линейный разбор]'
            a += ins.size
        else:
            a += 2
    return extra


def build_symbols(dis, entries, insns, calls, xrefs):
    sym = {}
    for a, name in reversed(VECTORS):        # RESET (0xFFFE) первым
        t = dis.word(a)
        if t != 0xFFFF and dis.has(t):
            n = name.split(' ')[0].split('/')[0]
            sym.setdefault(t, 'reset' if a == 0xFFFE else 'isr_' + n.lower())
    for t, nm in FUNC_NAMES.items():
        if dis.has(t):
            sym[t] = nm
    for t in sorted(calls):
        sym.setdefault(t, 'sub_%04X' % t)
    for t in sorted(xrefs):
        if dis.has(t):
            sym.setdefault(t, 'loc_%04X' % t)
    return sym


# ---------------------------------------------------------------- вывод

def emit(dis, insns, xrefs, out, mem):
    lines = []
    addrs = sorted(mem)
    i = 0
    while i < len(addrs):
        a = addrs[i]
        if a in insns:
            ins = insns[a]
            if a in dis.symbols and (a in xrefs or dis.symbols[a].startswith(('sub_', 'isr_'))):
                lines.append('')
                refs = ', '.join('0x%04X' % r for r in sorted(xrefs.get(a, ())))
                lines.append('%s:%s' % (dis.symbols[a],
                                        ('   ; xrefs: ' + refs) if refs else ''))
            hexs = ' '.join('%04X' % w for w in ins.words)
            cmt = ''
            if ins.raw and ins.raw != ins.text():
                cmt = '  ; = %s' % ins.raw
            if ins.comment:
                cmt += '  ; ' + ins.comment
            lines.append('  %04X:  %-15s %-28s%s' % (a, hexs, ins.text(), cmt))
            i += ins.size
        else:
            # данные: группируем по 16 байт
            chunk = []
            start = a
            while i < len(addrs) and len(chunk) < 16 and addrs[i] not in insns:
                if chunk and addrs[i] != start + len(chunk):
                    break
                chunk.append(mem[addrs[i]])
                i += 1
            txt = ''.join(chr(c) if 32 <= c < 127 else '.' for c in chunk)
            lines.append('  %04X:  %-47s |%s|' %
                         (start, ' '.join('%02X' % c for c in chunk), txt))
    out.write('\n'.join(lines) + '\n')


def find_strings(mem, minlen=4):
    out = []
    cur = []
    start = None
    for a in sorted(mem):
        c = mem[a]
        if 32 <= c < 127:
            if not cur:
                start = a
            cur.append(chr(c))
        else:
            if len(cur) >= minlen:
                out.append((start, ''.join(cur)))
            cur = []
    if len(cur) >= minlen:
        out.append((start, ''.join(cur)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('hexfile')
    ap.add_argument('-o', '--output')
    ap.add_argument('--map', action='store_true')
    ap.add_argument('--strings', action='store_true')
    ap.add_argument('--sfr', action='store_true')
    args = ap.parse_args()

    mem = load_ihex(args.hexfile)
    dis = Disassembler(mem)

    if args.map:
        print('Занятые области памяти:')
        for s, e in ranges(mem):
            print('  0x%04X-0x%04X  %6d байт' % (s, e, e - s + 1))
        print('\nТаблица векторов прерываний:')
        for a, name in VECTORS:
            v = dis.word(a)
            mark = '' if v != 0xFFFF else '   (не используется)'
            print('  0x%04X  %-26s -> 0x%04X%s' % (a, name, v, mark))
        return

    if args.strings:
        for a, s in find_strings(mem):
            print('0x%04X  %r' % (a, s))
        return

    entries = []
    for a, _ in VECTORS:
        t = dis.word(a)
        if t != 0xFFFF and t in mem:
            entries.append(t)

    rr = [(s, e) for s, e in ranges(mem) if s >= 0x8000 and e < 0xFFE0]
    lo = min(a for a in mem if 0x8000 <= a < 0xFFE0 and mem[a] != 0xFF)
    hi = max(a for a in mem if 0x8000 <= a < 0xFFE0 and mem[a] != 0xFF)

    insns, calls, xrefs = trace(dis, entries)
    # указатели из таблиц switch/case и таблиц обработчиков
    for base, ptrs in find_pointer_tables(dis, mem, lo, hi):
        entries.extend(ptrs)
    insns, calls, xrefs = trace(dis, entries)
    dis.symbols = build_symbols(dis, entries, insns, calls, xrefs)
    insns, calls, xrefs = trace(dis, entries)          # проход с именами
    insns.update(sweep_gaps(dis, mem, insns, lo, hi))

    if args.sfr:
        used = defaultdict(int)
        for ins in insns.values():
            for op in ins.ops:
                nm = op.lstrip('&#@').rstrip('+')
                for addr, name in SFR.items():
                    if nm == name:
                        used[name] += 1
        for name, n in sorted(used.items(), key=lambda kv: -kv[1]):
            print('%-10s %d обращений' % (name, n))
        return

    out = open(args.output, 'w') if args.output else sys.stdout
    out.write('; Дизассемблирование %s\n' % args.hexfile)
    out.write('; Инструкций найдено: %d, подпрограмм: %d\n\n' % (len(insns), len(calls)))
    emit(dis, insns, xrefs, out, mem)
    if args.output:
        out.close()
        print('Записано в %s (%d инструкций, %d подпрограмм)' %
              (args.output, len(insns), len(calls)))


if __name__ == '__main__':
    main()
