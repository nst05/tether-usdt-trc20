@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Сборка VF Gen
echo ============================================================

echo.
echo [1/4] Установка зависимостей...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error

echo.
echo [2/4] Компиляция ядра в машинный код (защита исходника)...
echo       Если Cython/компилятор не установлены — шаг пропускается,
echo       exe всё равно соберётся (без нативного ядра).
python -m pip install cython >nul 2>&1
python compile_core.py
REM ошибку компиляции ядра не считаем фатальной

echo.
echo [3/4] Сборка программы (VF_Gen.exe)...
python -m PyInstaller --noconfirm vf_gen.spec
if errorlevel 1 goto error

echo.
echo [4/4] Сборка генератора ключей (keygen_vf.exe)...
python -m PyInstaller --noconfirm keygen_vf.spec
if errorlevel 1 goto error

echo.
echo ============================================================
echo   Готово:
echo     dist\VF_Gen.exe     - программа для клиента
echo     dist\keygen_vf.exe  - генератор ключей, КЛИЕНТУ НЕ ДАВАТЬ
echo ============================================================
pause
exit /b 0

:error
echo.
echo ОШИБКА СБОРКИ. Смотрите сообщения выше.
pause
exit /b 1
