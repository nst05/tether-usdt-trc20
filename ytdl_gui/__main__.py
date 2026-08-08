"""Точка входа: python -m ytdl_gui"""

from .startup import ensure_dependencies


def run() -> int:
    if not ensure_dependencies():
        return 1
    from .gui import main  # импорт после проверки зависимостей

    return main()


if __name__ == "__main__":
    raise SystemExit(run())
