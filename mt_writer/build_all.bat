@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Сборка MT Writer
echo ============================================================

echo.
echo [1/3] Установка зависимостей...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error

echo.
echo [2/3] Сборка программы (MT_Writer.exe)...
python -m PyInstaller --noconfirm mt_writer.spec
if errorlevel 1 goto error

echo.
echo [3/3] Сборка генератора ключей (keygen_mt.exe)...
python -m PyInstaller --noconfirm keygen_mt.spec
if errorlevel 1 goto error

echo.
echo ============================================================
echo   Готово:
echo     dist\MT_Writer.exe   - программа для клиента
echo     dist\keygen_mt.exe   - генератор ключей, КЛИЕНТУ НЕ ДАВАТЬ
echo ============================================================
pause
exit /b 0

:error
echo.
echo ОШИБКА СБОРКИ. Смотрите сообщения выше.
pause
exit /b 1
