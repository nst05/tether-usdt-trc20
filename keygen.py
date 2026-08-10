#!/usr/bin/env python3
"""
Генератор ключей активации (инструмент продавца — клиенту НЕ передаётся).

Примеры:
    python keygen.py A1B2C-D3E4F-6789A-BCDEF                 # бессрочный ключ
    python keygen.py A1B2C-D3E4F-6789A-BCDEF --days 365      # на 1 год
    python keygen.py --my-code                               # код этого ПК
    python keygen.py --check XXXXXXX-XXXXXXX-XXXXXXX --code A1B2C-...

Секрет берётся из переменной окружения CRM_LICENSE_SECRET; он должен
совпадать с секретом, зашитым в сборку программы (crm_islamic/licensing.py).
"""
import argparse
import importlib.util
import os
import sys

# Загружаем licensing.py напрямую по пути — чтобы генератор работал
# без установленного Flask и остальных зависимостей CRM.
_LICENSING_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'crm_islamic', 'licensing.py')
_spec = importlib.util.spec_from_file_location('crm_licensing', _LICENSING_PATH)
licensing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(licensing)


def main():
    parser = argparse.ArgumentParser(
        description='Генератор ключей активации CRM «Исламская рассрочка»')
    parser.add_argument('machine_code', nargs='?',
                        help='Код компьютера клиента (A1B2C-D3E4F-6789A-BCDEF)')
    parser.add_argument('--days', type=int, default=0,
                        help='Срок действия в днях (0 или без флага — бессрочно)')
    parser.add_argument('--my-code', action='store_true',
                        help='Показать код этого компьютера')
    parser.add_argument('--check', metavar='KEY',
                        help='Проверить ключ (нужен --code или запуск на том же ПК)')
    parser.add_argument('--code', metavar='MACHINE_CODE',
                        help='Код компьютера для проверки ключа')
    args = parser.parse_args()

    if os.environ.get('CRM_LICENSE_SECRET') is None:
        print('  ⚠  CRM_LICENSE_SECRET не задан — используется секрет по умолчанию.\n'
              '     Перед продажей замените секрет и в программе, и здесь.\n',
              file=sys.stderr)

    if args.my_code:
        print(f'Код этого компьютера: {licensing.get_machine_code()}')
        print(f'Источник отпечатка:   {licensing.get_fingerprint_source()}')
        return 0

    if args.check:
        result = licensing.verify_key(args.check, args.code or licensing.get_machine_code())
        if result['valid']:
            срок = 'бессрочно' if result['perpetual'] else result['expires'].strftime('%d.%m.%Y')
            print(f'✓ Ключ действителен ({срок})')
            return 0
        print(f'✗ Ключ недействителен: {result["reason"]}')
        return 1

    if not args.machine_code:
        parser.print_help()
        return 2

    try:
        key = licensing.generate_key(args.machine_code, args.days)
    except ValueError as exc:
        print(f'Ошибка: {exc}')
        return 1

    code = licensing.normalize_code(args.machine_code)
    print('=' * 52)
    print('  Ключ активации CRM «Исламская рассрочка»')
    print('=' * 52)
    print(f'  Компьютер:  {code}')
    print(f'  Срок:       {"бессрочно" if args.days <= 0 else f"{args.days} дн."}')
    print(f'  Ключ:       {key}')
    print('=' * 52)
    return 0


if __name__ == '__main__':
    sys.exit(main())
