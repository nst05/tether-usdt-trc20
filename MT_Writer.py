# -*- coding: utf-8 -*-
# MT_Writer — 200_MT и 310_MT в одном окне (две вкладки).
# Логика записи в EEPROM 24C16 — дословно как в исходных 200_MT/310_MT.
# Добавлены: дизайн с вкладками, счётчик прошивок (не сбрасывается) и
# привязка к компьютеру. Один файл, зависимостей столько же, сколько было.
#
# Сборка (той же командой, что и оригиналы):
#     pyinstaller --onefile --windowed --hidden-import=i2cpy MT_Writer.py
#
# Генерация ключа активации (запускать с python, не в собранном exe):
#     python MT_Writer.py keygen КОД_КОМПЬЮТЕРА [дней]
#     python MT_Writer.py keygen A1B2C-D3E4F-6789A-BCDEF          (бессрочно)
#     python MT_Writer.py keygen A1B2C-D3E4F-6789A-BCDEF 365      (на год)

import gc
import os
import random
import sys
import time

import base64
import binascii
import hashlib
import hmac
import json
import platform
import struct
import uuid
from datetime import date, datetime, timedelta

from PyQt5 import QtCore, QtGui, QtWidgets

if getattr(sys, "frozen", False):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")

try:
    from i2cpy import I2C
except ImportError:
    I2C = None


# ═══════════════════════════════════════════════════════════════════════════
#  EEPROM — константы и функции (БЕЗ ИЗМЕНЕНИЙ, как в 200_MT/310_MT)
# ═══════════════════════════════════════════════════════════════════════════

# 24C16 / 24AA16: 2 КБ, 8 блоков по 256 байт.
EEPROM_SIZE = 2048
VALUE_OFFSET = 0x0040
VALUE_SIZE = 4
SCALE = 100
BASE_I2C_ADDRESS = 0x50


def encode_value(value: float) -> bytes:
    raw = int(round(value * SCALE))
    if not 0 <= raw <= 0xFFFFFFFF:
        raise ValueError("Значение слишком большое.")
    return raw.to_bytes(4, "little", signed=False)


def decode_value(data: bytes) -> float:
    if len(data) != 4:
        raise ValueError("Неверная длина данных.")
    return int.from_bytes(data, "little", signed=False) / SCALE


# ═══════════════════════════════════════════════════════════════════════════
#  Где хранить лицензию и счётчик (рядом с программой)
# ═══════════════════════════════════════════════════════════════════════════

def data_dir():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    try:
        probe = os.path.join(base, ".w")
        open(probe, "w").close()
        os.remove(probe)
        return base
    except Exception:
        alt = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MT_Writer")
        os.makedirs(alt, exist_ok=True)
        return alt


COUNTERS_FILE = "counters.json"


# ═══════════════════════════════════════════════════════════════════════════
#  ЛИЦЕНЗИЯ — перенос ОДИН-В-ОДИН из mt_license.py, чтобы ключи от
#  keygen_mt.exe подходили. Секрет, код компьютера и формат ключа не меняются.
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_SECRET = 'mt-writer-license-secret-change-me-2024'
SECRET = os.environ.get('MT_LICENSE_SECRET', DEFAULT_SECRET).encode('utf-8')

KEY_VERSION = 1
LICENSE_FILE = 'license.key'
_EPOCH = date(2020, 1, 1)
_SIG_LEN = 10
_CLOCK_TOLERANCE_DAYS = 2


def _win_machine_guid():
    try:
        import winreg
        for view in (getattr(winreg, 'KEY_WOW64_64KEY', 0), 0):
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                     r'SOFTWARE\Microsoft\Cryptography',
                                     0, winreg.KEY_READ | view)
                try:
                    value, _ = winreg.QueryValueEx(key, 'MachineGuid')
                finally:
                    winreg.CloseKey(key)
                if value:
                    return str(value).strip()
            except OSError:
                continue
    except Exception:
        pass
    return None


def _win_volume_serial():
    try:
        import ctypes
        root = os.environ.get('SystemDrive', 'C:') + '\\'
        serial = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root), None, 0,
            ctypes.byref(serial), None, None, None, 0)
        if ok:
            return '%08X' % serial.value
    except Exception:
        pass
    return None


def _linux_machine_id():
    for path in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
        try:
            with open(path, 'r') as fh:
                value = fh.read().strip()
            if value:
                return value
        except Exception:
            continue
    return None


def _linux_dmi_uuid():
    for path in ('/sys/class/dmi/id/product_uuid', '/sys/class/dmi/id/board_serial'):
        try:
            with open(path, 'r') as fh:
                value = fh.read().strip()
            if value and value.lower() not in ('none', 'unknown', '', '0'):
                return value
        except Exception:
            continue
    return None


def _mac_platform_uuid():
    try:
        import subprocess
        out = subprocess.run(['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
                             capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            if 'IOPlatformUUID' in line:
                return line.split('=')[-1].strip().strip('"')
    except Exception:
        pass
    return None


def _mac_address():
    node = uuid.getnode()
    if node and not (node >> 40) & 0x01:
        return '%012X' % node
    return None


def _sources():
    system = platform.system()
    if system == 'Windows':
        return [('win-guid', _win_machine_guid),
                ('win-vol', _win_volume_serial),
                ('mac', _mac_address)]
    if system == 'Darwin':
        return [('mac-uuid', _mac_platform_uuid),
                ('mac', _mac_address)]
    return [('linux-id', _linux_machine_id),
            ('linux-dmi', _linux_dmi_uuid),
            ('mac', _mac_address)]


def _raw_fingerprint():
    for tag, getter in _sources():
        try:
            value = getter()
        except Exception:
            value = None
        if value:
            return tag, value
    return None, None


def _format_code(digest_hex):
    body = digest_hex[:20].upper()
    return '-'.join(body[i:i + 5] for i in range(0, 20, 5))


def machine_code():
    override = os.environ.get('MT_MACHINE_CODE')
    if override:
        return normalize(override)
    tag, value = _raw_fingerprint()
    if not value:
        tag, value = 'host', platform.node() or 'unknown-host'
    payload = ('%s:%s:%s' % (tag, value, platform.system())).encode('utf-8', 'replace')
    return _format_code(hashlib.sha256(payload).hexdigest())


def normalize(value):
    cleaned = ''.join(ch for ch in (value or '').upper() if ch.isalnum())
    return '-'.join(cleaned[i:i + 5] for i in range(0, len(cleaned), 5))


def _canonical(value):
    return ''.join(ch for ch in (value or '').upper() if ch.isalnum())


_fmt_code = normalize  # для встроенного keygen


def _signature(code, version, days):
    message = ('%s|%d|%d' % (_canonical(code), version, days)).encode('utf-8')
    return hmac.new(SECRET, message, hashlib.sha256).digest()[:_SIG_LEN]


def generate_key(code, valid_days=0):
    code = _canonical(code)
    if len(code) != 20:
        raise ValueError('Код компьютера должен содержать 20 символов '
                         '(например A1B2C-D3E4F-6789A-BCDEF)')
    if valid_days and int(valid_days) > 0:
        expiry_days = (date.today() + timedelta(days=int(valid_days)) - _EPOCH).days
        if not 0 < expiry_days <= 0xFFFF:
            raise ValueError('Слишком большой срок действия')
    else:
        expiry_days = 0
    blob = struct.pack('>BH', KEY_VERSION, expiry_days)
    blob += _signature(code, KEY_VERSION, expiry_days)
    encoded = base64.b32encode(blob).decode('ascii').rstrip('=')
    return '-'.join(encoded[i:i + 7] for i in range(0, len(encoded), 7))


def verify_key(key, code=None, today=None):
    code = code or machine_code()
    today = today or date.today()
    cleaned = _canonical(key)
    result = {'valid': False, 'reason': None, 'expires': None, 'perpetual': False}
    if not cleaned:
        result['reason'] = 'Ключ не введён'
        return result
    try:
        blob = base64.b32decode(cleaned + '=' * (-len(cleaned) % 8))
    except (binascii.Error, ValueError):
        result['reason'] = 'Ключ введён с ошибкой'
        return result
    if len(blob) != 3 + _SIG_LEN:
        result['reason'] = 'Неверная длина ключа'
        return result
    version, expiry_days = struct.unpack('>BH', blob[:3])
    if version != KEY_VERSION:
        result['reason'] = 'Ключ версии %d не поддерживается этой программой' % version
        return result
    if not hmac.compare_digest(_signature(code, version, expiry_days), blob[3:]):
        result['reason'] = 'Ключ не подходит к этому компьютеру'
        return result
    if expiry_days == 0:
        result.update(valid=True, perpetual=True)
        return result
    expires = _EPOCH + timedelta(days=expiry_days)
    result['expires'] = expires
    if today > expires:
        result['reason'] = 'Срок лицензии истёк %s' % expires.strftime('%d.%m.%Y')
        return result
    result['valid'] = True
    return result


def _guard(key, last_seen):
    message = ('%s|%s' % (_canonical(key), last_seen)).encode('utf-8')
    return hmac.new(SECRET, message, hashlib.sha256).hexdigest()[:32]


def _read_license():
    try:
        with open(os.path.join(data_dir(), LICENSE_FILE), encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def _write_license(data):
    try:
        with open(os.path.join(data_dir(), LICENSE_FILE), 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def check_license():
    code = machine_code()
    status = {'valid': False, 'reason': 'Программа не активирована на этом компьютере',
              'machine_code': code, 'expires': None, 'perpetual': False, 'days_left': None}
    data = _read_license()
    if not data or not data.get('key'):
        return status
    key = data.get('key', '')
    result = verify_key(key, code)
    if not result['valid']:
        status['reason'] = result['reason']
        return status
    last_seen = data.get('last_seen')
    if last_seen and data.get('guard') == _guard(key, last_seen):
        try:
            seen = date.fromisoformat(last_seen)
            if date.today() < seen - timedelta(days=_CLOCK_TOLERANCE_DAYS):
                status['reason'] = ('Системная дата переведена назад. '
                                    'Установите правильную дату и запустите снова.')
                return status
        except ValueError:
            pass
    status.update(valid=True, reason=None,
                  expires=result['expires'], perpetual=result['perpetual'])
    if result['expires']:
        status['days_left'] = (result['expires'] - date.today()).days
    # обновляем отметку последнего запуска
    today = date.today().isoformat()
    if data.get('last_seen') != today:
        data['last_seen'] = today
        data['guard'] = _guard(key, today)
        _write_license(data)
    return status


def activate(key):
    code = machine_code()
    result = verify_key(key, code)
    if not result['valid']:
        return False, result['reason']
    last_seen = date.today().isoformat()
    _write_license({
        'key': normalize(key),
        'machine': code,
        'activated_at': datetime.now().isoformat(timespec='seconds'),
        'last_seen': last_seen,
        'guard': _guard(key, last_seen),
    })
    if result['perpetual']:
        return True, 'Программа активирована на этом компьютере (бессрочно).'
    return True, ('Программа активирована на этом компьютере до %s.'
                  % result['expires'].strftime('%d.%m.%Y'))


def license_line(st):
    if not st["valid"]:
        return "Лицензия: не активирована"
    if st["perpetual"]:
        return "Лицензия: бессрочная"
    return "Лицензия: до %s (%d дн.)" % (st["expires"].strftime("%d.%m.%Y"), st["days_left"])


# ═══════════════════════════════════════════════════════════════════════════
#  Счётчик прошивок (по вкладкам, не сбрасывается)
# ═══════════════════════════════════════════════════════════════════════════

class Counters:
    def __init__(self, names):
        self.names = names
        self.data = {n: 0 for n in names}
        try:
            with open(os.path.join(data_dir(), COUNTERS_FILE), encoding="utf-8") as fh:
                saved = json.load(fh)
            for n in names:
                self.data[n] = int(saved.get(n, 0))
        except Exception:
            pass

    def get(self, name):
        return self.data.get(name, 0)

    def inc(self, name):
        self.data[name] = self.get(name) + 1
        try:
            with open(os.path.join(data_dir(), COUNTERS_FILE), "w", encoding="utf-8") as fh:
                json.dump(self.data, fh)
        except Exception:
            pass
        return self.data[name]


# ═══════════════════════════════════════════════════════════════════════════
#  Стиль
# ═══════════════════════════════════════════════════════════════════════════

APP_STYLE = """
QWidget { background:#10131a; color:#f2f4f8; font-family:'Segoe UI'; font-size:15px; }
QLineEdit {
    background:#181d27; border:2px solid #38445a; border-radius:14px;
    padding:14px 18px; font-size:28px; font-weight:700; color:#fff;
    selection-background-color:#4f7cff;
}
QLineEdit:focus { border-color:#6b8cff; }
QPushButton {
    background:#3f6df6; border:2px solid #6f91ff; border-radius:16px;
    padding:16px; font-size:22px; font-weight:800; color:white;
}
QPushButton:hover { background:#4e79ff; }
QPushButton:pressed { background:#345acb; }
QPushButton:disabled { background:#2b3240; border-color:#3a4352; color:#8d96a8; }
QPushButton#Ghost { background:#1a2230; border-color:#2b3648; color:#cdd6e6; font-size:14px; padding:10px; }
QPushButton#Ghost:hover { background:#222c3d; }
QLabel#TitleLabel { font-size:22px; font-weight:900; color:#fff; }
QLabel#HintLabel { font-size:14px; color:#aab3c5; }
QProgressBar {
    border:2px solid #3d4a60; border-radius:10px; background:#18202c;
    color:white; text-align:center; height:24px; font-weight:700;
}
QProgressBar::chunk { border-radius:8px; background:#3f6df6; }
QTabWidget::pane { border:2px solid #2a3346; border-radius:16px; top:-2px; background:#10131a; }
QTabWidget::tab-bar { left:10px; }
QTabBar::tab {
    background:#181d27; color:#aab3c5; border:2px solid #2a3346; border-bottom:none;
    border-top-left-radius:14px; border-top-right-radius:14px;
    padding:10px 30px; margin-right:6px; font-size:16px; font-weight:800;
}
QTabBar::tab:selected { background:#3f6df6; color:#fff; border-color:#6f91ff; }
QTabBar::tab:hover:!selected { background:#202838; color:#dfe5f0; }
QFrame#Card { background:#18202c; border:2px solid #3d4a60; border-radius:14px; }
QLabel#CounterValue { font-size:34px; font-weight:900; color:#7ff0ac; }
QLabel#CounterCaption { font-size:12px; font-weight:800; color:#8d96a8; }
QLabel#Footer { font-size:12px; color:#8d96a8; }
"""


# ═══════════════════════════════════════════════════════════════════════════
#  Вкладка записи — методы i2c ДОСЛОВНО из оригинала
# ═══════════════════════════════════════════════════════════════════════════

class WriterTab(QtWidgets.QWidget):
    def __init__(self, name, counters, license_check):
        super().__init__()
        self.name = name
        self.counters = counters
        self.license_check = license_check
        self.i2c = None
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        head = QtWidgets.QHBoxLayout()
        tbox = QtWidgets.QVBoxLayout()
        tbox.setSpacing(4)
        title = QtWidgets.QLabel("ЗАПИСЬ ЗНАЧЕНИЯ — " + self.name)
        title.setObjectName("TitleLabel")
        tbox.addWidget(title)
        hint = QtWidgets.QLabel("Введите целую часть. Дробная часть 01–99 добавляется автоматически.")
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        tbox.addWidget(hint)
        head.addLayout(tbox, 1)

        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        card.setMinimumWidth(190)
        cc = QtWidgets.QVBoxLayout(card)
        cc.setContentsMargins(16, 8, 16, 8)
        cc.setSpacing(0)
        cap = QtWidgets.QLabel("ПРОШИВОК ВСЕГО")
        cap.setObjectName("CounterCaption")
        cap.setAlignment(QtCore.Qt.AlignCenter)
        self.counter_lbl = QtWidgets.QLabel(str(self.counters.get(self.name)))
        self.counter_lbl.setObjectName("CounterValue")
        self.counter_lbl.setAlignment(QtCore.Qt.AlignCenter)
        cc.addWidget(cap)
        cc.addWidget(self.counter_lbl)
        head.addWidget(card)
        layout.addLayout(head)

        self.value_input = QtWidgets.QLineEdit()
        self.value_input.setPlaceholderText("Например: 3456")
        self.value_input.setAlignment(QtCore.Qt.AlignCenter)
        self.value_input.setMinimumHeight(64)
        validator = QtGui.QDoubleValidator(0.0, 42949672.95, 2, self)
        validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.value_input.setValidator(validator)
        self.value_input.returnPressed.connect(self.write_and_verify)
        layout.addWidget(self.value_input)

        self.write_button = QtWidgets.QPushButton("ЗАПИСАТЬ И ПРОВЕРИТЬ")
        self.write_button.setMinimumHeight(66)
        self.write_button.clicked.connect(self.write_and_verify)
        layout.addWidget(self.write_button)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.status = QtWidgets.QLabel("Готово к работе")
        self.status.setWordWrap(True)
        self.status.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.status)

        self.value_input.setFocus()
        self.set_status("Готово к работе")

    def set_status(self, text, ok=None):
        self.status.setText(text)
        if ok is True:
            css = "background:#153c28;border:2px solid #2fc46f;color:#7ff0ac;"
        elif ok is False:
            css = "background:#471d25;border:2px solid #ff5a6f;color:#ff9cab;"
        else:
            css = "background:#18202c;border:2px solid #3d4a60;color:#d9dfeb;"
        self.status.setStyleSheet("QLabel{%s border-radius:14px;padding:16px;font-size:18px;font-weight:800;}" % css)
        QtWidgets.QApplication.processEvents()

    # ── i2c: методы дословно из оригинала ──────────────────────────────────

    def open_programmer(self):
        if I2C is None:
            raise RuntimeError("Не установлена библиотека i2cpy.")

        self.close_programmer()
        self.i2c = I2C(driver="ch341")

    def close_programmer(self):
        obj = self.i2c
        self.i2c = None

        if obj is not None:
            for method_name in ("close", "deinit", "disconnect"):
                method = getattr(obj, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
                    break

        del obj
        gc.collect()
        time.sleep(0.08)

    @staticmethod
    def split_address(address):
        if not 0 <= address < EEPROM_SIZE:
            raise ValueError("Адрес выходит за пределы 24C16.")
        block = (address >> 8) & 0x07
        device_address = BASE_I2C_ADDRESS | block
        memory_address = address & 0xFF
        return device_address, memory_address

    def read_bytes(self, address, length):
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")
        result = bytearray()
        current = address
        remaining = length
        while remaining > 0:
            dev_addr, mem_addr = self.split_address(current)
            chunk_len = min(remaining, 0x100 - mem_addr)
            chunk = self.i2c.readfrom_mem(dev_addr, mem_addr, chunk_len, addrsize=8)
            result.extend(bytes(chunk))
            current += chunk_len
            remaining -= chunk_len
        return bytes(result)

    def write_bytes(self, address, payload):
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")
        dev_addr, mem_addr = self.split_address(address)
        self.i2c.writeto_mem(dev_addr, mem_addr, bytes(payload), addrsize=8)

    def parse_value(self):
        text = self.value_input.text().strip().replace(",", ".")
        if not text:
            raise ValueError("Введите целую часть.")
        base_value = float(text)
        if base_value < 0:
            raise ValueError("Значение не может быть отрицательным.")
        integer_part = int(base_value)
        fraction = random.randint(1, 99)
        value = integer_part + fraction / 100.0
        encode_value(value)
        return value

    def write_and_verify(self):
        # привязка: без лицензии запись заблокирована
        st = self.license_check()
        if not st["valid"]:
            self.set_status("Запись заблокирована: " + st["reason"], False)
            return

        self.write_button.setEnabled(False)
        self.progress.setValue(5)
        self.set_status("Запись...")

        try:
            value = self.parse_value()
            expected = encode_value(value)

            # 1. Сессия записи.
            self.progress.setValue(20)
            self.open_programmer()

            before = self.read_bytes(VALUE_OFFSET, VALUE_SIZE)

            self.progress.setValue(45)
            self.write_bytes(VALUE_OFFSET, expected)

            self.close_programmer()

            # Ожидаем внутренний цикл записи EEPROM.
            self.progress.setValue(65)
            time.sleep(0.15)

            # 2. Новая сессия проверки.
            self.progress.setValue(80)
            self.open_programmer()

            actual = None
            for _ in range(10):
                try:
                    actual = self.read_bytes(VALUE_OFFSET, VALUE_SIZE)
                    if actual == expected:
                        break
                except Exception:
                    pass
                time.sleep(0.05)

            if actual != expected:
                raise RuntimeError("Проверка записи не пройдена.")

            verified = decode_value(actual)
            self.progress.setValue(100)
            self.value_input.clear()
            self.value_input.setFocus()

            total = self.counters.inc(self.name)
            self.counter_lbl.setText(str(total))

            self.set_status("Успех: записано %.2f  ·  прошивка № %d" % (verified, total), True)

        except Exception as exc:
            self.progress.setValue(0)
            self.set_status("Ошибка: %s" % exc, False)

        finally:
            self.close_programmer()
            self.write_button.setEnabled(True)

    def closeEvent(self, event):
        self.close_programmer()
        event.accept()


# ═══════════════════════════════════════════════════════════════════════════
#  Активация
# ═══════════════════════════════════════════════════════════════════════════

class ActivationDialog(QtWidgets.QDialog):
    def __init__(self, st):
        super().__init__()
        self.st = st
        self.setWindowTitle("Активация MT Writer")
        self.setFixedWidth(540)
        self.setStyleSheet(APP_STYLE)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 20)
        v.setSpacing(12)

        title = QtWidgets.QLabel("АКТИВАЦИЯ ПРОГРАММЫ")
        title.setObjectName("TitleLabel")
        title.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(title)

        hint = QtWidgets.QLabel("Программа работает только на одном компьютере.\n"
                                "Отправьте код поставщику и введите полученный ключ.")
        hint.setObjectName("HintLabel")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setWordWrap(True)
        v.addWidget(hint)

        cap = QtWidgets.QLabel("КОД ЭТОГО КОМПЬЮТЕРА")
        cap.setObjectName("CounterCaption")
        cap.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(cap)

        self.code = QtWidgets.QLineEdit(self.st["machine_code"])
        self.code.setReadOnly(True)
        self.code.setAlignment(QtCore.Qt.AlignCenter)
        self.code.setStyleSheet("color:#7ff0ac;font-size:20px;")
        v.addWidget(self.code)

        copy = QtWidgets.QPushButton("Скопировать код")
        copy.setObjectName("Ghost")
        copy.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(self.st["machine_code"]))
        v.addWidget(copy)

        cap2 = QtWidgets.QLabel("КЛЮЧ АКТИВАЦИИ")
        cap2.setObjectName("CounterCaption")
        cap2.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(cap2)

        self.key = QtWidgets.QLineEdit()
        self.key.setPlaceholderText("XXX-XXX-XXX")
        self.key.setAlignment(QtCore.Qt.AlignCenter)
        self.key.setStyleSheet("font-size:18px;")
        self.key.returnPressed.connect(self.try_activate)
        v.addWidget(self.key)

        self.msg = QtWidgets.QLabel(self.st["reason"] or "Введите ключ")
        self.msg.setWordWrap(True)
        self.msg.setAlignment(QtCore.Qt.AlignCenter)
        self.msg.setMinimumHeight(44)
        self.msg.setStyleSheet("color:#93a1b8;")
        v.addWidget(self.msg)

        row = QtWidgets.QHBoxLayout()
        ok = QtWidgets.QPushButton("Активировать")
        ok.clicked.connect(self.try_activate)
        row.addWidget(ok, 2)
        q = QtWidgets.QPushButton("Выход")
        q.setObjectName("Ghost")
        q.clicked.connect(self.reject)
        row.addWidget(q, 1)
        v.addLayout(row)
        self.key.setFocus()

    def try_activate(self):
        ok, message = activate(self.key.text())
        self.msg.setStyleSheet("color:#7ff0ac;" if ok else "color:#ff9cab;")
        self.msg.setText(message)
        if ok:
            QtCore.QTimer.singleShot(500, self.accept)


# ═══════════════════════════════════════════════════════════════════════════
#  Главное окно
# ═══════════════════════════════════════════════════════════════════════════

class MainWindow(QtWidgets.QWidget):
    def __init__(self, st):
        super().__init__()
        self.st = st
        self.counters = Counters(["200_MT", "310_MT"])
        self.setWindowTitle("MT Writer — 200_MT / 310_MT")
        self.setFixedSize(680, 560)
        self.setStyleSheet(APP_STYLE)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 10)
        root.setSpacing(8)

        self.tabs = QtWidgets.QTabWidget()
        self.tab_objs = {}
        for name in ("200_MT", "310_MT"):
            tab = WriterTab(name, self.counters, self.check_license)
            self.tabs.addTab(tab, name)
            self.tab_objs[name] = tab
        root.addWidget(self.tabs)

        self.footer = QtWidgets.QLabel()
        self.footer.setObjectName("Footer")
        self.footer.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(self.footer)
        self.update_footer()

    def update_footer(self):
        self.footer.setText("%s   ·   ПК: %s" % (license_line(self.st), self.st["machine_code"]))

    def check_license(self):
        self.st = check_license()
        self.update_footer()
        return self.st

    def closeEvent(self, event):
        for tab in self.tab_objs.values():
            tab.close_programmer()
        event.accept()


# ═══════════════════════════════════════════════════════════════════════════
#  Точка входа + встроенный генератор ключей
# ═══════════════════════════════════════════════════════════════════════════

def run_keygen(argv):
    if not argv:
        print("Код этого компьютера:", machine_code())
        print("Использование: python MT_Writer.py keygen КОД [дней]")
        return 0
    code = argv[0]
    days = int(argv[1]) if len(argv) > 1 else 0
    try:
        key = generate_key(code, days)
    except ValueError as exc:
        print("Ошибка:", exc)
        return 1
    print("Компьютер:", _fmt_code(code))
    print("Срок:     ", "бессрочно" if days <= 0 else "%d дн." % days)
    print("Ключ:     ", key)
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() == "keygen":
        return run_keygen(sys.argv[2:])

    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)

    st = check_license()
    if not st["valid"]:
        dlg = ActivationDialog(st)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return 0
        st = check_license()
        if not st["valid"]:
            return 0

    win = MainWindow(st)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
