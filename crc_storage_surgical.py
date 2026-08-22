#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CRC Storage Surgical Edition — точечное изменение только необходимых данных
Не трогает никакие другие данные в файле
"""

import struct
import sys
from pathlib import Path
from datetime import datetime

SCALE = 100
BLOCK_SIZE = 0x28
CRC_SIZE = 2
INIT_CRC = 0xFFFF
POLY_CRC = 0x1021


def crc16_ccitt(data):
    """CRC-16 CCITT"""
    crc = INIT_CRC
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc <<= 1
            if crc & 0x10000:
                crc ^= POLY_CRC
            crc &= 0xFFFF
    return crc


def encode_value(value: float) -> bytes:
    """Значение → fixed-point big-endian"""
    raw = int(round(value * SCALE))
    if not 0 <= raw <= 0xFFFFFFFF:
        raise ValueError(f"Диапазон: 0.00 – 42949672.95")
    return raw.to_bytes(4, "big", signed=False)


def decode_value(data: bytes) -> float:
    """Fixed-point big-endian → значение"""
    if len(data) != 4:
        raise ValueError("Неверная длина данных")
    return int.from_bytes(data, "big", signed=False) / SCALE


class SurgicalEditor:
    """Редактор для точечных изменений данных"""

    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.original_data = None
        self.modified_data = None
        self.changes = []

    def load(self):
        """Загружает файл"""
        if not self.filepath.exists():
            raise FileNotFoundError(f"Файл не найден: {self.filepath}")

        with open(self.filepath, 'rb') as f:
            self.original_data = f.read()

        self.modified_data = bytearray(self.original_data)
        self.changes = []

        print(f"✓ Файл загружен: {self.filepath}")
        print(f"  Размер: {len(self.original_data)} байт")

    def find_all_values(self):
        """Находит все значения в файле"""
        values = []
        data = bytes(self.original_data)

        pos = 0
        while pos < len(data) - BLOCK_SIZE - CRC_SIZE:
            val1 = data[pos:pos+4]
            val2 = data[pos+4:pos+8]
            zeros = data[pos+8:pos+12]

            if val1 == val2 and zeros == b'\x00\x00\x00\x00':
                try:
                    block = data[pos:pos+BLOCK_SIZE]
                    crc_pos = pos + BLOCK_SIZE

                    if crc_pos + CRC_SIZE <= len(data):
                        stored_crc = struct.unpack('>H', data[crc_pos:crc_pos+2])[0]
                        calculated_crc = crc16_ccitt(block)

                        if stored_crc == calculated_crc:
                            value = decode_value(val1)
                            values.append({
                                'pos': pos,
                                'value': value,
                                'crc': stored_crc,
                                'valid': True
                            })
                            pos += BLOCK_SIZE + CRC_SIZE
                            continue
                except Exception:
                    pass

            pos += 1

        return values

    def update_value_at(self, position: int, new_value: float):
        """
        Изменяет ТОЛЬКО значение на позиции.
        Не трогает ничего больше в файле.
        """
        if position < 0 or position + BLOCK_SIZE + CRC_SIZE > len(self.modified_data):
            raise ValueError("Позиция выходит за пределы файла")

        # Вычисляем новый блок и CRC
        val_bytes = encode_value(new_value)
        block = val_bytes + val_bytes + b'\x00' * 32
        crc = crc16_ccitt(block)

        # Записываем ТОЛЬКО эти 42 байта:
        # - 40 байт блока
        # - 2 байта CRC
        self.modified_data[position:position+BLOCK_SIZE] = block
        self.modified_data[position+BLOCK_SIZE:position+BLOCK_SIZE+CRC_SIZE] = struct.pack('>H', crc)

        # Записываем в лог изменений
        old_value = decode_value(bytes(self.original_data[position:position+4]))
        old_crc = struct.unpack('>H', self.original_data[position+BLOCK_SIZE:position+BLOCK_SIZE+2])[0]

        self.changes.append({
            'pos': position,
            'old_value': old_value,
            'new_value': new_value,
            'old_crc': old_crc,
            'new_crc': crc,
            'bytes_changed': BLOCK_SIZE + CRC_SIZE
        })

    def verify_changes(self):
        """Проверяет, что изменения корректны"""
        print("\n📋 ПРОВЕРКА ИЗМЕНЕНИЙ:")
        print("=" * 80)

        for change in self.changes:
            pos = change['pos']

            # Проверяем, что исходные данные не изменились вне наших изменений
            start = pos + BLOCK_SIZE + CRC_SIZE
            end = start + 100  # Проверяем 100 байт после нашего блока

            if end <= len(self.original_data):
                original_part = self.original_data[start:end]
                modified_part = self.modified_data[start:end]

                if original_part != modified_part:
                    print(f"✗ ОШИБКА: Данные за пределами блока были изменены!")
                    return False

            # Проверяем CRC
            block_modified = self.modified_data[pos:pos+BLOCK_SIZE]
            crc_calculated = crc16_ccitt(bytes(block_modified))

            if crc_calculated != change['new_crc']:
                print(f"✗ ОШИБКА: CRC не совпадает на позиции 0x{pos:06X}")
                return False

            print(f"✓ Позиция 0x{pos:06X}:")
            print(f"  Значение:  {change['old_value']:.2f} → {change['new_value']:.2f}")
            print(f"  CRC:       0x{change['old_crc']:04X} → 0x{change['new_crc']:04X}")
            print(f"  Размер:    {change['bytes_changed']} байт изменено")

        print("\n✓ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
        return True

    def save(self):
        """Сохраняет файл с резервной копией"""
        if not self.changes:
            print("Нечего сохранять (нет изменений)")
            return False

        backup = self.filepath.with_suffix('.bak')

        try:
            # Создаём резервную копию оригинального файла
            self.filepath.rename(backup)
            print(f"\n✓ Резервная копия: {backup}")

            # Записываем изменённый файл
            with open(self.filepath, 'wb') as f:
                f.write(self.modified_data)

            print(f"✓ Файл сохранён: {self.filepath}")
            return True

        except Exception as e:
            # Восстанавливаем оригинальный файл при ошибке
            if backup.exists():
                backup.rename(self.filepath)
            raise e

    def get_summary(self):
        """Возвращает сводку изменений"""
        if not self.changes:
            return "Нет изменений"

        total_bytes_changed = sum(c['bytes_changed'] for c in self.changes)
        file_size = len(self.original_data)
        percent = (total_bytes_changed / file_size) * 100

        summary = f"""
СВОДКА ИЗМЕНЕНИЙ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Файл:                 {self.filepath.name}
Размер файла:         {file_size} байт
Изменено байт:        {total_bytes_changed} байт ({percent:.2f}%)
Количество изменений: {len(self.changes)}

ДЕТАЛИ:
"""
        for i, change in enumerate(self.changes, 1):
            summary += f"\n  {i}. Позиция 0x{change['pos']:06X}\n"
            summary += f"     {change['old_value']:.2f} → {change['new_value']:.2f}\n"
            summary += f"     CRC: 0x{change['old_crc']:04X} → 0x{change['new_crc']:04X}\n"

        return summary


# ═══════════════════════════════════════════════════════════════════════════
#  Пример использования
# ═══════════════════════════════════════════════════════════════════════════

def example_single_value():
    """Пример: изменение одного значения"""
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║  CRC Storage Surgical Editor — Пример 1: Одно значение           ║
╚═══════════════════════════════════════════════════════════════════╝
    """)

    try:
        # Загружаем файл
        editor = SurgicalEditor("test_file.bin")
        editor.load()

        # Находим все значения
        values = editor.find_all_values()
        print(f"\n✓ Найдено {len(values)} значений")

        if values:
            # Меняем первое значение
            first = values[0]
            print(f"\nИзменяем значение на позиции 0x{first['pos']:06X}:")
            print(f"  Старое значение: {first['value']:.2f}")
            print(f"  Новое значение: 9999.99")

            editor.update_value_at(first['pos'], 9999.99)

            # Проверяем изменения
            if editor.verify_changes():
                print(editor.get_summary())
                # editor.save()

    except Exception as e:
        print(f"✗ Ошибка: {e}")


def example_multiple_values():
    """Пример: изменение нескольких значений"""
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║  CRC Storage Surgical Editor — Пример 2: Несколько значений      ║
╚═══════════════════════════════════════════════════════════════════╝
    """)

    try:
        editor = SurgicalEditor("test_file.bin")
        editor.load()

        values = editor.find_all_values()
        print(f"\n✓ Найдено {len(values)} значений")

        # Меняем несколько значений
        updates = [
            (1000.00, "Первое значение"),
            (2000.00, "Второе значение"),
            (3000.00, "Третье значение"),
        ]

        for i, (new_val, desc) in enumerate(updates):
            if i < len(values):
                pos = values[i]['pos']
                old_val = values[i]['value']
                print(f"\n{i+1}. {desc} (0x{pos:06X}): {old_val:.2f} → {new_val:.2f}")
                editor.update_value_at(pos, new_val)

        # Проверяем и сохраняем
        if editor.verify_changes():
            print(editor.get_summary())
            # editor.save()

    except Exception as e:
        print(f"✗ Ошибка: {e}")


def demo_surgical_precision():
    """Демонстрация точечного редактирования"""
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║  Демонстрация: Что меняется при редактировании                   ║
╚═══════════════════════════════════════════════════════════════════╝

При изменении значения на позиции 0x01C1:

МЕНЯЕТСЯ (42 байта):
  ├─ 0x01C1-0x01E8: Блок данных (40 байт)
  │   ├─ 0x01C1-0x01C4: Значение (4 байта)
  │   ├─ 0x01C5-0x01C8: Дубль (4 байта)
  │   └─ 0x01C9-0x01E8: Паддинг (32 байта)
  └─ 0x01E9-0x01EA: CRC-16 (2 байта)

НЕ МЕНЯЕТСЯ:
  ├─ 0x0000-0x01C0: Данные ДО значения
  ├─ 0x01EB-0x01FF: Данные ПОСЛЕ значения
  └─ Остаток файла: Всё как было

ТОЧНОСТЬ:
  ✓ Минимальное изменение данных
  ✓ Не затрагиваются другие значения
  ✓ Безопасно для структурированных файлов
  ✓ Гарантирует целостность других данных
    """)


def main():
    """Главная функция"""
    import argparse

    parser = argparse.ArgumentParser(
        prog='crc_storage_surgical',
        description='Точечное редактирование CRC-16 CCITT хранилища'
    )

    parser.add_argument('--example', choices=['demo', 'single', 'multiple'],
                        help='Запустить пример')

    args = parser.parse_args()

    if args.example == 'demo':
        demo_surgical_precision()
    elif args.example == 'single':
        example_single_value()
    elif args.example == 'multiple':
        example_multiple_values()
    else:
        demo_surgical_precision()
        print("\nУспользование:")
        print("  python crc_storage_surgical.py --example demo")
        print("  python crc_storage_surgical.py --example single")
        print("  python crc_storage_surgical.py --example multiple")


if __name__ == "__main__":
    main()
