"""
Runtime-хук PyInstaller для драйвера CH341.

i2cpy грузит DLL по голому имени:

    windll.LoadLibrary("CH341DLLA64.dll")

В onefile-сборке распакованные файлы лежат во временной папке sys._MEIPASS,
которой нет в путях поиска DLL, поэтому загрузка падает ещё на импорте
драйвера. Хук подставляет переменную окружения CH341DLL с полным путём —
i2cpy читает её раньше, чем берёт имя по умолчанию.

Если DLL в сборку неклали, хук ничего не делает: библиотека будет искаться
рядом с exe и в системных путях, как обычно.
"""

import os
import sys


def _setup_ch341():
    # Переменную, заданную пользователем вручную, не трогаем.
    if os.environ.get("CH341DLL"):
        return

    base = getattr(sys, "_MEIPASS", None)
    if not base:
        base = os.path.dirname(os.path.abspath(sys.executable))

    # Порядок как в i2cpy: сначала под разрядность текущего процесса.
    names = (["CH341DLLA64.dll", "CH341DLL.dll"]
             if sys.maxsize > 2147483647
             else ["CH341DLL.dll", "CH341DLLA64.dll"])

    for name in names:
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            os.environ["CH341DLL"] = candidate
            # Каталог с DLL — в пути поиска, на случай зависимостей.
            if hasattr(os, "add_dll_directory") and os.path.isdir(base):
                try:
                    os.add_dll_directory(base)
                except OSError:
                    pass
            return


_setup_ch341()
