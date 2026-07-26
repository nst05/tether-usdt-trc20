#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Клиент физического прибора через оптический UART/RS-485.

Модуль специально не содержит эмуляторов. Главная задача транспорта — надёжно
работать с реальной USB-оптоголовкой: безопасно определить кадрирование на
команде чтения, снять оптическое эхо, дождаться полного ответа и пережить
фрагментированную выдачу UART.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from typing import Callable, Optional

try:
    import serial
except ImportError:  # GUI покажет нормальную ошибку при попытке подключения
    serial = None

try:
    import smt_aliases as _aliases   # обезличенные имена (CMD_###) -> реальные
except Exception:
    _aliases = None

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

# GUI может осознанно отправить эти команды только в экспертном режиме. CLI-клиент
# по умолчанию по-прежнему блокирует их, чтобы случайная команда из терминала не
# ушла в физический прибор.
PROTECTED_WRITE = {
    # обработка среды
    "Volume", "VOLUME_GLOB", "VOLUME_INST", "VOLUME_COMMIS", "VOLUME_DISC",
    "ADD_DISCREDITED_VOLUME", "ADD_DISC_ALARM", "ADD_DISC_CRASH",
    "ENABLE_DISCREDITED_VOLUME",
    "KFACTOR", "GAS_RANGE", "PABS",
    # актуатор
    "VALVE", "VALVE_OPEN", "VALVE_OPEN_FORCE", "VALVE_TRY_CLOSE",
    "VALVE_AUTO_CONTROL", "VALVE_CLOSE_REV_P", "EN_MDM_CHNG_VLV",
    "VALVE_DELAY_TRY_OPEN", "CNT_VALVE_MIN",
    # сервис / защита от вмешательства / сброс
    "CLEAR_SABOTAG", "BAN_OPEN_CASE", "DATE_VERIFIC", "DATE_VERIFIC_NEXT",
    "COMMISSIONING", "CLEAR_ARHIVE", "DEFAULT_SETTINGS", "RSTSMT",
    "WARNING_CLEAR", "ALARM_CLEAR", "CRASH_CLEAR", "CLEAR_SN_SGM",
    # часы (влияют на метки/обработка)
    "DATETIME", "TIME_ZONE", "RTC_CALIB", "RTC_OUTPUT_CALIB",
    # связь (перенаправление телеметрии)
    "SERVER_URL", "SERVER_URL2", "APN_ADDRESS", "APN_LOGIN", "APN_PASSWORD",
    # доступ / секреты
    "PASSWORD_PROVIDER", "PASSWORD_OMEGA", "PASSWORD_OMEGA2", "PASSWORD_FABRIC",
    "MAGIC", "ENABLE_OMEGA", "EVENT_OMEGA",
}

# Императивные ДЕЙСТВИЯ: «голое» имя (без `=`) уже выполняет операцию на приборе.
# Их нельзя трактовать как чтение — только как действие (заблокировано по умолчанию,
# доступно в экспертном режиме, без автоповтора). Список задан явно, чтобы не зависеть
# от типа в каталоге (там встречаются опечатки/пропуски).
IMPERATIVE_ACTIONS = {
    "VALVE_OPEN", "VALVE_OPEN_FORCE", "VALVE_TRY_CLOSE", "VALVE_CLOSE_REV_P",
    "CLEAR_SABOTAG", "CLEAR_ARHIVE", "CLEAR_SN_SGM",
    "WARNING_CLEAR", "ALARM_CLEAR", "CRASH_CLEAR",
    "DEFAULT_SETTINGS", "RSTSMT", "COMMISSIONING",
}

# Имена-креденшлы: их ЗНАЧЕНИЕ не пишем в журнал сессии (маскируем).
SECRET_NAMES = {
    "PASSWORD_PROVIDER", "PASSWORD_OMEGA", "PASSWORD_OMEGA2", "PASSWORD_FABRIC",
    "MAGIC", "ENABLE_OMEGA", "EVENT_OMEGA", "APN_PASSWORD",
}


def command_name(cmd: str) -> str:
    """Имя команды из строки `NAME`, `NAME=value`, `{NAME}`, `/?NAME!`."""
    base = str(cmd).split("=", 1)[0].strip().strip("{}!/? ").strip()
    return base


def is_protected(cmd: str) -> bool:
    """Критична ли команда на запись/действие — по имени, независимо от `=`."""
    return command_name(cmd) in PROTECTED_WRITE

FRAMINGS: dict[str, Callable[[str], bytes]] = {
    "cr":    lambda c: (c + "\r").encode("utf-8"),
    "crlf":  lambda c: (c + "\r\n").encode("utf-8"),
    "brace": lambda c: ("{" + c + "}").encode("utf-8"),
    "iec":   lambda c: ("/?" + c + "!\r\n").encode("utf-8"),
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
                data = after
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


def value_of(resp: bytes, name: Optional[str] = None):
    """Извлечь значение из `NAME=value;`, устойчиво к нескольким строкам."""
    text = decode_response(resp).strip("\x00 \t\r\n")
    if not text:
        return None
    if name:
        matches = re.findall(re.escape(name) + r"\s*=\s*([^;\r\n}]*)", text, flags=re.I)
        if matches:
            return matches[-1].strip()
    # Последняя пара name=value обычно является полезным ответом после служебных строк.
    matches = re.findall(r"[A-Za-zА-Яа-я0-9_]+\s*=\s*([^;\r\n}]*)", text)
    if matches:
        return matches[-1].strip()
    return text.strip(";\r\n{} ") or None


class OpticTransport:
    """Физический UART-транспорт для оптоголовки.

    Автоопределение кадрирования всегда выполняется командой чтения `DevInfo`.
    Записываемая команда никогда не используется как проба и не дублируется.
    """

    def __init__(
        self,
        port: str,
        baud: int = BAUD,
        *,
        response_timeout: Optional[float] = None,
        idle_gap: Optional[float] = None,
        read_retries: Optional[int] = None,
        max_response: int = 65536,
        ser=None,
    ):
        # `ser` — внутренняя инъекция уже открытого порта (используется в тестах
        # без железа). В обычной работе GUI всегда открывает реальный serial.
        if ser is None and serial is None:
            raise TransportError("Нужен pyserial: pip install pyserial")
        if not port:
            raise TransportError("Не указан serial-порт")

        self.port = port
        self.baud = int(baud)
        if response_timeout is None:
            response_timeout = float(os.environ.get("SMT_RESPONSE_TIMEOUT", "2.5"))
        if idle_gap is None:
            idle_gap = float(os.environ.get("SMT_IDLE_GAP", "0.25"))
        if read_retries is None:
            read_retries = int(os.environ.get("SMT_READ_RETRIES", "1"))
        self.response_timeout = max(0.2, float(response_timeout))
        self.idle_gap = max(0.03, float(idle_gap))
        self.read_retries = max(0, int(read_retries))
        self.max_response = max(256, int(max_response))
        self.frame: Optional[Callable[[str], bytes]] = None
        self.frame_name: Optional[str] = None
        self.last_tx = b""
        self.last_raw_rx = b""
        self.last_rx = b""
        self.last_echo_removed = False
        self.last_latency_ms = 0
        self.last_attempts = 0
        self.last_probe_response = b""
        self._lock = threading.RLock()

        if ser is not None:
            self.ser = ser
            return

        kwargs = dict(
            port=port,
            baudrate=self.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.05,
            write_timeout=1.5,
            inter_byte_timeout=None,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        try:
            if os.name != "nt":
                kwargs["exclusive"] = True
            self.ser = serial.Serial(**kwargs)
        except TypeError:
            kwargs.pop("exclusive", None)
            self.ser = serial.Serial(**kwargs)
        except Exception as exc:
            raise TransportError(f"Не удалось открыть {port}: {exc}") from exc

        # Не дёргать reset/boot-линии USB-UART при открытии.
        for attr in ("dtr", "rts"):
            try:
                setattr(self.ser, attr, False)
            except Exception:
                pass
        time.sleep(0.12)
        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except Exception:
            pass

    @property
    def is_open(self) -> bool:
        return bool(getattr(self.ser, "is_open", False))

    def set_framing(self, name: str) -> None:
        if name not in FRAMINGS:
            raise ValueError(f"Неизвестное кадрирование: {name}")
        self.frame_name = name
        self.frame = FRAMINGS[name]

    def close(self) -> None:
        with self._lock:
            try:
                if self.ser and self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass

    def _ensure_open(self) -> None:
        if not self.is_open:
            raise PortClosedError(f"Порт {self.port} закрыт или устройство отключено")

    def _read_burst(self) -> bytes:
        deadline = time.monotonic() + self.response_timeout
        last_byte_at: Optional[float] = None
        buf = bytearray()
        while time.monotonic() < deadline and len(buf) < self.max_response:
            self._ensure_open()
            try:
                waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
                chunk = self.ser.read(min(waiting, 4096)) if waiting else self.ser.read(1)
            except Exception as exc:
                raise PortClosedError(f"Ошибка чтения {self.port}: {exc}") from exc
            if chunk:
                buf.extend(chunk)
                last_byte_at = time.monotonic()
                continue
            if last_byte_at is not None and time.monotonic() - last_byte_at >= self.idle_gap:
                break
        return bytes(buf)

    def _exchange(self, command: str, frame: Callable[[str], bytes]) -> bytes:
        self._ensure_open()
        payload = frame(command)
        self.last_tx = payload
        started = time.monotonic()
        try:
            self.ser.reset_input_buffer()
            self.ser.write(payload)
            self.ser.flush()
        except Exception as exc:
            raise PortClosedError(f"Ошибка записи в {self.port}: {exc}") from exc
        raw = self._read_burst()
        clean, echoed = strip_optical_echo(command, payload, raw)
        self.last_raw_rx = raw
        self.last_rx = clean
        self.last_echo_removed = echoed
        self.last_latency_ms = int((time.monotonic() - started) * 1000)
        return clean

    def detect_framing(self, probe_cmd: str = "DevInfo") -> tuple[str, bytes]:
        """Определить кадрирование только безопасной командой чтения."""
        with self._lock:
            for name, frame in FRAMINGS.items():
                # Две попытки полезны при спящем оптопорте; обе являются чтением.
                for _ in range(2):
                    clean = self._exchange(probe_cmd, frame)
                    if _contains_named_response(probe_cmd, clean):
                        self.frame_name, self.frame = name, frame
                        self.last_probe_response = clean
                        return name, clean
                    time.sleep(0.08)
            raise TransportError(
                "Прибор не ответил на DevInfo ни с одним кадрированием "
                "(cr/crlf/brace/iec). Проверь питание, TX/RX, положение головки и baud."
            )

    def probe(self, probe_cmd: str = "DevInfo") -> bytes:
        with self._lock:
            if self.frame is None:
                return self.detect_framing(probe_cmd)[1]
            clean = self._exchange(probe_cmd, self.frame)
            if not _contains_named_response(probe_cmd, clean):
                raise TransportError(
                    f"Порт открыт, но корректный ответ на {probe_cmd} не получен "
                    f"с кадрированием {self.frame_name or 'ручным'}"
                )
            self.last_probe_response = clean
            return clean

    def send(self, cmd: str, *, retry_safe: bool = False) -> bytes:
        command = str(cmd).strip("\r\n")
        if not command:
            return b""
        with self._lock:
            if self.frame is None:
                _, probe = self.detect_framing("DevInfo")
                if command.casefold() == "devinfo".casefold():
                    return probe
            attempts = 1 + (self.read_retries if retry_safe else 0)
            last = b""
            for attempt in range(1, attempts + 1):
                self.last_attempts = attempt
                last = self._exchange(command, self.frame)
                if last:
                    return last
                if attempt < attempts:
                    time.sleep(0.12)
            return last


class SmsTransport:
    def send(self, cmd):
        raise NotImplementedError("SMS-транспорт не входит в физическую версию оптопорта")


class TcpServerTransport:
    def send(self, cmd):
        raise NotImplementedError("GPRS-приём выполняет smt_server.py/вкладка Телеметрия")


class SmtClient:
    def __init__(self, transport: OpticTransport):
        self.t = transport

    def send(self, cmd: str, *, retry_safe: bool = False, expert: bool = False,
             mutating: Optional[bool] = None):
        """Единая точка отправки.

        mutating — это запись/действие (True) или чтение-get (False). Если не задан,
        выводится по наличию `=` (чтение bare-имени считается get). Критичные
        ИЗМЕНЯЮЩИЕ операции (`VALVE_OPEN`, `CLEAR_SABOTAG`, `SERVER_URL=…`)
        блокируются, пока не передан expert=True — живой второй рубеж поверх гейта GUI.
        Чтение защищённого параметра (get, например `VALVE`) разрешено всегда.
        Повтор допустим только для чтения; запись/действие не повторяются никогда.

        Если пришло обезличенное имя (`CMD_###`), оно резолвится в реальное ДО
        проверок и отправки — гейт и провод всегда работают с настоящим именем."""
        if _aliases is not None:
            cmd = _aliases.to_wire(cmd)
        name = command_name(cmd)
        mut = mutating if mutating is not None else ("=" in cmd)
        if mut and name in PROTECTED_WRITE and not expert:
            raise PermissionError(
                f"[отказ] '{name}' — критичная команда. Доступна только в экспертном "
                "режиме (осознанная запись/действие в физический прибор)."
            )
        safe = retry_safe and not mut
        return self.t.send(cmd, retry_safe=safe)

    def get(self, name: str):
        return value_of(self.t.send(name, retry_safe=True), name=name)

    def get_all(self, delay: float = 0.05):
        out = {}
        for name in PASSPORT:
            try:
                out[name] = self.get(name)
            except Exception as exc:
                out[name] = f"<err:{exc}>"
            if delay:
                time.sleep(delay)
        return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    port = sys.argv[1]
    cli = SmtClient(OpticTransport(port))
    try:
        cli.t.probe()
        if "--passport" in sys.argv:
            print(f"# паспорт физического прибора · порт {port}\n")
            for key, val in cli.get_all().items():
                print(f"  {key:<20} = {val!r}")
            return
        if "--get" in sys.argv:
            name = sys.argv[sys.argv.index("--get") + 1]
            print(f"{name} = {cli.get(name)!r}")
            return
        if "--send" in sys.argv:
            cmd = sys.argv[sys.argv.index("--send") + 1]
            try:
                raw = cli.send(cmd)
                print(f">> {cmd}\n<< {raw!r}")
            except PermissionError as exc:
                print(exc)
            return
        print(__doc__)
    finally:
        cli.t.close()


if __name__ == "__main__":
    main()
