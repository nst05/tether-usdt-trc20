#!/usr/bin/env python3
"""Совместимый публичный фасад клиента SMT.

Реализация начиная с v4.5.3 разделена на пакет ``smt_core``; старые импорты
``import smt_client as sc`` продолжают работать без изменения поведения.
"""
from __future__ import annotations

import sys

from smt_core.client import *  # noqa: F401,F403
from smt_core.commands import *  # noqa: F401,F403
from smt_core.protocol import *  # noqa: F401,F403
from smt_core.transports import *  # noqa: F401,F403
from smt_logging import configure_logging


def main() -> None:
    configure_logging()
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    port = sys.argv[1]
    transport = OpticTransport(port)
    transport.probe()
    client = SmtClient(transport)
    try:
        if "--passport" in sys.argv:
            print(f"# паспорт физического прибора · порт {port}\n")
            for key, value in client.get_all().items():
                print(f"  {key:<20} = {value!r}")
            return
        if "--get" in sys.argv:
            name = sys.argv[sys.argv.index("--get") + 1]
            print(f"{name} = {client.get(name)!r}")
            return
        if "--send" in sys.argv:
            command = sys.argv[sys.argv.index("--send") + 1]
            try:
                raw = client.send(
                    command,
                    expert=("--expert" in sys.argv),
                    mutating=is_mutating_command(command),
                )
                print(f">> {command}\n<< {raw!r}")
            except PermissionError as exc:
                print(exc)
            return
        print(__doc__)
    finally:
        transport.close()


if __name__ == "__main__":
    main()
