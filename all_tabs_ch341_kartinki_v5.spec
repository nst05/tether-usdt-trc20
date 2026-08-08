# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для «ENERGOMERA — все программаторы».

Сборка:
    pip install pyinstaller pyqt5 i2cpy
    python make_icon.py            # создаст icon.ico (один раз)
    pyinstaller all_tabs_ch341_kartinki_v5.spec

Результат:
    dist/ENERGOMERA_all_tabs.exe   — один файл.

Рядом со .spec можно положить:
  - CH341DLLA64.dll (64-битный Python) или CH341DLL.dll (32-битный) — драйвер;
  - картинки вкладок: 201.png, c101_old2.jpg, 1F_NEW.png, 3F_NEW.png, 3F_old.jpg;
  - icon.ico — иконка .exe.
Всё найденное упакуется внутрь .exe. Чего нет — просто не попадёт (картинки
вкладок необязательны, без DLL не будет связи с железом).
"""

import os
import sys

ROOT = os.path.abspath(os.getcwd())

DLL_NAME = "CH341DLLA64.dll" if sys.maxsize > 2 ** 31 - 1 else "CH341DLL.dll"

binaries = []
dll_path = os.path.join(ROOT, DLL_NAME)
if os.path.isfile(dll_path):
    binaries.append((dll_path, "."))
    print(f"[spec] CH341 DLL упакована: {dll_path}")
else:
    print(f"[spec] ВНИМАНИЕ: {DLL_NAME} не найдена — .exe будет без драйвера CH341")

# Картинки вкладок — кладём в корень .exe, если присутствуют.
datas = []
for image_name in ("201.png", "c101_old2.jpg", "1F_NEW.png", "3F_NEW.png", "3F_old.jpg"):
    image_path = os.path.join(ROOT, image_name)
    if os.path.isfile(image_path):
        datas.append((image_path, "."))
        print(f"[spec] картинка упакована: {image_name}")

ICON_PATH = os.path.join(ROOT, "icon.ico")
icon = ICON_PATH if os.path.isfile(ICON_PATH) else None
if icon is None:
    print("[spec] icon.ico не найден — .exe будет с иконкой по умолчанию")

a = Analysis(
    ["all_tabs_ch341_kartinki_v5.py"],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        # i2cpy грузит драйвер через import_module — PyInstaller его не видит.
        "i2cpy",
        "i2cpy.driver.ch341",
        "i2cpy.driver.ch341.dll",
        "i2cpy.driver.ch341.constants",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5.QtWebEngineWidgets",
        "PyQt5.QtWebEngine",
        "PyQt5.QtQml",
        "PyQt5.QtQuick",
        "PyQt5.QtMultimedia",
        "PyQt5.QtBluetooth",
        "PyQt5.Qt3DCore",
        "tkinter",
        "matplotlib",
        "numpy",
        "PIL",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ENERGOMERA_all_tabs",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # console=False — без окна консоли. На время отладки поставьте True.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
