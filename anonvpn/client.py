"""
Клиент AnonVPN.

Делает рукопожатие с сервером, поднимает TUN, заворачивает в туннель весь
трафик (или указанные маршруты), шифрует + обфусцирует и шлёт по UDP.

Запуск (нужен root):
    sudo python -m anonvpn.client --config client.conf
"""

from __future__ import annotations

import argparse
import base64
import logging
import select
import socket
import sys
import time

from . import obfs, protocol, tun

log = logging.getLogger("anonvpn.client")

KEEPALIVE_INTERVAL = 20  # сек, чтобы держать NAT-маппинг открытым


def run_client(cfg: dict) -> None:
    static_priv = base64.b64decode(cfg["private_key"])
    server_pub = base64.b64decode(cfg["server_public_key"])
    server_addr = (cfg["server_host"], cfg["server_port"])

    obfuscator = obfs.Obfuscator(cfg["obfs_password"])
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)

    # --- Рукопожатие (с повторами) ---
    session = None
    handshake = protocol.ClientHandshake(static_priv, server_pub)
    for attempt in range(5):
        sock.sendto(obfuscator.wrap(handshake.build_init()), server_addr)
        try:
            raw, _ = sock.recvfrom(65535)
        except socket.timeout:
            log.warning("Нет ответа от сервера, попытка %d", attempt + 1)
            handshake = protocol.ClientHandshake(static_priv, server_pub)
            continue
        payload = obfuscator.unwrap(raw)
        if payload is None:
            continue
        try:
            session = handshake.consume_response(payload)
            break
        except protocol.HandshakeError as exc:
            log.error("Рукопожатие не удалось: %s", exc)
            time.sleep(1)
            handshake = protocol.ClientHandshake(static_priv, server_pub)
    if session is None:
        raise SystemExit("Не удалось установить сессию с сервером")
    log.info("Сессия установлена с %s", server_addr)

    # --- Поднимаем TUN ---
    tun_if = tun.TunInterface(name=cfg.get("tun_name", "anon0"),
                              mtu=cfg.get("mtu", 1380))
    tun_if.configure(cfg["client_vpn_ip"], cfg["server_vpn_ip"])
    _setup_routes(cfg, server_addr[0])

    sock.settimeout(None)
    last_keepalive = time.time()

    while True:
        readable, _, _ = select.select([sock, tun_if.fileno()], [], [], 5)

        for src in readable:
            if src is sock:
                try:
                    raw, _ = sock.recvfrom(65535)
                except OSError:
                    continue
                payload = obfuscator.unwrap(raw)
                if payload is None:
                    continue
                result = session.decrypt_packet(payload)
                if result is None:
                    continue
                mtype, ip_packet = result
                if mtype == protocol.MSG_DATA and ip_packet:
                    tun_if.write_packet(ip_packet)
            else:
                packet = tun_if.read_packet()
                if not packet:
                    continue
                enc = session.encrypt_packet(packet)
                sock.sendto(obfuscator.wrap(enc), server_addr)

        now = time.time()
        if now - last_keepalive > KEEPALIVE_INTERVAL:
            ka = session.encrypt_packet(b"", msg_type=protocol.MSG_KEEPALIVE)
            sock.sendto(obfuscator.wrap(ka), server_addr)
            last_keepalive = now


def _setup_routes(cfg: dict, server_ip: str) -> None:
    """
    Если redirect_gateway=True — заворачиваем ВЕСЬ трафик в туннель,
    кроме маршрута до самого VPN-сервера (иначе разорвём соединение).
    """
    import subprocess

    if not cfg.get("redirect_gateway"):
        return
    # Узнаём текущий шлюз по умолчанию.
    res = subprocess.run(["ip", "route", "show", "default"],
                         capture_output=True, text=True)
    parts = res.stdout.split()
    gw = parts[2] if len(parts) > 2 else None
    if gw:
        # Трафик до VPN-сервера идёт мимо туннеля.
        subprocess.run(["ip", "route", "add", f"{server_ip}/32",
                        "via", gw], check=False)
    # Перекрываем 0.0.0.0/0 двумя /1-маршрутами через VPN.
    peer = cfg["server_vpn_ip"]
    subprocess.run(["ip", "route", "add", "0.0.0.0/1", "via", peer],
                   check=False)
    subprocess.run(["ip", "route", "add", "128.0.0.0/1", "via", peer],
                   check=False)
    log.info("Весь трафик направлен в туннель (redirect_gateway)")


def load_config(path: str) -> dict:
    import json
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AnonVPN client")
    parser.add_argument("--config", required=True)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_client(load_config(args.config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
