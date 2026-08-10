# -*- mode: python ; coding: utf-8 -*-
"""
Сборка MT Writer в один .exe:

    pip install pyinstaller
    pyinstaller mt_writer.spec

Результат: dist/MT_Writer.exe

Перед сборкой замените секрет в mt_license.py (DEFAULT_SECRET) —
иначе ключи сможет выпустить кто угодно, у кого есть эта программа.
"""

import os

block_cipher = None
ROOT = os.path.abspath('.')

a = Analysis(
    [os.path.join(ROOT, 'mt_writer.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        'mt_license',
        'mt_counters',
        'mt_storage',
        'i2cpy',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        # для отпечатка компьютера
        'hmac',
        'hashlib',
        'base64',
        'struct',
        'platform',
        'ctypes',
        'winreg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtQml',
        'PyQt5.QtNetwork',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MT_Writer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # окно консоли не нужно — программа с интерфейсом
    icon=None,              # укажите путь к .ico, если есть иконка
)
