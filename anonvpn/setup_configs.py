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


def _ip_from_subnet(subnet: str, host: int) -> str:
    """Берёт сеть вида 10.9.0.0/24 и возвращает адрес .<host>."""
    base = subnet.split("/")[0].rsplit(".", 1)[0]
    return f"{base}.{host}"


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
    p.add_argument("--subnet", default="10.9.0.0/24")
    p.add_argument("--clients", type=int, default=1,
                   help="сколько клиентских устройств сгенерировать")
    p.add_argument("--redirect-all", action="store_true",
                   help="заворачивать весь трафик клиента в туннель")
    p.add_argument("--dns", default="1.1.1.1,1.0.0.1",
                   help="DNS-серверы клиента через запятую (пусто = не менять)")
    p.add_argument("--kill-switch", action="store_true",
                   help="включить kill-switch у клиентов (блок трафика при обрыве)")
    args = p.parse_args(argv)

    s_priv, s_pub = crypto.generate_keypair()
    dns_servers = [d.strip() for d in args.dns.split(",") if d.strip()]

    allowed_clients: list[str] = []
    ip_assignments: dict[str, str] = {}
    client_summaries: list[str] = []

    for idx in range(args.clients):
        c_priv, c_pub = crypto.generate_keypair()
        # клиентам раздаём .2, .3, .4 ... (.1 занят сервером)
        client_ip = _ip_from_subnet(args.subnet, 2 + idx)
        allowed_clients.append(b64(c_pub))
        ip_assignments[b64(c_pub)] = client_ip

        client_conf = {
            "private_key": b64(c_priv),
            "server_public_key": b64(s_pub),
            "server_host": args.server_host,
            "server_port": args.server_port,
            "client_vpn_ip": client_ip,
            "server_vpn_ip": args.server_vpn_ip,
            "obfs_password": args.obfs_pass,
            "tun_name": "anon0",
            "mtu": 1380,
            "redirect_gateway": bool(args.redirect_all),
            "dns_servers": dns_servers,
            "kill_switch": bool(args.kill_switch),
        }
        fname = "client.conf" if args.clients == 1 else f"client{idx + 1}.conf"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(client_conf, f, indent=2, ensure_ascii=False)
        os.chmod(fname, 0o600)
        client_summaries.append(f"  {fname}: {client_ip}  pub={b64(c_pub)}")

    server_conf = {
        "private_key": b64(s_priv),
        "allowed_clients": allowed_clients,
        "ip_assignments": ip_assignments,
        "listen_addr": "0.0.0.0",
        "listen_port": args.server_port,
        "server_vpn_ip": args.server_vpn_ip,
        "vpn_subnet": args.subnet,
        "out_interface": args.out_interface,
        "obfs_password": args.obfs_pass,
        "tun_name": "anon0",
        "mtu": 1380,
    }
    with open("server.conf", "w", encoding="utf-8") as f:
        json.dump(server_conf, f, indent=2, ensure_ascii=False)
    os.chmod("server.conf", 0o600)

    print(f"Создан server.conf и {args.clients} клиентский(их) конфиг(ов):")
    print(f"  server public key: {b64(s_pub)}")
    for line in client_summaries:
        print(line)
    print("Скопируйте server.conf на сервер, каждый clientN.conf — на своё "
          "устройство.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
