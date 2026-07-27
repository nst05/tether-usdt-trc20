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
    TELE_PARAMS,
    classify_secret,
    classify_send,
    hexdump,
    parse_reading,
    pretty,
    sc,
    ss,
    tools_mod,
)


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
            except Exception as exc:
                outcome = "error"
                failure = exc
                self.log("err", f"[FAIL] {op}: {exc}")
                if op == "connect" or isinstance(exc, getattr(sc, "TransportError", OSError)):
                    self._close()
                    self.post("status", ("off", ""))
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
                frame_name, probe = tr.detect_framing("DevInfo")
            else:
                tr.set_framing(requested); probe = tr.probe("DevInfo"); frame_name = requested
        except Exception:
            tr.close(); raise
        self.cli = sc.SmtClient(tr); self.mode = "serial"; self._echo_noted = False
        self._wire_log(); devinfo = sc.value_of(probe, name="DevInfo")
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
        devinfo = sc.value_of(probe, name="DevInfo")
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
        # Запись/действие не повторяются автоматически: неизвестно, успел ли прибор
        # выполнить первую посылку до потери ответа.
        raw, val = self._tx(text, retry_safe=False, expert=expert, mutating=True, kind=kind)
        self.log("io", f">> {text}\n<< {self._fmt(name, raw, val)}")


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

    def _auth(self, cred, value):
        self.auth_state = {"level": "guest", "verified": False, "verified_at": 0.0}
        self.post("auth_state", dict(self.auth_state))
        if cred == "PASSWORD_PROVIDER" and len(str(value)) != 6:
            raise ValueError("Пароль Provider должен содержать ровно 6 символов")
        cmd = f"{cred}={value}" if value != "" else cred
        self.log("ok", f"[auth] Предъявление учётных данных: {cred} …")
        raw, val = self._tx(cmd, retry_safe=False, expert=True, mutating=True, kind="auth")
        self.log("io", f">> {cred}=•••\n<< ответ получен ({len(raw)} байт; значение скрыто)")
        if cred in ("PASSWORD_PROVIDER", "PASSWORD_OMEGA"):
            level = "provider" if cred == "PASSWORD_PROVIDER" else "omega"
            label = "Provider" if level == "provider" else "Omega"
            if sc.response_has_auth_error(raw):
                raise PermissionError(f"Прибор отклонил пароль {label}")
            if self.mode == "sms":
                self.auth_state = {
                    "level": level, "verified": False,
                    "verified_at": time.time(), "sms_sent": True,
                }
                self.post("auth_state", dict(self.auth_state))
                self.log("warn", f"[auth] Пароль {label} отправлен по SMS. "
                                 "Модем подтвердил отправку, но уровень прибора автоматически не проверен.")
            else:
                self.auth_state = {
                    "level": level, "verified": True,
                    "verified_at": time.time(), "verified_by": cred,
                }
                self.post("auth_state", dict(self.auth_state))
                self.log("ok", f"[auth] Команда {cred} принята без явного отказа; "
                               f"активирован уровень {label} на текущем подключении.")
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
        protected = [s for s in steps if s.kind in ("write", "action") and s.name in self.critical]
        if protected and not expert and not dry_run:
            names = ", ".join(sorted({x.name for x in protected}))
            raise PermissionError("сценарий содержит критические операции: " + names +
                                  ". Включи Экспертный режим.")
        self.log("ok", f"[batch] сценарий: {len(steps)} шагов" +
                 (" · только проверка" if dry_run else " · выполнение"))
        if dry_run:
            for i, step in enumerate(steps, 1):
                self.log("io", f"  {i:03d} · строка {step.line}: {step.kind} "
                               f"{step.name}{('=' + step.value) if step.kind == 'write' else ''}"
                               f"{(' ' + str(step.delay_ms) + ' ms') if step.kind == 'sleep' else ''}")
            self.post("batch_done", (True, len(steps), "Сценарий корректен"))
            return
        self.cancel_event.clear()
        done = 0
        for i, step in enumerate(steps, 1):
            if self.cancel_event.is_set():
                self.log("warn", f"[batch] остановлено: {done}/{len(steps)}")
                self.post("batch_done", (False, done, "Остановлено пользователем")); return
            self.post("batch_progress", (i, len(steps), step.source))
            if step.kind == "sleep":
                deadline = time.monotonic() + step.delay_ms / 1000.0
                while time.monotonic() < deadline:
                    if self.cancel_event.is_set():
                        break
                    time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            elif step.kind == "read":
                self._read(step.name)
            elif step.kind == "write":
                self._send(f"{step.name}={step.value}", expert)
            elif step.kind == "action":
                self._send(step.name, expert)
            done += 1
        self.post("batch_done", (True, done, "Выполнено"))
        self.log("ok", f"[batch] завершено: {done}/{len(steps)}")

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
        self._wire_log(); value = sc.value_of(raw, name="DevInfo")
        self.log("ok", f"[OK] Канал отвечает · {self.mode} · кадр "
                       f"{getattr(tr, 'frame_name', '—') or 'ручной'} · "
                       f"{tr.last_latency_ms} мс · RX {len(tr.last_raw_rx)} байт" +
                       (" · оптическое эхо снято" if getattr(tr, 'last_echo_removed', False) else ""))
        self.log("io", f"     DevInfo = {pretty(value)!r}")
