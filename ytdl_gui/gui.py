"""Графический интерфейс загрузчика видео с YouTube (tkinter + yt-dlp)."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .core import (
    DEFAULT_PRESET_INDEX,
    QUALITY_PRESETS,
    DownloadWorker,
    build_ydl_opts,
    fetch_info,
    format_bytes,
    format_duration,
    format_speed,
    preset_by_label,
)

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".ytdl_gui.json")


def default_download_dir() -> str:
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    return downloads if os.path.isdir(downloads) else os.path.expanduser("~")


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(config: dict) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass  # настройки — не критичные данные, молча переживём


def open_in_file_manager(path: str) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError as exc:
        messagebox.showwarning("Не удалось открыть папку", str(exc))


class DownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Загрузчик видео с YouTube")
        self.geometry("820x680")
        self.minsize(720, 600)

        self.config_data = load_config()
        self.has_ffmpeg = shutil.which("ffmpeg") is not None

        self.jobs: list[dict] = []          # [{"url": ..., "status": ...}]
        self.ui_queue: queue.Queue = queue.Queue()
        self.worker: DownloadWorker | None = None

        self.url_var = tk.StringVar()
        self.dir_var = tk.StringVar(
            value=self.config_data.get("output_dir") or default_download_dir()
        )
        self.quality_var = tk.StringVar(
            value=self.config_data.get("quality")
            or QUALITY_PRESETS[DEFAULT_PRESET_INDEX].label
        )
        self.playlist_var = tk.BooleanVar(value=bool(self.config_data.get("playlist")))
        self.subs_var = tk.BooleanVar(value=bool(self.config_data.get("subtitles")))
        self.subs_langs_var = tk.StringVar(
            value=self.config_data.get("subtitle_langs") or "ru,en"
        )
        self.status_var = tk.StringVar(value="Готов к работе")
        self.detail_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_ui()
        self._bind_shortcuts()

        if not self.has_ffmpeg:
            self._log(
                "⚠ ffmpeg не найден — качество ограничу автоматически, ошибки не будет.\n"
                "   Скачиваю только готовые дорожки, где видео и звук уже в одном файле "
                "(обычно не выше 720p), звук сохраняю как есть, без конвертации в MP3.\n"
                "   Чтобы снять ограничение, установите ffmpeg — см. README."
            )

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._pump_ui_queue)

    # --- построение интерфейса --------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)

        pad = {"padx": 10, "pady": 6}

        # 1. Ссылка
        link_frame = ttk.LabelFrame(self, text="Ссылка на видео или плейлист")
        link_frame.grid(row=0, column=0, sticky="ew", **pad)
        link_frame.columnconfigure(0, weight=1)

        url_entry = ttk.Entry(link_frame, textvariable=self.url_var)
        url_entry.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        url_entry.focus_set()
        url_entry.bind("<Return>", lambda _event: self._add_url())

        ttk.Button(link_frame, text="Добавить", command=self._add_url).grid(
            row=0, column=1, padx=(0, 4), pady=8
        )
        self.info_button = ttk.Button(
            link_frame, text="Информация", command=self._fetch_info
        )
        self.info_button.grid(row=0, column=2, padx=(0, 8), pady=8)

        # 2. Очередь
        queue_frame = ttk.LabelFrame(self, text="Очередь загрузки")
        queue_frame.grid(row=1, column=0, sticky="nsew", **pad)
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.queue_list = tk.Listbox(queue_frame, height=6, activestyle="none")
        self.queue_list.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)

        scrollbar = ttk.Scrollbar(
            queue_frame, orient="vertical", command=self.queue_list.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)
        self.queue_list.configure(yscrollcommand=scrollbar.set)

        buttons = ttk.Frame(queue_frame)
        buttons.grid(row=0, column=2, sticky="n", padx=8, pady=8)
        ttk.Button(buttons, text="Удалить", command=self._remove_selected).pack(
            fill="x", pady=(0, 4)
        )
        ttk.Button(buttons, text="Очистить", command=self._clear_queue).pack(fill="x")

        # 3. Настройки
        options = ttk.LabelFrame(self, text="Настройки")
        options.grid(row=2, column=0, sticky="ew", **pad)
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="Папка:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(options, textvariable=self.dir_var).grid(
            row=0, column=1, sticky="ew", pady=6
        )
        ttk.Button(options, text="Обзор…", command=self._choose_dir).grid(
            row=0, column=2, padx=4, pady=6
        )
        ttk.Button(options, text="Открыть", command=self._open_dir).grid(
            row=0, column=3, padx=(0, 8), pady=6
        )

        ttk.Label(options, text="Качество:").grid(
            row=1, column=0, sticky="w", padx=8, pady=6
        )
        quality_box = ttk.Combobox(
            options,
            textvariable=self.quality_var,
            values=[preset.label for preset in QUALITY_PRESETS],
            state="readonly",
        )
        quality_box.grid(row=1, column=1, sticky="ew", pady=6)

        checks = ttk.Frame(options)
        checks.grid(row=2, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 8))
        ttk.Checkbutton(
            checks, text="Скачивать весь плейлист", variable=self.playlist_var
        ).pack(side="left")
        ttk.Checkbutton(
            checks,
            text="Субтитры",
            variable=self.subs_var,
            command=self._toggle_subs,
        ).pack(side="left", padx=(16, 4))
        self.subs_entry = ttk.Entry(checks, textvariable=self.subs_langs_var, width=12)
        self.subs_entry.pack(side="left")
        self._toggle_subs()

        # 4. Кнопки запуска
        actions = ttk.Frame(self)
        actions.grid(row=3, column=0, sticky="ew", **pad)
        self.download_button = ttk.Button(
            actions, text="Скачать", command=self._start_download
        )
        self.download_button.pack(side="left")
        self.cancel_button = ttk.Button(
            actions, text="Отмена", command=self._cancel_download, state="disabled"
        )
        self.cancel_button.pack(side="left", padx=8)

        # 5. Прогресс
        progress_frame = ttk.LabelFrame(self, text="Прогресс")
        progress_frame.grid(row=4, column=0, sticky="ew", **pad)
        progress_frame.columnconfigure(0, weight=1)

        ttk.Progressbar(
            progress_frame,
            orient="horizontal",
            mode="determinate",
            maximum=100.0,
            variable=self.progress_var,
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ttk.Label(progress_frame, textvariable=self.status_var).grid(
            row=1, column=0, sticky="w", padx=8
        )
        ttk.Label(progress_frame, textvariable=self.detail_var).grid(
            row=2, column=0, sticky="w", padx=8, pady=(0, 8)
        )

        # 6. Лог
        log_frame = ttk.LabelFrame(self, text="Журнал")
        log_frame.grid(row=5, column=0, sticky="nsew", **pad)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_widget = ScrolledText(log_frame, height=10, state="disabled", wrap="word")
        self.log_widget.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-v>", lambda _event: None)  # штатная вставка в Entry
        self.bind("<Escape>", lambda _event: self._cancel_download())

    # --- работа с очередью -----------------------------------------------------

    def _add_url(self) -> None:
        raw = self.url_var.get().strip()
        if not raw:
            return
        added = 0
        for url in raw.split():
            if not url.startswith(("http://", "https://")):
                self._log(f"⚠ Пропускаю (не похоже на ссылку): {url}")
                continue
            if any(job["url"] == url for job in self.jobs):
                self._log(f"⚠ Уже в очереди: {url}")
                continue
            self.jobs.append({"url": url, "status": "ожидает"})
            added += 1
        if added:
            self.url_var.set("")
            self._render_queue()

    def _remove_selected(self) -> None:
        selection = list(self.queue_list.curselection())
        if not selection:
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(
                "Загрузка идёт", "Нельзя менять очередь во время загрузки."
            )
            return
        for index in reversed(selection):
            del self.jobs[index]
        self._render_queue()

    def _clear_queue(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(
                "Загрузка идёт", "Нельзя менять очередь во время загрузки."
            )
            return
        self.jobs.clear()
        self._render_queue()

    def _render_queue(self) -> None:
        self.queue_list.delete(0, tk.END)
        for job in self.jobs:
            self.queue_list.insert(tk.END, f"[{job['status']}]  {job['url']}")

    # --- настройки -------------------------------------------------------------

    def _choose_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.dir_var.get() or os.getcwd())
        if chosen:
            self.dir_var.set(chosen)

    def _open_dir(self) -> None:
        path = self.dir_var.get().strip()
        if path and os.path.isdir(path):
            open_in_file_manager(path)
        else:
            messagebox.showwarning("Папка не найдена", "Укажите существующую папку.")

    def _toggle_subs(self) -> None:
        self.subs_entry.configure(state="normal" if self.subs_var.get() else "disabled")

    def _current_config(self) -> dict:
        return {
            "output_dir": self.dir_var.get().strip(),
            "quality": self.quality_var.get(),
            "playlist": self.playlist_var.get(),
            "subtitles": self.subs_var.get(),
            "subtitle_langs": self.subs_langs_var.get().strip(),
        }

    # --- метаданные ------------------------------------------------------------

    def _fetch_info(self) -> None:
        url = self.url_var.get().strip().split(" ")[0]
        if not url:
            selection = self.queue_list.curselection()
            if selection:
                url = self.jobs[selection[0]]["url"]
        if not url:
            messagebox.showinfo("Нет ссылки", "Вставьте ссылку или выберите её в очереди.")
            return

        self.info_button.configure(state="disabled")
        self.status_var.set("Запрашиваю информацию…")

        def work() -> None:
            try:
                info = fetch_info(url)
            except Exception as exc:  # noqa: BLE001 — ошибку показываем в логе
                self.ui_queue.put(("log", {"text": f"✖ Не удалось получить данные: {exc}"}))
                self.ui_queue.put(("info_done", {}))
                return
            self.ui_queue.put(("info", info))
            self.ui_queue.put(("info_done", {}))

        threading.Thread(target=work, daemon=True).start()

    # --- загрузка --------------------------------------------------------------

    def _start_download(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        self._add_url()  # если ссылка осталась в поле — добавим её

        pending = [job["url"] for job in self.jobs]
        if not pending:
            messagebox.showinfo("Очередь пуста", "Добавьте хотя бы одну ссылку.")
            return

        output_dir = self.dir_var.get().strip()
        if not output_dir:
            messagebox.showwarning("Папка не выбрана", "Укажите папку для сохранения.")
            return
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Ошибка папки", f"Не удалось создать папку:\n{exc}")
            return

        preset = preset_by_label(self.quality_var.get())
        if preset.kind == "audio" and not self.has_ffmpeg:
            self._log("⚠ Без ffmpeg сохраню исходную аудиодорожку без конвертации.")

        save_config(self._current_config())

        for job in self.jobs:
            job["status"] = "ожидает"
        self._render_queue()

        def opts_factory(**hooks) -> dict:
            return build_ydl_opts(
                preset=preset,
                output_dir=output_dir,
                download_playlist=self.playlist_var.get(),
                write_subtitles=self.subs_var.get(),
                subtitle_langs=self.subs_langs_var.get() or "ru,en",
                has_ffmpeg=self.has_ffmpeg,
                **hooks,
            )

        self.worker = DownloadWorker(pending, opts_factory, self._emit)
        self.download_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress_var.set(0.0)
        self.status_var.set("Загрузка…")
        self.detail_var.set("")
        self.worker.start()

    def _cancel_download(self) -> None:
        if self.worker and self.worker.is_alive():
            self.worker.cancel()
            self.status_var.set("Останавливаю после текущего фрагмента…")
            self.cancel_button.configure(state="disabled")

    def _emit(self, kind: str, **payload) -> None:
        """Вызывается из рабочего потока — только кладём событие в очередь."""
        self.ui_queue.put((kind, payload))

    # --- перекачка событий в интерфейс ----------------------------------------

    def _pump_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        self.after(100, self._pump_ui_queue)

    def _handle_event(self, kind: str, payload: dict) -> None:
        if kind == "log":
            self._log(payload["text"])
        elif kind == "progress":
            self._update_progress(payload)
        elif kind == "stage":
            self.detail_var.set(payload["text"])
        elif kind == "job_status":
            index = payload["index"]
            if 0 <= index < len(self.jobs):
                self.jobs[index]["status"] = payload["status"]
                self._render_queue()
        elif kind == "info":
            self._show_info(payload)
        elif kind == "info_done":
            self.info_button.configure(state="normal")
            if self.status_var.get() == "Запрашиваю информацию…":
                self.status_var.set("Готов к работе")
        elif kind == "finished":
            self._on_finished(payload)

    def _update_progress(self, data: dict) -> None:
        percent = data.get("percent")
        if percent is None:
            self.status_var.set(
                f"Загрузка… {format_bytes(data.get('downloaded'))} "
                f"({format_speed(data.get('speed'))})"
            )
        else:
            self.progress_var.set(percent)
            self.status_var.set(f"Загрузка… {percent:.1f}%")

        parts = [
            f"{format_bytes(data.get('downloaded'))} из {format_bytes(data.get('total'))}",
            format_speed(data.get("speed")),
        ]
        eta = data.get("eta")
        if eta:
            parts.append(f"осталось {format_duration(eta)}")
        name = data.get("filename")
        if name:
            parts.append(name)
        self.detail_var.set("   ·   ".join(parts))

    def _show_info(self, info: dict) -> None:
        if info.get("is_playlist"):
            self._log(
                f"ℹ Плейлист: {info['title']} — {info['count']} видео, "
                f"общая длительность {format_duration(info['duration'])}"
            )
        else:
            author = f", автор: {info['uploader']}" if info.get("uploader") else ""
            self._log(
                f"ℹ {info['title']} — {format_duration(info['duration'])}{author}"
            )

    def _on_finished(self, payload: dict) -> None:
        self.download_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        completed = payload.get("completed", 0)
        failed = payload.get("failed", 0)
        if payload.get("cancelled"):
            self.status_var.set(f"Отменено. Успешно: {completed}, с ошибками: {failed}")
        elif failed:
            self.status_var.set(f"Завершено с ошибками. Успешно: {completed}, ошибок: {failed}")
        else:
            self.status_var.set(f"Готово. Скачано: {completed}")
            self.progress_var.set(100.0)
        self.detail_var.set("")

    def _log(self, text: str) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert(tk.END, text + "\n")
        self.log_widget.see(tk.END)
        self.log_widget.configure(state="disabled")

    # --- закрытие --------------------------------------------------------------

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askokcancel(
                "Выйти?", "Загрузка ещё идёт. Прервать и закрыть программу?"
            ):
                return
            self.worker.cancel()
        save_config(self._current_config())
        self.destroy()


def main() -> int:
    try:
        app = DownloaderApp()
    except tk.TclError as exc:
        print(f"Не удалось запустить графический интерфейс: {exc}", file=sys.stderr)
        print("Нужен доступ к дисплею (X11/Wayland) и установленный tkinter.", file=sys.stderr)
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
