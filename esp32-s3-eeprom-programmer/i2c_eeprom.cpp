#include "i2c_eeprom.h"

namespace {
const EepromProfile PROFILES[] = {
    {"24C16", 2048, 16},
    {"24C04", 512, 16},
    {"AT24C1024", 131072, 32},
};
}

const EepromProfile& eepromProfile(EepromType type) {
    return PROFILES[static_cast<uint8_t>(type)];
}

I2cEeprom::I2cEeprom(TwoWire& wire) : wire_(wire) {}

bool I2cEeprom::begin(int sda, int scl, uint32_t frequency) {
    lastError_ = "";
    if (!wire_.begin(sda, scl, frequency)) {
        fail("I2C initialization failed");
        return false;
    }
    wire_.setTimeOut(50);
    return true;
}

bool I2cEeprom::mapAddress(EepromType type, uint32_t address,
                           uint8_t& device, uint16_t& memory, uint8_t& addrBytes,
                           uint32_t& blockRemaining) const {
    if (address >= eepromProfile(type).capacity) return false;

    switch (type) {
        case EepromType::C24C16:
            device = 0x50 | ((address >> 8) & 0x07);
            memory = address & 0xFF;
            addrBytes = 1;
            blockRemaining = 0x100 - memory;
            return true;

        case EepromType::C24C04:
            device = 0x50 | ((address >> 8) & 0x01);
            memory = address & 0xFF;
            addrBytes = 1;
            blockRemaining = 0x100 - memory;
            return true;

        case EepromType::AT24C1024:
            // A16 is part of the slave address: 0x50 for lower 64 KiB,
            // 0x54 for upper 64 KiB (A2=1 convention used by 24C1024).
            device = 0x50 | ((address >> 14) & 0x04);
            memory = address & 0xFFFF;
            addrBytes = 2;
            blockRemaining = 0x10000UL - memory;
            return true;
    }
    return false;
}

bool I2cEeprom::waitReady(uint8_t device, uint32_t timeoutMs) {
    const uint32_t started = millis();
    do {
        wire_.beginTransmission(device);
        if (wire_.endTransmission() == 0) return true;
        delay(1);
    } while (millis() - started < timeoutMs);
    fail("EEPROM did not acknowledge after write");
    return false;
}

bool I2cEeprom::probe(EepromType type) {
    uint8_t dev, ab;
    uint16_t mem;
    uint32_t remain;
    if (!mapAddress(type, 0, dev, mem, ab, remain)) return false;
    wire_.beginTransmission(dev);
    const uint8_t result = wire_.endTransmission();
    if (result != 0) {
        fail("No EEPROM response at I2C address 0x" + String(dev, HEX));
        return false;
    }
    return true;
}

bool I2cEeprom::read(EepromType type, uint32_t address, uint8_t* data, size_t length) {
    lastError_ = "";
    if (!data || address + length > eepromProfile(type).capacity) {
        fail("Read outside EEPROM capacity");
        return false;
    }

    size_t done = 0;
    while (done < length) {
        uint8_t dev, addrBytes;
        uint16_t mem;
        uint32_t blockRemaining;
        if (!mapAddress(type, address + done, dev, mem, addrBytes, blockRemaining)) {
            fail("Invalid EEPROM address");
            return false;
        }

        size_t chunk = (length - done < blockRemaining) ? (length - done) : blockRemaining;
        chunk = (chunk < 32) ? chunk : 32; // Arduino Wire buffer

        wire_.beginTransmission(dev);
        if (addrBytes == 2) wire_.write(uint8_t(mem >> 8));
        wire_.write(uint8_t(mem & 0xFF));
        if (wire_.endTransmission(false) != 0) {
            fail("I2C address phase failed at 0x" + String(address + done, HEX));
            return false;
        }

        const size_t received = wire_.requestFrom(int(dev), int(chunk), int(true));
        if (received != chunk) {
            fail("Short I2C read at 0x" + String(address + done, HEX));
            return false;
        }
        for (size_t i = 0; i < chunk; ++i) data[done + i] = wire_.read();
        done += chunk;
    }
    return true;
}

bool I2cEeprom::write(EepromType type, uint32_t address, const uint8_t* data, size_t length) {
    lastError_ = "";
    if (!data || address + length > eepromProfile(type).capacity) {
        fail("Write outside EEPROM capacity");
        return false;
    }

    const uint16_t page = eepromProfile(type).pageSize;
    size_t done = 0;
    while (done < length) {
        uint8_t dev, addrBytes;
        uint16_t mem;
        uint32_t blockRemaining;
        if (!mapAddress(type, address + done, dev, mem, addrBytes, blockRemaining)) {
            fail("Invalid EEPROM address");
            return false;
        }

        const uint32_t absolute = address + done;
        const uint32_t pageRemaining = page - (absolute % page);
        size_t chunk = (length - done < pageRemaining) ? (length - done) : pageRemaining;
        chunk = (chunk < blockRemaining) ? chunk : blockRemaining;
        chunk = (chunk < size_t(32 - addrBytes)) ? chunk : size_t(32 - addrBytes);

        wire_.beginTransmission(dev);
        if (addrBytes == 2) wire_.write(uint8_t(mem >> 8));
        wire_.write(uint8_t(mem & 0xFF));
        wire_.write(data + done, chunk);
        if (wire_.endTransmission(true) != 0) {
            fail("I2C write failed at 0x" + String(absolute, HEX));
            return false;
        }
        if (!waitReady(dev)) return false;
        done += chunk;
    }
    return true;
}

bool I2cEeprom::verify(EepromType type, uint32_t address,
                       const uint8_t* data, size_t length) {
    uint8_t buffer[32];
    size_t done = 0;
    while (done < length) {
        const size_t chunk = (sizeof(buffer) < length - done) ? sizeof(buffer) : (length - done);
        if (!read(type, address + done, buffer, chunk)) return false;
        if (memcmp(buffer, data + done, chunk) != 0) {
            fail("Verification mismatch at 0x" + String(address + done, HEX));
            return false;
        }
        done += chunk;
    }
    return true;
}
