@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ============================================================
REM  Flash a .hex into PIC16F1934 with PICkit 3 (one click)
REM  Uses ipecmd.exe from MPLAB IPE / MPLAB X.
REM  NOTE: PICkit 3 works only in MPLAB X v6.15 or older
REM        (removed in v6.20+). Install v6.15 or v5.50.
REM ============================================================

REM ---- settings (change here if needed) ----
set "DEVICE=16F1934"
set "TOOL=PPK3"
REM Power the target from the PICkit? 1 = yes (PICkit feeds VDD),
REM 0 = target has its own power. Set to 1 only if your board is
REM NOT self-powered.
set "POWER_FROM_TOOL=0"
set "VDD=5.0"

REM ---- locate ipecmd.exe ----
set "IPECMD="
for /d %%V in ("C:\Program Files\Microchip\MPLABX\v*") do set "IPECMD=%%V\mplab_platform\bin\ipecmd.exe"
for /d %%V in ("C:\Program Files (x86)\Microchip\MPLABX\v*") do set "IPECMD=%%V\mplab_platform\bin\ipecmd.exe"

if not exist "%IPECMD%" (
    echo.
    echo   ipecmd.exe not found.
    echo   Install MPLAB IPE ^(free, part of MPLAB X v6.15 or older^),
    echo   or set the IPECMD path manually in this file.
    echo.
    pause
    exit /b 1
)

REM ---- choose the .hex: dragged onto the bat, or newest in folder ----
set "HEX=%~1"
if "%HEX%"=="" (
    for /f "delims=" %%F in ('dir /b /o-d *.hex 2^>nul') do (
        set "HEX=%%~fF"
        goto :gothex
    )
)
:gothex
if "%HEX%"=="" (
    echo   No .hex file found in this folder.
    pause
    exit /b 1
)

set "POWERARG="
if "%POWER_FROM_TOOL%"=="1" set "POWERARG=-A%VDD%"

echo ============================================================
echo   Device : PIC%DEVICE%
echo   Tool   : PICkit 3
echo   File   : %HEX%
echo ============================================================
echo.

"%IPECMD%" -T%TOOL% -P%DEVICE% -F"%HEX%" -M -Y %POWERARG% -OL
set "RC=%errorlevel%"

echo.
if "%RC%"=="0" (
    echo   OK - programmed and verified.
) else (
    echo   FAILED ^(code %RC%^). See the messages above.
)
echo.
pause
exit /b %RC%
