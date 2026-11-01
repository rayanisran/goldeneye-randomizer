"""Generate a seed.

    python -m randomizer.generate [--seed N] [--difficulty agent|secret|00agent]
                                  [--no-bonus] [--logic easy|normal|advanced] [--containers] [--show-handover]
                                  [--race CODE] [--out data/rando]

Writes <out>/seed.bin (read by the game) and <out>/spoiler-<code>.txt (only
for when you're stuck). Every seed is played through on paper before it is
written: the run must be able to beat every level and Cradle from nothing.

Placement is an "assumed fill": progression items are placed one at a time,
each only where it could be reached while assuming every item still unplaced
is already owned. That makes circular locks impossible by construction.

Races: a race code (e.g. 1-52da-A1-2F4KXQ9) holds the generator version, the
world-data fingerprint, the settings and the seed. The same code gives the
same game on every machine (randomizer/rng.py, not Python's `random`); a code
from a different randomizer version is refused rather than quietly differing.
"""

import argparse
import dataclasses
import collections
import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path

from . import levels, logic, seedfile, world as worlddata
from .items import CODE_WORD, POOL, Item
from .spots import Spot
from .rng import SeedRNG

CARRIERS = ("greyer", "same")    # race-code order: index 0 is the default
CARRIER_LABELS = {"greyer": "Slightly greyer", "same": "Look the same"}
PLACEMENTS = ("anywhere", "original")   # race-code bit 11
PLACEMENT_LABELS = {"anywhere": "Anywhere (hiding spots, any soldier)",
                    "original": "Original locations only"}
GOALS = ("codes", "all")                 # race-code bit 12
GOAL_LABELS = {"codes": f"Satellite codes ({CODE_WORD} + GoldenEye Key opens Cradle)",
               "all": "Beat every level (+ GoldenEye Key opens Cradle)"}
LOGIC_VERSION = 11             # bump whenever generation can change for the same code
DIFFS = ("agent", "secret", "00agent")
DIFF_CHARS = "ASO"
ORIGINAL_SAME_LEVEL_WEIGHT = 0.04   # the same target there: few spots per level, so lower
SAME_LEVEL_WEIGHT = 0.3        # ~1-3% of items land on their own level
MIN_SPHERES = 4                # balance: progression has to unfold in steps
MIN_LEVELS = 10                # satellite-code goal: a seed has you visit at least this many levels
LETTER_CROWD = 0.35            # each code letter already in a level makes another there this much likelier
START_LEVELS = 3
LIGHT_WEAPONS = ["ITEM_MP5K", "ITEM_MP5KSIL", "ITEM_UZI", "ITEM_SKORPION", "ITEM_TT33"]
MAG = {"ITEM_WPPK": 7, "ITEM_WPPKSIL": 7, "ITEM_TT33": 8, "ITEM_SKORPION": 20, "ITEM_UZI": 32,
       "ITEM_MP5K": 30, "ITEM_MP5KSIL": 30}
SP = {lv.key: i for i, lv in enumerate(levels.ALL)}
CHAIN = [lv.key for lv in levels.CHAIN]
CHECK_WORDS = ["Bond", "Natalya", "Boris", "Ourumov", "Xenia", "Jaws", "Mayday", "Oddjob", "Baron", "Trevelyan",
               "Valentin", "Mishkin", "Doak", "Q", "Klobb", "ZMG", "KF7", "D5K", "RCP90", "Moonraker",
               "Magnum", "Laser", "Grenade", "Plastique", "Decoder", "Keycard", "Satellite", "Tank",
               "Train", "Dam", "Bunker", "Cradle"]


class GenerationError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    difficulty: str = "agent"
    bonus: bool = True
    tier: str = "normal"          # logic tier: easy / normal / advanced (logic.TIERS)
    containers: bool = False
    show_handover: bool = False
    new_locks: int = 0              # extra locked doors, each with a new key (0-10)
    glow_items: bool = True         # items still to find pulse gold and show from afar
    carriers: str = "greyer"        # guards holding one: drawn slightly "greyer", or the "same"
    placement: str = "anywhere"     # "original": items only where the original game has one
    goal: str = "codes"             # "codes": the code letters and the GoldenEye Key open Cradle

    def flags(self):
        # glow stored inverted and carriers as an index with "greyer" = 0, so
        # codes from before these settings read as the defaults
        return (1 if self.bonus else 0) | (logic.TIERS.index(self.tier) << 1) | \
               (8 if self.containers else 0) | (16 if self.show_handover else 0) | (self.new_locks << 5) | \
               (0 if self.glow_items else 512) | (CARRIERS.index(self.carriers) << 10) | \
               (PLACEMENTS.index(self.placement) << 11) | (GOALS.index(self.goal) << 12)


# ------------------------------------------------------------------ race codes

def _b36(n):
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if n == 0:
            return out


def version_tag(world):
    return f"{LOGIC_VERSION}-{worlddata.fingerprint(world)[:4]}"


def race_code(seed, settings, world):
    return f"{version_tag(world)}-{DIFF_CHARS[DIFFS.index(settings.difficulty)]}{settings.flags():X}-{_b36(seed)}"


def parse_race_code(code, world):
    parts = code.strip().upper().split("-")
    if len(parts) != 4:
        raise ValueError("a race code looks like 1-52DA-A1-2F4KXQ9")
    tag = f"{parts[0]}-{parts[1]}"
    if tag.lower() != version_tag(world).lower():
        raise ValueError(f"this code is for randomizer version {tag}, this copy is {version_tag(world).upper()}: "
                         "both racers need the same version")
    d, flags = parts[2][0], int(parts[2][1:] or "0", 16)
    settings = Settings(difficulty=DIFFS[DIFF_CHARS.index(d)], bonus=bool(flags & 1),
                        tier=logic.TIERS[(flags >> 1) & 3], containers=bool(flags & 8),
                        show_handover=bool(flags & 16), new_locks=(flags >> 5) & 15,
                        glow_items=not flags & 512, carriers=CARRIERS[(flags >> 10) & 1], placement=PLACEMENTS[(flags >> 11) & 1],
                        goal=GOALS[(flags >> 12) & 1])
    return int(parts[3], 36), settings


def run_id(code):
    """64-bit id the game keys its save and log by (unique per code)."""
    return int(hashlib.sha256(code.upper().encode()).hexdigest()[:16], 16)


def check_words(seed_bytes):
    h = hashlib.sha256(seed_bytes).digest()
    return " ".join(CHECK_WORDS[b % len(CHECK_WORDS)] for b in h[:4])


# ------------------------------------------------------------------ logic

class World:
    def __init__(self, diff, enabled, tier, start, bonus_parent, tricks=None, extra_gates=None, goal="codes"):
        self.diff, self.enabled, self.tier, self.goal = diff, enabled, tier, goal
        self.start, self.bonus_parent = set(start), bonus_parent
        self.nobeat = frozenset()        # levels_to_visit: levels the player is assumed never to beat
        self.req = {lv: logic.requirements(lv, diff, tier, tricks) for lv in enabled}
        self.gates = {lv: logic.gates(lv, diff, tier, tricks) for lv in enabled}
        for lv, keys in (extra_gates or {}).items():   # new locks: their key opens the level
            self.req[lv] |= keys
            self.gates[lv] |= keys

    def progress(self, caps):
        """Levels unlocked and beaten with capabilities `caps`."""
        beaten = set()
        while True:
            unlocked = self.unlocked(beaten, caps)
            new = {lv for lv in unlocked - beaten - self.nobeat if logic.satisfied(self.req[lv], caps)}
            if not new:
                return unlocked, beaten
            beaten |= new

    def unlocked(self, beaten, caps):
        out = set(self.start)
        for lv in beaten:
            if lv in CHAIN and lv != "caverns" and lv != "cradle":
                out.add(CHAIN[CHAIN.index(lv) + 1])
        for bonus, parent in self.bonus_parent.items():
            if parent in beaten:
                out.add(bonus)
        out |= {lv for lv in self.enabled if f"clear_{lv}" in caps}   # a clearance opens its level too
        if self.goal == "codes":
            opens = all(f"letter_{c.lower()}" in caps for c in CODE_WORD)
        else:
            opens = all(lv in beaten for lv in self.enabled if lv != "cradle")
        if opens and "goldeneye_key" in caps:
            out.add("cradle")
        return out & set(self.enabled)

    def levels_to_visit(self, placement, prog_keys):
        """The fewest levels a player could get by with: every needed item the
        win can do without and every level it needn't beat dropped, one at a
        time; then the levels holding what's left, those still beaten, and Cradle."""
        def wins(p):
            return "cradle" in self.sweep(set(), p)[1]

        need = {s: it for s, it in placement.items() if it.key in prog_keys}
        for spot, it in sorted(need.items(), key=lambda kv: kv[1].key):
            trial = {k: v for k, v in need.items() if k != spot}
            if wins(trial):
                need = trial
        for lv in sorted(self.enabled):
            self.nobeat = self.nobeat | {lv}
            if lv == "cradle" or not wins(need):
                self.nobeat = self.nobeat - {lv}
        beaten = self.sweep(set(), need)[1]
        self.nobeat = frozenset()
        return {s.level for s in need} | beaten | {"cradle"}

    def reachable(self, spot, caps, unlocked):
        gates = self.gates[spot.level]
        if spot.skip:
            gates = {g for g in gates if g not in spot.skip}
        return spot.level in unlocked and logic.satisfied(gates, caps) and logic.satisfied(spot.needs, caps)

    def sweep(self, start_caps, placement):
        """Collect everything reachable. Returns caps, beaten, spheres (item keys per step)."""
        caps, got, spheres = set(start_caps), set(), []
        while True:
            unlocked, beaten = self.progress(caps)
            step = [it for spot, it in placement.items()
                    if it.key not in got and self.reachable(spot, caps, unlocked)]
            if not step:
                return caps, beaten, spheres
            spheres.append([it.key for it in step])
            for it in step:
                got.add(it.key)
                caps |= set(it.capabilities())


# ------------------------------------------------------------------ generation

def pick_start(rng, enabled):
    bonus = [b for b in ("aztec", "egyptian") if b in enabled]
    parents = {b: rng.choice([lv for lv in CHAIN if lv != "cradle"]) for b in bonus}

    def neighbours(a, b):
        if a in CHAIN and b in CHAIN:
            return abs(CHAIN.index(a) - CHAIN.index(b)) == 1
        if a in parents and parents[a] == b or b in parents and parents[b] == a:
            return True
        return a in bonus and b in bonus

    # any level can be one: clearances open the rest (Dam no longer has to be,
    # with nothing before it in the chain)
    pool = [lv for lv in enabled if lv != "cradle"]
    for _ in range(1000):
        pick = rng.sample(pool, START_LEVELS)
        if not any(neighbours(a, b) for i, a in enumerate(pick) for b in pick[i + 1:]):
            return pick, parents
    raise GenerationError("no valid start levels")


def allowed(item, spot, homes, own=None, prog_keys=None):
    """own: item key -> its original spot (never placed back there)."""
    if item.key in spot.needs:
        return False   # never behind itself (a safe's own key inside it)
    if item.clearance == spot.level:
        return False   # a level's clearance inside it could never open it
    if spot.kind in ("guard", "safe") and not can_guard(item):
        return False   # guards would wield a gadget as a gun
    if spot.level == "cradle" and item.progression:
        return False
    if not spot.reliable and (item.key in prog_keys if prog_keys is not None else item.progression):
        return False   # this holder may never drop it
    if own and own.get(item.key) == spot and spot.reliable:
        return False   # (Ourumov may keep his own never-needed master keycard)
    if own is not None:
        return True    # original locations: `own` is the whole own-spot rule
    home = homes.get(item.key)
    if home and home["level"] == spot.level:
        # never the item's own original position
        if spot.kind == "pad" and home.get("pad") == spot.ref:
            return False
        if spot.kind == "guard" and home.get("held_by_guard") == spot.ref:
            return False
        if spot.kind == "inside" and home.get("inside") == spot.ref:
            return False
    return True


# Share of a level's chances per kind of spot (renormalised over the kinds the
# level has): floor spots most of the time, guards for a fair share (any
# ordinary soldier can carry), crates only when that setting is on.
KIND_SHARE = {"pad": 0.6, "guard": 0.3, "inside": 0.1, "safe": 0.1, "start": 0.1}


def can_guard(item):
    return bool(item.rec and item.rec.type in ("Key", "StandardProp"))


def weight(item, spot, per_level):
    if per_level is None:                # original locations: every spot alike, except
        w = 1.0                          # keys lean toward guards: guns and gadgets can't go there
        if spot.kind == "guard" or not can_guard(item):
            w = 4.0 if spot.kind == "guard" else 1.0
        return w * ORIGINAL_SAME_LEVEL_WEIGHT if spot.level == item.home else w
    kinds = per_level[spot.level]
    share = KIND_SHARE[spot.kind] / sum(KIND_SHARE[k] for k in kinds)
    w = share / kinds[spot.kind]
    return w * SAME_LEVEL_WEIGHT if spot.level == item.home else w


def generate(seed, settings, world=None):
    world = world or worlddata.load()
    diff, tier = settings.difficulty, settings.tier
    rng = SeedRNG(seed)
    tricks = logic.pick_tricks(rng, settings.tier)   # tricks this seed's logic may rely on
    enabled = [lv.key for lv in levels.CHAIN] + (["aztec", "egyptian"] if settings.bonus else [])

    homes, pool = {}, []
    for it in POOL:
        if it.home and it.home not in enabled or it.letter >= 0 and settings.goal != "codes":
            continue
        if it.rec:
            rec = world["records"][it.key]
            if diff not in rec.get("diffs", DIFFS):
                continue
            homes[it.key] = dict(rec, level=it.home)
        pool.append(it)
    for it, rec in pickup_items(world, enabled, diff):
        homes[it.key] = dict(rec, level=it.home)
        pool.append(it)

    locks, lock_items = pick_new_locks(rng, settings, enabled, world)
    pool += lock_items
    extra_gates = {}
    for it in lock_items:
        extra_gates.setdefault(it.home, set()).add(it.key)
    needed = logic.required_capabilities(diff, enabled, tier, tricks) | {"goldeneye_key"} \
        | {it.key for it in lock_items} | {it.key for it in pool if it.clearance or it.letter >= 0}
    prog = [it for it in pool if set(it.capabilities()) & needed]
    prog_keys = {it.key for it in prog}
    filler = [it for it in pool if it not in prog]
    for cap in sorted(needed):
        if not any(cap in it.capabilities() for it in pool):
            raise GenerationError(f"nothing provides {cap}")

    own = None
    if settings.placement == "original":
        all_spots, own = original_spots(pool, homes, world, diff, enabled)
        per_level = None
    else:
        # items inside crates and barrels are a setting: shooting every box gets old
        all_spots = [spot_from(lv, s, world) for lv in enabled for s in world["levels"][lv]["spots"]
                     if diff in s["diffs"] and (settings.containers or s["kind"] != "inside")]
        per_level = {}                       # level -> {kind: spot count}
        for s in all_spots:
            kinds = per_level.setdefault(s.level, {})
            kinds[s.kind] = kinds.get(s.kind, 0) + 1

    for attempt in range(2000 if settings.placement == "original" else 500):
        start, parents = pick_start(rng, enabled)
        state = World(diff, enabled, tier, start, parents, tricks, extra_gates, settings.goal)
        placement = {}
        order = [it for it in prog if it.clearance not in start]   # levels open from the start need none
        rng.shuffle(order)
        if per_level is None:
            # original locations: items that leave the fewest spots open while
            # missing go first (pop() takes from the end), while room is left
            def room_without(item):
                caps = set().union(*(set(o.capabilities()) for o in prog if o is not item))
                caps, _, _ = state.sweep(caps, {})
                opened, _ = state.progress(caps)
                return sum(1 for s in all_spots if state.reachable(s, caps, opened))
            order.sort(key=room_without, reverse=True)
        # the goal's items (code letters, the GoldenEye Key) go first, while the
        # whole game is open to them: placed last, they piled up in the start
        # levels (all five letters in one level in 1 seed of 200)
        order.sort(key=lambda it: it.letter >= 0 or it.cradle_key)
        letters_in = collections.Counter()
        # original locations: spots open from the very start are scarce (one per
        # item), so items placed early in the fill (those needed late) spare them
        opening = set()
        if per_level is None:
            caps0, _, _ = state.sweep(set(), {})
            open0, _ = state.progress(caps0)
            opening = {s for s in all_spots if state.reachable(s, caps0, open0)}
        try:
            while order:
                item = order.pop()
                assumed = set().union(*(set(o.capabilities()) for o in order)) if order else set()
                caps, _, _ = state.sweep(assumed, placement)
                unlocked, _ = state.progress(caps)
                free = [s for s in all_spots if s not in placement and allowed(item, s, homes, own, prog_keys)
                        and state.reachable(s, caps, unlocked)]
                if not free:
                    raise GenerationError(f"no room for {item.key}")
                spot = rng.weighted(free, [weight(item, s, per_level) * (0.1 if s in opening else 1.0)
                                           * (LETTER_CROWD ** letters_in[s.level] if item.letter >= 0 else 1.0)
                                           for s in free])
                placement[spot] = item
                if item.letter >= 0:
                    letters_in[spot.level] += 1
        except GenerationError as e:
            FAILS[str(e)] += 1
            continue

        caps, beaten, spheres = state.sweep(set(), placement)
        if set(enabled) - beaten:
            FAILS["unbeatable"] += 1
            continue                      # cannot happen with assumed fill; belt and braces
        if len(spheres) < MIN_SPHERES:
            FAILS["too flat"] += 1
            continue                      # too flat: most of the run open from the start

        rest = [s for s in all_spots if s not in placement]
        rng.shuffle(filler)
        if per_level is None:
            # original locations: as many items as the original game has places.
            # Keys and documents first, onto guards and into safes while they
            # last; then gadgets and weapons; then body armor and floor guns,
            # the ones left out when the places run out.
            filler.sort(key=lambda it: (not can_guard(it), it.pickup is not None))
        else:
            filler.sort(key=can_guard)   # guns and gadgets first: they can't go to guards
        unplaced, left_out = 0, []
        filler_keys = {it.key for it in filler}
        for item in filler:
            free = [s for s in rest if allowed(item, s, homes, own, prog_keys)]
            if per_level is None and can_guard(item):
                free = [s for s in free if s.kind == "safe" or s.tag >= 0] \
                    or [s for s in free if s.kind == "guard"] or free
            if not free and swap_in(rng, item, placement, rest, homes, own, filler_keys, prog_keys):
                continue
            if not free:
                if per_level is None:
                    left_out.append(item)
                else:
                    unplaced += 1
                continue
            spot = rng.weighted(free, [weight(item, s, per_level) for s in free])
            placement[spot] = item
            rest.remove(spot)
        if unplaced:
            FAILS["filler unplaced"] += 1
            continue                      # anywhere: every item has a place
        fill_safes(rng, placement, all_spots, homes, filler_keys, prog_keys, state, enabled)
        if per_level is None:
            # what moved into a safe left its own place free: a spare one takes it
            for s in [s for s in all_spots if s not in placement]:
                fits = [it for it in left_out if allowed(it, s, homes, own, prog_keys)]
                if fits:
                    it = rng.choice(fits)
                    placement[s] = it
                    left_out.remove(it)
        _, _, collected = state.sweep(set(), placement)
        if sum(len(step) for step in collected) < len(placement):
            FAILS["unreachable item"] += 1
            continue                      # every item collectable, spare ones too (no key locked in a safe it opens)
        if settings.goal == "codes" and len(state.levels_to_visit(placement, prog_keys)) < MIN_LEVELS:
            FAILS["too short"] += 1
            continue                      # Cradle reachable after too few levels

        code = race_code(seed, settings, world)
        return dict(seed=seed, code=code, settings=settings, start=start, parents=parents, tricks=tricks,
                    locks=locks, extra_gates=extra_gates,
                    placement=placement, left_out=left_out, spheres=spheres, homes=homes, world=world,
                    enabled=enabled,
                    loadout=pick_loadout(rng), attempts=attempt + 1)

    raise GenerationError("could not build a balanced seed")


FAILS = collections.Counter()   # why generation attempts were thrown away (diagnostics)


def spot_from(lv, s, world):
    unreliable = set(world["levels"][lv].get("unreliable_guards", []))
    return Spot(lv, s["kind"], s["ref"], tuple(s["diffs"]), s["note"], tuple(s.get("needs", ())),
                s.get("tag", -1), not (s["kind"] == "guard" and s["ref"] in unreliable))


# Original locations: which of its own level's items each original spot is
# behind, from the original game. Spots not listed are behind
# all the level's gate items (safe, but on Easy logic that leaves too few
# spots open early); things handed over at the start are behind nothing.
VANILLA_NEEDS = {
    # an officer in a hut drops the large key; it opens the hut with the safe
    # key, which opens the hut with the plans' safe
    "surface1": {"surface1_large_key": [], "surface1_safe_key": ["surface1_large_key"],
                 "surface1_plans": ["surface1_large_key", "surface1_safe_key"]},
    # keycard A first, then the decoder; B isn't needed (treated as after A)
    "facility": {"facility_keycard_a": [], "facility_decoder": ["facility_keycard_a"],
                 "facility_keycard_b": ["facility_keycard_a"]},
    # two patrolling guards carry the keycards: either can come first
    "bunker1": {"bunker1_keycard_security": [], "bunker1_keycard_computer": []},
    # out of Bond's cell, the order doesn't matter (the safe still needs both keys)
    "bunker2": {"*": ["magnet_watch"]},
    # code card C first; then A and B in either order (treated as after C)
    "caverns": {"caverns_code_card_3": [], "caverns_code_card_1": ["caverns_code_card_3"],
                "caverns_code_card_2": ["caverns_code_card_3"]},
    # each main-floor room's keycard opens its exit and the next room's entry
    "silo": {"silo_keycard_1": [], "silo_keycard_2": ["silo_keycard_1"],
             "silo_keycard_3": ["silo_keycard_1", "silo_keycard_2"]},
}


def skip_for(level, item_key, kind, level_items):
    """Gate items of the level this original spot is not behind."""
    if kind == "start":
        return tuple(sorted(level_items))
    table = VANILLA_NEEDS.get(level, {})
    needs = table.get(item_key, table.get("*"))
    return () if needs is None else tuple(sorted(set(level_items) - set(needs)))


def original_spots(pool, homes, world, diff, enabled):
    """Original-locations mode: every shuffled item's place in the original game
    (on the floor, on its guard, in its crate or safe, or handed over when the
    level starts like Q's gadgets) becomes a spot, so items swap places and no
    one carries anything they didn't before. Items the original game doesn't
    have (clearances, code letters, the GoldenEye Key, new-lock keys) take
    those places too, and the spare items that no longer fit are left out.
    Returns (spots, own: item key -> original spot)."""
    spots, own = [], {}
    for it in pool:
        if it.home is None or it.newlock_bit or it.cradle_key or homes.get(it.key) is None:
            continue   # no place of its own in a level (Q's start gadgets too): a hiding spot
        L, home = world["levels"][it.home], homes.get(it.key)
        note = f"where {it.label} is in the original game"
        tag = L.get("record_tags", {}).get(str(home["idx"]), -1)
        if tag >= 0:
            note = next((s["note"] for s in L["spots"] if s.get("tag") == tag and s["kind"] == "pad"), note)
        unreliable = set(L.get("unreliable_guards", []))
        if home.get("held_by_guard") is not None:
            g = home["held_by_guard"]
            sp = Spot(it.home, "guard", g, tuple(home["diffs"]), f"carried by guard {g} ({it.label} originally)",
                      (), L["guard_tags"].get(str(g), -1), g not in unreliable)
        elif home.get("inside") is not None:
            sp = Spot(it.home, "inside", home["inside"], tuple(home["diffs"]), note)
        else:
            safe = next((s for s in L["safes"] if s["item_rec"] == home["idx"]), None)
            sp = Spot(it.home, "safe", safe["link"], tuple(home["diffs"]), f"inside the safe ({it.label} originally)",
                      tuple(safe["needs"])) if safe else \
                Spot(it.home, "pad", home["pad"], tuple(home["diffs"]), note, (),
                     L.get("record_tags", {}).get(str(home["idx"]), -1))
        skip = skip_for(it.home, it.key, sp.kind, [i.key for i in pool if i.home == it.home])
        if skip:
            sp = dataclasses.replace(sp, skip=skip)
        spots.append(sp)
        own[it.key] = sp
    return spots, own


def swap_in(rng, item, placement, rest, homes, own, filler_keys, prog_keys):
    """`item` fits no free spot (say only its own original spot is left): give
    it the spot of a placed filler item that can move to a free one instead."""
    options = [(s, other, r) for s, other in placement.items() if other.key in filler_keys
               and allowed(item, s, homes, own, prog_keys)
               for r in rest if allowed(other, r, homes, own, prog_keys)]
    if not options:
        return False
    s, other, r = rng.choice(sorted(options, key=lambda o: (o[0].id, o[0].note, o[2].id, o[2].note)))
    placement[s] = item
    placement[r] = other
    rest.remove(r)
    return True


def fill_safes(rng, placement, all_spots, homes, filler_keys, prog_keys, state, enabled):
    """A safe is never empty: its key should be worth finding. Nor is a
    character who hands something over (Dr. Doak, Mishkin). Move a key or
    document into any such spot the fill left empty - a spare one if there is
    one, else a needed one, kept only if the seed is still beatable."""
    def must_fill(s):
        return s.kind == "safe" or s.tag >= 0

    for safe in [s for s in all_spots if must_fill(s) and s not in placement]:
        movable = sorted([(s, it) for s, it in placement.items()
                          if not must_fill(s) and allowed(it, safe, homes, prog_keys=prog_keys)],
                         key=lambda m: (m[1].key not in filler_keys, m[0].id, m[0].note))
        spare = [m for m in movable if m[1].key in filler_keys]
        rng.shuffle(spare)
        needed = [m for m in movable if m[1].key not in filler_keys]
        rng.shuffle(needed)
        for s, it in spare + needed:
            del placement[s]
            placement[safe] = it
            if it.key in filler_keys:
                break
            _, beaten, _ = state.sweep(set(), placement)
            if not set(enabled) - beaten:
                break
            del placement[safe]          # would lock the seed: put it back
            placement[s] = it


PICKUP_NAMES = {
    "ITEM_KNIFE": "a hunting knife", "ITEM_THROWKNIFE": "throwing knives", "ITEM_WPPK": "a PP7",
    "ITEM_WPPKSIL": "a silenced PP7", "ITEM_TT33": "a DD44 Dostovei", "ITEM_SKORPION": "a Klobb",
    "ITEM_AK47": "a KF7 Soviet", "ITEM_UZI": "a ZMG (9mm)", "ITEM_MP5K": "a D5K Deutsche",
    "ITEM_MP5KSIL": "a silenced D5K", "ITEM_SPECTRE": "a Phantom", "ITEM_M16": "an AR33 assault rifle",
    "ITEM_FNP90": "an RC-P90", "ITEM_SHOTGUN": "a shotgun", "ITEM_AUTOSHOT": "an automatic shotgun",
    "ITEM_SNIPERRIFLE": "a sniper rifle", "ITEM_RUGER": "a Cougar Magnum", "ITEM_GOLDENGUN": "a Golden Gun",
    "ITEM_SILVERWPPK": "a silver PP7", "ITEM_GOLDWPPK": "a gold PP7", "ITEM_LASER": "a Moonraker laser",
    "ITEM_GRENADELAUNCH": "a grenade launcher", "ITEM_ROCKETLAUNCH": "a rocket launcher",
    "ITEM_GRENADE": "grenades", "ITEM_TIMEDMINE": "timed mines", "ITEM_PROXIMITYMINE": "proximity mines",
    "ITEM_REMOTEMINE": "remote mines",
}


def pickup_items(world, enabled, diff):
    """Each level's own body armor and floor guns, as never-needed items:
    shuffled like everything else, and in original-locations mode each one's
    place is an original location. Yields (item, its record)."""
    for lv in enabled:
        for rec in world["levels"][lv]["pickups"]:
            if diff not in rec["diffs"]:
                continue
            if rec["type"] == "Armour":
                label = "body armor" if rec["armour"] >= 100 else f"body armor ({rec['armour']}%)"
            else:
                label = PICKUP_NAMES.get(rec["item"], rec["item"])
            yield Item(f"pickup_{lv}_{rec['idx']}", label, lv, progression=False, pickup=rec["type"]), rec


def pick_new_locks(rng, settings, enabled, world):
    """Lock settings.new_locks normally-open doors; one new key each, named for
    its level. Spread over different levels first. Returns (lock table, items)."""
    names = {lv.key: lv.name for lv in levels.ALL}
    avail = {lv: (list(world["levels"][lv]["lock_doors"]), list(world["levels"][lv]["free_key_bits"]))
             for lv in enabled if world["levels"][lv]["lock_doors"] and world["levels"][lv]["free_key_bits"]}
    locks, items, per_level = [], [], {}
    for _ in range(settings.new_locks):
        usable = [lv for lv in sorted(avail) if avail[lv][1]
                  and any(settings.difficulty in d["diffs"] for d in avail[lv][0])]
        if not usable:
            break
        fewest = min(per_level.get(lv, 0) for lv in usable)
        lv = rng.choice([x for x in usable if per_level.get(x, 0) == fewest])
        doors, bits = avail[lv]
        door = rng.choice([d for d in doors if settings.difficulty in d["diffs"]])
        bit = bits.pop(0)
        taken = {door["idx"], door["partner"]}
        doors[:] = [d for d in doors if d["idx"] not in taken and d["partner"] not in taken]
        for idx in (door["idx"], door["partner"]):
            if idx is not None:
                locks.append((SP[lv], bit, idx))
        per_level[lv] = per_level.get(lv, 0) + 1
        n = per_level[lv]
        items.append(Item(f"newlock_{lv}_{n}", f"the {names[lv]} key" + (f" {n}" if n > 1 else ""), lv,
                          model="PROP_CHRKEYYALE", newlock_bit=bit))
    return locks, items


def pick_loadout(rng):
    first = rng.choice(["ITEM_WPPK", "ITEM_WPPKSIL"]) if rng.random() < 0.8 else rng.choice(LIGHT_WEAPONS)
    guns = [first]
    if rng.random() < 0.5:
        second = rng.choice([w for w in LIGHT_WEAPONS if w != first])
        guns.append(second)
    ammo = sum(rng.randint(2, 4) * MAG[g] for g in guns)   # all light guns use 9mm
    return guns, ammo


# ------------------------------------------------------------------ output

def to_seedfile(res):
    world, homes, settings = res["world"], res["homes"], res["settings"]
    items, props, ammo = world["enums"]["items"], world["enums"]["props"], world["enums"]["ammo"]

    seed = seedfile.Seed(seed=run_id(res["code"]), difficulty=DIFFS.index(settings.difficulty),
                         bonus_levels=settings.bonus, show_handover=settings.show_handover,
                         glow_items=settings.glow_items, carriers=settings.carriers,
                         goal_codes=settings.goal == "codes",
                         start_levels=[SP[k] for k in res["start"]],
                         bonus_parent=(SP.get(res["parents"].get("aztec"), seedfile.NO_LEVEL),
                                       SP.get(res["parents"].get("egyptian"), seedfile.NO_LEVEL)),
                         start_pads=[world["levels"][lv.key]["start_pad"] for lv in levels.ALL])

    # left out (original locations): listed nowhere, so its own record in its
    # home level doesn't load either
    nowhere = Spot(None, "pad", 0, (), "left out")
    for spot, it in list(res["placement"].items()) + [(nowhere, it) for it in res.get("left_out", ())
                                                      if homes.get(it.key)]:
        home = homes.get(it.key)
        if it.cradle_key:
            kind = seedfile.KIND_CRADLEKEY
        elif it.pickup:
            kind = seedfile.KIND_PICKUP
        elif it.clearance:
            kind = seedfile.KIND_CLEARANCE
        elif it.letter >= 0:
            kind = seedfile.KIND_LETTER
        elif it.newlock_bit:
            kind = seedfile.KIND_NEWKEY
        elif home and (home["type"] in ("Key", "StandardProp")
                       or home["idx"] in world["levels"][it.home]["collect_targets"]):
            kind = seedfile.KIND_RECORD
        else:
            kind = seedfile.KIND_INVENTORY

        rectype = {"Key": 4, "StandardProp": 3, "Armour": 21}.get(home["type"], 8) \
            if home and kind in (seedfile.KIND_RECORD, seedfile.KIND_PICKUP) else \
            4 if kind in (seedfile.KIND_NEWKEY, seedfile.KIND_CLEARANCE, seedfile.KIND_LETTER) else 8
        model = home["model"] if home and kind in (seedfile.KIND_RECORD, seedfile.KIND_PICKUP) \
            else (it.model or (home or {}).get("model"))
        weapon = it.weapon or (home or {}).get("item")
        mode, ref = {"pad": (seedfile.MODE_PAD, spot.ref), "guard": (seedfile.MODE_GUARD, spot.ref),
                     "inside": (seedfile.MODE_INSIDE, spot.ref), "safe": (seedfile.MODE_SAFE, spot.ref),
                     "start": (seedfile.MODE_START, spot.ref)}[spot.kind]
        if spot.tag >= 0:
            seed.tags.append((SP[spot.level], spot.tag, len(seed.items)))
        seed.items.append(seedfile.SeedItem(
            home=SP[it.home] if it.home else seedfile.NO_LEVEL, rectype=rectype,
            homerec=home["idx"] if home else seedfile.NO_RECORD,
            model=props[model], weaponnum=items[weapon] if weapon else -1, kind=kind,
            place=SP[spot.level] if spot.level else seedfile.NO_LEVEL, mode=mode, ref=ref,
            flags=home.get("flags1", 0) if home else 0, flags2=home.get("flags2", 0) if home else 0,
            name="" if it.pickup else f"Picked up {it.label}.",   # armor and guns: the game's own message
            ammotype=ammo[it.ammo[0]] if it.ammo else 0,
            ammo=home["armour"] if it.pickup == "Armour" else it.ammo[1] if it.ammo else 0,   # armor: percent
            keybit=SP[it.clearance] if it.clearance else it.letter if it.letter >= 0 else it.newlock_bit))

    guns, rounds = res["loadout"]
    seed.loadout = [(0, items[g], 0) for g in guns] + [(1, ammo["AMMO_9MM"], rounds)]
    seed.topups = [(SP[lv], items[w], ammo[a], n) for lv, w, a, n in logic.TOPUPS if lv in res["enabled"]]
    seed.locks = list(res["locks"])
    return seed


def describe(settings):
    return (f"{settings.difficulty}, bonus levels {'on' if settings.bonus else 'off'}, "
            f"logic {settings.tier}, "
            f"crates/barrels {'on' if settings.containers else 'off'}, "
            f"announce carried items {'on' if settings.show_handover else 'off'}, "
            f"new locks {settings.new_locks}, "
            f"glowing items {'on' if settings.glow_items else 'off'}, "
            f"guards carrying items: {CARRIER_LABELS[settings.carriers].lower()}, "
            f"item locations: {settings.placement}, goal: {settings.goal}")


def spoiler(res, words):
    names = {lv.key: lv.name for lv in levels.ALL}
    out = [f"GoldenEye Randomizer  race code {res['code']}  (seed {res['seed']})",
           f"check words: {words}",
           describe(res["settings"]), "",
           "Goal: " + GOAL_LABELS[res["settings"].goal],
           "Start levels: " + ", ".join(names[k] for k in res["start"])]
    for b, p in res["parents"].items():
        out.append(f"{names[b]} unlocks after beating {names[p]}")
    guns, rounds = res["loadout"]
    newlock_levels = sorted(res["extra_gates"], key=SP.get)
    out += [f"Loadout: {', '.join(guns)} + {rounds} rounds of 9mm",
            "New locks on: " + (", ".join(names[k] for k in newlock_levels) if newlock_levels else "none"),
            "", "Tricks this seed may require:"]
    out += [f"  {logic.TRICKS[i][1]}: skip {logic.TRICKS[i][3]}" for i in sorted(res['tricks'])] or ["  none"]
    out += ["", "Progression, step by step:"]
    for i, step in enumerate(res["spheres"], 1):
        out.append(f"  step {i}: " + ", ".join(step))
    out += ["", "Where everything is:"]
    for spot, it in sorted(res["placement"].items(), key=lambda kv: (SP[kv[0].level], kv[0].id)):
        out.append(f"  {names[spot.level]:10} {spot.note:40} {it.label}")
    if res.get("left_out"):
        out += ["", f"Left out (no original place left for them): {len(res['left_out'])}"]
        out += [f"  {names[it.home] if it.home else '':10} {it.label}"
                for it in sorted(res["left_out"], key=lambda it: (SP.get(it.home, 99), it.label))]
    return "\n".join(out) + "\n"


def write(res, out):
    """Write seed.bin + spoiler. Returns (seed bytes, check words)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    blob = to_seedfile(res).pack()
    words = check_words(blob)
    (out / "seed.bin").write_bytes(blob)
    (out / f"spoiler-{res['code']}.txt").write_text(spoiler(res, words), encoding="utf-8", newline="\n")
    (out / "current.txt").write_text(f"{res['code']}\n{words}\n", encoding="utf-8", newline="\n")
    return blob, words


def new_seed():
    return secrets.randbits(40)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--race", help="race code from another player (sets seed and settings)")
    ap.add_argument("--difficulty", choices=DIFFS, default="agent")
    ap.add_argument("--no-bonus", action="store_true", help="leave out Aztec and Egyptian")
    ap.add_argument("--logic", choices=logic.TIERS, default="normal",
                    help="easy: no tricks required; normal: known tricks may be required; advanced: + glitches")
    ap.add_argument("--containers", action="store_true", help="also hide items inside crates and barrels")
    ap.add_argument("--show-handover", action="store_true",
                    help="announce carried items when a level starts (off: it hints where they're used)")
    ap.add_argument("--new-locks", type=int, default=0, choices=range(0, 11), metavar="0-10",
                    help="lock this many normally-open doors, each with a new key named for its level")
    ap.add_argument("--no-glow", action="store_true", help="items still to find don't glow")
    ap.add_argument("--carriers", choices=CARRIERS, default="greyer",
                    help="guards holding an item: drawn slightly greyer, or the same as other guards")
    ap.add_argument("--original-locations", action="store_true",
                    help="items only where the original game has one (they swap places)")
    ap.add_argument("--goal", choices=GOALS, default="codes",
                    help=f"codes: {CODE_WORD} + the GoldenEye Key open Cradle; all: beat every level, then Cradle")
    ap.add_argument("--out", default="data/rando")
    args = ap.parse_args(argv)

    world = worlddata.load()
    if args.race:
        seed, settings = parse_race_code(args.race, world)
    else:
        seed = args.seed if args.seed is not None else new_seed()
        settings = Settings(args.difficulty, not args.no_bonus, args.logic, args.containers, args.show_handover,
                            args.new_locks, not args.no_glow, args.carriers,
                            "original" if args.original_locations else "anywhere", args.goal)
    res = generate(seed, settings, world)
    _, words = write(res, args.out)
    print(f"race code {res['code']}  check words: {words}\n"
          f"{len(res['placement'])} items, {len(res['spheres'])} steps -> {Path(args.out) / 'seed.bin'}")


if __name__ == "__main__":
    main()
