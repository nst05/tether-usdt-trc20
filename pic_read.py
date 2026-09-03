#!/usr/bin/env python3
"""
PIC16LF1934 Firmware Reader Script
Пытается считать прошивку с микроконтроллера
"""

import subprocess
import sys
import os
from pathlib import Path

class PICReader:
    def __init__(self):
        self.pic_model = "PIC16LF1934"
        self.output_file = f"{self.pic_model}_firmware.hex"

    def check_programmer(self):
        """Проверить наличие pk2cmd"""
        try:
            result = subprocess.run(['pk2cmd', '-?'],
                                  capture_output=True, text=True)
            print("✓ pk2cmd найден")
            return True
        except FileNotFoundError:
            print("✗ pk2cmd не найден. Установите MPLAB X IDE или pk2cmd")
            return False

    def get_device_info(self):
        """Получить информацию о подключенном микроконтроллере"""
        print("\n[*] Проверка подключения микроконтроллера...")
        try:
            result = subprocess.run(['pk2cmd', '-P', self.pic_model, '-I'],
                                  capture_output=True, text=True, timeout=5)
            print(result.stdout)
            if result.returncode == 0:
                print("✓ Микроконтроллер подключен")
                return True
            else:
                print("✗ Не удалось подключиться к микроконтроллеру")
                print(result.stderr)
                return False
        except subprocess.TimeoutExpired:
            print("✗ Timeout при подключении")
            return False
        except Exception as e:
            print(f"✗ Ошибка: {e}")
            return False

    def read_firmware(self):
        """Попытка считать прошивку"""
        print(f"\n[*] Попытка чтения прошивки с {self.pic_model}...")
        print(f"    Вывод в файл: {self.output_file}")

        try:
            # Попытка 1: Полное чтение
            cmd = ['pk2cmd', '-P', self.pic_model, '-R', '-O', self.output_file]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            print(result.stdout)

            if result.returncode == 0 and os.path.exists(self.output_file):
                size = os.path.getsize(self.output_file)
                print(f"✓ Прошивка успешно считана! ({size} байт)")
                print(f"  Файл сохранен: {self.output_file}")
                return True
            else:
                print("✗ Ошибка при чтении:")
                print(result.stderr)
                return False

        except subprocess.TimeoutExpired:
            print("✗ Timeout при чтении (может быть защита)")
            return False
        except Exception as e:
            print(f"✗ Ошибка: {e}")
            return False

    def read_config(self):
        """Чтение конфигурационных слов (может быть доступно)"""
        print(f"\n[*] Попытка чтения конфигурации...")
        try:
            cmd = ['pk2cmd', '-P', self.pic_model, '-RC']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            print(result.stdout)
            if result.returncode == 0:
                print("✓ Конфиг считан")
                return True
            else:
                print("✗ Не удалось считать конфиг")
                return False
        except Exception as e:
            print(f"✗ Ошибка: {e}")
            return False


    def run(self):
        """Основная программа"""
        print("=" * 60)
        print("PIC16LF1934 Firmware Reader (Read-Only)")
        print("=" * 60)

        if not self.check_programmer():
            sys.exit(1)

        if not self.get_device_info():
            print("\n[!] Микроконтроллер не подключен!")
            sys.exit(1)

        print("\n" + "=" * 60)
        print("Выберите операцию:")
        print("1. Считать прошивку (попытка)")
        print("2. Считать конфигурацию")
        print("0. Выход")
        print("=" * 60)

        choice = input("\nВводьте номер (0-2): ").strip()

        if choice == '1':
            self.read_firmware()
        elif choice == '2':
            self.read_config()
        elif choice == '0':
            print("Выход")
        else:
            print("Неверный выбор")

if __name__ == "__main__":
    reader = PICReader()
    reader.run()
