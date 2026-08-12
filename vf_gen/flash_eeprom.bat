@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ============================================================
REM  PIC16F1934 - write EEPROM ONLY, keep firmware, power from PICkit 3
REM   -ME       program EEPROM only
REM   -OH       do NOT erase all before programming (default erases!)
REM   -W        power target from tool (like "VDD PICkit 3 On")
REM   -OL       release from reset
REM  Close the "PICkit 3 Programmer" app before running.
REM ============================================================

set "IPECMD=C:\Program Files\Microchip\MPLABX\v6.00\mplab_platform\mplab_ipe\ipecmd.exe"
set "DEVICE=16F1934"
set "TOOL=PPK3"

if not exist "%IPECMD%" (
    echo   ipecmd.exe not found: %IPECMD%
    pause
    exit /b 1
)

set "HEX=%~1"
if "%HEX%"=="" (
    for /f "delims=" %%F in ('dir /b /o-d *.hex 2^>nul') do (
        set "HEX=%%~fF"
        goto :gothex
    )
)
:gothex
if "%HEX%"=="" (
    echo   No .hex in this folder.
    pause
    exit /b 1
)

echo ============================================================
echo   PIC%DEVICE% via PICkit 3 - EEPROM only, firmware preserved
echo   File: %HEX%
echo ============================================================
echo.

"%IPECMD%" -P%DEVICE% -T%TOOL% -F"%HEX%" -ME -OH -W -OL
set "RC=%errorlevel%"

echo.
if "%RC%"=="0" (
    echo   OK - EEPROM written, firmware untouched.
) else (
    echo   FAILED ^(code %RC%^) - close the PICkit 3 Programmer app and retry.
)
echo.
pause
exit /b %RC%
