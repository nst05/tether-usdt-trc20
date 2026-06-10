"""
Cryptographic primitives for AnonVPN.

Design goals:
  * Modern, misuse-resistant AEAD (ChaCha20-Poly1305).
  * Curve25519 (X25519) Diffie-Hellman.
  * HKDF-SHA256 for key derivation.
  * A WireGuard-inspired, mutually-authenticated handshake that gives
    forward secrecy and hides peer identities from a passive observer.

This module deliberately depends only on `cryptography` (pyca), which wraps
audited C implementations (OpenSSL / BoringSSL). Do NOT roll your own ciphers.
"""

from __future__ import annotations

import os
import struct
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    PrivateFormat,
    NoEncryption,
)

KEY_LEN = 32
NONCE_LEN = 12
TAG_LEN = 16

# Protocol-wide domain separation string. Changing this makes the whole
# wire format incompatible, which is exactly what you want between versions.
PROTOCOL_LABEL = b"AnonVPN-v1-Noise-X25519-ChaChaPoly"


# --------------------------------------------------------------------------- #
# Key management
# --------------------------------------------------------------------------- #
def generate_keypair() -> tuple[bytes, bytes]:
    """Return (private_key_bytes, public_key_bytes) for a fresh X25519 key."""
    priv = X25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )
    pub_raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv_raw, pub_raw


def public_from_private(priv_raw: bytes) -> bytes:
    priv = X25519PrivateKey.from_private_bytes(priv_raw)
    return priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def dh(priv_raw: bytes, pub_raw: bytes) -> bytes:
    """X25519 shared secret."""
    priv = X25519PrivateKey.from_private_bytes(priv_raw)
    pub = X25519PublicKey.from_public_bytes(pub_raw)
    return priv.exchange(pub)


# --------------------------------------------------------------------------- #
# KDF
# --------------------------------------------------------------------------- #
def hkdf(key_material: bytes, info: bytes, length: int = KEY_LEN,
         salt: bytes | None = None) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=info,
    ).derive(key_material)


def hkdf_pair(key_material: bytes, info: bytes) -> tuple[bytes, bytes]:
    """Derive two independent 32-byte keys at once (e.g. send/recv keys)."""
    out = hkdf(key_material, info, length=2 * KEY_LEN)
    return out[:KEY_LEN], out[KEY_LEN:]


# --------------------------------------------------------------------------- #
# AEAD wrapper with a strict, never-reused nonce
# --------------------------------------------------------------------------- #
class AeadCipher:
    """
    ChaCha20-Poly1305 with a 64-bit monotonic counter expanded to a 96-bit
    nonce. A single key is bound to a single direction; the counter must never
    repeat for a given key, so we refuse to wrap around.
    """

    MAX_COUNTER = (1 << 64) - 2  # leave headroom; force rekey before exhaustion

    def __init__(self, key: bytes):
        if len(key) != KEY_LEN:
            raise ValueError("key must be 32 bytes")
        self._aead = ChaCha20Poly1305(key)

    @staticmethod
    def _nonce(counter: int) -> bytes:
        # 4 zero bytes + 8-byte big-endian counter = 12-byte nonce.
        return b"\x00\x00\x00\x00" + struct.pack(">Q", counter)

    def seal(self, counter: int, plaintext: bytes, aad: bytes = b"") -> bytes:
        if counter > self.MAX_COUNTER:
            raise OverflowError("nonce counter exhausted; rekey required")
        return self._aead.encrypt(self._nonce(counter), plaintext, aad)

    def open(self, counter: int, ciphertext: bytes, aad: bytes = b"") -> bytes:
        return self._aead.decrypt(self._nonce(counter), ciphertext, aad)


# --------------------------------------------------------------------------- #
# Anti-replay sliding window (RFC 6479 style)
# --------------------------------------------------------------------------- #
class ReplayWindow:
    """Rejects duplicated or too-old packet counters."""

    def __init__(self, size: int = 1024):
        self.size = size
        self.bitmap: set[int] = set()
        self.highest = -1

    def check_and_update(self, counter: int) -> bool:
        if counter < 0:
            return False
        if counter > self.highest:
            # advance window; drop entries that fell out of range
            self.highest = counter
            self.bitmap = {c for c in self.bitmap if c > counter - self.size}
            self.bitmap.add(counter)
            return True
        if counter <= self.highest - self.size:
            return False  # too old
        if counter in self.bitmap:
            return False  # replay
        self.bitmap.add(counter)
        return True


def timestamp_now() -> bytes:
    """Tai64-ish 12-byte timestamp used as an anti-replay nonce in handshakes."""
    now = time.time()
    secs = int(now)
    nanos = int((now - secs) * 1e9)
    return struct.pack(">QI", secs + (2 ** 62), nanos)


def random_bytes(n: int) -> bytes:
    return os.urandom(n)
