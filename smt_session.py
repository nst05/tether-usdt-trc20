#!/usr/bin/env python3
"""Журнал сессии работы с ФИЗИЧЕСКИМ прибором.

Каждый обмен по оптопорту (чтение/запись/действие/аутентификация/пре-флайт)
сохраняется на диск сразу, построчно:
  * `sessions/optic_<штамп>.jsonl` — по одной JSON-записи на обмен (для разбора);
  * `sessions/optic_<штамп>.log`   — человекочитаемый протокол.

Свойства:
  * запись переживает перезапуск программы (каждый запуск — свой файл в общей папке);
  * секреты (пароли/креды) не сохраняются — значение маскируется;
  * сохранение никогда не роняет GUI (ошибки диска гасятся);
  * есть экспорт всей сессии в CSV.
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import time


def _hx(b) -> str:
    if not b:
        return ""
    if isinstance(b, str):
        b = b.encode("latin1", "replace")
    return b.hex(" ")


class SessionRecorder:
    """Потокобезопасный журнал одной физической сессии (JSONL + LOG)."""

    def __enter__(self) -> SessionRecorder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __init__(self, folder: str, mask_secrets: bool = True):
        self.folder = folder
        self.mask_secrets = mask_secrets
        self.jsonl_path: str | None = None
        self.log_path: str | None = None
        self._jsonl = None
        self._log = None
        self.count = 0
        try:
            os.makedirs(folder, exist_ok=True)
            now = datetime.datetime.now()
            stamp = now.strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}_{time.time_ns()}"
            self.jsonl_path = os.path.join(folder, f"optic_{stamp}.jsonl")
            self.log_path = os.path.join(folder, f"optic_{stamp}.log")
            self._jsonl = open(self.jsonl_path, "a", encoding="utf-8")
            self._log = open(self.log_path, "a", encoding="utf-8")
        except Exception:
            self._jsonl = self._log = None  # тихо: работа с прибором важнее журнала

    # ── служебное ──
    def _write(self, obj: dict, human: str) -> None:
        if self._jsonl:
            try:
                self._jsonl.write(json.dumps(obj, ensure_ascii=False) + "\n")
                self._jsonl.flush()
            except Exception:
                pass
        if self._log:
            try:
                self._log.write(human + "\n")
                self._log.flush()
            except Exception:
                pass
        self.count += 1

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now().isoformat(timespec="milliseconds")

    # ── публичное ──
    def header(self, *, port: str, baud: int, framing: str, devinfo: str = "") -> None:
        ts = self._now()
        self._write(
            {"type": "session", "ts": ts, "port": port, "baud": baud,
             "framing": framing, "devinfo": devinfo},
            f"# сессия {ts} · порт {port} · {baud} 8N1 · кадр {framing}"
            + (f" · DevInfo={devinfo!r}" if devinfo else ""),
        )

    def record(self, *, kind: str, name: str, cmd: str,
               tx: bytes = b"", rx_raw: bytes = b"", rx_clean: bytes = b"",
               value=None, latency_ms: int = 0, attempts: int = 1,
               echo_removed: bool = False, ok: bool = True,
               expert: bool = False, critical: bool = False,
               secret: bool = False, error: str = "") -> None:
        ts = self._now()
        shown_val = value
        shown_cmd = cmd
        if secret and self.mask_secrets:
            shown_val = "•••" if value not in (None, "") else value
            if "=" in cmd:
                shown_cmd = cmd.split("=", 1)[0] + "=•••"
            tx = rx_raw = rx_clean = b""
        entry = {
            "type": "exchange", "ts": ts, "kind": kind, "name": name,
            "cmd": shown_cmd, "value": shown_val,
            "tx_hex": _hx(tx), "rx_raw_hex": _hx(rx_raw), "rx_clean_hex": _hx(rx_clean),
            "latency_ms": latency_ms, "attempts": attempts,
            "echo_removed": echo_removed, "ok": ok,
            "expert": expert, "critical": critical, "secret": secret,
        }
        if error:
            entry["error"] = error
        flags = "".join(f for f, on in
                        (("K", critical), ("E", expert), ("S", secret), ("!", not ok)) if on)
        human = (f"{ts}  {kind:<7} {shown_cmd:<28} -> "
                 f"{('' if shown_val in (None, '') else repr(shown_val))}"
                 f"  [{latency_ms}ms x{attempts}{(' ' + flags) if flags else ''}]")
        if error:
            human += f"  ERROR: {error}"
        self._write(entry, human)

    def export_csv(self, path: str) -> int:
        """Выгрузить текущую сессию (jsonl) в CSV. Возвращает число строк."""
        rows = []
        if self.jsonl_path and os.path.exists(self.jsonl_path):
            with open(self.jsonl_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if obj.get("type") == "exchange":
                        rows.append(obj)
        cols = ["ts", "kind", "name", "cmd", "value", "latency_ms", "attempts",
                "echo_removed", "ok", "expert", "critical", "secret",
                "tx_hex", "rx_raw_hex", "rx_clean_hex", "error"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return len(rows)

    def close(self) -> None:
        for h in (self._jsonl, self._log):
            try:
                if h:
                    h.close()
            except Exception:
                pass
        self._jsonl = self._log = None


def _jsonl_to_csv(jsonl_path: str, csv_path: str) -> int:
    """Офлайн-конвертация ранее записанного .jsonl в .csv (без GUI)."""
    r = SessionRecorder.__new__(SessionRecorder)
    r.jsonl_path = jsonl_path
    return r.export_csv(csv_path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit("использование: python3 smt_session.py <сессия.jsonl> [выход.csv]")
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src.rsplit(".", 1)[0] + ".csv"
    n = _jsonl_to_csv(src, dst)
    print(f"экспортировано строк: {n} → {dst}")
