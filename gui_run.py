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


def _find_free_port():
    for p in range(5000, 5100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    return 5000


def _start_flask(port):
    from crm_islamic.app import create_app
    flask_app = create_app()
    flask_app.run(host='127.0.0.1', port=port, debug=False,
                  use_reloader=False, threaded=True)


def _wait_for_server(port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _open_browser(url):
    import webbrowser
    webbrowser.open(url)


def main():
    port = _find_free_port()
    url  = f'http://127.0.0.1:{port}'

    threading.Thread(target=_start_flask, args=(port,), daemon=True).start()

    if not _wait_for_server(port):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                'Не удалось запустить сервер приложения.',
                'CRM — Ошибка',
                0x10,
            )
        except Exception:
            pass
        sys.exit(1)

    # Пробуем открыть в нативном окне (pywebview + Edge WebView2)
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
        # Fallback: открываем в браузере, держим сервер живым
        _open_browser(url)
        try:
            # Ждём пока пользователь закроет процесс вручную
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
