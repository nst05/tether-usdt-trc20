# -*- mode: python ; coding: utf-8 -*-
"""
Сборка VF Gen в один защищённый .exe:

    pip install pyinstaller
    pyinstaller vf_gen.spec

Результат: dist/VF_Gen.exe

Защита исходного кода
─────────────────────
Модуль vf_core (математика) шифруется в отдельный расширенный модуль через
Cython, если он установлен (см. build_all.bat). Даже без Cython байт-код
Python 3.13 на момент выпуска штатными декомпиляторами не восстанавливается —
из exe можно достать только .pyc, который не читается как исходник.
Дополнительно ключевые строки не хранятся в открытом виде.

Перед распространением обязательно замените секрет в vf_license.py.
"""

import os

block_cipher = None
ROOT = os.path.abspath('.')

# Иконка/картинка предупреждения подключаются, если лежат рядом.
datas = []
for asset in ('warning.png', 'icon.ico'):
    if os.path.exists(os.path.join(ROOT, asset)):
        datas.append((os.path.join(ROOT, asset), '.'))

a = Analysis(
    [os.path.join(ROOT, 'vf_gen.py')],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'vf_core',
        'vf_license',
        'vf_counters',
        'vf_storage',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'hmac', 'hashlib', 'base64', 'struct', 'platform', 'ctypes', 'winreg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'pandas',
        'PyQt5.QtWebEngineWidgets', 'PyQt5.QtQml', 'PyQt5.QtNetwork',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,          # упаковать .pyc в архив, а не класть файлами
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VF_Gen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # окно консоли не нужно
    icon='icon.ico' if os.path.exists(os.path.join(ROOT, 'icon.ico')) else None,
)
