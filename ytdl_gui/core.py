"""Логика загрузки: обёртка вокруг yt-dlp без привязки к GUI.

Модуль намеренно не импортирует tkinter — его можно использовать и тестировать
отдельно от интерфейса.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import yt_dlp


class DownloadCancelled(Exception):
    """Выбрасывается из progress-hook, чтобы прервать текущую загрузку."""


@dataclass(frozen=True)
class QualityPreset:
    label: str          # что видит пользователь в списке
    kind: str           # "video" или "audio"
    value: object       # для video — максимальная высота (или None), для audio — кодек


QUALITY_PRESETS: tuple[QualityPreset, ...] = (
    QualityPreset("Лучшее доступное качество", "video", None),
    QualityPreset("2160p (4K)", "video", 2160),
    QualityPreset("1440p (2K)", "video", 1440),
    QualityPreset("1080p (Full HD)", "video", 1080),
    QualityPreset("720p (HD)", "video", 720),
    QualityPreset("480p", "video", 480),
    QualityPreset("360p", "video", 360),
    QualityPreset("Только звук — MP3", "audio", "mp3"),
    QualityPreset("Только звук — M4A", "audio", "m4a"),
)

DEFAULT_PRESET_INDEX = 3  # 1080p — разумный компромисс по размеру файла


def preset_by_label(label: str) -> QualityPreset:
    for preset in QUALITY_PRESETS:
        if preset.label == label:
            return preset
    return QUALITY_PRESETS[DEFAULT_PRESET_INDEX]


def build_format_selector(preset: QualityPreset, has_ffmpeg: bool = True) -> str:
    """Строка -f для yt-dlp по выбранному пресету.

    Без ffmpeg склеивать видео и звук нечем, поэтому селектор не должен содержать
    ``+``: любой такой вариант yt-dlp отклонит с ошибкой "requested merging of
    multiple formats". В этом режиме берём только готовые дорожки, где видео и
    звук уже в одном файле (``best`` — в отличие от ``bestvideo`` — выбирает
    именно такие).
    """
    if preset.kind == "audio":
        # Одна аудиодорожка — это тоже один файл, склейка не нужна.
        return "bestaudio/best"

    height = preset.value

    if not has_ffmpeg:
        if height is None:
            return "best"
        return f"best[height<={height}]/best"

    if height is None:
        return "bestvideo+bestaudio/best"
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"


def build_ydl_opts(
    *,
    preset: QualityPreset,
    output_dir: str,
    download_playlist: bool = False,
    write_subtitles: bool = False,
    subtitle_langs: str = "ru,en",
    has_ffmpeg: bool = True,
    progress_hooks: Sequence[Callable] = (),
    postprocessor_hooks: Sequence[Callable] = (),
    logger: object | None = None,
) -> dict:
    """Собирает словарь опций yt-dlp под выбранные настройки."""
    if download_playlist:
        template = os.path.join(
            output_dir, "%(playlist_title)s", "%(playlist_index)s - %(title)s.%(ext)s"
        )
    else:
        template = os.path.join(output_dir, "%(title)s.%(ext)s")

    opts: dict = {
        "format": build_format_selector(preset, has_ffmpeg=has_ffmpeg),
        # Сначала разрешение, и только при равном — mp4/m4a как более совместимый
        # контейнер. Фильтр [ext=mp4] внутри селектора так делать нельзя: он
        # отбросил бы 4K, которое YouTube отдаёт только в webm/av01.
        "format_sort": ["res", "ext:mp4:m4a"],
        "outtmpl": template,
        "noplaylist": not download_playlist,
        "ignoreerrors": download_playlist,  # один битый ролик не должен рушить плейлист
        "continuedl": True,
        "retries": 5,
        "fragment_retries": 5,
        "restrictfilenames": False,
        "windowsfilenames": os.name == "nt",
        "noprogress": True,   # свой прогресс рисуем в GUI
        "color": "no_color",  # в тексте лога цветовые escape-последовательности не нужны
        "quiet": True,
        "no_warnings": False,
        "progress_hooks": list(progress_hooks),
        "postprocessor_hooks": list(postprocessor_hooks),
    }

    if logger is not None:
        opts["logger"] = logger

    if preset.kind == "audio":
        # Без ffmpeg перекодировать нечем — забираем исходную аудиодорожку как есть.
        if has_ffmpeg:
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": str(preset.value),
                    "preferredquality": "192",
                }
            ]
    else:
        if has_ffmpeg:
            opts["merge_output_format"] = "mp4"

    if write_subtitles:
        langs = [lang.strip() for lang in subtitle_langs.split(",") if lang.strip()]
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = True
        opts["subtitleslangs"] = langs or ["ru", "en"]

    return opts


def fetch_info(url: str) -> dict:
    """Читает метаданные без загрузки: заголовок, автор, длительность, плейлист."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": False}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = info.get("entries")
    if entries is not None:
        items = [entry for entry in entries if entry]
        return {
            "is_playlist": True,
            "title": info.get("title") or "Плейлист",
            "uploader": info.get("uploader") or info.get("channel") or "",
            "count": len(items),
            "duration": sum(int(entry.get("duration") or 0) for entry in items),
        }

    return {
        "is_playlist": False,
        "title": info.get("title") or "Без названия",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "count": 1,
        "duration": int(info.get("duration") or 0),
    }


# --- форматирование значений для интерфейса -------------------------------------


def format_bytes(num: float | None) -> str:
    if not num:
        return "—"
    size = float(num)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if size < 1024 or unit == "ТБ":
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


def format_speed(speed: float | None) -> str:
    if not speed:
        return "—"
    return f"{format_bytes(speed)}/с"


def format_duration(seconds: float | None) -> str:
    if not seconds:
        return "—"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class DownloadWorker(threading.Thread):
    """Последовательно скачивает список ссылок в отдельном потоке.

    Общение с GUI — только через callback ``emit``: он складывает события в
    очередь, которую интерфейс разбирает в своём потоке.
    """

    def __init__(
        self,
        jobs: Iterable[str],
        opts_factory: Callable[..., dict],
        emit: Callable[..., None],
    ) -> None:
        super().__init__(daemon=True)
        self.jobs = list(jobs)
        self.opts_factory = opts_factory
        self.emit = emit
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:
        completed = 0
        failed = 0
        for index, url in enumerate(self.jobs):
            if self._cancel.is_set():
                self.emit("job_status", index=index, status="отменено")
                continue

            self.emit("job_status", index=index, status="загрузка")
            self.emit("log", text=f"▶ Начинаю: {url}")
            try:
                opts = self.opts_factory(
                    progress_hooks=[self._on_progress],
                    postprocessor_hooks=[self._on_postprocess],
                    logger=_YdlLogger(self.emit),
                )
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
            except DownloadCancelled:
                self.emit("job_status", index=index, status="отменено")
                self.emit("log", text=f"■ Отменено: {url}")
                continue
            except Exception as exc:  # noqa: BLE001 — показываем любую ошибку в логе
                failed += 1
                self.emit("job_status", index=index, status="ошибка")
                self.emit("log", text=f"✖ Ошибка: {url}\n   {exc}")
            else:
                completed += 1
                self.emit("job_status", index=index, status="готово")
                self.emit("log", text=f"✔ Готово: {url}")

        self.emit(
            "finished",
            completed=completed,
            failed=failed,
            cancelled=self._cancel.is_set(),
        )

    def _on_progress(self, data: dict) -> None:
        if self._cancel.is_set():
            raise DownloadCancelled

        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes") or 0
            percent = (downloaded / total * 100) if total else None
            self.emit(
                "progress",
                filename=os.path.basename(data.get("filename") or ""),
                percent=percent,
                downloaded=downloaded,
                total=total,
                speed=data.get("speed"),
                eta=data.get("eta"),
            )
        elif status == "finished":
            self.emit(
                "progress",
                filename=os.path.basename(data.get("filename") or ""),
                percent=100.0,
                downloaded=data.get("downloaded_bytes"),
                total=data.get("total_bytes"),
                speed=None,
                eta=0,
            )
            self.emit("log", text="   Файл загружен, обрабатываю…")

    def _on_postprocess(self, data: dict) -> None:
        if self._cancel.is_set():
            raise DownloadCancelled
        if data.get("status") == "started":
            name = data.get("postprocessor") or "постобработка"
            self.emit("stage", text=f"Обработка: {name}")


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    """Убирает escape-последовательности цвета: в текстовом логе они мусор."""
    return _ANSI_RE.sub("", text)


class _YdlLogger:
    """Переадресует сообщения yt-dlp в лог интерфейса."""

    def __init__(self, emit: Callable[..., None]) -> None:
        self.emit = emit

    def debug(self, msg: str) -> None:
        # yt-dlp дублирует info-сообщения в debug с префиксом "[debug] "
        if msg.startswith("[debug] "):
            return
        text = strip_ansi(msg).strip()
        if text:
            self.emit("log", text=f"   {text}")

    def info(self, msg: str) -> None:
        text = strip_ansi(msg).strip()
        if text:
            self.emit("log", text=f"   {text}")

    def warning(self, msg: str) -> None:
        self.emit("log", text=f"   ⚠ {strip_ansi(msg).strip()}")

    def error(self, msg: str) -> None:
        self.emit("log", text=f"   ✖ {strip_ansi(msg).strip()}")
