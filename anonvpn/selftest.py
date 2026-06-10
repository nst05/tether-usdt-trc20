"""
Самопроверка криптоядра без root и без TUN.

Прогоняет полный цикл: генерация ключей -> рукопожатие клиент/сервер ->
шифрование/дешифрование пакетов -> обфускация/деобфускация -> проверки
защиты от реплея и подделки.

    python -m anonvpn.selftest
"""

from __future__ import annotations

from . import crypto, obfs, protocol


def _ok(cond: bool, msg: str) -> None:
    status = "OK  " if cond else "FAIL"
    print(f"[{status}] {msg}")
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    print("== AnonVPN selftest ==")

    # 1. Ключи
    s_priv, s_pub = crypto.generate_keypair()
    c_priv, c_pub = crypto.generate_keypair()
    _ok(crypto.public_from_private(s_priv) == s_pub, "вывод pub из priv")

    # 2. Рукопожатие
    client = protocol.ClientHandshake(c_priv, s_pub)
    server = protocol.ServerHandshake(s_priv, {c_pub})
    init = client.build_init()
    response, server_sess, who = server.consume_init(init)
    _ok(who == c_pub, "сервер опознал клиента по статическому ключу")
    client_sess = client.consume_response(response)

    # 3. Симметричность ключей сессии (клиент<->сервер)
    msg = b"Hello over the encrypted tunnel \x00\x01\x02\xff"
    enc = client_sess.encrypt_packet(msg)
    dec = server_sess.decrypt_packet(enc)
    _ok(dec is not None and dec[1] == msg, "клиент -> сервер шифрование")

    reply = b"response payload"
    enc2 = server_sess.encrypt_packet(reply)
    dec2 = client_sess.decrypt_packet(enc2)
    _ok(dec2 is not None and dec2[1] == reply, "сервер -> клиент шифрование")

    # 4. Защита от реплея
    replayed = server_sess.decrypt_packet(enc)
    _ok(replayed is None, "реплей того же пакета отклонён")

    # 5. Защита от подделки (изменён один байт шифротекста)
    tampered = bytearray(client_sess.encrypt_packet(b"secret"))
    tampered[-1] ^= 0x01
    _ok(server_sess.decrypt_packet(bytes(tampered)) is None,
        "подделанный пакет отклонён AEAD")

    # 6. Чужой клиент (не в allowlist) не проходит рукопожатие
    evil_priv, _ = crypto.generate_keypair()
    evil = protocol.ClientHandshake(evil_priv, s_pub)
    try:
        server.consume_init(evil.build_init())
        rejected = False
    except protocol.HandshakeError:
        rejected = True
    _ok(rejected, "неавторизованный клиент отклонён")

    # 7. Обфускация: round-trip и отсутствие явных сигнатур
    ob = obfs.Obfuscator("super-secret-obfs-password")
    payload = enc
    wire = ob.wrap(payload)
    back = ob.unwrap(wire)
    _ok(back == payload, "обфускация round-trip")
    _ok(wire[:12] != b"\x00" * 12, "nonce обфускации не нулевой")
    # Разные оборачивания одного payload должны выглядеть по-разному.
    _ok(ob.wrap(payload) != ob.wrap(payload), "обфускация рандомизирована")

    # 8. Неверный пароль обфускации -> мусор/None, не падение
    ob_wrong = obfs.Obfuscator("wrong-password")
    res = ob_wrong.unwrap(wire)
    _ok(res != payload, "чужой пароль обфускации не даёт исходный payload")

    print("\nВсе проверки пройдены ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
