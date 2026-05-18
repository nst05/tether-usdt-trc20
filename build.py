"""
Сборка CRM Исламская рассрочка — автономное GUI приложение.
Запуск: python build.py
Результат: dist/CRM_Murabaha.exe
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
    print("  ☪  Сборка CRM Исламская рассрочка — GUI приложение")
    print("=" * 60)

    if sys.version_info < (3, 10):
        print("[ОШИБКА] Требуется Python 3.10+")
        sys.exit(1)

    # 1. Зависимости
    print("\n[1/4] Установка зависимостей...")
    run([sys.executable, '-m', 'pip', 'install',
         '-r', REQS,
         'pywebview>=4.4',
         'pyinstaller>=6.0',
         '--quiet'])

    # 2. Очистка
    print("\n[2/4] Очистка предыдущей сборки...")
    for folder in ['build']:
        p = os.path.join(ROOT, folder)
        if os.path.exists(p):
            shutil.rmtree(p)
            print(f"  Удалено: {p}")
    old_exe = os.path.join(DIST, 'CRM_Murabaha.exe')
    if os.path.exists(old_exe):
        os.remove(old_exe)
        print(f"  Удалено: {old_exe}")

    # 3. Компиляция
    print("\n[3/4] Компиляция (2–5 минут)...")
    run([sys.executable, '-m', 'PyInstaller', '--noconfirm', SPEC], cwd=ROOT)

    # 4. Результат
    exe_path = os.path.join(DIST, 'CRM_Murabaha.exe')

    print("\n[4/4] Готово!")
    print("=" * 60)
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print(f"  Файл:   {exe_path}")
        print(f"  Размер: {size_mb:.1f} МБ")
        print()
        print("  Запуск: двойной клик на CRM_Murabaha.exe")
        print("  База данных и файлы хранятся рядом с .exe")
    else:
        print("[ОШИБКА] Файл не создан — проверьте вывод выше.")
    print("=" * 60)


if __name__ == '__main__':
    main()
