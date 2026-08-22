@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ================================================================
echo   Сборка integra101
echo ================================================================
echo.

rem ── 1. Проверка Python ────────────────────────────────────────────
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"

if not defined PY (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY=python"
)

if not defined PY (
    echo [ОШИБКА] Python не найден.
    echo.
    echo Установите Python 3.8 или новее с python.org
    echo При установке обязательно отметьте "Add Python to PATH".
    goto :fail
)

for /f "tokens=*" %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
echo [1/6] Python: !PYVER!

rem Разрядность важна: под 64-битный Python нужна CH341DLLA64.dll,
rem под 32-битный — CH341DLL.dll. Одинарных кавычек в коде быть не должно,
rem иначе разъедется кавычкование самого for /f.
for /f %%b in ('%PY% -c "import sys;print(64 if sys.maxsize^>2**32 else 32)"') do set "BITS=%%b"
echo       Разрядность: !BITS! бит

rem ── 2. Проверка исходников ────────────────────────────────────────
echo.
echo [2/6] Проверка файлов...
set "MISSING="
for %%f in (crc_storage_gui.py crc_storage_i2c.py crc_storage_writer.spec pyi_rth_ch341.py) do (
    if not exist "%%f" set "MISSING=!MISSING! %%f"
)
if defined MISSING (
    echo [ОШИБКА] Не хватает файлов:!MISSING!
    echo Распакуйте архив целиком и запускайте .bat из той же папки.
    goto :fail
)
echo       Все файлы на месте.

rem ── 3. Зависимости ────────────────────────────────────────────────
echo.
echo [3/6] Установка зависимостей...
%PY% -m pip install --upgrade pip --quiet
rem PyInstaller 6+: spec написан под его форму EXE(pyz, a.scripts, a.binaries,
rem a.datas, ...) — в 5.x там ещё был отдельный a.zipfiles.
%PY% -m pip install --quiet PyQt5 i2cpy "pyinstaller>=6.0"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости.
    echo Проверьте подключение к интернету и права доступа.
    goto :fail
)
echo       PyQt5, i2cpy, pyinstaller — готово.

rem ── 4. Проверка DLL для CH341 ─────────────────────────────────────
echo.
echo [4/6] Библиотека CH341...
if "!BITS!"=="64" (set "DLL=CH341DLLA64.dll") else (set "DLL=CH341DLL.dll")

if exist "!DLL!" (
    echo       !DLL! найдена, будет включена в сборку.
) else (
    echo       [ВНИМАНИЕ] !DLL! рядом с .bat не найдена.
    echo.
    echo       Сборка продолжится, но записывать в микросхему програм-
    echo       ма сможет только если !DLL! окажется рядом с готовым
    echo       exe или в системе. Файл идёт с драйверами программатора
    echo       CH341 от WCH.
    echo.
)

rem ── 5. Очистка и сборка ───────────────────────────────────────────
echo.
echo [5/6] Компиляция...
if exist build rd /s /q build
if exist "dist\integra101.exe" del /q "dist\integra101.exe"

%PY% -m PyInstaller --noconfirm --clean crc_storage_writer.spec
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Компиляция не удалась. Текст ошибки выше.
    goto :fail
)

rem ── 6. Результат ──────────────────────────────────────────────────
echo.
echo [6/6] Проверка результата...
if not exist "dist\integra101.exe" (
    echo [ОШИБКА] exe не создан, хотя PyInstaller не сообщил об ошибке.
    goto :fail
)

for %%f in ("dist\integra101.exe") do set /a SIZE=%%~zf/1048576

echo.
echo ================================================================
echo   Готово
echo ================================================================
echo.
echo   Файл:   %CD%\dist\integra101.exe
echo   Размер: !SIZE! МБ
echo.
if not exist "!DLL!" (
    echo   ВАЖНО: положите !DLL! рядом с exe, иначе запись
    echo   в микросхему работать не будет.
    echo.
)
echo   Порядок работы:
echo     1. Запустить exe
echo     2. Вкладка "I2C/EEPROM"
echo     3. Нажать "Определить чип"
echo     4. Нажать "Найти записи"
echo     5. Ввести значение в нужный слот и нажать "Записать"
echo.
goto :done

:fail
echo.
echo ================================================================
echo   Сборка прервана
echo ================================================================
echo.
pause
exit /b 1

:done
pause
exit /b 0
