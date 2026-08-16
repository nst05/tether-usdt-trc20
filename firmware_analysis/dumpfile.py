#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dumpfile.py — кодек дампов прошивки в форматах Motorola S-record (.s19/.srec)
и Intel HEX (.hex), с редактированием байтов «на месте».

Особенность: при сохранении сохраняется исходная структура записей — меняются
только затронутые байты и пересчитывается контрольная сумма их строк. Поэтому
выходной файл побайтно совпадает с исходным везде, кроме отредактированных
значений (важно для безопасной перепрошивки прибора).

Используется редактором коэффициентов dumpedit.py; работает и самостоятельно
как библиотека.
"""


class Record(object):
    """Одна запись дампа. kind: 'data' | 'other'."""
    __slots__ = ('rectype', 'addr', 'data', 'kind', 'fmt')

    def __init__(self, rectype, addr, data, kind, fmt):
        self.rectype = rectype     # напр. 'S1' или Intel-тип 0x00
        self.addr = addr
        self.data = bytearray(data)
        self.kind = kind
        self.fmt = fmt             # 'srec' | 'ihex'

    def end(self):
        return self.addr + len(self.data)


class DumpFile(object):
    def __init__(self):
        self.records = []
        self.fmt = None            # 'srec' | 'ihex'

    # --------------------------------------------------- загрузка
    @classmethod
    def load(cls, path):
        with open(path, 'r') as f:
            first = ''
            for line in f:
                s = line.strip()
                if s:
                    first = s
                    break
        f = None
        d = cls()
        if first.startswith('S'):
            d.fmt = 'srec'
            d._load_srec(path)
        elif first.startswith(':'):
            d.fmt = 'ihex'
            d._load_ihex(path)
        else:
            raise ValueError('неизвестный формат файла (ни S-record, ни Intel HEX)')
        return d

    def _load_srec(self, path):
        for lineno, raw in enumerate(open(path), 1):
            s = raw.strip()
            if not s:
                continue
            if not s.startswith('S'):
                raise ValueError('строка %d: не S-record' % lineno)
            t = s[1]
            b = bytes.fromhex(s[2:])
            count = b[0]
            body = b[1:1 + count]
            if (sum(b[:1 + count]) & 0xFF) != 0xFF:
                raise ValueError('строка %d: неверная КС S-record' % lineno)
            alen = {'0': 2, '1': 2, '2': 3, '3': 4,
                    '5': 2, '6': 3, '7': 4, '8': 3, '9': 2}.get(t)
            if alen is None:
                raise ValueError('строка %d: тип S%s не поддержан' % (lineno, t))
            addr = int.from_bytes(body[:alen], 'big')
            data = body[alen:-1]                        # минус байт КС
            is_data = t in ('1', '2', '3')
            self.records.append(Record('S' + t, addr, data,
                                       'data' if is_data else 'other', 'srec'))

    def _load_ihex(self, path):
        upper = 0
        for lineno, raw in enumerate(open(path), 1):
            s = raw.strip()
            if not s:
                continue
            b = bytes.fromhex(s[1:])
            if (sum(b) & 0xFF) != 0:
                raise ValueError('строка %d: неверная КС Intel HEX' % lineno)
            n, ah, al, rtype = b[0], b[1], b[2], b[3]
            data = b[4:4 + n]
            addr = (ah << 8) | al
            if rtype == 0x04:
                upper = (data[0] << 8) | data[1]
            full = (upper << 16) | addr if rtype == 0x00 else addr
            self.records.append(Record(rtype, full, data,
                                       'data' if rtype == 0x00 else 'other', 'ihex'))

    # --------------------------------------------------- доступ к байтам
    def get_byte(self, addr):
        for r in self.records:
            if r.kind == 'data' and r.addr <= addr < r.end():
                return r.data[addr - r.addr]
        return None

    def get_word(self, addr):
        """16-битное слово little-endian по адресу."""
        lo = self.get_byte(addr)
        hi = self.get_byte(addr + 1)
        if lo is None or hi is None:
            return None
        return lo | (hi << 8)

    def get_bytes(self, addr, n):
        return bytes(self.get_byte(addr + i) or 0 for i in range(n))

    def set_byte(self, addr, val):
        for r in self.records:
            if r.kind == 'data' and r.addr <= addr < r.end():
                r.data[addr - r.addr] = val & 0xFF
                return True
        raise KeyError('адрес 0x%04X отсутствует в дампе' % addr)

    def set_word(self, addr, val):
        self.set_byte(addr, val & 0xFF)
        self.set_byte(addr + 1, (val >> 8) & 0xFF)

    # --------------------------------------------------- сериализация
    def _srec_line(self, r):
        alen = {'S1': 2, 'S2': 3, 'S3': 4, 'S5': 2,
                'S7': 4, 'S8': 3, 'S9': 2}[r.rectype]
        addr = r.addr.to_bytes(alen, 'big')
        body = addr + bytes(r.data)
        count = len(body) + 1
        csum = 0xFF - ((count + sum(body)) & 0xFF)
        return '%s%02X%s%02X' % (r.rectype, count,
                                 body.hex().upper(), csum)

    def _ihex_line(self, r):
        n = len(r.data)
        addr16 = r.addr & 0xFFFF
        head = bytes([n, (addr16 >> 8) & 0xFF, addr16 & 0xFF, r.rectype])
        body = head + bytes(r.data)
        csum = (-sum(body)) & 0xFF
        return ':' + (body + bytes([csum])).hex().upper()

    def dumps(self):
        out = []
        for r in self.records:
            if r.fmt == 'srec':
                out.append(self._srec_line(r))
            else:
                out.append(self._ihex_line(r))
        return '\r\n'.join(out) + '\r\n'

    def save(self, path):
        with open(path, 'w', newline='') as f:
            f.write(self.dumps())


# --------------------------------------------------- самопроверка
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('использование: python3 dumpfile.py <файл.s19|.hex>')
        sys.exit(1)
    d = DumpFile.load(sys.argv[1])
    print('формат:', d.fmt, '| записей:', len(d.records))
    print('0x1000 ADAPTI1  =', hex(d.get_word(0x1000)))
    print('0x1002 масштаб U=', hex(d.get_word(0x1002)))
    print('0x1004 масштаб I=', hex(d.get_word(0x1004)))
    print('0x1008 ID       =', d.get_bytes(0x1008, 4).hex())
    # round-trip: сериализация должна совпасть с исходником
    orig = open(sys.argv[1]).read().replace('\r\n', '\n').strip()
    again = d.dumps().replace('\r\n', '\n').strip()
    print('round-trip идентичен:', orig.upper() == again.upper())
