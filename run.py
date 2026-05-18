"""Запуск CRM Исламской рассрочки (Мурабаха)"""
import os
import sys

from crm_islamic.app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  ☪  CRM Исламская рассрочка (Мурабаха) запущена!")
    print(f"  →  Откройте в браузере: http://localhost:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=False)
