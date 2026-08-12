@echo off
setlocal
set "IPECMD=C:\Program Files\Microchip\MPLABX\v6.00\mplab_platform\mplab_ipe\ipecmd.exe"
set "OUT=%~dp0ipecmd_help.txt"

echo Dumping ipecmd options to ipecmd_help.txt ...
> "%OUT%" echo ===== ipecmd -? =====
"%IPECMD%" -? >> "%OUT%" 2>&1
>> "%OUT%" echo.
>> "%OUT%" echo ===== ipecmd (no args) =====
"%IPECMD%" >> "%OUT%" 2>&1

echo.
echo Saved: %OUT%
echo Send that file back.
pause
