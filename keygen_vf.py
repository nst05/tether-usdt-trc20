# -*- coding: utf-8 -*-
# Генератор ключей активации для VF Gen (self-contained, один файл).
# ЭТО ТВОЙ ИНСТРУМЕНТ — клиенту передавать НЕЛЬЗЯ.
#
# Запуск:
#   python keygen_vf.py КОД                 -> бессрочный ключ
#   python keygen_vf.py КОД 365             -> ключ на 365 дней
#   python keygen_vf.py --my-code           -> код этого компьютера
#   python keygen_vf.py --check КЛЮЧ КОД     -> проверить ключ
#   (двойной клик по exe/файлу -> спросит код и срок)
#
# Сборка в exe:
#   pyinstaller --onefile keygen_vf.py      -> dist\keygen_vf.exe
#
# ВАЖНО: секрет должен совпадать с секретом в VF_Gen.py. По умолчанию оба
# 'vf-gen-license-secret-change-me-2024'. Сменишь там — задай тот же и здесь
# (переменной окружения VF_LICENSE_SECRET) или поменяй строку ниже.

import base64
import binascii
import hashlib
import hmac
import os
import platform
import struct
import sys
import uuid
from datetime import date, timedelta

DEFAULT_SECRET = 'vf-gen-license-secret-change-me-2024'
SECRET = os.environ.get('VF_LICENSE_SECRET', DEFAULT_SECRET).encode('utf-8')

KEY_VERSION = 1
_EPOCH = date(2020, 1, 1)
_SIG_LEN = 10


# ── код компьютера (идентично vf_license.py) ─────────────────────────────────

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
                v = fh.read().strip()
            if v:
                return v
        except Exception:
            continue
    return None


def _linux_dmi_uuid():
    for path in ('/sys/class/dmi/id/product_uuid', '/sys/class/dmi/id/board_serial'):
        try:
            with open(path, 'r') as fh:
                v = fh.read().strip()
            if v and v.lower() not in ('none', 'unknown', '', '0'):
                return v
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
        return [_win_machine_guid, _win_volume_serial, _mac_address], ('win-guid', 'win-vol', 'mac')
    if system == 'Darwin':
        return [_mac_platform_uuid, _mac_address], ('mac-uuid', 'mac')
    return [_linux_machine_id, _linux_dmi_uuid, _mac_address], ('linux-id', 'linux-dmi', 'mac')


def _raw_fingerprint():
    getters, tags = _sources()
    for getter, tag in zip(getters, tags):
        try:
            v = getter()
        except Exception:
            v = None
        if v:
            return tag, v
    return None, None


def normalize(value):
    cleaned = ''.join(ch for ch in (value or '').upper() if ch.isalnum())
    return '-'.join(cleaned[i:i + 5] for i in range(0, len(cleaned), 5))


def _canonical(value):
    return ''.join(ch for ch in (value or '').upper() if ch.isalnum())


def get_machine_code():
    override = os.environ.get('VF_MACHINE_CODE')
    if override:
        return normalize(override)
    tag, value = _raw_fingerprint()
    if not value:
        tag, value = 'host', platform.node() or 'unknown-host'
    payload = ('%s:%s:%s' % (tag, value, platform.system())).encode('utf-8', 'replace')
    body = hashlib.sha256(payload).hexdigest()[:20].upper()
    return '-'.join(body[i:i + 5] for i in range(0, 20, 5))


# ── ключи (идентично vf_license.py) ──────────────────────────────────────────

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
    enc = base64.b32encode(blob).decode('ascii').rstrip('=')
    return '-'.join(enc[i:i + 7] for i in range(0, len(enc), 7))


def verify_key(key, code):
    cleaned = _canonical(key)
    try:
        blob = base64.b32decode(cleaned + '=' * (-len(cleaned) % 8))
    except (binascii.Error, ValueError):
        return False, 'Ключ введён с ошибкой'
    if len(blob) != 3 + _SIG_LEN:
        return False, 'Неверная длина ключа'
    version, expiry_days = struct.unpack('>BH', blob[:3])
    if version != KEY_VERSION:
        return False, 'Другая версия ключа'
    if not hmac.compare_digest(_signature(code, version, expiry_days), blob[3:]):
        return False, 'Ключ не подходит к этому компьютеру'
    if expiry_days == 0:
        return True, 'действителен (бессрочно)'
    expires = _EPOCH + timedelta(days=expiry_days)
    if date.today() > expires:
        return False, 'срок истёк ' + expires.strftime('%d.%m.%Y')
    return True, 'действителен до ' + expires.strftime('%d.%m.%Y')


# ── интерфейс ────────────────────────────────────────────────────────────────

def _print_key(code, days, key):
    print('=' * 52)
    print('  Ключ активации VF Gen')
    print('=' * 52)
    print('  Компьютер:', normalize(code))
    print('  Срок:     ', 'бессрочно' if days <= 0 else '%d дн.' % days)
    print('  Ключ:     ', key)
    print('=' * 52)


def _interactive():
    print('=' * 52)
    print('  Генератор ключей VF Gen')
    print('=' * 52)
    print('  Код этого компьютера:', get_machine_code())
    print()
    code = input('  Код компьютера клиента: ').strip()
    if not code:
        input('  Код не введён. Enter для выхода...')
        return 2
    days_txt = input('  Срок в днях (Enter — бессрочно): ').strip()
    try:
        days = int(days_txt) if days_txt else 0
    except ValueError:
        input('  Срок должен быть числом. Enter для выхода...')
        return 2
    print()
    try:
        key = generate_key(code, days)
    except ValueError as exc:
        input('  Ошибка: %s. Enter для выхода...' % exc)
        return 1
    _print_key(code, days, key)
    input('\n  Enter для выхода...')
    return 0


def main():
    args = sys.argv[1:]

    if os.environ.get('VF_LICENSE_SECRET') is None:
        print("  (используется секрет по умолчанию; смени его перед продажей)\n",
              file=sys.stderr)

    if not args:
        if sys.stdin and sys.stdin.isatty():
            return _interactive()
        print('Использование: keygen_vf.py КОД [дней]   |   --my-code   |   --check КЛЮЧ КОД')
        return 2

    if args[0] == '--my-code':
        print('Код этого компьютера:', get_machine_code())
        return 0

    if args[0] == '--check':
        if len(args) < 3:
            print('Нужно: --check КЛЮЧ КОД')
            return 2
        ok, msg = verify_key(args[1], args[2])
        print(('✓ ' if ok else '✗ ') + msg)
        return 0 if ok else 1

    code = args[0]
    days = int(args[1]) if len(args) > 1 else 0
    try:
        key = generate_key(code, days)
    except ValueError as exc:
        print('Ошибка:', exc)
        return 1
    _print_key(code, days, key)
    return 0


if __name__ == '__main__':
    sys.exit(main())
