"""
Графический интерфейс AnonVPN (tkinter).

Окно с кнопками Подключить/Отключить, выбором конфига, индикатором статуса и
живым логом. GUI сам не трогает сеть — он запускает клиент (`anonvpn.client`)
как отдельный процесс, показывает его вывод в логе и корректно завершает его при
отключении (что запускает откат kill-switch/DNS в самом клиенте).

Требуется:
    sudo apt install python3-tk      # сам tkinter
    pip install -r requirements.txt

Запуск (TUN требует прав root):
    sudo python -m anonvpn.gui
Если запускаете без root, GUI попробует поднять клиент через pkexec/sudo.

Это только клиентский GUI. Сервер запускается отдельно на сервере.
"""

from __future__ import annotations

import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time

try:
    import tkinter as tk
    from tkinter import filedialog, ttk
    _TK_ERROR = None
except ModuleNotFoundError as _exc:  # pragma: no cover
    tk = None  # type: ignore
    filedialog = ttk = None  # type: ignore
    _TK_ERROR = (
        "Не найден tkinter. Установите его:\n"
        "  Debian/Ubuntu:  sudo apt install python3-tk\n"
        "  Fedora:         sudo dnf install python3-tkinter\n"
        "  Arch:           sudo pacman -S tk"
    )


# Маркеры в логе клиента, по которым определяем состояние.
MARK_CONNECTED = "Сессия установлена"
MARK_DISCONNECTED = "Очистка завершена"


class VpnController:
    """Запускает/останавливает клиентский процесс и читает его вывод."""

    def __init__(self, line_queue: "queue.Queue[str]"):
        self.proc: subprocess.Popen | None = None
        self.queue = line_queue
        self._reader: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _build_command(self, config_path: str) -> list[str]:
        base = [sys.executable, "-u", "-m", "anonvpn.client",
                "--config", config_path, "-v"]
        if os.geteuid() == 0:
            return base
        # не root — пробуем повысить права графически
        if shutil.which("pkexec"):
            return ["pkexec", *base]
        if shutil.which("sudo"):
            return ["sudo", *base]
        raise RuntimeError("Нужны права root, но pkexec/sudo не найдены")

    def start(self, config_path: str) -> None:
        if self.running:
            return
        cmd = self._build_command(config_path)
        self.queue.put(f"$ {' '.join(cmd)}")
        # запускаем из корня проекта, чтобы модуль anonvpn находился
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=project_root,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def _read_output(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            self.queue.put(line.rstrip("\n"))
        code = self.proc.wait()
        self.queue.put(f"[процесс завершён, код {code}]")

    def stop(self) -> None:
        if not self.running:
            return
        self.queue.put("Останавливаю клиент…")
        # SIGTERM -> клиент откатит kill-switch/DNS в своих обработчиках
        try:
            self.proc.send_signal(signal.SIGTERM)
            for _ in range(50):
                if self.proc.poll() is not None:
                    break
                time.sleep(0.1)
            if self.proc.poll() is None:
                self.proc.kill()
        except Exception as exc:  # noqa: BLE001
            self.queue.put(f"Ошибка остановки: {exc}")


class VpnGui:
    COLORS = {
        "off": "#c0392b",     # красный
        "connecting": "#e67e22",  # оранжевый
        "on": "#27ae60",      # зелёный
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.controller = VpnController(self.queue)

        root.title("AnonVPN")
        root.geometry("720x500")
        root.minsize(560, 380)

        self._build_ui()
        self._set_status("off", "Отключено")
        self.root.after(100, self._pump)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 6}

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)

        ttk.Label(top, text="Конфиг:").pack(side="left")
        self.config_var = tk.StringVar(value=self._default_config())
        self.config_entry = ttk.Entry(top, textvariable=self.config_var)
        self.config_entry.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="Обзор…", command=self._browse).pack(side="left")

        # статус
        status_row = ttk.Frame(self.root)
        status_row.pack(fill="x", **pad)
        self.status_canvas = tk.Canvas(status_row, width=18, height=18,
                                       highlightthickness=0)
        self.status_dot = self.status_canvas.create_oval(
            3, 3, 15, 15, fill=self.COLORS["off"], outline="")
        self.status_canvas.pack(side="left")
        self.status_label = ttk.Label(status_row, text="Отключено",
                                      font=("", 11, "bold"))
        self.status_label.pack(side="left", padx=8)

        # кнопки
        btns = ttk.Frame(self.root)
        btns.pack(fill="x", **pad)
        self.connect_btn = ttk.Button(btns, text="Подключить",
                                      command=self._connect)
        self.connect_btn.pack(side="left")
        self.disconnect_btn = ttk.Button(btns, text="Отключить",
                                         command=self._disconnect,
                                         state="disabled")
        self.disconnect_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="Очистить лог",
                   command=self._clear_log).pack(side="right")

        # лог
        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(log_frame, wrap="none", state="disabled",
                           bg="#1e1e1e", fg="#d4d4d4",
                           insertbackground="#d4d4d4", font=("monospace", 10))
        yscroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=yscroll.set)
        yscroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        # цветовые теги
        self.log.tag_config("info", foreground="#9cdcfe")
        self.log.tag_config("ok", foreground="#6abf69")
        self.log.tag_config("warn", foreground="#e6b450")
        self.log.tag_config("err", foreground="#f48771")

    def _default_config(self) -> str:
        for cand in ("client.conf", "client1.conf"):
            if os.path.exists(cand):
                return os.path.abspath(cand)
        return os.path.abspath("client.conf")

    # ---------------- действия ----------------
    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите конфиг клиента",
            filetypes=[("AnonVPN config", "*.conf"), ("Все файлы", "*.*")],
        )
        if path:
            self.config_var.set(path)

    def _connect(self) -> None:
        config_path = self.config_var.get().strip()
        if not os.path.exists(config_path):
            self._append(f"Конфиг не найден: {config_path}", "err")
            return
        try:
            self.controller.start(config_path)
        except RuntimeError as exc:
            self._append(str(exc), "err")
            return
        self._set_status("connecting", "Подключение…")
        self.connect_btn.config(state="disabled")
        self.disconnect_btn.config(state="normal")

    def _disconnect(self) -> None:
        self.controller.stop()

    def _clear_log(self) -> None:
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    # ---------------- статус/лог ----------------
    def _set_status(self, key: str, text: str) -> None:
        self.status_canvas.itemconfig(self.status_dot, fill=self.COLORS[key])
        self.status_label.config(text=text)

    def _append(self, line: str, tag: str = "info") -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log.config(state="normal")
        self.log.insert("end", f"[{stamp}] {line}\n", tag)
        self.log.see("end")
        self.log.config(state="disabled")

    def _classify(self, line: str) -> str:
        low = line.lower()
        if "error" in low or "ошибк" in low or "не удалось" in low:
            return "err"
        if "warning" in low or "warn" in low or "пропущен" in low:
            return "warn"
        if MARK_CONNECTED.lower() in low or "kill-switch включён" in low:
            return "ok"
        return "info"

    def _pump(self) -> None:
        """Каждые 100 мс выгребаем строки из очереди в лог (в GUI-потоке)."""
        try:
            while True:
                line = self.queue.get_nowait()
                self._append(line, self._classify(line))
                if MARK_CONNECTED in line:
                    self._set_status("on", "Подключено")
                elif "[процесс завершён" in line or MARK_DISCONNECTED in line:
                    self._set_status("off", "Отключено")
                    self.connect_btn.config(state="normal")
                    self.disconnect_btn.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    def _on_close(self) -> None:
        if self.controller.running:
            self.controller.stop()
        self.root.destroy()


def main() -> int:
    if _TK_ERROR:
        sys.stderr.write(_TK_ERROR + "\n")
        return 1
    root = tk.Tk()
    VpnGui(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
