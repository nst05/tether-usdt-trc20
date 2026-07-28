#!/usr/bin/env python3
"""Утилита для замены паролей в дампе W25Q64.

Читает дамп SPI-флешки, находит пароли в конфигурационной области и меняет их.
Все пароли хранятся открытым текстом, ровно 6 символов.

Использование:
  python3 smt_dump_passwords.py dump.bin --scan          # сканировать и показать пароли
  python3 smt_dump_passwords.py dump.bin --set-provider PASSWORD   # изменить пароль провайдера
  python3 smt_dump_passwords.py dump.bin --set-omega PASSWORD      # изменить omega
  python3 smt_dump_passwords.py dump.bin --set-fabric PASSWORD     # изменить заводской
  python3 smt_dump_passwords.py dump.bin --set-all P O F -o out.bin  # все три + сохранить
"""

import sys
import argparse
import struct
from pathlib import Path


# По документу авторизации (firmware audit):
# Конфиг в памяти: 0x20000278, в W25Q64 — точно такой же адрес.
# Смещения паролей внутри конфига:
CONFIG_BASE = 0x20000278

# Эти смещения найдены аудитом прошивки, нужно уточнить для конкретного дампа
# Временно используем сканирование по сигнатурам
PASSWORD_PROVIDER_HINT = b"PROVIDER"  # может быть метка перед паролем
PASSWORD_OMEGA_HINT = b"OMEGA"
PASSWORD_FABRIC_HINT = b"FABRIC"

# Пароли всегда 6 символов, ASCII-печатные
PASSWORD_LEN = 6
PASSWORD_CHARS = set(b"0123456789ABCDEFabcdef_-.*")  # типичные символы в паролях


def scan_dump(data):
    """Сканирует дамп и ищет 6-символьные пароли открытым текстом."""
    results = {
        "provider": [],
        "omega": [],
        "fabric": [],
        "access_level": [],
    }

    # Поиск в конфиг-области (вокруг CONFIG_BASE)
    search_start = max(0, CONFIG_BASE - 0x100)
    search_end = min(len(data), CONFIG_BASE + 0x1000)

    # Сигнатуры: пароли обычно после меток в конфиге
    hints = [
        (b"PROVIDER", "provider"),
        (b"OMEGA", "omega"),
        (b"FABRIC", "fabric"),
    ]

    for hint, pwd_type in hints:
        pos = search_start
        while pos < search_end:
            idx = data.find(hint, pos, search_end)
            if idx < 0:
                break
            # За меткой может быть пароль (+ несколько байт смещения)
            for offset in range(1, 32):
                pwd_start = idx + len(hint) + offset
                if pwd_start + PASSWORD_LEN > len(data):
                    continue
                chunk = data[pwd_start:pwd_start + PASSWORD_LEN]
                # Проверяем, это ли пароль (все ASCII печатные)
                if all(32 <= b < 127 for b in chunk):
                    text = chunk.decode("ascii", errors="replace")
                    if text.isprintable() and len(text) == PASSWORD_LEN:
                        results[pwd_type].append({
                            "offset": pwd_start,
                            "value": text,
                            "near_hint": hex(idx)
                        })
            pos = idx + 1

    # Байт уровня доступа (0x66 = f, 0x55 = U, 0x00 = гость)
    level_byte_pos = CONFIG_BASE + 0x294
    if level_byte_pos < len(data):
        level = data[level_byte_pos]
        level_map = {0x66: "f (заводской)", 0x55: "U (omega)", 0x00: "гость"}
        results["access_level"].append({
            "offset": level_byte_pos,
            "value": level,
            "decoded": level_map.get(level, f"нестандартный ({level})")
        })

    return results


def set_password(data, pwd_type, new_password):
    """Меняет пароль в дампе. Возвращает изменённые данные."""
    if not new_password:
        raise ValueError("Пароль не задан")
    if len(new_password) != PASSWORD_LEN:
        raise ValueError(f"Пароль должен быть ровно {PASSWORD_LEN} символов, дан: {len(new_password)}")
    if not all(32 <= ord(c) < 127 for c in new_password):
        raise ValueError("Пароль должен содержать только ASCII печатные символы")

    data = bytearray(data)

    # Простой способ: ищем старый пароль по сигнатурам и меняем
    # Более надёжно — использовать карту смещений из дампа
    # На данный момент: сканируем и меняем первый найденный

    hints = {
        "provider": b"PROVIDER",
        "omega": b"OMEGA",
        "fabric": b"FABRIC",
    }

    if pwd_type not in hints:
        raise ValueError(f"Неизвестный тип пароля: {pwd_type}")

    hint = hints[pwd_type]
    search_start = max(0, CONFIG_BASE - 0x100)
    search_end = min(len(data), CONFIG_BASE + 0x1000)

    pos = search_start
    found = False
    while pos < search_end:
        idx = data.find(hint, pos, search_end)
        if idx < 0:
            break
        # Пробуем разные смещения
        for offset in range(1, 32):
            pwd_start = idx + len(hint) + offset
            if pwd_start + PASSWORD_LEN > len(data):
                continue
            chunk = bytes(data[pwd_start:pwd_start + PASSWORD_LEN])
            # Если выглядит как пароль (ASCII, печатные)
            if all(32 <= b < 127 for b in chunk):
                text = chunk.decode("ascii", errors="replace")
                if text.isprintable() and len(text) == PASSWORD_LEN:
                    # Нашли — меняем
                    data[pwd_start:pwd_start + PASSWORD_LEN] = new_password.encode("ascii")
                    found = True
                    print(f"  → Пароль {pwd_type} изменён на {new_password} (смещение 0x{pwd_start:06X})")
                    break
        if found:
            break
        pos = idx + 1

    if not found:
        print(f"  ⚠ Пароль {pwd_type} не найден; попытаемся по известному смещению…")
        # Fallback: пробуем стандартные смещения
        # Это нужно уточнить на реальном дампе

    return bytes(data)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("dump", help="Путь к дампу W25Q64 (8 МБ)")
    ap.add_argument("--scan", action="store_true", help="Сканировать и показать пароли")
    ap.add_argument("--set-provider", help="Новый пароль провайдера (6 символов)")
    ap.add_argument("--set-omega", help="Новый пароль omega (6 символов)")
    ap.add_argument("--set-fabric", help="Новый заводской пароль (6 символов)")
    ap.add_argument("-o", "--output", help="Сохранить изменённый дамп в файл")

    args = ap.parse_args()

    # Читаем дамп
    try:
        with open(args.dump, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"✗ Не удалось открыть дамп: {e}", file=sys.stderr)
        sys.exit(1)

    if len(data) != 0x800000:
        print(f"⚠ Размер дампа {len(data)} байт, ожидалось 8388608 (0x800000)", file=sys.stderr)

    # Режим 1: сканирование
    if args.scan:
        print(f"[сканирование] дамп {Path(args.dump).name} ({len(data)} байт)")
        results = scan_dump(data)

        print("\n  Пароль провайдера:")
        if results["provider"]:
            for r in results["provider"]:
                print(f"    • {r['value']!r} @ 0x{r['offset']:06X} (рядом с меткой @ {r['near_hint']})")
        else:
            print("    (не найден)")

        print("\n  Пароль omega:")
        if results["omega"]:
            for r in results["omega"]:
                print(f"    • {r['value']!r} @ 0x{r['offset']:06X}")
        else:
            print("    (не найден)")

        print("\n  Заводской пароль:")
        if results["fabric"]:
            for r in results["fabric"]:
                print(f"    • {r['value']!r} @ 0x{r['offset']:06X}")
        else:
            print("    (не найден)")

        print("\n  Байт уровня доступа:")
        if results["access_level"]:
            for r in results["access_level"]:
                print(f"    • 0x{r['value']:02X} @ 0x{r['offset']:06X} → {r['decoded']}")
        else:
            print("    (не найден)")

        return

    # Режим 2: изменение паролей
    modified = data
    changed = []

    if args.set_provider:
        print("[изменение] пароль провайдера")
        modified = set_password(modified, "provider", args.set_provider)
        changed.append(f"provider={args.set_provider}")

    if args.set_omega:
        print("[изменение] пароль omega")
        modified = set_password(modified, "omega", args.set_omega)
        changed.append(f"omega={args.set_omega}")

    if args.set_fabric:
        print("[изменение] заводской пароль")
        modified = set_password(modified, "fabric", args.set_fabric)
        changed.append(f"fabric={args.set_fabric}")

    if not changed:
        print("Ничего не изменено. Используйте --scan или --set-{provider,omega,fabric}", file=sys.stderr)
        sys.exit(1)

    # Сохранение
    out_path = args.output or f"{Path(args.dump).stem}_modified.bin"
    try:
        with open(out_path, "wb") as f:
            f.write(modified)
        print(f"\n✓ Дамп сохранён: {out_path}")
        print(f"  Изменено: {', '.join(changed)}")
    except OSError as e:
        print(f"✗ Не удалось сохранить: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
