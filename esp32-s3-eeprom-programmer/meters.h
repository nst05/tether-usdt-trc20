// -*- coding: utf-8 -*-
// Полный цикл прошивки для каждого из 6 программаторов:
// считать дамп -> проверить -> пропатчить -> записать -> считать обратно -> сверить.
#ifndef METERS_H
#define METERS_H

#include <stdint.h>
#include <stdbool.h>
#include "eeprom_i2c.h"

struct MeterResult {
    bool ok;
    char message[192];   // UTF-8, для вывода в статус-строку
};

MeterResult meter_201_program(uint32_t int_part, eeprom_progress_fn cb);   // 24C16
MeterResult meter_c101_program(double reading, eeprom_progress_fn cb);     // 24C04
MeterResult meter_1F_program(double value, eeprom_progress_fn cb);         // AT24C1024
MeterResult meter_3F_program(double value, eeprom_progress_fn cb);         // AT24C1024
MeterResult meter_6803_program(double reading, eeprom_progress_fn cb);     // 24C04
MeterResult meter_200mt_program(double base_value, eeprom_progress_fn cb); // 24C16

#endif // METERS_H
