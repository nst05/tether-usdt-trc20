@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ================================================================
echo   Sborka MERK-3F (vse vkladki)
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
rem pod 32-bitnyy - CH341DLL.dll. Odinarnyh kavychek v kode byt ne dolzhno,
rem inache razedetsya kavychkovanie samogo for /f.
set "BITS="
for /f %%b in ('%PY% -c "import struct;print(struct.calcsize(chr(80))*8)"') do set "BITS=%%b"
if not defined BITS set "BITS=64"
echo       Razryadnost: !BITS! bit

rem ---- 2. Proverka fajlov ----------------------------------------
echo.
echo [2/7] Proverka fajlov...
set "MISSING="
for %%f in (srt_mod_spi.py spi_memory.py splash_screen.py make_icon.py pyi_rth_ch341.py merk3f_full.spec) do (
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
%PY% -m pip install --quiet PyQt5 "pyinstaller>=6.0"
if errorlevel 1 (
    echo [OSHIBKA] Ne udalos ustanovit zavisimosti.
    echo Proverte podklyuchenie k internetu i prava dostupa.
    goto :fail
)
echo       PyQt5, pyinstaller - gotovo.

rem ---- 4. Ikonka i zastavka --------------------------------------
echo.
echo [4/7] Ikonka i zastavka...
rem Otdelnyy flag vmesto vlozhennyh if: v cmd "if A if B (X) else (Y)"
rem privyazyvaet else k vnutrennemu if, i pri otsutstvii pervogo fayla
rem ne vypolnyaetsya ni odna vetka.
set "NEEDGEN=1"
if exist icon_srt.ico if exist icon_srt_splash.png set "NEEDGEN="

if defined NEEDGEN (
    %PY% make_icon.py srt
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
    echo       Sborka prodolzhitsya, no rabotat s mikroshemoy programma
    echo       smozhet tolko esli !DLL! okazhetsya ryadom s gotovym exe
    echo       ili v sisteme. Fayl idet s drayverami programmatora
    echo       CH341 ot WCH.
    echo.
)

rem ---- 6. Ochistka i sborka --------------------------------------
echo.
echo [6/7] Kompilyatsiya...
if exist build rd /s /q build
if exist "dist\MERK-3F.exe" del /q "dist\MERK-3F.exe"

%PY% -m PyInstaller --noconfirm --clean merk3f_full.spec
if errorlevel 1 (
    echo.
    echo [OSHIBKA] Kompilyatsiya ne udalas. Tekst oshibki vyshe.
    goto :fail
)

rem ---- 7. Rezultat -----------------------------------------------
echo.
echo [7/7] Proverka rezultata...
if not exist "dist\MERK-3F.exe" (
    echo [OSHIBKA] exe ne sozdan, hotya PyInstaller ne soobshchil ob oshibke.
    goto :fail
)

set "SIZE=0"
for %%f in ("dist\MERK-3F.exe") do set /a SIZE=%%~zf/1048576

echo.
echo ================================================================
echo   Gotovo
echo ================================================================
echo.
echo   Fayl:    %CD%\dist\MERK-3F.exe
echo   Razmer:  !SIZE! MB
echo   Vkladki: ART, AR, 231-AT-01
echo.
if not exist "!DLL!" (
    echo   VAZHNO: polozhite !DLL! ryadom s exe, inache svyazi
    echo   s programmatorom ne budet.
    echo.
)
echo   Poryadok raboty:
echo     1. Zapustit exe
echo     2. Vybrat tip mikroshemy
echo     3. "Opredelit" - proverit svyaz
echo     4. "Prochitat iz pamyati"
echo     5. Popravit znacheniya i "Zapisat v pamyat"
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
