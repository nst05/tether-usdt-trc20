@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import serial" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Не установлен pyserial.
  echo Выполните: py -3 -m pip install -r requirements.txt
  pause
  exit /b 1
)
py -3 smt_gui.py
if errorlevel 1 pause
