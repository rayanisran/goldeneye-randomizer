"""What each level needs, per difficulty and logic tier, in capabilities (see items.py).

Tiers:
  easy      no tricks are ever required
  normal    veterans' default: the known tricks below count as valid ways
            forward, so a seed may require them
  advanced  normal plus glitches and warps

gates  : capabilities that open parts of the level. Until hiding spots carry
         per-area data, every spot in a level assumes ALL of its gates, which
         is conservative: it can only narrow where items go, never strand one.
needs  : what the objectives use, per difficulty.
Beating a level requires its gates plus its needs.

A requirement is a capability name, or a tuple of alternatives (any one will
do): ("surface2_comms_key", "explosives") reads "the comms key OR explosives".
"""

A, S, O = "agent", "secret", "00agent"
ALL = (A, S, O)
SO = (S, O)
TIERS = ("easy", "normal", "advanced")

LEVELS = {
    # 00 Agent: Dam and Frigate each use up a bug, and the covert modem and the
    # tracking bug are one bug each (same game item), so both are needed there.
    "dam":       {"needs": {O: ["covert_modem", "tracker_bug"]}},
    "facility":  {"gates": ["facility_keycard_a", "facility_keycard_b"],
                  "gates_by_diff": {S: ["facility_decoder"], O: ["facility_decoder"]}},
    "runway":    {"needs": {d: ["runway_ignition_key"] for d in ALL}},
    "surface1":  {"gates": ["surface1_large_key", "surface1_safe_key"],
                  "needs": {d: ["surface1_safe_key", "surface1_plans"] for d in SO}},
    "bunker1":   {"gates": ["bunker1_keycard_computer", "bunker1_keycard_security"],
                  "needs": {A: ["key_analyser", "camera"], S: ["key_analyser", "camera"],
                            O: ["key_analyser", "camera", "data_thief"]}},
    # Silo: three scientists each carry the keycard for their room's exit and
    # the next room's entry (4-H4, 4-C3, 4-K2). Ourumov's master keycard (#4)
    # opens all of them but is never needed, so it isn't required here.
    "silo":      {"gates": [f"silo_keycard_{n}" for n in range(1, 4)],
                  "needs": {A: ["camera"],
                            S: ["camera", "silo_dat"] + [f"silo_circuit_{n}" for n in range(1, 5)],
                            O: ["camera", "silo_dat", "plastique"] + [f"silo_circuit_{n}" for n in range(1, 5)]}},
    "frigate":   {"needs": {A: ["bug"], S: ["bug", "bomb_defuser"],
                            O: ["covert_modem", "tracker_bug", "bomb_defuser"]}},
    "surface2":  {"gates": ["surface2_comms_key"],
                  "needs": {A: ["surface2_comms_key"], S: ["surface2_comms_key", "remote_mines"],
                            O: ["surface2_comms_key", "remote_mines"]}},
    "bunker2":   {"gates": ["magnet_watch", "bunker2_cell_key", "bunker2_keycard_1", "bunker2_keycard_2"],
                  "needs": {A: ["bunker2_cctv_tape"],
                            S: ["bunker2_cctv_tape", "bunker2_safe_key_1", "bunker2_safe_key_2",
                                "bunker2_clipboard", "bunker2_staff_list"],
                            O: ["bunker2_cctv_tape", "bunker2_safe_key_1", "bunker2_safe_key_2", "bunker2_dossier",
                                "bunker2_clipboard", "bunker2_staff_list"]}},
    "statue":    {"needs": {d: ["statue_flight_recorder"] for d in ALL}},
    "archives":  {"gates": ["archives_door_key"],
                  "needs": {d: ["archives_safe_key", "archives_black_box"] for d in SO}},
    "streets":   {},
    "depot":     {"needs": {d: ["depot_safe_key", "depot_blueprints"] for d in SO}},
    "train":     {"gates": ["train_door_key"], "needs": {d: ["laser_watch"] for d in ALL}},
    "jungle":    {},
    "control":   {"needs": {d: ["explosives"] for d in ALL}},   # 6 mainframes; grenades can be farmed
    "caverns":   {"gates": [f"caverns_code_card_{n}" for n in range(1, 4)]},
    "cradle":    {},
    "aztec":     {"gates": ["aztec_smart_card"], "needs": {d: ["explosive_floppy"] for d in ALL}},
    "egyptian":  {"needs": {d: ["golden_gun"] for d in ALL}},
}

# Tricks, applied from the tier named. Each entry rewrites one
# requirement of one level: "drop" removes it, "need" turns an access gate into
# a completion-only need (the area is reachable without it, beating the level
# is not), "alt" replaces it with a tuple of alternatives.
TRICKS = [
    # Facility: shooting lures scientists to open the keycard doors
    ("normal", "facility", ALL, "facility_keycard_a", "drop"),
    ("normal", "facility", ALL, "facility_keycard_b", "drop"),
    # Facility SA/00: the bottling room is reachable without the decoder
    # (the level still can't be beaten without it)
    ("normal", "facility", SO, "facility_decoder", "need"),
    # Silo: guards open every keycard door (exit of each main room, entry of the next)
    ("normal", "silo", ALL, "silo_keycard_1", "drop"),
    ("normal", "silo", ALL, "silo_keycard_2", "drop"),
    ("normal", "silo", ALL, "silo_keycard_3", "drop"),
    # Bunker 1: guards open the mainframe room and the ending corridor
    ("normal", "bunker1", ALL, "bunker1_keycard_computer", "drop"),
    ("normal", "bunker1", ALL, "bunker1_keycard_security", "drop"),
    # Surface 2: the comms objective falls to any explosive (mines, grenades,
    # rockets); the comms room itself still needs its key
    ("normal", "surface2", ALL, "surface2_comms_key", ("alt", ("surface2_comms_key", "explosives"))),
    # Bunker 2: warp through the cell door; keycard B is never required.
    # Keycard A also opens the glass doors before the exit: kept until confirmed.
    ("normal", "bunker2", ALL, "magnet_watch", "drop"),
    ("normal", "bunker2", ALL, "bunker2_keycard_1", "drop"),   # keycard_1 = keycard B (mask 8)
    # Archives: out of the interrogation room without the guard's key
    ("normal", "archives", ALL, "archives_door_key", "drop"),
    # Train: the door key is never needed
    ("normal", "train", ALL, "train_door_key", "drop"),
    # Caverns: blast doors A and B can be skipped; C stays (exit)
    ("normal", "caverns", ALL, "caverns_code_card_1", "drop"),
    ("normal", "caverns", ALL, "caverns_code_card_2", "drop"),
    # Aztec: guards open the glass door (~80% of attempts; restarting is fine)
    ("normal", "aztec", ALL, "aztec_smart_card", "drop"),
    # Train's laser watch is not strictly needed either: guns break the floor
    # hatch (tedious), and the warp off the train needs N64 lag (Z64 build
    # only). Kept as a requirement everywhere for a fun run.
]

# No resupply: ammo and gadget charges are yours to manage.
# Mines and grenades wasted elsewhere can be farmed back from guards.
TOPUPS = []


# Each seed relies on a random share of its tier's tricks (the rest still work
# for the player, the generator just never needs them). Same chance for every
# trick, so none is singled out; 0.55 puts the most-needed skips (Facility's
# keycards) in the 40-50 % range wanted.
TRICK_ODDS = 0.55


def pick_tricks(rng, tier):
    """Indices of the tricks this seed's logic may rely on."""
    rank = TIERS.index(tier)
    return frozenset(i for i, t in enumerate(TRICKS)
                     if TIERS.index(t[0]) <= rank and rng.random() < TRICK_ODDS)


def _tricks(level, diff, tier, enabled=None):
    rank = TIERS.index(tier)
    return [(cap, act) for i, (t, lv, diffs, cap, act) in enumerate(TRICKS)
            if lv == level and diff in diffs and TIERS.index(t) <= rank
            and (enabled is None or i in enabled)]


def _apply(reqs, tricks, as_gate):
    out = []
    for r in reqs:
        act = next((a for cap, a in tricks if cap == r), None)
        if act == "drop":
            continue
        if act == "need":
            if as_gate:
                continue          # reachable without it; stays a completion need
        elif isinstance(act, tuple) and act[0] == "alt" and not as_gate:
            r = act[1]            # the objective has alternatives; the area still needs r
        out.append(r)
    return out


def gates(level, diff, tier="easy", enabled=None):
    spec = LEVELS[level]
    raw = list(spec.get("gates", [])) + list(spec.get("gates_by_diff", {}).get(diff, []))
    return set(_apply(raw, _tricks(level, diff, tier, enabled), as_gate=True))


def requirements(level, diff, tier="easy", enabled=None):
    """Requirements to beat `level` on `diff` (names or tuples of alternatives)."""
    spec = LEVELS[level]
    raw = list(spec.get("gates", [])) + list(spec.get("gates_by_diff", {}).get(diff, [])) \
        + list(spec.get("needs", {}).get(diff, []))
    return set(_apply(raw, _tricks(level, diff, tier, enabled), as_gate=False))


def satisfied(reqs, caps):
    return all((any(a in caps for a in r) if isinstance(r, tuple) else r in caps) for r in reqs)


def required_capabilities(diff, levels, tier="easy", enabled=None):
    """Every capability some requirement could use (alternatives included)."""
    out = set()
    for lv in levels:
        for r in requirements(lv, diff, tier, enabled) | gates(lv, diff, tier, enabled):
            out |= set(r) if isinstance(r, tuple) else {r}
    return out
