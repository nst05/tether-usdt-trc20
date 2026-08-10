# -*- coding: utf-8 -*-
"""
Счётчики прошивок — по одному на каждую вкладку (200_MT и 310_MT).

Счётчик увеличивается только после успешной записи И проверки чтением.
Хранится в counters.json рядом с программой, поэтому не сбрасывается
при перезапуске, обновлении программы или перезагрузке компьютера.

Файл подписан контрольной суммой: если счётчики правили вручную,
программа это видит и показывает предупреждение (но продолжает работать,
считая дальше от найденного значения).
"""

import hashlib
import hmac
import json
from datetime import datetime

from mt_storage import read_json, write_json

COUNTERS_FILE = 'counters.json'
FORMAT_VERSION = 1

# Отдельный от лицензии секрет — только для контрольной суммы файла счётчиков.
_GUARD_SECRET = b'mt-writer-counters-guard-2024'


def _guard(counters):
    payload = json.dumps(counters, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hmac.new(_GUARD_SECRET, payload, hashlib.sha256).hexdigest()[:32]


class Counters:
    """Счётчики прошивок по именам профилей."""

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

        if raw.get('guard') != _guard(stored):
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
            'guard': _guard(self._data),
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
        """Записать факт успешной прошивки. Возвращает новое значение счётчика."""
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
