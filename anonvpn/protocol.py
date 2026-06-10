"""
Рукопожатие и шифрование сессии AnonVPN.

Рукопожатие вдохновлено WireGuard / Noise IK: обе стороны имеют статические
X25519-ключи и заранее знают публичный ключ собеседника (как в WireGuard).
Это даёт:
  * Взаимную аутентификацию (никто посторонний не установит сессию).
  * Forward secrecy (компрометация статических ключей не раскрывает прошлый
    трафик — благодаря эфемерным ключам).
  * Сокрытие идентичности: статические публичные ключи НЕ передаются в открытом
    виде (сервер уже знает ключ клиента из конфигурации), а на проводе всё ещё
    дополнительно гаммируется слоем обфускации.

Сообщения:
  HANDSHAKE_INIT     (клиент -> сервер): эфемерный pub + зашифрованный timestamp
  HANDSHAKE_RESPONSE (сервер -> клиент): эфемерный pub + подтверждение
  DATA               (обе стороны): зашифрованный AEAD IP-пакет
"""

from __future__ import annotations

import struct

from . import crypto

# Типы сообщений (первый байт расшифрованного payload)
MSG_INIT = 0x01
MSG_RESPONSE = 0x02
MSG_DATA = 0x03
MSG_KEEPALIVE = 0x04


class HandshakeError(Exception):
    pass


def _mix(*chunks: bytes) -> bytes:
    out = b""
    for c in chunks:
        out += c
    return out


# --------------------------------------------------------------------------- #
# Сторона клиента (инициатор)
# --------------------------------------------------------------------------- #
class ClientHandshake:
    def __init__(self, static_priv: bytes, server_static_pub: bytes):
        self.s_priv = static_priv
        self.s_pub = crypto.public_from_private(static_priv)
        self.server_pub = server_static_pub
        self.e_priv, self.e_pub = crypto.generate_keypair()

    def build_init(self) -> bytes:
        """
        INIT = MSG_INIT | e_pub(32) | aead(timestamp)
        Ключ для шифрования timestamp выводится из ECDH(e_C, s_S),
        что заодно доказывает серверу, что клиент знает его статический ключ.
        """
        es = crypto.dh(self.e_priv, self.server_pub)
        k = crypto.hkdf(es, crypto.PROTOCOL_LABEL + b"|init", salt=self.e_pub)
        aead = crypto.AeadCipher(k)
        ts = crypto.timestamp_now()
        # В AAD кладём наш статический pub — связываем личность с рукопожатием.
        ct = aead.seal(0, ts, aad=self.s_pub)
        return struct.pack("B", MSG_INIT) + self.e_pub + ct

    def consume_response(self, payload: bytes) -> "Session":
        if not payload or payload[0] != MSG_RESPONSE:
            raise HandshakeError("ожидался RESPONSE")
        body = payload[1:]
        if len(body) < 32 + crypto.TAG_LEN:
            raise HandshakeError("короткий RESPONSE")
        server_e_pub = body[:32]
        confirm_ct = body[32:]

        master = self._derive_master(server_e_pub)
        # Сервер подтверждает владение статикой, шифруя фиксированную метку.
        confirm_key = crypto.hkdf(master, b"confirm")
        aead = crypto.AeadCipher(confirm_key)
        try:
            tag = aead.open(0, confirm_ct, aad=self.s_pub)
        except Exception as exc:  # noqa: BLE001
            raise HandshakeError("аутентификация сервера не пройдена") from exc
        if tag != b"AnonVPN-confirm":
            raise HandshakeError("неверная метка подтверждения")

        send_key, recv_key = crypto.hkdf_pair(master, b"client-keys")
        return Session(send_key=send_key, recv_key=recv_key)

    def _derive_master(self, server_e_pub: bytes) -> bytes:
        ee = crypto.dh(self.e_priv, server_e_pub)        # forward secrecy
        es = crypto.dh(self.e_priv, self.server_pub)     # аутентификация сервера
        se = crypto.dh(self.s_priv, server_e_pub)        # аутентификация клиента
        return crypto.hkdf(_mix(ee, es, se), crypto.PROTOCOL_LABEL + b"|master")


# --------------------------------------------------------------------------- #
# Сторона сервера (респондер)
# --------------------------------------------------------------------------- #
class ServerHandshake:
    def __init__(self, static_priv: bytes, allowed_client_pubs: set[bytes]):
        self.s_priv = static_priv
        self.s_pub = crypto.public_from_private(static_priv)
        self.allowed = set(allowed_client_pubs)

    def consume_init(self, payload: bytes) -> tuple[bytes, "Session", bytes]:
        """
        Возвращает (response_payload, session, client_static_pub).
        Бросает HandshakeError, если клиент не авторизован.
        """
        if not payload or payload[0] != MSG_INIT:
            raise HandshakeError("ожидался INIT")
        body = payload[1:]
        if len(body) < 32 + crypto.TAG_LEN:
            raise HandshakeError("короткий INIT")
        client_e_pub = body[:32]
        ct = body[32:]

        es = crypto.dh(self.s_priv, client_e_pub)
        k = crypto.hkdf(es, crypto.PROTOCOL_LABEL + b"|init", salt=client_e_pub)
        aead = crypto.AeadCipher(k)

        # Перебираем разрешённые статические ключи клиентов: AAD = client_static_pub.
        client_static = None
        for cand in self.allowed:
            try:
                aead.open(0, ct, aad=cand)
                client_static = cand
                break
            except Exception:  # noqa: BLE001
                continue
        if client_static is None:
            raise HandshakeError("неизвестный или неавторизованный клиент")

        # Эфемерные ключи сервера + общий master.
        e_priv, e_pub = crypto.generate_keypair()
        ee = crypto.dh(e_priv, client_e_pub)
        es2 = crypto.dh(self.s_priv, client_e_pub)
        se = crypto.dh(e_priv, client_static)
        master = crypto.hkdf(_mix(ee, es2, se),
                             crypto.PROTOCOL_LABEL + b"|master")

        confirm_key = crypto.hkdf(master, b"confirm")
        confirm_ct = crypto.AeadCipher(confirm_key).seal(
            0, b"AnonVPN-confirm", aad=client_static
        )
        response = struct.pack("B", MSG_RESPONSE) + e_pub + confirm_ct

        # У сервера направления ключей зеркальны клиентским.
        recv_key, send_key = crypto.hkdf_pair(master, b"client-keys")
        session = Session(send_key=send_key, recv_key=recv_key)
        return response, session, client_static


# --------------------------------------------------------------------------- #
# Установленная сессия: шифрование/дешифрование пакетов данных
# --------------------------------------------------------------------------- #
class Session:
    def __init__(self, send_key: bytes, recv_key: bytes):
        self._send = crypto.AeadCipher(send_key)
        self._recv = crypto.AeadCipher(recv_key)
        self._send_counter = 0
        self._replay = crypto.ReplayWindow()

    def encrypt_packet(self, ip_packet: bytes,
                       msg_type: int = MSG_DATA) -> bytes:
        counter = self._send_counter
        self._send_counter += 1
        header = struct.pack("B", msg_type) + struct.pack(">Q", counter)
        ct = self._send.seal(counter, ip_packet, aad=header)
        return header + ct

    def decrypt_packet(self, datagram: bytes) -> tuple[int, bytes] | None:
        if len(datagram) < 9 + crypto.TAG_LEN:
            return None
        msg_type = datagram[0]
        counter = struct.unpack(">Q", datagram[1:9])[0]
        header = datagram[:9]
        ct = datagram[9:]
        if not self._replay.check_and_update(counter):
            return None  # реплей или слишком старый пакет
        try:
            pt = self._recv.open(counter, ct, aad=header)
        except Exception:  # noqa: BLE001
            return None  # подделка / повреждение
        return msg_type, pt
