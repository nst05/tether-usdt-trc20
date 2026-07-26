#!/usr/bin/env python3
"""
smt_eventlog — парсер журнала событий/аудита конфигурации исследуемый прибор из дампа.

Журнал (регион 0x15E000..0x171000) — это аудит-трейл изменений: каждая запись
фиксирует ВРЕМЯ, порядковый номер, код параметра и значение. По нему виден ввод
в эксплуатацию и все правки настроек.

Формат записи:
    +0x00 u32   метка времени Unix
    +0x08 u32   порядковый номер события
    +0x0C u16   код параметра/события
    +0x0E …     ASCII-значение (null-terminated)

    python3 smt_eventlog.py <dump.bin> [--all]
"""
import sys, struct, datetime
from collections import Counter

R0, R1 = 0x15E000, 0x171000

# известные текстовые метки событий (по значению)
KNOWN = {
    "DEF->RAM":  "загрузка заводских настроек в ОЗУ (сброс/старт)",
    "RAM->USER": "фиксация настроек в пользовательский профиль",
}

# разметка кодов событий (по логируемому значению/корреляции)
CODE_NAMES = {
    0x0205: "дата/время (DATETIME)",
    0x02C6: "дата (ввод в работу/калибровка)",
    0x020F: "пароль провайдера",
    0x0220: "пароль (OMEGA, маскир.)",
    0x02B7: "пароль (OMEGA, маскир.)",
    0x020B: "расписание передачи",
    0x0278: "6 калибр. коэффициентов",
    0x0233: "строка калибр. таблицы (LUT)",
    0x026D: "темп. порог мин",
    0x026E: "темп. порог макс",
    0x0248: "предел Q",
    0x0249: "предел Q",
    0x023D: "конфиг датчика/актуатора",
    0x023C: "байт уровня доступа",
    0x026B: "байт уровня доступа",
    0x02D1: "сброс к заводским",
}


def parse(data):
    def u32(o): return struct.unpack_from("<I", data, o)[0]
    def u16(o): return struct.unpack_from("<H", data, o)[0]
    seen = {}
    o = R0
    while o < R1 - 16:
        t, cnt = u32(o), u32(o + 8)
        if 0x66000000 <= t <= 0x69800000 and cnt < 100000:
            code = u16(o + 0x0C)
            e = data.find(b"\0", o + 0x0E)
            s = data[o + 0x0E:e]
            txt = s.decode("latin1") if (0 < len(s) < 48 and all(31 <= b < 127 for b in s)) else ""
            if cnt not in seen:
                seen[cnt] = (t, code, txt)
            o += 0x10
        else:
            o += 4
    return seen


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    data = open(sys.argv[1], "rb").read()
    seen = parse(data)
    show_all = "--all" in sys.argv
    ts = [v[0] for v in seen.values() if 0x67000000 < v[0] < 0x69000000]
    print(f"═ Журнал событий/аудита · {sys.argv[1]} ═")
    print(f"  записей: {len(seen)}")
    if ts:
        print(f"  период:  {datetime.datetime.utcfromtimestamp(min(ts)):%Y-%m-%d %H:%M} … "
              f"{datetime.datetime.utcfromtimestamp(max(ts)):%Y-%m-%d %H:%M}")

    print("\n── ХРОНОЛОГИЯ (по регистру) ──")
    items = sorted(seen.items())
    limit = None if show_all else 30
    for cnt, (t, code, txt) in items[:limit]:
        dt = datetime.datetime.utcfromtimestamp(t)
        note = "  ← " + KNOWN[txt] if txt in KNOWN else (
               "  ← " + CODE_NAMES[code] if code in CODE_NAMES else "")
        val = f" = {txt!r}" if txt else ""
        print(f"  #{cnt:<4}{dt:%Y-%m-%d %H:%M:%S}  code=0x{code:04X}{val}{note}")
    if limit and len(items) > limit:
        print(f"  … ещё {len(items)-limit} (запуск с --all)")

    codes = Counter(v[1] for v in seen.values())
    print("\n── ЧАСТЫЕ КОДЫ ──")
    for code, n in codes.most_common(8):
        ex = next((v[2] for v in seen.values() if v[1] == code and v[2]), "")
        print(f"  0x{code:04X}: {n:3d}×   пример={ex!r}")
    print(f"\n  калибровочная таблица (code 0x0233): {codes.get(0x0233,0)} строк")

    # находка: секреты в журнале
    secrets = [(c, v) for c, (t, code, v) in seen.items()
               if v and (v.isdigit() and 4 <= len(v) <= 8) and code == 0x020F]
    if any(v == "123456" for _, v in secrets) or \
       any(seen[c][2] == "123456" for c in seen):
        print("\n  ⚠ находка F7: в журнале встречается пароль ОТКРЫТЫМ ТЕКСТОМ (123456)")


if __name__ == "__main__":
    main()
