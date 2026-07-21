"""Точка входа для запуска сервиса доставки veho."""
import sys
import os

if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
    os.environ['VEHO_BASE_DIR'] = base_dir
    os.environ['VEHO_DB_DIR'] = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

from app import create_app

application = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n  ●  veho — сервис доставки запущен!")
    print(f"  →  http://localhost:{port}\n")
    application.run(host='0.0.0.0', port=port, debug=False)
