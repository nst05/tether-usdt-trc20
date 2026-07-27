"""Каталог и классификация команд SMT.

Единый источник истины для GUI, CLI, пакетных сценариев и клиента.
"""
from __future__ import annotations

__all__ = [
    "BAUD", "PASSPORT", "PROTECTED_WRITE", "IMPERATIVE_ACTIONS", "SECRET_NAMES",
    "CommandKind", "command_name", "load_catalog", "build_actions", "build_critical",
    "classify_command", "is_mutating_command", "is_protected", "directions",
]

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

BAUD = 9600

PASSPORT = [
    "DevInfo", "DEVICE_SN", "HW_VERSION", "VER_PO", "VER_PROTOCOL",
    "NUMBER_BOARD", "NUMBER_BOARD2", "DATE_WORK", "DATE_VERIFIC", "DATE_VERIFIC_NEXT",
    "Volume", "VOLUME_GLOB", "VOLUME_INST", "VOLUME_COMMIS", "VOLUME_DISC",
    "GAS_DAY", "GAS_RANGE", "KFACTOR", "PABS", "Q_PosLimit", "Q_NegLimit",
    "QGL_MIN", "QGL_MAX", "QFL_LIMIT",
    "Max_Temp", "Min_Temp", "EXT_MAX_TEMP", "EXT_MIN_TEMP", "SN_SGM_E",
    "TEMP_GAS_MIN_CRASH", "TEMP_GAS_MAX_CRASH",
    "EN_KALMAN_FILTER", "KALMAN_K", "KALMAN_BORDER_H", "KALMAN_BORDER_L",
    "VALVE", "VALVE_AUTO_CONTROL", "CNT_VALVE_MIN",
    "STATUS_SYSTEM", "STATUS_WARNING", "STATUS_ALARM", "STATUS_CRASH",
    "BAN_OPEN_CASE", "COMMISSIONING",
    "SERVER_URL", "Server_MT", "SERVER_URL2",
    "APN_ADDRESS", "APN_LOGIN", "BALANCE_PHONE", "MDM_SPEED", "GET_GSM_INFO",
    "COUNT_SESSION", "ERROR_SESSION", "RS485_ENABLE",
    "DATETIME", "TIME_ZONE", "LCD_MENU", "LCD_TIME", "KONTRAST", "OPTIC_TIME",
    "COUNT_BAT_REPLACE", "TIME_BAT_REPLACE", "TEL_BAT_REPLACE",
    "ArcNumRecords", "RTC_CALIB",
]

PROTECTED_WRITE = {
    "Volume", "VOLUME_GLOB", "VOLUME_INST", "VOLUME_COMMIS", "VOLUME_DISC",
    "ADD_DISCREDITED_VOLUME", "ADD_DISC_ALARM", "ADD_DISC_CRASH",
    "ENABLE_DISCREDITED_VOLUME", "KFACTOR", "GAS_RANGE", "PABS",
    "VALVE", "VALVE_OPEN", "VALVE_OPEN_FORCE", "VALVE_TRY_CLOSE",
    "VALVE_AUTO_CONTROL", "VALVE_CLOSE_REV_P", "EN_MDM_CHNG_VLV",
    "VALVE_DELAY_TRY_OPEN", "CNT_VALVE_MIN", "CLEAR_SABOTAG", "BAN_OPEN_CASE",
    "DATE_VERIFIC", "DATE_VERIFIC_NEXT", "COMMISSIONING", "CLEAR_ARHIVE",
    "DEFAULT_SETTINGS", "RSTSMT", "WARNING_CLEAR", "ALARM_CLEAR", "CRASH_CLEAR",
    "CLEAR_SN_SGM", "DATETIME", "TIME_ZONE", "RTC_CALIB", "RTC_OUTPUT_CALIB",
    "SERVER_URL", "SERVER_URL2", "APN_ADDRESS", "APN_LOGIN", "APN_PASSWORD",
    "PASSWORD_PROVIDER", "PASSWORD_OMEGA", "PASSWORD_OMEGA2", "PASSWORD_FABRIC",
    "MAGIC", "ENABLE_OMEGA", "EVENT_OMEGA",
}

IMPERATIVE_ACTIONS = {
    "VALVE_OPEN", "VALVE_OPEN_FORCE", "VALVE_TRY_CLOSE", "VALVE_CLOSE_REV_P",
    "CLEAR_SABOTAG", "CLEAR_ARHIVE", "CLEAR_SN_SGM",
    "WARNING_CLEAR", "ALARM_CLEAR", "CRASH_CLEAR",
    "DEFAULT_SETTINGS", "RSTSMT", "COMMISSIONING",
}

PROTECTED_WRITE |= IMPERATIVE_ACTIONS | {
    "READ_CALIB_LOG", "EXIT", "READYTD", "READY_TO_DIALOG",
    "ADD_DISC_ALARM", "ADD_DISC_CRASH", "CLEAR_COUNT", "CLEAR_QDF",
    "CLEAR_MDM_CNT", "Modem_START", "START", "ADD_DISCREDITED_VOLUME",
}

SECRET_NAMES = {
    "PASSWORD_PROVIDER", "PASSWORD_OMEGA", "PASSWORD_OMEGA2", "PASSWORD_FABRIC",
    "PASWORD_PROVID_VALUE", "MAGIC", "ENABLE_OMEGA", "EVENT_OMEGA", "APN_PASSWORD",
}

CommandKind = Literal["read", "write", "action"]


def command_name(command: str) -> str:
    """Вернуть имя из `NAME`, `NAME=value`, `{NAME}` или `/?NAME!`."""
    return str(command).split("=", 1)[0].strip().strip("{}!/? ").strip()


def load_catalog(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Загрузить неизменяемый внешний каталог команд."""
    catalog_path = Path(path) if path else Path(__file__).resolve().parent.parent / "smt_commands.json"
    with catalog_path.open(encoding="utf-8") as stream:
        document = json.load(stream)
    commands = document.get("commands")
    if not isinstance(commands, list):
        raise ValueError(f"Некорректный каталог команд: {catalog_path}")
    return commands


def build_actions(catalog: Iterable[Mapping[str, Any]]) -> set[str]:
    actions = {str(item.get("name", "")) for item in catalog
               if "действие" in str(item.get("type") or "").lower()}
    return actions | set(IMPERATIVE_ACTIONS)


def build_critical(catalog: Iterable[Mapping[str, Any]]) -> set[str]:
    return set(PROTECTED_WRITE) | {
        str(item.get("name", "")) for item in catalog if item.get("protected_write")
    }


def classify_command(command: str, actions: Iterable[str] | None = None) -> tuple[str, CommandKind]:
    """Классифицировать команду один раз для всех интерфейсов."""
    text = str(command or "").strip()
    name = command_name(text)
    if "=" in text:
        return name, "write"
    action_set = set(IMPERATIVE_ACTIONS)
    if actions is not None:
        action_set.update(actions)
    return name, "action" if name in action_set else "read"


def is_mutating_command(command: str, actions: Iterable[str] | None = None) -> bool:
    return classify_command(command, actions)[1] != "read"


def is_protected(command: str) -> bool:
    return command_name(command) in PROTECTED_WRITE


def directions(command: Mapping[str, Any], actions: Iterable[str] | None = None) -> tuple[bool, bool, bool]:
    name = str(command.get("name", ""))
    if classify_command(name, actions)[1] == "action":
        return False, False, True
    read_only = str(command.get("type") or "").lower().strip() == "чтение"
    return True, not read_only, False
