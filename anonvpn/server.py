"""
Сервер AnonVPN.

Слушает UDP, проводит рукопожатие с авторизованными клиентами, форвардит
расшифрованные IP-пакеты в TUN (и наружу через NAT), а пакеты из TUN —
обратно нужному клиенту в зашифрованном и обфусцированном виде.

Запуск (нужен root):
    sudo python -m anonvpn.server --config server.conf
"""

from __future__ import annotations

import argparse
import base64
import logging
import select
import socket
import sys
import time

from . import crypto, obfs, protocol, tun

log = logging.getLogger("anonvpn.server")


class ClientState:
    def __init__(self, addr, session: protocol.Session,
                 static_pub: bytes, vpn_ip: str):
        self.addr = addr
        self.session = session
        self.static_pub = static_pub
        self.vpn_ip = vpn_ip
        self.last_seen = time.time()


def _ipv4_dst(packet: bytes) -> str | None:
    if len(packet) < 20 or (packet[0] >> 4) != 4:
        return None
    return ".".join(str(b) for b in packet[16:20])


def run_server(cfg: dict) -> None:
    static_priv = base64.b64decode(cfg["private_key"])
    allowed = {base64.b64decode(p) for p in cfg["allowed_clients"]}
    # Карта: статический pub клиента -> назначенный ему VPN-IP.
    ip_assignments = cfg["ip_assignments"]

    handshaker = protocol.ServerHandshake(static_priv, allowed)
    obfuscator = obfs.Obfuscator(cfg["obfs_password"])

    tun_if = tun.TunInterface(name=cfg.get("tun_name", "anon0"),
                              mtu=cfg.get("mtu", 1380))
    tun_if.configure(cfg["server_vpn_ip"], cfg["vpn_subnet"].split("/")[0])
    tun.enable_ip_forwarding()
    try:
        tun.setup_nat(cfg["out_interface"], cfg["vpn_subnet"])
    except Exception as exc:  # noqa: BLE001
        log.warning("NAT не настроен (%s); выход в интернет может не работать", exc)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((cfg.get("listen_addr", "0.0.0.0"), cfg["listen_port"]))
    log.info("Сервер слушает %s:%s", cfg.get("listen_addr", "0.0.0.0"),
             cfg["listen_port"])

    # Активные клиенты: по адресу источника и по VPN-IP назначения.
    by_addr: dict = {}
    by_vpnip: dict = {}

    while True:
        readable, _, _ = select.select([sock, tun_if.fileno()], [], [], 30)

        for src in readable:
            if src is sock:
                _handle_udp(sock, obfuscator, handshaker, ip_assignments,
                            by_addr, by_vpnip, tun_if)
            else:
                _handle_tun(sock, obfuscator, by_vpnip, tun_if)

        # Чистим протухшие сессии.
        now = time.time()
        for addr in list(by_addr):
            if now - by_addr[addr].last_seen > 180:
                st = by_addr.pop(addr)
                by_vpnip.pop(st.vpn_ip, None)
                log.info("Сессия истекла: %s", addr)


def _handle_udp(sock, obfuscator, handshaker, ip_assignments,
                by_addr, by_vpnip, tun_if) -> None:
    try:
        raw, addr = sock.recvfrom(65535)
    except OSError:
        return
    payload = obfuscator.unwrap(raw)
    if payload is None or not payload:
        return  # чужой/битый пакет — молча игнорируем (stealth)

    msg_type = payload[0]

    if msg_type == protocol.MSG_INIT:
        try:
            response, session, client_pub = handshaker.consume_init(payload)
        except protocol.HandshakeError as exc:
            log.debug("Отклонено рукопожатие от %s: %s", addr, exc)
            return
        vpn_ip = ip_assignments.get(base64.b64encode(client_pub).decode())
        if vpn_ip is None:
            log.warning("Нет назначенного IP для клиента; отказ")
            return
        st = ClientState(addr, session, client_pub, vpn_ip)
        # Снимаем старую сессию этого же клиента, если была.
        old = by_vpnip.get(vpn_ip)
        if old is not None:
            by_addr.pop(old.addr, None)
        by_addr[addr] = st
        by_vpnip[vpn_ip] = st
        sock.sendto(obfuscator.wrap(response), addr)
        log.info("Клиент подключён: %s -> %s", addr, vpn_ip)
        return

    # Пакет данных от уже установленной сессии.
    st = by_addr.get(addr)
    if st is None:
        return
    result = st.session.decrypt_packet(payload)
    if result is None:
        return
    mtype, ip_packet = result
    st.last_seen = time.time()
    if mtype == protocol.MSG_KEEPALIVE:
        return
    if mtype == protocol.MSG_DATA and ip_packet:
        tun_if.write_packet(ip_packet)


def _handle_tun(sock, obfuscator, by_vpnip, tun_if) -> None:
    packet = tun_if.read_packet()
    dst = _ipv4_dst(packet)
    if dst is None:
        return
    st = by_vpnip.get(dst)
    if st is None:
        return  # нет клиента с таким VPN-IP
    enc = st.session.encrypt_packet(packet)
    sock.sendto(obfuscator.wrap(enc), st.addr)


def load_config(path: str) -> dict:
    import json
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AnonVPN server")
    parser.add_argument("--config", required=True)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_server(load_config(args.config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
