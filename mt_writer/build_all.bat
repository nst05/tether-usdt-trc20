@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   MT Writer - build
echo ============================================================

echo.
echo [1/3] Installing dependencies...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error

echo.
echo [2/3] Building the program (MT_Writer.exe)...
python -m PyInstaller --noconfirm mt_writer.spec
if errorlevel 1 goto error

echo.
echo [3/3] Building the key generator (keygen_mt.exe)...
python -m PyInstaller --noconfirm keygen_mt.spec
if errorlevel 1 goto error

echo.
echo ============================================================
echo   Done:
echo     dist\MT_Writer.exe   - program for the client
echo     dist\keygen_mt.exe   - key generator, DO NOT give to client
echo ============================================================
pause
exit /b 0

:error
echo.
echo BUILD FAILED. See the messages above.
pause
exit /b 1
