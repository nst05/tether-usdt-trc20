# -*- mode: python ; coding: utf-8 -*-
"""
Сборка генератора ключей в отдельный .exe:

    pyinstaller keygen_mt.spec

Результат: dist/keygen_mt.exe  (консольная утилита)

ЭТОТ ФАЙЛ КЛИЕНТУ НЕ ПЕРЕДАВАТЬ — с ним можно выпустить ключ
для любого компьютера.

Секрет подписи должен совпадать с секретом в mt_license.py на момент
сборки MT_Writer.exe.
"""

import os

block_cipher = None
ROOT = os.path.abspath('.')

a = Analysis(
    [os.path.join(ROOT, 'keygen_mt.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        'mt_license',
        'mt_storage',
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
        'PyQt5',
        'matplotlib',
        'numpy',
        'pandas',
        'i2cpy',
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
    name='keygen_mt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,           # консольная утилита — вывод ключа виден в окне
    icon=None,
)
