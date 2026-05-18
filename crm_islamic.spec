# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — одиночный .exe для CRM Исламская рассрочка.
Сборка:  python build.py
         или: pyinstaller crm_islamic.spec
Результат: dist/crm_islamic.exe
"""

import os
import sys

block_cipher = None

ROOT = os.path.abspath('.')
PKG  = os.path.join(ROOT, 'crm_islamic')

a = Analysis(
    [os.path.join(PKG, 'run.py')],
    pathex=[ROOT, PKG],
    binaries=[],
    datas=[
        (os.path.join(PKG, 'templates'), 'templates'),
    ],
    hiddenimports=[
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
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.orm',
        'sqlalchemy.ext.declarative',
        'sqlalchemy.pool',
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
        'csv',
        'io',
        'json',
        'os',
        'sys',
        'uuid',
        'mimetypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'PyQt5',
        'PyQt6',
        'wx',
        'scipy',
        'IPython',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Одиночный .exe — все данные упакованы внутрь
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='crm_islamic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # консоль показывает адрес http://localhost:5000
    icon=None,          # укажите путь к .ico если нужна иконка
)
