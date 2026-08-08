#!/usr/bin/env python3
"""Запуск загрузчика видео: python youtube_downloader.py"""

import sys

from ytdl_gui.startup import ensure_dependencies


def run() -> int:
    if not ensure_dependencies():
        return 1
    from ytdl_gui.gui import main  # импорт после проверки зависимостей

    return main()


if __name__ == "__main__":
    sys.exit(run())
