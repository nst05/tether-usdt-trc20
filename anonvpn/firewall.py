"""
Kill-switch и защита от утечек DNS (Linux, iptables).

Kill-switch: пока он включён, исходящий трафик разрешён ТОЛЬКО внутрь туннеля
(интерфейс anon0), на loopback и до самого VPN-сервера (иначе туннель не
поднимется). Всё остальное блокируется. Если туннель падает — трафик не утекает
мимо VPN, а просто не идёт. Это главная защита от деанонимизации при обрыве.

DNS: бэкапим /etc/resolv.conf и прописываем выбранный резолвер. Так как при
redirect_gateway весь трафик (включая DNS) идёт через туннель, запросы к, скажем,
1.1.1.1 уходят зашифрованными внутрь VPN, а не к провайдеру.

Все изменения откатываются в cleanup() — это критично, иначе при выходе можно
остаться без интернета. Клиент вызывает cleanup() в обработчиках сигналов и через
atexit.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

log = logging.getLogger("anonvpn.firewall")

_CHAIN = "ANONVPN_KS"
_RESOLV = "/etc/resolv.conf"
_RESOLV_BACKUP = "/etc/resolv.conf.anonvpn.bak"


def _run(args: list[str], check: bool = True) -> int:
    log.debug("exec: %s", " ".join(args))
    res = subprocess.run(args, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} -> {res.stderr.strip()}")
    return res.returncode


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# --------------------------------------------------------------------------- #
# Kill-switch
# --------------------------------------------------------------------------- #
def build_killswitch_rules(server_ip: str, server_port: int,
                           tun_name: str) -> list[list[str]]:
    """
    Возвращает список iptables-команд для включения kill-switch.
    Вынесено отдельно, чтобы можно было протестировать без root.
    """
    return [
        # своя цепочка, чтобы не трогать чужие правила
        ["iptables", "-N", _CHAIN],
        # разрешаем loopback
        ["iptables", "-A", _CHAIN, "-o", "lo", "-j", "ACCEPT"],
        # разрешаем трафик внутрь туннеля
        ["iptables", "-A", _CHAIN, "-o", tun_name, "-j", "ACCEPT"],
        # разрешаем UDP до самого VPN-сервера (несущий туннель)
        ["iptables", "-A", _CHAIN, "-p", "udp", "-d", server_ip,
         "--dport", str(server_port), "-j", "ACCEPT"],
        # разрешаем ответы по уже установленным соединениям
        ["iptables", "-A", _CHAIN, "-m", "conntrack",
         "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT"],
        # всё остальное исходящее — блокируем
        ["iptables", "-A", _CHAIN, "-j", "DROP"],
        # подключаем цепочку к OUTPUT первой
        ["iptables", "-I", "OUTPUT", "1", "-j", _CHAIN],
    ]


def enable_killswitch(server_ip: str, server_port: int,
                      tun_name: str = "anon0") -> None:
    if not _have("iptables"):
        log.warning("iptables не найден — kill-switch пропущен")
        return
    # на всякий случай убираем прошлые остатки
    disable_killswitch(quiet=True)
    for cmd in build_killswitch_rules(server_ip, server_port, tun_name):
        _run(cmd)
    log.info("Kill-switch включён (исходящий трафик только через %s)", tun_name)


def disable_killswitch(quiet: bool = False) -> None:
    if not _have("iptables"):
        return
    # отцепляем от OUTPUT и удаляем цепочку
    _run(["iptables", "-D", "OUTPUT", "-j", _CHAIN], check=False)
    _run(["iptables", "-F", _CHAIN], check=False)
    _run(["iptables", "-X", _CHAIN], check=False)
    if not quiet:
        log.info("Kill-switch выключен")


# --------------------------------------------------------------------------- #
# DNS
# --------------------------------------------------------------------------- #
def set_dns(servers: list[str]) -> None:
    """Бэкапит resolv.conf и прописывает указанные DNS-серверы."""
    try:
        if os.path.exists(_RESOLV) and not os.path.exists(_RESOLV_BACKUP):
            shutil.copy2(_RESOLV, _RESOLV_BACKUP)
        content = "# AnonVPN: DNS через туннель\n"
        content += "".join(f"nameserver {s}\n" for s in servers)
        with open(_RESOLV, "w", encoding="utf-8") as f:
            f.write(content)
        log.info("DNS направлен в туннель: %s", ", ".join(servers))
    except OSError as exc:
        log.warning("Не удалось настроить DNS (%s)", exc)


def restore_dns() -> None:
    try:
        if os.path.exists(_RESOLV_BACKUP):
            shutil.copy2(_RESOLV_BACKUP, _RESOLV)
            os.remove(_RESOLV_BACKUP)
            log.info("DNS восстановлен")
    except OSError as exc:
        log.warning("Не удалось восстановить DNS (%s)", exc)


def cleanup() -> None:
    """Полный откат всех изменений (вызывать при выходе клиента)."""
    disable_killswitch()
    restore_dns()
