#!/usr/bin/env python3
"""Приём, отправка и сборка телеметрии для GUI."""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import socket
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
TELEMETRY_DB_PATH = os.path.join(HERE, "sessions", "telemetry.sqlite3")

try:
    import smt_server as srv
except Exception:
    srv = None
try:
    import smt_telemetry_store as tele_store_mod
except Exception:
    tele_store_mod = None

def build_telemetry_packet(readings):
    """Собрать РЕАЛЬНЫЙ телеметрический пакет из фактически снятых показаний:
    одна запись V с текущей меткой времени, честные CRC16 (XMODEM/KERMIT/MODBUS)
    и auth=MD5(всё до 'auth='). Формат — как у прибора (sub_08019192)."""
    def num(name, d=0.0):
        try:
            return float(str(readings.get(name, d)).replace(",", "."))
        except Exception:
            return d
    acc = int(round(num("Volume") * 10000))
    val = num("VOLUME_INST")
    now = datetime.datetime.now()
    rec = f"1;{now.strftime('%d.%m.%Y,%H:%M:%S')};{acc};{val:0.2f};;0;"
    body = "{V;1;1;" + rec + "}"
    inner = body[1:-1].encode("latin1")
    sn = str(readings.get("DEVICE_SN") or "")
    hex_sn = "".join(f"{ord(ch):02X}" for ch in sn[:8])
    id64 = hex_sn.ljust(16, "0")[:16] if hex_sn else "0123456789ABCDEF"
    if srv is None:
        return body
    c1 = srv.crc16(inner, *srv.CRC16_VARIANTS["XMODEM"])
    c2 = srv.crc16(inner, *srv.CRC16_VARIANTS["KERMIT"])
    c3 = srv.crc16(inner, *srv.CRC16_VARIANTS["MODBUS"])
    prefix = f"TELE;{c1:04X};{c2:04X};{c3:04X};{id64};{body}"
    return prefix + "auth=" + hashlib.md5(prefix.encode("latin1")).hexdigest()

class TeleServer(threading.Thread):
    """Живой приёмник телеметрии (TCP): принимает всплеск, парсит, шлёт ACK."""
    def __init__(self, port, out_q, idle=0.8, max_frame=2 * 1024 * 1024, diagnostic=None):
        super().__init__(daemon=True)
        self.port, self.out_q, self.idle = port, out_q, idle
        self.max_frame = max_frame
        self.diagnostic = diagnostic
        self._stop_event = threading.Event(); self.srv = None

    def _diag(self, action, *, status="info", details=None, error=None, duration_ms=None):
        if self.diagnostic is None:
            return
        with contextlib.suppress(Exception):
            self.diagnostic.emit("telemetry", action, status=status, details=details,
                                 error=error, duration_ms=duration_ms)

    def run(self):
        try:
            self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.srv.bind(("0.0.0.0", self.port)); self.srv.listen(5)
            self.srv.settimeout(0.5)
            self.out_q.put(("tele_log", ("ok", f"[приём] слушаю 0.0.0.0:{self.port} — жду сессию прибора")))
            self._diag("listener.start", status="ok", details={"host": "0.0.0.0", "port": self.port, "idle": self.idle, "max_frame": self.max_frame})
        except Exception as e:
            self._diag("listener.start", status="error", details={"port": self.port}, error=e)
            self.out_q.put(("tele_log", ("err", f"[приём] не удалось открыть порт: {e}")))
            self.out_q.put(("tele_state", "off"))
            return
        while not self._stop_event.is_set():
            try:
                conn, addr = self.srv.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            self._diag("connection.accept", status="ok", details={"remote_ip": addr[0], "remote_port": addr[1]})
            threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True).start()
        with contextlib.suppress(Exception):
            self.srv.close()
        self._diag("listener.stop", status="ok", details={"port": self.port})
        self.out_q.put(("tele_log", ("ok", "[приём] остановлен")))
        self.out_q.put(("tele_state", "off"))

    def _handle_connection(self, conn, addr):
        started_ns = __import__("time").perf_counter_ns()
        conn.settimeout(self.idle); buf = b""
        with conn:
            while True:
                try:
                    d = conn.recv(4096)
                except TimeoutError:
                    break
                if not d:
                    break
                buf += d
                if len(buf) > self.max_frame:
                    self._diag("connection.frame", status="error", details={"remote": addr, "bytes": len(buf), "max_frame": self.max_frame}, error="frame too large")
                    self.out_q.put(("tele_log", ("err", f"[приём] {addr[0]}: пакет больше "
                                                         f"{self.max_frame} байт — закрыт")))
                    return
            if not buf:
                self._diag("connection.empty", status="empty", details={"remote": addr})
                return
            rep = srv.parse_frame(buf) if srv else {"records": []}
            self._diag("packet.receive", status="ok", details={"remote_ip": addr[0], "remote_port": addr[1], "raw": buf, "parsed": rep})
            if srv and rep.get("auth"):
                rep["auth_check"] = srv.auth_check(rep.get("text", ""), rep["auth"])
            n = len(rep.get("records", []))
            if tele_store_mod is not None:
                try:
                    packet_id, inserted, anomalies = tele_store_mod.ingest(
                        TELEMETRY_DB_PATH, buf, rep, source_ip=addr[0], source_port=addr[1])
                    state = "добавлен" if inserted else "дубликат"
                    self._diag("packet.store", status="warn" if anomalies else "ok", details={"packet_id": packet_id, "inserted": inserted, "records": n, "anomalies": anomalies})
                    self.out_q.put(("tele_log", ("warn" if anomalies else "ok",
                        f"[база] пакет #{packet_id} {state}; записей {n}; аномалий {anomalies}")))
                except Exception as exc:
                    self._diag("packet.store", status="error", details={"remote": addr}, error=exc)
                    self.out_q.put(("tele_log", ("warn", f"[база] не удалось сохранить: {exc}")))
            try:
                folder = os.path.join(HERE, "sessions")
                os.makedirs(folder, exist_ok=True)
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                safe_ip = addr[0].replace(":", "_")
                base = os.path.join(folder, f"session_{stamp}_{safe_ip}_{addr[1]}")
                with open(base + ".log", "wb") as stream:
                    stream.write(buf)
                with open(base + ".json", "w", encoding="utf-8") as stream:
                    json.dump(rep, stream, ensure_ascii=False, indent=2)
                self._diag("packet.files", status="ok", details={"raw_path": base + ".log", "json_path": base + ".json"})
                self.out_q.put(("tele_log", ("ok", f"[приём] сохранено: {base}.log/.json")))
            except Exception as exc:
                self._diag("packet.files", status="error", details={"remote": addr}, error=exc)
                self.out_q.put(("tele_log", ("warn", f"[приём] не удалось сохранить пакет: {exc}")))
            self.out_q.put(("tele_rx", (buf.decode("latin1", "replace"), rep, addr[0], n)))
            try:
                ack = f"DATA ACCEPT:{n}\r\n".encode()
                conn.sendall(ack)
                duration_ms = (__import__("time").perf_counter_ns() - started_ns) / 1_000_000
                self._diag("connection.complete", status="ok", duration_ms=duration_ms, details={"remote": addr, "bytes": len(buf), "records": n, "ack": ack})
            except OSError as exc:
                self._diag("connection.ack", status="error", details={"remote": addr, "records": n}, error=exc)

    def stop(self):
        self._stop_event.set()
        with contextlib.suppress(Exception):
            self.srv.close()

def tele_send(host, port, data, out_q, diagnostic=None):
    """Реальная отправка пакета по TCP на host:port, показ ACK (в отдельном потоке)."""
    def worker():
        started_ns = __import__("time").perf_counter_ns()
        if diagnostic is not None:
            diagnostic.emit("telemetry", "send.start", status="start", details={"host": host, "port": port, "data": data})
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(3)
            s.connect((host, port)); s.sendall(data)
            s.shutdown(socket.SHUT_WR)
            try:
                ack = s.recv(256)
            except TimeoutError:
                ack = b""
            duration_ms = (__import__("time").perf_counter_ns() - started_ns) / 1_000_000
            if diagnostic is not None:
                diagnostic.emit("telemetry", "send.end", status="ok", duration_ms=duration_ms, details={"host": host, "port": port, "data": data, "ack": ack})
            out_q.put(("tele_log", ("ok", f"[отправка] → {host}:{port} · {len(data)} байт · "
                                          f"ACK {ack.decode('latin1','replace')!r}")))
        except Exception as e:
            duration_ms = (__import__("time").perf_counter_ns() - started_ns) / 1_000_000
            if diagnostic is not None:
                diagnostic.emit("telemetry", "send.end", status="error", duration_ms=duration_ms, details={"host": host, "port": port, "data": data}, error=e)
            out_q.put(("tele_log", ("err", f"[отправка] ошибка: {e}")))
        finally:
            if s is not None:
                with contextlib.suppress(Exception):
                    s.close()
    threading.Thread(target=worker, daemon=True).start()
