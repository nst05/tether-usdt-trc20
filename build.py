"""
Сборка CRM Исламская рассрочка в одиночный .exe
Запуск: python build.py
"""
import subprocess
import sys
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(ROOT, 'crm_islamic.spec')
REQS = os.path.join(ROOT, 'requirements.txt')
DIST = os.path.join(ROOT, 'dist')


def run(cmd, **kw):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}\n")
    result = subprocess.run(cmd, **kw)
    if result.returncode != 0:
        print(f"\n[ОШИБКА] Команда завершилась с кодом {result.returncode}")
        sys.exit(result.returncode)


def main():
    print("=" * 60)
    print("  ☪  Сборка CRM Исламская рассрочка (одиночный .exe)")
    print("=" * 60)

    # 1. Проверка Python версии
    if sys.version_info < (3, 10):
        print("[ОШИБКА] Требуется Python 3.10 или новее.")
        sys.exit(1)

    # 2. Установка зависимостей
    print("\n[1/4] Установка зависимостей...")
    run([sys.executable, '-m', 'pip', 'install',
         '-r', REQS, 'pyinstaller>=6.0', '--quiet'])

    # 3. Очистка предыдущей сборки
    print("\n[2/4] Очистка предыдущей сборки...")
    for folder in ['build', os.path.join(DIST, 'crm_islamic')]:
        path = os.path.join(ROOT, folder)
        if os.path.exists(path):
            shutil.rmtree(path)
            print(f"  Удалено: {path}")
    # Удалить старый одиночный exe если был
    old_exe = os.path.join(DIST, 'crm_islamic.exe')
    if os.path.exists(old_exe):
        os.remove(old_exe)

    # 4. Компиляция
    print("\n[3/4] Компиляция (это займёт 1-3 минуты)...")
    run([sys.executable, '-m', 'PyInstaller', '--noconfirm', SPEC], cwd=ROOT)

    # 5. Итог
    exe_name = 'crm_islamic.exe' if sys.platform == 'win32' else 'crm_islamic'
    exe_path = os.path.join(DIST, exe_name)

    print("\n[4/4] Готово!")
    print("=" * 60)
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print(f"  Файл:   {exe_path}")
        print(f"  Размер: {size_mb:.1f} МБ")
        print()
        print("  Запуск:")
        print(f"    {exe_path}")
        print("    Откройте браузер: http://localhost:5000")
        print()
        print("  База данных и загруженные файлы хранятся рядом с .exe")
    else:
        print("[ОШИБКА] Файл не найден — проверьте вывод выше.")
    print("=" * 60)


if __name__ == '__main__':
    main()
