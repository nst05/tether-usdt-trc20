#!/usr/bin/env python3
"""Утилита для замены паролей и уровней доступа в дампе W25Q64.

По документу авторизации (дизассемблер 0x0800B58E):
- Пароли хранятся открытым текстом (6 символов)
- Байт уровня доступа: 0x66=заводской (f), 0x55=omega (U), 0x00=гость
- Биты нумерованного уровня: бит0=уровень1, бит1=уровень2, бит2=уровень3

Примечание: Template дампы не содержат конфиг; конфиг создаётся прибором при старте.
Эта утилита позволяет редактировать конфиг, если вы знаете его смещение в дампе.

Использование:
  python3 smt_dump_passwords.py dump.bin --scan                    # сканировать
  python3 smt_dump_passwords.py dump.bin --config-base 0x7B0000 \\
      --provider-offset 0x100 --omega-offset 0x106 \\
      --fabric-offset 0x10C --level-offset 0x112 \\
      --set-provider P123 --set-level f -o out.bin
"""

import sys
import argparse
import struct
from pathlib import Path


# TEMPLATE дамп не содержит конфиг, эти значения — по умолчанию для поиска
# Если конфиг найден, смещения переопределяются

DEFAULT_CONFIG_BASE = 0x7B0000  # конец флешки (область, где может быть конфиг)
DEFAULT_PROVIDER_OFFSET = 0x100
DEFAULT_OMEGA_OFFSET = 0x106
DEFAULT_FABRIC_OFFSET = 0x10C
DEFAULT_LEVEL_OFFSET = 0x112

# Пароли: 6 символов, ASCII-печатные
PASSWORD_LEN = 6

# Коды уровней
LEVEL_CODES = {
    "f": 0x66,      # заводской (мастер-ключ)
    "F": 0x66,
    "U": 0x55,      # omega (мастер-ключ)
    "u": 0x55,
    "0": 0x00,      # гость
}
LEVEL_NAMES = {
    0x66: "заводской (f) — мастер-ключ",
    0x55: "omega (U) — мастер-ключ",
    0x00: "гость",
}


def scan_dump(data):
    """Сканирует дамп и показывает пароли + уровни доступа."""
    results = {
        "provider": [],
        "omega": [],
        "fabric": [],
        "access_level": [],
        "numbered_bits": [],
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
    # В ОЗУ: 0x20000D62, в конфиге W25Q64: CONFIG_BASE + 0x294
    level_byte_pos = CONFIG_BASE + ACCESS_LEVEL_OFFSET
    if level_byte_pos < len(data):
        level = data[level_byte_pos]
        decoded = LEVEL_NAMES.get(level, f"нестандартный (0x{level:02X})")
        results["access_level"].append({
            "offset": level_byte_pos,
            "value": level,
            "hex": hex(level),
            "decoded": decoded
        })

    # Биты нумерованного уровня (в ОЗУ 0x2000B1B0)
    # Структура: бит0=уровень1, бит1=уровень2, бит2=уровень3
    # Нужно найти в дампе по сигнатурам или известным смещениям
    # На данный момент: только сканируем вокруг конфига

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
                    print(f"  → Пароль {pwd_type} = {new_password} (смещение 0x{pwd_start:06X})")
                    break
        if found:
            break
        pos = idx + 1

    if not found:
        print(f"  ⚠ Пароль {pwd_type} не найден по сигнатурам")

    return bytes(data)


def set_access_level(data, level_char, config_base, level_offset):
    """Меняет байт уровня доступа (f/U/0).

    После авторизации прибор устанавливает этот байт в 0x20000D62 (ОЗУ).
    В W25Q64 он хранится по адресу config_base + level_offset.
    """
    if level_char not in LEVEL_CODES:
        raise ValueError(f"Неизвестный уровень: {level_char}. Допустимы: f, U, 0")

    level_byte = LEVEL_CODES[level_char]
    data = bytearray(data)

    level_byte_pos = config_base + level_offset
    if level_byte_pos >= len(data):
        raise ValueError(f"Смещение уровня 0x{level_byte_pos:06X} вне дампа ({len(data)} байт)")

    data[level_byte_pos] = level_byte
    decoded = LEVEL_NAMES.get(level_byte, "?")
    print(f"  → Уровень доступа = {level_char} (0x{level_byte:02X}) @ 0x{level_byte_pos:06X}: {decoded}")

    return bytes(data)


def set_numbered_bits(data, bits_str):
    """Меняет биты нумерованного уровня (бит0/1/2 = уровень1/2/3).

    Входной формат:
      "0b111" → уровни 1, 2, 3 включены
      "0b001" → только уровень 1
      "3" → decimal, равно 0b011 (уровни 1, 2)
    """
    # Парсим входные биты
    try:
        if bits_str.startswith("0b"):
            bits = int(bits_str, 2)
        else:
            bits = int(bits_str)
        if bits < 0 or bits > 0b111:
            raise ValueError
    except ValueError:
        raise ValueError("Биты должны быть 0-7, 0b000-0b111, или 0-3 для уровней")

    data = bytearray(data)

    # Это смещение нужно уточнить на реальном дампе
    # В ОЗУ: 0x2000B1B0, в W25Q64 — нужно найти по карте памяти
    # На данный момент: сигнал об отсутствии точного смещения

    print(f"  ⚠ Точное смещение битов нумерованного уровня в W25Q64 еще не определено")
    print(f"    (в ОЗУ это 0x2000B1B0; нужен реальный дамп для поиска)")
    print(f"    Желаемые биты: 0b{bits:03b} (уровни: {', '.join([str(i+1) for i in range(3) if bits & (1<<i)])})")

    return bytes(data)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("dump", help="Путь к дампу W25Q64 (8 МБ)")
    ap.add_argument("--scan", action="store_true", help="Сканировать и показать пароли + уровни")

    # Пароли
    ap.add_argument("--set-provider", metavar="PWD", help="Пароль провайдера (6 символов)")
    ap.add_argument("--set-omega", metavar="PWD", help="Пароль omega (6 символов)")
    ap.add_argument("--set-fabric", metavar="PWD", help="Заводской пароль (6 символов)")

    # Уровни доступа
    ap.add_argument("--set-level", metavar="LEVEL", choices=["f", "F", "U", "u", "0"],
                    help="Уровень доступа: f (заводской), U (omega), 0 (гость)")
    ap.add_argument("--set-level-bits", metavar="BITS",
                    help="Биты нумерованного уровня (0-7, 0b000-0b111)")

    # Смещения конфига (если известны)
    ap.add_argument("--config-base", type=lambda x: int(x, 0), default=DEFAULT_CONFIG_BASE,
                    help=f"Адрес конфига в дампе (hex, по умолч. 0x{DEFAULT_CONFIG_BASE:X})")
    ap.add_argument("--provider-offset", type=lambda x: int(x, 0), default=DEFAULT_PROVIDER_OFFSET,
                    help=f"Смещение PASSWORD_PROVIDER (по умолч. 0x{DEFAULT_PROVIDER_OFFSET:X})")
    ap.add_argument("--omega-offset", type=lambda x: int(x, 0), default=DEFAULT_OMEGA_OFFSET,
                    help=f"Смещение PASSWORD_OMEGA (по умолч. 0x{DEFAULT_OMEGA_OFFSET:X})")
    ap.add_argument("--fabric-offset", type=lambda x: int(x, 0), default=DEFAULT_FABRIC_OFFSET,
                    help=f"Смещение PASSWORD_FABRIC (по умолч. 0x{DEFAULT_FABRIC_OFFSET:X})")
    ap.add_argument("--level-offset", type=lambda x: int(x, 0), default=DEFAULT_LEVEL_OFFSET,
                    help=f"Смещение байта уровня (по умолч. 0x{DEFAULT_LEVEL_OFFSET:X})")

    ap.add_argument("-o", "--output", help="Сохранить изменённый дамп (по умолч. dump_modified.bin)")

    args = ap.parse_args()

    # Читаем дамп
    try:
        with open(args.dump, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"✗ Не удалось открыть дамп: {e}", file=sys.stderr)
        sys.exit(1)

    if len(data) != 0x800000:
        print(f"⚠ Размер дампа {len(data)} байт, ожидалось 8388608 (0x800000)")

    # Режим 1: сканирование
    if args.scan:
        print(f"[сканирование] дамп {Path(args.dump).name} ({len(data)} байт)\n")
        results = scan_dump(data)

        print("  Пароли:")
        for pwd_type in ["provider", "omega", "fabric"]:
            print(f"    {pwd_type.upper():>10}")
            if results[pwd_type]:
                for r in results[pwd_type]:
                    print(f"      {r['value']!r} @ 0x{r['offset']:06X}")
            else:
                print(f"      (не найден)")

        print("\n  Уровни доступа:")
        if results["access_level"]:
            for r in results["access_level"]:
                print(f"    Байт уровня @ 0x{r['offset']:06X}")
                print(f"      0x{r['value']:02X} → {r['decoded']}")
        else:
            print("    (не найдены)")

        print("\n  Биты нумерованного уровня:")
        print("    ⚠ Точное смещение в W25Q64 нужно уточнить на реальном дампе")
        return

    # Режим 2: изменение
    modified = data
    changed = []

    if args.set_provider:
        print("[пароль] провайдера")
        modified = set_password(modified, "provider", args.set_provider)
        changed.append(f"provider={args.set_provider}")

    if args.set_omega:
        print("[пароль] omega")
        modified = set_password(modified, "omega", args.set_omega)
        changed.append(f"omega={args.set_omega}")

    if args.set_fabric:
        print("[пароль] заводской")
        modified = set_password(modified, "fabric", args.set_fabric)
        changed.append(f"fabric={args.set_fabric}")

    if args.set_level:
        print("[уровень] доступа")
        modified = set_access_level(modified, args.set_level, args.config_base, args.level_offset)
        changed.append(f"level={args.set_level}")

    if args.set_level_bits:
        print("[биты] нумерованного уровня")
        modified = set_numbered_bits(modified, args.set_level_bits)
        changed.append(f"level_bits={args.set_level_bits}")

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
        print(f"✗ Ошибка при сохранении: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
