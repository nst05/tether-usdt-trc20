#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор ключей активации MT Writer.
Это ВАШ инструмент — клиенту его передавать нельзя.

Примеры:
    python keygen_mt.py A1B2C-D3E4F-6789A-BCDEF              # бессрочный ключ
    python keygen_mt.py A1B2C-D3E4F-6789A-BCDEF --days 365   # на год
    python keygen_mt.py --my-code                            # код этого ПК
    python keygen_mt.py --check XXXXXXX-XXXXXXX-XXXXXXX --code A1B2C-D3E4F-6789A-BCDEF

Секрет берётся из переменной окружения MT_LICENSE_SECRET и должен
совпадать с секретом в сборке программы (mt_license.py).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mt_license  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description='Генератор ключей активации MT Writer')
    parser.add_argument('machine_code', nargs='?',
                        help='Код компьютера клиента (A1B2C-D3E4F-6789A-BCDEF)')
    parser.add_argument('--days', type=int, default=0,
                        help='Срок действия в днях (без флага — бессрочно)')
    parser.add_argument('--my-code', action='store_true',
                        help='Показать код этого компьютера')
    parser.add_argument('--check', metavar='KEY', help='Проверить готовый ключ')
    parser.add_argument('--code', metavar='MACHINE_CODE',
                        help='Код компьютера для проверки ключа')
    args = parser.parse_args()

    if os.environ.get('MT_LICENSE_SECRET') is None:
        print('  ⚠  MT_LICENSE_SECRET не задан — используется секрет по умолчанию.\n'
              '     Перед продажей замените секрет в mt_license.py и здесь.\n',
              file=sys.stderr)

    if args.my_code:
        print('Код этого компьютера: %s' % mt_license.get_machine_code())
        print('Источник отпечатка:   %s' % mt_license.get_fingerprint_source())
        return 0

    if args.check:
        result = mt_license.verify_key(args.check, args.code or mt_license.get_machine_code())
        if result['valid']:
            period = ('бессрочно' if result['perpetual']
                      else result['expires'].strftime('%d.%m.%Y'))
            print('✓ Ключ действителен (%s)' % period)
            return 0
        print('✗ Ключ недействителен: %s' % result['reason'])
        return 1

    if not args.machine_code:
        parser.print_help()
        return 2

    try:
        key = mt_license.generate_key(args.machine_code, args.days)
    except ValueError as exc:
        print('Ошибка: %s' % exc)
        return 1

    print('=' * 52)
    print('  Ключ активации MT Writer')
    print('=' * 52)
    print('  Компьютер:  %s' % mt_license.normalize(args.machine_code))
    print('  Срок:       %s' % ('бессрочно' if args.days <= 0 else '%d дн.' % args.days))
    print('  Ключ:       %s' % key)
    print('=' * 52)
    return 0


if __name__ == '__main__':
    sys.exit(main())
