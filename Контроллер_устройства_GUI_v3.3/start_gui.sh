#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python3 -c 'import tkinter, serial' >/dev/null 2>&1 || {
  echo 'Нужны tkinter и pyserial. Установите зависимости из README_GUI.md.' >&2
  exit 1
}
exec python3 smt_gui.py
