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

from app import create_app

application = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  ☪  CRM Исламская рассрочка запущена!")
    print(f"  →  http://localhost:{port}\n")
    application.run(host='0.0.0.0', port=port, debug=False)
