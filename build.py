"""
Build script — компилирует CRM в исполняемый файл.
Запуск:  python build.py
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def run(cmd, **kw):
    print(f"\n>>> {' '.join(cmd)}\n")
    result = subprocess.run(cmd, **kw)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main():
    print("=" * 60)
    print("  ☪  Сборка CRM Исламская рассрочка")
    print("=" * 60)

    # 1. Install build deps
    print("\n[1/4] Установка зависимостей...")
    run([sys.executable, '-m', 'pip', 'install',
         '-r', os.path.join(ROOT, 'crm_islamic', 'requirements.txt'),
         'pyinstaller', '--quiet'])

    # 2. Clean previous build
    print("\n[2/4] Очистка предыдущей сборки...")
    for folder in ['build', os.path.join(ROOT, 'dist', 'crm_islamic')]:
        path = os.path.join(ROOT, folder)
        if os.path.exists(path):
            shutil.rmtree(path)
            print(f"  Удалено: {path}")

    # 3. Run PyInstaller
    print("\n[3/4] Компиляция (PyInstaller)...")
    run([
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        os.path.join(ROOT, 'crm_islamic.spec'),
    ], cwd=ROOT)

    # 4. Report
    dist = os.path.join(ROOT, 'dist', 'crm_islamic')
    exe_name = 'crm_islamic.exe' if sys.platform == 'win32' else 'crm_islamic'
    exe_path = os.path.join(dist, exe_name)

    print("\n[4/4] Готово!")
    print("=" * 60)
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print(f"  Исполняемый файл: {exe_path}")
        print(f"  Размер:           {size_mb:.1f} МБ")
    print(f"  Папка сборки:     {dist}/")
    print()
    print("  Запуск:")
    print(f"    cd dist/crm_islamic && ./{exe_name}")
    print("    Откройте браузер: http://localhost:5000")
    print("=" * 60)


if __name__ == '__main__':
    main()
