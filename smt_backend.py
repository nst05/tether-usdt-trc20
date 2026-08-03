#!/usr/bin/env python3
"""Фоновый исполнитель GUI — единственный владелец транспорта."""
from __future__ import annotations

import contextlib
import datetime
import os
import threading
import time
import uuid
from decimal import Decimal

from smt_gui_support import (
    AUTH_CREDS,
    HERE,
    READING_COMMANDS,
    SECRET_READS,
    STATUS_NAMES,
    TELE_PARAMS,
    classify_secret,
    classify_send,
    decode_status_bits,
    hexdump,
    parse_reading,
    pretty,
    sc,
    ss,
    tools_mod,
)


class SessionStats:
    """Счётчики сессии: TX/RX байты, команды, ошибки, латентность."""
    __slots__ = ("tx_bytes", "rx_bytes", "tx_count", "rx_count",
                 "errors", "latency_sum", "latency_max", "latency_count",
                 "connected_at")

    def __init__(self):
        self.reset()

    def reset(self):
        self.tx_bytes = 0
        self.rx_bytes = 0
        self.tx_count = 0
        self.rx_count = 0
        self.errors = 0
        self.latency_sum = 0.0
        self.latency_max = 0.0
        self.latency_count = 0
        self.connected_at = 0.0

    def record_exchange(self, tx_len: int, rx_len: int, latency_ms: float, ok: bool):
        self.tx_bytes += tx_len
        self.rx_bytes += rx_len
        self.tx_count += 1
        if rx_len > 0:
            self.rx_count += 1
        if not ok:
            self.errors += 1
        if latency_ms > 0:
            self.latency_sum += latency_ms
            self.latency_count += 1
            if latency_ms > self.latency_max:
                self.latency_max = latency_ms

    def as_dict(self) -> dict:
        avg = (self.latency_sum / self.latency_count) if self.latency_count else 0.0
        uptime = time.time() - self.connected_at if self.connected_at else 0.0
        return {
            "tx_bytes": self.tx_bytes, "rx_bytes": self.rx_bytes,
            "tx_count": self.tx_count, "rx_count": self.rx_count,
            "errors": self.errors,
            "latency_avg_ms": round(avg, 1),
            "latency_max_ms": round(self.latency_max, 1),
            "uptime_s": round(uptime, 0),
        }


class Backend(threading.Thread):
    """Единственный поток, владеющий реальным транспортом прибора."""
    def __init__(self, task_q, out_q, critical=None, actions=None, catalog=None, diagnostic=None):
        super().__init__(daemon=True)
        self.task_q, self.out_q = task_q, out_q
        self.cli = None
        self.critical = critical or set()
        self.actions = actions or set()
        self.catalog = list(catalog or [])
        self._echo_noted = False
        self.recorder = None
        self.mode = "off"
        self.cancel_event = threading.Event()
        self.auth_state = {"level": "guest", "verified": False, "verified_at": 0.0}
        self.diagnostic = diagnostic
        self.stats = SessionStats()

    def cancel_current(self):
        self.cancel_event.set()

    def post(self, kind, payload):
        self.out_q.put((kind, payload))

    def log(self, tag, text):
        self.post("log", (tag, text))

    def _diag(self, action, *, status="info", details=None, duration_ms=None, error=None, correlation_id=""):
        if self.diagnostic is None:
            return
        with contextlib.suppress(Exception):
            self.diagnostic.emit(
                "backend", action, status=status, details=details,
                duration_ms=duration_ms, error=error, correlation_id=correlation_id)

    def run(self):
        while True:
            task = self.task_q.get()
            op = task.get("op")
            correlation_id = str(task.get("_diagnostic_id") or uuid.uuid4().hex)
            task["_diagnostic_id"] = correlation_id
            started_ns = time.perf_counter_ns()
            outcome = "ok"
            failure = None
            self._diag("task.start", status="start", details=task, correlation_id=correlation_id)
            try:
                if op == "quit":
                    self._close()
                    return
                if op == "connect":
                    self._connect(task)
                elif op == "disconnect":
                    self._close()
                    self.post("status", ("off", ""))
                    self.log("ok", "[·] Отключено.")
                elif self.cli is None:
                    self.log("err", "[!] Нет подключения к физическому прибору.")
                elif op == "read":
                    self._read(task["name"])
                elif op == "write":
                    self._send(f"{task['name']}={task['val']}", task.get("expert", False))
                elif op == "write_reading_provider":
                    self._write_reading_provider(task)
                elif op == "send":
                    self._send(task["text"], task.get("expert", False))
                elif op == "auth":
                    self._auth(task["cred"], task["value"])
                elif op == "passport":
                    self._passport()
                elif op == "authscan":
                    self._authscan()
                elif op == "tele_read":
                    self._tele_read()
                elif op == "preflight":
                    self._preflight()
                elif op == "scan_all":
                    self._scan_all()
                elif op == "batch":
                    self._batch(task.get("text", ""), task.get("expert", False),
                                task.get("dry_run", False))
                elif op == "export_session":
                    self._export_session(task.get("path"))
                elif op == "raw_hex":
                    self._raw_hex(task.get("hex", ""), task.get("timeout"), task.get("expert", False))
                elif op == "sms_receive":
                    self._sms_receive(task.get("delete", False))
                elif op == "modem_at":
                    self._modem_at(task.get("text", "AT"))
                elif op == "read_status":
                    self._read_status_panel()
                elif op == "read_archive_port":
                    self._read_archive_port(task.get("count", 20))
                elif op == "backup":
                    self._backup_params()
                elif op == "restore":
                    self._restore_params(task.get("params", {}), task.get("expert", False))
                elif op == "write_kfactor":
                    self._write_kfactor(task.get("value", ""), task.get("expert", False))
                elif op == "tele_auto_cycle":
                    self._tele_auto_cycle(task.get("host", ""), task.get("port", 0),
                                          task.get("interval", 60))
                elif op == "gsm_init_apn":
                    self._gsm_init_apn(task.get("apn", ""), task.get("user", ""),
                                       task.get("password", ""))
            except Exception as exc:
                outcome = "error"
                failure = exc
                self.log("err", f"[FAIL] {op}: {exc}")
                if op == "connect" or isinstance(exc, getattr(sc, "TransportError", OSError)):
                    self._close()
                    self.post("status", ("off", ""))
                if op == "connect":
                    self.post("connect_error", str(exc))
            finally:
                duration_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
                self._diag("task.end", status=outcome, details={"op": op, "task": task},
                           duration_ms=duration_ms, error=failure, correlation_id=correlation_id)

    def _wire_log(self, secret=False):
        tr = self.cli.t
        if secret:
            self.post("hex", "TX [секрет скрыт]")
            self.post("hex", "RX [секрет скрыт]")
            return
        self.post("hex", hexdump("TX", getattr(tr, "last_tx", b"")))
        # В hex показываются именно байты на проводе, включая оптическое эхо.
        self.post("hex", hexdump("RX", getattr(tr, "last_raw_rx", b"") or b""))
        if getattr(tr, "last_echo_removed", False) and not self._echo_noted:
            self._echo_noted = True
            self.log("ok", "[линия] Обнаружено само-эхо оптоголовки; оно автоматически "
                           "удаляется только из разбираемого ответа. В hex остаются исходные байты.")

    def _connect(self, task):
        """Открыть выбранный реальный транспорт."""
        self._close()
        self.stats.reset()
        self.stats.connected_at = time.time()
        transport = task.get("transport", "serial")
        if transport == "serial":
            self._connect_serial(task)
        elif transport == "tcp":
            self._connect_tcp(task)
        elif transport == "sms":
            self._connect_sms(task)
        else:
            raise ValueError(f"Неизвестный транспорт: {transport}")

    def _start_recorder(self, **header):
        if ss is None:
            return
        try:
            self.recorder = ss.SessionRecorder(os.path.join(HERE, "sessions"))
            self.recorder.header(**header)
            self.post("session_file", self.recorder.jsonl_path or "")
            self.log("ok", f"[сессия] запись на диск: {self.recorder.jsonl_path}")
        except Exception as exc:
            self.recorder = None
            self.log("warn", f"[сессия] журнал не открыт: {exc}")

    def _connect_serial(self, task):
        port = task["port"].strip()
        baud = int(task["baud"]); requested = task["framing"]
        bits = int(task.get("bytesize", 8)); parity = task.get("parity", "N")
        stopbits = float(task.get("stopbits", 1))
        self.log("ok", f"[*] Открываю {port} · {baud} {bits}{parity}{stopbits:g} · кадр {requested}…")
        tr = sc.OpticTransport(
            port, baud, bytesize=bits, parity=parity, stopbits=stopbits,
            xonxoff=bool(task.get("xonxoff")), rtscts=bool(task.get("rtscts")),
            dsrdtr=bool(task.get("dsrdtr")), dtr=bool(task.get("dtr")),
            rts=bool(task.get("rts")),
            response_timeout=float(task.get("response_timeout", 2.5)),
            idle_gap=float(task.get("idle_gap", 0.25)),
            read_retries=int(task.get("read_retries", 1)),
        )
        try:
            if requested == "auto":
                def _on_attempt(name, try_no, ok, raw):
                    mark = "✓ ответ есть" if ok else "нет ответа"
                    self.log("io", f"    · пробую кадр {name} (попытка {try_no}/2)… {mark}")
                    self.post("hex", hexdump(f"TX [{name} #{try_no}]", tr.last_tx))
                    self.post("hex", hexdump(f"RX [{name} #{try_no}]", tr.last_raw_rx or b""))
                self.log("ok", "[*] Порт открыт, определяю кадрирование (auto)…")
                frame_name, probe = tr.detect_framing("DevInfo", on_attempt=_on_attempt)
            else:
                self.log("ok", f"[*] Порт открыт, кадрирование зафиксировано: {requested}")
                tr.set_framing(requested)
                try:
                    probe = tr.probe("DevInfo")
                finally:
                    self.post("hex", hexdump(f"TX [{requested}]", tr.last_tx))
                    self.post("hex", hexdump(f"RX [{requested}]", tr.last_raw_rx or b""))
                frame_name = requested
        except Exception:
            tr.close(); raise
        self.cli = sc.SmtClient(tr); self.mode = "serial"; self._echo_noted = False
        self._wire_log(); devinfo = sc.describe_passport(probe)
        self.post("status", ("serial", tr.line_description()))
        self.log("ok", f"[+] Реальный прибор подключён: {tr.line_description()} · "
                       f"кадр {frame_name} · ответ {tr.last_latency_ms} мс")
        self.log("io", f"     DevInfo = {pretty(devinfo)!r}")
        self._start_recorder(port=port, baud=baud, framing=frame_name,
                             transport="serial", line=tr.line_description(),
                             devinfo=str(pretty(devinfo)))

    def _connect_tcp(self, task):
        host = task.get("host", "").strip(); port = int(task.get("tcp_port", 0))
        term_name = task.get("terminator", "CRLF")
        terms = {"нет": b"", "CR": b"\r", "LF": b"\n", "CRLF": b"\r\n"}
        if not host or not 1 <= port <= 65535:
            raise ValueError("Для TCP укажи host и порт 1…65535")
        tr = sc.TcpServerTransport(host, port, timeout=float(task.get("tcp_timeout", 3.0)),
                                   idle_gap=float(task.get("idle_gap", 0.25)),
                                   terminator=terms.get(term_name, b"\r\n"))
        self.log("ok", f"[*] Подключаю реальный TCP-шлюз {host}:{port}…")
        probe = tr.probe("DevInfo")
        self.cli = sc.SmtClient(tr); self.mode = "tcp"; self._wire_log()
        devinfo = sc.describe_passport(probe)
        self.post("status", ("tcp", f"{host}:{port}"))
        self.log("ok", f"[+] TCP-шлюз доступен: {host}:{port} · ответ {tr.last_latency_ms} мс")
        self.log("io", f"     DevInfo = {pretty(devinfo)!r}")
        self._start_recorder(port=f"{host}:{port}", baud=0, framing="tcp",
                             transport="tcp", devinfo=str(pretty(devinfo)))

    def _connect_sms(self, task):
        port = task.get("modem_port", "").strip(); phone = task.get("phone", "").strip()
        baud = int(task.get("modem_baud", 115200)); prefix = task.get("sms_prefix", "")
        self.log("ok", f"[*] Открываю GSM-модем {port} · {baud} для SMS → {phone}…")
        tr = sc.SmsTransport(port, phone, baud=baud, prefix=prefix,
                             response_timeout=float(task.get("sms_timeout", 20.0)))
        health = tr.health_check()
        self.cli = sc.SmtClient(tr); self.mode = "sms"; self._wire_log()
        self.post("status", ("sms", f"{port} → {phone}"))
        self.log("ok", f"[+] GSM-модем готов: {port} · SMS → {phone}")
        self.log("io", "     " + pretty(sc.decode_response(health).strip()))
        self._start_recorder(port=port, baud=baud, framing="sms-text",
                             transport="sms", devinfo=f"SMS target {phone}")

    def _close(self):
        if self.recorder is not None:
            with contextlib.suppress(Exception):
                self.recorder.close()
            self.recorder = None
        try:
            if self.cli is not None:
                close = getattr(self.cli.t, "close", None)
                if close:
                    close()
                elif getattr(self.cli.t, "ser", None) is not None:
                    self.cli.t.ser.close()
        except Exception:
            pass
        self.cli = None
        self.mode = "off"
        self.auth_state = {"level": "guest", "verified": False, "verified_at": 0.0}
        self.post("auth_state", dict(self.auth_state))

    def _tx(self, cmd, retry_safe=False, expert=False, mutating=None, kind="read"):
        """Один физический обмен. Повтор — только для чтения; критичные записи/
        действия проходят только с expert=True (второй рубеж в SmtClient.send).
        Каждый обмен пишется в журнал сессии на диск."""
        tr = self.cli.t
        name = sc.command_name(cmd)
        secret = name in getattr(sc, "SECRET_NAMES", set()) or name in AUTH_CREDS
        error = ""
        raw = b""
        try:
            raw = self.cli.send(cmd, retry_safe=retry_safe, expert=expert, mutating=mutating)
        except Exception as exc:
            error = str(exc)
            tx_err = len(getattr(tr, "last_tx", b"") or b"")
            rx_err = len(getattr(tr, "last_raw_rx", b"") or b"")
            self.stats.record_exchange(tx_err, rx_err, 0, ok=False)
            self.post("session_stats", self.stats.as_dict())
            self._safe_record(kind=kind, name=name, cmd=cmd, tr=tr, value=None,
                              ok=False, expert=expert,
                              critical=(name in self.critical), secret=secret, error=error)
            self._diag("exchange", status="error", error=exc, details={
                "kind": kind, "name": name, "command": cmd, "expert": expert,
                "critical": name in self.critical, "secret": secret,
                "transport": self.mode,
                "tx": getattr(tr, "last_tx", b""),
                "rx_raw": getattr(tr, "last_raw_rx", b""),
                "rx_clean": getattr(tr, "last_rx", b""),
                "latency_ms": getattr(tr, "last_latency_ms", 0),
                "attempts": getattr(tr, "last_attempts", 1),
            })
            raise
        self._wire_log(secret=secret)
        tx_len = len(getattr(tr, "last_tx", b"") or b"")
        rx_len = len(getattr(tr, "last_raw_rx", b"") or b"")
        latency = getattr(tr, "last_latency_ms", 0) or 0
        self.stats.record_exchange(tx_len, rx_len, latency, ok=bool(raw))
        self.post("session_stats", self.stats.as_dict())
        val = sc.value_of(raw, name=name)
        base = cmd.strip()
        if "=" not in base and base in AUTH_CREDS and val and classify_secret(val) == "открытым текстом":
            self.post("password", (base, pretty(val)))
        self._safe_record(kind=kind, name=name, cmd=cmd, tr=tr, value=val,
                          ok=bool(raw), expert=expert,
                          critical=(name in self.critical), secret=secret)
        self._diag("exchange", status="ok" if raw else "empty", details={
            "kind": kind, "name": name, "command": cmd, "value": val,
            "expert": expert, "critical": name in self.critical, "secret": secret,
            "transport": self.mode,
            "tx": getattr(tr, "last_tx", b""),
            "rx_raw": getattr(tr, "last_raw_rx", b""),
            "rx_clean": getattr(tr, "last_rx", b""),
            "latency_ms": getattr(tr, "last_latency_ms", 0),
            "attempts": getattr(tr, "last_attempts", 1),
            "echo_removed": getattr(tr, "last_echo_removed", False),
            "read_truncated": getattr(tr, "last_read_truncated", False),
        })
        return raw, val

    def _safe_record(self, **kw):
        if not self.recorder:
            return
        tr = kw.pop("tr", None)
        with contextlib.suppress(Exception):
            self.recorder.record(
                tx=getattr(tr, "last_tx", b""),
                rx_raw=getattr(tr, "last_raw_rx", b""),
                rx_clean=getattr(tr, "last_rx", b""),
                latency_ms=getattr(tr, "last_latency_ms", 0),
                attempts=getattr(tr, "last_attempts", 1),
                echo_removed=getattr(tr, "last_echo_removed", False),
                **kw)

    def _export_session(self, path):
        if not (self.recorder and path):
            self.log("warn", "[сессия] нечего экспортировать.")
            return
        try:
            n = self.recorder.export_csv(path)
            self.log("ok", f"[сессия] экспортировано {n} строк → {path}")
        except Exception as exc:
            self.log("err", f"[сессия] ошибка экспорта: {exc}")

    def _fmt(self, name, raw, val):
        if val not in (None, ""):
            return f"{name} = {pretty(val)}"
        if not raw:
            return f"{name} = (нет ответа)"
        text = pretty(sc.decode_response(raw).strip())
        return text or f"{name} = (ok)"

    def _read(self, name):
        raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
        shown = pretty(val) if val not in (None, "") else ""
        self.post("reading", (name, shown, datetime.datetime.now().isoformat(timespec="seconds")))
        self.log("io", f">> {name}\n<< {self._fmt(name, raw, val)}")

    _VALVE_COMMANDS = {"VALVE_OPEN", "VALVE_OPEN_FORCE", "VALVE_TRY_CLOSE", "VALVE"}
    _VALVE_READBACK = ["VALVE", "LOCK_STATE", "CLOSED"]

    def _send(self, text, expert):
        text = text.strip()
        if not text:
            return
        name, kind = classify_send(text, self.actions)
        if kind == "read":
            self._read(name)
            return
        critical = name in self.critical
        if critical and not expert:
            self.log("warn", f"[заблокировано] '{name}' — критичная команда ({kind}). "
                             "Включи «Экспертный режим» для фактической отправки на прибор.")
            return
        if critical:
            self.log("warn", f"⚠ ЭКСПЕРТ: отправка критичной команды >> {text}")
        raw, val = self._tx(text, retry_safe=False, expert=expert, mutating=True, kind=kind)
        self.log("io", f">> {text}\n<< {self._fmt(name, raw, val)}")
        if name in self._VALVE_COMMANDS and raw:
            self._valve_readback()


    def _valve_readback(self):
        """Автоматический обратный запрос состояния клапана после управляющей команды."""
        self.log("ok", "[клапан] обратный запрос состояния…")
        time.sleep(0.3)
        for param in self._VALVE_READBACK:
            try:
                val = self._read_value_quiet(param)
                self.log("io", f"  {param:<16} = {val!r}")
            except Exception as exc:
                self.log("warn", f"  {param:<16} = <ошибка: {exc}>")

    def _read_value_quiet(self, name):
        raw, val = self._tx(name, retry_safe=True, mutating=False, kind="service-read")
        return pretty(val) if val not in (None, "") else ""

    def _provider_is_verified(self):
        return bool(self.auth_state.get("verified")) and self.auth_state.get("level") == "provider"

    def _require_provider(self, *, expert=False):
        if not expert:
            raise PermissionError("Операция требует Экспертный режим")
        if not self._provider_is_verified():
            raise PermissionError(
                "Уровень Provider не подтверждён. Выполни штатную авторизацию на текущем подключении")

    def _write_reading_provider(self, task):
        """Прямая штатная запись показания после Provider-авторизации.

        Отправляется ровно одна команда SET. Проверочное чтение выполняется
        только когда оператор включил read-back. Архив не затрагивается.
        """
        self._require_provider(expert=task.get("expert", False))
        name = str(task.get("name") or "Volume").strip()
        if name not in READING_COMMANDS:
            raise ValueError(f"{name}: не является командой учётных показаний")
        target = parse_reading(task.get("val", ""))
        target_text = format(target, "f")
        verify = bool(task.get("verify", True))

        self.log("warn", f"[Provider] прямая отправка: {name}={target_text}")
        raw, _ = self._tx(f"{name}={target_text}", retry_safe=False, expert=True,
                          mutating=True, kind="reading-set")
        after = ""
        verified = False
        if verify:
            after = self._read_value_quiet(name)
            if after in (None, ""):
                raise RuntimeError("read-back не получен: состояние записи неизвестно")
            try:
                actual = parse_reading(after)
            except (ValueError, ArithmeticError) as exc:
                raise RuntimeError(f"read-back получен, но значение не распознано: {after!r}") from exc
            tolerance = max(abs(target) * Decimal("0.000000001"), Decimal("0.000001"))
            if abs(actual - target) > tolerance:
                raise RuntimeError(f"read-back не совпал: ожидалось {target}, прибор вернул {actual}")
            verified = True
            self.log("ok", f"[Provider] {name}={after}; read-back подтверждён")
        else:
            self.log("ok", f"[Provider] {name}={target_text}; команда отправлена без read-back")

        shown = after or target_text
        result = {
            "command": name,
            "requested_value": target_text,
            "new_value": shown,
            "readback": verify,
            "verified": verified,
            "response_bytes": len(raw or b""),
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self.post("reading", (name, shown, result["timestamp"]))
        self.post("reading_write_done", result)

    _AUTH_LEVELS = {
        "PASSWORD_FABRIC":  ("fabric",  "Заводской (f)",  True),
        "PASSWORD_OMEGA":   ("omega",   "Omega (U)",      True),
        "PASSWORD_PROVIDER":("provider","Provider",       False),
    }

    def _auth(self, cred, value):
        if cred == "PASSWORD_PROVIDER" and len(str(value)) != 6:
            raise ValueError("Пароль Provider должен содержать ровно 6 символов")
        self.auth_state = {"level": "guest", "verified": False, "verified_at": 0.0}
        self.post("auth_state", dict(self.auth_state))
        if self.mode != "sms":
            self.log("ok", "[auth] READY_TO_DIALOG …")
            try:
                self._tx("READY_TO_DIALOG", retry_safe=True, mutating=False, kind="auth")
            except Exception:
                pass
        cmd = f"{cred}={value}" if value != "" else cred
        self.log("ok", f"[auth] Предъявление учётных данных: {cred} …")
        raw, val = self._tx(cmd, retry_safe=False, expert=True, mutating=True, kind="auth")
        self.log("io", f">> {cred}=•••\n<< ответ получен ({len(raw)} байт; значение скрыто)")
        if cred in self._AUTH_LEVELS:
            level, label, is_master = self._AUTH_LEVELS[cred]
            if sc.response_has_auth_error(raw):
                raise PermissionError(f"Прибор отклонил пароль {label}")
            if self.mode == "sms":
                self.auth_state = {
                    "level": level, "verified": False, "master": is_master,
                    "verified_at": time.time(), "sms_sent": True,
                }
                self.post("auth_state", dict(self.auth_state))
                self.log("warn", f"[auth] Пароль {label} отправлен по SMS. "
                                 "Модем подтвердил отправку, но уровень прибора автоматически не проверен.")
            else:
                self.auth_state = {
                    "level": level, "verified": True, "master": is_master,
                    "verified_at": time.time(), "verified_by": cred,
                }
                self.post("auth_state", dict(self.auth_state))
                kind = "мастер-ключ (все команды)" if is_master else "нумерованный доступ"
                self.log("ok", f"[auth] {label} принят; {kind}.")
        else:
            self.auth_state = {"level": "guest", "verified": False, "verified_at": 0.0}
            self.post("auth_state", dict(self.auth_state))
            self.log("warn", "[auth] Команда отправлена. Для этого типа учётных данных "
                             "в документации нет однозначного подтверждения активного уровня.")

    def _passport(self):
        self.log("ok", "[*] Снятие паспорта с текущего транспорта…")
        ok = 0
        for name in sc.PASSPORT:
            try:
                raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
                if raw:
                    ok += 1
                self.log("io", f"  {name:<20} = {pretty(val)!r}")
            except Exception as exc:
                self.log("err", f"  {name:<20} = <err:{exc}>")
            time.sleep(0.04)
        self.log("ok", f"[*] Паспорт завершён: ответы {ok}/{len(sc.PASSPORT)}.")

    def _authscan(self):
        self.log("ok", "[*] Auth-scan — чтение доступных учётных параметров:")
        plain = False
        for name, desc in SECRET_READS:
            raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
            status = classify_secret(val)
            shown = repr(pretty(val)) if val else "—"
            self.log("io", f"    {name:<22}= {shown:<18} [{status}]  · {desc}")
            plain |= status == "открытым текстом"
        if plain:
            self.log("ok", "[OK] Прибор отдал хотя бы один действующий креденшл открытым текстом.")
        else:
            self.log("warn", "[!] Креды не отданы или маскированы текущей прошивкой/уровнем.")

    def _tele_read(self):
        self.log("ok", "[тел] Снятие текущих параметров по физическому оптопорту…")
        values = {}
        for name in TELE_PARAMS:
            raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
            values[name] = pretty(val) if val not in (None, "") else ""
            self.log("io", f"  {name:<16} = {values[name]!r}")
        self.post("tele_reading", values)

    def _scan_all(self):
        if self.mode == "sms":
            raise RuntimeError("Полный опрос по SMS отключён: он отправил бы сотни сообщений. "
                               "Используй выборочные команды или пакетный сценарий.")
        self.cancel_event.clear()
        values = {}
        total = len(self.catalog)
        self.log("ok", f"[*] Полный безопасный опрос каталога: {total} команд (только READ)…")
        for index, item in enumerate(self.catalog, 1):
            if self.cancel_event.is_set():
                self.log("warn", f"[scan] остановлено пользователем: {index-1}/{total}")
                break
            name = item["name"]
            if name in self.actions:
                # Действия нельзя безопасно "прочитать": голое имя запускает операцию.
                # Они входят в снимок как доступная возможность, но не выполняются.
                values[name] = "<action: не выполнялось>"
            else:
                try:
                    raw, val = self._tx(name, retry_safe=True, mutating=False, kind="scan")
                    values[name] = pretty(val) if val not in (None, "") else ("<no response>" if not raw else "")
                except Exception as exc:
                    values[name] = f"<err:{exc}>"
            self.post("scan_progress", (index, total, name, values[name]))
            time.sleep(0.015)
        self.post("snapshot", (values, self.mode))
        self.log("ok", f"[*] Снимок готов: {len(values)}/{total} параметров.")

    def _batch(self, text, expert, dry_run=False):
        if tools_mod is None:
            raise RuntimeError("модуль smt_tools.py не найден")
        steps = tools_mod.parse_batch_script(text, self.actions)
        all_steps = self._batch_flatten(steps)
        protected = [s for s in all_steps if s.kind in ("write", "action") and s.name in self.critical]
        if protected and not expert and not dry_run:
            names = ", ".join(sorted({x.name for x in protected}))
            raise PermissionError("сценарий содержит критические операции: " + names +
                                  ". Включи Экспертный режим.")
        self.log("ok", f"[batch] сценарий: {len(steps)} шагов верхнего уровня" +
                 (" · только проверка" if dry_run else " · выполнение"))
        if dry_run:
            self._batch_dry_run(steps, indent=0)
            self.post("batch_done", (True, len(all_steps), "Сценарий корректен"))
            return
        self.cancel_event.clear()
        variables: dict[str, str] = {}
        done = self._batch_exec(steps, expert, variables)
        ok = not self.cancel_event.is_set()
        msg = "Выполнено" if ok else "Остановлено пользователем"
        self.post("batch_done", (ok, done, msg))
        self.log("ok", f"[batch] завершено: {done} операций")

    def _batch_flatten(self, steps):
        """Плоский список всех атомарных шагов (для проверки критичных)."""
        result = []
        for s in steps:
            if s.body:
                result.extend(self._batch_flatten(s.body))
            else:
                result.append(s)
        return result

    def _batch_dry_run(self, steps, indent=0):
        pad = "  " * indent
        for i, step in enumerate(steps, 1):
            if step.kind == "loop":
                self.log("io", f"{pad}  LOOP ×{step.repeat} (строка {step.line}):")
                self._batch_dry_run(step.body, indent + 1)
                self.log("io", f"{pad}  ENDLOOP")
            elif step.kind == "if":
                self.log("io", f"{pad}  IF {step.condition} (строка {step.line}):")
                self._batch_dry_run(step.body, indent + 1)
            elif step.repeat > 0 and step.kind not in ("loop", "if"):
                self.log("io", f"{pad}  {i:03d} · строка {step.line}: REPEAT ×{step.repeat} "
                               f"{step.kind} {step.name}"
                               f"{('=' + step.value) if step.kind == 'write' else ''}")
            else:
                self.log("io", f"{pad}  {i:03d} · строка {step.line}: {step.kind} "
                               f"{step.name}{('=' + step.value) if step.kind == 'write' else ''}"
                               f"{(' ' + str(step.delay_ms) + ' ms') if step.kind == 'sleep' else ''}")

    def _batch_exec(self, steps, expert, variables, total_done=0):
        """Рекурсивное выполнение шагов с поддержкой LOOP, IF, REPEAT, STORE."""
        done = total_done
        for step in steps:
            if self.cancel_event.is_set():
                return done

            if step.kind == "loop":
                for iteration in range(step.repeat):
                    if self.cancel_event.is_set():
                        return done
                    variables["_iter"] = str(iteration + 1)
                    variables["_loop"] = str(step.repeat)
                    self.log("io", f"[batch] LOOP итерация {iteration + 1}/{step.repeat}")
                    done = self._batch_exec(step.body, expert, variables, done)
                continue

            if step.kind == "if":
                cond_val = tools_mod.evaluate_condition(step.condition, variables)
                if cond_val:
                    done = self._batch_exec(step.body, expert, variables, done)
                continue

            iterations = max(step.repeat, 1)
            for _rep in range(iterations):
                if self.cancel_event.is_set():
                    return done
                self.post("batch_progress", (done + 1, 0, step.source))
                resolved_name = tools_mod.substitute_vars(step.name, variables)
                resolved_value = tools_mod.substitute_vars(step.value, variables)

                if step.kind == "sleep":
                    deadline = time.monotonic() + step.delay_ms / 1000.0
                    while time.monotonic() < deadline:
                        if self.cancel_event.is_set():
                            return done
                        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
                elif step.kind == "read":
                    self._read(resolved_name)
                elif step.kind == "write":
                    self._send(f"{resolved_name}={resolved_value}", expert)
                elif step.kind == "action":
                    self._send(resolved_name, expert)
                elif step.kind == "store":
                    val = self._read_value_quiet(resolved_name)
                    variables[resolved_value] = val
                    self.log("io", f"[batch] STORE ${{{resolved_value}}} = {val!r}")
                elif step.kind == "print":
                    msg = tools_mod.substitute_vars(step.value, variables)
                    self.log("ok", f"[batch] PRINT: {msg}")
                elif step.kind == "assert":
                    result = tools_mod.evaluate_condition(step.condition, variables)
                    if not result:
                        self.log("err", f"[batch] ASSERT FAILED: {step.condition}")
                        self.cancel_event.set()
                        return done
                    self.log("ok", f"[batch] ASSERT OK: {step.condition}")
                done += 1
        return done

    def _raw_hex(self, text, timeout=None, expert=False):
        if not expert:
            raise PermissionError("RAW HEX доступен в Экспертном режиме: точные байты могут "
                                  "выполнить неизвестную запись или сервисную операцию.")
        compact = "".join(str(text).replace("0x", "").replace(",", " ").split())
        if not compact:
            return
        if len(compact) % 2:
            raise ValueError("HEX-строка должна содержать чётное число цифр")
        try:
            payload = bytes.fromhex(compact)
        except ValueError as exc:
            raise ValueError("Некорректная HEX-строка") from exc
        raw_exchange = getattr(self.cli.t, "raw_exchange", None)
        if raw_exchange is None:
            raise RuntimeError("Текущий транспорт не поддерживает сырой HEX-обмен")
        raw = raw_exchange(payload, response_timeout=float(timeout) if timeout else None)
        self._wire_log()
        self.log("io", f">> RAW HEX ({len(payload)}): {payload.hex(' ').upper()}\n"
                       f"<< RAW HEX ({len(raw)}): {raw.hex(' ').upper() if raw else '(нет ответа)'}")
        self.post("raw_result", raw)

    def _sms_receive(self, delete=False):
        receive = getattr(self.cli.t, "receive_unread", None)
        if receive is None:
            raise RuntimeError("Текущий транспорт не является GSM/SMS-модемом")
        messages = receive(delete=bool(delete))
        self.log("ok", f"[SMS] непрочитанных сообщений: {len(messages)}")
        for item in messages:
            self.log("io", f"  #{item.get('index')} {item.get('header')}\n     {item.get('text')}")
        self.post("sms_messages", messages)

    def _modem_at(self, text):
        send_at = getattr(self.cli.t, "send_at", None)
        if send_at is None:
            raise RuntimeError("AT-команды доступны только для GSM-модема")
        raw = send_at(str(text).strip())
        self._wire_log()
        self.log("io", f">> AT {text}\n<< {pretty(sc.decode_response(raw).strip())}")

    def _preflight(self):
        self.log("ok", "[*] Пре-флайт: проверка активного реального транспорта…")
        tr = self.cli.t
        if self.mode == "sms":
            raw = tr.health_check(); self._wire_log()
            self.log("ok", f"[OK] GSM-модем отвечает · {tr.last_latency_ms} мс")
            self.log("io", "     " + pretty(sc.decode_response(raw).strip()))
            return
        raw = tr.probe("DevInfo")
        self._wire_log(); value = sc.describe_passport(raw)
        self.log("ok", f"[OK] Канал отвечает · {self.mode} · кадр "
                       f"{getattr(tr, 'frame_name', '—') or 'ручной'} · "
                       f"{tr.last_latency_ms} мс · RX {len(tr.last_raw_rx)} байт" +
                       (" · оптическое эхо снято" if getattr(tr, 'last_echo_removed', False) else ""))
        self.log("io", f"     DevInfo = {pretty(value)!r}")

    def _read_status_panel(self):
        self.log("ok", "[статус] Считываю регистры состояния…")
        result = {}
        for name in STATUS_NAMES:
            try:
                raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
                result[name] = pretty(val) if val not in (None, "") else ""
                bits = decode_status_bits(name, result[name])
                active = [label for _, label, _, is_set in bits if is_set]
                self.log("io", f"  {name} = {result[name]}" +
                         (f"  [{', '.join(active)}]" if active else "  [норма]"))
            except Exception as exc:
                result[name] = f"<err:{exc}>"
                self.log("err", f"  {name} = ошибка: {exc}")
        self.post("status_panel", result)

    def _read_archive_port(self, count=20):
        self.log("ok", "[архив] Считываю количество записей…")
        raw, val = self._tx("ArcNumRecords", retry_safe=True, mutating=False, kind="read")
        num_str = pretty(val) if val not in (None, "") else "0"
        try:
            total = int(num_str.strip().rstrip(";"))
        except (ValueError, AttributeError):
            total = 0
        self.log("io", f"  ArcNumRecords = {total}")
        if total == 0:
            self.post("archive_data", {"total": 0, "records": []})
            self.log("warn", "[архив] Архив пуст.")
            return
        self.cancel_event.clear()
        records = []
        read_count = min(count, total)
        self.log("ok", f"[архив] Читаю последние {read_count} из {total} записей…")
        for i in range(read_count):
            if self.cancel_event.is_set():
                self.log("warn", "[архив] Остановлено пользователем.")
                break
            idx = total - read_count + i + 1
            try:
                raw, val = self._tx(f"ARCHIVE(6;1;{idx})", retry_safe=True, mutating=False, kind="read")
                text = pretty(val) if val not in (None, "") else sc.decode_response(raw).strip() if raw else ""
                records.append({"index": idx, "data": text})
            except Exception as exc:
                records.append({"index": idx, "data": f"<err:{exc}>"})
            self.post("archive_progress", (i + 1, read_count))
            time.sleep(0.02)
        self.post("archive_data", {"total": total, "records": records})
        self.log("ok", f"[архив] Прочитано {len(records)}/{total} записей.")

    def _backup_params(self):
        if self.mode == "sms":
            raise RuntimeError("Резервное копирование по SMS отключено.")
        self.cancel_event.clear()
        readable = [c for c in self.catalog
                    if c["name"] not in self.actions
                    and c["name"] not in getattr(sc, "SECRET_NAMES", set())]
        total = len(readable)
        self.log("ok", f"[бэкап] Чтение {total} параметров…")
        params = {}
        for i, item in enumerate(readable, 1):
            if self.cancel_event.is_set():
                self.log("warn", f"[бэкап] Остановлено: {i-1}/{total}")
                break
            name = item["name"]
            try:
                raw, val = self._tx(name, retry_safe=True, mutating=False, kind="backup")
                params[name] = pretty(val) if val not in (None, "") else None
            except Exception:
                params[name] = None
            self.post("backup_progress", (i, total, name))
            time.sleep(0.015)
        params = {k: v for k, v in params.items() if v is not None}
        self.post("backup_data", params)
        self.log("ok", f"[бэкап] Считано {len(params)}/{total} параметров.")

    def _restore_params(self, params, expert):
        if not expert:
            raise PermissionError("Восстановление требует Экспертный режим.")
        self.cancel_event.clear()
        writable = {c["name"] for c in self.catalog
                    if c["name"] not in self.actions
                    and (c.get("prov") == "0101" or c.get("user") == "0101")}
        to_write = {k: v for k, v in params.items()
                    if k in writable and v is not None
                    and k not in getattr(sc, "SECRET_NAMES", set())}
        total = len(to_write)
        self.log("ok", f"[восстановление] Запись {total} параметров…")
        ok = 0
        for i, (name, value) in enumerate(to_write.items(), 1):
            if self.cancel_event.is_set():
                self.log("warn", f"[восстановление] Остановлено: {i-1}/{total}")
                break
            critical = name in self.critical
            if critical and not expert:
                self.log("warn", f"  {name}: пропущен (критичная, нет экспертного)")
                continue
            try:
                self._tx(f"{name}={value}", retry_safe=False, expert=expert, mutating=True, kind="restore")
                ok += 1
                self.log("io", f"  {name}={value}")
            except Exception as exc:
                self.log("err", f"  {name}: ошибка записи: {exc}")
            self.post("restore_progress", (i, total, name))
            time.sleep(0.03)
        self.post("restore_done", {"total": total, "ok": ok})
        self.log("ok", f"[восстановление] Записано {ok}/{total} параметров.")

    def _write_kfactor(self, value, expert):
        self._require_provider(expert=expert)
        target = parse_reading(value)
        target_text = format(target, "f")
        self.log("warn", f"[KFACTOR] Запись коэффициента: {target_text}")
        raw, _ = self._tx(f"KFACTOR={target_text}", retry_safe=False, expert=True,
                          mutating=True, kind="kfactor-set")
        after = self._read_value_quiet("KFACTOR")
        if after in (None, ""):
            raise RuntimeError("read-back KFACTOR не получен")
        try:
            actual = parse_reading(after)
        except (ValueError, ArithmeticError) as exc:
            raise RuntimeError(f"read-back не распознан: {after!r}") from exc
        tolerance = max(abs(target) * Decimal("0.000001"), Decimal("0.000001"))
        if abs(actual - target) > tolerance:
            raise RuntimeError(f"read-back не совпал: ожидалось {target}, прибор вернул {actual}")
        self.log("ok", f"[KFACTOR] Записано {after}; read-back подтверждён")
        self.post("kfactor_done", {"value": after, "ok": True})

    def _tele_auto_cycle(self, host, port, interval_s):
        self.log("ok", f"[автотелеметрия] Снимаю показания и отправляю на {host}:{port}…")
        values = {}
        for name in TELE_PARAMS:
            try:
                raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
                values[name] = pretty(val) if val not in (None, "") else ""
            except Exception:
                pass
        self.post("tele_reading", values)
        from smt_gui_support import build_telemetry_packet
        pkt = build_telemetry_packet(values)
        data = pkt.encode("latin1", "replace")
        import socket
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((host, port))
            s.sendall(data)
            s.shutdown(socket.SHUT_WR)
            try:
                ack = s.recv(256)
            except TimeoutError:
                ack = b""
            self.log("ok", f"[автотелеметрия] Отправлено {len(data)} б → {host}:{port} · "
                           f"ACK {ack.decode('latin1', 'replace')!r}")
            self.post("tele_auto_sent", {"ok": True, "bytes": len(data), "ack": ack.decode("latin1", "replace")})
        except Exception as exc:
            self.log("err", f"[автотелеметрия] Ошибка отправки: {exc}")
            self.post("tele_auto_sent", {"ok": False, "error": str(exc)})
        finally:
            if s is not None:
                import contextlib as _cl
                with _cl.suppress(Exception):
                    s.close()

    def _gsm_init_apn(self, apn, user, password):
        send_at = getattr(self.cli.t, "send_at", None)
        if send_at is None:
            raise RuntimeError("AT-команды доступны только для GSM-модема")
        steps = [
            ("AT", "проверка модема"),
            ("AT+CPIN?", "проверка SIM"),
            (f'AT+CSTT="{apn}","{user}","{password}"', "установка APN"),
            ("AT+CIICR", "активация PDP-контекста"),
            ("AT+CIFSR", "получение IP-адреса"),
            ("AT+CSQ", "уровень сигнала"),
            ("AT+CREG?", "регистрация в сети"),
            ("AT+CGATT?", "статус GPRS"),
        ]
        results = []
        for cmd, desc in steps:
            self.log("io", f"[GSM] {desc}: {cmd}")
            try:
                raw = send_at(cmd)
                self._wire_log()
                text = pretty(sc.decode_response(raw).strip()) if raw else ""
                results.append({"cmd": cmd, "desc": desc, "response": text, "ok": True})
                self.log("io", f"  ← {text}")
            except Exception as exc:
                results.append({"cmd": cmd, "desc": desc, "response": str(exc), "ok": False})
                self.log("err", f"  ← ошибка: {exc}")
            time.sleep(0.5)
        self.post("gsm_init_done", results)
