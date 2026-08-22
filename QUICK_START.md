# 🚀 Quick Start — Быстрый старт

## 1️⃣ Графический интерфейс (самый простой)

```bash
python crc_storage_gui.py
```

1. Нажмите **Обзор** и выберите файл `.bin`
2. В таблице видны все значения
3. Выберите значение в таблице
4. Введите новое значение в поле внизу
5. Нажмите **Обновить значение**
6. Нажмите **Сохранить файл**

**Результат:** Файл обновлён, резервная копия создана.

---

## 2️⃣ Командная строка (быстрые операции)

### Просмотр всех значений
```bash
python crc_storage_cli.py list file.bin
```

**Вывод:**
```
📄 Файл: file.bin
   Размер: 2048 байт (2.0 КБ)

Позиция      Значение    CRC-16   Статус
0x0001C1     9442.36     0xAC55   ✓ OK
0x000201     9440.38     0x8748   ✓ OK

Всего: 2 значений
```

### Изменить одно значение
```bash
python crc_storage_cli.py set file.bin 0x01C1 9999.99
```

**Вывод:**
```
✓ Позиция 0x0001C1:
  Старое значение: 9442.36
  Новое значение: 9999.99
  Новый CRC-16: 0xFABC
✓ Файл сохранён
  Резервная копия: file.bak
```

---

## 3️⃣ Python скрипт (программно)

```python
from crc_storage_cli import StorageFile, make_block, crc16_ccitt
import struct

# Загружаем файл
storage = StorageFile('data.bin')
storage.load()

# Просматриваем значения
for item in storage.values:
    print(f"0x{item['pos']:06X}: {item['value']:.2f} (CRC: 0x{item['crc']:04X})")

# Меняем значение
storage.write_value(0x01C1, 1234.56)

# Сохраняем
storage.save()
```

---

## 4️⃣ Вычисление CRC вручную

### Для значения 9442.36:

1. **Умножаем на 100:**
   - 9442.36 × 100 = 944236

2. **Переводим в HEX:**
   - 944236 = 0x000E686C

3. **В big-endian (старший байт первым):**
   - 00 0E 68 6C

4. **Создаём блок (40 байт):**
   - Значение: `00 0E 68 6C`
   - Дубль: `00 0E 68 6C`
   - Паддинг: 32 байта нулей

5. **Вычисляем CRC-16 CCITT:**
   ```python
   def crc16_ccitt(data):
       crc = 0xFFFF
       for byte in data:
           crc ^= byte << 8
           for _ in range(8):
               crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
               crc &= 0xFFFF
       return crc
   
   block = b'\x00\x0e\x68\x6c' + b'\x00\x0e\x68\x6c' + b'\x00' * 32
   crc = crc16_ccitt(block)
   print(f"CRC: 0x{crc:04X}")  # 0xAC55
   ```

---

## 5️⃣ Проверка алгоритма

Запустите тесты:

```bash
python test_crc_storage.py
```

**Ожидаемый результат:**
```
✓ CRC вычисление
✓ Кодирование/декодирование
✓ Структура блока
✓ Создание файла
✓ Граничные значения

✓ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!
```

---

## 📋 Таблица команд

| Задача | Команда |
|--------|---------|
| **Открыть GUI** | `python crc_storage_gui.py` |
| **Показать значения** | `python crc_storage_cli.py list file.bin` |
| **Прочитать значение** | `python crc_storage_cli.py get file.bin 0x01C1` |
| **Изменить значение** | `python crc_storage_cli.py set file.bin 0x01C1 1234.56` |
| **Справка** | `python crc_storage_cli.py info` |
| **Запустить тесты** | `python test_crc_storage.py` |
| **Демо редактирования** | `python crc_storage_surgical.py --example demo` |

---

## ⚙️ Установка

```bash
# Установить PyQt5 (для GUI)
pip install PyQt5

# Сборка в exe (Windows)
pip install pyinstaller
pyinstaller --onefile --windowed crc_storage_gui.py
```

---

## 🔍 Примеры значений и их CRC

```
Значение   Целое число  HEX         CRC-16
9442.36    944236      0x000E686C  0xAC55
9440.38    944038      0x000E67A6  0x8748
12.34      1234        0x000004D2  0xC7D9
50.00      5000        0x00001388  0x3798
99.99      9999        0x0000270F  0x98F2
100.00     10000       0x00002710  0xF17A
1234.56    123456      0x0001E240  0x8E2D
```

---

## ⚠️ Важно

✓ **Точечные изменения** — меняются ТОЛЬКО 42 байта (40 блок + 2 CRC)
✓ **Автоматическое резервирование** — создаётся файл.bak перед сохранением
✓ **Валидация CRC** — все значения проверяются при загрузке
✓ **Big-Endian** — старший байт первым
✓ **Fixed-Point** — значение × 100

---

## 🐛 Если что-то не работает

1. Проверьте установку PyQt5:
   ```bash
   python -c "from PyQt5 import QtWidgets; print('OK')"
   ```

2. Запустите тесты:
   ```bash
   python test_crc_storage.py
   ```

3. Используйте CLI для отладки:
   ```bash
   python crc_storage_cli.py info
   python crc_storage_cli.py list file.bin
   ```

---

## 📚 Дополнительно

- **CRC_STORAGE_README.md** — подробная документация
- **PROGRAMS_OVERVIEW.md** — описание каждой программы
- **crc_storage_surgical.py** — демонстрация точечного редактирования
- **test_crc_storage.py** — набор тестов

---

**Готово к использованию!** 🎉
