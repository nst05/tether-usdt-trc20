@echo off
rem Запуск редактора в режиме MSP432: контрольная сумма CRC-16 CCITT 0x1021.
setlocal
cd /d "%~dp0"
set "CE208_PYTHON=C:\Users\ixd\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CE208_PYTHON%" (
    "%CE208_PYTHON%" editor.py --crc=msp432 %*
    exit /b %errorlevel%
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3 editor.py --crc=msp432 %*
    exit /b %errorlevel%
)

echo Python 3 ne naiden. Ustanovite Python 3 s Tkinter ili zapustite editor.py vruchnuyu.
pause
exit /b 1
