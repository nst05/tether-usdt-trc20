#pragma once
#include "eeprom.h"

// Поднимает BLE GATT-сервер с характеристиками AUTH/CMD/RESP/SETPIN.
// eePtr — указатель на уже инициализированный объект Eeprom.
void bleServerBegin(Eeprom *eePtr);
void bleServerLoop();   // вызывать из loop() — отложенный рестарт рекламы
