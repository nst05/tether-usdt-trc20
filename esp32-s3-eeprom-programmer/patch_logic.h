#pragma once
#include <Arduino.h>

uint16_t crc16Ibm(const uint8_t* data, size_t len);
uint8_t crc8B5(const uint8_t* data, size_t len);
uint8_t crcLowCcittFalse3(const uint8_t data[3]);

bool patch201(uint8_t* image, size_t size, uint32_t integerPart, uint8_t fraction);
bool patchC101(uint8_t* image, size_t size, double reading);
bool patch1F(uint8_t* image, size_t size, double reading);
bool patch3F(uint8_t* image, size_t size, double reading);
bool patchCE6803(uint8_t* image, size_t size, double reading);
bool make200MT(double integerInput, uint8_t fraction, uint8_t out[4], double& actualValue);
