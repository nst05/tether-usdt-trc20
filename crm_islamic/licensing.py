"""
Привязка программы к конкретному компьютеру (офлайн-лицензирование).

Как это работает
────────────────
1. На компьютере клиента программа вычисляет «Код компьютера» — короткий
   отпечаток железа/ОС вида  A1B2C-D3E4F-6789A-BCDEF.
2. Клиент присылает этот код продавцу.
3. Продавец генерирует ключ активации:  python keygen.py A1B2C-... --days 365
   Ключ считается через HMAC-SHA256 от кода компьютера и секрета, поэтому
   работает ТОЛЬКО на том компьютере, для которого выпущен.
4. Клиент вводит ключ на странице /activate. Ключ сохраняется в файле
   license.key рядом с базой данных. При каждом запуске ключ проверяется
   заново: если железо изменилось (другой ПК) или срок истёк — программа
   снова требует активацию.

Важно: секрет CRM_LICENSE_SECRET зашит в программу, поэтому защита —
«от честного пользователя», а не от реверс-инжиниринга. Обязательно
поменяйте секрет перед распространением сборки (см. _SECRET ниже).
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
import platform
import struct
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta

# ── Секрет ────────────────────────────────────────────────────────────────────
# ВНИМАНИЕ: поменяйте эту строку на свою перед сборкой .exe и используйте
# то же значение в keygen.py (или задайте переменную окружения
# CRM_LICENSE_SECRET одинаково при сборке и при генерации ключей).
DEFAULT_SECRET = 'islamic-crm-license-secret-change-me-2024'

_SECRET = os.environ.get('CRM_LICENSE_SECRET', DEFAULT_SECRET).encode('utf-8')

KEY_VERSION = 1
_EPOCH = date(2020, 1, 1)          # начало отсчёта срока действия
_SIG_LEN = 10                      # байт подписи в ключе
_LICENSE_FILENAME = 'license.key'
_CLOCK_TOLERANCE_DAYS = 2          # допуск на перевод системных часов назад


# ══════════════════════════════════════════════════════════════════════════════
# Отпечаток компьютера
# ══════════════════════════════════════════════════════════════════════════════

def _win_machine_guid():
    """MachineGuid из реестра Windows — не меняется при переустановке железа."""
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
    """Серийный номер системного тома (меняется при форматировании диска)."""
    try:
        import ctypes
        root = os.environ.get('SystemDrive', 'C:') + '\\'
        serial = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root), None, 0,
            ctypes.byref(serial), None, None, None, 0,
        )
        if ok:
            return f'{serial.value:08X}'
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
    """Последний рубеж: MAC-адрес. Слабый идентификатор, но лучше, чем ничего."""
    node = uuid.getnode()
    # Бит 0x010000000000 означает, что адрес сгенерирован случайно
    if node and not (node >> 40) & 0x01:
        return f'{node:012X}'
    return None


def _sources():
    """Источники идентификатора в порядке приоритета (сверху — надёжнее).

    Берётся ПЕРВЫЙ доступный источник: так код компьютера не «плывёт»,
    если один из менее приоритетных источников вдруг станет недоступен.
    """
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
    """(метка_источника, сырое значение) либо (None, None), если ничего нет."""
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
    """Код компьютера вида A1B2C-D3E4F-6789A-BCDEF (стабилен на одном ПК)."""
    override = os.environ.get('CRM_MACHINE_CODE')
    if override:
        return normalize_code(override)

    tag, value = _raw_fingerprint()
    if not value:
        # Совсем ничего не удалось прочитать — используем имя хоста,
        # чтобы программа хотя бы не падала.
        tag, value = 'host', platform.node() or 'unknown-host'
    payload = f'{tag}:{value}:{platform.system()}'.encode('utf-8', 'replace')
    return _format_code(hashlib.sha256(payload).hexdigest())


def get_fingerprint_source():
    """Какой источник использован — для диагностики на странице лицензии."""
    if os.environ.get('CRM_MACHINE_CODE'):
        return 'override'
    tag, _ = _raw_fingerprint()
    return tag or 'host'


def normalize_code(value):
    """Приводит введённый пользователем код/ключ к каноническому виду."""
    cleaned = ''.join(ch for ch in (value or '').upper() if ch.isalnum())
    return '-'.join(cleaned[i:i + 5] for i in range(0, len(cleaned), 5))


# ══════════════════════════════════════════════════════════════════════════════
# Ключ активации
# ══════════════════════════════════════════════════════════════════════════════

def _canonical_code(machine_code):
    return ''.join(ch for ch in (machine_code or '').upper() if ch.isalnum())


def _signature(machine_code, version, days, secret=None):
    message = f'{_canonical_code(machine_code)}|{version}|{days}'.encode('utf-8')
    return hmac.new(secret or _SECRET, message, hashlib.sha256).digest()[:_SIG_LEN]


def _b32_encode(blob):
    return base64.b32encode(blob).decode('ascii').rstrip('=')


def _b32_decode(text):
    padding = '=' * (-len(text) % 8)
    return base64.b32decode(text + padding)


def generate_key(machine_code, valid_days=0, secret=None):
    """Выпускает ключ активации для указанного кода компьютера.

    valid_days=0 — бессрочная лицензия.
    """
    machine_code = _canonical_code(machine_code)
    if len(machine_code) != 20:
        raise ValueError('Код компьютера должен содержать 20 символов (A1B2C-D3E4F-6789A-BCDEF)')

    if valid_days and valid_days > 0:
        expiry_days = (date.today() + timedelta(days=int(valid_days)) - _EPOCH).days
        if not 0 < expiry_days <= 0xFFFF:
            raise ValueError('Слишком большой срок действия лицензии')
    else:
        expiry_days = 0

    blob = struct.pack('>BH', KEY_VERSION, expiry_days)
    blob += _signature(machine_code, KEY_VERSION, expiry_days, secret)
    encoded = _b32_encode(blob)
    return '-'.join(encoded[i:i + 7] for i in range(0, len(encoded), 7))


def verify_key(key, machine_code=None, secret=None, today=None):
    """Проверяет ключ. Возвращает dict со статусом.

    {'valid': bool, 'reason': str|None, 'expires': date|None, 'perpetual': bool}
    """
    machine_code = machine_code or get_machine_code()
    today = today or date.today()
    cleaned = ''.join(ch for ch in (key or '').upper() if ch.isalnum())

    result = {'valid': False, 'reason': None, 'expires': None, 'perpetual': False}

    if not cleaned:
        result['reason'] = 'Ключ не введён'
        return result

    try:
        blob = _b32_decode(cleaned)
    except (binascii.Error, ValueError):
        result['reason'] = 'Ключ повреждён или введён с ошибкой'
        return result

    if len(blob) != 3 + _SIG_LEN:
        result['reason'] = 'Неверная длина ключа'
        return result

    version, expiry_days = struct.unpack('>BH', blob[:3])
    if version != KEY_VERSION:
        result['reason'] = f'Ключ версии {version} не поддерживается этой сборкой'
        return result

    expected = _signature(machine_code, version, expiry_days, secret)
    if not hmac.compare_digest(expected, blob[3:]):
        result['reason'] = 'Ключ не подходит к этому компьютеру'
        return result

    if expiry_days == 0:
        result.update(valid=True, perpetual=True)
        return result

    expires = _EPOCH + timedelta(days=expiry_days)
    result['expires'] = expires
    if today > expires:
        result['reason'] = f'Срок лицензии истёк {expires.strftime("%d.%m.%Y")}'
        return result

    result['valid'] = True
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Хранение лицензии
# ══════════════════════════════════════════════════════════════════════════════

def license_path(license_dir):
    return os.path.join(license_dir, _LICENSE_FILENAME)


def _guard(key, last_seen):
    message = f'{_canonical_code(key)}|{last_seen}'.encode('utf-8')
    return hmac.new(_SECRET, message, hashlib.sha256).hexdigest()[:32]


def load_license(license_dir):
    try:
        with open(license_path(license_dir), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data.get('key'):
            return data
    except Exception:
        pass
    return None


def save_license(license_dir, key, machine_code):
    last_seen = date.today().isoformat()
    data = {
        'key': key,
        'machine': machine_code,
        'activated_at': datetime.now().isoformat(timespec='seconds'),
        'last_seen': last_seen,
        'guard': _guard(key, last_seen),
    }
    os.makedirs(license_dir, exist_ok=True)
    with open(license_path(license_dir), 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return data


def _touch_last_seen(license_dir, data):
    """Обновляет отметку «последний запуск» — защита от перевода часов назад."""
    today = date.today().isoformat()
    if data.get('last_seen') == today:
        return
    data['last_seen'] = today
    data['guard'] = _guard(data.get('key', ''), today)
    try:
        with open(license_path(license_dir), 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def check_license(license_dir):
    """Полная проверка сохранённой лицензии на текущем компьютере."""
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

    data = load_license(license_dir)
    if not data:
        return status

    key = data.get('key', '')
    result = verify_key(key, machine_code)
    status['activated_at'] = data.get('activated_at')

    if not result['valid']:
        status['reason'] = result['reason']
        return status

    # Защита от перевода системных часов назад (важно для срочных лицензий).
    last_seen = data.get('last_seen')
    if last_seen and data.get('guard') == _guard(key, last_seen):
        try:
            seen_date = date.fromisoformat(last_seen)
            if date.today() < seen_date - timedelta(days=_CLOCK_TOLERANCE_DAYS):
                status['reason'] = ('Системная дата переведена назад. '
                                    'Установите правильную дату и запустите программу снова.')
                return status
        except ValueError:
            pass

    status.update(
        valid=True,
        reason=None,
        expires=result['expires'],
        perpetual=result['perpetual'],
    )
    if result['expires']:
        status['days_left'] = (result['expires'] - date.today()).days

    _touch_last_seen(license_dir, data)
    return status


def activate(license_dir, key):
    """Проверяет ключ и, если он подходит, сохраняет лицензию."""
    machine_code = get_machine_code()
    result = verify_key(key, machine_code)
    if not result['valid']:
        return False, result['reason']

    save_license(license_dir, normalize_code(key), machine_code)
    if result['perpetual']:
        return True, 'Программа активирована на этом компьютере (бессрочно).'
    return True, ('Программа активирована на этом компьютере до '
                  f'{result["expires"].strftime("%d.%m.%Y")}.')


def deactivate(license_dir):
    """Удаляет файл лицензии (например, перед переносом на другой ПК)."""
    try:
        os.remove(license_path(license_dir))
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Интеграция с Flask
# ══════════════════════════════════════════════════════════════════════════════

def enforcement_enabled():
    """Проверку можно отключить только при запуске из исходников (для разработки)."""
    if getattr(sys, 'frozen', False):
        return True
    return os.environ.get('CRM_LICENSE_DISABLE', '0') not in ('1', 'true', 'yes', 'on')


def init_app(app, license_dir):
    """Подключает защиту: гейт до всех страниц + страницы /activate и /license."""
    from flask import (redirect, render_template, request, url_for, flash)

    app.config['LICENSE_DIR'] = license_dir
    exempt_endpoints = {'static', 'license_activate', 'license_info', 'license_deactivate'}

    @app.before_request
    def _license_gate():
        if not enforcement_enabled():
            return None
        if request.endpoint in exempt_endpoints:
            return None
        status = check_license(app.config['LICENSE_DIR'])
        if not status['valid']:
            return redirect(url_for('license_activate'))
        return None

    @app.context_processor
    def _inject_license():
        if not enforcement_enabled():
            return {'license_status': {'valid': True, 'perpetual': True,
                                       'days_left': None, 'disabled': True}}
        return {'license_status': check_license(app.config['LICENSE_DIR'])}

    @app.route('/activate', methods=['GET', 'POST'])
    def license_activate():
        status = check_license(app.config['LICENSE_DIR'])
        error = None

        if request.method == 'POST':
            key = request.form.get('license_key', '')
            ok, message = activate(app.config['LICENSE_DIR'], key)
            if ok:
                flash(message, 'success')
                return redirect(url_for('dashboard'))
            error = message

        if status['valid'] and request.method == 'GET':
            return redirect(url_for('license_info'))

        return render_template('license/activate.html', status=status, error=error), (
            200 if request.method == 'GET' else 400
        )

    @app.route('/license')
    def license_info():
        return render_template('license/info.html',
                               status=check_license(app.config['LICENSE_DIR']),
                               enforced=enforcement_enabled())

    @app.route('/license/deactivate', methods=['POST'])
    def license_deactivate():
        deactivate(app.config['LICENSE_DIR'])
        flash('Лицензия удалена с этого компьютера.', 'warning')
        return redirect(url_for('license_activate'))
