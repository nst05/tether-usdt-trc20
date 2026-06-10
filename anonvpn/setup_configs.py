"""
Помощник: генерирует готовую пару конфигов сервер/клиент со свежими ключами.

    python -m anonvpn.setup_configs --server-host vpn.example.com \\
        --out-interface eth0 --obfs-pass "длинный-секретный-пароль"

Создаёт server.conf и client.conf в текущем каталоге.
ВНИМАНИЕ: server.conf содержит приватный ключ сервера, client.conf — клиента.
Храните их в секрете (chmod 600).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys

from . import crypto


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Генератор конфигов AnonVPN")
    p.add_argument("--server-host", required=True,
                   help="публичный адрес/домен сервера")
    p.add_argument("--server-port", type=int, default=51820)
    p.add_argument("--out-interface", default="eth0",
                   help="внешний интерфейс сервера для NAT")
    p.add_argument("--obfs-pass", required=True,
                   help="общий пароль обфускации (одинаковый у сервера и клиента)")
    p.add_argument("--server-vpn-ip", default="10.9.0.1")
    p.add_argument("--client-vpn-ip", default="10.9.0.2")
    p.add_argument("--subnet", default="10.9.0.0/24")
    p.add_argument("--redirect-all", action="store_true",
                   help="заворачивать весь трафик клиента в туннель")
    args = p.parse_args(argv)

    s_priv, s_pub = crypto.generate_keypair()
    c_priv, c_pub = crypto.generate_keypair()

    server_conf = {
        "private_key": b64(s_priv),
        "allowed_clients": [b64(c_pub)],
        "ip_assignments": {b64(c_pub): args.client_vpn_ip},
        "listen_addr": "0.0.0.0",
        "listen_port": args.server_port,
        "server_vpn_ip": args.server_vpn_ip,
        "vpn_subnet": args.subnet,
        "out_interface": args.out_interface,
        "obfs_password": args.obfs_pass,
        "tun_name": "anon0",
        "mtu": 1380,
    }

    client_conf = {
        "private_key": b64(c_priv),
        "server_public_key": b64(s_pub),
        "server_host": args.server_host,
        "server_port": args.server_port,
        "client_vpn_ip": args.client_vpn_ip,
        "server_vpn_ip": args.server_vpn_ip,
        "obfs_password": args.obfs_pass,
        "tun_name": "anon0",
        "mtu": 1380,
        "redirect_gateway": bool(args.redirect_all),
    }

    with open("server.conf", "w", encoding="utf-8") as f:
        json.dump(server_conf, f, indent=2, ensure_ascii=False)
    os.chmod("server.conf", 0o600)
    with open("client.conf", "w", encoding="utf-8") as f:
        json.dump(client_conf, f, indent=2, ensure_ascii=False)
    os.chmod("client.conf", 0o600)

    print("Создано: server.conf (для сервера) и client.conf (для клиента)")
    print(f"  server public key: {b64(s_pub)}")
    print(f"  client public key: {b64(c_pub)}")
    print("Скопируйте server.conf на сервер, client.conf — на клиент.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
