"""Binary seed file read by src/game/rando.c (format documented at the top of rando.c)."""

import struct
from dataclasses import dataclass, field

VERSION = 1
LEVELS = 20
ITEM_BYTES = 64
NAME_LEN = 40

KIND_RECORD, KIND_INVENTORY, KIND_CRADLEKEY, KIND_NEWKEY = 0, 1, 2, 3
MODE_PAD, MODE_GUARD, MODE_INSIDE, MODE_SAFE, MODE_START = 0, 1, 2, 3, 4
NO_LEVEL = 0xFF
NO_RECORD = 0xFFFF


@dataclass
class SeedItem:
    home: int            # SP level the item belongs to (NO_LEVEL for none)
    rectype: int         # PROPDEF type of the record it lives in
    homerec: int         # record index in the home level (NO_RECORD if none)
    model: int           # PROP model
    weaponnum: int       # ITEM id for collectables, -1 otherwise
    kind: int
    place: int           # SP level where it is hidden
    mode: int
    ref: int             # pad / guard id / container record index
    flags: int
    flags2: int
    name: str            # pickup message for copies the randomizer adds
    ammotype: int = 0    # ammo given on pickup (packs like Control's remote mines)
    ammo: int = 0
    keybit: int = 0      # KIND_NEWKEY: the door bit this key opens on its home level

    def pack(self):
        name = self.name.encode("ascii", "replace")[:NAME_LEN - 1].ljust(NAME_LEN, b"\0")
        return (struct.pack("<BBHhbBBBHII", self.home, self.rectype, self.homerec, self.model,
                            self.weaponnum, self.kind, self.place, self.mode, self.ref,
                            self.flags & 0xFFFFFFFF, self.flags2 & 0xFFFFFFFF)
                + name + struct.pack("<BBH", self.ammotype, self.keybit, self.ammo))


@dataclass
class Seed:
    seed: int
    difficulty: int                     # 0 Agent, 1 Secret Agent, 2 00 Agent
    bonus_levels: bool
    start_levels: list                  # SP levels
    show_handover: bool = False         # announce items handed over at level start
    glow_items: bool = True             # items still to find pulse gold
    carriers: str = "greyer"            # guards holding one: "greyer" or "same"
    bonus_parent: tuple = (NO_LEVEL, NO_LEVEL)
    start_pads: list = field(default_factory=lambda: [0] * LEVELS)
    items: list = field(default_factory=list)
    loadout: list = field(default_factory=list)   # (kind 0 weapon / 1 ammo, id, amount)
    topups: list = field(default_factory=list)    # (level, weapon, ammo type, minimum)
    locks: list = field(default_factory=list)     # new locks: (level, key bit, door record index)
    tags: list = field(default_factory=list)      # scripted handovers: (level, tag, item index)

    def pack(self):
        mask = 0
        for lvl in self.start_levels:
            mask |= 1 << lvl
        head = struct.pack("<4sHBBIIIBBHHH", b"GERS", VERSION, self.difficulty,
                           (1 if self.bonus_levels else 0) | (2 if self.show_handover else 0)
                           | (4 if self.glow_items else 0)
                           | (8 if self.carriers == "greyer" else 0),
                           self.seed & 0xFFFFFFFF, (self.seed >> 32) & 0xFFFFFFFF, mask,
                           self.bonus_parent[0], self.bonus_parent[1],
                           len(self.items), len(self.loadout), len(self.topups))
        head += struct.pack("<20H", *self.start_pads)
        assert len(head) == 68
        body = b"".join(it.pack() for it in self.items)
        assert all(len(it.pack()) == ITEM_BYTES for it in self.items)
        tail = b"".join(struct.pack("<BBH", k, i, n) for k, i, n in self.loadout)
        tail += b"".join(struct.pack("<BBBBH", lv, w, a, 0, n) for lv, w, a, n in self.topups)
        tail += struct.pack("<H", len(self.locks)) + b"".join(struct.pack("<BBH", lv, b, d) for lv, b, d in self.locks)
        tail += struct.pack("<H", len(self.tags)) + b"".join(struct.pack("<BBH", lv, t, i) for lv, t, i in self.tags)
        return head + body + tail
