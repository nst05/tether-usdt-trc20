# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для «201 RANDOM».

Сборка:
    pip install pyinstaller pyqt5 i2cpy
    pyinstaller 201_drob_random.spec

Результат:
    dist/201_RANDOM.exe   — один файл, ничего рядом класть не нужно
                            (settings.json создастся рядом с .exe)

Перед сборкой положите CH341DLLA64.dll (для 64-битного Python)
или CH341DLL.dll (для 32-битного) рядом с этим .spec — она попадёт внутрь .exe.
Если файла нет, .exe соберётся, но работать с железом не сможет.
"""

import os
import sys

ROOT = os.path.abspath(os.getcwd())

# Имя DLL зависит от разрядности Python, которым идёт сборка.
DLL_NAME = "CH341DLLA64.dll" if sys.maxsize > 2 ** 31 - 1 else "CH341DLL.dll"
DLL_PATH = os.path.join(ROOT, DLL_NAME)

binaries = []
if os.path.isfile(DLL_PATH):
    binaries.append((DLL_PATH, "."))
    print(f"[spec] CH341 DLL найдена и будет упакована: {DLL_PATH}")
else:
    print(f"[spec] ВНИМАНИЕ: {DLL_NAME} не найдена в {ROOT} — .exe будет без драйвера CH341")

a = Analysis(
    ["201_drob_random.py"],
    pathex=[ROOT],
    binaries=binaries,
    datas=[],
    hiddenimports=[
        # i2cpy подгружает драйвер через import_module("i2cpy.driver.ch341"),
        # PyInstaller такой импорт сам не видит — перечисляем вручную.
        "i2cpy",
        "i2cpy.driver.ch341",
        "i2cpy.driver.ch341.dll",
        "i2cpy.driver.ch341.constants",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # заметно уменьшает размер: эти модули Qt программе не нужны
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
    name="201_RANDOM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # console=False — окно консоли не показывается.
    # На время отладки поставьте True, чтобы видеть текст ошибок.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icon.ico",
)
