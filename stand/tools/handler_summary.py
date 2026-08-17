#!/usr/bin/env python3
"""Для каждого обработчика команды/подкоманды извлекает семантическую сводку:
проверку длины запроса, читаемые и записываемые ячейки, вызовы, размер ответа.
"""
import json, re
from collections import deque
from msp430dis import Mem, disasm_one, render

img = open('fw.bin', 'rb').read()
mem = Mem(img, 0)
CODE_LO, CODE_HI = 0x1100, 0xFFDF
ERR = 0xB842  # общий обработчик «неверная команда»

# Имена ключевых RAM-переменных, восстановленные из анализа.
NAMED = {
    0x04FE: 'NET_ADDR', 0x04FD: 'chan_index', 0x04E0: 'uart_cfg',
    0x06B4: 'frame_ptr', 0x06B3: 'resp_flags', 0x07DF: 'subcmd',
    0x032C: 'BTN_FLAGS', 0x083D: 'lcd_page', 0x039F: 'UI_flags',
    0x0300: 'energy0', 0x0302: 'energy0h', 0x0306: 'energy_div',
    0x0500: 'cal0', 0x0508: 'cal_crc',
}


def peripheral(a):
    if a < 0x0200:
        return True
    return False


def walk(entry, limit=400):
    """Обходит тело обработчика (BFS по переходам) до ret/reti/br-наружу."""
    seen = set()
    q = deque([entry])
    reads, writes, calls, cmps, respw = set(), set(), set(), [], []
    stops_at = set()
    while q and len(seen) < limit:
        a = q.popleft()
        while CODE_LO <= a <= CODE_HI and a not in seen:
            ins = disasm_one(mem, a)
            if not ins:
                break
            seen.add(a)
            txt = render(ins)
            # проверки длины: cmp #N, r8  (r8 = длина полученного кадра)
            m = re.match(r'cmp(?:\.b)?\s+#(0x[0-9a-f]+|-?\d+),\s+r8$', txt)
            if m:
                cmps.append(int(m.group(1), 16) if m.group(1).startswith('0x') else int(m.group(1)))
            # операнды памяти
            for role, op in (('s', ins.src), ('d', ins.dst)):
                if op and op.startswith('&0x'):
                    v = int(op[3:], 16)
                    if role == 's':
                        reads.add(v)
                    else:
                        writes.add(v)
            # запись в буфер ответа: X(r7)
            m2 = re.search(r',\s+(-?\w+)?\(r7\)$', txt)
            if m2:
                respw.append((a, txt))
            if ins.is_call and ins.target:
                calls.add(ins.target)
            # переход-наружу к ERR / общий возврат
            if ins.mn in ('br',) and ins.target:
                if ins.target == ERR:
                    stops_at.add('ERR')
                elif ins.target and CODE_LO <= ins.target <= CODE_HI:
                    if ins.target not in seen:
                        q.append(ins.target)
                break
            if ins.target is not None and ins.mn.startswith('j'):
                if ins.target not in seen:
                    q.append(ins.target)
            if ins.is_ret or ins.mn == 'reti':
                break
            if ins.stops:
                break
            a += ins.size
    return dict(reads=sorted(reads), writes=sorted(writes),
                calls=sorted(calls), cmps=cmps, respw=respw, stops=sorted(stops_at))


def classify(v):
    if v < 0x0200:
        return 'periph'
    if 0x1000 <= v < 0x1100:
        return 'INFO'
    if 0x0200 <= v < 0x0A00:
        return 'RAM'
    if v >= 0x1100:
        return 'FLASH'
    return '?'


def fmt_addrs(lst, kind=None):
    out = []
    for v in lst:
        if v < 0x0200:
            continue  # периферию опускаем в сводке данных
        tag = NAMED.get(v, '0x%04X' % v)
        out.append(tag)
    return ' '.join(out) if out else '—'


if __name__ == '__main__':
    H = json.load(open('handlers.json'))
    print('# Сводка обработчиков (данные RAM/INFO/FLASH; периферия опущена)\n')
    cmds = [('0x00 тест связи', 0x8498), ('0x01 открыть канал', 0x84F4),
            ('0x02 закрыть канал', 0x8590), ('0x03 запись', 0x85B2),
            ('0x04 запись расш.', 0xA0FE), ('0x05 чтение массивов', 0xA3B6),
            ('0x06 спец', 0xA7C6), ('0x07 чтение всп.', 0xAAEC),
            ('0x08 чтение параметров', 0xAD98)]
    for name, a in cmds:
        s = walk(a)
        print('## CMD %s  @0x%04X' % (name, a))
        print('   длина(cmp r8): %s' % (s['cmps'] or '—'))
        print('   читает: %s' % fmt_addrs(s['reads']))
        print('   пишет : %s' % fmt_addrs(s['writes']))
        print()
    for cmd, base_n in (('03', 0x85D8), ('05', 0xA432), ('06', 0xA84A),
                        ('07', 0xAB2E), ('08', 0xAE18)):
        print('\n### Подкоманды CMD 0x%s' % cmd)
        tab = H['subtabs'][cmd]
        for i, h in enumerate(tab):
            if not h or h == ERR:
                continue
            s = walk(h)
            print('  sub 0x%02X @0x%04X | len=%s | rd:%s | wr:%s | resp:%d' % (
                i, h, s['cmps'] or '-', fmt_addrs(s['reads']),
                fmt_addrs(s['writes']), len(s['respw'])))
