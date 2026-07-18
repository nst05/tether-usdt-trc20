#pragma once
#include <lvgl.h>
#include "i2c_eeprom.h"

// Показать экран входа по PIN; после верного PIN строится интерфейс программаторов.
void programmer_ui_start(I2cEeprom& eeprom);
