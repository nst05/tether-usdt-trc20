"""
Автономное GUI приложение — CRM Исламская рассрочка (Мурабаха)
Двойной клик → открывается окно приложения.
"""
import sys
import os
import threading
import time
import socket


def _resolve_data_dir():
    """
    Portable (.exe рядом с данными): данные хранятся рядом с exe.
    Installed (Program Files, read-only): данные в %LOCALAPPDATA%\CRM_Murabaha.
    """
    exe_dir = os.path.dirname(sys.executable)
    test = os.path.join(exe_dir, '.crm_write_test')
    try:
        with open(test, 'w') as f:
            f.write('ok')
        os.remove(test)
        return exe_dir          # портативный режим
    except (PermissionError, OSError):
        local = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        d = os.path.join(local, 'CRM_Murabaha')
        os.makedirs(d, exist_ok=True)
        return d                # установленный режим


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


def main():
    import webview

    port = _find_free_port()
    threading.Thread(target=_start_flask, args=(port,), daemon=True).start()

    if not _wait_for_server(port):
        try:
            import tkinter.messagebox as mb
            mb.showerror('Ошибка', 'Не удалось запустить сервер приложения.')
        except Exception:
            pass
        sys.exit(1)

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
