"""Сборка архива с версией программы в имени.

Запуск:  python make_release.py [каталог назначения]
Результат: 208_CE_SPI_editor_<версия>.zip — версия берётся из editor.py,
поэтому имя архива всегда совпадает с версией программы.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
SKIP_DIRS = {"__pycache__", "build", "dist", ".git"}
SKIP_SUFFIXES = {".pyc", ".zip"}


def app_version() -> str:
    """Читает APP_VERSION из editor.py без импорта Tkinter."""
    text = (SOURCE / "editor.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("В editor.py не найдено APP_VERSION")
    return match.group(1)


def build(target_dir: Path | None = None) -> Path:
    version = app_version()
    target = (target_dir or SOURCE.parent) / f"208_CE_SPI_editor_v{version}.zip"
    files = sorted(
        path for path in SOURCE.rglob("*")
        if path.is_file()
        and not SKIP_DIRS & set(path.relative_to(SOURCE).parts)
        and path.suffix not in SKIP_SUFFIXES
    )
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, str(Path(f"208_CE_SPI_editor_v{version}") / path.relative_to(SOURCE)))
    print(f"Архив: {target}")
    print(f"Версия: {version}; файлов: {len(files)}; размер: {target.stat().st_size} байт")
    return target


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
