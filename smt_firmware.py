#!/usr/bin/env python3
"""Профили раскладки flash для поддерживаемых прошивок SMT.

Все адреса вынесены из парсеров в одно место. Текущий профиль сохраняет
байт-в-байт поведение v4.5.2 и может быть заменён при появлении другой прошивки.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FirmwareProfile:
    name: str
    checkpoint_halves: tuple[int, int]
    checkpoint_half_size: int
    state_record_size: int
    state_min_unix_ts: int
    state_max_unix_ts: int
    main_archive_start: int
    main_archive_end: int
    event_log_start: int
    event_log_end: int
    event_min_unix_ts: int
    event_max_unix_ts: int
    smart_data_offset: int
    smart_min_unix_ts: int
    smart_max_unix_ts: int

    @property
    def records_per_checkpoint_half(self) -> int:
        return self.checkpoint_half_size // self.state_record_size


SMT_SMART_DEFAULT = FirmwareProfile(
    name="SMT Smart / W25Q64 default",
    checkpoint_halves=(0x7FE000, 0x7FC000),
    checkpoint_half_size=0x2000,
    state_record_size=0x80,
    state_min_unix_ts=100_000_000,
    state_max_unix_ts=4_000_000_000,
    main_archive_start=0x40,
    main_archive_end=0x128000,
    event_log_start=0x15E000,
    event_log_end=0x171000,
    event_min_unix_ts=946_684_800,   # 2000-01-01 UTC
    event_max_unix_ts=4_102_444_800, # 2100-01-01 UTC
    smart_data_offset=0x40,
    smart_min_unix_ts=0x5E000000,
    smart_max_unix_ts=0x7A000000,
)

DEFAULT_PROFILE = SMT_SMART_DEFAULT
