"""Проверка зависимостей до импорта основного кода.

Модуль не тянет за собой ни yt_dlp, ни tkinter: он только сообщает понятным
языком, чего не хватает, вместо traceback с ModuleNotFoundError.
"""

from __future__ import annotations

import importlib.util
import os
import sys

_PY = "python" if os.name == "nt" else "python3"

_TK_HINT = {
    "nt": "В Windows tkinter входит в состав Python. Похоже, Python установлен\n"
          "без него — переустановите с python.org, отметив «tcl/tk and IDLE».",
    "darwin": "Установите: brew install python-tk",
    "linux": "Установите: sudo apt install python3-tk\n"
             "(Fedora: sudo dnf install python3-tkinter, Arch: sudo pacman -S tk)",
}


def _tk_hint() -> str:
    if os.name == "nt":
        return _TK_HINT["nt"]
    if sys.platform == "darwin":
        return _TK_HINT["darwin"]
    return _TK_HINT["linux"]


def missing_dependencies() -> list[str]:
    """Возвращает список сообщений о том, чего не хватает для запуска."""
    problems: list[str] = []

    if importlib.util.find_spec("yt_dlp") is None:
        problems.append(
            "Не установлен yt-dlp — библиотека, которая скачивает видео.\n"
            f"Установите командой:\n    {_PY} -m pip install yt-dlp"
        )

    if importlib.util.find_spec("tkinter") is None:
        problems.append(f"Не установлен tkinter — библиотека интерфейса.\n{_tk_hint()}")

    return problems


def ensure_dependencies() -> bool:
    """Печатает подсказки, если чего-то не хватает. True — можно запускаться."""
    problems = missing_dependencies()
    if not problems:
        return True

    text = "\n\n".join(problems)
    print("Программа не может запуститься.\n", file=sys.stderr)
    print(text, file=sys.stderr)

    # Если окно показать можно (не хватает только yt-dlp) — покажем и его:
    # программу часто запускают двойным щелчком, и консоль сразу закрывается.
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("Не хватает компонентов", text)
        root.destroy()
    except Exception:  # noqa: BLE001 — сообщение в консоли уже выведено
        pass

    return False
