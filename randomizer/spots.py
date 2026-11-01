"""Hiding spots per level.

Automatic candidates (v1), each provably reachable:
  dead ends  pads at the end of the guards' waypoint network: corners and the
             far ends of side rooms, never the middle of a route
  inside     destructible crates and boxes (the item drops when it breaks)
  guard      guards that already carry a key or objective item in vanilla, so
             they are known to drop what they hold (armed guards in general
             are not used yet: setup body ids don't identify named allies)

Hand-curated spots will be added from randomizer/data/spots/*.json; their
contents are deliberately not described anywhere a player would read.
"""

import math
from dataclasses import dataclass

from . import levels

INVINCIBLE = 0x00020000
IMMUNE_GUNFIRE = 0x00004000
CONTAINER_WORDS = ("CRATE", "BOX", "BARREL", "BIN")
MIN_START_DISTANCE = 600.0   # keep spots out of the spawn area

# Levels whose big outdoor areas are too vast to search (Rayan, 10-31): there,
# floor spots only count inside small rooms (huts, cabins, interiors). A room
# is the game's own unit: each level is cut into rooms, and outdoor ground into
# a few very large ones. On Surface the outdoor rooms span 1000-4400 units and
# the huts and interiors under 520, so anything spanning 800+ is open ground.
OPEN_AREA_LEVELS = {"surface1": 800, "surface2": 800}

# Vanilla carriers that still never get a shuffled item: Silo's Ourumov
# (escapes; dropping things is an advanced-only idea).
NO_VANILLA_CARRIER = {"BODY_Ourumov"}

# Characters that never carry a shuffled item (unless they already carry one
# in the original game): named characters, allies, scientists, civilians and
# Frigate's naval officers (the hostages).
NEVER_CARRY = {
    "BODY_Boris", "BODY_Ourumov", "BODY_Trevelyan_Janus", "BODY_Trevelyan_006", "BODY_Valentin_",
    "BODY_Baron_Samedi", "BODY_Jaws", "BODY_Mayday", "BODY_Oddjob", "BODY_Natalya_Skirt",
    "BODY_Natalya_Jungle_Fatigues", "BODY_Rosika", "BODY_Scientist_1_Male", "BODY_Scientist_2_Female",
    "BODY_Civilian_1_Female", "BODY_Civilian_2", "BODY_Civilian_3", "BODY_Civilian_4", "BODY_Naval_Officer",
    "BODY_Helicopter_Pilot", "BODY_Brosnan_Tuxedo", "BODY_Formal_Wear", "BODY_Unused_Female",
}


@dataclass(frozen=True)
class Spot:
    level: str
    kind: str        # "pad", "inside", "guard", "safe", "start"
    ref: int         # pad index / container record index / guard id / safe-link record index / start pad
    diffs: tuple
    note: str        # spoiler-log description
    needs: tuple = ()      # items needed to get at it beyond the level's gates (a safe's key)
    tag: int = -1          # the level's script hands over the object with this tag (Mishkin)
    reliable: bool = True  # False: the holder may never drop it (Ourumov) - filler only
    skip: tuple = ()       # level gate items this spot is not behind (original game order)

    @property
    def id(self):
        return f"{self.level}:{self.kind}:{self.ref}"


def _start_pos(cat):
    sp = next((s for s in cat["intro"]["spawns"] if s["set"] == 0), None)
    return sp["pos"] if sp else None


def find_spots(cat):
    level = cat["level"]
    start = _start_pos(cat)
    out = []

    # dead ends of the waypoint network
    open_span = OPEN_AREA_LEVELS.get(level)
    rooms = cat.get("rooms", {})
    for wp in cat["waypoints"]:
        if len(wp["neighbours"]) != 1:
            continue
        pad = wp["pad"]
        pos = cat["pads"][pad]["pos"] if pad < len(cat["pads"]) else None
        if pos is None or (start and math.dist(pos, start) < MIN_START_DISTANCE):
            continue
        room = cat["pads"][pad].get("room")
        if open_span and rooms.get(str(room), {}).get("span", 0) >= open_span:
            continue   # open ground on a vast map
        out.append(Spot(level, "pad", pad, ("agent", "secret", "00agent"), f"dead end at pad {pad} (room {room})"))

    by_idx = {o["idx"]: o for o in cat["objects"]}
    holders = {}
    for o in cat["objects"]:
        if o["type"] == "StandardProp" and any(w in str(o.get("model")) for w in CONTAINER_WORDS) \
                and not str(o.get("model")).startswith("PROP_CHR") \
                and not o.get("flags1", 0) & INVINCIBLE and not o.get("flags2", 0) & IMMUNE_GUNFIRE \
                and "pad" in o and o.get("diffs"):
            out.append(Spot(level, "inside", o["idx"], tuple(o["diffs"]), f"inside {o['model']} #{o['idx']}"))
        if "held_by_guard" in o and o["type"] in ("Key", "StandardProp") and o.get("diffs"):
            holders.setdefault(o["held_by_guard"], set()).update(o["diffs"])

    bodies = {o["guard_id"]: o.get("body_name") for o in cat["objects"] if o["type"] == "Guard"}
    for gid, diffs in holders.items():
        if bodies.get(gid) in NO_VANILLA_CARRIER:
            continue   # can't be relied on to drop anything (escapes, or story-protected)
        out.append(Spot(level, "guard", gid, tuple(sorted(diffs)), f"carried by guard {gid} (vanilla carrier)"))

    # any ordinary armed soldier, on the difficulties his gun exists on
    for o in cat["objects"]:
        if o["type"] != "Guard" or o["guard_id"] in holders or o.get("body_name") in NEVER_CARRY:
            continue
        diffs = tuple(o.get("armed_diffs", ()))
        if diffs:
            body = str(o.get("body_name", "")).replace("BODY_", "").replace("_", " ").lower()
            out.append(Spot(level, "guard", o["guard_id"], diffs, f"carried by guard {o['guard_id']} ({body})"))

    return out


def all_spots(catalogs, enabled):
    return [s for lv in levels.ALL if lv.key in enabled for s in find_spots(catalogs[lv.key])]
