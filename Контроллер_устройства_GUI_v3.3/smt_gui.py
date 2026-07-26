#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smt_gui — графический клиент физического прибора через оптопорт.

Интерфейс v3 сохранён. Обмен выполняется только с реальным serial-портом:
без демонстрационного режима и без эмуляции прибора. Транспорт автоматически
определяет кадрирование безопасной командой чтения, снимает оптическое эхо,
собирает фрагментированный ответ UART и фиксирует фактические TX/RX-байты.

Запуск:
    python3 smt_gui.py
Требования: Python 3 с tkinter + pyserial (pip install pyserial).
"""
import os, sys, json, time, threading, queue, datetime, socket, hashlib

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
    import smt_aliases as al         # обезличенные имена CMD_### для отображения
except Exception:
    al = None

def disp(name):
    """Показываемое имя команды: CMD_### если доступны алиасы, иначе как есть."""
    return al.to_display(name) if al else name

def disp_cmd(text):
    """Заменить ведущее имя в строке команды на алиас для показа (значение/хвост
    сохраняются). Реальный провод формируется отдельно и остаётся настоящим."""
    import re as _re
    m = _re.match(r"^(\s*[{}/?!]*\s*)([A-Za-z0-9_]+)(.*)$", str(text), _re.S)
    if not m:
        return text
    pre, tok, rest = m.groups()
    return pre + disp(tok) + rest
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


def build_telemetry_packet(readings):
    """Собрать РЕАЛЬНЫЙ телеметрический пакет из снятых показаний (не демо):
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
            n = len(rep.get("records", []))
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
        cmds = json.load(f)["commands"]
    for c in cmds:                      # видимое (обезличенное) имя; реальное — в c["name"]
        c["display"] = disp(c["name"])
    return cmds


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
    """Какие операции валидны для команды по её назначению: (read, write, action)."""
    read = True                       # прочитать можно любую (прибор решит)
    write = not is_action             # значение пишется у всех, кроме чистых действий
    return read, write, is_action


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
    """Единственный поток, владеющий физическим serial-портом."""
    def __init__(self, task_q, out_q, critical=None, actions=None, catalog=None):
        super().__init__(daemon=True)
        self.task_q, self.out_q = task_q, out_q
        self.cli = None
        self.critical = critical or set()
        self.actions = actions or set()
        self.catalog = catalog or []
        self._echo_noted = False
        self.recorder = None

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
                elif op == "send":
                    self._send(task["text"], task.get("expert", False))
                elif op == "auth":
                    self._auth(task["cred"], task["value"])
                elif op == "passport":
                    self._passport()
                elif op == "readall":
                    self._readall()
                elif op == "groupread":
                    self._groupread(task.get("group"))
                elif op == "authscan":
                    self._authscan()
                elif op == "tele_read":
                    self._tele_read()
                elif op == "preflight":
                    self._preflight()
                elif op == "export_session":
                    self._export_session(task.get("path"))
            except Exception as exc:
                self.log("err", f"[FAIL] {op}: {exc}")
                if op == "connect" or isinstance(exc, getattr(sc, "TransportError", OSError)):
                    self._close()
                    self.post("status", ("off", ""))

    def _wire_log(self):
        tr = self.cli.t
        self.post("hex", hexdump("TX", getattr(tr, "last_tx", b"")))
        # В hex показываются именно байты на проводе, включая оптическое эхо.
        self.post("hex", hexdump("RX", getattr(tr, "last_raw_rx", b"") or b""))
        if getattr(tr, "last_echo_removed", False) and not self._echo_noted:
            self._echo_noted = True
            self.log("ok", "[линия] Обнаружено само-эхо оптоголовки; оно автоматически "
                           "удаляется только из разбираемого ответа. В hex остаются исходные байты.")

    def _connect(self, task):
        self._close()
        port = task["port"].strip()
        baud = int(task["baud"])
        requested = task["framing"]
        self.log("ok", f"[*] Открываю {port} · {baud} 8N1 · кадр {requested}…")
        tr = sc.OpticTransport(port, baud)
        try:
            if requested == "auto":
                frame_name, probe = tr.detect_framing("DevInfo")
            else:
                tr.set_framing(requested)
                probe = tr.probe("DevInfo")
                frame_name = requested
        except Exception:
            tr.close()
            raise
        self.cli = sc.SmtClient(tr)
        self._echo_noted = False
        self._wire_log()
        devinfo = sc.value_of(probe, name="DevInfo")
        self.post("status", ("on", port))
        self.log("ok", f"[+] Подключено: {port} · {baud} 8N1 · кадрирование {frame_name} · "
                       f"ответ {tr.last_latency_ms} мс")
        self.log("io", f"     DevInfo = {pretty(devinfo)!r}")
        # журнал сессии на диск (вся работа с физическим прибором сохраняется)
        if ss is not None:
            try:
                self.recorder = ss.SessionRecorder(os.path.join(HERE, "sessions"))
                self.recorder.header(port=port, baud=baud, framing=frame_name,
                                     devinfo=str(pretty(devinfo)))
                self.post("session_file", self.recorder.jsonl_path or "")
                self.log("ok", f"[сессия] запись на диск: {self.recorder.jsonl_path}")
            except Exception as exc:
                self.recorder = None
                self.log("warn", f"[сессия] журнал не открыт: {exc}")

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
        self._wire_log()
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
            return f"{disp(name)} = {pretty(val)}"
        if not raw:
            return f"{name} = (нет ответа)"
        text = pretty(sc.decode_response(raw).strip())
        return text or f"{name} = (ok)"

    def _read(self, name):
        raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
        self.log("io", f">> {disp(name)}\n<< {self._fmt(name, raw, val)}")

    def _send(self, text, expert):
        text = text.strip()
        if not text:
            return
        name, kind = classify_send(text, self.actions)
        if kind == "read":
            self._read(name)
            return
        critical = name in self.critical
        if critical and not expert:
            self.log("warn", f"[заблокировано] '{name}' — критичная команда ({kind}). "
                             "Включи «Экспертный режим» для фактической отправки на прибор.")
            return
        if critical:
            self.log("warn", f"⚠ ЭКСПЕРТ: отправка критичной команды >> {disp_cmd(text)}")
        # Запись/действие не повторяются автоматически: неизвестно, успел ли прибор
        # выполнить первую посылку до потери ответа.
        raw, val = self._tx(text, retry_safe=False, expert=expert, mutating=True, kind=kind)
        self.log("io", f">> {disp_cmd(text)}\n<< {self._fmt(name, raw, val)}")

    def _auth(self, cred, value):
        cmd = f"{cred}={value}" if value != "" else cred
        self.log("ok", f"[auth] Предъявление обработканых данных: {cred} …")
        raw, val = self._tx(cmd, retry_safe=False, expert=True, mutating=True, kind="auth")
        self.log("io", f">> {disp_cmd(cmd)}\n<< {self._fmt(cred, raw, val)}")

    def _passport(self):
        self.log("ok", "[*] Снятие паспорта с физического прибора…")
        ok = 0
        for name in sc.PASSPORT:
            try:
                raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
                if raw:
                    ok += 1
                self.log("io", f"  {disp(name):<20} = {pretty(val)!r}")
            except Exception as exc:
                self.log("err", f"  {disp(name):<20} = <err:{exc}>")
            time.sleep(0.04)
        self.log("ok", f"[*] Паспорт завершён: ответы {ok}/{len(sc.PASSPORT)}.")

    def _read_names(self, names, title, delay=0.03):
        """Прочитать список команд подряд, собрать {имя: значение}, отчитаться о
        прогрессе и вернуть снимок. Только ЧТЕНИЕ (get) — ничего не меняет."""
        self.log("ok", f"[*] {title}: чтение {len(names)} параметров с прибора…")
        profile, ok = {}, 0
        total = len(names)
        for idx, name in enumerate(names, 1):
            try:
                raw, val = self._tx(name, retry_safe=True, mutating=False, kind="read")
                text = pretty(val) if val not in (None, "") else ""
                profile[name] = text
                if raw:
                    ok += 1
                self.log("io", f"  [{idx:>3}/{total}] {disp(name):<22} = {text!r}")
            except Exception as exc:
                profile[name] = f"<err:{exc}>"
                self.log("err", f"  [{idx:>3}/{total}] {disp(name):<22} = <err:{exc}>")
            if idx % 10 == 0 or idx == total:
                self.post("progress", (idx, total))
            time.sleep(delay)
        self.log("ok", f"[*] {title} завершено: ответы {ok}/{total}.")
        self.post("profile", profile)
        return profile

    def _readable_names(self, cmds):
        """Имена, которые безопасно читать (get). ДЕЙСТВИЯ исключаются: их «голое»
        имя на реальном приборе выполняет операцию, а не читает значение."""
        skipped = [c["name"] for c in cmds if c["name"] in self.actions]
        names = [c["name"] for c in cmds if c["name"] not in self.actions]
        if skipped:
            self.log("warn", f"[читаю] пропущено действий (их нельзя читать голым "
                             f"именем): {len(skipped)} — они выполняются только "
                             "кнопкой «Действие» в экспертном режиме.")
        return names

    def _readall(self):
        """Снять ПОЛНЫЙ снимок прибора — прочитать все параметры каталога (get).
        Команды-ДЕЙСТВИЯ в снимок не входят (чтобы ничего не выполнить)."""
        cmds = self.catalog or [{"name": n} for n in sc.PASSPORT]
        names = self._readable_names(cmds)
        self._read_names(names, "Полное чтение (все параметры)")

    def _groupread(self, group):
        cmds = [c for c in self.catalog if c.get("group") == group]
        if not cmds:
            self.log("warn", f"[группа] в каталоге нет команд группы {group!r}.")
            return
        names = self._readable_names(cmds)
        if not names:
            self.log("warn", f"[группа] в «{group}» только действия — читать нечего.")
            return
        self._read_names(names, f"Чтение группы «{group}»")

    def _authscan(self):
        self.log("ok", "[*] Auth-scan — чтение доступных кредов с физического прибора:")
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
            self.log("io", f"  {disp(name):<16} = {values[name]!r}")
        self.post("tele_reading", values)

    def _preflight(self):
        self.log("ok", "[*] Пре-флайт: повторная проверка физической линии…")
        raw = self.cli.t.probe("DevInfo")
        self._wire_log()
        value = sc.value_of(raw, name="DevInfo")
        tr = self.cli.t
        self.log("ok", f"[OK] Прибор отвечает · кадр {tr.frame_name or 'ручной'} · "
                       f"{tr.last_latency_ms} мс · RX {len(tr.last_raw_rx)} байт" +
                       (" · оптическое эхо снято" if tr.last_echo_removed else ""))
        self.log("io", f"     DevInfo = {pretty(value)!r}")


# ───────────────────────────── интерфейс ────────────────────────────────
def build_app(root, selftest=False):
    import tkinter as tk
    from tkinter import ttk, scrolledtext, filedialog, messagebox

    catalog = load_catalog()
    critical = build_critical(catalog)
    actions = build_actions(catalog)
    task_q, out_q = queue.Queue(), queue.Queue()
    backend = Backend(task_q, out_q, critical, actions, catalog); backend.start()

    root.title("Аудит прибора — оптопорт · каталог 158 команд")
    root.geometry("1220x850")

    state = {"selected": None, "connected": False, "expert": False}
    settings = load_settings()

    # ── шапка: подключение ──────────────────────────────────────────────
    top = ttk.Frame(root, padding=6); top.pack(fill="x")
    ttk.Label(top, text="Порт:").pack(side="left")
    port_var = tk.StringVar(value=suggested_port(settings.get("port")))
    port_ent = ttk.Entry(top, textvariable=port_var, width=16); port_ent.pack(side="left", padx=(2, 6))

    def list_ports():
        try:
            from serial.tools import list_ports
            ports = list(list_ports.comports())
            if not ports:
                messagebox.showinfo("Порты", "Serial-порты не найдены.\nПодключи USB-оптозонд.")
                return
            lines = []
            for item in ports:
                details = item.description or "serial"
                if item.vid is not None and item.pid is not None:
                    details += f" · VID:PID={item.vid:04X}:{item.pid:04X}"
                lines.append(f"{item.device} — {details}")
            candidates = [item.device for item in ports if any(
                hint in ((item.device or "") + " " + (item.description or "")).lower()
                for hint in ("ttyusb", "ttyacm", "usbserial", "usbmodem", " ch340", "cp210", "ftdi", "com")
            )]
            if len(candidates) == 1:
                port_var.set(candidates[0])
            messagebox.showinfo("Порты", "\n".join(lines) +
                                (f"\n\nАвтовыбран: {candidates[0]}" if len(candidates) == 1 else ""))
        except Exception as e:
            messagebox.showerror("Порты", str(e))
    ttk.Button(top, text="Порты…", command=list_ports).pack(side="left")

    ttk.Label(top, text="Baud:").pack(side="left", padx=(10, 2))
    baud_var = tk.StringVar(value=str(settings.get("baud", "9600")))
    ttk.Combobox(top, textvariable=baud_var, width=7, state="readonly",
                 values=["9600", "19200", "38400", "57600", "115200"]).pack(side="left")

    ttk.Label(top, text="Кадр:").pack(side="left", padx=(10, 2))
    fr_var = tk.StringVar(value=settings.get("framing", "auto"))
    ttk.Combobox(top, textvariable=fr_var, width=7, state="readonly",
                 values=["auto"] + list(sc.FRAMINGS.keys())).pack(side="left")

    conn_btn = ttk.Button(top, text="Подключить")
    conn_btn.pack(side="left", padx=12)
    status_lbl = ttk.Label(top, text="● отключено", foreground="#b00")
    status_lbl.pack(side="left")

    def do_connect():
        if state["connected"]:
            task_q.put({"op": "disconnect"})
        else:
            selected = {"port": port_var.get().strip(),
                        "baud": int(baud_var.get()), "framing": fr_var.get()}
            save_settings(selected)
            task_q.put({"op": "connect", **selected})
    conn_btn.config(command=do_connect)

    def do_dump():
        # Кнопка сохранена ради неизменности интерфейса. Файл используется только
        # парсерами вкладки «История» и никогда не подменяет физический прибор.
        path = filedialog.askopenfilename(filetypes=[("dump W25Q64", "*.bin"), ("все", "*.*")])
        if path:
            hist_load_path(path)
            main_nb.select(tab_hist)
    ttk.Button(top, text="Открыть дамп…", command=do_dump).pack(side="left", padx=(10, 0))

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
        # заявленный уровень по выбранному кредy (устройство проверит по факту)
        m = {"PASSWORD_PROVIDER": "Провайдер (П)", "PASSWORD_FABRIC": "Заводской (f)",
             "PASSWORD_OMEGA": "Omega (О)", "ENABLE_OMEGA": "Omega (О)",
             "PASSWORD_OMEGA2": "Omega (О)", "MAGIC": "Omega (О)"}
        level_var.set(m.get(cred_var.get(), level_var.get()))
    ttk.Button(top2, text="Аутентифицировать", command=do_auth).pack(side="left", padx=6)

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
    ttk.Checkbutton(top2, text="Экспертный режим", variable=expert_var,
                    command=toggle_expert).pack(side="left", padx=(16, 2))
    exp_lbl = ttk.Label(top2, text="○ эксперт выкл", foreground="#777")
    exp_lbl.pack(side="left")

    # ── верхний нотбук: «Команды», «Панели», «Телеметрия», «История» ─────
    main_nb = ttk.Notebook(root)
    tab_cmd = ttk.Frame(main_nb)
    tab_panels = ttk.Frame(main_nb)
    tab_tele = ttk.Frame(main_nb, padding=6)
    tab_hist = ttk.Frame(main_nb, padding=6)
    main_nb.add(tab_cmd, text="Команды (158)")
    main_nb.add(tab_panels, text="Панели управления")
    main_nb.add(tab_tele, text="Телеметрия")
    main_nb.add(tab_hist, text="История")
    main_nb.pack(fill="both", expand=True)

    # реестр полей значений по имени команды — заполняется полным/групповым чтением
    panel_vars = {}

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
            if q and q not in c["display"].lower() and q not in c["desc"].lower():
                continue
            prot = "заблок." if c["protected_write"] else "разрешена"
            tags = ("prot",) if c["protected_write"] else ()
            tree.insert("", "end", iid=c["name"],
                        values=(c["display"], clean_desc(c["desc"], 70), c["type"],
                                access_human(c["prov"]), access_human(c["user"]), prot),
                        tags=tags)
            n += 1
        count_lbl.config(text=f"Показано: {n} из {len(catalog)} команд "
                              f"· красным — запись защищена (сервис/актуатор/пароли)")
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

    free = ttk.LabelFrame(right, text="Свободная команда (сырой протокол)", padding=6)
    free.pack(fill="x")
    free_var = tk.StringVar()
    ttk.Entry(free, textvariable=free_var).pack(side="left", fill="x", expand=True)
    def do_send_free():
        txt = free_var.get().strip()
        if txt:
            task_q.put({"op": "send", "text": txt, "expert": state["expert"]})
    ttk.Button(free, text="Отправить", command=do_send_free).pack(side="left", padx=6)

    def do_export_profile():
        prof = state.get("profile")
        if not prof:
            messagebox.showinfo("Профиль устройства",
                                "Сначала сними полный снимок кнопкой «Прочитать ВСЁ (158)».")
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить профиль устройства",
            defaultextension=".json",
            initialfile=f"device_profile_{datetime.date.today()}",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")])
        if not path:
            return
        by_name = {c["name"]: c for c in catalog}
        try:
            if path.lower().endswith(".csv"):
                import csv as _csv
                with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                    w = _csv.writer(fh, delimiter=";")
                    w.writerow(["name", "display", "group", "type", "value"])
                    for name, val in prof.items():
                        c = by_name.get(name, {})
                        w.writerow([name, disp(name), c.get("group", ""),
                                    c.get("type", ""), val])
            else:
                rows = [{"name": name, "display": disp(name),
                         "group": by_name.get(name, {}).get("group", ""),
                         "type": by_name.get(name, {}).get("type", ""),
                         "value": val} for name, val in prof.items()]
                doc = {"captured": datetime.datetime.now().isoformat(timespec="seconds"),
                       "count": len(rows), "parameters": rows}
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh, ensure_ascii=False, indent=2)
            append("ok", f"[профиль] сохранено {len(prof)} параметров → {path}")
        except Exception as exc:
            messagebox.showerror("Профиль устройства", str(exc))

    quick = ttk.LabelFrame(right, text="Быстрые действия", padding=6); quick.pack(fill="x")
    quick.columnconfigure(0, weight=1); quick.columnconfigure(1, weight=1)
    _qa = [
        ("Пре-флайт", lambda: task_q.put({"op": "preflight"})),
        ("Паспорт", lambda: task_q.put({"op": "passport"})),
        ("Auth-scan", lambda: task_q.put({"op": "authscan"})),
        ("Показания", lambda: [task_q.put({"op": "read", "name": n}) for n in
                               ("Volume", "VOLUME_GLOB", "VOLUME_INST", "VOLUME_COMMIS")]),
        ("Прочитать ВСЁ (158)", lambda: task_q.put({"op": "readall"})),
        ("Профиль → файл…", do_export_profile),
    ]
    for _i, (_t, _cmd) in enumerate(_qa):
        ttk.Button(quick, text=_t, command=_cmd).grid(
            row=_i // 2, column=_i % 2, sticky="ew", padx=2, pady=2)
    profile_lbl = ttk.Label(quick, text="снимок не снят", foreground="#777")
    profile_lbl.grid(row=len(_qa) // 2 + 1, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def on_select(_=None):
        sel = tree.focus()
        if not sel:
            return
        c = next((x for x in catalog if x["name"] == sel), None)
        if not c:
            return
        state["selected"] = c
        det_txt.configure(state="normal"); det_txt.delete("1.0", "end")
        det_txt.insert("end", f"{c['display']}   ({c['type']})\n", "h")
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
        if state["selected"]:
            task_q.put({"op": "write", "name": state["selected"]["name"],
                        "val": val_var.get(), "expert": state["expert"]})
    def do_action():
        if state["selected"]:
            task_q.put({"op": "send", "text": state["selected"]["name"],
                        "expert": state["expert"]})
    read_btn.config(command=do_read)
    write_btn.config(command=do_write)
    act_btn.config(command=do_action)

    # ── вкладка «Панели управления»: ВСЕ команды по функциям ────────────
    pan_top = ttk.Frame(tab_panels, padding=6); pan_top.pack(fill="x")
    ttk.Label(pan_top, wraplength=980, foreground="#555", justify="left",
              text="Полное управление прибором: все 158 команд по функциональным группам. "
                   "Get — прочитать, Set — записать значение, Действие — выполнить. Поля "
                   "заполняются кнопками «Прочитать группу» / «Прочитать ВСЁ». Критичные "
                   "(красные) уходят на прибор только при включённом «Экспертном режиме»."
              ).pack(side="left", fill="x", expand=True)
    ttk.Button(pan_top, text="Прочитать ВСЁ",
               command=lambda: task_q.put({"op": "readall"})).pack(side="right", padx=4)

    pan_canvas = tk.Canvas(tab_panels, highlightthickness=0)
    pan_sb = ttk.Scrollbar(tab_panels, orient="vertical", command=pan_canvas.yview)
    pan_inner = ttk.Frame(pan_canvas)
    pan_inner.bind("<Configure>",
                   lambda e: pan_canvas.configure(scrollregion=pan_canvas.bbox("all")))
    pan_win = pan_canvas.create_window((0, 0), window=pan_inner, anchor="nw")
    pan_canvas.bind("<Configure>", lambda e: pan_canvas.itemconfigure(pan_win, width=e.width))
    pan_canvas.configure(yscrollcommand=pan_sb.set)
    pan_canvas.pack(side="left", fill="both", expand=True)
    pan_sb.pack(side="right", fill="y")

    def _pan_wheel(e):
        step = -1 if getattr(e, "num", None) == 4 else 1 if getattr(e, "num", None) == 5 \
            else int(-1 * (e.delta / 120)) if getattr(e, "delta", 0) else 0
        if step:
            pan_canvas.yview_scroll(step, "units")
    pan_canvas.bind("<Enter>", lambda e: (pan_canvas.bind_all("<MouseWheel>", _pan_wheel),
                                          pan_canvas.bind_all("<Button-4>", _pan_wheel),
                                          pan_canvas.bind_all("<Button-5>", _pan_wheel)))
    pan_canvas.bind("<Leave>", lambda e: (pan_canvas.unbind_all("<MouseWheel>"),
                                          pan_canvas.unbind_all("<Button-4>"),
                                          pan_canvas.unbind_all("<Button-5>")))

    def make_panel_row(parent, c, r):
        name = c["name"]
        is_action = name in actions
        is_crit = name in critical
        ttk.Label(parent, text=disp(name), width=22, anchor="w",
                  foreground=("#c0392b" if is_crit else "#111")).grid(
            row=r, column=0, sticky="w", padx=(0, 4), pady=1)
        ttk.Label(parent, text=(clean_desc(c["desc"], 44) or c["type"]), width=44,
                  anchor="w", foreground="#666").grid(row=r, column=1, sticky="w", padx=4)
        var = tk.StringVar()
        panel_vars[name] = var
        ent = ttk.Entry(parent, textvariable=var, width=18)
        ent.grid(row=r, column=2, sticky="ew", padx=4)
        opts = value_options(c)
        if opts:
            ocb = ttk.Combobox(parent, width=13, state="readonly", values=opts)
            ocb.grid(row=r, column=3, padx=1)
            ocb.bind("<<ComboboxSelected>>",
                     lambda e, v=var, cb=ocb: v.set(cb.get().split(" ", 1)[0]))
        else:
            ttk.Label(parent, text=c["type"], width=13, foreground="#999").grid(
                row=r, column=3, padx=1)
        ttk.Button(parent, text="Get", width=5,
                   command=lambda n=name: task_q.put({"op": "read", "name": n})).grid(
            row=r, column=4, padx=1)
        if is_action:
            ent.state(["disabled"])
            ttk.Button(parent, text="Действие", width=10,
                       command=lambda n=name: task_q.put(
                           {"op": "send", "text": n, "expert": state["expert"]})).grid(
                row=r, column=5, padx=1)
        else:
            ttk.Button(parent, text="Set", width=10,
                       command=lambda n=name, v=var: task_q.put(
                           {"op": "write", "name": n, "val": v.get(),
                            "expert": state["expert"]})).grid(row=r, column=5, padx=1)

    by_group = {}
    for c in catalog:
        by_group.setdefault(c["group"], []).append(c)
    _preferred = ["Значения и накопители", "Датчик и температура", "Фильтр Калмана",
                  "Исполнительный механизм (актуатор)", "Связь: GSM / RS-485 / сервер",
                  "Дисплей / сервис / питание", "Сервис и защита от вмешательства",
                  "Доступ / пароли", "Прочее / служебное"]
    group_order = [g for g in _preferred if g in by_group] + \
                  [g for g in sorted(by_group) if g not in _preferred]
    for group in group_order:
        cmds = sorted(by_group[group], key=lambda x: x["name"])
        n_crit = sum(1 for c in cmds if c["name"] in critical)
        gf = ttk.LabelFrame(pan_inner, padding=6,
                            text=f"{group}  ·  {len(cmds)} команд"
                                 + (f"  ·  критичных: {n_crit}" if n_crit else ""))
        gf.pack(fill="x", padx=8, pady=5)
        gf.columnconfigure(2, weight=1)
        ttk.Button(gf, text="Прочитать группу",
                   command=lambda g=group: task_q.put({"op": "groupread", "group": g})).grid(
            row=0, column=0, columnspan=6, sticky="w", pady=(0, 4))
        for r, c in enumerate(cmds, start=1):
            make_panel_row(gf, c, r)

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

    # ── вкладка «История»: чекпоинт показаний + журнал событий (только чтение) ──
    ttk.Label(tab_hist, wraplength=1150, foreground="#555", justify="left",
              text="История — ТОЛЬКО ЧТЕНИЕ. Разбор дампа W25Q64: чекпоинт показаний "
                   "(0x7FE000/0x7FC000, кольцо 64×128 Б, пинг-понг) и журнал событий/"
                   "аудита (0x15E000, записи по 16 Б). Столбец «Целостн.» = маркер 0xA5A5 "
                   "И совпадение показания с его копией (+0x00 vs +0x10). Инструмент "
                   "разбирает и показывает; редактирования нет."
              ).pack(anchor="w")
    hctl = ttk.Frame(tab_hist); hctl.pack(fill="x", pady=4)
    ttk.Button(hctl, text="Загрузить дамп…", command=lambda: hist_load()).pack(side="left")
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

    def hist_fill(data):
        cp_tree.delete(*cp_tree.get_children()); ev_tree.delete(*ev_tree.get_children())
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
                ev_info.config(text=f"Журнал 0x15E000 · записей: {len(seen)}")
            except Exception as e:
                ev_info.config(text=f"Журнал не разобран: {e}")

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
                elif kind == "tele_log":
                    append(*payload)
                elif kind == "tele_reading":
                    state["readings"] = payload
                    append("ok", "[тел] показания сняты — можно «Собрать пакет».")
                elif kind == "tele_rx":
                    raw, rep, ip, n = payload
                    tele_in.delete("1.0", "end"); tele_in.insert("1.0", raw)
                    _tele_render(rep)
                    main_nb.select(tab_tele)
                    append("ok", f"[приём] пакет от {ip}: {n} записей → ACK DATA ACCEPT:{n}")
                elif kind == "tele_state":
                    if payload == "off":
                        state["tele_srv"] = None
                        listen_status.config(text="○ не слушаю", foreground="#777")
                elif kind == "session_file":
                    state["session_file"] = payload
                elif kind == "profile":
                    prof = state.setdefault("profile", {})
                    prof.update(payload)
                    state["readings"] = {k: v for k, v in prof.items()
                                         if not str(v).startswith("<err:")}
                    for _nm, _v in payload.items():             # заполнить поля панелей
                        if _nm in panel_vars and not str(_v).startswith("<err:"):
                            panel_vars[_nm].set(_v)
                    profile_lbl.config(
                        text=f"снимок: {len(prof)} параметров "
                             f"· {datetime.datetime.now():%H:%M:%S}")
                    append("ok", f"[профиль] обновлено {len(payload)} параметров "
                                 f"(всего {len(prof)}). Можно «Профиль → файл…».")
                elif kind == "progress":
                    done, total = payload
                    profile_lbl.config(text=f"чтение {done}/{total}…")
                elif kind == "password":
                    cred, value = payload
                    pw_var.set(value)
                    if cred in AUTH_CREDS:
                        cred_var.set(cred)
                    append("ok", f"[auto] Пароль из {cred} подставлен в поле "
                                 f"аутентификации ({value}).")
                elif kind == "status":
                    st, port = payload
                    state["connected"] = (st == "on")
                    if st == "on":
                        status_lbl.config(text=f"● подключено {port}", foreground="#0a7d0a")
                        conn_btn.config(text="Отключить")
                    else:
                        status_lbl.config(text="● отключено", foreground="#b00")
                        conn_btn.config(text="Подключить")
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
        {"op": "connect", "port": port, "baud": 9600, "framing": "auto"},
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
