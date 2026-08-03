"""Физические транспорты: Serial/оптопорт, GSM/SMS и TCP."""
from __future__ import annotations

__all__ = ["OpticTransport", "SmsTransport", "TcpServerTransport"]

import os
import socket
import threading
import time
from collections.abc import Callable

try:
    import serial
except ImportError:
    serial = None

from smt_logging import get_logger

from .commands import BAUD

logger = get_logger("transports")

import contextlib

from .protocol import (
    FRAMINGS,
    PortClosedError,
    TransportError,
    _contains_named_response,
    decode_response,
    strip_optical_echo,
)


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
        response_timeout: float | None = None,
        idle_gap: float | None = None,
        read_retries: int | None = None,
        max_response: int = 65536,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        xonxoff: bool = False,
        rtscts: bool = False,
        dsrdtr: bool = False,
        dtr: bool = False,
        rts: bool = False,
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
        self.bytesize = int(bytesize)
        self.parity = str(parity).upper()
        self.stopbits = float(stopbits)
        self.xonxoff = bool(xonxoff)
        self.rtscts = bool(rtscts)
        self.dsrdtr = bool(dsrdtr)
        self.dtr_level = bool(dtr)
        self.rts_level = bool(rts)
        self.frame: Callable[[str], bytes] | None = None
        self.frame_name: str | None = None
        self.last_tx = b""
        self.last_raw_rx = b""
        self.last_rx = b""
        self.last_echo_removed = False
        self.last_latency_ms = 0
        self.last_attempts = 0
        self.last_probe_response = b""
        self.last_read_truncated = False
        self._lock = threading.RLock()

        if ser is not None:
            self.ser = ser
            return

        bytesize_map = {5: serial.FIVEBITS, 6: serial.SIXBITS,
                        7: serial.SEVENBITS, 8: serial.EIGHTBITS}
        parity_map = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN,
                      "O": serial.PARITY_ODD, "M": serial.PARITY_MARK,
                      "S": serial.PARITY_SPACE}
        stopbits_map = {1.0: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE,
                        2.0: serial.STOPBITS_TWO}
        if self.bytesize not in bytesize_map:
            raise TransportError("Размер слова должен быть 5, 6, 7 или 8 бит")
        if self.parity not in parity_map:
            raise TransportError("Чётность должна быть N/E/O/M/S")
        if self.stopbits not in stopbits_map:
            raise TransportError("Стоп-биты должны быть 1, 1.5 или 2")
        kwargs = dict(
            port=port,
            baudrate=self.baud,
            bytesize=bytesize_map[self.bytesize],
            parity=parity_map[self.parity],
            stopbits=stopbits_map[self.stopbits],
            timeout=0.05,
            write_timeout=1.5,
            inter_byte_timeout=None,
            xonxoff=self.xonxoff,
            rtscts=self.rtscts,
            dsrdtr=self.dsrdtr,
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

        # Уровни служебных линий задаются явно. По умолчанию оба выключены,
        # чтобы USB-UART не дёргал reset/boot входы прибора при открытии.
        for attr, level in (("dtr", self.dtr_level), ("rts", self.rts_level)):
            try:
                setattr(self.ser, attr, level)
            except Exception as exc:
                logger.debug("Не удалось задать служебную линию %s", attr, exc_info=exc)
        time.sleep(0.12)
        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except Exception as exc:
            logger.debug("Не удалось очистить serial-буфер при открытии", exc_info=exc)

    def __enter__(self) -> OpticTransport:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

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
            except Exception as exc:
                logger.debug("Ошибка при закрытии serial-порта", exc_info=exc)

    def _ensure_open(self) -> None:
        if not self.is_open:
            raise PortClosedError(f"Порт {self.port} закрыт или устройство отключено")

    def _read_burst(self) -> bytes:
        """Собрать ответ до межбайтовой паузы, не обрезая активный поток.

        `response_timeout` остаётся таймаутом ожидания первого байта. После начала
        ответа чтение продолжается, пока данные приходят, с аварийным потолком
        `SMT_RESPONSE_HARD_TIMEOUT` (по умолчанию 30 с) и `max_response`.
        """
        started = time.monotonic()
        first_byte_deadline = started + self.response_timeout
        hard_timeout = max(self.response_timeout, float(os.environ.get("SMT_RESPONSE_HARD_TIMEOUT", "30")))
        hard_deadline = started + hard_timeout
        last_byte_at: float | None = None
        buf = bytearray()
        self.last_read_truncated = False
        while len(buf) < self.max_response:
            now = time.monotonic()
            if last_byte_at is None:
                if now >= first_byte_deadline:
                    break
            elif now >= hard_deadline:
                self.last_read_truncated = True
                break
            self._ensure_open()
            try:
                waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
                to_read = min(waiting, 4096, self.max_response - len(buf)) if waiting else 1
                chunk = self.ser.read(to_read)
            except Exception as exc:
                raise PortClosedError(f"Ошибка чтения {self.port}: {exc}") from exc
            if chunk:
                buf.extend(chunk)
                last_byte_at = time.monotonic()
                continue
            if last_byte_at is not None and time.monotonic() - last_byte_at >= self.idle_gap:
                break
        if len(buf) >= self.max_response:
            self.last_read_truncated = True
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

    def detect_framing(self, probe_cmd: str = "DevInfo", on_attempt=None) -> tuple[str, bytes]:
        """Определить кадрирование только безопасной командой чтения.

        `on_attempt(name, try_no, ok, raw)` — необязательный колбэк, вызывается
        после КАЖДОЙ попытки (успешной или нет), чтобы вызывающий код мог
        показать живой прогресс перебора вместо тишины на 10-20 секунд."""
        with self._lock:
            for name, frame in FRAMINGS.items():
                # Две попытки полезны при спящем оптопорте; обе являются чтением.
                for try_no in range(1, 3):
                    clean = self._exchange(probe_cmd, frame)
                    ok = _contains_named_response(probe_cmd, clean)
                    if on_attempt is not None:
                        with contextlib.suppress(Exception):
                            on_attempt(name, try_no, ok, clean)
                    if ok:
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

    def raw_exchange(self, payload: bytes, *, response_timeout: float | None = None) -> bytes:
        """Передать точные байты без кадрирования и вернуть сырой ответ.

        Метод предназначен для диагностики неизвестных/двоичных расширений
        протокола. Оптическое эхо здесь не удаляется, потому что пользователь
        запросил именно сырой обмен.
        """
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("payload должен быть bytes")
        data = bytes(payload)
        with self._lock:
            self._ensure_open()
            old_timeout = self.response_timeout
            if response_timeout is not None:
                self.response_timeout = max(0.05, float(response_timeout))
            started = time.monotonic()
            try:
                try:
                    self.ser.reset_input_buffer()
                    self.ser.write(data)
                    self.ser.flush()
                except Exception as exc:
                    raise PortClosedError(f"Ошибка сырой записи в {self.port}: {exc}") from exc
                raw = self._read_burst()
            finally:
                self.response_timeout = old_timeout
            self.last_tx = data
            self.last_raw_rx = self.last_rx = raw
            self.last_echo_removed = False
            self.last_latency_ms = int((time.monotonic() - started) * 1000)
            self.last_attempts = 1
            return raw

    def line_description(self) -> str:
        flow = []
        if self.xonxoff: flow.append("XON/XOFF")
        if self.rtscts: flow.append("RTS/CTS")
        if self.dsrdtr: flow.append("DSR/DTR")
        return (f"{self.port} · {self.baud} {self.bytesize}{self.parity}{self.stopbits:g}"
                + (" · " + "+".join(flow) if flow else ""))


class SmsTransport:
    """Отправка команд через обычный GSM-модем с AT-интерфейсом.

    Транспорт посылает SMS и возвращает ответ самого модема (`+CMGS`/`OK`). Ответ
    удалённого устройства можно получить методом :meth:`receive_unread`. Повторы
    отправки намеренно отсутствуют. При использовании через SmtClient экспертный
    гейт работает так же, как для оптопорта.
    """
    def __init__(self, modem_port: str, phone: str, *, baud: int = 115200,
                 response_timeout: float = 20.0, prefix: str = "", ser=None):
        if ser is None and serial is None:
            raise TransportError("Нужен pyserial: pip install pyserial")
        if not phone:
            raise TransportError("Не указан номер получателя SMS")
        self.port, self.phone, self.baud = modem_port, phone, int(baud)
        self.response_timeout, self.prefix = float(response_timeout), prefix
        self._lock = threading.RLock()
        self.ser = ser or serial.Serial(port=modem_port, baudrate=self.baud,
                                        timeout=0.1, write_timeout=3)
        self.frame_name = "sms-text"
        self.last_tx = self.last_raw_rx = self.last_rx = b""
        self.last_echo_removed = False; self.last_latency_ms = 0; self.last_attempts = 1
        self._at("AT", timeout=3)
        self._at("ATE0", timeout=3)
        rep = self._at("AT+CMGF=1", timeout=3)
        if b"ERROR" in rep.upper():
            raise TransportError("GSM-модем не включил текстовый режим SMS")

    def __enter__(self) -> SmsTransport:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        return bool(getattr(self.ser, "is_open", False))

    def close(self) -> None:
        with self._lock:
            try:
                if self.ser and self.ser.is_open:
                    self.ser.close()
            except Exception as exc:
                logger.debug("Ошибка при закрытии GSM-модема", exc_info=exc)

    def _read_until(self, *, timeout=None, prompt=False):
        deadline = time.monotonic() + (self.response_timeout if timeout is None else timeout)
        buf = bytearray(); last = None
        while time.monotonic() < deadline:
            waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
            chunk = self.ser.read(min(waiting, 4096)) if waiting else self.ser.read(1)
            if chunk:
                buf.extend(chunk); last = time.monotonic()
                up = bytes(buf).upper()
                if prompt and b">" in buf:
                    break
                if b"\r\nOK\r\n" in up or b"\r\nERROR\r\n" in up or b"+CMS ERROR:" in up:
                    break
            elif last is not None and time.monotonic() - last > 0.35:
                break
        return bytes(buf)

    def _at(self, command, *, timeout=None, prompt=False):
        with contextlib.suppress(Exception):
            self.ser.reset_input_buffer()
        payload = (command + "\r").encode("ascii", "replace")
        self.ser.write(payload); self.ser.flush()
        return self._read_until(timeout=timeout, prompt=prompt)

    def send(self, cmd: str, *, retry_safe: bool = False) -> bytes:
        del retry_safe
        text = self.prefix + str(cmd).strip("\r\n")
        with self._lock:
            started = time.monotonic()
            prompt = self._at(f'AT+CMGS="{self.phone}"', timeout=8, prompt=True)
            if b">" not in prompt:
                raise TransportError("GSM-модем не выдал приглашение '>' для SMS")
            payload = text.encode("utf-8") + b"\x1a"
            self.last_tx = payload
            self.ser.write(payload); self.ser.flush()
            raw = self._read_until(timeout=self.response_timeout)
            self.last_raw_rx = self.last_rx = raw
            self.last_latency_ms = int((time.monotonic() - started) * 1000)
            if b"ERROR" in raw.upper() or b"+CMS ERROR:" in raw.upper():
                raise TransportError("Ошибка отправки SMS: " + decode_response(raw).strip())
            return raw

    def probe(self, probe_cmd: str = "DevInfo") -> bytes:
        return self.send(probe_cmd)

    def send_at(self, command: str, *, timeout: float = 5.0) -> bytes:
        """Выполнить диагностическую AT-команду модема."""
        with self._lock:
            started = time.monotonic()
            raw = self._at(str(command).strip(), timeout=timeout)
            self.last_tx = (str(command).strip() + "\r").encode("ascii", "replace")
            self.last_raw_rx = self.last_rx = raw
            self.last_latency_ms = int((time.monotonic() - started) * 1000)
            self.last_attempts = 1
            return raw

    def health_check(self) -> bytes:
        return self.send_at("AT", timeout=3)

    def receive_unread(self, *, delete: bool = False):
        """Получить непрочитанные SMS: список dict(index, header, text)."""
        with self._lock:
            raw = self._at('AT+CMGL="REC UNREAD"', timeout=10)
            text = decode_response(raw)
            lines = [x.strip() for x in text.splitlines() if x.strip()]
            out = []
            for i, line in enumerate(lines):
                if not line.startswith("+CMGL:"):
                    continue
                try:
                    index = int(line.split(":", 1)[1].split(",", 1)[0].strip())
                except Exception:
                    index = -1
                body = lines[i + 1] if i + 1 < len(lines) and not lines[i + 1].startswith("+CMGL:") else ""
                out.append({"index": index, "header": line, "text": body})
                if delete and index >= 0:
                    self._at(f"AT+CMGD={index}", timeout=5)
            return out


class TcpServerTransport:
    """Командный TCP-транспорт request/response.

    Для входящей GPRS-телеметрии по-прежнему используется smt_server.py. Этот
    класс закрывает обратное направление: отправляет одну команду удалённому
    TCP-шлюзу и собирает ответ до закрытия соединения или межбайтовой паузы.
    """
    def __init__(self, host: str, port: int, *, timeout: float = 3.0,
                 idle_gap: float = 0.25, terminator: bytes = b"\r\n",
                 max_response: int = 1024 * 1024):
        self.host, self.port = host, int(port)
        self.timeout, self.idle_gap = float(timeout), float(idle_gap)
        self.terminator, self.max_response = terminator, int(max_response)
        self.frame_name = "tcp"
        self.last_tx = self.last_raw_rx = self.last_rx = b""
        self.last_echo_removed = False; self.last_latency_ms = 0; self.last_attempts = 1
        self._lock = threading.RLock(); self._open = True

    def __enter__(self) -> TcpServerTransport:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        return self._open

    def close(self) -> None:
        self._open = False

    def send(self, cmd: str, *, retry_safe: bool = False) -> bytes:
        del retry_safe
        if not self._open:
            raise PortClosedError("TCP-транспорт закрыт")
        payload = str(cmd).strip("\r\n").encode("utf-8") + self.terminator
        with self._lock:
            started = time.monotonic(); buf = bytearray(); last = None
            try:
                with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                    sock.settimeout(min(0.2, self.timeout)); sock.sendall(payload)
                    with contextlib.suppress(OSError):
                        sock.shutdown(socket.SHUT_WR)
                    deadline = time.monotonic() + self.timeout
                    while time.monotonic() < deadline and len(buf) < self.max_response:
                        try:
                            chunk = sock.recv(min(4096, self.max_response - len(buf)))
                        except TimeoutError:
                            if last is not None and time.monotonic() - last >= self.idle_gap:
                                break
                            continue
                        if not chunk:
                            break
                        buf.extend(chunk); last = time.monotonic()
            except OSError as exc:
                raise TransportError(f"TCP {self.host}:{self.port}: {exc}") from exc
            self.last_tx = payload
            self.last_raw_rx = self.last_rx = bytes(buf)
            self.last_latency_ms = int((time.monotonic() - started) * 1000)
            return self.last_rx

    def probe(self, probe_cmd: str = "DevInfo") -> bytes:
        return self.send(probe_cmd, retry_safe=True)

    def raw_exchange(self, payload: bytes, *, response_timeout: float | None = None) -> bytes:
        if not self._open:
            raise PortClosedError("TCP-транспорт закрыт")
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("payload должен быть bytes")
        data = bytes(payload)
        timeout = self.timeout if response_timeout is None else float(response_timeout)
        with self._lock:
            started = time.monotonic(); buf = bytearray(); last = None
            try:
                with socket.create_connection((self.host, self.port), timeout=timeout) as sock:
                    sock.settimeout(min(0.2, timeout)); sock.sendall(data)
                    with contextlib.suppress(OSError):
                        sock.shutdown(socket.SHUT_WR)
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline and len(buf) < self.max_response:
                        try:
                            chunk = sock.recv(min(4096, self.max_response - len(buf)))
                        except TimeoutError:
                            if last is not None and time.monotonic() - last >= self.idle_gap:
                                break
                            continue
                        if not chunk:
                            break
                        buf.extend(chunk); last = time.monotonic()
            except OSError as exc:
                raise TransportError(f"TCP {self.host}:{self.port}: {exc}") from exc
            self.last_tx = data
            self.last_raw_rx = self.last_rx = bytes(buf)
            self.last_latency_ms = int((time.monotonic() - started) * 1000)
            self.last_attempts = 1
            return self.last_rx

    def line_description(self) -> str:
        return f"TCP {self.host}:{self.port}"
