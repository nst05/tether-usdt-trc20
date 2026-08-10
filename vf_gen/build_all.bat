@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   VF Gen - build
echo ============================================================

echo.
echo [1/4] Installing dependencies...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error

echo.
echo [2/4] Compiling core to native code (source protection)...
echo       If Cython or a C compiler is missing, this step is skipped
echo       and the exe is still built (without the native core).
python -m pip install cython >nul 2>&1
python compile_core.py

echo.
echo [3/4] Building the program (VF_Gen.exe)...
python -m PyInstaller --noconfirm vf_gen.spec
if errorlevel 1 goto error

echo.
echo [4/4] Building the key generator (keygen_vf.exe)...
python -m PyInstaller --noconfirm keygen_vf.spec
if errorlevel 1 goto error

echo.
echo ============================================================
echo   Done:
echo     dist\VF_Gen.exe     - program for the client
echo     dist\keygen_vf.exe  - key generator, DO NOT give to client
echo ============================================================
pause
exit /b 0

:error
echo.
echo BUILD FAILED. See the messages above.
pause
exit /b 1
