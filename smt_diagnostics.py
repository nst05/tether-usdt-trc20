#!/usr/bin/env python3
"""Полный диагностический журнал приложения.

Журнал фиксирует действия интерфейса/CLI, фоновые операции, обмены TX/RX,
телеметрию, исключения и длительности. Записи не маскируются и не обрезаются:
JSONL остаётся источником истины, человекочитаемый LOG удобен для просмотра,
CSV — для фильтрации и анализа.
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import platform
import queue
import sys
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from contextlib import contextmanager, suppress
from typing import Any


def _jsonable(value: Any) -> Any:
    """Преобразовать объект в JSON без потери диагностически полезных данных."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {
            "bytes": len(value),
            "hex": value.hex(" "),
            "latin1": value.decode("latin1", "replace"),
        }
    if isinstance(value, bytearray):
        return _jsonable(bytes(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    if isinstance(value, BaseException):
        return {
            "type": type(value).__name__,
            "message": str(value),
            "repr": repr(value),
        }
    try:
        json.dumps(value)
        return value
    except Exception:
        return repr(value)


class DiagnosticRecorder:
    """Потокобезопасный append-only журнал одного запуска программы."""

    def __enter__(self) -> DiagnosticRecorder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __init__(
        self,
        folder: str,
        *,
        application: str,
        version: str = "",
        live_sink: Callable[[dict], None] | None = None,
    ) -> None:
        self.folder = folder
        self.application = application
        self.version = version
        self.live_sink = live_sink
        self.session_id = uuid.uuid4().hex
        self.started_monotonic_ns = time.monotonic_ns()
        self._lock = threading.RLock()
        self._seq = 0
        self._jsonl = None
        self._log = None
        self.jsonl_path = ""
        self.log_path = ""
        os.makedirs(folder, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base = os.path.join(folder, f"diagnostic_{application}_{stamp}_{os.getpid()}_{self.session_id[:8]}")
        self.jsonl_path = base + ".jsonl"
        self.log_path = base + ".log"
        self._jsonl = open(self.jsonl_path, "a", encoding="utf-8", buffering=1)
        self._log = open(self.log_path, "a", encoding="utf-8", buffering=1)
        self.emit(
            "diagnostic",
            "session.start",
            status="ok",
            details={
                "application": application,
                "version": version,
                "pid": os.getpid(),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "cwd": os.getcwd(),
                "argv": list(sys.argv),
                "jsonl_path": self.jsonl_path,
                "log_path": self.log_path,
            },
        )

    @staticmethod
    def _timestamp() -> str:
        return _dt.datetime.now().astimezone().isoformat(timespec="milliseconds")

    def emit(
        self,
        component: str,
        action: str,
        *,
        status: str = "info",
        details: Any = None,
        duration_ms: float | None = None,
        error: BaseException | str | None = None,
        correlation_id: str = "",
    ) -> dict:
        with self._lock:
            self._seq += 1
            event = {
                "type": "diagnostic",
                "seq": self._seq,
                "ts": self._timestamp(),
                "monotonic_ns": time.monotonic_ns(),
                "session_id": self.session_id,
                "application": self.application,
                "version": self.version,
                "process_id": os.getpid(),
                "thread_id": threading.get_ident(),
                "thread_name": threading.current_thread().name,
                "component": component,
                "action": action,
                "status": status,
                "correlation_id": correlation_id,
                "details": _jsonable(details if details is not None else {}),
            }
            if duration_ms is not None:
                event["duration_ms"] = round(float(duration_ms), 3)
            if error is not None:
                if isinstance(error, BaseException):
                    event["error"] = _jsonable(error)
                    event["traceback"] = "".join(
                        traceback.format_exception(type(error), error, error.__traceback__)
                    )
                else:
                    event["error"] = str(error)
            line = json.dumps(event, ensure_ascii=False, sort_keys=False)
            try:
                self._jsonl.write(line + "\n")
                self._jsonl.flush()
            except Exception:
                pass
            human = (
                f"{event['ts']} #{event['seq']:06d} "
                f"[{event['thread_name']}] {component}.{action} "
                f"status={status}"
            )
            if duration_ms is not None:
                human += f" duration={float(duration_ms):.3f}ms"
            if correlation_id:
                human += f" cid={correlation_id}"
            human += " details=" + json.dumps(event["details"], ensure_ascii=False)
            if "error" in event:
                human += " error=" + json.dumps(event["error"], ensure_ascii=False)
            try:
                self._log.write(human + "\n")
                self._log.flush()
            except Exception:
                pass
        if self.live_sink is not None:
            with suppress(Exception):
                self.live_sink(dict(event))
        return event

    @contextmanager
    def span(self, component: str, action: str, *, details: Any = None, correlation_id: str = ""):
        started = time.perf_counter_ns()
        self.emit(component, action + ".start", status="start", details=details,
                  correlation_id=correlation_id)
        try:
            yield
        except Exception as exc:
            duration = (time.perf_counter_ns() - started) / 1_000_000
            self.emit(component, action + ".end", status="error", details=details,
                      duration_ms=duration, error=exc, correlation_id=correlation_id)
            raise
        else:
            duration = (time.perf_counter_ns() - started) / 1_000_000
            self.emit(component, action + ".end", status="ok", details=details,
                      duration_ms=duration, correlation_id=correlation_id)

    def export_csv(self, path: str, source_path: str | None = None) -> int:
        source = source_path or self.jsonl_path
        rows: list[dict] = []
        with open(source, encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if event.get("type") == "diagnostic":
                    rows.append(event)
        columns = [
            "seq", "ts", "session_id", "application", "version", "process_id",
            "thread_id", "thread_name", "component", "action", "status",
            "correlation_id", "duration_ms", "details", "error", "traceback",
        ]
        with open(path, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                flat = dict(row)
                flat["details"] = json.dumps(row.get("details", {}), ensure_ascii=False)
                flat["error"] = json.dumps(row.get("error", ""), ensure_ascii=False)
                writer.writerow(flat)
        self.emit("diagnostic", "export.csv", status="ok",
                  details={"path": path, "rows": len(rows), "source": source})
        return len(rows)

    def close(self) -> None:
        with suppress(Exception):
            self.emit(
                "diagnostic",
                "session.end",
                status="ok",
                details={
                    "events": self._seq,
                    "uptime_ms": (time.monotonic_ns() - self.started_monotonic_ns) / 1_000_000,
                },
            )
        with self._lock:
            for stream in (self._jsonl, self._log):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass
            self._jsonl = self._log = None


class InstrumentedQueue:
    """Совместимая с queue.Queue обёртка, фиксирующая каждую поставленную задачу."""

    def __init__(self, base: queue.Queue, recorder: DiagnosticRecorder, component: str = "gui") -> None:
        self._base = base
        self._recorder = recorder
        self._component = component

    def put(self, item, *args, **kwargs):
        self._recorder.emit(self._component, "task.enqueue", status="queued", details=item)
        return self._base.put(item, *args, **kwargs)

    def put_nowait(self, item):
        return self.put(item, block=False)

    def get(self, *args, **kwargs):
        return self._base.get(*args, **kwargs)

    def get_nowait(self):
        return self._base.get_nowait()

    def task_done(self):
        return self._base.task_done()

    def join(self):
        return self._base.join()

    def qsize(self):
        return self._base.qsize()

    def empty(self):
        return self._base.empty()

    def full(self):
        return self._base.full()


def export_jsonl_to_csv(jsonl_path: str, csv_path: str) -> int:
    recorder = DiagnosticRecorder.__new__(DiagnosticRecorder)
    recorder.jsonl_path = jsonl_path
    recorder.emit = lambda *args, **kwargs: {}  # type: ignore[assignment]
    return DiagnosticRecorder.export_csv(recorder, csv_path, source_path=jsonl_path)
