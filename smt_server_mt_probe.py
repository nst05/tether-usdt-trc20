#!/usr/bin/env python3
"""smt_server_mt_probe — проверка Server_MT на СВОЁМ TCP-командном сервере.

ТОЛЬКО ДЛЯ АВТОРИЗОВАННОГО ПЕНТЕСТА своего сервера (без реальных клиентов).

Зачем
-----
Server_MT (см. smt_commands.json, handler sub_08006380) — одноразовый токен
сеанса (challenge): 33 символа из алфавита 012345678ABCDEFGHIJKLMNOPQRSTUVWXYZ
(35 симв., без «9» — побочный эффект генерации index=rand%35) + 4-байтовый
проприетарный тег. Токен случаен на каждый вызов, в дампе не хранится. Тег —
не CRC16/24/32, не усечение MD5/SHA, не Adler/Fletcher/сумма (проверено
перебором в smt_rogue_server.py); подобрать его без реверса кодировщика
нельзя. Единственный практический вопрос, который можно закрыть СНАРУЖИ,
без знания секрета — НАСКОЛЬКО СЛУЧАЕН сам генератор нонса: если сидируется
чем-то предсказуемым (аптайм/время/счётчик), токен и его тег можно предвидеть,
даже не умея вычислить тег из произвольного токена.

Команда шлётся тем же протоколом, что и smt_core.transports.TcpServerTransport
(строка + терминатор, без логина/хендшейка) — см. smt_cli.py --transport tcp.

Что проверяется
---------------
  1. Стабильность: один и тот же ответ на каждый вызов, или новый нонс
     (ожидаемо, раз это challenge) — и совпадает ли что-то с уже известными
     12 образцами (smt_rogue_server.SERVER_MT_SAMPLES).
  2. Коллизии: повторился ли токен в серии запросов (при малом числе
     попыток почти невероятно для качественного RNG — сигнал очень
     маленького пространства состояний/периода).
  3. Равномерность символов по позициям (χ²-тест против равномерного
     распределения по 35 символам) — грубая эвристика, не строгое
     статистическое доказательство.
  4. Монотонность/линейность префикса токена и тега относительно номера
     запроса — признак счётчика/LCG вместо RNG.
  5. Корреляция (Пирсон) между временем запроса и числовым значением
     префикса токена/тега — признак сидирования от времени/аптайма.

Запуск
------
  python3 smt_server_mt_probe.py --host in.tehnomer.ru --port 40200
  python3 smt_server_mt_probe.py --host in.tehnomer.ru --port 40200 --count 30 --delay 0.1
  python3 smt_server_mt_probe.py --host in.tehnomer.ru --port 40200 --command DevInfo
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from collections import Counter

from smt_core import transports
from smt_rogue_server import SERVER_MT_ALPHABET, SERVER_MT_SAMPLES

TOKEN_LEN = 33
ALPHABET_SIZE = len(SERVER_MT_ALPHABET)          # 35
PREFIX_LEN = 6                                    # символов токена для числового префикса


def parse_server_mt(raw: bytes) -> tuple[str, bytes] | None:
    """Пытается разобрать сырой ответ как токен(33)+тег(4). None, если не похоже."""
    if len(raw) < 37:
        return None
    token = raw[:33]
    try:
        token_s = token.decode("ascii")
    except UnicodeDecodeError:
        return None
    if not all(c in SERVER_MT_ALPHABET for c in token_s):
        return None
    return token_s, raw[33:37]


def find_known_sample(token: str, tag: bytes) -> int | None:
    for i, (tok, tg) in enumerate(SERVER_MT_SAMPLES):
        if tok == token and tg == tag:
            return i
    return None


def token_prefix_value(token: str, n: int = PREFIX_LEN) -> int:
    """Числовое значение первых n символов токена по основанию 35 — компактный
    признак для проверки монотонности/корреляции, не требует всего токена."""
    value = 0
    for ch in token[:n]:
        value = value * ALPHABET_SIZE + SERVER_MT_ALPHABET.index(ch)
    return value


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return 0.0
    return cov / (vx * vy) ** 0.5


def is_monotonic(values: list[float]) -> str | None:
    if len(values) < 3:
        return None
    inc = all(b >= a for a, b in zip(values, values[1:], strict=False))
    dec = all(b <= a for a, b in zip(values, values[1:], strict=False))
    if inc:
        return "возрастает"
    if dec:
        return "убывает"
    return None


def chi_square_positions(tokens: list[str]) -> tuple[float, list[tuple[int, float]]]:
    """Суммарный χ² по всем 33 позициям + список позиций с наибольшим
    отклонением (для отчёта)."""
    n = len(tokens)
    per_position = []
    for pos in range(TOKEN_LEN):
        cnt = Counter(t[pos] for t in tokens)
        expected = n / ALPHABET_SIZE
        chi2 = sum((cnt.get(c, 0) - expected) ** 2 / expected for c in SERVER_MT_ALPHABET)
        per_position.append((pos, chi2))
    total = sum(c for _, c in per_position)
    worst = sorted(per_position, key=lambda x: -x[1])[:3]
    return total, worst


def analyze_predictability(samples: list[dict]) -> None:
    print("\n[*] Анализ предсказуемости нонса")
    n = len(samples)
    if n < 3:
        print("    недостаточно образцов (нужно хотя бы 3-5, лучше 20+)")
        return

    tokens = [s["token"] for s in samples]
    tags = [s["tag"] for s in samples]
    order = list(range(n))
    t0 = samples[0]["t"]
    elapsed = [s["t"] - t0 for s in samples]
    prefix_vals = [float(token_prefix_value(t)) for t in tokens]
    tag_vals = [float(int.from_bytes(tg, "big")) for tg in tags]

    # 1. коллизии
    dupes = n - len(set(tokens))
    if dupes:
        print(f"    ⚠ КОЛЛИЗИИ: {dupes} повторяющихся токенов из {n} — очень маленькое "
              "пространство состояний/период RNG для такого объёма выборки")
    else:
        print(f"    коллизий токенов нет ({n} уникальных из {n}) — на этом объёме выборки ожидаемо")

    # 2. равномерность символов по позициям (df=34 на позицию)
    total_chi2, worst = chi_square_positions(tokens)
    df_total = TOKEN_LEN * (ALPHABET_SIZE - 1)
    # нормальное приближение для критического значения при большом df
    crit05 = df_total + 1.645 * math.sqrt(2 * df_total)
    crit01 = df_total + 2.326 * math.sqrt(2 * df_total)
    verdict = "похоже на равномерное" if total_chi2 < crit05 else "ЕСТЬ ОТКЛОНЕНИЕ от равномерного"
    print(f"    χ² по всем позициям: {total_chi2:.1f} (df={df_total}, "
          f"крит.0.05≈{crit05:.1f}, крит.0.01≈{crit01:.1f}) → {verdict}")
    if total_chi2 >= crit05:
        pos_list = ", ".join(f"#{p}(χ²={c:.1f})" for p, c in worst)
        print(f"      самые смещённые позиции: {pos_list}")

    # 3. монотонность/линейность (признак счётчика/LCG вместо RNG)
    mono_prefix = is_monotonic(prefix_vals)
    mono_tag = is_monotonic(tag_vals)
    if mono_prefix:
        print(f"    ⚠ префикс токена МОНОТОННО {mono_prefix} с номером запроса — "
              "похоже на счётчик, а не RNG")
    if mono_tag:
        print(f"    ⚠ тег (как число) МОНОТОННО {mono_tag} с номером запроса — "
              "похоже на счётчик, а не RNG")
    if not mono_prefix and not mono_tag:
        print("    монотонности по номеру запроса не обнаружено")

    # 4. корреляция с временем запроса
    r_prefix_time = pearson(elapsed, prefix_vals)
    r_tag_time = pearson(elapsed, tag_vals)
    r_prefix_order = pearson([float(o) for o in order], prefix_vals)
    r_tag_order = pearson([float(o) for o in order], tag_vals)
    print(f"    корреляция с временем запроса: префикс r={r_prefix_time:+.3f}, тег r={r_tag_time:+.3f}")
    print(f"    корреляция с номером запроса:  префикс r={r_prefix_order:+.3f}, тег r={r_tag_order:+.3f}")
    if max(abs(r_prefix_time), abs(r_tag_time), abs(r_prefix_order), abs(r_tag_order)) > 0.7:
        print("    ⚠ сильная корреляция (|r|>0.7) — генератор, вероятно, сидируется "
              "предсказуемо (время/аптайм/счётчик), стоит проверить прицельно")
    else:
        print("    сильной линейной корреляции не найдено (это не исключает нелинейную "
              "предсказуемость — тест грубый)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--command", default="Server_MT", help="какую команду слать (по умолчанию Server_MT)")
    ap.add_argument("--count", type=int, default=20, help="сколько раз подряд запросить")
    ap.add_argument("--delay", type=float, default=0.2, help="пауза между запросами, сек")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--terminator", choices=["none", "cr", "lf", "crlf"], default="crlf")
    args = ap.parse_args(argv)

    terms = {"none": b"", "cr": b"\r", "lf": b"\n", "crlf": b"\r\n"}
    print(f"[*] цель: {args.host}:{args.port} · команда: {args.command!r} · попыток: {args.count}")

    responses: list[bytes] = []
    samples: list[dict] = []
    for i in range(1, args.count + 1):
        tr = transports.TcpServerTransport(args.host, args.port, timeout=args.timeout,
                                            terminator=terms[args.terminator])
        t_wall = time.time()
        t0 = time.monotonic()
        try:
            raw = tr.send(args.command)
        except Exception as exc:
            print(f"  [{i}/{args.count}] [!] ошибка: {exc}")
            continue
        dt = (time.monotonic() - t0) * 1000
        responses.append(raw)
        print(f"  [{i}/{args.count}] {len(raw)} байт за {dt:.0f} мс: {raw!r}")
        parsed = parse_server_mt(raw)
        if parsed:
            token, tag = parsed
            known = find_known_sample(token, tag)
            note = f" (= известный образец #{known})" if known is not None else " (НОВЫЙ, не из известных 12)"
            print(f"           токен={token} тег={tag.hex().upper()}{note}")
            samples.append({"token": token, "tag": tag, "t": t_wall})
        if i < args.count:
            time.sleep(args.delay)

    print()
    if len(responses) < 2:
        print("[*] недостаточно успешных ответов для сравнения")
        return 0
    if all(r == responses[0] for r in responses):
        print("[*] ВЫВОД: сервер отдаёт СТАБИЛЬНЫЙ (одинаковый) ответ на каждый запрос")
        print("    → не нонс/не сессионный — можно рассматривать как статичный секрет/токен канала")
    else:
        print("[*] ВЫВОД: ответы РАЗНЫЕ между запросами (ожидаемо для challenge-нонса)")

    if samples:
        analyze_predictability(samples)
    return 0


if __name__ == "__main__":
    sys.exit(main())
