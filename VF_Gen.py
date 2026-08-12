# -*- coding: utf-8 -*-
# VF Gen - odin fayl (self-contained). Sborka: pyinstaller --onefile --windowed VF_Gen.py
import glob
import os
import shutil
import subprocess
import sys
import tempfile

from PyQt5 import QtCore, QtGui, QtWidgets

if getattr(sys, "frozen", False):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")

# ===== vf_storage =====
# -*- coding: utf-8 -*-
"""
Где программа хранит свои данные (лицензию и счётчики прошивок).

Приоритет:
1. Папка, заданная переменной окружения VF_DATA_DIR.
2. Папка рядом с .exe (или рядом со скриптом) — если в неё можно писать.
3. %APPDATA%\\VF_Gen (Windows) / ~/.local/share/VF_Gen — если папка
   программы только для чтения (например, установка в Program Files).

Файлы пишутся атомарно: сначала во временный файл, потом os.replace, —
чтобы счётчик не терялся при выключении питания посреди записи.
"""

import json
import os
import sys
import tempfile

_APP_FOLDER = 'VF_Gen'
_cached_dir = None


def program_dir():
    """Папка, из которой запущена программа."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _is_writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, '.write_test')
        with open(probe, 'w'):
            pass
        os.remove(probe)
        return True
    except Exception:
        return False


def app_data_dir():
    """Папка для license.key и counters.json (создаётся при необходимости)."""
    global _cached_dir
    if _cached_dir:
        return _cached_dir

    override = os.environ.get('VF_DATA_DIR')
    if override and _is_writable(override):
        _cached_dir = os.path.abspath(override)
        return _cached_dir

    near_exe = program_dir()
    if _is_writable(near_exe):
        _cached_dir = near_exe
        return _cached_dir

    if os.name == 'nt':
        root = os.environ.get('APPDATA') or os.path.expanduser('~')
    else:
        root = (os.environ.get('XDG_DATA_HOME')
                or os.path.join(os.path.expanduser('~'), '.local', 'share'))

    fallback = os.path.join(root, _APP_FOLDER)
    os.makedirs(fallback, exist_ok=True)
    _cached_dir = fallback
    return _cached_dir


def data_path(filename):
    return os.path.join(app_data_dir(), filename)


def read_json(filename, default=None):
    try:
        with open(data_path(filename), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return default


def write_json(filename, data):
    """Атомарная запись JSON. Возвращает True при успехе."""
    target = data_path(filename)
    directory = os.path.dirname(target)
    os.makedirs(directory, exist_ok=True)

    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=directory, prefix='.tmp_', suffix='.json')
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
        return True
    except Exception:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass
        return False

# ===== vf_license =====
# -*- coding: utf-8 -*-
"""
Привязка программы к конкретному компьютеру (офлайн, без интернета).

Схема работы
────────────
1. На компьютере клиента считается «Код компьютера» — отпечаток железа/ОС
   вида  A1B2C-D3E4F-6789A-BCDEF.
2. Клиент присылает этот код вам.
3. Вы генерируете ключ:  python keygen_vf.py A1B2C-D3E4F-6789A-BCDEF
4. Клиент вводит ключ в окне активации. Ключ сохраняется в license.key
   рядом с программой и проверяется при каждом запуске и перед каждой
   записью в EEPROM.

Ключ подписан HMAC-SHA256 от кода компьютера, поэтому на другом ПК
не работает: скопированный license.key там просто не пройдёт проверку.

ВАЖНО: секрет SECRET ниже нужно заменить своим перед сборкой .exe,
и тот же секрет использовать в keygen_vf.py.
"""

import base64
import binascii
import hashlib
import hmac
import os
import platform
import struct
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta


# ── Секрет подписи ключей ─────────────────────────────────────────────────────
# ЗАМЕНИТЕ на свою длинную случайную строку перед распространением программы.
DEFAULT_SECRET = 'vf-gen-license-secret-change-me-2024'
SECRET = os.environ.get('VF_LICENSE_SECRET', DEFAULT_SECRET).encode('utf-8')

KEY_VERSION = 1
LICENSE_FILE = 'license_vf.key'
_EPOCH = date(2020, 1, 1)
_SIG_LEN = 10
_CLOCK_TOLERANCE_DAYS = 2


# ══════════════════════════════════════════════════════════════════════════════
# Отпечаток компьютера
# ══════════════════════════════════════════════════════════════════════════════

def _win_machine_guid():
    """MachineGuid из реестра — самый стабильный идентификатор Windows."""
    try:
        import winreg
        for view in (getattr(winreg, 'KEY_WOW64_64KEY', 0), 0):
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r'SOFTWARE\Microsoft\Cryptography',
                    0, winreg.KEY_READ | view,
                )
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
    """Серийный номер системного тома."""
    try:
        import ctypes
        root = os.environ.get('SystemDrive', 'C:') + '\\'
        serial = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root), None, 0,
            ctypes.byref(serial), None, None, None, 0,
        )
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
        out = subprocess.run(
            ['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
            capture_output=True, text=True, timeout=10,
        ).stdout
        for line in out.splitlines():
            if 'IOPlatformUUID' in line:
                return line.split('=')[-1].strip().strip('"')
    except Exception:
        pass
    return None


def _mac_address():
    """Запасной вариант: MAC-адрес (слабее, но лучше, чем ничего)."""
    node = uuid.getnode()
    if node and not (node >> 40) & 0x01:   # не случайно сгенерированный адрес
        return '%012X' % node
    return None


def _sources():
    """Источники отпечатка по приоритету — берётся первый доступный."""
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


def get_machine_code():
    """Код компьютера вида A1B2C-D3E4F-6789A-BCDEF."""
    override = os.environ.get('VF_MACHINE_CODE')
    if override:
        return normalize(override)

    tag, value = _raw_fingerprint()
    if not value:
        tag, value = 'host', platform.node() or 'unknown-host'
    payload = ('%s:%s:%s' % (tag, value, platform.system())).encode('utf-8', 'replace')
    return _format_code(hashlib.sha256(payload).hexdigest())


def get_fingerprint_source():
    if os.environ.get('VF_MACHINE_CODE'):
        return 'override'
    tag, _ = _raw_fingerprint()
    return tag or 'host'


def normalize(value):
    """Убирает пробелы/дефисы и приводит к виду XXXXX-XXXXX-…"""
    cleaned = ''.join(ch for ch in (value or '').upper() if ch.isalnum())
    return '-'.join(cleaned[i:i + 5] for i in range(0, len(cleaned), 5))


def _canonical(value):
    return ''.join(ch for ch in (value or '').upper() if ch.isalnum())


# ══════════════════════════════════════════════════════════════════════════════
# Ключи активации
# ══════════════════════════════════════════════════════════════════════════════

def _signature(machine_code, version, days, secret=None):
    message = ('%s|%d|%d' % (_canonical(machine_code), version, days)).encode('utf-8')
    return hmac.new(secret or SECRET, message, hashlib.sha256).digest()[:_SIG_LEN]


def generate_key(machine_code, valid_days=0, secret=None):
    """Ключ для указанного кода компьютера. valid_days=0 — бессрочно."""
    code = _canonical(machine_code)
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
    blob += _signature(code, KEY_VERSION, expiry_days, secret)
    encoded = base64.b32encode(blob).decode('ascii').rstrip('=')
    return '-'.join(encoded[i:i + 7] for i in range(0, len(encoded), 7))


def verify_key(key, machine_code=None, secret=None, today=None):
    """Проверка ключа. -> {'valid', 'reason', 'expires', 'perpetual'}"""
    machine_code = machine_code or get_machine_code()
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

    if not hmac.compare_digest(_signature(machine_code, version, expiry_days, secret), blob[3:]):
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


# ══════════════════════════════════════════════════════════════════════════════
# Хранение и проверка лицензии
# ══════════════════════════════════════════════════════════════════════════════

def _guard(key, last_seen):
    message = ('%s|%s' % (_canonical(key), last_seen)).encode('utf-8')
    return hmac.new(SECRET, message, hashlib.sha256).hexdigest()[:32]


def save_license(key, machine_code):
    last_seen = date.today().isoformat()
    data = {
        'key': normalize(key),
        'machine': machine_code,
        'activated_at': datetime.now().isoformat(timespec='seconds'),
        'last_seen': last_seen,
        'guard': _guard(key, last_seen),
    }
    write_json(LICENSE_FILE, data)
    return data


def _touch_last_seen(data):
    """Отметка последнего запуска — защита от перевода часов назад."""
    today = date.today().isoformat()
    if data.get('last_seen') == today:
        return
    data['last_seen'] = today
    data['guard'] = _guard(data.get('key', ''), today)
    write_json(LICENSE_FILE, data)


def check_license():
    """Полная проверка лицензии на текущем компьютере."""
    machine_code = get_machine_code()
    status = {
        'valid': False,
        'reason': 'Программа не активирована на этом компьютере',
        'machine_code': machine_code,
        'expires': None,
        'perpetual': False,
        'days_left': None,
        'activated_at': None,
        'source': get_fingerprint_source(),
    }

    data = read_json(LICENSE_FILE)
    if not data or not data.get('key'):
        return status

    key = data.get('key', '')
    status['activated_at'] = data.get('activated_at')

    result = verify_key(key, machine_code)
    if not result['valid']:
        status['reason'] = result['reason']
        return status

    last_seen = data.get('last_seen')
    if last_seen and data.get('guard') == _guard(key, last_seen):
        try:
            seen = date.fromisoformat(last_seen)
            if date.today() < seen - timedelta(days=_CLOCK_TOLERANCE_DAYS):
                status['reason'] = ('Системная дата переведена назад. '
                                    'Установите правильную дату и запустите программу снова.')
                return status
        except ValueError:
            pass

    status.update(valid=True, reason=None,
                  expires=result['expires'], perpetual=result['perpetual'])
    if result['expires']:
        status['days_left'] = (result['expires'] - date.today()).days

    _touch_last_seen(data)
    return status


def activate(key):
    """Проверяет ключ и сохраняет лицензию. -> (успех, сообщение)"""
    machine_code = get_machine_code()
    result = verify_key(key, machine_code)
    if not result['valid']:
        return False, result['reason']

    save_license(key, machine_code)
    if result['perpetual']:
        return True, 'Программа активирована на этом компьютере (бессрочно).'
    return True, ('Программа активирована на этом компьютере до %s.'
                  % result['expires'].strftime('%d.%m.%Y'))


def status_text(status):
    """Короткая строка для панели окна."""
    if not status['valid']:
        return 'Лицензия: не активирована'
    if status['perpetual']:
        return 'Лицензия: бессрочная'
    return ('Лицензия: до %s (%d дн.)'
            % (status['expires'].strftime('%d.%m.%Y'), status['days_left']))

# ===== vf_counters =====
# -*- coding: utf-8 -*-
"""
Счётчик сгенерированных .hex-файлов.

Счётчик увеличивается только после успешного сохранения файла.
Хранится в counters_vf.json рядом с программой, поэтому не сбрасывается
при перезапуске, обновлении программы или перезагрузке компьютера.

Файл подписан контрольной суммой: если счётчики правили вручную,
программа это видит и показывает предупреждение (но продолжает работать,
считая дальше от найденного значения).
"""

import hashlib
import hmac
import json
from datetime import datetime


COUNTERS_FILE = 'counters_vf.json'
FORMAT_VERSION = 1

# Отдельный от лицензии секрет — только для контрольной суммы файла счётчиков.
_GUARD_SECRET = b'vf-gen-counters-guard-2024'


def _ctr_guard(counters):
    payload = json.dumps(counters, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hmac.new(_GUARD_SECRET, payload, hashlib.sha256).hexdigest()[:32]


class Counters:
    """Счётчики по именам."""

    def __init__(self, names):
        self.names = list(names)
        self.tampered = False
        self.readonly = False
        self._data = self._load()

    # ── загрузка/сохранение ───────────────────────────────────────────────────

    def _blank(self):
        return {name: {'count': 0, 'last_value': None, 'last_time': None}
                for name in self.names}

    def _load(self):
        raw = read_json(COUNTERS_FILE)
        counters = self._blank()

        if not raw:
            return counters

        stored = raw.get('counters')
        if not isinstance(stored, dict):
            return counters

        if raw.get('guard') != _ctr_guard(stored):
            self.tampered = True

        for name in self.names:
            item = stored.get(name)
            if not isinstance(item, dict):
                continue
            try:
                count = int(item.get('count', 0))
            except (TypeError, ValueError):
                count = 0
            counters[name] = {
                'count': max(0, count),
                'last_value': item.get('last_value'),
                'last_time': item.get('last_time'),
            }
        return counters

    def _save(self):
        payload = {
            'version': FORMAT_VERSION,
            'counters': self._data,
            'guard': _ctr_guard(self._data),
        }
        ok = write_json(COUNTERS_FILE, payload)
        self.readonly = not ok
        return ok

    # ── доступ ────────────────────────────────────────────────────────────────

    def count(self, name):
        return self._data.get(name, {}).get('count', 0)

    def last_value(self, name):
        return self._data.get(name, {}).get('last_value')

    def last_time(self, name):
        return self._data.get(name, {}).get('last_time')

    def increment(self, name, value=None):
        """Записать факт сохранения файла. Возвращает новое значение счётчика."""
        item = self._data.setdefault(
            name, {'count': 0, 'last_value': None, 'last_time': None})
        item['count'] = int(item.get('count', 0)) + 1
        item['last_value'] = value
        item['last_time'] = datetime.now().isoformat(timespec='seconds')
        self.tampered = False
        self._save()
        return item['count']

    def summary(self, name):
        """Строка вида «последняя: 10.08.2026 17:55 · 3456.42»."""
        stamp = self.last_time(name)
        value = self.last_value(name)
        if not stamp:
            return 'записей ещё не было'
        try:
            shown = datetime.fromisoformat(stamp).strftime('%d.%m.%Y %H:%M')
        except ValueError:
            shown = stamp
        if value is None:
            return 'последняя: %s' % shown
        return 'последняя: %s · %.2f' % (shown, float(value))

# ===== vf_core =====
# -*- coding: utf-8 -*-
"""
Математика генератора ce101 r5 145 — без Qt, поэтому легко проверяется тестами.

Формат прошивки
───────────────
В EEPROM пишутся два блока по 512 байт:

  0x1E000  базовый блок — повторяющийся триплет [b1, b3, b2]  (b2 и b3 переставлены!)
  0x1E200  дробный блок — N триплетов «01 00 00», остальное нули

Показание прибора:

  R = 0.85 * idx(b1)
    + 435.20 * (b2 // 2) + 5.95 * (b2 & 1)
    + 111411.20 * (b3 // 2) + 2.55 * (b3 & 1)
    + 0.03 * N_дробных

  idx(b1) = (b1 & ~0x06) + 256*(бит 0x04) + 65536*(бит 0x02)

Всё это кратно 0.01, поэтому внутри модуля считаем в сотых долях (целыми),
чтобы не накапливать ошибку float:

  R_сотых = 85 * U + 3 * N,  где U = idx + 512*(b2>>1) + 7*(b2&1)
                                     + 131072*(b3>>1) + 3*(b3&1)

Почему исходная программа «не все числа» выдаёт
───────────────────────────────────────────────
1. Без дробного блока показание всегда кратно 0.85, а из-за структуры b1
   достижимы только 75% значений U (пропущены остатки 2, 5, 6 по модулю 8).
   Точно попасть в целое число удаётся лишь в ~6% случаев, средняя ошибка
   0.36, максимальная 1.20.
2. Дробный блок (шаг 0.03) в интерфейсе был скрыт — а именно он позволяет
   попасть в цель точно: 0.85 и 0.03 взаимно просты в сотых долях (85 и 3),
   поэтому подбором N = 0..170 цель берётся ровно.
3. Перебор был ограничен b3 <= 0x0F, что срезало диапазон на 891 292.15.
   Полный b3 поднимает потолок до 14 260 636.15.
4. Старый решатель брал только floor/ceil от idx и, если оба значения
   оказывались недопустимыми, пропускал вариант целиком.
"""

import bisect

# ── Параметры прошивки ────────────────────────────────────────────────────────
BASE_ADDR = 0x1E000
FRAC_ADDR = 0x1E200
BLOCK_SIZE = 512
TRIPLET_LEN = 3
TRIP_COUNT = BLOCK_SIZE // TRIPLET_LEN      # 170 дробных триплетов

FRAC_STEP_C = 3         # 0.03 в сотых
UNIT_C = 85             # 0.85 в сотых
B3_MAX_ORIGINAL = 0x0F  # ограничение старой программы
B3_MAX_FULL = 0xFF


# ── Соответствие b1 <-> idx ───────────────────────────────────────────────────

def _idx_from_b1(b1):
    base = b1 & ~0x06
    return base + (256 if b1 & 0x04 else 0) + (65536 if b1 & 0x02 else 0)


_IDX_TO_B1 = {}
for _b1 in range(256):
    _IDX_TO_B1.setdefault(_idx_from_b1(_b1), _b1)
IDX_VALUES = sorted(_IDX_TO_B1)             # 256 достижимых idx, максимум 66041


def b1_from_idx(idx):
    return _IDX_TO_B1.get(idx)


# ── Показание ─────────────────────────────────────────────────────────────────

def units(b1, b2, b3):
    """U — показание в единицах по 0.85 (без дробного блока)."""
    return (_idx_from_b1(b1)
            + 512 * (b2 >> 1) + 7 * (b2 & 1)
            + 131072 * (b3 >> 1) + 3 * (b3 & 1))


def reading_centi(b1, b2, b3, n_frac=0):
    """Показание в сотых долях (целое число)."""
    return UNIT_C * units(b1, b2, b3) + FRAC_STEP_C * n_frac


def reading(b1, b2, b3, n_frac=0):
    """Показание как число с плавающей точкой."""
    return reading_centi(b1, b2, b3, n_frac) / 100.0


def max_reading(b3_max=B3_MAX_FULL):
    """Максимум, который вообще можно записать при заданном пределе b3."""
    return reading(0xFF, 0xFF, b3_max, TRIP_COUNT if b3_max >= 0 else 0)


# ── Подбор ────────────────────────────────────────────────────────────────────

class Candidate:
    """Один вариант прошивки."""

    __slots__ = ('b1', 'b2', 'b3', 'n_frac', 'centi', 'target_centi')

    def __init__(self, b1, b2, b3, n_frac, centi, target_centi):
        self.b1 = b1
        self.b2 = b2
        self.b3 = b3
        self.n_frac = n_frac
        self.centi = centi
        self.target_centi = target_centi

    @property
    def value(self):
        return self.centi / 100.0

    @property
    def base_value(self):
        """Показание без дробного блока."""
        return (self.centi - FRAC_STEP_C * self.n_frac) / 100.0

    @property
    def error(self):
        return abs(self.centi - self.target_centi) / 100.0

    @property
    def exact(self):
        return self.centi == self.target_centi

    def triplet(self):
        """Байты так, как они лежат в файле: b1, b3, b2."""
        return bytes((self.b1, self.b3, self.b2))

    def __repr__(self):
        return ('Candidate(b1=%02X b2=%02X b3=%02X n=%d -> %.2f, err=%.2f)'
                % (self.b1, self.b2, self.b3, self.n_frac, self.value, self.error))


def solve(target, use_frac=True, b3_max=B3_MAX_ORIGINAL, max_results=3, idx_window=8):
    """Подбирает варианты для заданного показания.

    target     — желаемое значение (float или строка с числом);
    use_frac   — разрешить дробный блок 0.03 (именно он даёт точное попадание);
    b3_max     — верхний предел b3 (0x0F — как в старой программе, 0xFF — полный);
    Возвращает список Candidate, отсортированный по ошибке.
    """
    target_c = int(round(float(target) * 100))
    if target_c < 0:
        raise ValueError('Значение не может быть отрицательным.')

    frac_max = TRIP_COUNT if use_frac else 0
    best = {}

    for b3 in range(0, min(255, b3_max) + 1):
        t3 = 131072 * (b3 >> 1) + 3 * (b3 & 1)
        if UNIT_C * t3 > target_c + UNIT_C * IDX_VALUES[-1]:
            break
        for b2 in range(256):
            t = t3 + 512 * (b2 >> 1) + 7 * (b2 & 1)
            rest_c = target_c - UNIT_C * t
            if rest_c < -UNIT_C * IDX_VALUES[-1]:
                continue

            # Идеальный idx: дробный блок только прибавляет, поэтому целимся
            # чуть ниже цели и добираем остаток шагами по 0.03.
            ideal = rest_c / UNIT_C
            pos = bisect.bisect_left(IDX_VALUES, ideal)

            for k in range(pos - idx_window, pos + idx_window + 1):
                if not 0 <= k < len(IDX_VALUES):
                    continue
                idx = IDX_VALUES[k]
                base_c = UNIT_C * (t + idx)
                if base_c < 0:
                    continue

                n = 0
                if frac_max:
                    n = (target_c - base_c) // FRAC_STEP_C
                    n = max(0, min(frac_max, n))

                for n_try in {n, min(frac_max, n + 1)}:
                    centi = base_c + FRAC_STEP_C * n_try
                    b1 = _IDX_TO_B1[idx]
                    key = (b1, b2, b3, n_try)
                    if key not in best:
                        best[key] = Candidate(b1, b2, b3, n_try, centi, target_c)

    if not best:
        return []

    ranked = sorted(
        best.values(),
        # при равной ошибке предпочитаем меньше дробных триплетов и меньший b3
        key=lambda c: (abs(c.centi - target_c), c.n_frac, c.b3, c.b2, c.b1),
    )

    # Оставляем варианты с разным результатом, чтобы список не дублировался.
    result, seen = [], set()
    for cand in ranked:
        if cand.centi in seen:
            continue
        seen.add(cand.centi)
        result.append(cand)
        if len(result) >= max_results:
            break
    return result


# ── Сборка блоков и Intel HEX ─────────────────────────────────────────────────

def make_base_block(b1, b2, b3):
    """Базовый блок: повтор триплета [b1, b3, b2] (b2 и b3 переставлены)."""
    trip = bytes((b1 & 0xFF, b3 & 0xFF, b2 & 0xFF))
    reps = BLOCK_SIZE // TRIPLET_LEN + 2
    return (trip * reps)[:BLOCK_SIZE]


def make_frac_block(n_ones):
    """Дробный блок: N триплетов «01 00 00», дальше нули."""
    n = max(0, min(TRIP_COUNT, int(n_ones)))
    blob = bytes((0x01, 0x00, 0x00)) * n
    return blob.ljust(BLOCK_SIZE, b'\x00')[:BLOCK_SIZE]


def _record(count, addr, rectype, payload):
    body = [count, (addr >> 8) & 0xFF, addr & 0xFF, rectype] + list(payload)
    checksum = (~(sum(body) & 0xFF) + 1) & 0xFF
    return ':' + ''.join('%02X' % b for b in body) + '%02X' % checksum


def build_ihex(blocks):
    """blocks — список (адрес, данные). Возвращает текст Intel HEX."""
    lines = []
    current_ela = None

    for addr_base, data in blocks:
        ela = (addr_base >> 16) & 0xFFFF
        if ela != current_ela:
            lines.append(_record(2, 0x0000, 0x04, bytes(((ela >> 8) & 0xFF, ela & 0xFF))))
            current_ela = ela
        base16 = addr_base & 0xFFFF
        for off in range(0, len(data), 16):
            chunk = data[off:off + 16]
            lines.append(_record(len(chunk), base16 + off, 0x00, chunk))

    lines.append(':00000001FF')
    return '\n'.join(lines) + '\n'


def build_hex_for(candidate, base_addr=BASE_ADDR, frac_addr=FRAC_ADDR):
    """Готовый Intel HEX для варианта: базовый блок + дробный, если он нужен."""
    blocks = [(base_addr, make_base_block(candidate.b1, candidate.b2, candidate.b3))]
    if candidate.n_frac > 0:
        blocks.append((frac_addr, make_frac_block(candidate.n_frac)))
    return build_ihex(blocks)


def parse_ihex(text):
    """Разбор Intel HEX обратно в {адрес: байт} — для самопроверки."""
    memory = {}
    ela = 0
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(':'):
            continue
        raw = bytes.fromhex(line[1:])
        if (sum(raw) & 0xFF) != 0:
            raise ValueError('Неверная контрольная сумма строки: %s' % line)
        count, addr, rectype = raw[0], (raw[1] << 8) | raw[2], raw[3]
        payload = raw[4:4 + count]
        if rectype == 0x04:
            ela = (payload[0] << 8) | payload[1]
        elif rectype == 0x00:
            for i, byte in enumerate(payload):
                memory[(ela << 16) + addr + i] = byte
        elif rectype == 0x01:
            break
    return memory


def format_value(value):
    """7035.0 -> «7035», 7034.6 -> «7034.6» — для имени файла и таблицы."""
    text = ('%.2f' % value).rstrip('0').rstrip('.')
    return text if text else '0'

# ===== GUI / auto =====
COUNTER_NAME = "hex"


# ── Прошивка через PICkit (ipecmd) ────────────────────────────────────────────
PIC_DEVICE = "16F1934"       # модель чипа (параметр -P)
PIC_TOOL = "PPK3"            # PICkit 3 (для PK4 → PPK4, PK5 → PPK5)
EEPROM_ONLY = True           # писать ТОЛЬКО EEPROM, не трогая прошивку (-ME)
POWER_FROM_TOOL = False      # питать чип от PICkit? обычно нет
VDD = "5.0"


def find_ipecmd():
    """Ищет ipecmd.exe от MPLAB IPE где угодно в папке Microchip.
    Можно жёстко задать путь переменной окружения IPECMD или файлом
    ipecmd_path.txt рядом с программой."""
    # 1) явный путь: переменная окружения
    env = os.environ.get("IPECMD")
    if env and os.path.isfile(env):
        return env
    # 2) явный путь: файл ipecmd_path.txt рядом с exe
    try:
        base = (os.path.dirname(os.path.abspath(sys.executable))
                if getattr(sys, "frozen", False)
                else os.path.dirname(os.path.abspath(__file__)))
        txt = os.path.join(base, "ipecmd_path.txt")
        if os.path.isfile(txt):
            p = open(txt, encoding="utf-8").read().strip().strip('"')
            if p and os.path.isfile(p):
                return p
    except Exception:
        pass
    # 3) в PATH
    w = shutil.which("ipecmd") or shutil.which("ipecmd.exe")
    if w:
        return w
    if os.name != "nt":
        return None
    # 4) рекурсивный поиск по всей папке Microchip (любая версия/путь)
    roots = []
    for var in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        p = os.environ.get(var)
        if p:
            roots.append(os.path.join(p, "Microchip"))
    roots += [r"C:\Program Files\Microchip", r"C:\Program Files (x86)\Microchip"]
    hits, seen = [], set()
    for base in roots:
        low = base.lower()
        if low in seen or not os.path.isdir(base):
            continue
        seen.add(low)
        hits += glob.glob(os.path.join(base, "**", "ipecmd.exe"), recursive=True)
    return sorted(hits)[-1] if hits else None

# ── Палитра и стиль ───────────────────────────────────────────────────────────
APP_STYLE = """
    QWidget {
        background: #0e1117;
        color: #e8ecf4;
        font-family: 'Segoe UI';
        font-size: 14px;
    }
    QLabel#Title {
        font-size: 22px;
        font-weight: 900;
        color: #ffffff;
    }
    QLabel#Subtitle { font-size: 13px; color: #93a1b8; }
    QLabel#FieldLabel {
        font-size: 12px; font-weight: 700; letter-spacing: .04em;
        color: #93a1b8; text-transform: uppercase;
    }
    QLineEdit {
        background: #161c26;
        border: 2px solid #2b3648;
        border-radius: 12px;
        padding: 12px 14px;
        font-size: 24px;
        font-weight: 700;
        color: #ffffff;
        selection-background-color: #3f6df6;
    }
    QLineEdit:focus { border-color: #6b8cff; }
    QPushButton {
        background: #3f6df6;
        border: 2px solid #6f91ff;
        border-radius: 12px;
        padding: 12px 18px;
        font-size: 16px;
        font-weight: 800;
        color: white;
    }
    QPushButton:hover { background: #4e79ff; }
    QPushButton:pressed { background: #345acb; }
    QPushButton:disabled { background: #2b3240; border-color: #3a4352; color: #8d96a8; }
    QPushButton#Ghost {
        background: #1a2230; border-color: #2b3648; color: #cdd6e6;
        font-size: 14px; font-weight: 700;
    }
    QPushButton#Ghost:hover { background: #222c3d; }
    QCheckBox { font-size: 13px; color: #cdd6e6; spacing: 8px; }
    QCheckBox::indicator {
        width: 20px; height: 20px; border-radius: 6px;
        border: 2px solid #2b3648; background: #161c26;
    }
    QCheckBox::indicator:checked { background: #3f6df6; border-color: #6f91ff; }
    QFrame#Card {
        background: #131a24; border: 2px solid #222c3b; border-radius: 16px;
    }
    QFrame#CandCard {
        background: #131a24; border: 2px solid #222c3b; border-radius: 14px;
    }
    QFrame#CandCard[best="true"] { border-color: #2fc46f; background: #12251b; }
    QLabel#CandValue { font-size: 24px; font-weight: 900; color: #ffffff; }
    QLabel#CandValueBest { font-size: 24px; font-weight: 900; color: #7ff0ac; }
    QLabel#CandMeta { font-size: 12px; color: #93a1b8; }
    QLabel#CandErr { font-size: 12px; font-weight: 700; }
    QLabel#Counter { font-size: 30px; font-weight: 900; color: #7ff0ac; }
    QLabel#CounterCap { font-size: 11px; font-weight: 800; color: #8d96a8; }
    QLabel#Footer { font-size: 11px; color: #7a869c; }
    QTextEdit {
        background: #10151d; border: 2px solid #222c3b; border-radius: 12px;
        color: #a8b3c7; font-family: 'Consolas','Courier New',monospace; font-size: 12px;
    }
    QToolTip { background: #1a2230; color: #e8ecf4; border: 1px solid #2b3648; }
"""


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# ══════════════════════════════════════════════════════════════════════════════
# Анимация запуска
# ══════════════════════════════════════════════════════════════════════════════

class SplashScreen(QtWidgets.QWidget):
    """Заставка с плавным появлением, вращающимся кольцом и прогрессом."""

    finished = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__(None,
                         QtCore.Qt.FramelessWindowHint |
                         QtCore.Qt.WindowStaysOnTopHint |
                         QtCore.Qt.SplashScreen)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setFixedSize(460, 300)
        self._angle = 0
        self._progress = 0.0
        self._opacity = 0.0
        self._center_to_screen()

        self._spin = QtCore.QTimer(self)
        self._spin.timeout.connect(self._on_spin)
        self._fade = QtCore.QTimer(self)
        self._fade.timeout.connect(self._on_fade_in)

    def _center_to_screen(self):
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())

    def start(self):
        self.show()
        self._fade.start(16)
        self._spin.start(16)

    def _on_fade_in(self):
        self._opacity = min(1.0, self._opacity + 0.06)
        self.setWindowOpacity(self._opacity)
        if self._opacity >= 1.0:
            self._fade.stop()

    def _on_spin(self):
        self._angle = (self._angle + 6) % 360
        self._progress = min(1.0, self._progress + 0.012)
        self.update()
        if self._progress >= 1.0:
            self._spin.stop()
            QtCore.QTimer.singleShot(180, self._fade_out)

    def _fade_out(self):
        self._out = QtCore.QTimer(self)

        def step():
            self._opacity = max(0.0, self._opacity - 0.08)
            self.setWindowOpacity(self._opacity)
            if self._opacity <= 0.0:
                self._out.stop()
                self.close()
                self.finished.emit()

        self._out.timeout.connect(step)
        self._out.start(16)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        # карточка
        rect = self.rect().adjusted(10, 10, -10, -10)
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), 22, 22)
        p.fillPath(path, QtGui.QColor("#131a24"))
        pen = QtGui.QPen(QtGui.QColor("#222c3b"))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawPath(path)

        cx, cy = self.width() / 2, self.height() / 2 - 26

        # вращающееся кольцо
        ring = QtCore.QRectF(cx - 34, cy - 34, 68, 68)
        p.setPen(QtGui.QPen(QtGui.QColor("#22314a"), 6))
        p.drawArc(ring, 0, 360 * 16)
        grad_pen = QtGui.QPen(QtGui.QColor("#4e79ff"), 6, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        p.setPen(grad_pen)
        p.drawArc(ring, -self._angle * 16, 110 * 16)

        # заголовок
        p.setPen(QtGui.QColor("#ffffff"))
        p.setFont(QtGui.QFont("Segoe UI", 20, QtGui.QFont.Black))
        p.drawText(QtCore.QRectF(0, cy + 34, self.width(), 34),
                   QtCore.Qt.AlignCenter, "VF Gen")
        p.setPen(QtGui.QColor("#93a1b8"))
        p.setFont(QtGui.QFont("Segoe UI", 10))
        p.drawText(QtCore.QRectF(0, cy + 66, self.width(), 22),
                   QtCore.Qt.AlignCenter, "ce101 r5 145 · генератор прошивок")

        # прогресс-полоса
        bar_w = self.width() - 96
        bx, by = 48, self.height() - 46
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#22314a"))
        p.drawRoundedRect(QtCore.QRectF(bx, by, bar_w, 6), 3, 3)
        p.setBrush(QtGui.QColor("#4e79ff"))
        p.drawRoundedRect(QtCore.QRectF(bx, by, bar_w * self._progress, 6), 3, 3)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
# Фоновый подбор (чтобы окно не подвисало)
# ══════════════════════════════════════════════════════════════════════════════

class SolveWorker(QtCore.QThread):
    done = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, target, use_frac, b3_max):
        super().__init__()
        self.target = target
        self.use_frac = use_frac
        self.b3_max = b3_max

    def run(self):
        try:
            result = solve(self.target, use_frac=self.use_frac,
                                 b3_max=self.b3_max, max_results=3)
            self.done.emit(result)
        except Exception as exc:              # noqa: BLE001
            self.failed.emit(str(exc))


class FlashWorker(QtCore.QThread):
    """Запускает ipecmd и шьёт EEPROM, не блокируя окно."""

    line = QtCore.pyqtSignal(str)
    done = QtCore.pyqtSignal(int)

    def __init__(self, ipecmd, hex_path):
        super().__init__()
        self.ipecmd = ipecmd
        self.hex_path = hex_path

    def run(self):
        args = [self.ipecmd, "-T" + PIC_TOOL, "-P" + PIC_DEVICE,
                "-F" + self.hex_path, "-ME" if EEPROM_ONLY else "-M"]
        if POWER_FROM_TOOL:
            args.append("-A" + VDD)
        args.append("-OL")
        flags = 0x08000000 if os.name == "nt" else 0     # CREATE_NO_WINDOW
        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=os.path.dirname(self.hex_path) or None,
                creationflags=flags)
            for ln in proc.stdout:
                ln = ln.rstrip()
                if ln:
                    self.line.emit(ln)
            proc.wait()
            self.done.emit(proc.returncode)
        except Exception as exc:              # noqa: BLE001
            self.line.emit("Ошибка запуска ipecmd: %s" % exc)
            self.done.emit(-1)


# ══════════════════════════════════════════════════════════════════════════════
# Карточка варианта
# ══════════════════════════════════════════════════════════════════════════════

class CandidateCard(QtWidgets.QFrame):
    save_requested = QtCore.pyqtSignal(int)

    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.setObjectName("CandCard")
        self.setMinimumHeight(70)
        self.index = index
        self.candidate = None
        self._build()

    def _build(self):
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(14)

        left = QtWidgets.QVBoxLayout()
        left.setSpacing(2)
        self.value_lbl = QtWidgets.QLabel("—")
        self.value_lbl.setObjectName("CandValue")
        self.meta_lbl = QtWidgets.QLabel("")
        self.meta_lbl.setObjectName("CandMeta")
        left.addWidget(self.value_lbl)
        left.addWidget(self.meta_lbl)
        lay.addLayout(left, 1)

        self.err_lbl = QtWidgets.QLabel("")
        self.err_lbl.setObjectName("CandErr")
        self.err_lbl.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.err_lbl)

        self.save_btn = QtWidgets.QPushButton("Сохранить .hex")
        self.save_btn.setFixedHeight(48)
        self.save_btn.clicked.connect(lambda: self.save_requested.emit(self.index))
        self.save_btn.setEnabled(False)
        lay.addWidget(self.save_btn)

    def set_candidate(self, cand, is_best):
        self.candidate = cand
        if cand is None:
            self.value_lbl.setText("—")
            self.meta_lbl.setText("")
            self.err_lbl.setText("")
            self.save_btn.setEnabled(False)
            self.setProperty("best", "false")
        else:
            self.value_lbl.setObjectName("CandValueBest" if is_best else "CandValue")
            self.value_lbl.setText(format_value(cand.value))
            note = "точное совпадение" if cand.exact else "ближайшее"
            self.meta_lbl.setText(
                "%s · база %s · дробных %d"
                % (note, format_value(cand.base_value), cand.n_frac))
            if cand.exact:
                self.err_lbl.setText("ТОЧНО")
                self.err_lbl.setStyleSheet("color:#7ff0ac;")
            else:
                self.err_lbl.setText("±%.2f" % cand.error)
                self.err_lbl.setStyleSheet("color:#ffd27f;")
            self.setProperty("best", "true" if is_best else "false")
            self.save_btn.setEnabled(True)
        self.style().unpolish(self)
        self.style().polish(self)


# ══════════════════════════════════════════════════════════════════════════════
# Активация (диалог)
# ══════════════════════════════════════════════════════════════════════════════

class ActivationDialog(QtWidgets.QDialog):
    def __init__(self, status, parent=None):
        super().__init__(parent)
        self.status = status
        self.setWindowTitle("Активация VF Gen")
        self.setFixedWidth(540)
        self.setStyleSheet(APP_STYLE)
        self._build()

    def _build(self):
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 20)
        v.setSpacing(12)

        title = QtWidgets.QLabel("Активация программы")
        title.setObjectName("Title")
        title.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(title)

        hint = QtWidgets.QLabel(
            "Программа работает только на одном компьютере.\n"
            "Отправьте код компьютера поставщику и введите полученный ключ.")
        hint.setObjectName("Subtitle")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setWordWrap(True)
        v.addWidget(hint)

        cap = QtWidgets.QLabel("КОД ЭТОГО КОМПЬЮТЕРА")
        cap.setObjectName("FieldLabel")
        cap.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(cap)

        self.code = QtWidgets.QLineEdit(self.status["machine_code"])
        self.code.setReadOnly(True)
        self.code.setAlignment(QtCore.Qt.AlignCenter)
        self.code.setStyleSheet("color:#7ff0ac; font-size:20px;")
        v.addWidget(self.code)

        copy = QtWidgets.QPushButton("Скопировать код")
        copy.setObjectName("Ghost")
        copy.clicked.connect(self._copy)
        v.addWidget(copy)

        cap2 = QtWidgets.QLabel("КЛЮЧ АКТИВАЦИИ")
        cap2.setObjectName("FieldLabel")
        cap2.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(cap2)

        self.key = QtWidgets.QLineEdit()
        self.key.setPlaceholderText("XXXXXXX-XXXXXXX-XXXXXXX")
        self.key.setAlignment(QtCore.Qt.AlignCenter)
        self.key.setStyleSheet("font-size:18px;")
        self.key.returnPressed.connect(self._activate)
        v.addWidget(self.key)

        self.msg = QtWidgets.QLabel(self.status["reason"] or "Введите ключ активации")
        self.msg.setWordWrap(True)
        self.msg.setAlignment(QtCore.Qt.AlignCenter)
        self.msg.setMinimumHeight(48)
        self.msg.setStyleSheet("color:#93a1b8;")
        v.addWidget(self.msg)

        row = QtWidgets.QHBoxLayout()
        ok = QtWidgets.QPushButton("Активировать")
        ok.clicked.connect(self._activate)
        row.addWidget(ok, 2)
        quit_btn = QtWidgets.QPushButton("Выход")
        quit_btn.setObjectName("Ghost")
        quit_btn.clicked.connect(self.reject)
        row.addWidget(quit_btn, 1)
        v.addLayout(row)

        self.key.setFocus()
        self.adjustSize()

    def _copy(self):
        QtWidgets.QApplication.clipboard().setText(self.status["machine_code"])
        self.msg.setStyleSheet("color:#93a1b8;")
        self.msg.setText("Код скопирован в буфер обмена.")

    def _activate(self):
        ok, message = activate(self.key.text())
        self.msg.setStyleSheet("color:#7ff0ac;" if ok else "color:#ff9cab;")
        self.msg.setText(message)
        if ok:
            QtCore.QTimer.singleShot(500, self.accept)


# ══════════════════════════════════════════════════════════════════════════════
# Главное окно
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QtWidgets.QWidget):
    def __init__(self, license_status):
        super().__init__()
        self.license_status = license_status
        self.counters = Counters([COUNTER_NAME])
        self.candidates = []
        self.worker = None
        self.setWindowTitle("VF Gen — ce101 r5 145")
        self.setMinimumSize(780, 730)
        self.setStyleSheet(APP_STYLE)
        self._build()
        self._appear()

    # ── интерфейс ─────────────────────────────────────────────────────────────

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(14)

        # шапка: заголовок + счётчик
        head = QtWidgets.QHBoxLayout()
        tbox = QtWidgets.QVBoxLayout()
        tbox.setSpacing(2)
        title = QtWidgets.QLabel("Генератор прошивок")
        title.setObjectName("Title")
        sub = QtWidgets.QLabel("ce101 r5 145 · авторежим: введите показание → «Записать в прибор»")
        sub.setObjectName("Subtitle")
        tbox.addWidget(title)
        tbox.addWidget(sub)
        head.addLayout(tbox, 1)

        counter_card = QtWidgets.QFrame()
        counter_card.setObjectName("Card")
        cc = QtWidgets.QVBoxLayout(counter_card)
        cc.setContentsMargins(18, 8, 18, 8)
        cc.setSpacing(0)
        cap = QtWidgets.QLabel("ЗАПИСАНО")
        cap.setObjectName("CounterCap")
        cap.setAlignment(QtCore.Qt.AlignCenter)
        self.counter_lbl = QtWidgets.QLabel("0")
        self.counter_lbl.setObjectName("Counter")
        self.counter_lbl.setAlignment(QtCore.Qt.AlignCenter)
        cc.addWidget(cap)
        cc.addWidget(self.counter_lbl)
        head.addWidget(counter_card)
        root.addLayout(head)

        # поле ввода
        input_card = QtWidgets.QFrame()
        input_card.setObjectName("Card")
        input_card.setMinimumHeight(150)
        ic = QtWidgets.QVBoxLayout(input_card)
        ic.setContentsMargins(18, 16, 18, 16)
        ic.setSpacing(12)

        lab = QtWidgets.QLabel("ЦЕЛЕВОЕ ЗНАЧЕНИЕ")
        lab.setObjectName("FieldLabel")
        ic.addWidget(lab)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)
        self.inp = QtWidgets.QLineEdit("7035")
        self.inp.setValidator(QtGui.QDoubleValidator(0.0, 1e12, 2))
        self.inp.setMinimumHeight(56)
        self.inp.returnPressed.connect(self.on_write_auto)   # Enter = записать
        row.addWidget(self.inp, 1)
        self.auto_btn = QtWidgets.QPushButton("ЗАПИСАТЬ В ПРИБОР")
        self.auto_btn.setMinimumWidth(210)
        self.auto_btn.setMinimumHeight(56)
        self.auto_btn.clicked.connect(self.on_write_auto)
        row.addWidget(self.auto_btn)
        ic.addLayout(row)

        opts = QtWidgets.QHBoxLayout()
        self.chk_frac = QtWidgets.QCheckBox("Дробный блок (точное попадание)")
        self.chk_frac.setChecked(True)
        self.chk_frac.setToolTip(
            "Записывает второй блок 0x1E200 с шагом 0.03 — позволяет попасть\n"
            "в любое число. Без него показание всегда кратно 0.85.")
        self.chk_full = QtWidgets.QCheckBox("Полный диапазон (b3 до 0xFF)")
        self.chk_full.setChecked(True)
        self.chk_full.setToolTip(
            "Снимает ограничение старой программы (b3 ≤ 0x0F).\n"
            "Потолок поднимается с 891 297 до 14 260 641.")
        opts.addWidget(self.chk_frac)
        opts.addWidget(self.chk_full)
        opts.addStretch(1)
        # ручной подбор без записи — оставлен для проверки/сохранения .hex
        self.solve_btn = QtWidgets.QPushButton("Только подобрать")
        self.solve_btn.setObjectName("Ghost")
        self.solve_btn.clicked.connect(self.on_solve)
        opts.addWidget(self.solve_btn)
        ic.addLayout(opts)
        root.addWidget(input_card)

        # варианты
        vary_lbl = QtWidgets.QLabel("ВАРИАНТЫ")
        vary_lbl.setObjectName("FieldLabel")
        root.addWidget(vary_lbl)
        self.cards = []
        for i in range(3):
            card = CandidateCard(i)
            card.save_requested.connect(self.on_save)
            self.cards.append(card)
            root.addWidget(card)

        # папка сохранения
        out_row = QtWidgets.QHBoxLayout()
        out_lbl = QtWidgets.QLabel("Папка:")
        out_lbl.setObjectName("Subtitle")
        self.outdir = QtWidgets.QLineEdit(os.getcwd())
        browse = QtWidgets.QPushButton("Обзор…")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self.on_browse)
        out_row.addWidget(out_lbl)
        out_row.addWidget(self.outdir, 1)
        out_row.addWidget(browse)
        root.addLayout(out_row)

        # лог
        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        root.addWidget(self.log)

        # подвал
        self.footer = QtWidgets.QLabel()
        self.footer.setObjectName("Footer")
        self.footer.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(self.footer)

        self._refresh_counter()
        self._refresh_footer()

        self.license_timer = QtCore.QTimer(self)
        self.license_timer.timeout.connect(self._check_license)
        self.license_timer.start(60 * 60 * 1000)

    def _appear(self):
        """Плавное появление окна."""
        self._fx = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._anim = QtCore.QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(320)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._anim.finished.connect(lambda: self.setGraphicsEffect(None))
        self._anim.start()

    # ── данные ────────────────────────────────────────────────────────────────

    def _refresh_counter(self):
        self.counter_lbl.setText(str(self.counters.count(COUNTER_NAME)))

    def _refresh_footer(self):
        self.footer.setText(
            "%s   ·   ПК: %s   ·   данные: %s"
            % (status_text(self.license_status),
               self.license_status["machine_code"], app_data_dir()))

    def _check_license(self):
        self.license_status = check_license()
        self._refresh_footer()
        return self.license_status

    # ── действия ──────────────────────────────────────────────────────────────

    def on_browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Куда сохранять .hex?", self.outdir.text())
        if d:
            self.outdir.setText(d)

    def on_solve(self):
        try:
            target = float(self.inp.text().strip().replace(",", "."))
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Введите число.")
            return
        if target < 0:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Значение не может быть отрицательным.")
            return

        ceiling = max_reading(B3_MAX_FULL if self.chk_full.isChecked()
                                   else B3_MAX_ORIGINAL)
        if target > ceiling:
            QtWidgets.QMessageBox.warning(
                self, "Вне диапазона",
                "Максимум при текущих настройках — %s.\n"
                "Включите «Полный диапазон», если он выключен." % format_value(ceiling))
            return

        self.solve_btn.setEnabled(False)
        self.solve_btn.setText("Подбор…")
        for card in self.cards:
            card.set_candidate(None, False)

        self.worker = SolveWorker(
            target,
            self.chk_frac.isChecked(),
            B3_MAX_FULL if self.chk_full.isChecked() else B3_MAX_ORIGINAL)
        self.worker.done.connect(self._on_solved)
        self.worker.failed.connect(self._on_solve_failed)
        self.worker.start()

    def _on_solved(self, candidates):
        self.candidates = candidates
        self.solve_btn.setEnabled(True)
        self.solve_btn.setText("Только подобрать")
        if not candidates:
            QtWidgets.QMessageBox.warning(self, "Не найдено", "Не удалось подобрать вариант.")
            return
        for i, card in enumerate(self.cards):
            card.set_candidate(candidates[i] if i < len(candidates) else None, i == 0)
        best = candidates[0]
        self.log.append(
            "Цель %s → b1=%02X b2=%02X b3=%02X, дробных %d = %s (%s)"
            % (self.inp.text().strip(), best.b1, best.b2, best.b3, best.n_frac,
               format_value(best.value),
               "точно" if best.exact else "±%.2f" % best.error))

    def _on_solve_failed(self, message):
        self.solve_btn.setEnabled(True)
        self.solve_btn.setText("Только подобрать")
        QtWidgets.QMessageBox.critical(self, "Ошибка", message)

    def on_save(self, index):
        if not self.license_status["valid"]:
            QtWidgets.QMessageBox.critical(
                self, "Нет лицензии",
                "Сохранение заблокировано: %s" % self.license_status["reason"])
            return
        if index >= len(self.candidates):
            return
        cand = self.candidates[index]

        out_dir = self.outdir.text().strip() or os.getcwd()
        if not os.path.isdir(out_dir):
            QtWidgets.QMessageBox.critical(self, "Папка", "Папка не существует.")
            return

        text = build_hex_for(cand)
        suffix = "V2" if cand.n_frac > 0 else "V1"
        name = "ce101 r5 145_%s__%s.hex" % (suffix, format_value(cand.value))
        path = os.path.join(out_dir, name)
        try:
            with open(path, "w", encoding="ascii", newline="\n") as fh:
                fh.write(text)
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "Запись", "Не удалось сохранить:\n%s" % exc)
            return

        total = self.counters.increment(COUNTER_NAME, cand.value)
        self._refresh_counter()
        self.log.append("Сохранено (%d): %s" % (total, path))

    # ── АВТОРЕЖИМ: ввёл → «Записать» → подбор + прошивка EEPROM ──────────────

    def on_write_auto(self):
        if getattr(self, "flash_worker", None) and self.flash_worker.isRunning():
            return
        if not self.license_status["valid"]:
            QtWidgets.QMessageBox.critical(
                self, "Нет лицензии",
                "Запись заблокирована: %s" % self.license_status["reason"])
            return
        try:
            target = float(self.inp.text().strip().replace(",", "."))
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Введите число.")
            return
        if target < 0:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Значение не может быть отрицательным.")
            return

        b3_max = B3_MAX_FULL if self.chk_full.isChecked() else B3_MAX_ORIGINAL
        if target > max_reading(b3_max):
            QtWidgets.QMessageBox.warning(
                self, "Вне диапазона",
                "Максимум — %s. Включите «Полный диапазон»." % format_value(max_reading(b3_max)))
            return

        ipecmd = find_ipecmd()
        if not ipecmd:
            QtWidgets.QMessageBox.critical(
                self, "PICkit не найден",
                "Не найден ipecmd.exe.\n\nУстановите MPLAB IPE (MPLAB X v6.15 или старее — "
                "в v6.20+ PICkit 3 не поддерживается) либо задайте путь в переменной "
                "окружения IPECMD.")
            return

        cands = solve(target, use_frac=self.chk_frac.isChecked(),
                           b3_max=b3_max, max_results=3)
        if not cands:
            QtWidgets.QMessageBox.warning(self, "Не найдено", "Не удалось подобрать вариант.")
            return
        self.candidates = cands
        for i, card in enumerate(self.cards):
            card.set_candidate(cands[i] if i < len(cands) else None, i == 0)
        cand = cands[0]

        out_dir = self.outdir.text().strip()
        if not os.path.isdir(out_dir):
            out_dir = tempfile.gettempdir()
        name = "ce101 r5 145_%s__%s.hex" % ("V2" if cand.n_frac > 0 else "V1",
                                            format_value(cand.value))
        path = os.path.join(out_dir, name)
        try:
            with open(path, "w", encoding="ascii", newline="\n") as fh:
                fh.write(build_hex_for(cand))
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "Запись", "Не удалось сохранить .hex:\n%s" % exc)
            return

        self._flash_value = cand.value
        self.log.append("Подобрано %s (%s) → прошиваю EEPROM в PIC%s…"
                        % (format_value(cand.value),
                           "точно" if cand.exact else "±%.2f" % cand.error, PIC_DEVICE))
        self.auto_btn.setEnabled(False)
        self.auto_btn.setText("ПРОШИВКА…")
        self.solve_btn.setEnabled(False)

        self.flash_worker = FlashWorker(ipecmd, path)
        self.flash_worker.line.connect(self.log.append)
        self.flash_worker.done.connect(self.on_flash_done)
        self.flash_worker.start()

    def on_flash_done(self, rc):
        self.auto_btn.setEnabled(True)
        self.auto_btn.setText("ЗАПИСАТЬ В ПРИБОР")
        self.solve_btn.setEnabled(True)
        if rc == 0:
            total = self.counters.increment(COUNTER_NAME, getattr(self, "_flash_value", 0))
            self._refresh_counter()
            self.log.append("✓ EEPROM записан (№ %d). Основная прошивка не тронута." % total)
            self.inp.selectAll()
            self.inp.setFocus()
        else:
            self.log.append("✗ Ошибка прошивки (код %d). См. сообщения выше." % rc)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(2000)
        if getattr(self, "flash_worker", None) and self.flash_worker.isRunning():
            self.flash_worker.wait(3000)
        event.accept()


# ══════════════════════════════════════════════════════════════════════════════
# Точка входа
# ══════════════════════════════════════════════════════════════════════════════

def run_keygen(argv):
    if not argv:
        print("Kod etogo kompyutera:", get_machine_code())
        print("Ispolzovanie: python VF_Gen.py keygen KOD [dney]")
        return 0
    code = argv[0]
    days = int(argv[1]) if len(argv) > 1 else 0
    try:
        key = generate_key(code, days)
    except ValueError as exc:
        print("Oshibka:", exc)
        return 1
    print("Kompyuter:", normalize(code))
    print("Srok:     ", "bessrochno" if days <= 0 else "%d dn." % days)
    print("Klyuch:   ", key)
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() == "keygen":
        return run_keygen(sys.argv[2:])

    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)

    holder = {}

    def after_splash():
        status = check_license()
        if not status["valid"]:
            dlg = ActivationDialog(status)
            if dlg.exec_() != QtWidgets.QDialog.Accepted:
                app.quit()
                return
            status = check_license()
            if not status["valid"]:
                app.quit()
                return
        holder["win"] = MainWindow(status)
        holder["win"].show()

    splash = SplashScreen()
    splash.finished.connect(after_splash)
    splash.start()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
