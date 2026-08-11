@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   MT Writer - build (32-bit, matches the original 200/310_MT)
echo ============================================================

REM ---- 1. find a 32-bit Python interpreter --------------------------------
set "PY="

REM prefer the launcher's 32-bit build
py -3-32 --version >nul 2>&1 && set "PY=py -3-32"

REM else accept a bare python if it is itself 32-bit
if not defined PY (
    python -c "import struct,sys; sys.exit(0 if struct.calcsize('P')*8==32 else 1)" >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo.
    echo   32-bit Python was not found on this PC.
    echo.
    echo   Install it once:
    echo     https://www.python.org/downloads/windows/
    echo     pick "Windows installer (32-bit)" ^(the x86 one^),
    echo     tick "Add python.exe to PATH" during setup.
    echo.
    echo   Then run this file again - it will do the rest.
    echo.
    pause
    exit /b 1
)

echo   Interpreter: %PY%
%PY% -c "import struct;print('   bitness:', struct.calcsize('P')*8, 'bit')"

REM ---- 2. isolated build environment --------------------------------------
echo.
echo [1/4] Creating build environment...
%PY% -m venv .venv32 || goto error
call ".venv32\Scripts\activate.bat" || goto error

echo.
echo [2/4] Installing dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto error

echo.
echo [3/4] Building MT_Writer.exe...
python -m PyInstaller --noconfirm mt_writer.spec || goto error

echo.
echo [4/4] Building keygen_mt.exe...
python -m PyInstaller --noconfirm keygen_mt.spec || goto error

echo.
echo ============================================================
echo   Done (32-bit):
echo     dist\MT_Writer.exe   - program for the client
echo     dist\keygen_mt.exe   - key generator, DO NOT give to client
echo.
echo   This build uses the same CH341DLL.DLL (32-bit) as the
echo   original 200_MT / 310_MT - no extra files needed.
echo ============================================================
pause
exit /b 0

:error
echo.
echo BUILD FAILED. See the messages above.
pause
exit /b 1
