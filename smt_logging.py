#!/usr/bin/env python3
"""Общая конфигурация стандартного logging без изменения пользовательского UI."""
from __future__ import annotations

import logging
import os

_ROOT_NAME = "smt_controller"


def get_logger(component: str) -> logging.Logger:
    logger = logging.getLogger(f"{_ROOT_NAME}.{component}")
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def configure_logging(level: str | int | None = None) -> None:
    """Включить диагностический stderr-лог по запросу приложения/переменной среды."""
    selected = level if level is not None else os.environ.get("SMT_LOG_LEVEL", "WARNING")
    numeric = selected if isinstance(selected, int) else getattr(logging, str(selected).upper(), logging.WARNING)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
