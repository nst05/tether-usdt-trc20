#!/usr/bin/env python3
"""smt_rogue_server_gui — GUI-обёртка над smt_rogue_server (стенд подмены сервера).

ТОЛЬКО ДЛЯ АВТОРИЗОВАННОГО ПЕНТЕСТА своего / переданного по договору оборудования.

Та же логика, что в smt_rogue_server.py (CLI), но без ключей командной строки:
задаёшь host/port и что отвечать прибору мышкой, смотришь лог в окне, при
необходимости отвечаешь на каждое соединение вручную прямо в GUI.

Запуск
------
  python3 smt_rogue_server_gui.py
"""
from __future__ import annotations

import contextlib
import datetime
import queue
import socket
import threading
import tkinter as tk
from collections import deque
from tkinter import filedialog, messagebox, scrolledtext, ttk

import smt_rogue_server as rogue

DEFAULT_PORT = 40000


def handle_conn(conn, addr, cfg, outq):
    conn.settimeout(cfg["idle"])
    buf = b""
    while True:
        try:
            d = conn.recv(4096)
        except TimeoutError:
            break
        if not d:
            break
        buf += d
        if len(buf) > cfg["max_frame"]:
            outq.put(("log", f"  [!] кадр > {cfg['max_frame']} байт — обрыв"))
            break

    ts = datetime.datetime.now().strftime("%H:%M:%S")
    outq.put(("log", "═" * 70))
    outq.put(("log", f"[{ts}] подключился прибор {addr[0]}:{addr[1]}"))
    outq.put(("log", f"  принято {len(buf)} байт"))
    if buf:
        outq.put(("log", "  ─ сырьё (latin1) ─"))
        outq.put(("log", "    " + buf.decode("latin1", "replace").replace("\n", "\n    ")))

    rep = rogue.analyse_inbound(buf)
    n = len(rep.get("records", []))
    outq.put(("log", f"  разобрано записей: {n}"))
    ac = rep.get("auth_check")
    if ac:
        matched = any(x.get("match") for x in ac)
        outq.put(("log", f"  auth (MD5 целостности) сходится: {matched}"))
        outq.put(("log", "  ⚠ вывод: контроль целостности БЕЗ секрета — сервер прибором "
                          "НЕ аутентифицируется."))

    if cfg["interactive"]:
        holder: dict = {}
        ev = threading.Event()
        outq.put(("ask", addr, holder, ev))
        got = ev.wait(timeout=120)
        if not got or "text" not in holder:
            sent = rogue.make_response("accept", n, None, None)
            outq.put(("log", "  (тайм-аут ожидания оператора — отправлен DATA ACCEPT по умолчанию)"))
        elif holder["text"].strip():
            sent = rogue._unescape(holder["text"])
        else:
            sent = rogue.make_response("accept", n, None, None)
    else:
        try:
            sent = rogue.make_response(cfg["mode"], n, cfg["raw"], cfg["file"])
        except OSError as exc:
            outq.put(("log", f"  [!] не удалось прочитать файл ответа: {exc}"))
            sent = b""
        if cfg["followup"]:
            sent += rogue._unescape(cfg["followup"])

    reaction = b""
    if sent:
        try:
            conn.sendall(sent)
            outq.put(("log", f"  → отправлено {len(sent)} байт: {sent!r}"))
        except OSError as exc:
            outq.put(("log", f"  [!] ошибка отправки: {exc}"))
    else:
        outq.put(("log", "  → (ничего не отправлено, режим silent)"))

    if not cfg["no_reaction"]:
        conn.settimeout(cfg["reaction_wait"])
        try:
            while True:
                d = conn.recv(4096)
                if not d:
                    break
                reaction += d
        except TimeoutError:
            pass
        if reaction:
            outq.put(("log", f"  ← ПРИБОР ОТВЕТИЛ на нашу реплику ({len(reaction)} байт):"))
            outq.put(("log", "    " + reaction.decode("latin1", "replace").replace("\n", "\n    ")))
            outq.put(("log", "  ⚠ реакция на ответ сервера — повод проверить downstream-обработку "
                              "(конфиг/команды сверху)."))
        else:
            outq.put(("log", "  ← прибор молчит после нашего ответа (или закрыл соединение)"))

    base = rogue.log_session(addr, buf, rep, sent, reaction)
    outq.put(("log", f"  сохранено: {base}.log / .json"))
    outq.put(("session", base))
    with contextlib.suppress(Exception):
        conn.close()


def server_loop(cfg, outq, stop_event):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((cfg["host"], cfg["port"]))
    except OSError as exc:
        outq.put(("log", f"[!] не удалось открыть {cfg['host']}:{cfg['port']}: {exc}"))
        outq.put(("stopped", None))
        return
    s.settimeout(0.5)
    s.listen(5)
    outq.put(("log", f"[*] слушаю {cfg['host']}:{cfg['port']} — жду сессию прибора "
                      f"(режим ответа: {'вручную' if cfg['interactive'] else cfg['mode']})"))
    outq.put(("started", None))
    while not stop_event.is_set():
        try:
            conn, addr = s.accept()
        except TimeoutError:
            continue
        except OSError:
            break
        threading.Thread(target=handle_conn, args=(conn, addr, cfg, outq), daemon=True).start()
    with contextlib.suppress(Exception):
        s.close()
    outq.put(("log", "[*] сервер остановлен"))
    outq.put(("stopped", None))


class App:
    MODES = [
        ("accept", "DATA ACCEPT:n — штатный ответ (по умолчанию)"),
        ("update", "ACK update — проверить ветку прошивки 0801E594"),
        ("silent", "Ничего не отправлять (проверить таймаут прибора)"),
        ("raw", "Свой текст (ниже, с поддержкой \\r\\n\\xHH)"),
        ("file", "Из файла (байты как есть)"),
    ]

    def __init__(self, root):
        self.root = root
        root.title("SMT Rogue Server — стенд подмены сервера · пентест")
        root.geometry("880x640")

        self.outq: queue.Queue = queue.Queue()
        self.stop_event: threading.Event | None = None
        self.running = False
        self.pending_asks: deque = deque()
        self.current_ask = None  # (addr, holder, ev)

        self._build_ui()
        self.root.after(80, self._pump)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- UI --
    def _build_ui(self):
        warn = tk.Label(
            self.root,
            text="⚠ ТОЛЬКО для авторизованного пентеста своего / переданного по договору "
                 "оборудования (RoE). Стенд не атакует сеть — отвечает лишь тому прибору, "
                 "который сам сюда подключился.",
            fg="#a33", justify="left", wraplength=860, anchor="w",
        )
        warn.pack(fill="x", padx=8, pady=(8, 4))

        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=4)

        ttk.Label(top, text="Host:").grid(row=0, column=0, sticky="w")
        self.host_var = tk.StringVar(value="0.0.0.0")
        ttk.Entry(top, textvariable=self.host_var, width=14).grid(row=0, column=1, padx=(2, 12))

        ttk.Label(top, text="Port:").grid(row=0, column=2, sticky="w")
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        ttk.Entry(top, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=(2, 12))

        self.start_btn = ttk.Button(top, text="▶ Запустить", command=self._start)
        self.start_btn.grid(row=0, column=4, padx=4)
        self.stop_btn = ttk.Button(top, text="■ Остановить", command=self._stop, state="disabled")
        self.stop_btn.grid(row=0, column=5, padx=4)

        self.status_var = tk.StringVar(value="остановлен")
        ttk.Label(top, textvariable=self.status_var, foreground="#666").grid(
            row=0, column=6, padx=(12, 0), sticky="w")

        # ---- как отвечать прибору ----
        mode_box = ttk.LabelFrame(self.root, text="Что отвечать прибору")
        mode_box.pack(fill="x", padx=8, pady=4)

        self.mode_var = tk.StringVar(value="accept")
        for i, (val, label) in enumerate(self.MODES):
            ttk.Radiobutton(mode_box, text=label, value=val, variable=self.mode_var,
                            command=self._sync_mode_fields).grid(
                row=i, column=0, columnspan=3, sticky="w", padx=6, pady=1)

        ttk.Label(mode_box, text="Свой текст:").grid(row=len(self.MODES), column=0, sticky="w", padx=6)
        self.raw_var = tk.StringVar(value="ACK update\\r\\n")
        self.raw_entry = ttk.Entry(mode_box, textvariable=self.raw_var, width=50)
        self.raw_entry.grid(row=len(self.MODES), column=1, sticky="we", padx=4)

        ttk.Label(mode_box, text="Файл ответа:").grid(row=len(self.MODES) + 1, column=0, sticky="w", padx=6)
        self.file_var = tk.StringVar(value="")
        self.file_entry = ttk.Entry(mode_box, textvariable=self.file_var, width=40)
        self.file_entry.grid(row=len(self.MODES) + 1, column=1, sticky="we", padx=4)
        self.file_btn = ttk.Button(mode_box, text="Обзор…", command=self._pick_file)
        self.file_btn.grid(row=len(self.MODES) + 1, column=2, sticky="w", padx=4)

        ttk.Separator(mode_box).grid(row=len(self.MODES) + 2, column=0, columnspan=3, sticky="we", pady=4)

        self.interactive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            mode_box, text="Спрашивать вручную на каждое соединение (игнорирует режим выше)",
            variable=self.interactive_var, command=self._sync_mode_fields,
        ).grid(row=len(self.MODES) + 3, column=0, columnspan=3, sticky="w", padx=6)

        ttk.Label(mode_box, text="Добавка после ответа (followup):").grid(
            row=len(self.MODES) + 4, column=0, sticky="w", padx=6, pady=(4, 6))
        self.followup_var = tk.StringVar(value="")
        ttk.Entry(mode_box, textvariable=self.followup_var, width=50).grid(
            row=len(self.MODES) + 4, column=1, columnspan=2, sticky="we", padx=4, pady=(4, 6))

        mode_box.columnconfigure(1, weight=1)

        # ---- таймауты ----
        tm = ttk.Frame(self.root)
        tm.pack(fill="x", padx=8, pady=2)
        ttk.Label(tm, text="Таймаут склейки входящего (с):").pack(side="left")
        self.idle_var = tk.StringVar(value="0.8")
        ttk.Entry(tm, textvariable=self.idle_var, width=6).pack(side="left", padx=(2, 16))
        ttk.Label(tm, text="Ждать реакцию прибора (с):").pack(side="left")
        self.reaction_var = tk.StringVar(value="2.0")
        ttk.Entry(tm, textvariable=self.reaction_var, width=6).pack(side="left", padx=(2, 16))
        self.no_reaction_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tm, text="не слушать реакцию", variable=self.no_reaction_var).pack(side="left")

        # ---- панель ручного ответа (появляется при interactive) ----
        self.ask_box = ttk.LabelFrame(self.root, text="Прибор ждёт ответ — введи, что отправить")
        self.ask_var = tk.StringVar(value="")
        ttk.Entry(self.ask_box, textvariable=self.ask_var, width=60).pack(
            side="left", padx=6, pady=6, fill="x", expand=True)
        ttk.Button(self.ask_box, text="Отправить", command=self._send_ask).pack(side="left", padx=4)
        ttk.Button(self.ask_box, text="DATA ACCEPT (по умолч.)", command=self._send_ask_default).pack(
            side="left", padx=4)
        self.ask_label = tk.StringVar(value="")
        # ask_box упаковывается динамически в _pump

        # ---- лог ----
        log_box = ttk.LabelFrame(self.root, text="Лог сессий")
        log_box.pack(fill="both", expand=True, padx=8, pady=4)
        self.log = scrolledtext.ScrolledText(log_box, wrap="word", font=("Courier New", 9))
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=8, pady=(0, 8))
        self.last_session_var = tk.StringVar(value="сессии: sessions/rogue_*.log/.json")
        ttk.Label(bottom, textvariable=self.last_session_var, foreground="#666").pack(side="left")
        ttk.Button(bottom, text="Очистить лог", command=self._clear_log).pack(side="right")

        self._sync_mode_fields()

    def _sync_mode_fields(self):
        interactive = self.interactive_var.get()
        mode = self.mode_var.get()
        state_raw = "normal" if (not interactive and mode == "raw") else "disabled"
        state_file = "normal" if (not interactive and mode == "file") else "disabled"
        self.raw_entry.configure(state=state_raw)
        self.file_entry.configure(state=state_file)
        self.file_btn.configure(state=state_file)

    def _pick_file(self):
        path = filedialog.askopenfilename(title="Файл ответа")
        if path:
            self.file_var.set(path)

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------ control --
    def _start(self):
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Порт должен быть числом")
            return
        try:
            idle = float(self.idle_var.get())
            reaction_wait = float(self.reaction_var.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Таймауты должны быть числами")
            return

        cfg = {
            "host": self.host_var.get().strip() or "0.0.0.0",
            "port": port,
            "mode": self.mode_var.get(),
            "raw": self.raw_var.get(),
            "file": self.file_var.get().strip() or None,
            "followup": self.followup_var.get(),
            "interactive": self.interactive_var.get(),
            "idle": idle,
            "reaction_wait": reaction_wait,
            "no_reaction": self.no_reaction_var.get(),
            "max_frame": 2 * 1024 * 1024,
        }

        self.stop_event = threading.Event()
        threading.Thread(target=server_loop, args=(cfg, self.outq, self.stop_event),
                          daemon=True).start()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_var.set("запускается…")

    def _stop(self):
        if self.stop_event:
            self.stop_event.set()
        self.stop_btn.configure(state="disabled")
        self.status_var.set("останавливается…")

    def _on_close(self):
        if self.stop_event:
            self.stop_event.set()
        self.root.after(200, self.root.destroy)

    # ------------------------------------------------------- запрос ответа --
    def _send_ask(self):
        if not self.current_ask:
            return
        addr, holder, ev = self.current_ask
        holder["text"] = self.ask_var.get()
        ev.set()
        self._finish_ask()

    def _send_ask_default(self):
        if not self.current_ask:
            return
        _addr, holder, ev = self.current_ask
        holder["text"] = ""
        ev.set()
        self._finish_ask()

    def _finish_ask(self):
        self.ask_box.pack_forget()
        self.ask_var.set("")
        self.current_ask = None
        self._maybe_show_next_ask()

    def _maybe_show_next_ask(self):
        if self.current_ask is None and self.pending_asks:
            addr, holder, ev = self.pending_asks.popleft()
            self.current_ask = (addr, holder, ev)
            self.ask_box.configure(text=f"Прибор {addr[0]}:{addr[1]} ждёт ответ — введи, что отправить")
            self.ask_box.pack(fill="x", padx=8, pady=4, before=self.log.master)
            self.ask_var.set("")

    # ------------------------------------------------------------- насос --
    def _pump(self):
        try:
            while True:
                item = self.outq.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._append_log(item[1])
                elif kind == "started":
                    self.status_var.set("работает")
                elif kind == "stopped":
                    self.status_var.set("остановлен")
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                elif kind == "session":
                    self.last_session_var.set(f"последняя сессия: {item[1]}.log / .json")
                elif kind == "ask":
                    _tag, addr, holder, ev = item
                    self.pending_asks.append((addr, holder, ev))
                    self._maybe_show_next_ask()
        except queue.Empty:
            pass
        self.root.after(80, self._pump)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
