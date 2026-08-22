@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ================================================================
echo   Sborka integra101
echo ================================================================
echo.

rem ---- 1. Poisk Python -------------------------------------------
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"

if not defined PY (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY=python"
)

if not defined PY (
    echo [OSHIBKA] Python ne nayden.
    echo.
    echo Ustanovite Python 3.8 ili novee s python.org
    echo Pri ustanovke otmette "Add Python to PATH".
    goto :fail
)

for /f "tokens=*" %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
echo [1/7] Python: !PYVER!

rem Razryadnost: pod 64-bitnyy Python nuzhna CH341DLLA64.dll,
rem pod 32-bitnyy - CH341DLL.dll.
set "BITS="
for /f %%b in ('%PY% -c "import struct;print(struct.calcsize(chr(80))*8)"') do set "BITS=%%b"
if not defined BITS set "BITS=64"
echo       Razryadnost: !BITS! bit

rem ---- 2. Proverka fajlov ----------------------------------------
echo.
echo [2/7] Proverka fajlov...
set "MISSING="
for %%f in (crc_storage_gui.py crc_storage_i2c.py crc_storage_writer.spec pyi_rth_ch341.py splash_screen.py make_icon.py) do (
    if not exist "%%f" set "MISSING=!MISSING! %%f"
)
if defined MISSING (
    echo [OSHIBKA] Ne hvataet fajlov:!MISSING!
    echo Raspakuyte arhiv tselikom i zapuskayte .bat iz toy zhe papki.
    goto :fail
)
echo       Vse fajly na meste.

rem ---- 3. Zavisimosti --------------------------------------------
echo.
echo [3/7] Ustanovka zavisimostey...
%PY% -m pip install --upgrade pip --quiet
rem PyInstaller 6+: spec napisan pod ego formu EXE(...).
%PY% -m pip install --quiet PyQt5 i2cpy "pyinstaller>=6.0"
if errorlevel 1 (
    echo [OSHIBKA] Ne udalos ustanovit zavisimosti.
    echo Proverte podklyuchenie k internetu i prava dostupa.
    goto :fail
)
echo       PyQt5, i2cpy, pyinstaller - gotovo.

rem ---- 4. Ikonka i zastavka --------------------------------------
echo.
echo [4/7] Ikonka i zastavka...
rem Otdelnyy flag vmesto vlozhennyh if: v cmd "if A if B (X) else (Y)"
rem privyazyvaet else k vnutrennemu if, i pri otsutstvii icon.ico ne
rem vypolnyaetsya ni odna vetka.
set "NEEDGEN=1"
if exist icon.ico if exist splash.png set "NEEDGEN="

if defined NEEDGEN (
    %PY% make_icon.py
    if errorlevel 1 (
        echo       [VNIMANIE] Ne udalos sgenerirovat ikonku.
        echo       Sborka prodolzhitsya so standartnoy ikonkoy Windows.
    )
) else (
    echo       Uzhe est, propuskayu.
)

rem ---- 5. Biblioteka CH341 ---------------------------------------
echo.
echo [5/7] Biblioteka CH341...
if "!BITS!"=="64" (set "DLL=CH341DLLA64.dll") else (set "DLL=CH341DLL.dll")

if exist "!DLL!" (
    echo       !DLL! naydena, budet vklyuchena v sborku.
) else (
    echo       [VNIMANIE] !DLL! ryadom s .bat ne naydena.
    echo.
    echo       Sborka prodolzhitsya, no pisat v mikroshemu programma
    echo       smozhet tolko esli !DLL! okazhetsya ryadom s gotovym exe
    echo       ili v sisteme. Fayl idet s drayverami programmatora
    echo       CH341 ot WCH.
    echo.
)

rem ---- 6. Ochistka i sborka --------------------------------------
echo.
echo [6/7] Kompilyatsiya...
if exist build rd /s /q build
if exist "dist\integra101.exe" del /q "dist\integra101.exe"

%PY% -m PyInstaller --noconfirm --clean crc_storage_writer.spec
if errorlevel 1 (
    echo.
    echo [OSHIBKA] Kompilyatsiya ne udalas. Tekst oshibki vyshe.
    goto :fail
)

rem ---- 7. Rezultat -----------------------------------------------
echo.
echo [7/7] Proverka rezultata...
if not exist "dist\integra101.exe" (
    echo [OSHIBKA] exe ne sozdan, hotya PyInstaller ne soobshchil ob oshibke.
    goto :fail
)

set "SIZE=0"
for %%f in ("dist\integra101.exe") do set /a SIZE=%%~zf/1048576

echo.
echo ================================================================
echo   Gotovo
echo ================================================================
echo.
echo   Fayl:   %CD%\dist\integra101.exe
echo   Razmer: !SIZE! MB
echo.
if not exist "!DLL!" (
    echo   VAZHNO: polozhite !DLL! ryadom s exe, inache zapis
    echo   v mikroshemu rabotat ne budet.
    echo.
)
echo   Poryadok raboty:
echo     1. Zapustit exe
echo     2. Vkladka "I2C/EEPROM"
echo     3. Nazhat "Opredelit chip"
echo     4. Nazhat "Nayti zapisi"
echo     5. Vvesti znachenie v slot i nazhat "Zapisat"
echo.
goto :done

:fail
echo.
echo ================================================================
echo   Sborka prervana
echo ================================================================
echo.
pause
exit /b 1

:done
pause
exit /b 0
