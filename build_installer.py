"""
Сборка CRM в установщик Windows (Inno Setup).
Результат: dist/installer/CRM_Murabaha_Setup.exe

Требования:
  - Python 3.10+
  - Inno Setup 6  →  https://jrsoftware.org/isdl.php

Запуск: python build_installer.py
"""
import subprocess
import sys
import os
import shutil

ROOT  = os.path.dirname(os.path.abspath(__file__))
SPEC  = os.path.join(ROOT, 'crm_islamic_folder.spec')
REQS  = os.path.join(ROOT, 'requirements.txt')
DIST  = os.path.join(ROOT, 'dist')
ISS   = os.path.join(ROOT, 'installer.iss')

# Стандартные места установки Inno Setup
ISCC_PATHS = [
    r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    r'C:\Program Files\Inno Setup 6\ISCC.exe',
    r'C:\Program Files (x86)\Inno Setup 5\ISCC.exe',
    r'C:\Program Files\Inno Setup 5\ISCC.exe',
]


def run(cmd, **kw):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}\n")
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        print(f"\n[ОШИБКА] Код {r.returncode}")
        sys.exit(r.returncode)


def find_iscc():
    # Из PATH
    iscc = shutil.which('iscc') or shutil.which('ISCC')
    if iscc:
        return iscc
    for p in ISCC_PATHS:
        if os.path.exists(p):
            return p
    return None


def main():
    print("=" * 62)
    print("  ☪  Сборка CRM — Установщик Windows")
    print("=" * 62)

    if sys.version_info < (3, 10):
        print("[ОШИБКА] Требуется Python 3.10+")
        sys.exit(1)

    # 1. Зависимости
    print("\n[1/4] Установка зависимостей...")
    run([sys.executable, '-m', 'pip', 'install',
         '-r', REQS, 'pywebview>=4.4', 'pyinstaller>=6.0', '--quiet'])

    # 2. Очистка папки сборки
    print("\n[2/4] Очистка предыдущей сборки...")
    folder_dist = os.path.join(DIST, 'CRM_Murabaha')
    for d in ['build', folder_dist]:
        p = os.path.join(ROOT, d)
        if os.path.exists(p):
            shutil.rmtree(p)
            print(f"  Удалено: {p}")

    # 3. PyInstaller (папочный режим — быстрый старт)
    print("\n[3/4] Компиляция PyInstaller (папочный режим)...")
    run([sys.executable, '-m', 'PyInstaller', '--noconfirm', SPEC], cwd=ROOT)

    if not os.path.isdir(folder_dist):
        print(f"[ОШИБКА] Папка не создана: {folder_dist}")
        sys.exit(1)

    # 4. Inno Setup
    print("\n[4/4] Сборка установщика (Inno Setup)...")
    iscc = find_iscc()

    installer_dir = os.path.join(DIST, 'installer')
    installer_exe = os.path.join(installer_dir, 'CRM_Murabaha_Setup.exe')

    if iscc:
        os.makedirs(installer_dir, exist_ok=True)
        run([iscc, ISS], cwd=ROOT)
    else:
        print()
        print("  [!] Inno Setup не найден — установщик НЕ создан.")
        print()
        print("  Установите Inno Setup 6:")
        print("  https://jrsoftware.org/isdl.php")
        print()
        print("  Затем запустите вручную:")
        print(f'  iscc "{ISS}"')
        print()
        print("  Или сразу откройте installer.iss в Inno Setup IDE.")

    print()
    print("=" * 62)

    if iscc and os.path.exists(installer_exe):
        size_mb = os.path.getsize(installer_exe) / 1024 / 1024
        print(f"  Установщик: {installer_exe}")
        print(f"  Размер:     {size_mb:.1f} МБ")
        print()
        print("  Запустите CRM_Murabaha_Setup.exe на компьютере клиента.")
        print("  Устанавливает в Program Files, создаёт ярлыки.")
        print("  Данные (БД, документы) → %LOCALAPPDATA%\\CRM_Murabaha\\")
    else:
        folder_size = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fns in os.walk(folder_dist)
            for f in fns
        ) / 1024 / 1024
        print(f"  Папка с программой: {folder_dist}")
        print(f"  Размер папки:       {folder_size:.0f} МБ")
        print()
        print("  После установки Inno Setup запустите:")
        print(f'  iscc "{ISS}"')

    print("=" * 62)


if __name__ == '__main__':
    main()
