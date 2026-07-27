#!/usr/bin/env python3
"""Невизуальная поддержка GUI: настройки и каталог команд."""
from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation

from smt_logging import get_logger

logger = get_logger("gui_support")
HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".smt_optic_gui.json")

try:
    import smt_session as ss
except Exception as exc:
    logger.debug("smt_session unavailable", exc_info=exc)
    ss = None
try:
    import smt_client as sc  # noqa: F401 — реэкспорт для smt_backend и smt_gui
except Exception as exc:  # pragma: no cover
    raise RuntimeError(f"Не импортируется smt_client.py: {exc}") from exc
try:
    import smt_eventlog as evlog_mod
    import smt_state as state_mod
except Exception as exc:
    logger.debug("flash parsers unavailable", exc_info=exc)
    state_mod = evlog_mod = None
try:
    import smt_tools as tools_mod
except Exception as exc:
    logger.debug("smt_tools unavailable", exc_info=exc)
    tools_mod = None

from smt_core import commands as command_catalog
from smt_telemetry import (  # noqa: F401 — реэкспорт для smt_backend и smt_gui
    TELEMETRY_DB_PATH,
    TeleServer,
    build_telemetry_packet,
    srv,
    tele_send,
    tele_store_mod,
)

SECRET_READS = [
    ("PASSWORD_PROVIDER", "пароль провайдера (=%s, открытым текстом) — высший"),
    ("PASWORD_PROVID_VALUE", "числовое представление/проверка пароля"),
    ("PASSWORD_OMEGA", "пароль omega (может быть маскирован ******)"),
    ("PASSWORD_OMEGA2", "сервисный код omega (=%04x)"),
    ("MAGIC", "сервисная разблокировка"),
    ("ENABLE_OMEGA", "статус omega-доступа"),
]
MASK_MARKERS = ("****", "xxxx", "----")
TELE_PARAMS = ["Volume", "VOLUME_GLOB", "VOLUME_INST", "VOLUME_COMMIS", "VOLUME_DISC",
               "ArcNumRecords", "COUNT_SESSION", "ERROR_SESSION", "SERVER_URL",
               "STATUS_SYSTEM", "STATUS_ALARM", "DEVICE_SN"]
READING_COMMANDS = {"Volume", "VOLUME_GLOB", "VOLUME_COMMIS", "VOLUME_DISC"}
LEVELS = ["Гость", "Провайдер (П)", "Omega (О)", "Заводской (f)"]
AUTH_CREDS = ["PASSWORD_PROVIDER", "PASSWORD_OMEGA", "ENABLE_OMEGA",
              "PASSWORD_FABRIC", "MAGIC", "PASSWORD_OMEGA2"]
ENUM_OPTS = {
    "VALVE": ["1 (Lock_OPEN)", "0 (Lock_CLOSE)"],
    "LOCK_STATE": ["1 (открыт)", "0 (закрыт)"],
    "CLOSED": ["1 (закрыто)", "0 (открыто)"],
    "MODE_TRANSFER": ["0 (расписание)", "1 (по событию)"],
}

def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logger.debug("Не удалось загрузить настройки %s", SETTINGS_PATH, exc_info=exc)
        return {}

def save_settings(data: dict, *, merge: bool = True) -> None:
    """Сохранить настройки, объединяя с существующими по умолчанию."""
    try:
        if merge:
            existing = load_settings()
            existing.update(data)
            data = existing
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Не удалось сохранить настройки %s: %s", SETTINGS_PATH, exc)

def suggested_port(saved=None):
    if os.environ.get("SMT_PORT"):
        return os.environ["SMT_PORT"]
    if saved:
        return saved
    try:
        from serial.tools import list_ports
        ports = list(list_ports.comports())
        candidates = [item.device for item in ports if any(
            hint in ((item.device or "") + " " + (item.description or "")).lower()
            for hint in ("ttyusb", "ttyacm", "usbserial", "usbmodem", "ch340", "cp210", "ftdi", "com")
        )]
        if len(candidates) == 1:
            return candidates[0]
    except (ImportError, OSError) as exc:
        logger.debug("Автопоиск serial-порта недоступен", exc_info=exc)
    return "COM3" if os.name == "nt" else "/dev/ttyUSB0"

def parse_reading(value):
    """Разобрать показание в конечное Decimal без экспоненциальной записи."""
    text = str(value).strip().replace(",", ".")
    if not text:
        raise ValueError("Показание не задано")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Некорректное показание: {value!r}") from exc
    if not result.is_finite():
        raise ValueError("Показание должно быть конечным числом")
    return result

def reading_text(value):
    result = parse_reading(value)
    return format(result, "f")





def load_catalog():
    return command_catalog.load_catalog()


def pretty(value):
    """Сохранённая совместимость косметического декодирования v4.5.2."""
    if not isinstance(value, str) or not value:
        return value
    try:
        return value.encode("latin1").decode("utf-8")
    except Exception:
        return value


def access_human(flags):
    return {"0101": "чт+зп", "0100": "чтение", "0000": "нет"}.get(flags, flags)


def clean_desc(value, limit=None):
    if not value:
        return ""
    text = value.replace("**", "").replace("`", "").strip()
    return text[:limit - 1].rstrip() + "…" if limit and len(text) > limit else text


def hexdump(prefix, data):
    if isinstance(data, str):
        data = data.encode("latin1", "replace")
    hexs = " ".join(f"{byte:02X}" for byte in data)
    ascii_text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in data)
    return f"{prefix} [{len(data):>3}] {hexs}  |{ascii_text}|"


def classify_secret(value):
    if value is None or value == "":
        return "нет доступа"
    low = str(value).lower()
    return "маскирован" if any(marker in low for marker in MASK_MARKERS) else "открытым текстом"


def value_options(command):
    options = ENUM_OPTS.get(command["name"])
    if options:
        return options
    return ["1", "0"] if "флаг" in (command.get("type") or "") else []


def directions(command, is_action):
    actions = {command["name"]} if is_action else set()
    return command_catalog.directions(command, actions)


def build_critical(catalog):
    return command_catalog.build_critical(catalog)


def build_actions(catalog):
    return command_catalog.build_actions(catalog)


def access_at_level(command, level):
    column = command["prov"] if level in ("Провайдер (П)", "Заводской (f)") else \
             command["user"] if level == "Omega (О)" else None
    if column is None:
        return ("гость: публичное чтение (по гейту прибора)", True, False)
    can_read = column in ("0101", "0100")
    can_write = column == "0101"
    text = {"0101": "чтение+запись", "0100": "чтение", "0000": "нет"}.get(column, column)
    return text, can_read, can_write


def classify_send(text, actions):
    return command_catalog.classify_command(text, actions)


class CommandHistory:
    """Персистентная история команд и избранное."""

    MAX_HISTORY = 200

    def __init__(self, settings_path: str = SETTINGS_PATH):
        self._path = settings_path
        self._history: list[str] = []
        self._favorites: list[str] = []
        self._load()

    def _load(self):
        data = load_settings()
        self._history = list(data.get("command_history", []))[:self.MAX_HISTORY]
        self._favorites = list(data.get("command_favorites", []))

    def _save(self):
        save_settings({
            "command_history": self._history[:self.MAX_HISTORY],
            "command_favorites": self._favorites,
        })

    def add(self, cmd: str):
        cmd = cmd.strip()
        if not cmd:
            return
        if cmd in self._history:
            self._history.remove(cmd)
        self._history.insert(0, cmd)
        self._history = self._history[:self.MAX_HISTORY]
        self._save()

    def toggle_favorite(self, cmd: str) -> bool:
        cmd = cmd.strip()
        if cmd in self._favorites:
            self._favorites.remove(cmd)
            self._save()
            return False
        self._favorites.insert(0, cmd)
        self._save()
        return True

    def is_favorite(self, cmd: str) -> bool:
        return cmd.strip() in self._favorites

    @property
    def history(self) -> list[str]:
        return list(self._history)

    @property
    def favorites(self) -> list[str]:
        return list(self._favorites)

    def combined(self) -> list[str]:
        seen = set()
        result = []
        for cmd in self._favorites:
            if cmd not in seen:
                result.append(f"★ {cmd}")
                seen.add(cmd)
        for cmd in self._history:
            if cmd not in seen:
                result.append(cmd)
                seen.add(cmd)
        return result
