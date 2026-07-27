"""Строгие интерфейсы транспортов без привязки к реализации.

Каждый транспорт обязан реализовать CommandTransport; расширенные возможности
(сырой обмен, SMS-приём) проверяются через дополнительные протоколы.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CommandTransport(Protocol):
    """Минимальный контракт транспорта для SmtClient."""

    frame_name: str | None
    last_tx: bytes
    last_raw_rx: bytes
    last_rx: bytes
    last_latency_ms: int
    last_attempts: int

    @property
    def is_open(self) -> bool: ...

    def send(self, command: str, *, retry_safe: bool = False) -> bytes: ...

    def probe(self, probe_cmd: str = "DevInfo") -> bytes: ...

    def close(self) -> None: ...


@runtime_checkable
class RawTransport(CommandTransport, Protocol):
    """Транспорт с поддержкой сырого байтового обмена."""

    def raw_exchange(self, payload: bytes, *, response_timeout: float | None = None) -> bytes: ...
