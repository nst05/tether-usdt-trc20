"""Поиск текстовых строк и таблиц данных в образе прошивки."""
from __future__ import annotations

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import analyze
import ihex

CYR = set(range(0xC0, 0x100)) | {0xA8, 0xB8}  # CP1251: А-я, Ё, ё


def printable(b: int) -> bool:
    return 0x20 <= b < 0x7F or b in CYR


def cp1251(data: bytes) -> str:
    try:
        return data.decode("cp1251")
    except UnicodeDecodeError:
        return data.decode("latin1")


def scan(img: ihex.Image, minlen: int = 4):
    out = []
    run = []
    start = None
    for a in range(0x1000, 0x10000):
        b = img.mem.get(a)
        if b is not None and printable(b):
            if start is None:
                start = a
            run.append(b)
        else:
            if start is not None and len(run) >= minlen:
                out.append((start, bytes(run)))
            start, run = None, []
    if start is not None and len(run) >= minlen:
        out.append((start, bytes(run)))
    return out


def main():
    path = sys.argv[1]
    minlen = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    an = analyze.build(path)
    img = an.img
    res = scan(img, minlen)
    print(f"Найдено строк-кандидатов: {len(res)}\n")
    for a, s in res:
        in_code = a in an.code
        xr = an.data_xrefs.get(a, set())
        tag = "код " if in_code else "ДАННЫЕ"
        ref = f" xref:{','.join(f'{x:04X}' for x in sorted(xr))}" if xr else ""
        print(f"{a:04X} [{tag}] {cp1251(s)!r}{ref}")


if __name__ == "__main__":
    main()
