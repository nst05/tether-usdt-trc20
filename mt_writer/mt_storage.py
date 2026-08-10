# -*- coding: utf-8 -*-
"""
Где программа хранит свои данные (лицензию и счётчики прошивок).

Приоритет:
1. Папка, заданная переменной окружения MT_DATA_DIR.
2. Папка рядом с .exe (или рядом со скриптом) — если в неё можно писать.
3. %APPDATA%\\MT_Writer (Windows) / ~/.local/share/MT_Writer — если папка
   программы только для чтения (например, установка в Program Files).

Файлы пишутся атомарно: сначала во временный файл, потом os.replace, —
чтобы счётчик не терялся при выключении питания посреди записи.
"""

import json
import os
import sys
import tempfile

_APP_FOLDER = 'MT_Writer'
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

    override = os.environ.get('MT_DATA_DIR')
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
