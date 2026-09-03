#!/bin/bash
# PIC16LF1934 Firmware Reader Bash Script

PIC_MODEL="PIC16LF1934"
OUTPUT_HEX="${PIC_MODEL}_firmware.hex"
OUTPUT_BIN="${PIC_MODEL}_firmware.bin"

echo "=========================================="
echo "PIC16LF1934 Firmware Reader"
echo "=========================================="

# Проверка pk2cmd
if ! command -v pk2cmd &> /dev/null; then
    echo "[✗] pk2cmd не найден!"
    echo "    Установите MPLAB X IDE или pk2cmd"
    exit 1
fi

echo "[✓] pk2cmd найден"

# Проверка подключения
echo ""
echo "[*] Проверка подключения..."
pk2cmd -P $PIC_MODEL -I

if [ $? -ne 0 ]; then
    echo "[✗] Микроконтроллер не подключен!"
    exit 1
fi

echo "[✓] Микроконтроллер подключен"

# Меню
echo ""
echo "=========================================="
echo "Выберите операцию:"
echo "=========================================="
echo "1) Считать прошивку (попытка)"
echo "2) Считать конфигурацию"
echo "3) Стирать микроконтроллер (сотрет защиту)"
echo "4) Проверить статус защиты"
echo "0) Выход"
echo ""

read -p "Введите номер операции: " choice

case $choice in
    1)
        echo "[*] Считывание прошивки..."
        pk2cmd -P $PIC_MODEL -R -O $OUTPUT_HEX

        if [ $? -eq 0 ] && [ -f "$OUTPUT_HEX" ]; then
            SIZE=$(wc -c < "$OUTPUT_HEX")
            echo "[✓] Прошивка успешно считана!"
            echo "    Файл: $OUTPUT_HEX"
            echo "    Размер: $SIZE байт"

            # Конвертирование в бинарник (если нужно)
            echo ""
            read -p "Конвертировать в бинарный формат? (y/n): " conv
            if [ "$conv" = "y" ]; then
                # Нужен srec_cat или objcopy
                if command -v objcopy &> /dev/null; then
                    objcopy -I ihex -O binary $OUTPUT_HEX $OUTPUT_BIN
                    echo "[✓] Бинарник сохранен: $OUTPUT_BIN"
                else
                    echo "[!] objcopy не найден, пропускаем конвертацию"
                fi
            fi
        else
            echo "[✗] Ошибка при чтении (вероятно, установлена защита)"
        fi
        ;;

    2)
        echo "[*] Считывание конфигурации..."
        pk2cmd -P $PIC_MODEL -RC
        ;;

    3)
        echo "[!] ВНИМАНИЕ: Стирание сотрет ВСЕ данные!"
        read -p "Продолжить? (yes/no): " confirm

        if [ "$confirm" = "yes" ]; then
            echo "[*] Стирание микроконтроллера..."
            pk2cmd -P $PIC_MODEL -E

            if [ $? -eq 0 ]; then
                echo "[✓] Микроконтроллер успешно стран"
                echo "[!] Защита сотрена, теперь можно перепрограммировать"
            else
                echo "[✗] Ошибка при стирании"
            fi
        else
            echo "[*] Операция отменена"
        fi
        ;;

    4)
        echo "[*] Проверка статуса защиты..."
        echo ""
        echo "Статус защиты можно увидеть в:MPLAB X IDE"
        echo "  1. Откройте MPLAB X IDE"
        echo "  2. Programming > Device > Read"
        echo "  3. Посмотрите Configuration bits"
        echo "     CODE_PROTECT = OFF  -> без защиты"
        echo "     CODE_PROTECT = ON   -> с защитой (чтение невозможно)"
        ;;

    0)
        echo "Выход"
        exit 0
        ;;

    *)
        echo "[✗] Неверный выбор"
        exit 1
        ;;
esac
