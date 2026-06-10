"""
Управление TUN-интерфейсом (Linux).

TUN — это виртуальный сетевой интерфейс уровня L3: ядро отдаёт нам «сырые»
IP-пакеты, которые маршрутизируются в этот интерфейс, и принимает обратно
пакеты, которые мы в него пишем. Это и есть точка, где VPN перехватывает
трафик приложений.

Требует root (CAP_NET_ADMIN). Работает на Linux без сторонних зависимостей.
"""

from __future__ import annotations

import fcntl
import os
import struct
import subprocess

# ioctl-константы Linux для TUN/TAP (см. <linux/if_tun.h>)
TUNSETIFF = 0x400454CA
IFF_TUN = 0x0001
IFF_NO_PI = 0x1000  # без 4-байтового protocol info — сразу чистый IP-пакет


class TunInterface:
    def __init__(self, name: str = "anon0", mtu: int = 1380):
        self.name = name
        self.mtu = mtu
        self.fd = os.open("/dev/net/tun", os.O_RDWR)
        flags = IFF_TUN | IFF_NO_PI
        ifr = struct.pack("16sH", name.encode("ascii"), flags)
        fcntl.ioctl(self.fd, TUNSETIFF, ifr)

    def configure(self, local_ip: str, peer_ip: str) -> None:
        """Назначает IP и поднимает интерфейс (point-to-point)."""
        self._ip("addr", "add", f"{local_ip}/32", "peer", peer_ip,
                 "dev", self.name)
        self._ip("link", "set", "dev", self.name, "mtu", str(self.mtu))
        self._ip("link", "set", "dev", self.name, "up")

    @staticmethod
    def _ip(*args: str) -> None:
        subprocess.run(["ip", *args], check=True)

    def read_packet(self) -> bytes:
        return os.read(self.fd, self.mtu + 64)

    def write_packet(self, data: bytes) -> None:
        os.write(self.fd, data)

    def fileno(self) -> int:
        return self.fd

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


def enable_ip_forwarding() -> None:
    """Включает форвардинг IPv4 на сервере (нужно для выхода трафика в интернет)."""
    with open("/proc/sys/net/ipv4/ip_forward", "w") as f:
        f.write("1")


def setup_nat(out_interface: str, vpn_subnet: str) -> None:
    """Настраивает MASQUERADE, чтобы трафик клиентов выходил наружу."""
    subprocess.run(
        ["iptables", "-t", "nat", "-A", "POSTROUTING",
         "-s", vpn_subnet, "-o", out_interface, "-j", "MASQUERADE"],
        check=True,
    )
    subprocess.run(
        ["iptables", "-A", "FORWARD", "-i", out_interface,
         "-o", "anon0", "-m", "state",
         "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"],
        check=False,
    )
    subprocess.run(
        ["iptables", "-A", "FORWARD", "-s", vpn_subnet, "-j", "ACCEPT"],
        check=False,
    )
