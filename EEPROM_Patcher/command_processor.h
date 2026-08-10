#pragma once
#include <ArduinoJson.h>
#include "eeprom.h"

// Обработка команд от приложения (BLE) для EEPROM-патчера.
// Команды:
//   write  — записать показание (value) + верификация обратным чтением
//   read   — прочитать текущее показание с чипа
//   status — тип чипа/режим
//   ping   — проверка связи
void processCommand(Eeprom &ee, const JsonDocument &in, JsonDocument &out);
