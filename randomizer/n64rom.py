"""N64 ROM for an EverDrive or an emulator: the randomizer's base ROM (the
original game built from the decomp with the randomizer compiled in, see
randomizer/n64/build_base.sh) plus a seed.

    python -m randomizer.n64rom --base ge007-rando-base.z64 --out run.z64 [settings]
    python -m randomizer.n64rom --base ... --out ... --race 11-e978-A3-4FNP1QRP

The ROM is padded to 16 MB. The seed goes at SEED_ROM; the game reads its own
developer token string at TOKEN_ROM (test ROMs use it to boot straight into a
level and to log to the IS-Viewer port; normal ROMs leave it empty). The
header asks for a 16K EEPROM ("ED" homebrew header): the game's own saves fill
the 4K chip it shipped with.
"""

import argparse
import hashlib
import sys
from pathlib import Path

from . import generate as gen, world as worlddata

ROM_SIZE = 0x1000000
SEED_ROM = 0xFF0000      # rando.c RANDO_SEED_ROM
TOKEN_ROM = 0xFFB000     # the game's tokenReadIo address
TOKEN_LEN = 160 * 4
OPT_GLOW_ITEMS = 0x04    # seed options byte (rando.c OPT_GLOW_ITEMS)
BASE_NAME = "ge007-rando-base.z64"


def find_base(root):
    """The base ROM where build_base.sh puts it, or next to the game's data."""
    for p in (root / "randomizer" / "n64" / "build" / BASE_NAME, root / "data" / BASE_NAME):
        if p.exists():
            return p
    return None


def cic6102_crc(rom):
    """The boot checksum pair the CIC-6102 checks (over 1 MB from 0x1000)."""
    m = 0xFFFFFFFF
    t1 = t2 = t3 = t4 = t5 = t6 = 0xF8CA4DDC
    for i in range(0x1000, 0x101000, 4):
        d = int.from_bytes(rom[i:i + 4], "big")
        if (t6 + d) & m < t6:
            t4 = (t4 + 1) & m
        t6 = (t6 + d) & m
        t3 ^= d
        r = ((d << (d & 0x1F)) | (d >> (32 - (d & 0x1F)))) & m if d & 0x1F else d
        t5 = (t5 + r) & m
        t2 = t2 ^ r if t2 > d else t2 ^ t6 ^ d
        t1 = (t1 + (t5 ^ d)) & m
    return t6 ^ t4 ^ t3, t5 ^ t2 ^ t1


def check(rom):
    """Problems with a finished ROM, as strings (empty = good)."""
    out = []
    if len(rom) != ROM_SIZE:
        out.append(f"size {len(rom):#x}, want {ROM_SIZE:#x}")
    if rom[:4] != b"\x80\x37\x12\x40":
        out.append("not a big-endian .z64")
    crc = cic6102_crc(rom)
    if (int.from_bytes(rom[0x10:0x14], "big"), int.from_bytes(rom[0x14:0x18], "big")) != crc:
        out.append("boot checksum wrong")
    if rom[0x3C:0x3E] != b"ED" or rom[0x3F] >> 4 != 2:
        out.append("header doesn't ask for a 16K EEPROM")
    if rom[SEED_ROM:SEED_ROM + 4] != b"GERS":
        out.append("no seed")
    return out


def patch(base, seed_blob, tokens=""):
    """Base ROM bytes + a packed seed -> the finished 16 MB ROM."""
    if base[:4] != b"\x80\x37\x12\x40":
        raise ValueError("base ROM must be big-endian (.z64)")
    if len(base) > SEED_ROM:
        raise ValueError(f"base ROM too big ({len(base):#x}): it would overlap the seed")
    if len(seed_blob) > TOKEN_ROM - SEED_ROM:
        raise ValueError(f"seed too big ({len(seed_blob)} bytes)")
    if len(tokens) >= TOKEN_LEN:
        raise ValueError("token string too long")
    seed_blob = bytearray(seed_blob)
    seed_blob[7] &= ~OPT_GLOW_ITEMS   # untested on the N64; cosmetic, placement unchanged
    rom = bytearray(base) + bytes(ROM_SIZE - len(base))
    rom[SEED_ROM:SEED_ROM + len(seed_blob)] = seed_blob
    rom[TOKEN_ROM:TOKEN_ROM + TOKEN_LEN] = tokens.encode("ascii").ljust(TOKEN_LEN, b"\0")
    rom[0x3C:0x3E] = b"ED"          # advanced homebrew header: game ID
    rom[0x3F] = 0x20                # save type 2 = 16K EEPROM
    crc1, crc2 = cic6102_crc(rom)   # unchanged (it covers 0x1000-0x101000), kept honest anyway
    rom[0x10:0x14] = crc1.to_bytes(4, "big")
    rom[0x14:0x18] = crc2.to_bytes(4, "big")
    bad = check(rom)
    if bad:
        raise ValueError("; ".join(bad))
    return bytes(rom)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="the randomizer base ROM (randomizer/n64/build_base.sh)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--race", help="race code (sets seed and settings)")
    ap.add_argument("--difficulty", choices=gen.DIFFS, default="agent")
    ap.add_argument("--no-bonus", action="store_true")
    ap.add_argument("--logic", choices=gen.logic.TIERS, default="advanced")
    ap.add_argument("--placement", choices=gen.PLACEMENTS, default="original")
    ap.add_argument("--goal", choices=gen.GOALS, default="codes")
    ap.add_argument("--new-locks", type=int, default=0)
    ap.add_argument("--spoiler", help="also write the spoiler log here")
    ap.add_argument("--tokens", default="", help=argparse.SUPPRESS)   # test ROMs: -level_NN -hardN -rlog
    a = ap.parse_args(argv)

    world = worlddata.load()
    if a.race:
        seed, settings = gen.parse_race_code(a.race, world)
    else:
        seed = a.seed if a.seed is not None else gen.new_seed()
        settings = gen.Settings(difficulty=a.difficulty, bonus=not a.no_bonus, tier=a.logic,
                                placement=a.placement, goal=a.goal, new_locks=a.new_locks,
                                containers=False, show_handover=False, glow_items=False)
    res = gen.generate(seed, settings, world)
    blob = gen.to_seedfile(res).pack()
    rom = patch(Path(a.base).read_bytes(), blob, a.tokens)
    Path(a.out).write_bytes(rom)
    if a.spoiler:
        Path(a.spoiler).write_text(gen.spoiler(res, gen.check_words(blob)), encoding="utf-8")
    print(f"{a.out}: race code {res['code']}, check words {gen.check_words(blob)}, "
          f"sha1 {hashlib.sha1(rom).hexdigest()[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
