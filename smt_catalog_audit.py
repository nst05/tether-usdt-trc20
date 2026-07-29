#!/usr/bin/env python3
"""smt_catalog_audit — сверка каталога команд с реальными форматными строками
в дизассемблере прошивки.

Зачем
-----
MODE_TRANSFER в каталоге (smt_commands.json) описан как простой enum (0/1), но
его реальный обработчик (sub_08006C80) читает/пишет СОСТАВНОЕ значение из
5 чисел (`%d,%d,%d,%d,%d` на чтение, `%d;%d;%d;%d;%d` на запись) — режим и
дни/час передачи, которые GUI просто не показывал. Этот скрипт ищет ДРУГИЕ
команды с той же проблемой: обработчик работает с составным (2+ значения)
форматом, а каталог объявляет её как одиночное значение (тип не "строка",
где составной текст ожидаем).

Как работает
------------
Для каждой команды берётся её `handler` (имя функции), в дизассемблере
находится тело этой функции (от метки `; ---- sub_XXXXXXXX ----` до следующей
такой метки) и внутри ищутся форматные строки с 2+ спецификаторами
(`%d`, `%s`, `%f`, `%.02f` и т.п.), разделёнными `,` или `;`. Если такая
строка найдена, а тип команды в каталоге не подразумевает составной текст —
команда попадает в отчёт как подозрительная (возможно, GUI показывает не всё).

Запуск
------
  python3 smt_catalog_audit.py
  python3 smt_catalog_audit.py --json report.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(HERE, "smt_commands.json")
DISASM_PATH = os.path.join(HERE, "docs", "firmware", "app_disasm.txt")

FUNC_MARKER = re.compile(r"^; ---- (sub_[0-9A-Fa-f]+) ----$")
FORMAT_STR = re.compile(r'"((?:%[#0\-+ ]?\.?\d*(?:\.\d+)?[dsfxX])(?:[,;:](?:%[#0\-+ ]?\.?\d*(?:\.\d+)?[dsfxX]))+)"')

# Типы, для которых составной текст ожидаем и не считается находкой.
COMPOUND_OK_TYPES = {"строка", "строка/цел"}


def load_functions(disasm_path: str) -> dict[str, tuple[int, int]]:
    """Возвращает {имя_функции: (первая_строка, последняя_строка)} — диапазон
    строк файла, относящихся к телу каждой функции."""
    with open(disasm_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    markers = [(i, m.group(1)) for i, line in enumerate(lines)
               if (m := FUNC_MARKER.match(line.rstrip("\n")))]
    funcs: dict[str, tuple[int, int]] = {}
    for idx, (line_no, name) in enumerate(markers):
        end = markers[idx + 1][0] if idx + 1 < len(markers) else len(lines)
        funcs.setdefault(name, (line_no, end))
    return funcs, lines


def find_format_strings(lines: list[str], start: int, end: int) -> list[str]:
    found = []
    for line in lines[start:end]:
        m = FORMAT_STR.search(line)
        if m:
            found.append(m.group(1))
    return found


def audit(catalog_path: str = CATALOG_PATH, disasm_path: str = DISASM_PATH) -> list[dict]:
    catalog = json.loads(open(catalog_path, encoding="utf-8").read())["commands"]
    funcs, lines = load_functions(disasm_path)

    report = []
    for cmd in catalog:
        handler = cmd.get("handler", "")
        if handler not in funcs:
            continue
        start, end = funcs[handler]
        fmts = find_format_strings(lines, start, end)
        if not fmts:
            continue
        max_fields = max(f.count("%") for f in fmts)
        if max_fields < 2:
            continue
        if cmd.get("type") in COMPOUND_OK_TYPES:
            continue
        report.append({
            "name": cmd["name"],
            "type": cmd.get("type", ""),
            "handler": handler,
            "format_strings": sorted(set(fmts)),
            "max_fields": max_fields,
        })
    report.sort(key=lambda r: -r["max_fields"])
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default=CATALOG_PATH)
    ap.add_argument("--disasm", default=DISASM_PATH)
    ap.add_argument("--json", metavar="FILE", help="сохранить отчёт в JSON")
    args = ap.parse_args(argv)

    report = audit(args.catalog, args.disasm)

    print(f"Проверено команд с обработчиком в дизассемблере. Подозрительных "
          f"(составной формат при простом заявленном типе): {len(report)}\n")
    for item in report:
        print(f"  {item['name']:<20} тип={item['type']:<10} "
              f"обработчик={item['handler']} полей={item['max_fields']}")
        for fmt in item["format_strings"]:
            print(f"      формат: {fmt}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nОтчёт сохранён: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
