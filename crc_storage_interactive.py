#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CRC Storage Interactive — интерактивное редактирование
Полный цикл: Загрузка → Просмотр → Выбор → Редактирование → Сохранение
"""

import struct
import sys
from pathlib import Path

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


class InteractiveEditor:
    """Интерактивный редактор"""

    def __init__(self):
        self.filepath = None
        self.original_data = None
        self.modified_data = None
        self.values = []
        self.selected_index = -1
        self.changes = []

    def print_header(self):
        """Печатает заголовок"""
        print("""
╔════════════════════════════════════════════════════════════════════╗
║        CRC Storage Interactive Editor                              ║
║   Загрузка → Просмотр → Выбор → Редактирование → Сохранение       ║
╚════════════════════════════════════════════════════════════════════╝
        """)

    def step1_load_file(self):
        """Шаг 1: Загрузка файла"""
        print("\n" + "="*70)
        print("ШАГ 1: ЗАГРУЗКА ФАЙЛА")
        print("="*70)

        while True:
            filepath = input("\nВведите путь к файлу (или 'q' для выхода): ").strip()

            if filepath.lower() == 'q':
                return False

            if not filepath:
                print("✗ Путь не может быть пуст")
                continue

            try:
                path = Path(filepath)
                if not path.exists():
                    print(f"✗ Файл не найден: {filepath}")
                    continue

                with open(path, 'rb') as f:
                    self.original_data = f.read()

                self.modified_data = bytearray(self.original_data)
                self.filepath = path
                self.changes = []

                print(f"\n✓ Файл загружен: {self.filepath}")
                print(f"  Размер: {len(self.original_data)} байт")
                return True

            except Exception as e:
                print(f"✗ Ошибка: {e}")

    def step2_scan_values(self):
        """Шаг 2: Сканирование значений"""
        print("\n" + "="*70)
        print("ШАГ 2: ПОИСК ЗНАЧЕНИЙ В ФАЙЛЕ")
        print("="*70)

        self.values = []
        data = bytes(self.original_data)

        print("\nСканирование...")

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
                            self.values.append({
                                'idx': len(self.values),
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

        print(f"\n✓ Найдено {len(self.values)} значений\n")
        return len(self.values) > 0

    def step3_view_values(self):
        """Шаг 3: Просмотр значений"""
        print("\n" + "="*70)
        print("ШАГ 3: ПРОСМОТР НАЙДЕННЫХ ЗНАЧЕНИЙ")
        print("="*70)

        if not self.values:
            print("\n✗ Значения не найдены")
            return False

        print(f"\n{'№':<3} {'Позиция':<12} {'Значение':<15} {'CRC-16':<10} {'Статус'}")
        print("-" * 60)

        for item in self.values:
            status = "✓ OK" if item['valid'] else "✗ ERROR"
            hex_val = int(item['value'] * SCALE)
            print(f"{item['idx']:<3} 0x{item['pos']:06X}    {item['value']:13.2f}  "
                  f"0x{item['crc']:04X}    {status}")

        print()
        return True

    def step4_select_value(self):
        """Шаг 4: Выбор значения"""
        print("\n" + "="*70)
        print("ШАГ 4: ВЫБОР ЗНАЧЕНИЯ ДЛЯ РЕДАКТИРОВАНИЯ")
        print("="*70)

        while True:
            try:
                idx = input("\nВведите номер значения для редактирования (или 'q' для выхода): ").strip()

                if idx.lower() == 'q':
                    return False

                idx = int(idx)

                if 0 <= idx < len(self.values):
                    self.selected_index = idx
                    item = self.values[idx]
                    print(f"\n✓ Выбран элемент #{idx}")
                    print(f"  Позиция:      0x{item['pos']:06X}")
                    print(f"  Текущее значение: {item['value']:.2f}")
                    print(f"  HEX:          0x{int(item['value'] * SCALE):08X}")
                    print(f"  CRC-16:       0x{item['crc']:04X}")
                    return True
                else:
                    print(f"✗ Номер должен быть от 0 до {len(self.values)-1}")

            except ValueError:
                print("✗ Введите корректный номер")

    def step5_edit_value(self):
        """Шаг 5: Редактирование значения"""
        print("\n" + "="*70)
        print("ШАГ 5: ВВОД НОВОГО ЗНАЧЕНИЯ")
        print("="*70)

        item = self.values[self.selected_index]

        while True:
            try:
                new_val = input(f"\nВведите новое значение (текущее: {item['value']:.2f}): ").strip()

                if new_val.lower() == 'q':
                    return False

                new_value = float(new_val.replace(",", "."))

                # Вычисляем новый CRC
                val_bytes = encode_value(new_value)
                block = val_bytes + val_bytes + b'\x00' * 32
                new_crc = crc16_ccitt(block)

                print(f"\n📝 Проверка изменения:")
                print(f"  Старое значение: {item['value']:.2f} (CRC: 0x{item['crc']:04X})")
                print(f"  Новое значение:  {new_value:.2f} (CRC: 0x{new_crc:04X})")
                print(f"  Старый HEX:      0x{int(item['value'] * SCALE):08X}")
                print(f"  Новый HEX:       0x{int(new_value * SCALE):08X}")

                confirm = input("\nПодтвердить изменение? (y/n): ").strip().lower()

                if confirm == 'y':
                    # Применяем изменение
                    pos = item['pos']
                    self.modified_data[pos:pos+BLOCK_SIZE] = block
                    self.modified_data[pos+BLOCK_SIZE:pos+BLOCK_SIZE+CRC_SIZE] = struct.pack('>H', new_crc)

                    # Сохраняем в логе
                    self.changes.append({
                        'idx': self.selected_index,
                        'pos': pos,
                        'old_value': item['value'],
                        'new_value': new_value,
                        'old_crc': item['crc'],
                        'new_crc': new_crc
                    })

                    # Обновляем элемент
                    item['value'] = new_value
                    item['crc'] = new_crc

                    print(f"\n✓ Значение изменено!")
                    return True
                else:
                    print("✗ Отменено")
                    return False

            except ValueError:
                print("✗ Введите корректное число")

    def step6_save_file(self):
        """Шаг 6: Сохранение файла"""
        print("\n" + "="*70)
        print("ШАГ 6: СОХРАНЕНИЕ ФАЙЛА")
        print("="*70)

        if not self.changes:
            print("\n✗ Нет изменений для сохранения")
            return False

        print(f"\n📋 Сводка изменений:")
        print(f"   Количество изменений: {len(self.changes)}")
        print(f"   Файл: {self.filepath}")

        for change in self.changes:
            print(f"\n   • Позиция 0x{change['pos']:06X}:")
            print(f"     {change['old_value']:.2f} → {change['new_value']:.2f}")
            print(f"     CRC: 0x{change['old_crc']:04X} → 0x{change['new_crc']:04X}")

        confirm = input("\nСохранить изменения? (y/n): ").strip().lower()

        if confirm != 'y':
            print("✗ Отменено")
            return False

        try:
            # Создаём резервную копию
            backup = self.filepath.with_suffix('.bak')
            self.filepath.rename(backup)
            print(f"\n✓ Резервная копия создана: {backup}")

            # Сохраняем новый файл
            with open(self.filepath, 'wb') as f:
                f.write(self.modified_data)

            print(f"✓ Файл сохранён: {self.filepath}")
            print(f"\n✓ ВСЕ ИЗМЕНЕНИЯ СОХРАНЕНЫ!")
            return True

        except Exception as e:
            print(f"✗ Ошибка при сохранении: {e}")
            if backup.exists():
                backup.rename(self.filepath)
                print("  Резервная копия восстановлена")
            return False

    def run(self):
        """Запускает интерактивный сеанс"""
        self.print_header()

        # Шаг 1: Загрузка
        if not self.step1_load_file():
            return

        # Шаг 2: Сканирование
        if not self.step2_scan_values():
            print("✗ Не удалось найти значения в файле")
            return

        # Шаг 3: Просмотр
        if not self.step3_view_values():
            return

        # Цикл редактирования
        while True:
            # Шаг 4: Выбор
            if not self.step4_select_value():
                break

            # Шаг 5: Редактирование
            if not self.step5_edit_value():
                continue

            # Спрашиваем, продолжить редактирование
            cont = input("\n\nОтредактировать ещё одно значение? (y/n): ").strip().lower()
            if cont != 'y':
                break

        # Шаг 6: Сохранение
        if self.changes:
            self.step6_save_file()

        print("\n✓ Спасибо за использование CRC Storage Interactive!\n")


def main():
    editor = InteractiveEditor()
    editor.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Прервано пользователем")
        sys.exit(1)
