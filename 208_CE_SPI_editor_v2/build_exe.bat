@echo off
rem Сборка CE208_Editor.exe одним файлом. Требуется Python 3 с Tkinter.
setlocal
cd /d "%~dp0"

set "CE208_PYTHON=C:\Users\ixd\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%CE208_PYTHON%" (
    where py >nul 2>&1
    if errorlevel 1 (
        echo Python 3 ne naiden. Ustanovite Python 3 s Tkinter.
        pause
        exit /b 1
    )
    set "CE208_PYTHON=py -3"
)

echo [1/3] Ustanovka PyInstaller...
%CE208_PYTHON% -m pip install --upgrade pyinstaller || goto :error

echo [2/3] Ochistka predydushchey sborki...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] Sborka CE208_Editor.exe...
%CE208_PYTHON% -m PyInstaller --noconfirm ce208_editor.spec || goto :error

echo.
echo Gotovo: dist\CE208_Editor.exe
pause
exit /b 0

:error
echo.
echo Sborka ne udalas. Smotrite soobshcheniya vyshe.
pause
exit /b 1
