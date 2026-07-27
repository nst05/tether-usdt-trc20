"""Строгие интерфейсы транспортов без привязки к реализации."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CommandTransport(Protocol):
    frame_name: str | None
    last_tx: bytes
    last_raw_rx: bytes
    last_rx: bytes
    last_latency_ms: int
    last_attempts: int

    @property
    def is_open(self) -> bool: ...
    def send(self, command: str, *, retry_safe: bool = False) -> bytes: ...
    def close(self) -> None: ...


@runtime_checkable
class RawTransport(CommandTransport, Protocol):
    def raw_exchange(self, payload: bytes, *, response_timeout: float | None = None) -> bytes: ...
