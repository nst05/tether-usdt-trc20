# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — автономное GUI приложение CRM Исламская рассрочка.
Сборка:  python build.py
Результат: dist/CRM_Murabaha.exe  (одиночный файл, без консоли)
"""

import os

block_cipher = None

ROOT = os.path.abspath('.')
PKG  = os.path.join(ROOT, 'crm_islamic')

a = Analysis(
    [os.path.join(ROOT, 'gui_run.py')],
    pathex=[ROOT, PKG],
    binaries=[],
    datas=[
        (os.path.join(PKG, 'templates'), 'templates'),
    ],
    hiddenimports=[
        # Flask и расширения
        'flask',
        'flask.templating',
        'flask_sqlalchemy',
        'flask_wtf',
        'flask_wtf.csrf',
        'wtforms',
        'wtforms.validators',
        'wtforms.fields',
        'wtforms.fields.choices',
        'wtforms.fields.datetime',
        'wtforms.fields.numeric',
        'wtforms.fields.simple',
        # SQLAlchemy
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.orm',
        'sqlalchemy.ext.declarative',
        'sqlalchemy.pool',
        # Прочие зависимости Flask
        'email_validator',
        'idna',
        'dateutil',
        'dateutil.relativedelta',
        'jinja2',
        'jinja2.ext',
        'markupsafe',
        'werkzeug',
        'werkzeug.routing',
        'werkzeug.serving',
        'werkzeug.utils',
        'werkzeug.security',
        'itsdangerous',
        'click',
        # pywebview (Windows backend — Edge WebView2)
        'webview',
        'webview.platforms.winforms',
        'webview.platforms.cef',
        'clr',
        # Стандартные
        'csv', 'io', 'json', 'os', 'sys',
        'uuid', 'mimetypes', 'socket', 'threading',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'pandas',
        'PIL', 'PyQt5', 'PyQt6', 'wx', 'scipy', 'IPython',
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
    name='CRM_Murabaha',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # без консоли — сразу GUI окно
    windowed=True,
    icon=None,          # укажите .ico если нужна иконка
)
