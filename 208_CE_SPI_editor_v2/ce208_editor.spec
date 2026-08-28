# -*- mode: python ; coding: utf-8 -*-
"""Сборка одного исполняемого файла редактора памяти CE208.

Запуск:  pyinstaller --noconfirm ce208_editor.spec
Результат: dist/CE208_Editor.exe (Windows) — без консольного окна, со значком.
"""

analysis = Analysis(
    ["editor.py"],
    pathex=["."],
    binaries=[],
    # Значок окна и файл .ico кладём внутрь сборки: их читает app_icon.py
    datas=[("assets/ce208.ico", "assets"), ("assets/ce208.png", "assets")],
    hiddenimports=["ce208_model", "ui_theme", "splash", "app_icon"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # i2cpy нужна только для прямой записи через CH341; без неё программа
    # работает с файлами образов, поэтому её отсутствие сборку не ломает.
    excludes=["numpy", "pandas", "matplotlib", "PIL", "pytest", "setuptools", "unittest"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="CE208_Editor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX часто провоцирует ложные срабатывания антивирусов
    runtime_tmpdir=None,
    console=False,           # оконное приложение, без чёрного окна консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/ce208.ico", # значок самого .exe
)
