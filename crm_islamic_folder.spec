# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — папочный режим (для установщика).
Результат: dist/CRM_Murabaha/  — папка с exe и dll-файлами.
Быстрый старт: нет распаковки при каждом запуске.
Упаковывается в установщик через Inno Setup (installer.iss).
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
        (os.path.join(PKG, 'default_contract_template.docx'), '.'),
    ],
    hiddenimports=[
        'flask', 'flask.templating',
        'flask_sqlalchemy', 'flask_wtf', 'flask_wtf.csrf',
        'wtforms', 'wtforms.validators', 'wtforms.fields',
        'wtforms.fields.choices', 'wtforms.fields.datetime',
        'wtforms.fields.numeric', 'wtforms.fields.simple',
        'sqlalchemy', 'sqlalchemy.dialects.sqlite',
        'sqlalchemy.orm', 'sqlalchemy.ext.declarative', 'sqlalchemy.pool',
        'email_validator', 'idna',
        'dateutil', 'dateutil.relativedelta',
        'jinja2', 'jinja2.ext', 'markupsafe',
        'werkzeug', 'werkzeug.routing', 'werkzeug.serving',
        'werkzeug.utils', 'werkzeug.security',
        'itsdangerous', 'click',
        'webview', 'webview.platforms.winforms', 'webview.platforms.cef',
        'clr',
        # openpyxl (Excel import)
        'openpyxl', 'openpyxl.styles', 'openpyxl.utils',
        'openpyxl.reader.excel', 'openpyxl.writer.excel',
        # python-docx (contract generation)
        'docx', 'docx.oxml', 'docx.oxml.ns', 'docx.opc',
        'docx.opc.constants', 'docx.shared',
        # lxml (required by python-docx)
        'lxml', 'lxml.etree',
        'csv', 'io', 'json', 'os', 'sys', 'copy', 'zipfile',
        'uuid', 'mimetypes', 'socket', 'threading',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'pandas',
        'PIL', 'PyQt5', 'PyQt6', 'wx', 'scipy', 'IPython',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # папочный режим — dll отдельно
    name='CRM_Murabaha',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    windowed=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CRM_Murabaha',        # папка: dist/CRM_Murabaha/
)
