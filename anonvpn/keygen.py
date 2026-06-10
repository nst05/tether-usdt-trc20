"""
Генерация ключей AnonVPN.

Использование:
    python -m anonvpn.keygen          # вывести новую пару ключей
    python -m anonvpn.keygen --pub <priv_base64>   # получить pub из priv
"""

from __future__ import annotations

import argparse
import base64
import sys

from . import crypto


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(text: str) -> bytes:
    return base64.b64decode(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AnonVPN keygen")
    parser.add_argument("--pub", metavar="PRIV_B64",
                        help="вывести публичный ключ из приватного")
    args = parser.parse_args(argv)

    if args.pub:
        priv = unb64(args.pub)
        print(b64(crypto.public_from_private(priv)))
        return 0

    priv, pub = crypto.generate_keypair()
    print(f"private = {b64(priv)}")
    print(f"public  = {b64(pub)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
