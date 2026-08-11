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

# CH341DLL.DLL — драйвер программатора. Если файл лежит рядом со spec,
# он упаковывается внутрь exe (при запуске окажется в _MEIPASS), и на
# компьютере клиента отдельная установка CH341PAR больше не нужна.
# ВАЖНО: имя файла должно быть именно CH341DLL.DLL, а его разрядность
# (32/64) — совпадать с разрядностью Python, которым идёт сборка.
# 64-битную CH341DLLA64.DLL переименуйте в CH341DLL.DLL.
binaries = []
_dll = os.path.join(ROOT, 'CH341DLL.DLL')
if os.path.exists(_dll):
    binaries.append((_dll, '.'))
    print('  [spec] CH341DLL.DLL найдена и будет упакована в exe')
else:
    print('  [spec] CH341DLL.DLL рядом не найдена — положите её сюда, '
          'иначе на чистом ПК будет ошибка загрузки драйвера')

a = Analysis(
    [os.path.join(ROOT, 'mt_writer.py')],
    pathex=[ROOT],
    binaries=binaries,
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
