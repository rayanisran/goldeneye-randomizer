"""Solo levels in mission order, with their setup and text files."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Level:
    key: str
    name: str
    setup: str      # setup stem, e.g. "UsetupdamZ" (u/ variant preferred when present)
    textbank: str   # TEXTBANK_LEVEL_INDEX name, e.g. "LDAM"
    bg: str = ""    # floor-tile file: assets/obseg/stan/Tbg_<bg>_all_p_stanZ.c
    bonus: bool = False


# Mission order. Neighbours in this list are "adjacent" for the starting-level rule.
CHAIN = [
    Level("dam", "Dam", "UsetupdamZ", "LDAM", bg="dam"),
    Level("facility", "Facility", "UsetuparkZ", "LARK", bg="ark"),
    Level("runway", "Runway", "UsetuprunZ", "LRUN", bg="run"),
    Level("surface1", "Surface 1", "UsetupsevxZ", "LSEVX", bg="sevx"),
    Level("bunker1", "Bunker 1", "UsetupsevbunkerZ", "LSEV", bg="sev"),
    Level("silo", "Silo", "UsetupsiloZ", "LSILO", bg="silo"),
    Level("frigate", "Frigate", "UsetupdestZ", "LDEST", bg="dest"),
    Level("surface2", "Surface 2", "UsetupsevxbZ", "LSEVXB", bg="sevx"),
    Level("bunker2", "Bunker 2", "UsetupsevbZ", "LSEVB", bg="sevb"),
    Level("statue", "Statue", "UsetupstatueZ", "LSTAT", bg="stat"),
    Level("archives", "Archives", "UsetuparchZ", "LARCH", bg="arch"),
    Level("streets", "Streets", "UsetuppeteZ", "LPETE", bg="pete"),
    Level("depot", "Depot", "UsetupdepoZ", "LDEPO", bg="depo"),
    Level("train", "Train", "UsetuptraZ", "LTRA", bg="tra"),
    Level("jungle", "Jungle", "UsetupjunZ", "LJUN", bg="jun"),
    Level("control", "Control", "UsetupcontrolZ", "LAREC", bg="arec"),
    Level("caverns", "Caverns", "UsetupcaveZ", "LCAVE", bg="cave"),
    Level("cradle", "Cradle", "UsetupcradZ", "LCRAD", bg="crad"),
]

BONUS = [
    Level("aztec", "Aztec", "UsetupaztZ", "LAZT", bg="azt", bonus=True),
    Level("egyptian", "Egyptian", "UsetupcrypZ", "LCRYP", bg="cryp", bonus=True),
]

ALL = CHAIN + BONUS
BY_KEY = {lv.key: lv for lv in ALL}
