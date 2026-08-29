@echo off
rem Запуск редактора в режиме STM32: контроль CRC-32 по 16-битным словам.
setlocal
cd /d "%~dp0"
set "CE208_PYTHON=C:\Users\ixd\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CE208_PYTHON%" (
    "%CE208_PYTHON%" editor.py --crc=stm32 %*
    exit /b %errorlevel%
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3 editor.py --crc=stm32 %*
    exit /b %errorlevel%
)

echo Python 3 ne naiden. Ustanovite Python 3 s Tkinter ili zapustite editor.py vruchnuyu.
pause
exit /b 1
