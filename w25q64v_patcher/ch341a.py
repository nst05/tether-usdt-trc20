#!/usr/bin/env python3
"""
Direct in-circuit writing to the W25Q64V through a CH341A USB programmer.

Backend: libusb via pyusb, using the exact CH341A stream protocol from
flashrom / ch341prog (VID 0x1A86, PID 0x5512). The CH341 transmits SPI
LSB-first, so every byte is bit-reversed on the way out and back.

Windows note: pyusb needs a libusb-compatible driver on the CH341A. Use Zadig
to install "WinUSB" on the "USB-EPP/I2C... CH341A" interface (this replaces the
vendor WCH driver used by the CH341A GUI — you can switch back with Zadig).
Then:  pip install pyusb   (and have libusb-1.0 present).

Safety: nothing here writes without an explicit call. write_changes() checks
the JEDEC ID matches the expected chip, writes ONLY the changed 4 KiB sectors
(erase + program), and verifies every sector by read-back.
"""

# ---- CH341A protocol constants (ch341prog/flashrom) ----------------------- #
VID, PID = 0x1A86, 0x5512
EP_OUT, EP_IN = 0x02, 0x82
PACKET_LEN = 0x20                       # 32-byte USB packets
CMD_SPI_STREAM = 0xA8
CMD_UIO_STREAM = 0xAB
UIO_STM_OUT = 0x80
UIO_STM_DIR = 0x40
UIO_STM_END = 0x20
TIMEOUT_MS = 1000

# ---- SPI NOR (Winbond 25-series) commands --------------------------------- #
CMD_RDID = 0x9F
CMD_WREN = 0x06
CMD_RDSR = 0x05
CMD_READ = 0x03
CMD_PP = 0x02                           # page program (<=256 B)
CMD_SE = 0x20                           # 4 KiB sector erase
SECTOR = 0x1000
PAGE = 0x100
W25Q64_ID = (0xEF, 0x40, 0x17)          # Winbond, mem type, 64 Mbit

_REV = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))   # bit-reversal table


class CH341Error(Exception):
    pass


class CH341A:
    """SPI-flash access over a CH341A. `transport` must expose write(bytes) and
    read(n)->bytes; UsbTransport is the real one, but any object works (used by
    the offline self-test)."""

    def __init__(self, transport):
        self.t = transport

    # --- low level ---------------------------------------------------------- #
    def _cs(self, enable):
        if enable:                       # D0=CS low, all UIO pins output
            pkt = bytes([CMD_UIO_STREAM, UIO_STM_OUT | 0x36,
                         UIO_STM_DIR | 0x3F, UIO_STM_END])
        else:                            # D0=CS high (idle)
            pkt = bytes([CMD_UIO_STREAM, UIO_STM_OUT | 0x37, UIO_STM_END])
        self.t.write(pkt)

    def _txn(self, data):
        """One CS-framed full-duplex SPI transaction; returns MISO, same len."""
        self._cs(True)
        try:
            out = bytearray()
            for i in range(0, len(data), PACKET_LEN - 1):
                chunk = data[i:i + PACKET_LEN - 1]
                self.t.write(bytes([CMD_SPI_STREAM]) + bytes(_REV[b] for b in chunk))
                got = bytes(self.t.read(len(chunk)))
                out += bytes(_REV[b] for b in got)
        finally:
            self._cs(False)
        return bytes(out)

    # --- flash primitives --------------------------------------------------- #
    def read_id(self):
        return tuple(self._txn(bytes([CMD_RDID, 0, 0, 0]))[1:4])

    def _wren(self):
        self._txn(bytes([CMD_WREN]))

    def _status(self):
        return self._txn(bytes([CMD_RDSR, 0]))[1]

    def _wait_ready(self, tries=100000):
        for _ in range(tries):
            if not (self._status() & 0x01):     # WIP bit clear
                return
        raise CH341Error("flash stayed busy (WIP) too long")

    @staticmethod
    def _addr(a):
        return bytes([(a >> 16) & 0xFF, (a >> 8) & 0xFF, a & 0xFF])

    def read(self, addr, length):
        return self._txn(bytes([CMD_READ]) + self._addr(addr) + bytes(length))[4:]

    def erase_sector(self, addr):
        self._wren()
        self._txn(bytes([CMD_SE]) + self._addr(addr))
        self._wait_ready()

    def program_page(self, addr, data):
        assert len(data) <= PAGE and (addr & (PAGE - 1)) + len(data) <= PAGE
        self._wren()
        self._txn(bytes([CMD_PP]) + self._addr(addr) + bytes(data))
        self._wait_ready()

    def write_sector(self, base, data, verify=True):
        """Erase + program one 4 KiB sector, then verify by read-back."""
        assert base % SECTOR == 0 and len(data) == SECTOR
        self.erase_sector(base)
        for off in range(0, SECTOR, PAGE):
            self.program_page(base + off, data[off:off + PAGE])
        if verify:
            back = self.read(base, SECTOR)
            if bytes(back) != bytes(data):
                bad = next(i for i in range(SECTOR) if back[i] != data[i])
                raise CH341Error(f"verify failed at {base + bad:#08x}: "
                                 f"wrote {data[bad]:02X}, read {back[bad]:02X}")


# --------------------------------------------------------------------------- #
# real USB transport (lazy pyusb import so the module loads without pyusb)
# --------------------------------------------------------------------------- #
class UsbTransport:
    def __init__(self):
        try:
            import usb.core
            import usb.util
        except ImportError as e:
            raise CH341Error(
                "pyusb не установлен. Установите: pip install pyusb "
                "(и libusb-1.0; на Windows — драйвер WinUSB на CH341A через Zadig)."
            ) from e
        self._util = usb.util
        dev = usb.core.find(idVendor=VID, idProduct=PID)
        if dev is None:
            raise CH341Error("CH341A не найден (VID 1A86:5512). Проверьте кабель "
                             "и драйвер (Windows: WinUSB через Zadig).")
        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except Exception:                    # not supported on all platforms
            pass
        dev.set_configuration()
        self.dev = dev

    def write(self, data):
        self.dev.write(EP_OUT, data, TIMEOUT_MS)

    def read(self, n):
        return self.dev.read(EP_IN, n, TIMEOUT_MS)

    def close(self):
        self._util.dispose_resources(self.dev)


# --------------------------------------------------------------------------- #
# high-level: flash only what changed
# --------------------------------------------------------------------------- #
def write_changes(loaded, patched, expected_id=W25Q64_ID,
                  transport=None, progress=None):
    """Flash only the changed 4 KiB sectors of `patched` (vs `loaded`).

    Returns the list of sector base addresses written. Raises CH341Error on a
    wrong chip or a verify mismatch. `progress(done, total, addr)` is optional.
    """
    import w25q64v_patcher as core
    rep = core.export_changes(loaded, patched, SECTOR)
    sectors = rep["sectors"]
    if not sectors:
        raise CH341Error("нет изменений для записи")

    own = transport is None
    if own:
        transport = UsbTransport()
    dev = CH341A(transport)
    try:
        got = dev.read_id()
        if expected_id and got != tuple(expected_id):
            raise CH341Error(
                f"чужой чип: JEDEC ID {':'.join(f'{b:02X}' for b in got)}, "
                f"ожидался {':'.join(f'{b:02X}' for b in expected_id)}. Запись отменена.")
        total = len(sectors)
        for i, (base, data) in enumerate(sectors.items(), 1):
            dev.write_sector(base, data, verify=True)
            if progress:
                progress(i, total, base)
        return list(sectors)
    finally:
        if own and hasattr(transport, "close"):
            transport.close()


def read_id(transport=None):
    """Open the programmer and return the JEDEC ID tuple (for a link test)."""
    own = transport is None
    if own:
        transport = UsbTransport()
    try:
        return CH341A(transport).read_id()
    finally:
        if own and hasattr(transport, "close"):
            transport.close()


if __name__ == "__main__":
    print("JEDEC ID:", ":".join(f"{b:02X}" for b in read_id()))
