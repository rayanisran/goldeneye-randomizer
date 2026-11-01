"""Level survey: turn the vanilla setups into a catalog the logic and placer build on.

    python -m randomizer.survey [--out randomizer/build/catalog]

Writes one JSON per level plus summary.json. The catalog is derived data
(regenerate it any time); nothing in it is a randomizer decision.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from . import levels
from . import setupparse as sp

DIFFS = ("agent", "secret", "00agent")
# PROPFLAG2 "don't load on Agent / Secret Agent / 00 Agent"
DIFF_EXCLUDE = (0x10, 0x20, 0x40)

ASSIGNEDTOCHR = 0x00004000
INSIDEANOTHEROBJ = 0x00008000
UNCOLLECTABLE = 0x00100000
LINKEDTOSAFE = 0x00000400

# Object record types that occupy a world position (32-word ObjectRecord header).
PLACED = {
    "Door", "StandardProp", "Key", "Alarm", "Cctv", "AmmoMag", "Collectable",
    "SingleMonitor", "MultiMonitor", "HangingMonitor", "Drone", "Hat", "AmmoBox",
    "Armour", "GasProp", "Glass", "TintedGlass", "Safe", "Vehicle", "Aircraft", "Tank",
}
CONTAINER_HINTS = ("CRATE", "BARREL", "BOX", "BIN", "CASE", "CABINET", "LOCKER")

# ObjectiveStart..ObjectiveEnd sub-records and the word holding their target
OBJECTIVE_PARTS = {
    "ObjectiveDestroyObject": ("destroy", 1),
    "ObjectiveCompleteCondition": ("complete_if", 1),
    "ObjectiveFailCondition": ("fail_if", 1),
    "ObjectiveCollectObject": ("collect", 1),
    "ObjectiveDepositObject": ("deposit", 1),
    "ObjectivePhotograph": ("photograph", 1),
    "ObjectiveEnterRoom": ("enter_room_pad", 1),
    "ObjectiveDepositObjectInRoom": ("deposit_in_room", 1),
    "ObjectiveCopy_Item": ("copy_item", None),
}


def _diffs(flags2):
    return [d for d, bit in zip(DIFFS, DIFF_EXCLUDE) if not flags2 & bit]


def survey_level(root, lv, enums, banks):
    data = sp.parse_setup(sp.setup_path(root, lv.setup))
    items, props, ammo = enums["ITEM_IDS"], enums["PROP"], enums["AMMOTYPE"]
    recs = data["objects"]
    pads, pads3d = data["pads"], data["pads3d"]

    # Rooms: the game splits every level into rooms (indoor rooms, and large
    # outdoor areas cut into a few big ones). A pad's floor tile names its room.
    tile_room = sp.load_tile_rooms(root, lv.bg) if lv.bg else {}
    rooms = {}
    for p in pads:
        m = re.match(r"p(\d+)", p["tile"])
        p["room"] = tile_room.get(int(m.group(1))) if m else None
        if p["room"] is not None:
            b = rooms.setdefault(p["room"], [1e9, -1e9, 1e9, -1e9, 0])
            x, _, z = p["pos"]
            b[0], b[1], b[2], b[3], b[4] = min(b[0], x), max(b[1], x), min(b[2], z), max(b[3], z), b[4] + 1
    rooms = {r: {"span": max(b[1] - b[0], b[3] - b[2]), "pads": b[4]} for r, b in rooms.items()}

    def pad_pos(p):
        if p is None:
            return None
        if p >= 10000:
            q = p - 10000
            return pads3d[q]["pos"] if q < len(pads3d) else None
        return pads[p]["pos"] if 0 <= p < len(pads) else None

    objs, tags, guards = [], {}, {}
    for i, (typ, idx, w) in enumerate(recs):
        o = {"idx": idx, "type": typ}
        if typ in PLACED and len(w) >= 32:
            model, pad, rel = w[1] >> 16, w[1] & 0xFFFF, sp.s16(w[1])
            flags1, flags2 = w[2], w[3]
            o.update(model=props.get(model, model), flags1=flags1, flags2=flags2,
                     diffs=_diffs(flags2))
            if flags1 & ASSIGNEDTOCHR:
                o["held_by_guard"] = pad
            elif flags1 & INSIDEANOTHEROBJ:
                o["inside"] = idx + rel
            else:
                o["pad"] = pad
                o["pos"] = pad_pos(pad)
            if flags1 & UNCOLLECTABLE:
                o["uncollectable"] = True
            if typ == "Key":
                o["key_mask"] = w[32]
            elif typ == "Door":
                o["linked_door"] = sp.s32(w[32])
                o["lock_mask"] = w[39] & 0xFF
            elif typ == "Collectable":
                o["item"] = items.get((w[32] >> 24) & 0xFF)
            elif typ == "AmmoMag":
                o["ammo"] = ammo.get(w[32], w[32])
            elif typ == "AmmoBox":
                # 13 slots of [u16 model][u16 quantity]; slot k holds ammo type k + 1
                o["ammo"] = {ammo.get(k + 1, k + 1): n & 0xFFFF for k, n in enumerate(w[32:45]) if n & 0xFFFF}
            elif typ == "Armour":
                o["armour"] = w[32]
            if any(h in str(o["model"]) for h in CONTAINER_HINTS):
                o["container_like"] = True
        elif typ == "Guard":
            gid, gpad = w[1] >> 16, w[1] & 0xFFFF
            o.update(guard_id=gid, pad=gpad, pos=pad_pos(gpad), body=w[2] >> 16,
                     body_name=enums["BODIES"].get(w[2] >> 16), ai_list=w[2] & 0xFFFF, health=w[4] & 0xFFFF)
            guards[gid] = o
        elif typ == "Tag":
            tag_id, off = w[1] >> 16, sp.s16(w[1])
            tags[tag_id] = idx + off
            o.update(tag=tag_id, target=idx + off)
        elif typ == "Rename":
            o.update(target=idx + sp.s32(w[1]), item_slot=w[2],
                     names=[sp.text(banks, t) for t in w[3:8]])
        elif typ == "LockDoor":
            o.update(door=idx + sp.s32(w[1]), lock=idx + sp.s32(w[2]))
        elif typ == "SafeItem":
            o.update(item_obj=idx + sp.s32(w[1]), safe=idx + sp.s32(w[2]), safe_door=idx + sp.s32(w[3]))
        elif typ in ("LinkItems", "LinkProps"):
            o.update(a=idx + sp.s32(w[1]), b=idx + sp.s32(w[2]))
        elif typ == "SetGuardAttribute":
            o.update(guard_id=w[1], attribute=w[2])
        elif typ in ("ObjectiveStart", "WatchMenuObjectiveText"):
            o["words"] = w[1:]
        elif typ in OBJECTIVE_PARTS:
            o["words"] = w[1:]
        objs.append(o)

    by_idx = {o["idx"]: o for o in objs}
    for o in objs:
        if o["type"] == "Rename" and o["target"] in by_idx:
            by_idx[o["target"]]["name"] = next((n for n in o["names"][::-1] if n), None)
            by_idx[o["target"]]["names"] = o["names"]
    for tag_id, target in tags.items():
        if target in by_idx:
            by_idx[target].setdefault("tags", []).append(tag_id)
    for o in objs:
        gid = o.get("held_by_guard")
        if gid is not None and gid in guards:
            guards[gid].setdefault("carries", []).append(o["idx"])
            if o["type"] == "Collectable":   # a guard exists on the difficulties his gun is placed
                guards[gid]["armed_diffs"] = sorted(set(guards[gid].get("armed_diffs", [])) | set(o.get("diffs", [])))

    # Objectives: ObjectiveStart(num, text, mindiff) ... ObjectiveEnd
    objectives, cur = [], None
    for o in objs:
        if o["type"] == "ObjectiveStart":
            num, tid, mindiff = o["words"][:3]
            cur = {"num": num, "text": sp.text(banks, tid), "min_difficulty": mindiff,
                   "difficulties": list(DIFFS[mindiff:]), "parts": []}
            objectives.append(cur)
        elif o["type"] == "ObjectiveEnd":
            cur = None
        elif cur is not None and o["type"] in OBJECTIVE_PARTS:
            kind, wi = OBJECTIVE_PARTS[o["type"]]
            part = {"kind": kind}
            if wi is not None and o["words"]:
                val = o["words"][wi - 1]
                part["arg"] = val
                if kind in ("destroy", "collect", "deposit", "photograph", "deposit_in_room"):
                    target = tags.get(val)
                    part["target"] = target
                    t = by_idx.get(target, {})
                    part["target_desc"] = t.get("name") or t.get("item") or t.get("model")
            cur["parts"].append(part)

    intro = {"spawns": [], "start_weapons": [], "start_ammo": []}
    for typ, idx, w in data["intro"]:
        if typ == "Spawn":
            intro["spawns"].append({"pad": w[1], "set": w[2], "pos": pad_pos(w[1])})
        elif typ == "StartWeapon":
            intro["start_weapons"].append({"right": items.get(w[1]), "left": items.get(sp.s32(w[2])),
                                           "set": w[3]})
        elif typ == "StartAmmo":
            intro["start_ammo"].append({"ammo": ammo.get(w[1], w[1]), "qty": w[2], "set": w[3]})

    ai_refs = {aid: [ln for ln in lines if any(k in ln for k in (
        "item", "objective", "give", "drop", "gadget", "object_move_to_pad", "spawning_item"))]
        for aid, lines in data["ai"].items()}

    return {
        "level": lv.key, "name": lv.name, "bonus": lv.bonus,
        "counts": {"pads": len(pads), "pads3d": len(pads3d), "waypoints": len(data["waypoints"]),
                   "objects": len(objs), "guards": len(guards), "ai_lists": len(data["ai"])},
        "objectives": objectives,
        "intro": intro,
        "objects": objs,
        "waypoints": data["waypoints"],
        "waygroups": data["waygroups"],
        "pads": pads,
        "pads3d": pads3d,
        "rooms": {str(r): v for r, v in rooms.items()},
        "ai_item_refs": {k: v for k, v in ai_refs.items() if v},
    }


def load_enums(root):
    return {name: sp.parse_enum(root, name) for name in ("ITEM_IDS", "PROP", "AMMOTYPE", "BODIES")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repo root")
    ap.add_argument("--out", default="randomizer/build/catalog")
    args = ap.parse_args(argv)
    root, out = Path(args.root), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    enums, banks = load_enums(root), sp.load_textbanks(root)

    summary = {}
    for lv in levels.ALL:
        cat = survey_level(root, lv, enums, banks)
        (out / f"{lv.key}.json").write_text(json.dumps(cat, indent=1), encoding="utf-8", newline="\n")
        kinds = Counter(o["type"] for o in cat["objects"])
        summary[lv.key] = {"counts": cat["counts"], "object_types": dict(kinds),
                           "objectives": [(o["num"], o["text"], o["difficulties"]) for o in cat["objectives"]]}
        print(f"{lv.name:10} pads {cat['counts']['pads']:4}  objects {cat['counts']['objects']:4}  "
              f"guards {cat['counts']['guards']:3}  objectives {len(cat['objectives'])}")
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
