"""
Автономное GUI приложение — CRM Исламская рассрочка (Мурабаха)
Двойной клик → открывается окно приложения.

Если pywebview / Edge WebView2 недоступен — открывается браузер.
"""
import sys
import os
import threading
import time
import socket
import traceback


def _resolve_data_dir():
    exe_dir = os.path.dirname(sys.executable)
    test = os.path.join(exe_dir, '.crm_write_test')
    try:
        with open(test, 'w') as f:
            f.write('ok')
        os.remove(test)
        return exe_dir
    except (PermissionError, OSError):
        local = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        d = os.path.join(local, 'CRM_Murabaha')
        os.makedirs(d, exist_ok=True)
        return d


if getattr(sys, 'frozen', False):
    os.environ['CRM_DB_DIR'] = _resolve_data_dir()
    sys.path.insert(0, sys._MEIPASS)

# Лог пишется рядом с exe (или в data dir)
_LOG_PATH = os.path.join(
    os.environ.get('CRM_DB_DIR', os.path.dirname(sys.executable)),
    'crm_error.log'
)


def _log(msg):
    try:
        with open(_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {msg}\n')
    except Exception:
        pass


def _find_free_port():
    for p in range(5000, 5100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    return 5000


_flask_error = None


def _start_flask(port):
    global _flask_error
    try:
        _log('Flask: импорт приложения...')
        from crm_islamic.app import create_app
        _log('Flask: create_app()...')
        flask_app = create_app()
        _log(f'Flask: запуск на порту {port}')
        flask_app.run(host='127.0.0.1', port=port, debug=False,
                      use_reloader=False, threaded=True)
    except Exception as e:
        _flask_error = traceback.format_exc()
        _log(f'Flask ОШИБКА:\n{_flask_error}')


def _wait_for_server(port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _show_error(msg):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, 'CRM — Ошибка', 0x10)
    except Exception:
        pass


def _open_browser(url):
    import webbrowser
    webbrowser.open(url)


def main():
    _log('=== Запуск CRM ===')
    port = _find_free_port()
    url  = f'http://127.0.0.1:{port}'
    _log(f'Порт: {port}')

    t = threading.Thread(target=_start_flask, args=(port,), daemon=True)
    t.start()

    if not _wait_for_server(port):
        err = _flask_error or 'Неизвестная ошибка'
        _log(f'Сервер не запустился. Ошибка:\n{err}')
        _show_error(
            f'Не удалось запустить сервер приложения.\n\n'
            f'Подробности в файле:\n{_LOG_PATH}'
        )
        sys.exit(1)

    _log('Сервер запущен. Открываем окно...')

    try:
        import webview
        webview.create_window(
            title='CRM — Исламская рассрочка (Мурабаха)',
            url=url,
            width=1440,
            height=900,
            min_size=(1024, 640),
            resizable=True,
            text_select=True,
        )
        webview.start(debug=False)
    except Exception:
        err = traceback.format_exc()
        _log(f'webview не сработал, открываем браузер.\n{err}')
        _open_browser(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
