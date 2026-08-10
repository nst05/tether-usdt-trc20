#include <Arduino.h>
#include "config.h"
#include "eeprom.h"
#include "ble_server.h"
#include "mcu_reset.h"

Eeprom ee;

void setup() {
    // Первым делом — увести RESET процессора счётчика в Hi-Z (не мешаем прибору)
    mcuInitReset();

    Serial.begin(115200);
    delay(300);
    Serial.println("\n[EEPROM Patcher BLE] старт");

    // СНАЧАЛА BLE — чтобы плата гарантированно появилась в эфире,
    // даже если I2C-чип не подключён (иначе Wire мог бы подвесить старт).
    bleServerBegin(&ee);

    // Потом I2C — если чип не отвечает, это уже не помешает BLE.
    ee.begin();
    bool ok = ee.probe();
    Serial.printf("[EEPROM] чип %s\n", ok ? "отвечает" : "НЕ отвечает (проверь I2C/питание)");
}

void loop() {
    bleServerLoop();   // отложенный рестарт BLE-рекламы после дисконнекта
    delay(20);
}
