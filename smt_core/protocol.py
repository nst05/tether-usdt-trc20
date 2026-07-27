"""Кадрирование и разбор текстового протокола SMT.

Четыре режима кадрирования (CR, CRLF, brace, IEC), декодирование ответов
с каскадным fallback (UTF-8 → CP1251 → Latin-1), снятие оптического эхо,
извлечение значений из пар ``NAME=value`` и распознавание ошибок авторизации.
"""
from __future__ import annotations

__all__ = [
    "AUTH_ERROR_MARKERS", "FRAMINGS", "TransportError", "PortClosedError",
    "decode_response", "strip_optical_echo", "value_of", "response_has_auth_error",
]

import re
from collections.abc import Callable

AUTH_ERROR_MARKERS = (
    "ERROR", "DENIED", "FAIL", "WRONG", "INVALID", "UNAUTHORIZED",
    "INCORRECT_PASSWORD", "INCORRECT_VALUE", "ACCESS_DENIED", "ERROR_COMMAND",
    "NAK", "ОШИБ", "ОТКАЗ", "НЕВЕР", "ЗАПРЕЩ",
)

FRAMINGS: dict[str, Callable[[str], bytes]] = {
    "cr": lambda command: (command + "\r").encode("utf-8"),
    "crlf": lambda command: (command + "\r\n").encode("utf-8"),
    "brace": lambda command: ("{" + command + "}").encode("utf-8"),
    "iec": lambda command: ("/?" + command + "!\r\n").encode("utf-8"),
}


class TransportError(IOError):
    """Ошибка физического транспорта."""


class PortClosedError(TransportError):
    """Порт закрыт или USB-устройство отключено."""


def decode_response(raw: bytes) -> str:
    """Декодировать ответ без mojibake: UTF-8 → CP1251 → Latin-1."""
    if not raw:
        return ""
    data = raw.replace(b"\x00", b"")
    for enc in ("utf-8", "cp1251", "latin1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin1", "replace")

def _leading_noise_len(data: bytes) -> int:
    n = 0
    while n < len(data) and data[n] in b"\x00 \t\r\n":
        n += 1
    return n

def strip_optical_echo(command: str, payload: bytes, raw: bytes) -> tuple[bytes, bool]:
    """Снять точное само-эхо оптоголовки, не удаляя настоящий `NAME=value`.

    Эхо может совпадать с полным физическим кадром, идти после CR/LF/NUL либо
    повториться дважды. Срезается только точное совпадение отправленных байтов.
    """
    if not raw:
        return b"", False
    data = raw
    removed = False
    for _ in range(3):
        lead = _leading_noise_len(data)
        tail = data[lead:]
        if payload and tail.startswith(payload):
            data = tail[len(payload):]
            removed = True
            continue
        # Некоторые преобразователи возвращают только ASCII-команду без обрамления.
        cmd_b = command.encode("ascii", "ignore")
        if cmd_b and tail.startswith(cmd_b):
            after = tail[len(cmd_b):]
            # `NAME=value` — это ответ, а не эхо команды чтения.
            if after.startswith(b"="):
                break
            if after[:1] in (b"\r", b"\n", b"}", b"!", b"/"):
                data = after[1:]
                removed = True
                continue
        break
    if removed:
        data = data[_leading_noise_len(data):]
    return data, removed

def _contains_named_response(command: str, raw: bytes) -> bool:
    """Проверка ответа на безопасную пробу кадрирования."""
    text = decode_response(raw)
    name = command.strip()
    return bool(re.search(r"(?:^|[\r\n{;])\s*" + re.escape(name) + r"\s*=", text, re.I))

def value_of(resp: bytes, name: str | None = None):
    """Извлечь значение из `NAME=value;`, устойчиво к нескольким строкам."""
    text = decode_response(resp).strip("\x00 \t\r\n")
    if not text:
        return None
    if name:
        matches = re.findall(re.escape(name) + r"\s*=\s*([^;\r\n}]*)", text, flags=re.I)
        if matches:
            return matches[-1].strip()
        # При запросе конкретного имени нельзя подставлять значение чужого поля.
        return None
    # Без конкретного имени последняя пара name=value остаётся полезным fallback.
    matches = re.findall(r"[A-Za-zА-Яа-я0-9_]+\s*=\s*([^;\r\n}]*)", text)
    if matches:
        return matches[-1].strip()
    return text.strip(";\r\n{} ") or None


def response_has_auth_error(raw: bytes | bytearray | str | None) -> bool:
    """Распознать явный отказ; пустой ответ также не является успехом."""
    if raw is None:
        return True
    data = raw if isinstance(raw, (bytes, bytearray)) else str(raw).encode("utf-8")
    text = decode_response(bytes(data)).strip("\x00 \t\r\n;{}")
    if not text:
        return True
    upper = text.upper()
    if upper in {"?", "NO", "FALSE"}:
        return True
    return any(marker in upper for marker in AUTH_ERROR_MARKERS)
