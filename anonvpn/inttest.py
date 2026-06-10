"""
Интеграционный тест: реальные UDP-сокеты по loopback, без TUN.

Поднимает мини-сервер в отдельном потоке, клиент делает рукопожатие и
обменивается зашифрованными+обфусцированными «пакетами». Проверяет, что весь
проводной путь (obfs -> AEAD -> handshake -> data) работает на живых сокетах.

    python -m anonvpn.inttest
"""

from __future__ import annotations

import socket
import threading

from . import crypto, obfs, protocol


def _server(sock, s_priv, allowed, ob, ready, result):
    handshaker = protocol.ServerHandshake(s_priv, allowed)
    session = None
    ready.set()
    while True:
        raw, addr = sock.recvfrom(65535)
        payload = ob.unwrap(raw)
        if payload is None:
            continue
        if payload[0] == protocol.MSG_INIT:
            resp, session, _ = handshaker.consume_init(payload)
            sock.sendto(ob.wrap(resp), addr)
        elif session is not None:
            dec = session.decrypt_packet(payload)
            if dec is None:
                continue
            _, data = dec
            # эхо обратно
            echo = session.encrypt_packet(b"echo:" + data)
            sock.sendto(ob.wrap(echo), addr)
            if data == b"BYE":
                result["ok"] = True
                return


def main() -> int:
    print("== AnonVPN integration test (UDP loopback) ==")
    s_priv, s_pub = crypto.generate_keypair()
    c_priv, c_pub = crypto.generate_keypair()
    ob = obfs.Obfuscator("integration-pass")

    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]

    ready = threading.Event()
    result = {"ok": False}
    t = threading.Thread(target=_server,
                         args=(srv, s_priv, {c_pub}, ob, ready, result),
                         daemon=True)
    t.start()
    ready.wait()

    cli = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cli.settimeout(3)
    addr = ("127.0.0.1", port)

    handshake = protocol.ClientHandshake(c_priv, s_pub)
    cli.sendto(ob.wrap(handshake.build_init()), addr)
    raw, _ = cli.recvfrom(65535)
    session = handshake.consume_response(ob.unwrap(raw))
    print("[OK  ] рукопожатие по реальному UDP")

    for payload in [b"packet-1", b"packet-2", b"BYE"]:
        cli.sendto(ob.wrap(session.encrypt_packet(payload)), addr)
        raw, _ = cli.recvfrom(65535)
        _, data = session.decrypt_packet(ob.unwrap(raw))
        assert data == b"echo:" + payload, data
    print("[OK  ] обмен зашифрованными пакетами туда-обратно")

    t.join(timeout=2)
    assert result["ok"], "сервер не завершил сценарий"
    print("[OK  ] сервер обработал весь поток")
    print("\nИнтеграционный тест пройден ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
