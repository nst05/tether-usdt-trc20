#!/usr/bin/env python3
"""Утилита для замены паролей и уровней доступа в дампе W25Q64.

Пароли хранятся в ЖУРНАЛЕ СОБЫТИЙ (0x15E000..0x171000), не в конфиге.
Формат записи журнала:
  +0x00 (4б)  u32 время (Unix timestamp)
  +0x04 (4б)  u32 счётчик события
  +0x08 (2б)  u16 код события
  +0x0A (48б) ASCII значение

Коды событий (из dump_extract.py):
  0x020F = PASSWORD_PROVIDER (пароль провайдера)
  0x0220 = PASSWORD_OMEGA (пароль omega, маскирован)
  0x02B7 = PASSWORD_OMEGA (маскирован)
  0x023C = ACCESS_LEVEL (байт уровня: 0x66/0x55/0x00)
  0x026B = ACCESS_LEVEL

Использование:
  python3 smt_dump_passwords.py dump.bin --scan              # показать все пароли
  python3 smt_dump_passwords.py dump.bin --set-provider PWD  # изменить пароль провайдера
  python3 smt_dump_passwords.py dump.bin --set-omega PWD     # изменить omega
  python3 smt_dump_passwords.py dump.bin --set-level f -o out.bin
"""

import sys
import struct
import argparse
from pathlib import Path


# По dump_extract.py: журнал событий в 0x15E000..0x171000
EVT_R0 = 0x15E000
EVT_R1 = 0x171000

# Коды событий
EVENT_CODES = {
    0x020F: ("PASSWORD_PROVIDER", "пароль провайдера", "password"),
    0x0220: ("PASSWORD_OMEGA", "пароль omega", "password"),
    0x02B7: ("PASSWORD_OMEGA", "пароль omega", "password"),
    0x023C: ("ACCESS_LEVEL", "байт уровня доступа", "level"),
    0x026B: ("ACCESS_LEVEL", "байт уровня доступа", "level"),
}

# Формат записи журнала (из dump_extract.py):
# +0x00 u32 время
# +0x04 u32 счётчик
# +0x08 u16 код
# +0x0A ..  значение (ASCII, max 48 байт до \0)
EVENT_RECORD_SIZE = 0x10

LEVEL_CODES = {"f": 0x66, "F": 0x66, "U": 0x55, "u": 0x55, "0": 0x00}
LEVEL_NAMES = {
    0x66: "заводской (f)",
    0x55: "omega (U)",
    0x00: "гость",
}


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]

def u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def iter_journal(data):
    """Единый обход журнала: валидная запись → шаг 0x10, промах → 0x04 с
    повторным выравниванием. И чтение, и запись используют ОДИН обход."""
    o = EVT_R0
    limit = min(EVT_R1, len(data))
    while o < limit - 16:
        try:
            ts = u32(data, o)
            cnt = u32(data, o + 0x08)
        except struct.error:
            o += 4
            continue
        if not (100_000_000 < ts < 4_000_000_000) or cnt >= 100000:
            o += 4
            continue
        code = u16(data, o + 0x0C)
        vs = o + 0x0E
        ve = data.find(b"\0", vs, min(limit, vs + 48))
        if ve < 0:
            ve = min(limit, vs + 48)
        yield o, ts, cnt, code, vs, ve
        o += 0x10


def write_value_inplace(data, vs, ve, new_bytes):
    """Замена значения на месте: new_bytes + \\0, хвост старого значения в [vs, ve)
    обнуляется, следующая запись не затрагивается."""
    n = len(new_bytes)
    for i, b in enumerate(new_bytes):
        if vs + i < len(data):
            data[vs + i] = b
    if vs + n < len(data):
        data[vs + n] = 0
    for i in range(vs + n + 1, ve):
        if i < len(data):
            data[i] = 0


def scan_journal(dump):
    """Сканирует журнал событий и показывает пароли."""
    print(f"[сканирование] Журнал 0x{EVT_R0:06X}..0x{EVT_R1:06X}\n")

    passwords = []
    levels = []

    for o, ts, cnt, code, val_start, val_end in iter_journal(dump):
        raw = bytes(dump[val_start:val_end])
        text = raw.decode("ascii", errors="replace") if raw else ""
        if code in EVENT_CODES:
            cmd, human, kind = EVENT_CODES[code]
            entry = {
                "offset": o,
                "timestamp": ts,
                "counter": cnt,
                "code": code,
                "command": cmd,
                "value": text,
                "kind": kind,
            }
            if kind == "password":
                passwords.append(entry)
            elif kind == "level":
                try:
                    level_byte = int(text)
                    entry["level_byte"] = level_byte
                    entry["level_name"] = LEVEL_NAMES.get(level_byte, "?")
                    levels.append(entry)
                except ValueError:
                    pass

    # Показываем результаты
    if passwords:
        print(f"[ПАРОЛИ] Найдено {len(passwords)}:")
        for pwd in passwords:
            print(f"  {pwd['command']:20} = {pwd['value']!r:15} @ 0x{pwd['offset']:06X} "
                  f"(счётчик {pwd['counter']})")
    else:
        print("[ПАРОЛИ] Не найдены")

    if levels:
        print(f"\n[УРОВНИ] Найдено {len(levels)}:")
        for lev in levels:
            print(f"  0x{lev['level_byte']:02X} = {lev['level_name']:20} @ 0x{lev['offset']:06X} "
                  f"(счётчик {lev['counter']})")
    else:
        print("\n[УРОВНИ] Не найдены")

    print()
    return passwords, levels


def set_password_in_journal(dump, command, new_password):
    """Меняет пароль во всех записях журнала."""
    if not new_password:
        raise ValueError("Пароль не задан")

    if len(new_password) > 48:
        raise ValueError("Пароль не должен быть длиннее 48 символов")

    # Все коды, относящиеся к этой команде (у omega их два: 0x0220 и 0x02B7)
    target_codes = {code for code, (cmd, _, _) in EVENT_CODES.items() if cmd == command}
    if not target_codes:
        raise ValueError(f"Команда {command} не найдена")

    data = bytearray(dump)
    nb = new_password.encode("ascii")
    changed = 0
    # Пишем ровно по тем адресам, что находит сканер (общий обход iter_journal)
    for o, ts, cnt, code, vs, ve in iter_journal(data):
        if code in target_codes:
            write_value_inplace(data, vs, ve, nb)
            changed += 1

    print(f"  → {command} = {new_password!r}")
    print(f"    Заменено записей в журнале: {changed}")

    return bytes(data)


def set_level_in_journal(dump, level_char):
    """Меняет уровень доступа во всех записях журнала."""
    if level_char not in LEVEL_CODES:
        raise ValueError(f"Неизвестный уровень: {level_char}. Допустимы: f, U, 0")

    level_byte = LEVEL_CODES[level_char]
    data = bytearray(dump)
    nb = str(level_byte).encode("ascii")
    changed = 0
    for o, ts, cnt, code, vs, ve in iter_journal(data):
        if code in (0x023C, 0x026B):  # ACCESS_LEVEL коды
            write_value_inplace(data, vs, ve, nb)
            changed += 1

    level_name = LEVEL_NAMES.get(level_byte, "?")
    print(f"  → ACCESS_LEVEL = 0x{level_byte:02X} ({level_name})")
    print(f"    Заменено записей в журнале: {changed}")

    return bytes(data)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("dump", help="Путь к дампу W25Q64")
    ap.add_argument("--scan", action="store_true", help="Сканировать и показать пароли/уровни")
    ap.add_argument("--set-provider", metavar="PWD", help="Новый пароль провайдера")
    ap.add_argument("--set-omega", metavar="PWD", help="Новый пароль omega")
    ap.add_argument("--set-level", metavar="LEVEL", choices=["f", "F", "U", "u", "0"],
                    help="Уровень доступа: f (заводской), U (omega), 0 (гость)")
    ap.add_argument("-o", "--output", help="Сохранить изменённый дамп")

    args = ap.parse_args()

    # Читаем дамп
    try:
        with open(args.dump, "rb") as f:
            dump = f.read()
    except OSError as e:
        print(f"✗ Не удалось открыть: {e}", file=sys.stderr)
        sys.exit(1)

    # Режим сканирования
    if args.scan:
        scan_journal(dump)
        return

    # Режим изменения
    modified = dump
    changed = []

    if args.set_provider:
        print("[пароль] провайдера")
        modified = set_password_in_journal(modified, "PASSWORD_PROVIDER", args.set_provider)
        changed.append(f"provider={args.set_provider}")

    if args.set_omega:
        print("[пароль] omega")
        modified = set_password_in_journal(modified, "PASSWORD_OMEGA", args.set_omega)
        changed.append(f"omega={args.set_omega}")

    if args.set_level:
        print("[уровень] доступа")
        modified = set_level_in_journal(modified, args.set_level)
        changed.append(f"level={args.set_level}")

    if not changed:
        print("ℹ Используйте --scan для просмотра или --set-* для изменения")
        return

    # Сохранение
    out_path = args.output or f"{Path(args.dump).stem}_modified.bin"
    try:
        with open(out_path, "wb") as f:
            f.write(modified)
        print(f"\n✓ Сохранён: {out_path}")
        print(f"  Изменения: {', '.join(changed)}")
    except OSError as e:
        print(f"✗ Ошибка сохранения: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
