"""World data: everything the generator needs from the level files, in one file.

    python -m randomizer.world        # rebuild randomizer/data/world.json

The generator reads only this file, so a shared copy of the randomizer needs
no decomp sources, and every player generates from identical data. It holds
record numbers, pad numbers and flags (no models, textures, audio or text from
the game), rebuilt from the catalog that `python -m randomizer.survey` writes.
"""

import hashlib
import json
import sys
from pathlib import Path

from . import levels, spots
from . import setupparse as sp
from .items import POOL

DATA = Path(__file__).resolve().parent / "data" / "world.json"
FORMAT = 2


def _resolve(cat, rec):
    matches = []
    for o in cat["objects"]:
        if o["type"] != rec.type:
            continue
        if rec.model and o.get("model") != rec.model:
            continue
        if rec.item and o.get("item") != rec.item:
            continue
        if rec.name and not any(rec.name in (n or "") for n in o.get("names", [o.get("name")])):
            continue
        matches.append(o)
    if rec.nth >= len(matches):
        raise ValueError(f"no record for {rec} in {cat['level']}")
    return matches[rec.nth]


# New locks (a setting): doors that are normally open get a lock and a new key.
# Only doors that are safe to lock: not already locked, not tagged (the level's
# scripts and objectives open, close or test tagged doors), player-operable,
# not lifts, and never on escort levels (an ally must not be locked out).
CANNOT_ACTIVATE = 0x02000000
NO_NEW_LOCKS = {"archives", "bunker2", "statue", "train", "jungle", "control", "cradle"}


def _lockable(cat):
    if cat["level"] in NO_NEW_LOCKS:
        return {"lock_doors": [], "free_key_bits": []}
    objs = cat["objects"]
    by_idx = {o["idx"]: o for o in objs}
    used = 0
    for o in objs:
        used |= o.get("key_mask", 0) | (o.get("lock_mask", 0) if o["type"] == "Door" else 0)
    doors = []
    for d in objs:
        if d["type"] != "Door" or d.get("lock_mask") or d.get("tags") or d.get("flags1", 0) & CANNOT_ACTIVATE \
                or d.get("pad") is None or not d.get("diffs") or "LIFT" in str(d.get("model")):
            continue
        rel = d.get("linked_door", 0)
        partner = d["idx"] + rel if rel and (d["idx"] + rel) in by_idx else None
        doors.append({"idx": d["idx"], "partner": partner, "diffs": d["diffs"]})
    return {"lock_doors": doors, "free_key_bits": [b for b in (1, 2, 4, 8, 16, 32, 64, 128) if not used & b]}


# Guards whose script hands Bond what they carry (by its tag): the item put
# there takes over the tag. Only confirmed handovers - other tags on carried
# items are checked by objectives and must stay on the original.
HANDOVERS = {"archives": {1}}   # Mishkin gives the safe key after his speech
# The same for items lying where a character stands, whose script hands them
# over: record index per level.
HANDOVER_RECORDS = {"facility": {376}}   # Dr. Doak gives the door decoder
HANDOVER_NOTES = {"facility": "handed over by Dr. Doak (the door decoder originally)"}


def _safes_and_tags(cat, pool_recs):
    """Safes whose contents are shuffled items (each a hiding spot that needs the
    safe's keys), and tags on items guards carry that the level's script hands
    over (Mishkin's safe key) - not objective targets, whose tags must stay."""
    objs = {o["idx"]: o for o in cat["objects"]}
    targets = {p.get("target") for ob in cat["objectives"] for p in ob["parts"]}
    safes = []
    for o in cat["objects"]:
        if o["type"] != "SafeItem" or o["item_obj"] not in pool_recs:
            continue
        lock = objs.get(o["safe_door"], {}).get("lock_mask", 0)
        needs = sorted(pool_recs[k["idx"]] for k in cat["objects"]
                       if k["type"] == "Key" and k.get("key_mask", 0) & lock and k["idx"] in pool_recs)
        item = objs[o["item_obj"]]
        safes.append({"link": o["idx"], "item_rec": o["item_obj"], "needs": needs, "diffs": item.get("diffs", [])})
    tags, rec_tags = {}, {}
    for o in cat["objects"]:
        if o["idx"] in HANDOVER_RECORDS.get(cat["level"], ()) and o.get("tags") and o["idx"] in pool_recs:
            rec_tags[str(o["idx"])] = o["tags"][0]
        if o.get("held_by_guard") in HANDOVERS.get(cat["level"], ()) and o.get("tags")                 and o["idx"] not in targets and o["idx"] in pool_recs:
            tags[str(o["held_by_guard"])] = o["tags"][0]
    return safes, tags, rec_tags


def build(root):
    base = Path(root) / "randomizer/build/catalog"
    cats = {lv.key: json.loads((base / f"{lv.key}.json").read_text()) for lv in levels.ALL}

    keep = ("idx", "type", "model", "item", "flags1", "flags2", "diffs", "pad", "held_by_guard", "inside")
    records = {}
    for it in POOL:
        if it.rec:
            rec = _resolve(cats[it.home], it.rec)
            records[it.key] = {k: rec[k] for k in keep if k in rec}

    lv_out = {}
    for lv in levels.ALL:
        cat = cats[lv.key]
        start = next((s["pad"] for s in cat["intro"]["spawns"] if s["set"] == 0), 0)
        pool_recs = {records[it.key]["idx"]: it.key for it in POOL if it.home == lv.key and it.key in records}
        safes, tags, rec_tags = _safes_and_tags(cat, pool_recs)
        bodies = {o["guard_id"]: o.get("body_name") for o in cat["objects"] if o["type"] == "Guard"}
        found = [dict(kind=s.kind, ref=s.ref, diffs=list(s.diffs), note=s.note) for s in spots.find_spots(cat)]
        for spot in found:
            if spot["kind"] == "guard" and str(spot["ref"]) in tags:
                spot["tag"] = tags[str(spot["ref"])]
        found += [dict(kind="safe", ref=s["link"], diffs=s["diffs"], note=f"inside the safe (link {s['link']})",
                       needs=s["needs"]) for s in safes]
        # a character who hands over an item (Dr. Doak) always has one to give
        by_idx = {o["idx"]: o for o in cat["objects"]}
        found += [dict(kind="pad", ref=by_idx[int(i)]["pad"], diffs=by_idx[int(i)]["diffs"], tag=t,
                       note=HANDOVER_NOTES.get(lv.key, "handed over by the level's script"))
                  for i, t in rec_tags.items()]
        lv_out[lv.key] = {
            "start_pad": start,
            "collect_targets": sorted({p["target"] for ob in cat["objectives"] for p in ob["parts"]
                                       if p["kind"] == "collect" and p.get("target") is not None}),
            "spots": found,
            "safes": safes,
            "guard_tags": tags,
            "record_tags": rec_tags,
            "unreliable_guards": sorted(g for g, b in bodies.items() if b in spots.NO_VANILLA_CARRIER),
            **_lockable(cat),
        }

    want_items = {it.weapon for it in POOL if it.weapon} | {r.get("item") for r in records.values()} \
        | {"ITEM_WPPK", "ITEM_WPPKSIL", "ITEM_MP5K", "ITEM_MP5KSIL", "ITEM_UZI", "ITEM_SKORPION", "ITEM_TT33",
           "ITEM_BUG", "ITEM_CAMERA", "ITEM_PLASTIQUE", "ITEM_REMOTEMINE", "ITEM_WATCHLASER",
           "ITEM_WATCHMAGNETATTRACT"}
    want_props = {it.model for it in POOL if it.model} | {r.get("model") for r in records.values()}
    items = {v: k for k, v in sp.parse_enum(Path(root), "ITEM_IDS").items()}
    props = {v: k for k, v in sp.parse_enum(Path(root), "PROP").items()}
    ammo = {v: k for k, v in sp.parse_enum(Path(root), "AMMOTYPE").items()}

    return {
        "format": FORMAT,
        "levels": lv_out,
        "records": records,
        "enums": {
            "items": {k: items[k] for k in sorted(x for x in want_items if x)},
            "props": {k: props[k] for k in sorted(x for x in want_props if x)},
            "ammo": {k: v for k, v in sorted(ammo.items())},
        },
    }


def load():
    if not DATA.exists():
        raise SystemExit(f"{DATA} is missing: run `python -m randomizer.world` in the repo first")
    return json.loads(DATA.read_text(encoding="utf-8"))


def fingerprint(world):
    """Short hash of the world data: part of the race code's version check."""
    blob = json.dumps(world, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:6]


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    world = build(root)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(world, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
    nspots = sum(len(v["spots"]) for v in world["levels"].values())
    print(f"wrote {DATA} ({nspots} spots, {len(world['records'])} item records, fingerprint {fingerprint(world)})")


if __name__ == "__main__":
    main()
