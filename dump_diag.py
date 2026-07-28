#!/usr/bin/env python3
"""Диагностика дампа W25Q64 по паролям — только ЧИТАЕТ, ничего не портит.

Запуск:
    python3 dump_diag.py  ПУТЬ_К_ДАМПУ.bin

Что делает:
  1) Сканирует журнал (0x15E000..0x171000) и печатает ВСЕ записи паролей/уровня
     с адресами и значениями.
  2) Ищет строку старого пароля ПО ВСЕМУ образу (а не только в журнале) —
     показывает, есть ли копии вне журнала (в конфиг-области).
  3) В ПАМЯТИ меняет пароль провайдера на 000111, заново сканирует и сохраняет
     копию рядом (<имя>_diagtest.bin) — по ней видно, работает ли запись
     round-trip на ИМЕННО твоём файле.

Пришли, пожалуйста, весь вывод этого скрипта.
"""
import struct
import sys
from pathlib import Path

EVT_R0, EVT_R1 = 0x15E000, 0x171000
EVENT_CODES = {
    0x020F: "PASSWORD_PROVIDER",
    0x0220: "PASSWORD_OMEGA",
    0x02B7: "PASSWORD_OMEGA",
    0x023C: "ACCESS_LEVEL",
    0x026B: "ACCESS_LEVEL",
}


def u32(d, o): return struct.unpack_from("<I", d, o)[0]
def u16(d, o): return struct.unpack_from("<H", d, o)[0]


def iter_journal(data):
    o = EVT_R0
    limit = min(EVT_R1, len(data))
    while o < limit - 16:
        try:
            ts = u32(data, o); cnt = u32(data, o + 8)
        except struct.error:
            o += 4; continue
        if not (100_000_000 < ts < 4_000_000_000) or cnt >= 100000:
            o += 4; continue
        code = u16(data, o + 0x0C)
        vs = o + 0x0E
        ve = data.find(b"\0", vs, min(limit, vs + 48))
        if ve < 0:
            ve = min(limit, vs + 48)
        yield o, ts, cnt, code, vs, ve
        o += 0x10


def scan(data):
    rows = []
    for o, ts, cnt, code, vs, ve in iter_journal(data):
        if code in EVENT_CODES:
            val = bytes(data[vs:ve]).decode("ascii", "replace")
            rows.append((o, code, EVENT_CODES[code], val))
    return rows


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    data = bytearray(path.read_bytes())
    print(f"Файл: {path}   размер: {len(data)} (0x{len(data):X})\n")

    print("── 1) ЗАПИСИ ПАРОЛЕЙ/УРОВНЯ В ЖУРНАЛЕ ──")
    rows = scan(data)
    if not rows:
        print("  (ничего не найдено — возможно, template-дамп без конфига)")
    prov_val = None
    for o, code, name, val in rows:
        print(f"  0x{o:06X}  code=0x{code:04X}  {name:18} = {val!r}")
        if name == "PASSWORD_PROVIDER" and val and "*" not in val and prov_val is None:
            prov_val = val

    print("\n── 2) ПОИСК СТАРОГО ПАРОЛЯ ПРОВАЙДЕРА ПО ВСЕМУ ОБРАЗУ ──")
    if prov_val:
        needle = prov_val.encode("ascii")
        hits, start = [], 0
        while True:
            i = data.find(needle, start)
            if i < 0:
                break
            zone = "ЖУРНАЛ" if EVT_R0 <= i < EVT_R1 else "вне журнала (конфиг?)"
            hits.append((i, zone))
            start = i + 1
        print(f"  Ищем {prov_val!r}: найдено {len(hits)} вхождений")
        for i, zone in hits[:40]:
            print(f"    0x{i:06X}  [{zone}]")
        outside = [h for h in hits if not (EVT_R0 <= h[0] < EVT_R1)]
        if outside:
            print(f"  ⚠ ВНИМАНИЕ: {len(outside)} копий ВНЕ журнала — их правка журнала НЕ меняет!")
    else:
        print("  Открытый пароль провайдера в журнале не найден — пропускаю поиск.")

    print("\n── 3) ТЕСТ ЗАПИСИ round-trip (в памяти + копия на диск) ──")
    test = bytearray(data)
    changed = 0
    for o, ts, cnt, code, vs, ve in iter_journal(test):
        if code == 0x020F:
            nb = b"000111"
            for k, b in enumerate(nb):
                test[vs + k] = b
            if vs + len(nb) < len(test):
                test[vs + len(nb)] = 0
            for k in range(vs + len(nb) + 1, ve):
                test[k] = 0
            changed += 1
    print(f"  Заменено записей провайдера в журнале: {changed}")
    after = [(o, v) for o, code, name, v in scan(test) if name == "PASSWORD_PROVIDER"]
    print(f"  После замены значения провайдера в журнале: {sorted({v for _, v in after})}")
    out = path.with_name(path.stem + "_diagtest.bin")
    out.write_bytes(bytes(test))
    reread = out.read_bytes()
    rr = sorted({v for o, code, name, v in scan(bytearray(reread)) if name == "PASSWORD_PROVIDER"})
    print(f"  Сохранил {out.name}, перечитал → провайдер: {rr}")
    print("\n  Если тут '000111', а на реальном дампе пароль «не меняется» — значит,")
    print("  либо перед «Сохранить» не нажималось «Применить», либо есть копия ВНЕ журнала (п.2).")


if __name__ == "__main__":
    main()
