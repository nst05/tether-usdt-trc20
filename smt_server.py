#!/usr/bin/env python3
"""
smt_server — исследовательский приёмный сервер телеметрии (авторизованная лабораторная среда).

Инженерная архитектура (слои):
  1. Транспорт        — TCP-listener, приём всплеска байтов.
  2. Framing          — сборка кадра: прибор шлёт пакет одним всплеском и ждёт ACK;
                        кадр считается завершённым по паузе (--idle) или закрытию.
  3. Parser           — заголовок / группы {..} / записи по документированному формату.
  4. Research-checks   — скан параметров CRC16 по кадру; проверка поля auth (MD5).
  5. Sink             — session_*.log (сырьё) + session_*.json (разбор) + ACK.

Назначение: ПРИЁМНАЯ сторона для физического прибора по GPRS/TCP. Сервер
принимает фактический пакет, сохраняет исходные байты и возвращает ACK.

Формат (по статическому разбору прошивки; параметры CRC16 — уточняются захватом):
  заголовок:  <имя>;<CRC16>;<CRC16>;<CRC16>;<ID64hex>;
  группы:     { <имя>;<...>;<N>; <записи> }
  запись:     <тип>;ДД.ММ.ГГГГ,чч:мм:сс;<накопитель×10000>;<значение %0.2f>;;<флаг>;

Запуск:
  python3 smt_server.py --host 0.0.0.0 --port <PORT> --crc-scan
На приборе задать SERVER_URL = <IP сервера>:<PORT>, дождаться физической сессии.
"""
import argparse
import hashlib
import json
import os
import re
import socket
import threading
import time

from smt_diagnostics import DiagnosticRecorder
from smt_logging import configure_logging

# ═══════════════════════ слой 3: парсер формата ═══════════════════════ #
HEADER_RE = re.compile(
    r"(?P<name>[^;{}]+);(?P<c1>[0-9A-Fa-f]{1,4});(?P<c2>[0-9A-Fa-f]{1,4});"
    r"(?P<c3>[0-9A-Fa-f]{1,4});(?P<id>[0-9A-Fa-f]{16});")
REC_RE = re.compile(
    r"(?P<type>\d+);(?P<d>\d{2})\.(?P<mo>\d{2})\.(?P<y>\d{2,4}),"
    r"(?P<h>\d{2}):(?P<mi>\d{2}):(?P<s>\d{2});(?P<acc>\d+);(?P<val>-?\d+\.\d+);;(?P<flag>\d+);")
AUTH_RE = re.compile(r"auth=([0-9A-Fa-f]{32})")


def parse_records(text):
    out = []
    for m in REC_RE.finditer(text):
        y = int(m['y']); y = 2000 + y if y < 100 else y
        out.append(dict(type=int(m['type']),
                        dt=f"{y:04d}-{int(m['mo']):02d}-{int(m['d']):02d} "
                           f"{m['h']}:{m['mi']}:{m['s']}",
                        accumulator=int(m['acc']),          # ×10000 (итоговое значение)
                        value=float(m['val']), flag=int(m['flag'])))
    return out


def parse_frame(raw: bytes):
    text = raw.decode("latin1", "replace")
    hm = HEADER_RE.search(text)
    header = None
    if hm:
        header = dict(name=hm['name'],
                      crc16=[hm['c1'].upper(), hm['c2'].upper(), hm['c3'].upper()],
                      id64=hm['id'].upper(), span=[hm.start(), hm.end()])
    groups = re.findall(r"\{[^{}]*\}", text)
    records = parse_records(text)
    am = AUTH_RE.search(text)
    return dict(header=header, groups=groups, records=records,
                auth=(am.group(1).upper() if am else None), text=text)


# ═════════════════ слой 4: исследовательские проверки ═════════════════ #
def _reflect(v, w):
    r = 0
    for _ in range(w):
        r = (r << 1) | (v & 1); v >>= 1
    return r


def crc16(data: bytes, poly, init, refin, refout, xorout):
    crc = init
    for b in data:
        if refin: b = _reflect(b, 8)
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    if refout: crc = _reflect(crc, 16)
    return crc ^ xorout


CRC16_VARIANTS = {   # имя: (poly, init, refin, refout, xorout)
    "CCITT-FALSE": (0x1021, 0xFFFF, False, False, 0x0000),
    "XMODEM":      (0x1021, 0x0000, False, False, 0x0000),
    "KERMIT":      (0x1021, 0x0000, True,  True,  0x0000),
    "MODBUS":      (0x8005, 0xFFFF, True,  True,  0x0000),
    "IBM/ARC":     (0x8005, 0x0000, True,  True,  0x0000),
    "MAXIM":       (0x8005, 0x0000, True,  True,  0xFFFF),
    "USB":         (0x8005, 0xFFFF, True,  True,  0xFFFF),
    "DNP":         (0x3D65, 0x0000, True,  True,  0xFFFF),
    "CCITT-1D0F":  (0x1021, 0x1D0F, False, False, 0x0000),
}


def crc16_scan(frame_text, target_hex):
    """Ищет вариант CRC16, дающий target над правдоподобными участками кадра
    (окна между разделителями ';' и «тело после заголовка»). Закрывает пункт
    [CHECK] отчёта — определение параметров CRC16 по реальному кадру."""
    try:
        target = int(target_hex, 16)
    except ValueError:
        return []
    body = frame_text.encode("latin1", "replace")
    seps = [i for i, c in enumerate(body) if c == 0x3B]      # позиции ';'
    windows = set()
    for s in seps[:80]:
        windows.add((0, s)); windows.add((s + 1, len(body)))
    hm = HEADER_RE.search(frame_text)
    if hm:
        windows.add((hm.end(), len(body)))                  # тело пакета
        windows.add((0, hm.start('c1')))                    # имя до 1-го CRC
        # тело от конца ID64 до первой '{' и до 'auth='
        am = frame_text.find("auth=")
        if am > hm.end(): windows.add((hm.end(), am))
    for gm in re.finditer(r"\{[^{}]*\}", frame_text):        # каждая группа
        windows.add((gm.start(), gm.end()))                 #   со скобками
        windows.add((gm.start() + 1, gm.end() - 1))         #   без скобок
    hits = []
    for a, b in windows:
        if a >= b: continue
        chunk = body[a:b]
        for name, (poly, init, ri, ro, xo) in CRC16_VARIANTS.items():
            if crc16(chunk, poly, init, ri, ro, xo) == target:
                hits.append(dict(variant=name, window=[a, b], length=b - a))
    return hits


def auth_check(frame_text, auth_hex):
    """Пробует воспроизвести поле auth как MD5 над телом пакета (несколько
    кандидатов входа). Подтверждает вывод отчёта: auth = MD5(содержимое) —
    контроль целостности, а не аутентификация отправителя."""
    cands = {}
    cands["весь кадр без auth-поля"] = AUTH_RE.sub("", frame_text)
    idx = frame_text.find("auth=")
    if idx >= 0:
        cands["всё до 'auth='"] = frame_text[:idx]
    res = []
    for label, s in cands.items():
        h = hashlib.md5(s.encode("latin1", "replace")).hexdigest().upper()
        res.append(dict(input=label, md5=h, match=(h == auth_hex.upper())))
    return res


# ═══════════════════════ слои 1-2-5: сервер ═══════════════════════ #
def hexdump(b, width=16):
    out = []
    for i in range(0, len(b), width):
        ch = b[i:i+width]
        hx = " ".join(f"{x:02X}" for x in ch)
        asc = "".join(chr(x) if 32 <= x < 127 else "." for x in ch)
        out.append(f"  {i:04X}  {hx:<{width*3}}  |{asc}|")
    return "\n".join(out)


def analyse(raw, quiet, do_crc):
    p = parse_frame(raw); hdr = p["header"]; rec = p["records"]
    if not quiet:
        if hdr:
            print(f"  заголовок: имя={hdr['name']!r} CRC16={hdr['crc16']} ID64={hdr['id64']}")
        print(f"  групп: {len(p['groups'])}, записей: {len(rec)}")
        for r in rec[:8]:
            print(f"    запись: тип={r['type']} {r['dt']} накопитель={r['accumulator']} "
                  f"значение={r['value']} флаг={r['flag']}")
        if len(rec) > 8:
            print(f"    … ещё {len(rec) - 8}")
    report = dict(header=hdr, groups=p["groups"], records=rec, auth=p["auth"])
    if do_crc and hdr:
        report["crc16_scan"] = {c: crc16_scan(p["text"], c) for c in hdr["crc16"]}
        if not quiet:
            for c, h in report["crc16_scan"].items():
                s = ", ".join(f"{x['variant']}[{x['window'][0]}:{x['window'][1]}]" for x in h)
                print(f"  CRC16 {c}: {s or 'совпадений нет'}")
    if p["auth"]:
        report["auth_check"] = auth_check(p["text"], p["auth"])
        if not quiet:
            for a in report["auth_check"]:
                print(f"  auth MD5 ({a['input']}): {a['md5']} {'✓ совпало' if a['match'] else ''}")
    return report, len(rec)


def _recv_frame(conn, *, idle, max_frame, connection_timeout):
    """Принять один кадр по паузе с общим дедлайном соединения."""
    conn.settimeout(idle)
    started = time.monotonic()
    buf = bytearray()
    while True:
        if time.monotonic() - started >= connection_timeout:
            return bytes(buf), "connection-timeout"
        try:
            data = conn.recv(4096)
        except TimeoutError:
            if buf:
                return bytes(buf), "idle"
            continue
        if not data:
            return bytes(buf), "closed"
        buf.extend(data)
        if len(buf) > max_frame:
            return bytes(buf), "too-large"


def handle_conn(conn, addr, args):
    started_ns = time.perf_counter_ns()
    diag = getattr(args, "diagnostic", None)
    if diag is not None:
        diag.emit("server", "connection.start", status="start", details={"remote": addr})
    ts = time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns() % 1_000_000_000:09d}"
    safe_ip = addr[0].replace(":", "_")
    base = os.path.join(args.outdir, f"session_{ts}_{safe_ip}_{addr[1]}_{threading.get_ident()}")
    print(f"\n[+] соединение от {addr} → {base}.log")
    buf, reason = _recv_frame(conn, idle=args.idle, max_frame=args.max_frame,
                              connection_timeout=getattr(args, "connection_timeout", 60.0))
    if reason == "too-large":
        print(f"[!] {addr}: кадр больше лимита {args.max_frame} байт — соединение закрыто")
        if diag is not None:
            diag.emit("server", "connection.end", status="error",
                      duration_ms=(time.perf_counter_ns() - started_ns) / 1_000_000,
                      details={"remote": addr, "reason": reason, "raw": buf},
                      error="frame too large")
        conn.close()
        return
    if reason == "connection-timeout" and not buf:
        if diag is not None:
            diag.emit("server", "connection.end", status="timeout",
                      duration_ms=(time.perf_counter_ns() - started_ns) / 1_000_000,
                      details={"remote": addr, "reason": reason})
        conn.close(); print(f"[-] {addr}: общий таймаут без данных"); return
    if not buf:
        if diag is not None:
            diag.emit("server", "connection.end", status="empty",
                      duration_ms=(time.perf_counter_ns() - started_ns) / 1_000_000,
                      details={"remote": addr, "reason": reason})
        conn.close(); print(f"[-] {addr}: пусто"); return
    open(base + ".log", "wb").write(buf)
    print(f"--- получено {len(buf)} байт ---")
    if not args.quiet:
        print(hexdump(buf[:512]) + ("\n  …" if len(buf) > 512 else ""))
    report, n = analyse(buf, args.quiet, args.crc_scan)
    json.dump(report, open(base + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if diag is not None:
        diag.emit("server", "packet.analyse", status="ok", details={
            "remote": addr, "reason": reason, "raw": buf, "report": report,
            "records": n, "raw_path": base + ".log", "json_path": base + ".json"})
    ack = args.ack.format(n=n).encode("latin1")
    try:
        conn.sendall(ack); print(f"  → ACK {ack!r}  (принято записей N={n})")
    except OSError as exc:
        if diag is not None:
            diag.emit("server", "ack.send", status="error", details={"remote": addr, "ack": ack}, error=exc)
    conn.close()
    if diag is not None:
        diag.emit("server", "connection.end", status="ok",
                  duration_ms=(time.perf_counter_ns() - started_ns) / 1_000_000,
                  details={"remote": addr, "reason": reason, "bytes": len(buf), "records": n, "ack": ack})
    print(f"[-] {addr} закрыто; разбор → {base}.json")


def serve(args):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port)); srv.listen(5)
    print(f"[smt_server] слушаю {args.host}:{args.port} · idle={args.idle}s · "
          f"ACK={args.ack!r} · CRC-скан={'on' if args.crc_scan else 'off'}")
    diag = getattr(args, "diagnostic", None)
    if diag is not None:
        diag.emit("server", "listener.start", status="ok", details=vars(args))
    while True:
        conn, addr = srv.accept()
        if diag is not None:
            diag.emit("server", "connection.accept", status="ok", details={"remote": addr})
        threading.Thread(target=handle_conn, args=(conn, addr, args), daemon=True).start()


def main():
    configure_logging()
    ap = argparse.ArgumentParser(description="Приёмный сервер телеметрии физического прибора.")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=40000, help="TCP-порт из SERVER_URL прибора")
    ap.add_argument("--idle", type=float, default=1.0, help="пауза (с), завершающая пакет")
    ap.add_argument("--ack", default="DATA ACCEPT:{n}\r\n", help="ACK; {n}=число записей")
    ap.add_argument("--outdir", default="sessions", help="каталог session_*.log/.json")
    ap.add_argument("--max-frame", type=int, default=2 * 1024 * 1024,
                    help="максимальный размер одного принятого пакета")
    ap.add_argument("--connection-timeout", type=float, default=60.0,
                    help="общий таймаут одного TCP-подключения, включая молчащий клиент")
    ap.add_argument("--crc-scan", action="store_true", help="искать вариант CRC16 по фактическому кадру")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    args.diagnostic = DiagnosticRecorder(
        os.path.join(os.path.abspath(args.outdir), "diagnostics"),
        application="server", version="4.8.0")
    args.diagnostic.emit("server", "arguments", status="ok", details=vars(args))
    try:
        serve(args)
    except KeyboardInterrupt:
        args.diagnostic.emit("server", "listener.stop", status="ok", details={"reason": "keyboard-interrupt"})
        print("\n[smt_server] остановлен")
    except Exception as exc:
        args.diagnostic.emit("server", "listener.stop", status="error", error=exc)
        raise
    finally:
        args.diagnostic.close()


if __name__ == "__main__":
    main()
