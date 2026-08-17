#!/usr/bin/env python3
"""Строит машиночитаемую карту команд (cmdmap.json) и текстовый справочник.

Для каждого обработчика извлекает:
  - проверку длины запроса (cmp #N, r8);
  - поля запроса — чтения N(r9) из принятого кадра;
  - размер и поля ответа — записи N(r7) в кадр ответа;
  - характерные источники/приёмники данных (RAM/INFO/FLASH),
    исключая общий «хвост» отправки ответа.
"""
import json, re
from collections import deque
from msp430dis import Mem, disasm_one, render

img = open('fw.bin', 'rb').read()
mem = Mem(img, 0)
CODE_LO, CODE_HI = 0x1100, 0xFFDF
ERR = 0xB842

# Адреса, относящиеся к общему коду постановки ответа в буфер передачи
# (канал A1 0x05A*, канал A0 0x083*, указатели 0x06B0/0x06B2/0x06B4, 0x0681, 0x04A4..0x04A7, 0x0828..0x082B, 0x04FF).
TAIL = {0x05A0, 0x05A4, 0x05A6, 0x05A7, 0x05AC, 0x0681, 0x06B0, 0x06B2, 0x06B4,
        0x0828, 0x082A, 0x082B, 0x0830, 0x0832, 0x0833, 0x0835, 0x0836,
        0x04A4, 0x04A6, 0x04A7, 0x04FF,
        # общая машинерия квитанции / флаги отправки
        0x04A8, 0x04AB, 0x04AC, 0x04AE, 0x06B3, 0x0542, 0x07DE, 0x0546, 0x0548}

NAMED = {
    0x04FE: 'NET_ADDR', 0x04FD: 'chan_idx', 0x04E0: 'uart_cfg', 0x04E1: 'net_addr2',
    0x04E2: 'baud_idx', 0x07DF: 'subcmd', 0x0300: 'energy_LL', 0x0302: 'energy_LH',
    0x0306: 'energy_div', 0x0308: 'energy_HL', 0x030A: 'energy_HH',
    0x0500: 'pwd_L1', 0x0508: 'pwd_crc', 0x03E8: 'meas_phaseA', 0x03F8: 'meas_phaseB',
    0x0408: 'meas_phaseC', 0x083D: 'lcd_page', 0x032C: 'btn_flags',
}


def nm(v):
    if v < 0x0200:
        return None
    return NAMED.get(v, '0x%04X' % v)


def walk(entry, limit=500):
    seen = set()
    q = deque([entry])
    reads, writes = set(), set()
    req_fields, resp_fields = set(), set()
    cmps = []
    to_err = False
    while q and len(seen) < limit:
        a = q.popleft()
        while CODE_LO <= a <= CODE_HI and a not in seen:
            ins = disasm_one(mem, a)
            if not ins:
                break
            seen.add(a)
            txt = render(ins)
            m = re.match(r'cmp(?:\.b)?\s+#(0x[0-9a-f]+|-?\d+),\s+r8$', txt)
            if m:
                v = int(m.group(1), 16) if m.group(1).startswith('0x') else int(m.group(1))
                cmps.append(v)
            # поля запроса: смещение в кадре r9
            for mm in re.finditer(r'(-?\w+)?\(r9\)', txt):
                off = mm.group(1)
                if off is None:
                    req_fields.add(0)
                else:
                    try:
                        req_fields.add(int(off, 16) if off.startswith('0x') else int(off))
                    except ValueError:
                        pass
            # поля ответа: смещение в кадре r7 (запись)
            m2 = re.search(r',\s+(-?\w+)?\(r7\)$', txt)
            if m2:
                off = m2.group(1)
                try:
                    resp_fields.add(int(off, 16) if off and off.startswith('0x')
                                    else int(off) if off else 0)
                except ValueError:
                    pass
            for role, op in (('s', ins.src), ('d', ins.dst)):
                if op and op.startswith('&0x'):
                    v = int(op[3:], 16)
                    if v in TAIL or v < 0x0200:
                        continue
                    (reads if role == 's' else writes).add(v)
            if ins.is_call and ins.target == 0xBBF6:  # CRC — часть хвоста
                pass
            if ins.mn == 'br' and ins.target:
                if ins.target == ERR:
                    to_err = True
                elif CODE_LO <= ins.target <= CODE_HI and ins.target not in seen:
                    # не углубляемся в общий хвост отправки
                    if ins.target < 0xB894 or ins.target > 0xBBF0:
                        q.append(ins.target)
                break
            if ins.target is not None and ins.mn.startswith('j') and ins.target not in seen:
                q.append(ins.target)
            if ins.is_ret or ins.mn == 'reti' or ins.stops:
                break
            a += ins.size
    return dict(cmps=sorted(set(cmps)),
                req=sorted(req_fields), resp=sorted(resp_fields),
                reads=sorted(nm(v) for v in reads if nm(v)),
                writes=sorted(nm(v) for v in writes if nm(v)),
                to_err=to_err)


CMDS = {
    0x00: ('тест связи', 0x8498, None),
    0x01: ('открыть канал', 0x84F4, None),
    0x02: ('закрыть канал', 0x8590, None),
    0x03: ('запись параметров', 0x85B2, (0x85D8, 56)),
    0x04: ('запись расширенная', 0xA0FE, None),
    0x05: ('чтение массивов', 0xA3B6, (0xA432, 7)),
    0x06: ('спец. операции', 0xA7C6, (0xA84A, 5)),
    0x07: ('чтение вспомогательное', 0xAAEC, (0xAB2E, 3)),
    0x08: ('чтение параметров', 0xAD98, (0xAE18, 42)),
}


def rdtab(base, n):
    return [(img[base + i * 4 + 2] | (img[base + i * 4 + 3] << 8))
            if img[base + i * 4] == 0x30 and img[base + i * 4 + 1] == 0x40 else None
            for i in range(n)]


if __name__ == '__main__':
    out = {}
    for cmd, (name, addr, sub) in CMDS.items():
        entry = {'name': name, 'handler': addr, 'top': walk(addr)}
        if sub:
            base, n = sub
            subs = {}
            for i, h in enumerate(rdtab(base, n)):
                if h and h != ERR:
                    subs['0x%02X' % i] = {'handler': h, **walk(h)}
            entry['subs'] = subs
            entry['sub_table'] = base
        out['0x%02X' % cmd] = entry
    json.dump(out, open('cmdmap.json', 'w'), indent=1, ensure_ascii=False)
    n_sub = sum(len(v.get('subs', {})) for v in out.values())
    print('cmdmap.json: %d команд, %d подкоманд' % (len(out), n_sub))
