#pragma once
// Управление сбросом процессора счётчика на время I2C-операций.
void mcuInitReset();    // вызвать в setup — увести линию в Hi-Z
void mcuHoldReset();    // притянуть RESET процессора (LOW) на время операции
void mcuRelease();      // отпустить (Hi-Z или HIGH) — процессор стартует
void mcuResetAfterWrite();
