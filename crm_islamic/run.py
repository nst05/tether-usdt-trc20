"""Entry point for both direct run and PyInstaller executable."""
import sys
import os

# When frozen by PyInstaller, fix paths for templates and static files
if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
    # Override template and static folder resolution
    os.environ['CRM_BASE_DIR'] = base_dir
    # DB lives next to the executable, not inside the bundle
    os.environ['CRM_DB_DIR'] = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Пакет crm_islamic использует относительные импорты, поэтому импортируем
    # его как пакет — для этого родительская папка должна быть в sys.path.
    parent_dir = os.path.dirname(base_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

from crm_islamic.app import app as application
from crm_islamic import licensing

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  ☪  CRM Исламская рассрочка запущена!")
    print(f"  →  http://localhost:{port}\n")

    # Состояние лицензии — чтобы код компьютера был виден прямо в консоли
    try:
        status = licensing.check_license(application.config['LICENSE_DIR'])
        print(f"  Код компьютера: {status['machine_code']}")
        if not licensing.enforcement_enabled():
            print("  Лицензия:       проверка отключена (режим разработки)")
        elif not status['valid']:
            print(f"  Лицензия:       НЕ АКТИВИРОВАНА — {status['reason']}")
            print(f"  Активация:      http://localhost:{port}/activate")
        elif status['perpetual']:
            print("  Лицензия:       активна (бессрочная)")
        else:
            print(f"  Лицензия:       активна до {status['expires'].strftime('%d.%m.%Y')} "
                  f"({status['days_left']} дн.)")
        print()
    except Exception as exc:
        print(f"  Проверка лицензии: ошибка ({exc})\n")

    application.run(host='0.0.0.0', port=port, debug=False)
