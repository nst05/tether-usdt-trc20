#!/usr/bin/env python3
"""
W25Q64V memory-dump patcher.

Reverse-engineered tool for a two-channel temperature logger that stores its
samples in a W25Q64V (8 MiB) SPI flash, read out with a CH341 programmer.

Record format (128 bytes = one hourly super-record):

    META  [base+0x00 .. base+0x40)   device settings + a 6-byte device-side
                                      trailer (NOT a checksum of the sample,
                                      see README) followed by 0xFF padding
    DATA  [base+0x40 .. base+0x80)   the sample:

        DATA offset  file offset  type     meaning
        +0x00        base+0x40    u32 LE   Unix timestamp
        +0x04        base+0x44    u32 LE   timestamp high word (always 0)
        +0x08        base+0x48    u32 LE   sample counter
        +0x0C        base+0x4C    float64  channel-1 coefficient (== 1.280)
        +0x14        base+0x54    float64  channel-1 offset      (== 0.0)
        +0x1C        base+0x5C    float64  channel-2 coefficient (== 1.280)
        +0x24        base+0x64    float32  channel-1 value  (shown on screen)
        +0x28        base+0x68    float32  0.0 (unused)
        +0x2C        base+0x6C    float32  channel-2 value  (shown on screen)
        +0x30        base+0x70    float32  -35.0 constant (anchor)
        +0x34        base+0x74    float32  -35.0 constant (anchor)
        +0x38        base+0x78    float32  -35.0 constant (anchor)

The displayed value is  shown = raw * coeff + offset  (coeff = 1.280,
offset = 0).  To make the device show an arbitrary value X on a channel you can
either write X directly into the channel float, or change the coefficient.

Records are 0x80 apart but the log phase drifts across the flash (ring buffer /
page wrap), so records are located by the invariant -35.0 anchor, never by a
fixed stride.
"""

import argparse
import struct
import sys
from datetime import datetime, timezone

RECORD_SIZE = 0x80
DATA_OFF = 0x40  # data block starts here inside a super-record

# field offsets relative to the DATA block start
F_TS = 0x00
F_COUNTER = 0x08
F_COEFF1 = 0x0C   # float64
F_OFFSET1 = 0x14  # float64
F_COEFF2 = 0x1C   # float64
F_CH1 = 0x24      # float32  (displayed)
F_CH2 = 0x2C      # float32  (displayed)
F_ANCHOR = 0x30   # three -35.0 float32 in a row

MINUS35 = struct.pack("<f", -35.0)
ANCHOR = MINUS35 * 3  # 12 bytes, present in every record, never patched

FIELDS = {
    "ch1":    (F_CH1, "f"),
    "ch2":    (F_CH2, "f"),
    "coeff1": (F_COEFF1, "d"),
    "coeff2": (F_COEFF2, "d"),
    "offset1": (F_OFFSET1, "d"),
}


def find_records(buf):
    """Return sorted list of DATA-block start offsets.

    Anchored on the invariant three -35.0 floats at DATA+0x30, so it keeps
    working no matter how coefficients or channel values are patched.
    """
    bases = []
    start = 0
    n = len(buf)
    while True:
        i = buf.find(ANCHOR, start)
        if i < 0:
            break
        start = i + 1
        data_base = i - F_ANCHOR
        if data_base < 0 or data_base + DATA_OFF > n:
            continue
        ts = struct.unpack_from("<I", buf, data_base + F_TS)[0]
        # plausible Unix time 2020..2035
        if 0x5E000000 <= ts <= 0x7A000000:
            bases.append(data_base)
    return bases


def decode(buf, base):
    ts = struct.unpack_from("<I", buf, base + F_TS)[0]
    counter = struct.unpack_from("<I", buf, base + F_COUNTER)[0]
    coeff1 = struct.unpack_from("<d", buf, base + F_COEFF1)[0]
    coeff2 = struct.unpack_from("<d", buf, base + F_COEFF2)[0]
    ch1 = struct.unpack_from("<f", buf, base + F_CH1)[0]
    ch2 = struct.unpack_from("<f", buf, base + F_CH2)[0]
    when = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return dict(base=base, ts=ts, when=when, counter=counter,
                coeff1=coeff1, coeff2=coeff2, ch1=ch1, ch2=ch2)


def load(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_info(args):
    buf = load(args.file)
    bases = find_records(buf)
    print(f"file        : {args.file}")
    print(f"size        : {len(buf)} bytes ({len(buf)//1024//1024} MiB)")
    print(f"records     : {len(bases)}")
    if not bases:
        return
    first, last = decode(buf, bases[0]), decode(buf, bases[-1])
    counters = [struct.unpack_from('<I', buf, b + F_COUNTER)[0] for b in bases]
    print(f"time range  : {first['when']}  ->  {last['when']}")
    print(f"counter range: {min(counters)} .. {max(counters)}")
    print(f"coeff (ch1) : {first['coeff1']}")
    print(f"coeff (ch2) : {first['coeff2']}")


def cmd_list(args):
    buf = load(args.file)
    bases = find_records(buf)
    lo = args.start or 0
    hi = args.end if args.end is not None else len(bases)
    if args.csv:
        print("index,file_offset,timestamp,counter,coeff1,coeff2,ch1,ch2")
    else:
        print(f"{'idx':>5} {'offset':>9} {'time':<19} {'cnt':>6} "
              f"{'coeff1':>8} {'ch1':>8} {'ch2':>8}")
    for idx in range(lo, min(hi, len(bases))):
        r = decode(buf, bases[idx])
        if args.csv:
            print(f"{idx},{r['base']:#08x},{r['when']},{r['counter']},"
                  f"{r['coeff1']:.6f},{r['coeff2']:.6f},{r['ch1']:.4f},{r['ch2']:.4f}")
        else:
            print(f"{idx:5d} {r['base']:#09x} {r['when']:<19} {r['counter']:6d} "
                  f"{r['coeff1']:8.3f} {r['ch1']:8.3f} {r['ch2']:8.3f}")


def _resolve_indices(bases, spec):
    """spec: 'all' | '12' | '10-40'"""
    if spec == "all":
        return list(range(len(bases)))
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(spec)]


def cmd_set(args):
    buf = load(args.file)
    bases = find_records(buf)
    if args.field not in FIELDS:
        sys.exit(f"unknown field '{args.field}'; choose from {list(FIELDS)}")
    foff, fmt = FIELDS[args.field]
    packed = struct.pack("<" + fmt, args.value)

    indices = _resolve_indices(bases, args.records)
    changed = 0
    for idx in indices:
        if idx < 0 or idx >= len(bases):
            sys.exit(f"record index {idx} out of range (0..{len(bases)-1})")
        pos = bases[idx] + foff
        buf[pos:pos + len(packed)] = packed
        changed += 1

    out = args.out or args.file
    with open(out, "wb") as f:
        f.write(buf)

    # verify by re-reading
    verify = load(out)
    vbases = find_records(verify)
    ok = True
    for idx in indices:
        got = struct.unpack_from("<" + fmt, verify, vbases[idx] + foff)[0]
        if abs(got - args.value) > (1e-4 if fmt == "f" else 1e-9):
            ok = False
            print(f"  !! verify failed at record {idx}: got {got}")
    print(f"patched {changed} record(s): {args.field} = {args.value}")
    print(f"written : {out}")
    print(f"verify  : {'OK' if ok else 'FAILED'}")


def build_parser():
    p = argparse.ArgumentParser(description="W25Q64V logger dump patcher")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("info", help="summary of the dump")
    pi.add_argument("file")
    pi.set_defaults(func=cmd_info)

    pl = sub.add_parser("list", help="list decoded records")
    pl.add_argument("file")
    pl.add_argument("--start", type=int, default=0)
    pl.add_argument("--end", type=int, default=None)
    pl.add_argument("--csv", action="store_true", help="CSV output")
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("set", help="set a field and write a patched dump")
    ps.add_argument("file")
    ps.add_argument("field", help="one of: " + ", ".join(FIELDS))
    ps.add_argument("value", type=float)
    ps.add_argument("--records", default="all",
                    help="'all', a single index '12', or a range '10-40'")
    ps.add_argument("--out", help="output file (default: overwrite in place)")
    ps.set_defaults(func=cmd_set)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
