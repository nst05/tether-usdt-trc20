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
    [os.path.join(PKG, 'run.py')],
    pathex=[ROOT, PKG],
    binaries=[],
    datas=[
        # Bundle all HTML templates
        (os.path.join(PKG, 'templates'), 'templates'),
        # Bundle static assets if they exist
        # (os.path.join(PKG, 'static'), 'static'),
    ],
    hiddenimports=[
        # Flask internals
        'flask',
        'flask.templating',
        'flask_sqlalchemy',
        'flask_wtf',
        'flask_wtf.csrf',
        'wtforms',
        'wtforms.validators',
        'wtforms.fields',
        # SQLAlchemy dialects
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.orm',
        'sqlalchemy.ext.declarative',
        # Email validation
        'email_validator',
        'idna',
        # dateutil
        'dateutil',
        'dateutil.relativedelta',
        # Jinja2
        'jinja2',
        'jinja2.ext',
        'markupsafe',
        # Werkzeug
        'werkzeug',
        'werkzeug.routing',
        'werkzeug.serving',
        # Standard
        'csv',
        'io',
        'json',
        'os',
        'sys',
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
