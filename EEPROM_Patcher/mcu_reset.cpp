#include <Arduino.h>
#include "mcu_reset.h"
#include "config.h"

// Логика как в рабочем FRAM-проекте:
// в покое линия RESET процессора в Hi-Z (родная схема прибора держит её),
// на время I2C-операции тянем LOW (процессор в сбросе, шина свободна),
// после — отпускаем, процессор стартует.

void mcuInitReset() {
    pinMode(PIN_MCU_RESET, INPUT);   // Hi-Z: не трогаем линию прибора
}

void mcuHoldReset() {
    pinMode(PIN_MCU_RESET, OUTPUT);
    digitalWrite(PIN_MCU_RESET, LOW);   // процессор в сброс
    delay(RESET_ASSERT_SETTLE_MS);
}

void mcuRelease() {
#if RESET_RELEASE_HIZ
    pinMode(PIN_MCU_RESET, INPUT);      // Hi-Z: родная подтяжка прибора поднимет линию
#else
    pinMode(PIN_MCU_RESET, OUTPUT);
    digitalWrite(PIN_MCU_RESET, HIGH);  // активно держим HIGH
#endif
    delay(RESET_IDLE_MS);               // даём процессору стартовать
}

// Повторный сброс процессора на 2 секунды ПОСЛЕ записи —
// чтобы счётчик перезапустился и перечитал обновлённую EEPROM.
// Закоротить RST процессора на GND на 2 секунды, потом отпустить.
// Счётчик перезапустится и перечитает обновлённую EEPROM.
void mcuResetAfterWrite() {
    pinMode(PIN_MCU_RESET, OUTPUT);
    digitalWrite(PIN_MCU_RESET, LOW);   // закорачиваем RST на GND
    delay(RESET_AFTER_WRITE_MS);        // держим 2 секунды
    mcuRelease();                       // отпускаем в соответствии с RESET_RELEASE_HIZ
}
