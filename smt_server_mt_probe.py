#!/usr/bin/env python3
"""smt_server_mt_probe — проверка Server_MT на СВОЁМ TCP-командном сервере.

ТОЛЬКО ДЛЯ АВТОРИЗОВАННОГО ПЕНТЕСТА своего сервера (без реальных клиентов).

Зачем
-----
Поле Server_MT (см. smt_commands.json, handler sub_08006380) хранит 37 байт:
33-символьный токен + 4-байтовый проприетарный тег (не CRC/хэш — проверено).
Команда шлётся тем же протоколом, что и smt_core.transports.TcpServerTransport
(строка + терминатор, без логина/хендшейка) — см. smt_cli.py --transport tcp.

Этот скрипт шлёт "Server_MT" несколько раз подряд и смотрит:
  - стабилен ли ответ (один и тот же token+tag на каждый запрос), или
    сервер выдаёт новый токен на каждое обращение (нонс/сессионный);
  - совпадает ли токен/тег с уже известными образцами (smt_rogue_server.
    SERVER_MT_SAMPLES) — если да, сервер каждый раз возвращает ОДНО И ТО ЖЕ
    заранее выданное значение для этого канала/устройства (replay-риск).

Запуск
------
  python3 smt_server_mt_probe.py --host in.tehnomer.ru --port 40200
  python3 smt_server_mt_probe.py --host in.tehnomer.ru --port 40200 --count 10
  python3 smt_server_mt_probe.py --host in.tehnomer.ru --port 40200 --command DevInfo
"""
from __future__ import annotations

import argparse
import sys
import time

from smt_core import transports
from smt_rogue_server import SERVER_MT_ALPHABET, SERVER_MT_SAMPLES


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--command", default="Server_MT", help="какую команду слать (по умолчанию Server_MT)")
    ap.add_argument("--count", type=int, default=5, help="сколько раз подряд запросить")
    ap.add_argument("--delay", type=float, default=0.5, help="пауза между запросами, сек")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--terminator", choices=["none", "cr", "lf", "crlf"], default="crlf")
    args = ap.parse_args(argv)

    terms = {"none": b"", "cr": b"\r", "lf": b"\n", "crlf": b"\r\n"}
    print(f"[*] цель: {args.host}:{args.port} · команда: {args.command!r} · попыток: {args.count}")

    responses: list[bytes] = []
    for i in range(1, args.count + 1):
        tr = transports.TcpServerTransport(args.host, args.port, timeout=args.timeout,
                                            terminator=terms[args.terminator])
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
        print("[*] ВЫВОД: ответы РАЗНЫЕ между запросами")
        print("    → похоже на нонс/нумерацию/зависимость от состояния — проверить, меняется ли")
        print("      тег предсказуемо (инкремент, время) при фиксированном токене")
    return 0


if __name__ == "__main__":
    sys.exit(main())
