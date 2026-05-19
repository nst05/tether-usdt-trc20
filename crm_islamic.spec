# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for CRM Исламская рассрочка.
Build:  pyinstaller crm_islamic.spec
Output: dist/crm_islamic/  (folder mode)
        dist/crm_islamic.exe  (single-file mode, see below)
"""

import os

block_cipher = None

# Root of the project
ROOT = os.path.abspath('.')
PKG  = os.path.join(ROOT, 'crm_islamic')

a = Analysis(
    [os.path.join(ROOT, 'gui_run.py')],
    pathex=[ROOT, PKG],
    binaries=[],
    datas=[
        # Bundle all HTML templates
        (os.path.join(PKG, 'templates'), 'templates'),
        # Bundle default contract template
        (os.path.join(PKG, 'default_contract_template.docx'), '.'),
        # Bundle static assets if they exist
        # (os.path.join(PKG, 'static'), 'static'),
    ],
    hiddenimports=[
        # Flask
        'flask', 'flask.templating',
        'flask_sqlalchemy', 'flask_wtf', 'flask_wtf.csrf',
        'wtforms', 'wtforms.validators', 'wtforms.fields',
        'wtforms.fields.choices', 'wtforms.fields.datetime',
        'wtforms.fields.numeric', 'wtforms.fields.simple',
        # SQLAlchemy
        'sqlalchemy', 'sqlalchemy.dialects.sqlite',
        'sqlalchemy.orm', 'sqlalchemy.ext.declarative', 'sqlalchemy.pool',
        # Email / dateutil / jinja / werkzeug
        'email_validator', 'idna',
        'dateutil', 'dateutil.relativedelta',
        'jinja2', 'jinja2.ext', 'markupsafe',
        'werkzeug', 'werkzeug.routing', 'werkzeug.serving',
        'werkzeug.utils', 'werkzeug.security',
        'itsdangerous', 'click',
        # pywebview
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
        # Standard
        'csv', 'io', 'json', 'os', 'sys', 'copy', 'zipfile',
        'uuid', 'mimetypes', 'socket', 'threading',
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
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Option A: folder output (faster startup, easier to debug) ──────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='crm_islamic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,          # Keep console so users see startup URL
    icon=None,             # Add .ico path here if you have an icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='crm_islamic',
)

# ── Option B: single-file exe (comment out COLLECT above, uncomment below) ──
# exe = EXE(
#     pyz,
#     a.scripts,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     name='crm_islamic',
#     debug=False,
#     strip=False,
#     upx=True,
#     console=True,
#     onefile=True,
# )
