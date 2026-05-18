"""
Автономное GUI приложение — CRM Исламская рассрочка (Мурабаха)
Двойной клик → открывается окно приложения.
"""
import sys
import os
import threading
import time
import socket

# PyInstaller: БД и uploads хранятся рядом с .exe
if getattr(sys, 'frozen', False):
    _exe_dir = os.path.dirname(sys.executable)
    os.environ['CRM_DB_DIR'] = _exe_dir
    # Добавляем путь к распакованным модулям
    sys.path.insert(0, sys._MEIPASS)

PORT = 5000


def _find_free_port():
    """Если 5000 занят — найти свободный порт."""
    for p in range(5000, 5100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    return 5000


def _start_flask(port):
    from crm_islamic.app import create_app
    flask_app = create_app()
    flask_app.run(
        host='127.0.0.1',
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def _wait_for_server(port, timeout=15):
    """Ждём пока Flask поднимется."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main():
    import webview

    port = _find_free_port()

    # Запускаем Flask в фоновом потоке
    flask_thread = threading.Thread(target=_start_flask, args=(port,), daemon=True)
    flask_thread.start()

    # Ждём пока сервер готов (максимум 15 сек)
    if not _wait_for_server(port):
        import tkinter.messagebox as mb
        mb.showerror('Ошибка', 'Не удалось запустить сервер приложения.')
        sys.exit(1)

    # Создаём окно
    webview.create_window(
        title='CRM — Исламская рассрочка (Мурабаха)',
        url=f'http://127.0.0.1:{port}',
        width=1440,
        height=900,
        min_size=(1024, 640),
        resizable=True,
        text_select=True,
    )
    webview.start(debug=False)


if __name__ == '__main__':
    main()
