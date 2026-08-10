# -*- coding: utf-8 -*-
"""
Компиляция ядра vf_core в машинный код (нативный .pyd) через Cython.

Зачем: после этого логика формирования байтов лежит в exe как обычный
скомпилированный C-модуль, а не как Python-байткод. Декомпиляторами
(uncompyle6, decompyle3, pycdc) её уже не восстановить — только
дизассемблировать в ассемблер, что несопоставимо сложнее.

Запуск (обычно вызывается из build_all.bat):
    pip install cython
    python compile_core.py

Если Cython или компилятор C недоступны, скрипт просто печатает
предупреждение и завершается без ошибки — сборка exe продолжится с
обычным vf_core.py.
"""

import os
import shutil
import sys


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(root, 'vf_core.py')

    try:
        from Cython.Build import cythonize
        from setuptools import Extension
        from setuptools.dist import Distribution
    except ImportError:
        print('  Cython не установлен — ядро останется как vf_core.py '
              '(exe соберётся, но без нативной защиты ядра).')
        return 0

    # Копируем в .pyx, чтобы Cython его принял.
    pyx = os.path.join(root, 'vf_core.pyx')
    shutil.copyfile(src, pyx)

    try:
        ext = Extension('vf_core', [pyx])
        dist = Distribution({'ext_modules': cythonize(
            [ext],
            compiler_directives={'language_level': '3'},
            quiet=True,
        )})
        cmd = dist.get_command_obj('build_ext')
        cmd.inplace = True
        cmd.ensure_finalized()
        cmd.run()
    except Exception as exc:                    # noqa: BLE001
        print('  Компиляция ядра не удалась (%s).' % exc)
        print('  Нужен компилятor C: на Windows — "Build Tools for Visual Studio".')
        print('  Exe соберётся с обычным vf_core.py.')
        return 0
    finally:
        for junk in (pyx, os.path.join(root, 'vf_core.c')):
            if os.path.exists(junk):
                os.remove(junk)
        build_dir = os.path.join(root, 'build')
        if os.path.isdir(build_dir):
            shutil.rmtree(build_dir, ignore_errors=True)

    built = [f for f in os.listdir(root)
             if f.startswith('vf_core') and (f.endswith('.pyd') or f.endswith('.so'))]
    if built:
        print('  Ядро скомпилировано в нативный модуль: %s' % built[0])
        print('  PyInstaller подхватит его вместо vf_core.py.')
    else:
        print('  Нативный модуль не найден после сборки — используется vf_core.py.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
