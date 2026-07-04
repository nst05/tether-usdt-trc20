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
        +0x0C        base+0x4C    float64  READING shown on screen (e.g. 1.280)
        +0x14        base+0x54    float64  0.0 (unused)
        +0x1C        base+0x5C    float64  READING, mirror copy (always == +0x0C)
        +0x24        base+0x64    float32  temperature channel 1 (~ deg C)
        +0x28        base+0x68    float32  0.0 (unused)
        +0x2C        base+0x6C    float32  temperature channel 2 (~ deg C)
        +0x30        base+0x70    float32  -35.0 constant (anchor)
        +0x34        base+0x74    float32  -35.0 constant (anchor)
        +0x38        base+0x78    float32  -35.0 constant (anchor)

The main value on the display is stored *directly* as the float64 reading at
+0x0C, duplicated at +0x1C (the two copies are always identical -- redundant
mirror).  There is no scaling: stored value == displayed value.  Over the dump
the reading takes real measured values (1.280, 0.662944, ...), confirming it is
the measurement and not a calibration constant.  To make the device show X,
write float64(X) into both +0x0C and +0x1C.

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
F_READING = 0x0C   # float64  displayed reading
F_READING2 = 0x1C  # float64  mirror copy of the reading
F_TEMP1 = 0x24     # float32  temperature channel 1
F_TEMP2 = 0x2C     # float32  temperature channel 2
F_ANCHOR = 0x30    # three -35.0 float32 in a row

MINUS35 = struct.pack("<f", -35.0)
ANCHOR = MINUS35 * 3  # 12 bytes, present in every record, never patched

# name -> (format, [offsets to write])   the reading is stored twice (mirror)
FIELDS = {
    "reading": ("d", [F_READING, F_READING2]),  # the value shown on screen
    "temp1":   ("f", [F_TEMP1]),
    "temp2":   ("f", [F_TEMP2]),
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
    reading = struct.unpack_from("<d", buf, base + F_READING)[0]
    temp1 = struct.unpack_from("<f", buf, base + F_TEMP1)[0]
    temp2 = struct.unpack_from("<f", buf, base + F_TEMP2)[0]
    when = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return dict(base=base, ts=ts, when=when, counter=counter,
                reading=reading, temp1=temp1, temp2=temp2)


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
    # distinct readings actually seen on screen
    seen = {}
    for b in bases:
        r = round(struct.unpack_from("<d", buf, b + F_READING)[0], 6)
        seen[r] = seen.get(r, 0) + 1
    top = sorted(seen.items(), key=lambda kv: -kv[1])[:6]
    print("readings    : " + ", ".join(f"{v}×{c}" for v, c in top))


def cmd_list(args):
    buf = load(args.file)
    bases = find_records(buf)
    lo = args.start or 0
    hi = args.end if args.end is not None else len(bases)
    if args.csv:
        print("index,file_offset,timestamp,counter,reading,temp1,temp2")
    else:
        print(f"{'idx':>5} {'offset':>9} {'time':<19} {'cnt':>6} "
              f"{'reading':>10} {'temp1':>7} {'temp2':>7}")
    for idx in range(lo, min(hi, len(bases))):
        r = decode(buf, bases[idx])
        if args.csv:
            print(f"{idx},{r['base']:#08x},{r['when']},{r['counter']},"
                  f"{r['reading']:.6f},{r['temp1']:.4f},{r['temp2']:.4f}")
        else:
            print(f"{idx:5d} {r['base']:#09x} {r['when']:<19} {r['counter']:6d} "
                  f"{r['reading']:10.6f} {r['temp1']:7.2f} {r['temp2']:7.2f}")


def _resolve_indices(bases, spec):
    """spec: 'all' | '12' | '10-40'"""
    if spec == "all":
        return list(range(len(bases)))
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(spec)]


def apply_field(original, field, value, records_spec="all"):
    """Patch one field and guarantee nothing else changes.

    Returns dict(buf, indices, changed, ndiff, verify_ok). Raises ValueError on
    bad input, or PatchError if any byte outside the field would change.
    Used by both the CLI and the GUI so they behave identically.
    """
    if field not in FIELDS:
        raise ValueError(f"unknown field '{field}'; choose from {list(FIELDS)}")
    buf = bytearray(original)
    bases = find_records(buf)
    if not bases:
        raise ValueError("no records found in this file")
    fmt, offsets = FIELDS[field]
    packed = struct.pack("<" + fmt, float(value))
    indices = _resolve_indices(bases, records_spec)

    allowed = set()
    for idx in indices:
        if idx < 0 or idx >= len(bases):
            raise ValueError(f"record index {idx} out of range (0..{len(bases)-1})")
        for foff in offsets:
            allowed.update(range(bases[idx] + foff, bases[idx] + foff + len(packed)))

    for idx in indices:
        for foff in offsets:                 # reading is stored twice; write every copy
            pos = bases[idx] + foff
            buf[pos:pos + len(packed)] = packed

    outside = [i for i in range(len(buf)) if buf[i] != original[i] and i not in allowed]
    if outside:
        raise PatchError(f"{len(outside)} byte(s) would change outside the "
                         f"'{field}' field, e.g. {hex(outside[0])}")

    tol = 1e-4 if fmt == "f" else 1e-9
    verify_ok = all(
        abs(struct.unpack_from("<" + fmt, buf, bases[idx] + foff)[0] - float(value)) <= tol
        for idx in indices for foff in offsets)
    ndiff = sum(1 for i in range(len(buf)) if buf[i] != original[i])
    return dict(buf=buf, indices=indices, changed=len(indices),
                ndiff=ndiff, verify_ok=verify_ok)


class PatchError(Exception):
    pass


def cmd_set(args):
    original = load(args.file)
    try:
        res = apply_field(original, args.field, args.value, args.records)
    except (ValueError, PatchError) as e:
        sys.exit(f"ABORTED: {e}. Nothing written.")

    out = args.out or args.file
    with open(out, "wb") as f:
        f.write(res["buf"])
    print(f"patched {res['changed']} record(s): {args.field} = {args.value}")
    print(f"bytes changed  : {res['ndiff']} (all inside the {args.field} field)")
    print(f"other data     : untouched (0 bytes changed elsewhere)")
    print(f"written : {out}")
    print(f"verify  : {'OK' if res['verify_ok'] else 'FAILED'}")


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
