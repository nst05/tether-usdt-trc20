#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smt_gui — графический клиент физического прибора через оптопорт.

Интерфейс расширен для дипломной версии и работает только с реальными
каналами связи: USB-оптопорт/serial, TCP-шлюз и GSM-модем/SMS. Оптический
транспорт автоматически определяет кадрирование безопасной командой чтения,
снимает оптическое эхо, собирает фрагментированный ответ UART и фиксирует
фактические TX/RX-байты.

Запуск:
    python3 smt_gui.py
Требования: Python 3 с tkinter + pyserial (pip install pyserial).
"""
import os, sys, json, time, threading, queue, datetime, socket, hashlib, csv
from decimal import Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".smt_optic_gui.json")


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(data):
    try:
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)
    except Exception:
        pass


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
    except Exception:
        pass
    return "COM3" if os.name == "nt" else "/dev/ttyUSB0"

try:
    import smt_session as ss         # SessionRecorder — журнал работы с прибором
except Exception:
    ss = None
try:
    import smt_client as sc          # OpticTransport, SmtClient, PROTECTED_WRITE, FRAMINGS
except Exception as e:               # pragma: no cover
    sys.exit(f"Не найден/не импортируется smt_client.py рядом с GUI: {e}")

try:
    import smt_server as srv          # parse_frame, crc16_scan, auth_check (разбор телеметрии)
except Exception:                     # телеметрия-разбор будет отключён, если модуля нет
    srv = None

try:
    import smt_state as state_mod     # разбор чекпоинта показаний (история)
    import smt_eventlog as evlog_mod  # разбор журнала событий/аудита
except Exception:
    state_mod = evlog_mod = None

try:
    import smt_tools as tools_mod     # снимки, сравнение, пакетные сценарии
except Exception:
    tools_mod = None

try:
    import smt_telemetry_store as tele_store_mod  # накопительная база телеметрии
except Exception:
    tele_store_mod = None

# Креды уровней доступа для Auth-scan (только ЧТЕНИЕ). Пароль может быть НЕ дефолтным —
# читаем действующее значение (находка F7), не подставляя 123456.
SECRET_READS = [
    ("PASSWORD_PROVIDER",    "пароль провайдера (=%s, открытым текстом) — высший"),
    ("PASWORD_PROVID_VALUE", "числовое представление/проверка пароля"),
    ("PASSWORD_OMEGA",       "пароль omega (может быть маскирован ******)"),
    ("PASSWORD_OMEGA2",      "сервисный код omega (=%04x)"),
    ("MAGIC",                "сервисная разблокировка"),
    ("ENABLE_OMEGA",         "статус omega-доступа"),
]
MASK_MARKERS = ("****", "xxxx", "----")

# Параметры телеметрии, снимаемые по оптопорту (для сборки пакета).
TELE_PARAMS = ["Volume", "VOLUME_GLOB", "VOLUME_INST", "VOLUME_COMMIS", "VOLUME_DISC",
               "ArcNumRecords", "COUNT_SESSION", "ERROR_SESSION", "SERVER_URL",
               "STATUS_SYSTEM", "STATUS_ALARM", "DEVICE_SN"]

# Команды, меняющие учётные показания. Их запись выполняется отдельной штатной
# Provider-процедурой: подтверждённая авторизация -> SET -> read-back.
# CLEAR_ARHIVE является отдельной операцией и никогда не запускается автоматически.
READING_COMMANDS = {"Volume", "VOLUME_GLOB", "VOLUME_COMMIS", "VOLUME_DISC"}
PROVIDER_AUTH_TTL = 15 * 60
TELEMETRY_DB_PATH = os.path.join(HERE, "sessions", "telemetry.sqlite3")


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


def build_telemetry_packet(readings):
    """Собрать РЕАЛЬНЫЙ телеметрический пакет из фактически снятых показаний:
    одна запись V с текущей меткой времени, честные CRC16 (XMODEM/KERMIT/MODBUS)
    и auth=MD5(всё до 'auth='). Формат — как у прибора (sub_08019192)."""
    def num(name, d=0.0):
        try:
            return float(str(readings.get(name, d)).replace(",", "."))
        except Exception:
            return d
    acc = int(round(num("Volume") * 10000))
    val = num("VOLUME_INST")
    now = datetime.datetime.now()
    rec = f"1;{now.strftime('%d.%m.%Y,%H:%M:%S')};{acc};{val:0.2f};;0;"
    body = "{V;1;1;" + rec + "}"
    inner = body[1:-1].encode("latin1")
    sn = str(readings.get("DEVICE_SN") or "")
    id64 = "".join(f"{ord(ch):02X}" for ch in sn[:8]).ljust(16, "0")[:16] or "0123456789ABCDEF"
    if srv is None:
        return body
    c1 = srv.crc16(inner, *srv.CRC16_VARIANTS["XMODEM"])
    c2 = srv.crc16(inner, *srv.CRC16_VARIANTS["KERMIT"])
    c3 = srv.crc16(inner, *srv.CRC16_VARIANTS["MODBUS"])
    prefix = f"TELE;{c1:04X};{c2:04X};{c3:04X};{id64};{body}"
    return prefix + "auth=" + hashlib.md5(prefix.encode("latin1")).hexdigest()


class TeleServer(threading.Thread):
    """Живой приёмник телеметрии (TCP): принимает всплеск, парсит, шлёт ACK."""
    def __init__(self, port, out_q, idle=0.8, max_frame=2 * 1024 * 1024):
        super().__init__(daemon=True)
        self.port, self.out_q, self.idle = port, out_q, idle
        self.max_frame = max_frame
        self._stop_event = threading.Event(); self.srv = None

    def run(self):
        try:
            self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.srv.bind(("0.0.0.0", self.port)); self.srv.listen(5)
            self.srv.settimeout(0.5)
            self.out_q.put(("tele_log", ("ok", f"[приём] слушаю 0.0.0.0:{self.port} — жду сессию прибора")))
        except Exception as e:
            self.out_q.put(("tele_log", ("err", f"[приём] не удалось открыть порт: {e}")))
            self.out_q.put(("tele_state", "off"))
            return
        while not self._stop_event.is_set():
            try:
                conn, addr = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True).start()
        try:
            self.srv.close()
        except Exception:
            pass
        self.out_q.put(("tele_log", ("ok", "[приём] остановлен")))
        self.out_q.put(("tele_state", "off"))

    def _handle_connection(self, conn, addr):
        conn.settimeout(self.idle); buf = b""
        with conn:
            while True:
                try:
                    d = conn.recv(4096)
                except socket.timeout:
                    break
                if not d:
                    break
                buf += d
                if len(buf) > self.max_frame:
                    self.out_q.put(("tele_log", ("err", f"[приём] {addr[0]}: пакет больше "
                                                         f"{self.max_frame} байт — закрыт")))
                    return
            if not buf:
                return
            rep = srv.parse_frame(buf) if srv else {"records": []}
            if srv and rep.get("auth"):
                rep["auth_check"] = srv.auth_check(rep.get("text", ""), rep["auth"])
            n = len(rep.get("records", []))
            if tele_store_mod is not None:
                try:
                    packet_id, inserted, anomalies = tele_store_mod.ingest(
                        TELEMETRY_DB_PATH, buf, rep, source_ip=addr[0], source_port=addr[1])
                    state = "добавлен" if inserted else "дубликат"
                    self.out_q.put(("tele_log", ("warn" if anomalies else "ok",
                        f"[база] пакет #{packet_id} {state}; записей {n}; аномалий {anomalies}")))
                except Exception as exc:
                    self.out_q.put(("tele_log", ("warn", f"[база] не удалось сохранить: {exc}")))
            try:
                folder = os.path.join(HERE, "sessions")
                os.makedirs(folder, exist_ok=True)
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                safe_ip = addr[0].replace(":", "_")
                base = os.path.join(folder, f"session_{stamp}_{safe_ip}_{addr[1]}")
                with open(base + ".log", "wb") as stream:
                    stream.write(buf)
                with open(base + ".json", "w", encoding="utf-8") as stream:
                    json.dump(rep, stream, ensure_ascii=False, indent=2)
                self.out_q.put(("tele_log", ("ok", f"[приём] сохранено: {base}.log/.json")))
            except Exception as exc:
                self.out_q.put(("tele_log", ("warn", f"[приём] не удалось сохранить пакет: {exc}")))
            self.out_q.put(("tele_rx", (buf.decode("latin1", "replace"), rep, addr[0], n)))
            try:
                conn.sendall(f"DATA ACCEPT:{n}\r\n".encode())
            except OSError:
                pass

    def stop(self):
        self._stop_event.set()
        try:
            self.srv.close()
        except Exception:
            pass


def tele_send(host, port, data, out_q):
    """Реальная отправка пакета по TCP на host:port, показ ACK (в отдельном потоке)."""
    def worker():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(3)
            s.connect((host, port)); s.sendall(data)
            s.shutdown(socket.SHUT_WR)
            try:
                ack = s.recv(256)
            except socket.timeout:
                ack = b""
            s.close()
            out_q.put(("tele_log", ("ok", f"[отправка] → {host}:{port} · {len(data)} байт · "
                                          f"ACK {ack.decode('latin1','replace')!r}")))
        except Exception as e:
            out_q.put(("tele_log", ("err", f"[отправка] ошибка: {e}")))
    threading.Thread(target=worker, daemon=True).start()


def load_catalog():
    p = os.path.join(HERE, "smt_commands.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)["commands"]


def pretty(v):
    """Починка косметики: строка UTF-8, ошибочно декодированная как latin1
    (артефакт value_of в smt_client), приводится к читаемому виду."""
    if not isinstance(v, str) or not v:
        return v
    try:
        d = v.encode("latin1").decode("utf-8")
        return d
    except Exception:
        return v


def access_human(flags):
    return {"0101": "чт+зп", "0100": "чтение", "0000": "нет"}.get(flags, flags)


def clean_desc(s, limit=None):
    """Убрать markdown-разметку из описания команды для читаемого показа."""
    if not s:
        return ""
    s = s.replace("**", "").replace("`", "").replace("§", "§").strip()
    if limit and len(s) > limit:
        s = s[:limit - 1].rstrip() + "…"
    return s


def hexdump(prefix, data):
    """Строка hex + ASCII для сырого лога (фиксация терминатора/CRC вживую)."""
    if isinstance(data, str):
        data = data.encode("latin1", "replace")
    hexs = " ".join(f"{b:02X}" for b in data)
    asci = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return f"{prefix} [{len(data):>3}] {hexs}  |{asci}|"


def classify_secret(value):
    if value is None or value == "":
        return "нет доступа"
    low = value.lower()
    if any(m in low for m in MASK_MARKERS):
        return "маскирован"
    return "открытым текстом"


# Уровни доступа (байт 0x20000D62 / флаги 0x2000B1B0), см. отчёт §8bis.
LEVELS = ["Гость", "Провайдер (П)", "Omega (О)", "Заводской (f)"]
# Учётные данные для аутентификации на уровень (пресетные имена команд).
AUTH_CREDS = ["PASSWORD_PROVIDER", "PASSWORD_OMEGA", "ENABLE_OMEGA",
              "PASSWORD_FABRIC", "MAGIC", "PASSWORD_OMEGA2"]

# Пресеты значений для enum/статусных команд (значение до пробела — отправляется).
ENUM_OPTS = {
    "VALVE":      ["1 (Lock_OPEN)", "0 (Lock_CLOSE)"],
    "LOCK_STATE": ["1 (открыт)", "0 (закрыт)"],
    "CLOSED":     ["1 (закрыто)", "0 (открыто)"],
    "MODE_TRANSFER": ["0 (расписание)", "1 (по событию)"],
}


def value_options(cmd):
    """Пресет значений по имени/типу команды (для «во все стороны по назначению»)."""
    o = ENUM_OPTS.get(cmd["name"])
    if o:
        return o
    if "флаг" in (cmd["type"] or ""):
        return ["1", "0"]
    return []


def directions(cmd, is_action):
    """Какие операции валидны по назначению: (read, write, action).

    Сырый протокол остаётся доступен отдельно, но каталог не предлагает запись для
    явно read-only команд — это делает интерфейс убедительнее и снижает ошибки.
    """
    typ = (cmd.get("type") or "").lower()
    if is_action:
        return False, False, True
    read_only = typ.strip() == "чтение"
    return True, not read_only, False


def build_critical(catalog):
    """Критичные на ЗАПИСЬ/ДЕЙСТВИЕ команды: объединение границы аудита из
    smt_client.PROTECTED_WRITE и пометки protected_write в каталоге."""
    crit = set(getattr(sc, "PROTECTED_WRITE", set()))
    crit |= {c["name"] for c in catalog if c.get("protected_write")}
    return crit


def build_actions(catalog):
    """Множество ДЕЙСТВИЙ: тип «действие» в каталоге ∪ явный список императивов из
    smt_client (чтобы критичное действие не уехало как «чтение» из-за опечатки типа)."""
    acts = {c["name"] for c in catalog if "действие" in (c.get("type") or "")}
    acts |= set(getattr(sc, "IMPERATIVE_ACTIONS", set()))
    return acts


def access_at_level(cmd, level):
    """Доступ команды на выбранном уровне (по её флагам П/О). Возвращает
    ('чтение+запись'|'чтение'|'нет', can_read, can_write)."""
    col = cmd["prov"] if level in ("Провайдер (П)", "Заводской (f)") else \
          cmd["user"] if level == "Omega (О)" else None
    if col is None:                       # Гость — публичное чтение по гейту прибора
        return ("гость: публичное чтение (по гейту прибора)", True, False)
    r = col[:2] != "00" or col[1] == "1"
    w = col.endswith("1") and col != "0100"
    txt = {"0101": "чтение+запись", "0100": "чтение", "0000": "нет"}.get(col, col)
    return (txt, col in ("0101", "0100"), col == "0101")


def classify_send(text, actions):
    """Разбор строки: имя, вид (read|write|action)."""
    text = text.strip()
    if "=" in text:
        return text.split("=", 1)[0].strip(), "write"
    name = text.strip("{}!/? ").strip()
    return name, ("action" if name in actions else "read")


# ───────────────────────── фоновый исполнитель ──────────────────────────
class Backend(threading.Thread):
    """Единственный поток, владеющий реальным транспортом прибора."""
    def __init__(self, task_q, out_q, critical=None, actions=None, catalog=None):
        super().__init__(daemon=True)
        self.task_q, self.out_q = task_q, out_q
        self.cli = None
        self.critical = critical or set()
        self.actions = actions or set()
        self.catalog = list(catalog or [])
        self._echo_noted = False
        self.recorder = None
        self.mode = "off"
        self.cancel_event = threading.Event()
        self.auth_state = {"level": "guest", "verified": False, "verified_at": 0.0}

    def cancel_current(self):
        self.cancel_event.set()

    def post(self, kind, payload):
        self.out_q.put((kind, payload))

    def log(self, tag, text):
        self.post("log", (tag, text))

    def run(self):
        while True:
            task = self.task_q.get()
            op = task.get("op")
            try:
                if op == "quit":
                    self._close()
                    return
                if op == "connect":
                    self._connect(task)
                elif op == "disconnect":
                    self._close()
                    self.post("status", ("off", ""))
                    self.log("ok", "[·] Отключено.")
                elif self.cli is None:
                    self.log("err", "[!] Нет подключения к физическому прибору.")
                elif op == "read":
                    self._read(task["name"])
                elif op == "write":
                    self._send(f"{task['name']}={task['val']}", task.get("expert", False))
                elif op == "write_reading_provider":
                    self._write_reading_provider(task)
                elif op == "clear_archive_provider":
                    self._clear_archive_provider(task)
                elif op == "send":
                    self._send(task["text"], task.get("expert", False))
                elif op == "auth":
                    self._auth(task["cred"], task["value"])
                elif op == "passport":
                    self._passport()
                elif op == "authscan":
                    self._authscan()
                elif op == "tele_read":
                    self._tele_read()
                elif op == "preflight":
                    self._preflight()
                elif op == "scan_all":
                    self._scan_all()
                elif op == "batch":
                    self._batch(task.get("text", ""), task.get("expert", False),
                                task.get("dry_run", False))
                elif op == "export_session":
                    self._export_session(task.get("path"))
                elif op == "raw_hex":
                    self._raw_hex(task.get("hex", ""), task.get("timeout"), task.get("expert", False))
                elif op == "sms_receive":
                    self._sms_receive(task.get("delete", False))
                elif op == "modem_at":
                    self._modem_at(task.get("text", "AT"))
            except Exception as exc:
                self.log("err", f"[FAIL] {op}: {exc}")
                if op == "connect" or isinstance(exc, getattr(sc, "TransportError", OSError)):
                    self._close()
                    self.post("status", ("off", ""))

    def _wire_log(self, secret=False):
        tr = self.cli.t
        if secret:
            self.post("hex", "TX [секрет скрыт]")
            self.post("hex", "RX [секрет скрыт]")
            return
        self.post("hex", hexdump("TX", getattr(tr, "last_tx", b"")))
        # В hex показываются именно байты на проводе, включая оптическое эхо.
        self.post("hex", hexdump("RX", getattr(tr, "last_raw_rx", b"") or b""))
        if getattr(tr, "last_echo_removed", False) and not self._echo_noted:
            self._echo_noted = True
            self.log("ok", "[линия] Обнаружено само-эхо оптоголовки; оно автоматически "
                           "удаляется только из разбираемого ответа. В hex остаются исходные байты.")

    def _connect(self, task):
        """Открыть выбранный реальный транспорт."""
        self._close()
        transport = task.get("transport", "serial")
        if transport == "serial":
            self._connect_serial(task)
        elif transport == "tcp":
            self._connect_tcp(task)
        elif transport == "sms":
            self._connect_sms(task)
        else:
            raise ValueError(f"Неизвестный транспорт: {transport}")

    def _start_recorder(self, **header):
        if ss is None:
            return
        try:
            self.recorder = ss.SessionRecorder(os.path.join(HERE, "sessions"))
            self.recorder.header(**header)
            self.post("session_file", self.recorder.jsonl_path or "")
            self.log("ok", f"[сессия] запись на диск: {self.recorder.jsonl_path}")
        except Exception as exc:
            self.recorder = None
            self.log("warn", f"[сессия] журнал не открыт: {exc}")

    def _connect_serial(self, task):
        port = task["port"].strip()
        baud = int(task["baud"]); requested = task["framing"]
        bits = int(task.get("bytesize", 8)); parity = task.get("parity", "N")
        stopbits = float(task.get("stopbits", 1))
        self.log("ok", f"[*] Открываю {port} · {baud} {bits}{parity}{stopbits:g} · кадр {requested}…")
        tr = sc.OpticTransport(
            port, baud, bytesize=bits, parity=parity, stopbits=stopbits,
            xonxoff=bool(task.get("xonxoff")), rtscts=bool(task.get("rtscts")),
            dsrdtr=bool(task.get("dsrdtr")), dtr=bool(task.get("dtr")),
            rts=bool(task.get("rts")),
            response_timeout=float(task.get("response_timeout", 2.5)),
            idle_gap=float(task.get("idle_gap", 0.25)),
            read_retries=int(task.get("read_retries", 1)),
        )
        try:
            if requested == "auto":
                frame_name, probe = tr.detect_framing("DevInfo")
            else:
                tr.set_framing(requested); probe = tr.probe("DevInfo"); frame_name = requested
        except Exception:
            tr.close(); raise
        self.cli = sc.SmtClient(tr); self.mode = "serial"; self._echo_noted = False
        self._wire_log(); devinfo = sc.value_of(probe, name="DevInfo")
        self.post("status", ("serial", tr.line_description()))
        self.log("ok", f"[+] Реальный прибор подключён: {tr.line_description()} · "
                       f"кадр {frame_name} · ответ {tr.last_latency_ms} мс")
        self.log("io", f"     DevInfo = {pretty(devinfo)!r}")
        self._start_recorder(port=port, baud=baud, framing=frame_name,
                             transport="serial", line=tr.line_description(),
                             devinfo=str(pretty(devinfo)))

    def _connect_tcp(self, task):
        host = task.get("host", "").strip(); port = int(task.get("tcp_port", 0))
        term_name = task.get("terminator", "CRLF")
        terms = {"нет": b"", "CR": b"\r", "LF": b"\n", "CRLF": b"\r\n"}
        if not host or not 1 <= port <= 65535:
            raise ValueError("Для TCP укажи host и порт 1…65535")
        tr = sc.TcpServerTransport(host, port, timeout=float(task.get("tcp_timeout", 3.0)),
                                   idle_gap=float(task.get("idle_gap", 0.25)),
                                   terminator=terms.get(term_name, b"\r\n"))
        self.log("ok", f"[*] Подключаю реальный TCP-шлюз {host}:{port}…")
        probe = tr.probe("DevInfo")
        self.cli = sc.SmtClient(tr); self.mode = "tcp"; self._wire_log()
        devinfo = sc.value_of(probe, name="DevInfo")
        self.post("status", ("tcp", f"{host}:{port}"))
        self.log("ok", f"[+] TCP-шлюз доступен: {host}:{port} · ответ {tr.last_latency_ms} мс")
        self.log("io", f"     DevInfo = {pretty(devinfo)!r}")
        self._start_recorder(port=f"{host}:{port}", baud=0, framing="tcp",
                             transport="tcp", devinfo=str(pretty(devinfo)))

    def _connect_sms(self, task):
        port = task.get("modem_port", "").strip(); phone = task.get("phone", "").strip()
        baud = int(task.get("modem_baud", 115200)); prefix = task.get("sms_prefix", "")
        self.log("ok", f"[*] Открываю GSM-модем {port} · {baud} для SMS → {phone}…")
        tr = sc.SmsTransport(port, phone, baud=baud, prefix=prefix,
                             response_timeout=float(task.get("sms_timeout", 20.0)))
        health = tr.health_check()
        self.cli = sc.SmtClient(tr); self.mode = "sms"; self._wire_log()
        self.post("status", ("sms", f"{port} → {phone}"))
        self.log("ok", f"[+] GSM-модем готов: {port} · SMS → {phone}")
        self.log("io", "     " + pretty(sc.decode_response(health).strip()))
        self._start_recorder(port=port, baud=baud, framing="sms-text",
                             transport="sms", devinfo=f"SMS target {phone}")

    def _close(self):
        if self.recorder is not None:
            try:
                self.recorder.close()
            except Exception:
                pass
            self.recorder = None
        try:
            if self.cli is not None:
                close = getattr(self.cli.t, "close", None)
                if close:
                    close()
                elif getattr(self.cli.t, "ser", None) is not None:
                    self.cli.t.ser.close()
        except Exception:
            pass
        self.cli = None
        self.mode = "off"
        self.auth_state = {"level": "guest", "verified": False, "verified_at": 0.0}
        self.post("auth_state", dict(self.auth_state))

    def _tx(self, cmd, retry_safe=False, expert=False, mutating=None, kind="read"):
        """Один физический обмен. Повтор — только для чтения; критичные записи/
        действия проходят только с expert=True (второй рубеж в SmtClient.send).
        Каждый обмен пишется в журнал сессии на диск."""
        tr = self.cli.t
        name = sc.command_name(cmd)
        secret = name in getattr(sc, "SECRET_NAMES", set()) or name in AUTH_CREDS
        error = ""
        raw = b""
        try:
            raw = self.cli.send(cmd, retry_safe=retry_safe, expert=expert, mutating=mutating)
        except Exception as exc:
            error = str(exc)
            self._safe_record(kind=kind, name=name, cmd=cmd, tr=tr, value=None,
                              ok=False, expert=expert,
                              critical=(name in self.critical), secret=secret, error=error)
            raise
        self._wire_log(secret=secret)
        val = sc.value_of(raw, name=name)
        base = cmd.strip()
        if "=" not in base and base in AUTH_CREDS and val and classify_secret(val) == "открытым текстом":
            self.post("password", (base, pretty(val)))
        self._safe_record(kind=kind, name=name, cmd=cmd, tr=tr, value=val,
                          ok=bool(raw), expert=expert,
                          critical=(name in self.critical), secret=secret)
        return raw, val

    def _safe_record(self, **kw):
        if not self.recorder:
            return
        tr = kw.pop("tr", None)
        try:
            self.recorder.record(
                tx=getattr(tr, "last_tx", b""),
                rx_raw=getattr(tr, "last_raw_rx", b""),
                rx_clean=getattr(tr, "last_rx", b""),
                latency_ms=getattr(tr, "last_latency_ms", 0),
                attempts=getattr(tr, "last_attempts", 1),
                echo_removed=getattr(tr, "last_echo_removed", False),
                **kw)
        except Exception:
            pass

    def _export_session(self, path):
        if not (self.recorder and path):
            self.log("warn", "[сессия] нечего экспортировать.")
            return
        try:
            n = self.recorder.export_csv(path)
            self.log("ok", f"[сессия] экспортировано {n} строк → {path}")
        except Exception as exc:
            self.log("err", f"[сессия] ошибка экспорта: {exc}")

    def _fmt(self, name, raw, val):
        if val not in (None, ""):
            return f"{name} = {pretty(val)}"
        if not raw:
            return f"{name} = (нет ответа)"
        text = pretty(sc.decode_response(raw).strip())
        return text or f"{name} = (ok)"

    def _read(self, name):
        raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
        shown = pretty(val) if val not in (None, "") else ""
        self.post("reading", (name, shown, datetime.datetime.now().isoformat(timespec="seconds")))
        self.log("io", f">> {name}\n<< {self._fmt(name, raw, val)}")

    def _send(self, text, expert):
        text = text.strip()
        if not text:
            return
        name, kind = classify_send(text, self.actions)
        if kind == "read":
            self._read(name)
            return
        critical = name in self.critical
        if name == "CLEAR_ARHIVE":
            raise PermissionError(
                "CLEAR_ARHIVE доступна только отдельной Provider-операцией с проверкой ArcNumRecords=0")
        if kind == "write" and name in READING_COMMANDS:
            raise PermissionError(
                f"{name}=… меняет учётные показания. Используй контролируемую кнопку "
                "«Записать показание (Provider)»: подтверждённая авторизация, SET и read-back. "
                "Очистка архива выполняется отдельно.")
        if critical and not expert:
            self.log("warn", f"[заблокировано] '{name}' — критичная команда ({kind}). "
                             "Включи «Экспертный режим» для фактической отправки на прибор.")
            return
        if critical:
            self.log("warn", f"⚠ ЭКСПЕРТ: отправка критичной команды >> {text}")
        # Запись/действие не повторяются автоматически: неизвестно, успел ли прибор
        # выполнить первую посылку до потери ответа.
        raw, val = self._tx(text, retry_safe=False, expert=expert, mutating=True, kind=kind)
        self.log("io", f">> {text}\n<< {self._fmt(name, raw, val)}")


    def _read_value_quiet(self, name):
        raw, val = self._tx(name, retry_safe=True, mutating=False, kind="service-read")
        return pretty(val) if val not in (None, "") else ""

    def _provider_is_verified(self):
        if not self.auth_state.get("verified") or self.auth_state.get("level") != "provider":
            return False
        return time.time() - float(self.auth_state.get("verified_at") or 0.0) <= PROVIDER_AUTH_TTL

    def _require_provider(self, *, expert=False):
        if not expert:
            raise PermissionError("Операция требует Экспертный режим")
        if not self._provider_is_verified():
            self.auth_state = {"level": "guest", "verified": False, "verified_at": 0.0}
            self.post("auth_state", dict(self.auth_state))
            raise PermissionError(
                "Уровень Provider не подтверждён или истёк. Выполни штатную авторизацию заново")

    def _audit_service(self, *, kind, name, before="", after="", operator="", reason=""):
        if not self.recorder:
            return
        try:
            self.recorder.record(
                kind=kind, name=name, cmd=name,
                value={"before": before, "after": after,
                       "operator": operator or "не указан", "reason": reason or "не указана"},
                ok=True, expert=True, critical=True,
            )
        except Exception:
            pass

    def _write_reading_provider(self, task):
        """Штатная запись показания после подтверждённой Provider-авторизации.

        Архив прибора не очищается. После единственной команды SET выполняется
        обязательный read-back; результат и основание операции попадают в журнал
        сессии, при этом пароль Provider не сохраняется.
        """
        self._require_provider(expert=task.get("expert", False))
        name = str(task.get("name") or "Volume").strip()
        if name not in READING_COMMANDS:
            raise ValueError(f"{name}: не является командой учётных показаний")
        target = parse_reading(task.get("val", ""))
        target_text = format(target, "f")

        operator = str(task.get("operator") or "").strip()
        reason = str(task.get("reason") or "").strip()
        if not operator or not reason:
            raise ValueError("Для сервисной записи обязательны оператор и причина")

        self.log("warn", f"[Provider] {name}: штатная запись {target_text}; архив не изменяется")
        before = self._read_value_quiet(name)
        parse_reading(before)
        device_sn = self._read_value_quiet("DEVICE_SN")
        arc_before = self._read_value_quiet("ArcNumRecords")

        self._tx(f"{name}={target_text}", retry_safe=False, expert=True,
                 mutating=True, kind="reading-set")
        after = self._read_value_quiet(name)
        actual = parse_reading(after)
        tolerance = max(abs(target) * Decimal("0.000000001"), Decimal("0.000001"))
        if abs(actual - target) > tolerance:
            raise RuntimeError(f"read-back не совпал: ожидалось {target}, прибор вернул {actual}")

        result = {
            "device_sn": device_sn, "command": name, "old_value": before,
            "new_value": after, "archive_count_before": arc_before,
            "archive_count_after": arc_before, "archive_changed": False,
            "operator": operator, "reason": reason,
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self._audit_service(kind="provider-write", name=name, before=before, after=after,
                            operator=operator, reason=reason)
        self.log("ok", f"[Provider] {name}: {before} → {after}; "
                       f"ArcNumRecords не изменялся ({arc_before or '—'})")
        self.post("reading", (name, after, datetime.datetime.now().isoformat(timespec="seconds")))
        self.post("reading_write_done", result)

    def _clear_archive_provider(self, task):
        """Отдельно очистить измерительный архив после Provider-подтверждения."""
        self._require_provider(expert=task.get("expert", False))
        operator = str(task.get("operator") or "").strip()
        reason = str(task.get("reason") or "").strip()
        if not operator or not reason:
            raise ValueError("Для очистки архива обязательны оператор и причина")
        device_sn = self._read_value_quiet("DEVICE_SN")
        arc_before = self._read_value_quiet("ArcNumRecords")
        self._tx("CLEAR_ARHIVE", retry_safe=False, expert=True,
                 mutating=True, kind="archive-clear")
        arc_after = ""
        for attempt in range(4):
            if attempt:
                time.sleep(0.25)
            arc_after = self._read_value_quiet("ArcNumRecords")
            try:
                if int(Decimal(str(arc_after).replace(",", "."))) == 0:
                    break
            except (InvalidOperation, ValueError):
                pass
        else:
            raise RuntimeError(
                f"CLEAR_ARHIVE отправлена, но очистка не подтверждена: ArcNumRecords={arc_after!r}")
        result = {
            "device_sn": device_sn, "archive_count_before": arc_before,
            "archive_count_after": arc_after, "operator": operator, "reason": reason,
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self._audit_service(kind="archive-clear", name="CLEAR_ARHIVE",
                            before=arc_before, after=arc_after,
                            operator=operator, reason=reason)
        self.log("ok", f"[Provider] измерительный архив очищен: {arc_before or '—'} → {arc_after}")
        self.post("archive_clear_done", result)

    def _auth(self, cred, value):
        self.auth_state = {"level": "guest", "verified": False, "verified_at": 0.0}
        self.post("auth_state", dict(self.auth_state))
        if cred == "PASSWORD_PROVIDER" and self.mode == "sms":
            raise RuntimeError(
                "Подтверждённая Provider-авторизация по SMS недоступна: SMS асинхронен, "
                "а текущая операция требует немедленного PASWORD_PROVID_VALUE read-back")
        cmd = f"{cred}={value}" if value != "" else cred
        self.log("ok", f"[auth] Предъявление учётных данных: {cred} …")
        raw, val = self._tx(cmd, retry_safe=False, expert=True, mutating=True, kind="auth")
        self.log("io", f">> {cred}=•••\n<< ответ получен ({len(raw)} байт; значение скрыто)")
        if cred == "PASSWORD_PROVIDER":
            if sc.response_has_auth_error(raw):
                raise PermissionError("Прибор отклонил пароль Provider")
            probe_raw, probe_val = self._tx(
                "PASWORD_PROVID_VALUE", retry_safe=True, mutating=False, kind="auth-verify")
            if not sc.provider_probe_ok(probe_val):
                raise PermissionError(
                    "Provider не подтверждён: PASWORD_PROVID_VALUE не вернула допустимый ответ")
            self.auth_state = {
                "level": "provider", "verified": True,
                "verified_at": time.time(), "probe": pretty(probe_val),
            }
            self.post("auth_state", dict(self.auth_state))
            self.log("ok", "[auth] Уровень Provider подтверждён командой PASWORD_PROVID_VALUE "
                           f"на {PROVIDER_AUTH_TTL // 60} минут.")
        else:
            self.auth_state = {"level": "guest", "verified": False, "verified_at": 0.0}
            self.post("auth_state", dict(self.auth_state))
            self.log("warn", "[auth] Учётные данные отправлены, но автоматическая проверка "
                             "реализована только для Provider.")

    def _passport(self):
        self.log("ok", "[*] Снятие паспорта с текущего транспорта…")
        ok = 0
        for name in sc.PASSPORT:
            try:
                raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
                if raw:
                    ok += 1
                self.log("io", f"  {name:<20} = {pretty(val)!r}")
            except Exception as exc:
                self.log("err", f"  {name:<20} = <err:{exc}>")
            time.sleep(0.04)
        self.log("ok", f"[*] Паспорт завершён: ответы {ok}/{len(sc.PASSPORT)}.")

    def _authscan(self):
        self.log("ok", "[*] Auth-scan — чтение доступных учётных параметров:")
        plain = False
        for name, desc in SECRET_READS:
            raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
            status = classify_secret(val)
            shown = repr(pretty(val)) if val else "—"
            self.log("io", f"    {name:<22}= {shown:<18} [{status}]  · {desc}")
            plain |= status == "открытым текстом"
        if plain:
            self.log("ok", "[OK] Прибор отдал хотя бы один действующий креденшл открытым текстом.")
        else:
            self.log("warn", "[!] Креды не отданы или маскированы текущей прошивкой/уровнем.")

    def _tele_read(self):
        self.log("ok", "[тел] Снятие текущих параметров по физическому оптопорту…")
        values = {}
        for name in TELE_PARAMS:
            raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
            values[name] = pretty(val) if val not in (None, "") else ""
            self.log("io", f"  {name:<16} = {values[name]!r}")
        self.post("tele_reading", values)

    def _scan_all(self):
        if self.mode == "sms":
            raise RuntimeError("Полный опрос по SMS отключён: он отправил бы сотни сообщений. "
                               "Используй выборочные команды или пакетный сценарий.")
        self.cancel_event.clear()
        values = {}
        total = len(self.catalog)
        self.log("ok", f"[*] Полный безопасный опрос каталога: {total} команд (только READ)…")
        for index, item in enumerate(self.catalog, 1):
            if self.cancel_event.is_set():
                self.log("warn", f"[scan] остановлено пользователем: {index-1}/{total}")
                break
            name = item["name"]
            if name in self.actions:
                # Действия нельзя безопасно "прочитать": голое имя запускает операцию.
                # Они входят в снимок как доступная возможность, но не выполняются.
                values[name] = "<action: не выполнялось>"
            else:
                try:
                    raw, val = self._tx(name, retry_safe=True, mutating=False, kind="scan")
                    values[name] = pretty(val) if val not in (None, "") else ("<no response>" if not raw else "")
                except Exception as exc:
                    values[name] = f"<err:{exc}>"
            self.post("scan_progress", (index, total, name, values[name]))
            time.sleep(0.015)
        self.post("snapshot", (values, self.mode))
        self.log("ok", f"[*] Снимок готов: {len(values)}/{total} параметров.")

    def _batch(self, text, expert, dry_run=False):
        if tools_mod is None:
            raise RuntimeError("модуль smt_tools.py не найден")
        steps = tools_mod.parse_batch_script(text, self.actions)
        protected = [s for s in steps if s.kind in ("write", "action") and s.name in self.critical]
        if protected and not expert and not dry_run:
            names = ", ".join(sorted({x.name for x in protected}))
            raise PermissionError("сценарий содержит критические операции: " + names +
                                  ". Включи Экспертный режим.")
        self.log("ok", f"[batch] сценарий: {len(steps)} шагов" +
                 (" · только проверка" if dry_run else " · выполнение"))
        if dry_run:
            for i, step in enumerate(steps, 1):
                self.log("io", f"  {i:03d} · строка {step.line}: {step.kind} "
                               f"{step.name}{('=' + step.value) if step.kind == 'write' else ''}"
                               f"{(' ' + str(step.delay_ms) + ' ms') if step.kind == 'sleep' else ''}")
            self.post("batch_done", (True, len(steps), "Сценарий корректен"))
            return
        self.cancel_event.clear()
        done = 0
        for i, step in enumerate(steps, 1):
            if self.cancel_event.is_set():
                self.log("warn", f"[batch] остановлено: {done}/{len(steps)}")
                self.post("batch_done", (False, done, "Остановлено пользователем")); return
            self.post("batch_progress", (i, len(steps), step.source))
            if step.kind == "sleep":
                deadline = time.monotonic() + step.delay_ms / 1000.0
                while time.monotonic() < deadline:
                    if self.cancel_event.is_set():
                        break
                    time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            elif step.kind == "read":
                self._read(step.name)
            elif step.kind == "write":
                self._send(f"{step.name}={step.value}", expert)
            elif step.kind == "action":
                self._send(step.name, expert)
            done += 1
        self.post("batch_done", (True, done, "Выполнено"))
        self.log("ok", f"[batch] завершено: {done}/{len(steps)}")

    def _raw_hex(self, text, timeout=None, expert=False):
        if not expert:
            raise PermissionError("RAW HEX доступен в Экспертном режиме: точные байты могут "
                                  "выполнить неизвестную запись или сервисную операцию.")
        compact = "".join(str(text).replace("0x", "").replace(",", " ").split())
        if not compact:
            return
        if len(compact) % 2:
            raise ValueError("HEX-строка должна содержать чётное число цифр")
        try:
            payload = bytes.fromhex(compact)
        except ValueError as exc:
            raise ValueError("Некорректная HEX-строка") from exc
        raw_exchange = getattr(self.cli.t, "raw_exchange", None)
        if raw_exchange is None:
            raise RuntimeError("Текущий транспорт не поддерживает сырой HEX-обмен")
        raw = raw_exchange(payload, response_timeout=float(timeout) if timeout else None)
        self._wire_log()
        self.log("io", f">> RAW HEX ({len(payload)}): {payload.hex(' ').upper()}\n"
                       f"<< RAW HEX ({len(raw)}): {raw.hex(' ').upper() if raw else '(нет ответа)'}")
        self.post("raw_result", raw)

    def _sms_receive(self, delete=False):
        receive = getattr(self.cli.t, "receive_unread", None)
        if receive is None:
            raise RuntimeError("Текущий транспорт не является GSM/SMS-модемом")
        messages = receive(delete=bool(delete))
        self.log("ok", f"[SMS] непрочитанных сообщений: {len(messages)}")
        for item in messages:
            self.log("io", f"  #{item.get('index')} {item.get('header')}\n     {item.get('text')}")
        self.post("sms_messages", messages)

    def _modem_at(self, text):
        send_at = getattr(self.cli.t, "send_at", None)
        if send_at is None:
            raise RuntimeError("AT-команды доступны только для GSM-модема")
        raw = send_at(str(text).strip())
        self._wire_log()
        self.log("io", f">> AT {text}\n<< {pretty(sc.decode_response(raw).strip())}")

    def _preflight(self):
        self.log("ok", "[*] Пре-флайт: проверка активного реального транспорта…")
        tr = self.cli.t
        if self.mode == "sms":
            raw = tr.health_check(); self._wire_log()
            self.log("ok", f"[OK] GSM-модем отвечает · {tr.last_latency_ms} мс")
            self.log("io", "     " + pretty(sc.decode_response(raw).strip()))
            return
        raw = tr.probe("DevInfo")
        self._wire_log(); value = sc.value_of(raw, name="DevInfo")
        self.log("ok", f"[OK] Канал отвечает · {self.mode} · кадр "
                       f"{getattr(tr, 'frame_name', '—') or 'ручной'} · "
                       f"{tr.last_latency_ms} мс · RX {len(tr.last_raw_rx)} байт" +
                       (" · оптическое эхо снято" if getattr(tr, 'last_echo_removed', False) else ""))
        self.log("io", f"     DevInfo = {pretty(value)!r}")


# ───────────────────────────── интерфейс ────────────────────────────────
def build_app(root, selftest=False):
    import tkinter as tk
    from tkinter import ttk, scrolledtext, filedialog, messagebox, simpledialog

    catalog = load_catalog()
    critical = build_critical(catalog)
    actions = build_actions(catalog)
    task_q, out_q = queue.Queue(), queue.Queue()
    backend = Backend(task_q, out_q, critical, actions, catalog); backend.start()

    root.title("Контроллер устройства 4.4 PROVIDER SERVICE · 158 команд")
    root.geometry("1220x850")

    state = {"selected": None, "connected": False, "expert": False,
             "mode": "off", "current_snapshot": {}, "loaded_snapshot": {},
             "monitoring": False, "monitor_rows": [],
             "provider_verified": False, "provider_verified_at": 0.0}
    settings = load_settings()

    # ── шапка: реальные транспорты ─────────────────────────────────────
    top = ttk.Frame(root, padding=6); top.pack(fill="x")
    ttk.Label(top, text="Транспорт:").pack(side="left")
    transport_var = tk.StringVar(value=settings.get("transport", "Оптопорт / Serial"))
    transport_cb = ttk.Combobox(top, textvariable=transport_var, state="readonly", width=18,
                                values=["Оптопорт / Serial", "TCP-шлюз", "GSM / SMS"])
    transport_cb.pack(side="left", padx=(3, 8))
    conn_btn = ttk.Button(top, text="Подключить"); conn_btn.pack(side="left")
    status_lbl = ttk.Label(top, text="● отключено", foreground="#b00"); status_lbl.pack(side="left", padx=10)

    def list_ports():
        try:
            from serial.tools import list_ports
            ports = list(list_ports.comports())
            if not ports:
                messagebox.showinfo("Порты", "Serial-порты не найдены.\nПодключи USB-оптоголовку или GSM-модем.")
                return
            lines = []
            for item in ports:
                details = item.description or "serial"
                if item.vid is not None and item.pid is not None:
                    details += f" · VID:PID={item.vid:04X}:{item.pid:04X}"
                lines.append(f"{item.device} — {details}")
            candidates = [item.device for item in ports if any(
                hint in ((item.device or "") + " " + (item.description or "")).lower()
                for hint in ("ttyusb", "ttyacm", "usbserial", "usbmodem", "ch340", "cp210", "ftdi", "com")
            )]
            if len(candidates) == 1:
                port_var.set(candidates[0])
            messagebox.showinfo("Физические serial-порты", "\n".join(lines) +
                                (f"\n\nАвтовыбран: {candidates[0]}" if len(candidates) == 1 else ""))
        except Exception as e:
            messagebox.showerror("Порты", str(e))
    ttk.Button(top, text="Порты…", command=list_ports).pack(side="left")

    def do_dump():
        path = filedialog.askopenfilename(filetypes=[("dump W25Q64", "*.bin"), ("все", "*.*")])
        if path:
            hist_load_path(path); main_nb.select(tab_hist)
    ttk.Button(top, text="Открыть flash-дамп…", command=do_dump).pack(side="right")

    conn = ttk.LabelFrame(root, text="Параметры физического подключения", padding=(6, 3))
    conn.pack(fill="x", padx=6, pady=(0, 4))
    for col in range(14): conn.columnconfigure(col, weight=0)

    # Serial / оптопорт
    ttk.Label(conn, text="Serial:").grid(row=0, column=0, sticky="w")
    port_var = tk.StringVar(value=suggested_port(settings.get("port")))
    port_ent = ttk.Entry(conn, textvariable=port_var, width=15); port_ent.grid(row=0, column=1, padx=2)
    baud_var = tk.StringVar(value=str(settings.get("baud", "9600")))
    baud_cb = ttk.Combobox(conn, textvariable=baud_var, width=7, values=[
        "300", "600", "1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200", "230400"
    ])
    baud_cb.grid(row=0, column=2, padx=2)
    fr_var = tk.StringVar(value=settings.get("framing", "auto"))
    fr_cb = ttk.Combobox(conn, textvariable=fr_var, width=7, state="readonly",
                         values=["auto"] + list(sc.FRAMINGS.keys())); fr_cb.grid(row=0, column=3, padx=2)
    bits_var = tk.StringVar(value=str(settings.get("bytesize", "8")))
    bits_cb = ttk.Combobox(conn, textvariable=bits_var, width=3, state="readonly", values=["5","6","7","8"]); bits_cb.grid(row=0,column=4,padx=2)
    parity_var = tk.StringVar(value=settings.get("parity", "N"))
    parity_cb = ttk.Combobox(conn, textvariable=parity_var, width=3, state="readonly", values=["N","E","O","M","S"]); parity_cb.grid(row=0,column=5,padx=2)
    stop_var = tk.StringVar(value=str(settings.get("stopbits", "1")))
    stop_cb = ttk.Combobox(conn, textvariable=stop_var, width=4, state="readonly", values=["1","1.5","2"]); stop_cb.grid(row=0,column=6,padx=2)
    ttk.Label(conn, text="таймаут:").grid(row=0,column=7,sticky="e")
    resp_timeout_var = tk.StringVar(value=str(settings.get("response_timeout", "2.5")))
    resp_timeout_ent = ttk.Entry(conn,textvariable=resp_timeout_var,width=5); resp_timeout_ent.grid(row=0,column=8,padx=2)
    ttk.Label(conn, text="пауза:").grid(row=0,column=9,sticky="e")
    idle_gap_var = tk.StringVar(value=str(settings.get("idle_gap", "0.25")))
    idle_gap_ent = ttk.Entry(conn,textvariable=idle_gap_var,width=5); idle_gap_ent.grid(row=0,column=10,padx=2)
    ttk.Label(conn, text="повторы READ:").grid(row=0,column=11,sticky="e")
    retries_var = tk.StringVar(value=str(settings.get("read_retries", "1")))
    retries_ent = ttk.Entry(conn,textvariable=retries_var,width=3); retries_ent.grid(row=0,column=12,padx=2)

    flow = ttk.Frame(conn); flow.grid(row=0,column=13,sticky="w")
    xon_var=tk.BooleanVar(value=bool(settings.get("xonxoff",False)))
    rtscts_var=tk.BooleanVar(value=bool(settings.get("rtscts",False)))
    dsrdtr_var=tk.BooleanVar(value=bool(settings.get("dsrdtr",False)))
    dtr_var=tk.BooleanVar(value=bool(settings.get("dtr",False)))
    rts_var=tk.BooleanVar(value=bool(settings.get("rts",False)))
    for text,var in (("XON",xon_var),("RTS/CTS",rtscts_var),("DSR/DTR",dsrdtr_var),("DTR=1",dtr_var),("RTS=1",rts_var)):
        ttk.Checkbutton(flow,text=text,variable=var).pack(side="left")

    # TCP
    ttk.Label(conn, text="TCP:").grid(row=1,column=0,sticky="w")
    tcp_host_var=tk.StringVar(value=settings.get("tcp_host","127.0.0.1"))
    tcp_host_ent=ttk.Entry(conn,textvariable=tcp_host_var,width=20); tcp_host_ent.grid(row=1,column=1,columnspan=2,sticky="ew",padx=2)
    tcp_port_var=tk.StringVar(value=str(settings.get("tcp_port","40000")))
    tcp_port_ent=ttk.Entry(conn,textvariable=tcp_port_var,width=7); tcp_port_ent.grid(row=1,column=3,padx=2)
    term_var=tk.StringVar(value=settings.get("terminator","CRLF"))
    term_cb=ttk.Combobox(conn,textvariable=term_var,width=6,state="readonly",values=["нет","CR","LF","CRLF"]); term_cb.grid(row=1,column=4,padx=2)
    tcp_timeout_var=tk.StringVar(value=str(settings.get("tcp_timeout","3.0")))
    ttk.Label(conn,text="таймаут:").grid(row=1,column=5,sticky="e")
    tcp_timeout_ent=ttk.Entry(conn,textvariable=tcp_timeout_var,width=5); tcp_timeout_ent.grid(row=1,column=6,padx=2)

    # GSM/SMS
    ttk.Label(conn, text="SMS:").grid(row=2,column=0,sticky="w")
    modem_port_var=tk.StringVar(value=settings.get("modem_port", suggested_port()))
    modem_port_ent=ttk.Entry(conn,textvariable=modem_port_var,width=15); modem_port_ent.grid(row=2,column=1,padx=2)
    modem_baud_var=tk.StringVar(value=str(settings.get("modem_baud","115200")))
    modem_baud_cb=ttk.Combobox(conn,textvariable=modem_baud_var,width=7,values=["9600","19200","38400","57600","115200"]); modem_baud_cb.grid(row=2,column=2,padx=2)
    phone_var=tk.StringVar(value=settings.get("phone",""))
    phone_ent=ttk.Entry(conn,textvariable=phone_var,width=18); phone_ent.grid(row=2,column=3,columnspan=2,padx=2,sticky="ew")
    sms_prefix_var=tk.StringVar(value=settings.get("sms_prefix",""))
    sms_prefix_ent=ttk.Entry(conn,textvariable=sms_prefix_var,width=18); sms_prefix_ent.grid(row=2,column=5,columnspan=2,padx=2,sticky="ew")
    sms_timeout_var=tk.StringVar(value=str(settings.get("sms_timeout","20")))
    ttk.Label(conn,text="таймаут:").grid(row=2,column=7,sticky="e")
    sms_timeout_ent=ttk.Entry(conn,textvariable=sms_timeout_var,width=5); sms_timeout_ent.grid(row=2,column=8,padx=2)
    ttk.Label(conn,text="номер / префикс команды").grid(row=2,column=9,columnspan=4,sticky="w")

    serial_widgets=[port_ent,baud_cb,fr_cb,bits_cb,parity_cb,stop_cb,resp_timeout_ent,idle_gap_ent,retries_ent]
    tcp_widgets=[tcp_host_ent,tcp_port_ent,term_cb,tcp_timeout_ent]
    sms_widgets=[modem_port_ent,modem_baud_cb,phone_ent,sms_prefix_ent,sms_timeout_ent]
    def update_transport_fields(*_):
        mode=transport_var.get()
        def set_group(items,enabled):
            for w in items:
                try: w.state(["!disabled"] if enabled else ["disabled"])
                except Exception: w.configure(state="normal" if enabled else "disabled")
        set_group(serial_widgets, mode.startswith("Оптопорт"))
        set_group(tcp_widgets, mode.startswith("TCP"))
        set_group(sms_widgets, mode.startswith("GSM"))
    transport_cb.bind("<<ComboboxSelected>>", update_transport_fields)

    def do_connect():
        if state["connected"]:
            task_q.put({"op":"disconnect"}); return
        label=transport_var.get()
        try:
            common={"op":"connect", "idle_gap":float(idle_gap_var.get() or 0.25)}
            if label.startswith("Оптопорт"):
                selected={**common,"transport":"serial","port":port_var.get().strip(),
                    "baud":int(baud_var.get()),"framing":fr_var.get(),"bytesize":int(bits_var.get()),
                    "parity":parity_var.get(),"stopbits":float(stop_var.get()),
                    "response_timeout":float(resp_timeout_var.get()),"read_retries":int(retries_var.get()),
                    "xonxoff":xon_var.get(),"rtscts":rtscts_var.get(),"dsrdtr":dsrdtr_var.get(),
                    "dtr":dtr_var.get(),"rts":rts_var.get()}
            elif label.startswith("TCP"):
                selected={**common,"transport":"tcp","host":tcp_host_var.get().strip(),
                    "tcp_port":int(tcp_port_var.get()),"terminator":term_var.get(),
                    "tcp_timeout":float(tcp_timeout_var.get())}
            else:
                selected={**common,"transport":"sms","modem_port":modem_port_var.get().strip(),
                    "modem_baud":int(modem_baud_var.get()),"phone":phone_var.get().strip(),
                    "sms_prefix":sms_prefix_var.get(),"sms_timeout":float(sms_timeout_var.get())}
        except ValueError:
            messagebox.showerror("Подключение","Проверь числовые параметры транспорта."); return
        saved={k:v for k,v in selected.items() if k!="op"}; saved["transport"]=label
        save_settings(saved); task_q.put(selected)
    conn_btn.config(command=do_connect)
    update_transport_fields()

    # ── второй ряд: уровень доступа / аутентификация / экспертный режим ──
    top2 = ttk.Frame(root, padding=(6, 0, 6, 6)); top2.pack(fill="x")
    ttk.Label(top2, text="Уровень:").pack(side="left")
    level_var = tk.StringVar(value=LEVELS[0])
    ttk.Combobox(top2, textvariable=level_var, values=LEVELS, state="readonly",
                 width=15).pack(side="left", padx=(2, 12))
    ttk.Label(top2, text="Логин:").pack(side="left")
    cred_var = tk.StringVar(value=AUTH_CREDS[0])
    ttk.Combobox(top2, textvariable=cred_var, values=AUTH_CREDS, state="readonly",
                 width=18).pack(side="left", padx=2)
    pw_var = tk.StringVar()
    ttk.Entry(top2, textvariable=pw_var, width=12, show="•").pack(side="left", padx=2)

    def do_auth():
        task_q.put({"op": "auth", "cred": cred_var.get(), "value": pw_var.get()})
    ttk.Button(top2, text="Аутентифицировать", command=do_auth).pack(side="left", padx=6)
    auth_lbl = ttk.Label(top2, text="○ Provider не подтверждён", foreground="#777")
    auth_lbl.pack(side="left", padx=(2, 8))

    expert_var = tk.BooleanVar(value=False)
    def toggle_expert():
        from tkinter import messagebox
        if expert_var.get():
            ok = messagebox.askyesno(
                "Экспертный режим — подтверждение",
                "Включить отправку КРИТИЧНЫХ команд на прибор?\n\n"
                "Разблокирует запись/действия для: АКТУАТОР, СЕРВИС/объём, "
                "флаги ВМЕШАТЕЛЬСТВА, ПАРОЛИ, СБРОС/перезагрузка.\n\n"
                "На реальном приборе это влияет на рабочую безопасность и сервисию "
                "(единство измерений). Отправляй только то, на что есть право и "
                "штатное основание. Продолжить?")
            if not ok:
                expert_var.set(False)
        state["expert"] = expert_var.get()
        exp_lbl.config(text=("● ЭКСПЕРТ ВКЛ" if state["expert"] else "○ эксперт выкл"),
                       foreground=("#c0392b" if state["expert"] else "#777"))
        try:
            on_select()
        except Exception:
            pass
    ttk.Checkbutton(top2, text="Экспертный режим", variable=expert_var,
                    command=toggle_expert).pack(side="left", padx=(16, 2))
    exp_lbl = ttk.Label(top2, text="○ эксперт выкл", foreground="#777")
    exp_lbl.pack(side="left")

    # ── верхний нотбук: «Команды» и «Телеметрия» ────────────────────────
    main_nb = ttk.Notebook(root)
    tab_cmd = ttk.Frame(main_nb)
    tab_terminal = ttk.Frame(main_nb, padding=6)
    tab_tele = ttk.Frame(main_nb, padding=6)
    tab_hist = ttk.Frame(main_nb, padding=6)
    tab_lab = ttk.Frame(main_nb, padding=6)
    main_nb.add(tab_cmd, text="Команды (158)")
    main_nb.add(tab_terminal, text="Транспорт · RAW · SMS")
    main_nb.add(tab_tele, text="Телеметрия")
    main_nb.add(tab_hist, text="История")
    main_nb.add(tab_lab, text="Снимки · сценарии · мониторинг")
    main_nb.pack(fill="both", expand=True)

    # ── тело вкладки «Команды»: слева каталог, справа детали+запись ──────
    body = ttk.Panedwindow(tab_cmd, orient="horizontal"); body.pack(fill="both", expand=True)

    left = ttk.Frame(body, padding=4); body.add(left, weight=3)
    filt = ttk.Frame(left); filt.pack(fill="x")
    ttk.Label(filt, text="Поиск:").pack(side="left")
    search_var = tk.StringVar()
    ttk.Entry(filt, textvariable=search_var).pack(side="left", fill="x", expand=True, padx=4)
    groups = ["(все группы)"] + sorted({c["group"] for c in catalog})
    grp_var = tk.StringVar(value=groups[0])
    ttk.Combobox(filt, textvariable=grp_var, values=groups, state="readonly", width=26).pack(side="left")

    cols = ("name", "desc", "type", "prov", "user", "prot")
    tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
    for c, txt, w, stretch in (("name", "Команда", 175, False),
                               ("desc", "Что делает", 300, True),
                               ("type", "Тип", 78, False),
                               ("prov", "П", 56, False), ("user", "О", 56, False),
                               ("prot", "запись", 84, False)):
        tree.heading(c, text=txt); tree.column(c, width=w, anchor="w", stretch=stretch)
    tree.tag_configure("prot", foreground="#c0392b")
    ysb = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=ysb.set)
    tree.pack(side="left", fill="both", expand=True, pady=4)
    ysb.pack(side="left", fill="y")
    count_lbl = ttk.Label(left, text="")
    count_lbl.pack(anchor="w")

    def refill(*_):
        q = search_var.get().lower().strip()
        g = grp_var.get()
        tree.delete(*tree.get_children())
        n = 0
        for c in catalog:
            if g != "(все группы)" and c["group"] != g:
                continue
            if q and q not in c["name"].lower() and q not in c["desc"].lower():
                continue
            is_critical = c["name"] in critical
            prot = "эксперт" if is_critical else "обычная"
            tags = ("prot",) if is_critical else ()
            tree.insert("", "end", iid=c["name"],
                        values=(c["name"], clean_desc(c["desc"], 70), c["type"],
                                access_human(c["prov"]), access_human(c["user"]), prot),
                        tags=tags)
            n += 1
        count_lbl.config(text=f"Показано: {n} из {len(catalog)} команд "
                              f"· красным — экспертная запись/действие")
    search_var.trace_add("write", refill)
    grp_var.trace_add("write", refill)

    # ── правая панель ───────────────────────────────────────────────────
    right = ttk.Frame(body, padding=4); body.add(right, weight=2)
    det = ttk.LabelFrame(right, text="Выбранная команда", padding=6); det.pack(fill="x")
    det_txt = tk.Text(det, height=8, wrap="word"); det_txt.pack(fill="x")
    det_txt.configure(state="disabled")

    io = ttk.LabelFrame(right, text="Чтение / запись / действие", padding=6); io.pack(fill="x", pady=6)
    io.columnconfigure(1, weight=1)
    hint_lbl = ttk.Label(io, text="—", foreground="#555", wraplength=360, justify="left")
    hint_lbl.grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(io, text="Значение:").grid(row=1, column=0, sticky="w")
    val_var = tk.StringVar()
    val_ent = ttk.Entry(io, textvariable=val_var)
    val_ent.grid(row=1, column=1, sticky="ew", padx=4)
    opt_cb = ttk.Combobox(io, width=15, state="readonly", values=[])
    opt_cb.grid(row=1, column=2, sticky="e")
    opt_cb.bind("<<ComboboxSelected>>",
                lambda e: val_var.set(opt_cb.get().split(" ", 1)[0]) if opt_cb.get() else None)
    now_btn = ttk.Button(io, text="сейчас", width=8,
        command=lambda: val_var.set(datetime.datetime.now().strftime("%d.%m.%y,%H:%M:%S")))
    now_btn.grid(row=2, column=2, sticky="e")
    read_btn = ttk.Button(io, text="Прочитать (get)")
    read_btn.grid(row=2, column=0, sticky="ew", pady=4)
    write_btn = ttk.Button(io, text="Записать (set)")
    write_btn.grid(row=2, column=1, sticky="ew", pady=4, padx=4)
    act_btn = ttk.Button(io, text="Выполнить (действие)")
    act_btn.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 4))
    prot_note = ttk.Label(io, text="", foreground="#c0392b", wraplength=360, justify="left")
    prot_note.grid(row=4, column=0, columnspan=3, sticky="w")

    provider_box = ttk.LabelFrame(right, text="Provider · сервисная работа с показаниями", padding=6)
    provider_box.pack(fill="x", pady=(0, 6))
    ttk.Label(provider_box, foreground="#8a4b08", wraplength=360, justify="left",
              text="Запись выполняется только после подтверждённой Provider-авторизации: "
                   "SET → read-back. Архив не очищается автоматически. CLEAR_ARHIVE вынесена "
                   "в отдельную операцию с самостоятельным подтверждением.").pack(anchor="w")
    clear_archive_btn = ttk.Button(provider_box, text="Очистить измерительный архив отдельно")
    clear_archive_btn.pack(fill="x", pady=(6, 0))
    provider_box.pack_forget()

    free = ttk.LabelFrame(right, text="Свободная команда (сырой протокол)", padding=6)
    free.pack(fill="x")
    free_var = tk.StringVar()
    ttk.Entry(free, textvariable=free_var).pack(side="left", fill="x", expand=True)
    def do_send_free():
        txt = free_var.get().strip()
        if txt:
            task_q.put({"op": "send", "text": txt, "expert": state["expert"]})
    ttk.Button(free, text="Отправить", command=do_send_free).pack(side="left", padx=6)

    quick = ttk.LabelFrame(right, text="Быстрые действия", padding=6); quick.pack(fill="x")
    quick.columnconfigure(0, weight=1); quick.columnconfigure(1, weight=1)
    _qa = [
        ("Пре-флайт", lambda: task_q.put({"op": "preflight"})),
        ("Паспорт", lambda: task_q.put({"op": "passport"})),
        ("Auth-scan", lambda: task_q.put({"op": "authscan"})),
        ("Показания", lambda: [task_q.put({"op": "read", "name": n}) for n in
                               ("Volume", "VOLUME_GLOB", "VOLUME_INST", "VOLUME_COMMIS")]),
    ]
    for _i, (_t, _cmd) in enumerate(_qa):
        ttk.Button(quick, text=_t, command=_cmd).grid(
            row=_i // 2, column=_i % 2, sticky="ew", padx=2, pady=2)

    def on_select(_=None):
        sel = tree.focus()
        if not sel:
            return
        c = next((x for x in catalog if x["name"] == sel), None)
        if not c:
            return
        state["selected"] = c
        det_txt.configure(state="normal"); det_txt.delete("1.0", "end")
        det_txt.insert("end", f"{c['name']}   ({c['type']})\n", "h")
        det_txt.insert("end", f"Группа: {c['group']}\n")
        det_txt.insert("end", f"Доступ  П={c['prov']} ({access_human(c['prov'])})  "
                              f"О={c['user']} ({access_human(c['user'])})\n")
        acc, _, can_w = access_at_level(c, level_var.get())
        det_txt.insert("end", f"На уровне «{level_var.get()}»: {acc}\n")
        det_txt.insert("end", f"Обработчик: {c['handler']}\n")
        det_txt.insert("end", f"\n{clean_desc(c['desc'])}\n")
        det_txt.tag_configure("h", font=("TkDefaultFont", 11, "bold"))
        det_txt.configure(state="disabled")
        typ = c["type"] or ""
        is_action = c["name"] in actions
        can_r, can_w, can_a = directions(c, is_action)
        hint_lbl.config(text=f"Тип: {typ}  ·  доступ П={c['prov']} О={c['user']}  ·  "
                             + ("действие (кнопка «Выполнить»)" if is_action
                                else "работает в обе стороны: чтение и запись"))
        opts = value_options(c)
        opt_cb.config(values=opts); opt_cb.set("")
        now_btn.grid() if "дата" in typ else now_btn.grid_remove()
        read_btn.state(["!disabled"] if can_r else ["disabled"])
        write_btn.state(["!disabled"] if can_w else ["disabled"])
        act_btn.state(["!disabled"] if can_a else ["disabled"])
        if c["name"] in READING_COMMANDS:
            write_btn.config(text="Записать показание (Provider)")
            provider_box.pack(fill="x", pady=(0, 6), before=free)
        else:
            write_btn.config(text="Записать (set)")
            provider_box.pack_forget()
        val_ent.state(["disabled"] if is_action else ["!disabled"])
        if c["name"] in critical:
            if state["expert"]:
                prot_note.config(text="⚠ КРИТИЧНАЯ + Экспертный режим ВКЛ — отправка "
                                      "выполнится (актуатор/сервис/пароли/сброс). "
                                      "Устройство проверит уровень.")
            else:
                prot_note.config(text="⚠ Критичная команда — запись/действие "
                                      "заблокированы. Включи «Экспертный режим» для отправки.")
        else:
            prot_note.config(text="Обычная команда — читается и пишется свободно "
                                  "(при нужном уровне доступа на приборе).")
    tree.bind("<<TreeviewSelect>>", on_select)
    level_var.trace_add("write", lambda *a: on_select())

    def do_read():
        if state["selected"]:
            task_q.put({"op": "read", "name": state["selected"]["name"]})
    def do_write():
        if not state["selected"]:
            return
        name = state["selected"]["name"]
        if name in READING_COMMANDS:
            if not state["expert"]:
                messagebox.showwarning("Запись показаний", "Включи Экспертный режим.")
                return
            if not state.get("provider_verified"):
                messagebox.showwarning(
                    "Запись показаний",
                    "Сначала выполни PASSWORD_PROVIDER и дождись статуса «Provider подтверждён».")
                return
            new_value = val_var.get().strip()
            try:
                new_value = reading_text(new_value)
            except ValueError as exc:
                messagebox.showerror("Запись показаний", str(exc))
                return
            operator = simpledialog.askstring(
                "Оператор", "Укажи имя/идентификатор уполномоченного оператора:",
                initialvalue=os.environ.get("USERNAME") or os.environ.get("USER") or "",
                parent=root)
            if not operator:
                append("warn", "[Provider] запись отменена: оператор не указан.")
                return
            reason = simpledialog.askstring(
                "Основание записи", "Укажи служебную причину изменения показания:", parent=root)
            if not reason:
                append("warn", "[Provider] запись отменена: причина не указана.")
                return
            confirmation = simpledialog.askstring(
                "Подтверждение Provider-записи",
                f"Будет отправлено {name}={new_value}, затем выполнен read-back. "
                "Архив прибора не очищается.\n\nДля подтверждения введи: ЗАПИСАТЬ",
                parent=root)
            if confirmation != "ЗАПИСАТЬ":
                append("warn", "[Provider] операция отменена: подтверждение записи не введено.")
                return
            task_q.put({"op": "write_reading_provider", "name": name, "val": new_value,
                        "expert": state["expert"], "operator": operator, "reason": reason})
            return
        task_q.put({"op": "write", "name": name,
                    "val": val_var.get(), "expert": state["expert"]})

    def do_clear_archive():
        if not state["expert"]:
            messagebox.showwarning("Очистка архива", "Включи Экспертный режим.")
            return
        if not state.get("provider_verified"):
            messagebox.showwarning(
                "Очистка архива",
                "Сначала выполни PASSWORD_PROVIDER и дождись подтверждения уровня Provider.")
            return
        operator = simpledialog.askstring(
            "Оператор", "Укажи имя/идентификатор уполномоченного оператора:",
            initialvalue=os.environ.get("USERNAME") or os.environ.get("USER") or "",
            parent=root)
        if not operator:
            return
        reason = simpledialog.askstring(
            "Основание очистки", "Укажи служебную причину очистки измерительного архива:",
            parent=root)
        if not reason:
            return
        confirmation = simpledialog.askstring(
            "Безвозвратная очистка архива",
            "Будет отправлена CLEAR_ARHIVE и затем проверено ArcNumRecords=0.\n\n"
            "Для подтверждения введи: ОЧИСТИТЬ",
            parent=root)
        if confirmation != "ОЧИСТИТЬ":
            append("warn", "[Provider] очистка архива отменена.")
            return
        task_q.put({"op": "clear_archive_provider", "expert": state["expert"],
                    "operator": operator, "reason": reason})
    def do_action():
        if state["selected"]:
            task_q.put({"op": "send", "text": state["selected"]["name"],
                        "expert": state["expert"]})
    read_btn.config(command=do_read)
    write_btn.config(command=do_write)
    act_btn.config(command=do_action)
    clear_archive_btn.config(command=do_clear_archive)

    # ── вкладка «Транспорт · RAW · SMS» ────────────────────────────────
    ttk.Label(tab_terminal, wraplength=1160, foreground="#555", justify="left",
              text="Работа только с реальным подключением. Командный терминал использует "
                   "каталожное кадрирование и экспертный гейт; RAW HEX передаёт точные байты "
                   "без добавления CR/LF/скобок; AT и приём SMS доступны при GSM-подключении.").pack(anchor="w")

    term_cmd = ttk.LabelFrame(tab_terminal, text="Командный терминал", padding=6)
    term_cmd.pack(fill="x", pady=(6, 3)); term_cmd.columnconfigure(1, weight=1)
    ttk.Label(term_cmd, text="Команда:").grid(row=0,column=0,sticky="w")
    terminal_cmd_var=tk.StringVar()
    terminal_cmd_ent=ttk.Entry(term_cmd,textvariable=terminal_cmd_var)
    terminal_cmd_ent.grid(row=0,column=1,sticky="ew",padx=5)
    def terminal_send():
        text=terminal_cmd_var.get().strip()
        if text: task_q.put({"op":"send","text":text,"expert":state["expert"]})
    ttk.Button(term_cmd,text="Отправить",command=terminal_send).grid(row=0,column=2)
    terminal_cmd_ent.bind("<Return>",lambda _e: terminal_send())
    ttk.Label(term_cmd,text="Примеры: DevInfo · SERVER_URL=host:port · VALVE_OPEN",
              foreground="#777").grid(row=1,column=1,sticky="w")

    raw_box = ttk.LabelFrame(tab_terminal, text="Точный RAW HEX-обмен (Serial/TCP)", padding=6)
    raw_box.pack(fill="both", expand=True, pady=3)
    raw_top=ttk.Frame(raw_box); raw_top.pack(fill="x")
    ttk.Label(raw_top,text="Таймаут ответа, с:").pack(side="left")
    raw_timeout_var=tk.StringVar(value="2.5")
    ttk.Entry(raw_top,textvariable=raw_timeout_var,width=6).pack(side="left",padx=4)
    ttk.Label(raw_top,text="HEX допускает пробелы: 2F 3F 44 65 76 49 6E 66 6F 21 0D 0A",
              foreground="#777").pack(side="left",padx=8)
    raw_hex_text=scrolledtext.ScrolledText(raw_box,height=6,wrap="word",font=("TkFixedFont",10))
    raw_hex_text.pack(fill="both",expand=True,pady=4)
    raw_buttons=ttk.Frame(raw_box); raw_buttons.pack(fill="x")
    def raw_send():
        task_q.put({"op":"raw_hex","hex":raw_hex_text.get("1.0","end"),
                    "timeout":raw_timeout_var.get(), "expert":state["expert"]})
    ttk.Button(raw_buttons,text="Передать точные байты",command=raw_send).pack(side="left")
    ttk.Button(raw_buttons,text="DevInfo / IEC HEX",command=lambda:(
        raw_hex_text.delete("1.0","end"),
        raw_hex_text.insert("1.0","2F 3F 44 65 76 49 6E 66 6F 21 0D 0A"))).pack(side="left",padx=4)
    ttk.Button(raw_buttons,text="Очистить",command=lambda:raw_hex_text.delete("1.0","end")).pack(side="left")

    sms_box=ttk.LabelFrame(tab_terminal,text="GSM-модем / SMS",padding=6)
    sms_box.pack(fill="both",expand=True,pady=3)
    sms_top=ttk.Frame(sms_box); sms_top.pack(fill="x")
    at_var=tk.StringVar(value="AT+CSQ")
    ttk.Label(sms_top,text="AT:").pack(side="left")
    ttk.Entry(sms_top,textvariable=at_var,width=28).pack(side="left",padx=4)
    ttk.Button(sms_top,text="Выполнить AT",command=lambda:task_q.put(
        {"op":"modem_at","text":at_var.get()})).pack(side="left")
    sms_delete_var=tk.BooleanVar(value=False)
    ttk.Checkbutton(sms_top,text="удалить после чтения",variable=sms_delete_var).pack(side="left",padx=10)
    ttk.Button(sms_top,text="Получить непрочитанные SMS",command=lambda:task_q.put(
        {"op":"sms_receive","delete":sms_delete_var.get()})).pack(side="left")
    sms_text=scrolledtext.ScrolledText(sms_box,height=6,wrap="word",font=("TkFixedFont",9))
    sms_text.pack(fill="both",expand=True,pady=(4,0))

    # ── вкладка «Телеметрия»: ПРИЁМ + ОТПРАВКА (обе стороны) ─────────────
    state.setdefault("readings", {}); state.setdefault("tele_srv", None)

    ttk.Label(tab_tele, wraplength=1150, foreground="#555", justify="left",
              text="Телеметрия в обе стороны (GPRS/TCP). ПРИЁМ: слушать порт — поймать "
                   "сессию прибора, разобрать, ответить ACK. ОТПРАВКА: собрать пакет из "
                   "снятых показаний и реально отправить на host:port. + CRC16-скан и auth/MD5."
              ).pack(anchor="w")

    rxb = ttk.Frame(tab_tele); rxb.pack(fill="x", pady=(4, 0))
    ttk.Label(rxb, text="ПРИЁМ — порт:").pack(side="left")
    rx_port = tk.StringVar(value="40000")
    ttk.Entry(rxb, textvariable=rx_port, width=7).pack(side="left", padx=2)
    listen_status = ttk.Label(rxb, text="○ не слушаю", foreground="#777")

    def do_listen():
        if state.get("tele_srv"):
            return
        try:
            port = int(rx_port.get())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            append("err", "[приём] TCP-порт должен быть от 1 до 65535.")
            return
        s = TeleServer(port, out_q); state["tele_srv"] = s; s.start()
        listen_status.config(text=f"● слушаю :{port}", foreground="#0a7d0a")

    def do_stop():
        s = state.get("tele_srv")
        if s:
            s.stop(); state["tele_srv"] = None
        listen_status.config(text="○ не слушаю", foreground="#777")
    ttk.Button(rxb, text="Слушать", command=do_listen).pack(side="left", padx=(6, 2))
    ttk.Button(rxb, text="Стоп", command=do_stop).pack(side="left")
    listen_status.pack(side="left", padx=8)

    txb = ttk.Frame(tab_tele); txb.pack(fill="x", pady=(2, 0))
    ttk.Label(txb, text="ОТПРАВКА → host:").pack(side="left")
    tx_host = tk.StringVar(value="127.0.0.1")
    ttk.Entry(txb, textvariable=tx_host, width=14).pack(side="left", padx=2)
    ttk.Label(txb, text="порт:").pack(side="left")
    tx_port = tk.StringVar(value="40000")
    ttk.Entry(txb, textvariable=tx_port, width=7).pack(side="left", padx=2)

    def do_send():
        data = tele_in.get("1.0", "end").strip().encode("latin1", "replace")
        if not data:
            append("warn", "[отправка] пусто — сначала «Собрать пакет» или вставь пакет."); return
        try:
            tele_send(tx_host.get().strip(), int(tx_port.get()), data, out_q)
            append("ok", f"[отправка] отправляю {len(data)} байт → {tx_host.get()}:{tx_port.get()}")
        except ValueError:
            append("err", "[отправка] неверный порт.")
    ttk.Button(txb, text="Отправить", command=do_send).pack(side="left", padx=6)

    dab = ttk.Frame(tab_tele); dab.pack(fill="x", pady=(2, 4))

    def do_build():
        pkt = build_telemetry_packet(state.get("readings", {}))
        tele_in.delete("1.0", "end"); tele_in.insert("1.0", pkt)
        _tele_parse()
    ttk.Button(dab, text="Собрать пакет (из показаний)", command=do_build).pack(side="left")
    ttk.Button(dab, text="Снять по оптопорту",
               command=lambda: task_q.put({"op": "tele_read"})).pack(side="left", padx=6)

    def _tele_load():
        p = filedialog.askopenfilename(filetypes=[("session log", "*.log"), ("все", "*.*")])
        if p:
            tele_in.delete("1.0", "end")
            tele_in.insert("1.0", open(p, "rb").read().decode("latin1", "replace"))
    ttk.Button(dab, text="Загрузить .log…", command=_tele_load).pack(side="left")
    ttk.Button(dab, text="Разобрать", command=lambda: _tele_parse()).pack(side="left", padx=6)

    tele_in = scrolledtext.ScrolledText(tab_tele, height=4, wrap="none", font=("TkFixedFont", 9))
    tele_in.pack(fill="x")
    tpan = ttk.Panedwindow(tab_tele, orient="horizontal"); tpan.pack(fill="both", expand=True, pady=4)
    trf = ttk.Frame(tpan); tpan.add(trf, weight=3)
    ttk.Label(trf, text="Записи пакета:").pack(anchor="w")
    rec_cols = ("type", "dt", "acc", "val", "flag")
    rec_tree = ttk.Treeview(trf, columns=rec_cols, show="headings", height=8)
    for c, t, w in (("type", "Тип", 50), ("dt", "Дата/время", 155),
                    ("acc", "Накопитель ×10000", 140), ("val", "Значение", 90),
                    ("flag", "Флаг", 50)):
        rec_tree.heading(c, text=t); rec_tree.column(c, width=w, anchor="w")
    rsb = ttk.Scrollbar(trf, orient="vertical", command=rec_tree.yview)
    rec_tree.configure(yscrollcommand=rsb.set)
    rec_tree.pack(side="left", fill="both", expand=True); rsb.pack(side="left", fill="y")
    tsf = ttk.Frame(tpan); tpan.add(tsf, weight=2)
    ttk.Label(tsf, text="Заголовок · CRC16 · auth:").pack(anchor="w")
    tele_sum = scrolledtext.ScrolledText(tsf, wrap="word", font=("TkFixedFont", 9), height=8)
    tele_sum.pack(fill="both", expand=True)

    dbf = ttk.LabelFrame(tab_tele, text="Накопленная телеметрия · SQLite", padding=5)
    dbf.pack(fill="both", expand=True, pady=(2, 0))
    dbbar = ttk.Frame(dbf); dbbar.pack(fill="x")
    tele_db_info = ttk.Label(dbbar, text="—", foreground="#555")
    tele_db_info.pack(side="left")
    tele_anomaly_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(dbbar, text="только аномалии", variable=tele_anomaly_var,
                    command=lambda: refresh_telemetry_db()).pack(side="left", padx=8)
    tele_device_var = tk.StringVar(value="(все устройства)")
    tele_device_cb = ttk.Combobox(dbbar, textvariable=tele_device_var, state="readonly",
                                  width=20, values=["(все устройства)"])
    tele_device_cb.pack(side="left", padx=3)
    tele_device_cb.bind("<<ComboboxSelected>>", lambda _e: refresh_telemetry_db())
    ttk.Button(dbbar, text="Обновить", command=lambda: refresh_telemetry_db()).pack(side="left", padx=3)

    def export_telemetry_db():
        if tele_store_mod is None:
            messagebox.showerror("Телеметрия", "Модуль smt_telemetry_store.py не найден")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV", "*.csv")],
                                             initialfile="telemetry_history.csv")
        if not path:
            return
        try:
            count = tele_store_mod.export_csv(TELEMETRY_DB_PATH, path)
            append("ok", f"[телеметрия] экспортировано {count} записей → {path}")
        except Exception as exc:
            messagebox.showerror("Телеметрия", str(exc))
    ttk.Button(dbbar, text="Экспорт CSV…", command=export_telemetry_db).pack(side="left", padx=3)

    db_cols = ("rx", "device", "dt", "acc", "value", "flag", "anomaly", "ip")
    tele_db_tree = ttk.Treeview(dbf, columns=db_cols, show="headings", height=7)
    for c, title, width in (("rx", "Получено UTC", 145), ("device", "ID64", 135),
                            ("dt", "Время прибора", 145), ("acc", "Накопитель, м³", 120),
                            ("value", "Значение", 85), ("flag", "Флаг", 50),
                            ("anomaly", "Аномалия", 220), ("ip", "Источник", 105)):
        tele_db_tree.heading(c, text=title); tele_db_tree.column(c, width=width, anchor="w")
    tele_db_tree.tag_configure("bad", foreground="#c0392b")
    dbsb = ttk.Scrollbar(dbf, orient="vertical", command=tele_db_tree.yview)
    tele_db_tree.configure(yscrollcommand=dbsb.set)
    tele_db_tree.pack(side="left", fill="both", expand=True, pady=(4, 0))
    dbsb.pack(side="left", fill="y", pady=(4, 0))

    def refresh_telemetry_db():
        tele_db_tree.delete(*tele_db_tree.get_children())
        if tele_store_mod is None:
            tele_db_info.config(text="База недоступна: smt_telemetry_store.py не найден",
                                foreground="#c0392b")
            return
        try:
            stat = tele_store_mod.stats(TELEMETRY_DB_PATH)
            devices = tele_store_mod.devices(TELEMETRY_DB_PATH)
            selected = tele_device_var.get()
            values = ["(все устройства)"] + devices
            tele_device_cb.config(values=values)
            if selected not in values:
                tele_device_var.set("(все устройства)")
                selected = "(все устройства)"
            rows = tele_store_mod.recent_records(
                TELEMETRY_DB_PATH, 1000, anomalies_only=tele_anomaly_var.get(),
                id64="" if selected == "(все устройства)" else selected)
            for r in rows:
                anomaly = r.get("anomaly", "")
                tele_db_tree.insert("", "end", values=(
                    r.get("received_utc", ""), r.get("id64", ""),
                    r.get("device_datetime", ""),
                    "" if r.get("accumulator_m3") is None else f"{r['accumulator_m3']:.4f}",
                    r.get("value", ""), r.get("flag", ""), anomaly, r.get("source_ip", "")),
                    tags=("bad",) if anomaly else ())
            tele_db_info.config(
                text=(f"Пакетов: {stat['packets']} · записей: {stat['records']} · "
                      f"устройств: {stat['devices']} · аномалий: {stat['anomalies']} · "
                      f"показано: {len(rows)}"),
                foreground="#c0392b" if stat["anomalies"] else "#0a7d0a")
        except Exception as exc:
            tele_db_info.config(text=f"Ошибка базы: {exc}", foreground="#c0392b")

    refresh_telemetry_db()

    def _tele_render(rep):
        rec_tree.delete(*rec_tree.get_children())
        tele_sum.delete("1.0", "end")
        for r in rep.get("records", []):
            rec_tree.insert("", "end", values=(r["type"], r["dt"], r["accumulator"],
                                               r["value"], r["flag"]))
        h = rep.get("header")
        if h:
            tele_sum.insert("end", f"Заголовок:\n  имя = {h['name']}\n"
                                   f"  CRC16 (3 поля) = {', '.join(h['crc16'])}\n"
                                   f"  ID64 = {h['id64']}\n\nCRC16-скан:\n")
            for c in h["crc16"]:
                hits = srv.crc16_scan(rep["text"], c) if srv else []
                s = ", ".join(f"{x['variant']}[{x['window'][0]}:{x['window'][1]}]"
                              for x in hits) or "нет совпадений"
                tele_sum.insert("end", f"  {c}: {s}\n")
        else:
            tele_sum.insert("end", "Заголовок не распознан (проверь формат кадра).\n")
        tele_sum.insert("end", f"\nГрупп: {len(rep.get('groups', []))}, "
                               f"записей: {len(rep.get('records', []))}\n")
        if rep.get("auth"):
            tele_sum.insert("end", f"\nauth = {rep['auth']}\n")
            for a in (srv.auth_check(rep["text"], rep["auth"]) if srv else []):
                mark = " ✓ совпало" if a["match"] else ""
                tele_sum.insert("end", f"  MD5({a['input']}) = {a['md5']}{mark}\n")

    def _tele_parse():
        if srv is None:
            tele_sum.delete("1.0", "end")
            tele_sum.insert("end", "Модуль разбора smt_server.py не найден рядом с GUI.")
            return
        raw = tele_in.get("1.0", "end").strip().encode("latin1", "replace")
        if not raw:
            rec_tree.delete(*rec_tree.get_children()); tele_sum.delete("1.0", "end")
            tele_sum.insert("end", "Пусто. Собери пакет («Собрать пакет») или загрузи session_*.log.")
            return
        _tele_render(srv.parse_frame(raw))

    # ── вкладка «История»: разбор физического flash-дампа ─────────────────
    ttk.Label(tab_hist, wraplength=1150, foreground="#555", justify="left",
              text="История показывает только реальные данные прибора из дампа W25Q64: "
                   "чекпоинт 0x7FE000/0x7FC000, главный архив до 0x128000 и аудит 0x15E000. "
                   "Provider-запись показаний не очищает архив автоматически. CLEAR_ARHIVE "
                   "доступна отдельной подтверждаемой операцией; локальный журнал корректировок не ведётся."
              ).pack(anchor="w")
    hctl = ttk.Frame(tab_hist); hctl.pack(fill="x", pady=4)
    ttk.Button(hctl, text="Загрузить дамп…", command=lambda: hist_load()).pack(side="left")
    ttk.Button(hctl, text="Экспорт разбора CSV…", command=lambda: hist_export()).pack(side="left", padx=4)
    hist_path = ttk.Label(hctl, text="дамп не загружен", foreground="#777")
    hist_path.pack(side="left", padx=8)

    hpan = ttk.Panedwindow(tab_hist, orient="vertical"); hpan.pack(fill="both", expand=True)

    cpf = ttk.Labelframe(hpan, text="История показаний — чекпоинт", padding=4); hpan.add(cpf, weight=1)
    cp_info = ttk.Label(cpf, text="—", foreground="#555"); cp_info.pack(anchor="w")
    cp_tree = ttk.Treeview(cpf, columns=("idx", "dt", "vol", "t1", "t2", "ok"),
                           show="headings", height=6)
    for c, t, w in (("idx", "#", 50), ("dt", "Время (UTC)", 150), ("vol", "Показания, м³", 140),
                    ("t1", "t1 °C", 70), ("t2", "t2 °C", 70), ("ok", "Целостн.", 80)):
        cp_tree.heading(c, text=t); cp_tree.column(c, width=w, anchor="w")
    cp_tree.tag_configure("bad", foreground="#c0392b")
    cpsb = ttk.Scrollbar(cpf, orient="vertical", command=cp_tree.yview)
    cp_tree.configure(yscrollcommand=cpsb.set)
    cp_tree.pack(side="left", fill="both", expand=True); cpsb.pack(side="left", fill="y")

    evf = ttk.Labelframe(hpan, text="Журнал событий / аудит", padding=4); hpan.add(evf, weight=1)
    ev_info = ttk.Label(evf, text="—", foreground="#555"); ev_info.pack(anchor="w")
    ev_tree = ttk.Treeview(evf, columns=("cnt", "dt", "code", "val", "note"),
                           show="headings", height=6)
    for c, t, w in (("cnt", "#", 50), ("dt", "Время (UTC)", 150), ("code", "Код", 70),
                    ("val", "Значение", 150), ("note", "Что это", 320)):
        ev_tree.heading(c, text=t); ev_tree.column(c, width=w, anchor="w")
    evsb = ttk.Scrollbar(evf, orient="vertical", command=ev_tree.yview)
    ev_tree.configure(yscrollcommand=evsb.set)
    ev_tree.pack(side="left", fill="both", expand=True); evsb.pack(side="left", fill="y")

    arf = ttk.Labelframe(hpan, text="Главный архив измерений", padding=4); hpan.add(arf, weight=1)
    ar_head = ttk.Frame(arf); ar_head.pack(fill="x")
    ar_info = ttk.Label(ar_head, text="—", foreground="#555"); ar_info.pack(side="left")
    ar_anomaly_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(ar_head, text="только аномалии", variable=ar_anomaly_var,
                    command=lambda: refresh_archive_tree()).pack(side="right")
    ar_tree = ttk.Treeview(arf, columns=("idx", "dt", "vol", "t1", "t2", "integrity", "anomaly"),
                           show="headings", height=6)
    for c, t, w in (("idx", "#", 55), ("dt", "Время (UTC)", 155),
                    ("vol", "Показания, м³", 125), ("t1", "t1 °C", 70),
                    ("t2", "t2 °C", 70), ("integrity", "Копия", 70),
                    ("anomaly", "Аномалия", 250)):
        ar_tree.heading(c, text=t); ar_tree.column(c, width=w, anchor="w")
    ar_tree.tag_configure("bad", foreground="#c0392b")
    arsb = ttk.Scrollbar(arf, orient="vertical", command=ar_tree.yview)
    ar_tree.configure(yscrollcommand=arsb.set)
    ar_tree.pack(side="left", fill="both", expand=True); arsb.pack(side="left", fill="y")
    state["history_checkpoint"] = []; state["history_archive"] = []; state["history_events"] = []
    state["history_archive_summary"] = {}

    def refresh_archive_tree():
        ar_tree.delete(*ar_tree.get_children())
        rows = state.get("history_archive", [])
        if ar_anomaly_var.get():
            rows = [r for r in rows if r.get("anomaly")]
        visible = rows[-2000:]
        for r in visible:
            dt = r["datetime"].strftime("%Y-%m-%d %H:%M:%S") if r.get("datetime") else "—"
            anomaly = r.get("anomaly", "")
            ar_tree.insert("", "end", values=(r.get("index", ""), dt,
                                               f"{r.get('volume', 0):.6f}",
                                               f"{r.get('temp1', 0):.2f}",
                                               f"{r.get('temp2', 0):.2f}",
                                               "да" if r.get("integrity_ok", True) else "НЕТ",
                                               anomaly),
                           tags=("bad",) if anomaly else ())
        summary = state.get("history_archive_summary", {})
        if summary:
            ar_info.config(text=(f"Записей: {summary.get('count',0)} · Δ={summary.get('delta_volume',0):.6f} м³ · "
                                 f"аномалий: {summary.get('anomalies',0)} · показано: {len(visible)}"),
                           foreground="#c0392b" if summary.get("anomalies") else "#0a7d0a")

    def hist_fill(data):
        cp_tree.delete(*cp_tree.get_children()); ev_tree.delete(*ev_tree.get_children())
        ar_tree.delete(*ar_tree.get_children())
        if state_mod:
            try:
                base, recs = state_mod.parse_dump(data)
                for r in recs:
                    t = r['datetime'].strftime('%Y-%m-%d %H:%M') if r['datetime'] else '—'
                    ok = r['valid'] and abs(r['volume'] - r['volume_copy']) < 1e-9
                    cp_tree.insert("", "end",
                                   values=(r['index'], t, f"{r['volume']:.6f}",
                                           f"{r['temp1']:.2f}", f"{r['temp2']:.2f}",
                                           "да" if ok else "НЕТ"),
                                   tags=() if ok else ("bad",))
                state["history_checkpoint"] = recs
                cp_info.config(text=f"Активная половина 0x{base:06X} · записей: {len(recs)}")
            except Exception as e:
                cp_info.config(text=f"Чекпоинт не найден в дампе: {e}")
        if evlog_mod:
            try:
                seen = evlog_mod.parse(data)
                for cnt, (t, code, txt) in sorted(seen.items()):
                    dt = datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S')
                    note = evlog_mod.KNOWN.get(txt) or evlog_mod.CODE_NAMES.get(code, "")
                    ev_tree.insert("", "end", values=(cnt, dt, f"0x{code:04X}", txt, note))
                state["history_events"] = sorted(seen.items())
                ev_info.config(text=f"Журнал 0x15E000 · записей: {len(seen)}")
            except Exception as e:
                ev_info.config(text=f"Журнал не разобран: {e}")
        if state_mod:
            try:
                archive = state_mod.parse_archive(data)
                archive, summary = state_mod.analyse_timeline(archive)
                state["history_archive"] = archive
                state["history_archive_summary"] = summary
                refresh_archive_tree()
            except Exception as e:
                ar_info.config(text=f"Главный архив не разобран: {e}")

    def hist_load_path(p):
        try:
            data = open(p, "rb").read()
        except Exception as e:
            hist_path.config(text=f"ошибка: {e}"); return
        hist_path.config(text=f"{os.path.basename(p)} · {len(data)} байт")
        hist_fill(data)

    def hist_load():
        p = filedialog.askopenfilename(filetypes=[("dump W25Q64", "*.bin"), ("все", "*.*")])
        if p:
            hist_load_path(p)

    def hist_export():
        if not (state.get("history_checkpoint") or state.get("history_archive") or
                state.get("history_events")):
            append("warn", "[история] нет данных для экспорта."); return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                         initialfile="history_export.csv")
        if not p:
            return
        with open(p, "w", encoding="utf-8-sig", newline="") as stream:
            w = csv.writer(stream)
            w.writerow(["section", "index", "datetime_utc", "value", "temp1", "temp2", "code", "note"])
            for r in state.get("history_checkpoint", []):
                dt = r["datetime"].isoformat(sep=" ") if r.get("datetime") else ""
                ok = r.get("valid") and abs(r.get("volume", 0) - r.get("volume_copy", 0)) < 1e-9
                w.writerow(["checkpoint", r.get("index"), dt, r.get("volume"),
                            r.get("temp1"), r.get("temp2"), "", "integrity=ok" if ok else "integrity=bad"])
            for r in state.get("history_archive", []):
                dt = r["datetime"].isoformat(sep=" ") if r.get("datetime") else ""
                w.writerow(["archive", r.get("index"), dt, r.get("volume"),
                            r.get("temp1"), r.get("temp2"), "", ""])
            for cnt, (ts, code, txt) in state.get("history_events", []):
                dt = datetime.datetime.utcfromtimestamp(ts).isoformat(sep=" ")
                note = (evlog_mod.KNOWN.get(txt) or evlog_mod.CODE_NAMES.get(code, "")) if evlog_mod else ""
                w.writerow(["event", cnt, dt, txt, "", "", f"0x{code:04X}", note])
        append("ok", f"[история] экспортировано → {p}")

    # ── вкладка «Снимки · сценарии · мониторинг» ───────────────────────
    ttk.Label(tab_lab, wraplength=1160, foreground="#555", justify="left",
              text="Инженерная работа с реальным прибором: полный READ-аудит каталога, "
                   "экспорт и сравнение снимков, проверяемые пакетные сценарии и "
                   "периодический мониторинг параметров по активному физическому каналу."
              ).pack(anchor="w")

    lab_pan = ttk.Panedwindow(tab_lab, orient="horizontal"); lab_pan.pack(fill="both", expand=True, pady=4)
    snap_frame = ttk.Labelframe(lab_pan, text="Снимок всех 158 команд", padding=5)
    lab_pan.add(snap_frame, weight=3)
    work_frame = ttk.Frame(lab_pan, padding=(5, 0, 0, 0)); lab_pan.add(work_frame, weight=2)

    snap_bar = ttk.Frame(snap_frame); snap_bar.pack(fill="x")
    scan_btn = ttk.Button(snap_bar, text="Аудит всех 158 команд",
                          command=lambda: task_q.put({"op": "scan_all"}))
    scan_btn.pack(side="left")
    ttk.Button(snap_bar, text="Стоп", command=backend.cancel_current).pack(side="left", padx=3)
    scan_var = tk.DoubleVar(value=0)
    scan_progress = ttk.Progressbar(snap_bar, variable=scan_var, maximum=max(1, len(catalog)))
    scan_progress.pack(side="left", fill="x", expand=True, padx=6)
    scan_label = ttk.Label(snap_bar, text="0/158"); scan_label.pack(side="left")

    snap_cols = ("name", "current", "reference", "status")
    snap_tree = ttk.Treeview(snap_frame, columns=snap_cols, show="headings", height=16)
    for c, t, w in (("name", "Команда", 170), ("current", "Текущий снимок", 180),
                    ("reference", "Эталон / загруженный", 180), ("status", "Сравнение", 90)):
        snap_tree.heading(c, text=t); snap_tree.column(c, width=w, anchor="w")
    snap_tree.tag_configure("changed", foreground="#c0392b")
    snap_tree.tag_configure("same", foreground="#0a7d0a")
    snap_tree.tag_configure("error", foreground="#b00")
    snap_sb = ttk.Scrollbar(snap_frame, orient="vertical", command=snap_tree.yview)
    snap_tree.configure(yscrollcommand=snap_sb.set)
    snap_tree.pack(side="left", fill="both", expand=True, pady=5); snap_sb.pack(side="left", fill="y", pady=5)

    snap_actions = ttk.Frame(snap_frame); snap_actions.pack(fill="x", side="bottom")
    loaded_lbl = ttk.Label(snap_actions, text="эталон не загружен", foreground="#777")
    loaded_lbl.pack(side="left")

    def refresh_snapshot_tree():
        snap_tree.delete(*snap_tree.get_children())
        current = state.get("current_snapshot", {})
        reference = state.get("loaded_snapshot", {})
        names = sorted(set(current) | set(reference))
        for name in names:
            a = current.get(name, "<нет>"); b = reference.get(name, "<нет>")
            if not reference:
                status = "—"; tags = ("error",) if str(a).startswith("<err:") else ()
            elif str(a) == str(b):
                status = "совпадает"; tags = ("same",)
            else:
                status = "ИЗМЕНЕНО"; tags = ("changed",)
            snap_tree.insert("", "end", values=(name, a, b if reference else "", status), tags=tags)

    def save_snapshot(ext):
        values = state.get("current_snapshot", {})
        if not values:
            append("warn", "[снимок] сначала выполни полный опрос."); return
        if tools_mod is None:
            append("err", "[снимок] smt_tools.py не найден."); return
        p = filedialog.asksaveasfilename(defaultextension=ext,
                                         filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
                                         initialfile=f"snapshot_{datetime.datetime.now():%Y%m%d_%H%M%S}{ext}")
        if not p:
            return
        if p.lower().endswith(".csv"):
            tools_mod.save_snapshot_csv(p, values)
        else:
            tools_mod.save_snapshot_json(p, values, source=state.get("mode", "unknown"),
                                         meta={"catalog_count": len(catalog)})
        append("ok", f"[снимок] сохранено {len(values)} параметров → {p}")

    def load_reference():
        if tools_mod is None:
            append("err", "[снимок] smt_tools.py не найден."); return
        p = filedialog.askopenfilename(filetypes=[("Снимки", "*.json *.csv"), ("все", "*.*")])
        if not p:
            return
        try:
            state["loaded_snapshot"] = tools_mod.load_snapshot(p)
            loaded_lbl.config(text=f"эталон: {os.path.basename(p)} · {len(state['loaded_snapshot'])}")
            refresh_snapshot_tree()
            append("ok", f"[снимок] загружен эталон: {p}")
        except Exception as exc:
            append("err", f"[снимок] ошибка загрузки: {exc}")

    ttk.Button(snap_actions, text="Экспорт JSON…", command=lambda: save_snapshot(".json")).pack(side="right")
    ttk.Button(snap_actions, text="Экспорт CSV…", command=lambda: save_snapshot(".csv")).pack(side="right", padx=3)
    ttk.Button(snap_actions, text="Загрузить эталон…", command=load_reference).pack(side="right", padx=3)

    # Пакетные сценарии
    batch_frame = ttk.Labelframe(work_frame, text="Пакетный сценарий", padding=5)
    batch_frame.pack(fill="both", expand=True)
    batch_text = scrolledtext.ScrolledText(batch_frame, height=11, wrap="none", font=("TkFixedFont", 9))
    batch_text.pack(fill="both", expand=True)
    batch_text.insert("1.0", """# Пример сценария работы с прибором
READ DevInfo
READ DEVICE_SN
READ STATUS_SYSTEM
READ Volume
SLEEP 250
SET LCD_TIME=15
READ LCD_TIME
# Критические ACTION/SET выполняются только в Экспертном режиме
""")
    batch_status = ttk.Label(batch_frame, text="готов", foreground="#555"); batch_status.pack(anchor="w")
    batch_bar = ttk.Frame(batch_frame); batch_bar.pack(fill="x")
    ttk.Button(batch_bar, text="Проверить", command=lambda: task_q.put(
        {"op": "batch", "text": batch_text.get("1.0", "end"), "expert": state["expert"],
         "dry_run": True})).pack(side="left")
    ttk.Button(batch_bar, text="Выполнить", command=lambda: task_q.put(
        {"op": "batch", "text": batch_text.get("1.0", "end"), "expert": state["expert"],
         "dry_run": False})).pack(side="left", padx=3)
    ttk.Button(batch_bar, text="Стоп", command=backend.cancel_current).pack(side="left")

    def batch_load():
        p = filedialog.askopenfilename(filetypes=[("SMT script", "*.smt *.txt"), ("все", "*.*")])
        if p:
            batch_text.delete("1.0", "end"); batch_text.insert("1.0", open(p, encoding="utf-8").read())
    def batch_save():
        p = filedialog.asksaveasfilename(defaultextension=".smt", filetypes=[("SMT script", "*.smt")])
        if p:
            open(p, "w", encoding="utf-8").write(batch_text.get("1.0", "end"))
    ttk.Button(batch_bar, text="Открыть…", command=batch_load).pack(side="right")
    ttk.Button(batch_bar, text="Сохранить…", command=batch_save).pack(side="right", padx=3)

    # Мониторинг
    mon_frame = ttk.Labelframe(work_frame, text="Периодический мониторинг", padding=5)
    mon_frame.pack(fill="both", expand=True, pady=(6, 0))
    mon_ctl = ttk.Frame(mon_frame); mon_ctl.pack(fill="x")
    mon_names_var = tk.StringVar(value="Volume,VOLUME_INST,STATUS_SYSTEM,STATUS_ALARM")
    ttk.Entry(mon_ctl, textvariable=mon_names_var).pack(side="left", fill="x", expand=True)
    ttk.Label(mon_ctl, text="интервал, с:").pack(side="left", padx=(5, 1))
    mon_interval_var = tk.StringVar(value="2")
    ttk.Entry(mon_ctl, textvariable=mon_interval_var, width=5).pack(side="left")
    mon_status = ttk.Label(mon_ctl, text="○", foreground="#777"); mon_status.pack(side="left", padx=4)

    mon_tree = ttk.Treeview(mon_frame, columns=("ts", "name", "value"), show="headings", height=7)
    for c, t, w in (("ts", "Время", 145), ("name", "Параметр", 140), ("value", "Значение", 170)):
        mon_tree.heading(c, text=t); mon_tree.column(c, width=w, anchor="w")
    mon_tree.pack(fill="both", expand=True, pady=4)

    def monitor_tick():
        if not state.get("monitoring"):
            return
        for name in state.get("monitor_names", []):
            task_q.put({"op": "read", "name": name})
        try:
            ms = max(250, int(float(mon_interval_var.get().replace(",", ".")) * 1000))
        except ValueError:
            ms = 2000
        state["monitor_after"] = root.after(ms, monitor_tick)

    def monitor_start():
        names = [x.strip() for x in mon_names_var.get().replace(";", ",").split(",") if x.strip()]
        if not names:
            append("warn", "[мониторинг] укажи хотя бы один параметр."); return
        bad = [name for name in names if name in actions]
        if bad:
            append("err", "[мониторинг] действия нельзя опрашивать циклически: " + ", ".join(bad)); return
        state["monitor_names"] = names; state["monitoring"] = True
        mon_status.config(text="●", foreground="#0a7d0a")
        monitor_tick()

    def monitor_stop():
        state["monitoring"] = False; mon_status.config(text="○", foreground="#777")
        aid = state.pop("monitor_after", None)
        if aid:
            try: root.after_cancel(aid)
            except Exception: pass

    def monitor_export():
        if not state.get("monitor_rows"):
            append("warn", "[мониторинг] данных пока нет."); return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if p:
            with open(p, "w", encoding="utf-8-sig", newline="") as stream:
                w = csv.writer(stream); w.writerow(["timestamp", "command", "value"])
                w.writerows(state["monitor_rows"])
            append("ok", f"[мониторинг] экспорт → {p}")

    mon_buttons = ttk.Frame(mon_frame); mon_buttons.pack(fill="x")
    ttk.Button(mon_buttons, text="Старт", command=monitor_start).pack(side="left")
    ttk.Button(mon_buttons, text="Стоп", command=monitor_stop).pack(side="left", padx=3)
    ttk.Button(mon_buttons, text="Экспорт CSV…", command=monitor_export).pack(side="right")
    ttk.Button(mon_buttons, text="Очистить", command=lambda: (
        mon_tree.delete(*mon_tree.get_children()), state["monitor_rows"].clear())).pack(side="right", padx=3)

    # ── лог: вкладки «Журнал» и «Сырые байты (hex)» ─────────────────────
    nb = ttk.Notebook(root); nb.pack(fill="both", expand=False)
    tab_log = ttk.Frame(nb, padding=2); nb.add(tab_log, text="Журнал сессии")
    log = scrolledtext.ScrolledText(tab_log, height=12, wrap="word", font=("TkFixedFont", 9))
    log.pack(fill="both", expand=True)
    for tag, col in (("ok", "#0a7d0a"), ("err", "#b00"), ("warn", "#c47f00")):
        log.tag_configure(tag, foreground=col)

    tab_hex = ttk.Frame(nb, padding=2)
    nb.add(tab_hex, text="Сырые байты (hex) — для сверки кадра/CRC")
    hexlog = scrolledtext.ScrolledText(tab_hex, height=12, wrap="none", font=("TkFixedFont", 9))
    hexlog.pack(fill="both", expand=True)
    hexlog.tag_configure("tx", foreground="#0a5"); hexlog.tag_configure("rx", foreground="#05a")

    logbar = ttk.Frame(root); logbar.pack(fill="x")
    def save_log():
        p = filedialog.asksaveasfilename(defaultextension=".txt",
                                         initialfile=f"session_{datetime.date.today()}.txt")
        if p:
            open(p, "w", encoding="utf-8").write(log.get("1.0", "end"))
    def save_hex():
        p = filedialog.asksaveasfilename(defaultextension=".txt",
                                         initialfile=f"hex_{datetime.date.today()}.txt")
        if p:
            open(p, "w", encoding="utf-8").write(hexlog.get("1.0", "end"))
    ttk.Button(logbar, text="Сохранить лог…", command=save_log).pack(side="right")
    ttk.Button(logbar, text="Сохранить hex…", command=save_hex).pack(side="right", padx=6)
    ttk.Button(logbar, text="Очистить", command=lambda: (log.delete("1.0", "end"),
               hexlog.delete("1.0", "end"))).pack(side="right")

    def append(tag, text):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        log.insert("end", f"[{ts}] ", "io")
        log.insert("end", text + "\n", tag if tag in ("ok", "err", "warn") else "io")
        log.see("end")

    def append_hex(text):
        tag = "tx" if text.startswith("TX") else "rx" if text.startswith("RX") else ""
        hexlog.insert("end", text + "\n", tag)
        hexlog.see("end")

    # ── насос очереди результатов ───────────────────────────────────────
    def pump():
        try:
            while True:
                kind, payload = out_q.get_nowait()
                if kind == "log":
                    append(*payload)
                elif kind == "hex":
                    append_hex(payload)
                elif kind == "reading":
                    name, value, ts = payload
                    if state.get("monitoring") and name in state.get("monitor_names", []):
                        row = (ts, name, value)
                        state["monitor_rows"].append(row)
                        mon_tree.insert("", 0, values=row)
                        while len(mon_tree.get_children()) > 500:
                            mon_tree.delete(mon_tree.get_children()[-1])
                elif kind == "scan_progress":
                    index, total, name, value = payload
                    scan_var.set(index)
                    scan_label.config(text=f"{index}/{total} · {name}")
                elif kind == "snapshot":
                    values, mode = payload
                    state["current_snapshot"] = values
                    state["mode"] = mode
                    refresh_snapshot_tree()
                    main_nb.select(tab_lab)
                elif kind == "batch_progress":
                    index, total, source = payload
                    batch_status.config(text=f"{index}/{total}: {source}")
                elif kind == "batch_done":
                    ok, done, message = payload
                    batch_status.config(text=f"{message} · шагов {done}",
                                        foreground="#0a7d0a" if ok else "#c47f00")
                elif kind == "reading_write_done":
                    state.setdefault("readings", {})[payload.get("command", "Volume")] = payload.get("new_value", "")
                    append("ok", "[Provider] показание записано и подтверждено read-back; "
                                 "измерительный архив не очищался.")
                elif kind == "archive_clear_done":
                    main_nb.select(tab_hist)
                    append("ok", "[Provider] CLEAR_ARHIVE подтверждена: ArcNumRecords=0.")
                elif kind == "auth_state":
                    verified = bool(payload.get("verified")) and payload.get("level") == "provider"
                    state["provider_verified"] = verified
                    state["provider_verified_at"] = payload.get("verified_at", 0.0)
                    if verified:
                        level_var.set("Провайдер (П)")
                        auth_lbl.config(text="● Provider подтверждён (15 мин)", foreground="#0a7d0a")
                    else:
                        level_var.set("Гость")
                        auth_lbl.config(text="○ Provider не подтверждён", foreground="#777")
                elif kind == "tele_log":
                    append(*payload)
                elif kind == "tele_reading":
                    state["readings"] = payload
                    append("ok", "[тел] показания сняты — можно «Собрать пакет».")
                elif kind == "tele_rx":
                    raw, rep, ip, n = payload
                    tele_in.delete("1.0", "end"); tele_in.insert("1.0", raw)
                    _tele_render(rep)
                    refresh_telemetry_db()
                    main_nb.select(tab_tele)
                    append("ok", f"[приём] пакет от {ip}: {n} записей → ACK DATA ACCEPT:{n}")
                elif kind == "tele_state":
                    if payload == "off":
                        state["tele_srv"] = None
                        listen_status.config(text="○ не слушаю", foreground="#777")
                elif kind == "session_file":
                    state["session_file"] = payload
                elif kind == "password":
                    cred, value = payload
                    pw_var.set(value)
                    if cred in AUTH_CREDS:
                        cred_var.set(cred)
                    append("ok", f"[auto] Значение из {cred} подставлено в поле "
                                 "аутентификации (в журнале скрыто).")
                elif kind == "raw_result":
                    raw = payload
                    append("ok", f"[RAW] получено {len(raw)} байт")
                    main_nb.select(tab_terminal)
                elif kind == "sms_messages":
                    sms_text.delete("1.0", "end")
                    for item in payload:
                        sms_text.insert("end", f"#{item.get('index')} {item.get('header')}\n{item.get('text')}\n\n")
                    if not payload:
                        sms_text.insert("end", "Непрочитанных SMS нет.")
                    main_nb.select(tab_terminal)
                elif kind == "status":
                    st, endpoint = payload
                    state["connected"] = st in ("serial", "tcp", "sms")
                    state["mode"] = st if state["connected"] else "off"
                    if state["connected"]:
                        names={"serial":"ОПТОПОРТ","tcp":"TCP","sms":"GSM/SMS"}
                        status_lbl.config(text=f"● {names.get(st,st)} {endpoint}", foreground="#0a7d0a")
                        conn_btn.config(text="Отключить")
                        transport_cb.state(["disabled"])
                    else:
                        state["provider_verified"] = False
                        state["provider_verified_at"] = 0.0
                        auth_lbl.config(text="○ Provider не подтверждён", foreground="#777")
                        level_var.set("Гость")
                        status_lbl.config(text="● отключено", foreground="#b00")
                        conn_btn.config(text="Подключить")
                        transport_cb.state(["!disabled"])
                        update_transport_fields()
        except queue.Empty:
            pass
        root.after(80, pump)

    # ── меню «Сессия»: экспорт журнала работы с прибором ──
    def _open_sessions_folder():
        folder = os.path.join(HERE, "sessions")
        os.makedirs(folder, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}" >/dev/null 2>&1 &')
        except Exception:
            append("warn", f"[сессия] папка журналов: {folder}")

    def _export_session_csv():
        if not state.get("session_file"):
            append("warn", "[сессия] нет активной сессии — сначала подключись к прибору.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            title="Экспорт сессии в CSV")
        if path:
            task_q.put({"op": "export_session", "path": path})

    try:
        menubar = tk.Menu(root)
        sess_menu = tk.Menu(menubar, tearoff=0)
        sess_menu.add_command(label="Экспорт сессии в CSV…", command=_export_session_csv)
        sess_menu.add_command(label="Открыть папку sessions", command=_open_sessions_folder)
        menubar.add_cascade(label="Сессия", menu=sess_menu)
        root.config(menu=menubar)
    except Exception:
        pass

    refill()
    root.after(80, pump)

    def on_close():
        state["monitoring"] = False
        aid = state.pop("monitor_after", None)
        if aid:
            try:
                root.after_cancel(aid)
            except Exception:
                pass
        s = state.get("tele_srv")
        if s:
            s.stop()
        task_q.put({"op": "quit"})
        root.after(150, root.destroy)
    root.protocol("WM_DELETE_WINDOW", on_close)

    return {"root": root, "task_q": task_q, "log": log, "state": state}


def run_selftest(port):
    """Headless read-only проверка физического порта через Backend."""
    import tkinter as tk
    root = tk.Tk(); root.withdraw()
    app = build_app(root, selftest=True)
    task_q = app["task_q"]
    steps = [
        {"op": "connect", "transport": "serial", "port": port, "baud": 9600,
         "framing": "auto", "bytesize": 8, "parity": "N", "stopbits": 1},
        {"op": "preflight"},
        {"op": "read", "name": "DEVICE_SN"},
        {"op": "read", "name": "VER_PO"},
        {"op": "read", "name": "STATUS_SYSTEM"},
    ]
    for index, task in enumerate(steps):
        root.after(200 + index * 900, lambda task=task: task_q.put(task))

    def finish():
        print("===== PHYSICAL READ-ONLY SELFTEST =====")
        print(app["log"].get("1.0", "end").rstrip())
        print("===== catalog:", len(load_catalog()), "команд =====")
        task_q.put({"op": "quit"})
        root.after(150, root.quit)

    root.after(9000, finish)
    root.mainloop()
    try:
        root.destroy()
    except Exception:
        pass


def main():
    if "--selftest" in sys.argv:
        run_selftest(sys.argv[sys.argv.index("--selftest") + 1]); return
    try:
        import tkinter as tk
    except Exception as e:
        sys.exit(f"Нужен tkinter (напр. пакет python3-tk): {e}")
    root = tk.Tk()
    build_app(root)
    root.mainloop()


if __name__ == "__main__":
    main()
