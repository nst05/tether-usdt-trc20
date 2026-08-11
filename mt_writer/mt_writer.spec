# -*- mode: python ; coding: utf-8 -*-
"""
Сборка MT Writer в один .exe:

    pip install pyinstaller
    pyinstaller mt_writer.spec

Результат: dist/MT_Writer.exe

Перед сборкой замените секрет в mt_license.py (DEFAULT_SECRET) —
иначе ключи сможет выпустить кто угодно, у кого есть эта программа.
"""

import glob
import os

block_cipher = None
ROOT = os.path.abspath('.')

# DLL драйвера CH341. Любой файл рядом со spec, чьё имя начинается на
# CH341 и заканчивается на .dll, упаковывается внутрь exe (при запуске
# окажется в _MEIPASS), и на компьютере клиента отдельная установка
# CH341PAR больше не нужна. Имя можно НЕ менять — программа найдёт файл
# сама (CH341A.DLL, CH341DLL.DLL, CH341DLLA64.DLL...).
# ВАЖНО: разрядность DLL (32/64) должна совпадать с разрядностью Python,
# которым идёт сборка. Для 64-битного Python нужна 64-битная DLL.
binaries = []
_seen = set()
for _pat in ('CH341*.dll', 'CH341*.DLL', 'ch341*.dll'):
    for _f in glob.glob(os.path.join(ROOT, _pat)):
        _key = os.path.basename(_f).lower()
        if _key not in _seen:
            _seen.add(_key)
            binaries.append((_f, '.'))
if binaries:
    print('  [spec] упакованы DLL драйвера:', ', '.join(os.path.basename(b) for b, _ in binaries))
else:
    print('  [spec] DLL драйвера CH341 рядом не найдена — положите CH341*.DLL сюда, '
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
