@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ============================================================
REM  Write ONLY EEPROM to PIC16F1934 via PICkit 3
REM  - power the chip FROM the PICkit  (-A<VDD>)
REM  - keep the main firmware          (-ME, no chip erase)
REM
REM  BEFORE RUNNING: fully CLOSE the "PICkit 3 Programmer" app,
REM  otherwise it holds the PICkit and this fails to connect.
REM ============================================================

REM ---- settings (change VDD if your board is 3.3V) ----
set "IPECMD=C:\Program Files\Microchip\MPLABX\v6.00\mplab_platform\mplab_ipe\ipecmd.exe"
set "DEVICE=16F1934"
set "TOOL=PPK3"
set "VDD=5.0"

if not exist "%IPECMD%" (
    echo.
    echo   ipecmd.exe not found at:
    echo     %IPECMD%
    echo   Open this .bat in Notepad and fix the IPECMD path.
    echo.
    pause
    exit /b 1
)

REM ---- pick .hex: dragged onto the bat, or newest in this folder ----
set "HEX=%~1"
if "%HEX%"=="" (
    for /f "delims=" %%F in ('dir /b /o-d *.hex 2^>nul') do (
        set "HEX=%%~fF"
        goto :gothex
    )
)
:gothex
if "%HEX%"=="" (
    echo   No .hex file in this folder.
    pause
    exit /b 1
)

echo ============================================================
echo   Device : PIC%DEVICE%      Tool: PICkit 3
echo   Power  : from PICkit, %VDD% V
echo   Region : EEPROM only (firmware preserved)
echo   File   : %HEX%
echo ============================================================
echo.

"%IPECMD%" -T%TOOL% -P%DEVICE% -F"%HEX%" -ME -A%VDD% -OL
set "RC=%errorlevel%"

echo.
if "%RC%"=="0" (
    echo   OK - EEPROM written. Main firmware untouched.
) else (
    echo   FAILED ^(code %RC%^).
    echo   - is the "PICkit 3 Programmer" app closed?
    echo   - try VDD=3.3 if the board is 3.3V ^(edit this file^)
    echo   - check ICSP wiring: MCLR/VPP, PGC, PGD, VDD, GND
)
echo.
pause
exit /b %RC%
