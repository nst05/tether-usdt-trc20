"""
Слой обфускации трафика ("anti-DPI").

Задача: сделать так, чтобы пассивный наблюдатель (провайдер, локальная сеть,
DPI-оборудование) не мог по сигнатуре определить, что это VPN. У наших датаграмм
нет магических байтов, фиксированных заголовков или предсказуемой структуры —
снаружи это выглядит как равномерный случайный шум поверх UDP.

Техники:
  * Полное гаммирование (XOR keystream) датаграммы ключом-обфускатором,
    выведенным из пароля. Даже рукопожатие выглядит случайным.
  * Случайный padding переменной длины, чтобы скрыть истинный размер пакета
    (защита от анализа длин — traffic-shaping / packet-length fingerprinting).
  * Лёгкий джиттер по времени отправки (управляется на уровне транспорта).

ВАЖНО: обфускация — это НЕ замена шифрованию. Конфиденциальность обеспечивает
AEAD из crypto.py. Обфускация лишь прячет факт использования VPN.
"""

from __future__ import annotations

import os
import struct

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def derive_obfs_key(password: str) -> bytes:
    """Выводит 32-байтный ключ обфускации из общего пароля."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"AnonVPN-obfs-salt-v1",
        info=b"obfuscation-keystream",
    ).derive(password.encode("utf-8"))


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """ChaCha20 keystream (через шифрование нулей)."""
    # 16-байтовый nonce для ChaCha20 в pyca: 4 байта счётчика + 12 байт nonce.
    full_nonce = b"\x00\x00\x00\x00" + nonce
    cipher = Cipher(algorithms.ChaCha20(key, full_nonce), mode=None)
    enc = cipher.encryptor()
    return enc.update(b"\x00" * length)


class Obfuscator:
    """
    Оборачивает/разворачивает датаграммы.

    Формат на проводе (всё целиком гаммируется keystream'ом):
        [ 12 байт случайный nonce обфускации (в открытом виде) ]
        [ keystream( 2 байта длина паддинга | padding | payload ) ]
    """

    def __init__(self, password: str, max_pad: int = 256):
        self.key = derive_obfs_key(password)
        self.max_pad = max_pad

    def wrap(self, payload: bytes) -> bytes:
        nonce = os.urandom(12)
        pad_len = struct.unpack(">H", os.urandom(2))[0] % (self.max_pad + 1)
        padding = os.urandom(pad_len)
        inner = struct.pack(">H", pad_len) + padding + payload
        ks = _keystream(self.key, nonce, len(inner))
        masked = bytes(a ^ b for a, b in zip(inner, ks))
        return nonce + masked

    def unwrap(self, datagram: bytes) -> bytes | None:
        if len(datagram) < 12 + 2:
            return None
        nonce, masked = datagram[:12], datagram[12:]
        ks = _keystream(self.key, nonce, len(masked))
        inner = bytes(a ^ b for a, b in zip(masked, ks))
        pad_len = struct.unpack(">H", inner[:2])[0]
        if 2 + pad_len > len(inner):
            return None  # битый или чужой пакет
        return inner[2 + pad_len:]
