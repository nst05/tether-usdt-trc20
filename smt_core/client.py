"""Высокоуровневый клиент и штатная авторизация."""
from __future__ import annotations

__all__ = ["authenticate_provider", "authenticate_omega", "authenticate_fabric", "SmtClient"]

import time

from .commands import PASSPORT, PROTECTED_WRITE, command_name, is_mutating_command
from .interfaces import CommandTransport
from .protocol import response_has_auth_error, value_of


def authenticate_provider(client, password: str) -> dict:
    """Предъявить штатный шестизначный пароль Provider.

    По описанию прошивки PASSWORD_PROVIDER сам сравнивает введённое значение и
    при успехе переключает внутренний уровень доступа. Дополнительное чтение
    PASWORD_PROVID_VALUE не используется: это отдельный параметр, а не признак
    активной сессии.
    """
    password = str(password or "")
    if len(password) != 6:
        raise ValueError("Пароль Provider должен содержать ровно 6 символов")
    raw = client.send(f"PASSWORD_PROVIDER={password}", expert=True, mutating=True)
    if response_has_auth_error(raw):
        raise PermissionError("Прибор отклонил пароль Provider")
    return {
        "level": "provider",
        "verified": True,
        "verified_by": "PASSWORD_PROVIDER",
        "verified_at": time.time(),
    }


def authenticate_omega(client, password: str) -> dict:
    """Предъявить штатное значение PASSWORD_OMEGA без дополнительных команд."""
    password = str(password or "")
    if not password:
        raise ValueError("Пароль Omega не задан")
    raw = client.send(f"PASSWORD_OMEGA={password}", expert=True, mutating=True)
    if response_has_auth_error(raw):
        raise PermissionError("Прибор отклонил пароль Omega")
    return {
        "level": "omega",
        "verified": True,
        "verified_by": "PASSWORD_OMEGA",
        "verified_at": time.time(),
    }


def authenticate_fabric(client, password: str) -> dict:
    """Предъявить заводской пароль PASSWORD_FABRIC."""
    password = str(password or "")
    if not password:
        raise ValueError("Заводской пароль не задан")
    raw = client.send(f"PASSWORD_FABRIC={password}", expert=True, mutating=True)
    if response_has_auth_error(raw):
        raise PermissionError("Прибор отклонил заводской пароль")
    return {
        "level": "fabric",
        "verified": True,
        "verified_by": "PASSWORD_FABRIC",
        "verified_at": time.time(),
    }


class SmtClient:
    """Высокоуровневый клиент для работы с физическим прибором SMT."""

    def __init__(self, transport: CommandTransport, diagnostic: object = None) -> None:
        self.t = transport
        self.diagnostic = diagnostic

    def __enter__(self) -> SmtClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.t.close()

    def send(self, cmd: str, *, retry_safe: bool = False, expert: bool = False,
             mutating: bool | None = None):
        """Единая точка отправки.

        mutating — это запись/действие (True) или чтение-get (False). Если не задан,
        определяется единым классификатором каталога, включая голые действия. Критичные
        ИЗМЕНЯЮЩИЕ операции (`VALVE_OPEN`, `CLEAR_SABOTAG`, `SERVER_URL=…`)
        блокируются, пока не передан expert=True — живой второй рубеж поверх гейта GUI.
        Чтение защищённого параметра (get, например `VALVE`) разрешено всегда.
        Повтор допустим только для чтения; запись/действие не повторяются никогда."""
        name = command_name(cmd)
        mut = mutating if mutating is not None else is_mutating_command(cmd)
        safe = retry_safe and not mut
        started_ns = time.perf_counter_ns()
        if self.diagnostic is not None:
            self.diagnostic.emit("client", "command.start", status="start", details={
                "command": cmd, "name": name, "mutating": mut, "retry_safe": safe,
                "expert": expert, "transport": type(self.t).__name__,
            })
        try:
            raw = self.t.send(cmd, retry_safe=safe)
        except Exception as exc:
            if self.diagnostic is not None:
                self.diagnostic.emit("client", "command.end", status="error",
                    duration_ms=(time.perf_counter_ns() - started_ns) / 1_000_000,
                    error=exc, details={
                        "command": cmd, "name": name, "mutating": mut, "retry_safe": safe,
                        "expert": expert, "transport": type(self.t).__name__,
                        "tx": getattr(self.t, "last_tx", b""),
                        "rx_raw": getattr(self.t, "last_raw_rx", b""),
                        "rx_clean": getattr(self.t, "last_rx", b""),
                    })
            raise
        if self.diagnostic is not None:
            self.diagnostic.emit("client", "command.end", status="ok" if raw else "empty",
                duration_ms=(time.perf_counter_ns() - started_ns) / 1_000_000,
                details={
                    "command": cmd, "name": name, "mutating": mut, "retry_safe": safe,
                    "expert": expert, "transport": type(self.t).__name__,
                    "tx": getattr(self.t, "last_tx", b""),
                    "rx_raw": getattr(self.t, "last_raw_rx", b""),
                    "rx_clean": getattr(self.t, "last_rx", raw),
                    "latency_ms": getattr(self.t, "last_latency_ms", 0),
                    "attempts": getattr(self.t, "last_attempts", 1),
                    "echo_removed": getattr(self.t, "last_echo_removed", False),
                    "read_truncated": getattr(self.t, "last_read_truncated", False),
                })
        return raw

    def get(self, name: str) -> str | None:
        """Безопасное чтение параметра через единую точку отправки."""
        raw = self.send(name, retry_safe=True, mutating=False)
        return value_of(raw, name=name)

    def get_all(self, delay: float = 0.05) -> dict[str, str | None]:
        """Снять паспорт — прочитать все штатные параметры прибора."""
        out: dict[str, str | None] = {}
        for name in PASSPORT:
            try:
                out[name] = self.get(name)
            except Exception as exc:
                out[name] = f"<err:{exc}>"
            if delay:
                time.sleep(delay)
        return out
