"""Формирование полного дизассемблированного листинга прошивки."""
from __future__ import annotations

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import analyze
import msp430


def render(an: analyze.Analysis, out) -> None:
    img = an.img
    out.write("; ------------------------------------------------------------\n")
    out.write("; Дизассемблированный листинг прошивки (MSP430F249)\n")
    out.write("; Получен автоматически: tools/listing.py\n")
    out.write("; ------------------------------------------------------------\n\n")

    addr = 0x1100
    while addr <= 0xFFFF:
        if addr in an.insns:
            ins = an.insns[addr]
            if addr in an.func_entries:
                callers = an.call_xrefs.get(addr, set())
                out.write("\n; " + "=" * 60 + "\n")
                out.write(f"; Функция {an.symbols.get(addr, '')} @ 0x{addr:04X}"
                          f"   (вызовов: {len(callers)})\n")
                if callers:
                    lst = ", ".join(f"0x{c:04X}" for c in sorted(callers)[:12])
                    out.write(f";   вызывается из: {lst}\n")
                out.write("; " + "=" * 60 + "\n")
            elif addr in an.jump_xrefs:
                src = ", ".join(f"0x{c:04X}" for c in sorted(an.jump_xrefs[addr])[:8])
                out.write(f"\nloc_{addr:04X}:\t\t\t; переходы из {src}\n")
            out.write(f"{addr:04X}:  {ins.hexwords:<15} {ins.text}\n")
            addr += ins.size
        else:
            # область данных — вывод словами с ASCII-представлением
            start = addr
            chunk = []
            while addr <= 0xFFFF and addr not in an.insns and len(chunk) < 8:
                if not img.has_range(addr, 2):
                    break
                chunk.append(img.word(addr))
                addr += 2
            if not chunk:
                addr += 2
                continue
            raw = b"".join(w.to_bytes(2, "little") for w in chunk)
            if all(w == 0xFFFF for w in chunk):
                continue
            txt = "".join(chr(c) if 32 <= c < 127 else "." for c in raw)
            words = " ".join(f"{w:04X}" for w in chunk)
            out.write(f"{start:04X}:  .word {words:<40} |{txt}|\n")


def main():
    an = analyze.build(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        render(an, fh)
    print(f"Листинг записан: {sys.argv[2]}")


if __name__ == "__main__":
    main()
