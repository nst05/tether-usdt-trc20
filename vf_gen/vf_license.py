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

from vf_storage import read_json, write_json

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
