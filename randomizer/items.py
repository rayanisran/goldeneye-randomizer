"""The item pool: everything the randomizer moves between levels.

Each entry names where the item comes from in the vanilla game:
  rec(...)   a setup record in its home level (moved/hidden at load time)
  loadout    a gadget the level used to hand you at the start (no record)

`gives` lists the capabilities the item provides to the logic. Items that
are the same game object (Dam's covert modem and Frigate's tracking bug are
both ITEM_BUG) give the same capability, so either one satisfies both levels.
"""

from dataclasses import dataclass, field

# PROPDEF record types the randomizer creates
REC_PROP, REC_KEY, REC_COLLECTABLE, REC_AMMOBOX = 3, 4, 8, 20


@dataclass(frozen=True)
class Rec:
    """Selects a vanilla record: type, plus model / item / name substring, nth match."""
    type: str
    model: str = None
    item: str = None
    name: str = None
    nth: int = 0


@dataclass
class Item:
    key: str
    label: str                 # spoiler / pickup text ("Picked up <label>.")
    home: str                  # level key the item belongs to
    rec: Rec = None            # vanilla record, or None for a loadout gadget
    weapon: str = None         # ITEM_ id when the item is carried in the weapon inventory
    model: str = None          # pickup model when there is no vanilla record to copy
    ammo: tuple = None         # (AMMO_ type, amount) given on pickup
    gives: tuple = ()          # extra capabilities; the key itself is always given
    progression: bool = True   # False: weapons / ammo packs, placed anywhere
    cradle_key: bool = False
    diffs: tuple = ("agent", "secret", "00agent")   # difficulties the item exists on
    newlock_bit: int = 0       # key for a new lock: its level's door opens with this key bit

    def capabilities(self):
        return (self.key,) + tuple(self.gives)


def _ld(key, label, home, weapon, model, ammo=None, gives=(), **kw):
    return Item(key, label, home, weapon=weapon, model=model, ammo=ammo, gives=gives, **kw)


POOL = [
    # Dam
    _ld("covert_modem", "the covert modem", "dam", "ITEM_BUG", "PROP_CHRBUG", ("AMMO_BUG", 1), gives=("bug",)),
    # Facility
    Item("facility_decoder", "the Facility door decoder", "facility",
         Rec("Collectable", item="ITEM_DOORDECODER"), weapon="ITEM_DOORDECODER"),
    Item("facility_keycard_a", "the clearance A keycard", "facility", Rec("Key", name="clearance A")),
    Item("facility_keycard_b", "the clearance B keycard", "facility", Rec("Key", name="clearance B")),
    # Runway
    Item("runway_ignition_key", "the plane ignition key", "runway", Rec("Key", name="ignition key")),
    # Surface 1
    Item("surface1_large_key", "the Surface large key", "surface1", Rec("Key", name="large key")),
    Item("surface1_safe_key", "the Surface safe key", "surface1", Rec("Key", name="safe key")),
    Item("surface1_plans", "the bunker plans", "surface1", Rec("StandardProp", model="PROP_CHRMAP")),
    # Bunker 1
    _ld("key_analyser", "the key analyser", "bunker1", "ITEM_KEYANALYSERCASE", "PROP_CHRKEYANALYSERCASE"),
    _ld("camera", "the camera", "bunker1", "ITEM_CAMERA", "PROP_CHRCAMERA", ("AMMO_CAMERA", 10)),
    _ld("data_thief", "the data thief", "bunker1", "ITEM_DATATHIEF", "PROP_CHRDATATHIEF"),
    Item("bunker1_keycard_computer", "the computer room keycard", "bunker1", Rec("Key", name="computer room")),
    Item("bunker1_keycard_security", "the security keycard", "bunker1", Rec("Key", name="security keycard")),
    # Silo
    _ld("plastique", "the plastique", "silo", "ITEM_PLASTIQUE", "PROP_CHRPLASTIQUE", ("AMMO_PLASTIQUE", 8)),
    Item("silo_dat", "the telemetric DAT", "silo", Rec("StandardProp", model="PROP_CHRDATTAPE")),
    *[Item(f"silo_circuit_{n + 1}", f"circuit board {n + 1} of 4", "silo",
           Rec("StandardProp", model="PROP_CHRCIRCUITBOARD", nth=n)) for n in range(4)],
    *[Item(f"silo_keycard_{n + 1}", f"Silo keycard {name}", "silo",
           Rec("Key", model="PROP_SWIPE_CARD2", nth=n)) for n, name in enumerate(["4-H4", "4-C3", "4-K2"])],
    Item("silo_keycard_4", "Ourumov's master keycard", "silo", Rec("Key", model="PROP_SWIPE_CARD2", nth=3),
         progression=False),   # opens every Silo keycard door; never needed
    # Frigate
    _ld("tracker_bug", "the tracking bug", "frigate", "ITEM_BUG", "PROP_CHRBUG", ("AMMO_BUG", 1), gives=("bug",)),
    _ld("bomb_defuser", "the bomb defuser", "frigate", "ITEM_BOMBDEFUSER", "PROP_CHRBOMBDEFUSER"),
    # Surface 2
    Item("surface2_comms_key", "the comms room key", "surface2", Rec("Key", name="comms room")),
    _ld("surface2_remote_mine", "a remote mine", "surface2", "ITEM_REMOTEMINE", "PROP_CHRREMOTEMINE",
        ("AMMO_REMOTEMINE", 1), gives=("remote_mines", "explosives")),
    # Bunker 2
    _ld("magnet_watch", "the magnet watch", "bunker2", "ITEM_WATCHMAGNETATTRACT", "PROP_CHRWEAPONCASE",
        ("AMMO_WATCH_MAGNET", 5)),
    Item("bunker2_cell_key", "Natalya's cell key", "bunker2", Rec("Key", name="cell key", nth=1)),
    Item("bunker2_safe_key_1", "Bunker safe key 1 of 2", "bunker2", Rec("Key", name="safe key", nth=0)),
    Item("bunker2_safe_key_2", "Bunker safe key 2 of 2", "bunker2", Rec("Key", name="safe key", nth=1)),
    Item("bunker2_keycard_1", "Bunker keycard B", "bunker2", Rec("Key", model="PROP_SWIPE_CARD2", nth=0)),   # mask 8
    Item("bunker2_keycard_2", "Bunker keycard A", "bunker2", Rec("Key", model="PROP_SWIPE_CARD2", nth=1)),   # mask 4, opens the end glass doors
    Item("bunker2_cctv_tape", "the CCTV tape", "bunker2", Rec("StandardProp", model="PROP_CHRVIDEOTAPE")),
    Item("bunker2_dossier", "the GoldenEye ops manual", "bunker2", Rec("StandardProp", model="PROP_CHRDOSSIERRED")),
    # "compare staff / casualty lists" (Secret Agent, 00 Agent): the level's
    # script checks Bond collected both, by their tags
    Item("bunker2_clipboard", "the clipboard", "bunker2", Rec("StandardProp", model="PROP_CHRCLIPBOARD")),
    Item("bunker2_staff_list", "the staff list", "bunker2", Rec("StandardProp", model="PROP_CHRSTAFFLIST")),
    # Statue
    Item("statue_flight_recorder", "the flight recorder", "statue", Rec("StandardProp", model="PROP_CHRBLACKBOX")),
    # Archives
    Item("archives_door_key", "the interrogation door key", "archives", Rec("Key", name="door key")),
    Item("archives_safe_key", "the Archives safe key", "archives", Rec("Key", name="safe key")),
    Item("archives_black_box", "the helicopter black box", "archives", Rec("StandardProp", model="PROP_CHRBLACKBOX")),
    # Depot
    Item("depot_safe_key", "the Depot safe key", "depot", Rec("Key", name="safe key")),
    Item("depot_blueprints", "the helicopter blueprints", "depot", Rec("StandardProp", model="PROP_CHRBLUEPRINTS")),
    # Train
    _ld("laser_watch", "the laser watch", "train", "ITEM_WATCHLASER", "PROP_CHRWEAPONCASE",
        ("AMMO_WATCH_LASER", 300)),
    Item("train_door_key", "the Train door key", "train", Rec("Key", name="door key")),
    # Caverns
    *[Item(f"caverns_code_card_{n + 1}", f"code card {'ABC'[n]}", "caverns",
           Rec("Key", name="code card", nth=n)) for n in range(3)],   # blast doors A, B, C
    # Aztec
    Item("aztec_smart_card", "Jaws' smart card", "aztec", Rec("Key", name="smart card")),
    _ld("explosive_floppy", "the explosive floppy", "aztec", "ITEM_EXPLOSIVEFLOPPY", "PROP_CHRMICROCODE"),
    # Egyptian
    Item("golden_gun", "the Golden Gun", "egyptian", Rec("Collectable", item="ITEM_GOLDENGUN"),
         weapon="ITEM_GOLDENGUN"),
    # Cradle
    Item("goldeneye_key", "the GoldenEye Key", None, weapon="ITEM_GOLDENEYEKEY", model="PROP_CHRGOLDENEYEKEY",
         cradle_key=True),

    # Weapons and packs: placed anywhere, never required
    Item("control_remote_mines", "8 remote mines", "control", Rec("AmmoBox", model="PROP_AMMO_CRATE3"),
         weapon="ITEM_REMOTEMINE", model="PROP_CHRREMOTEMINE", ammo=("AMMO_REMOTEMINE", 8),
         gives=("remote_mines", "explosives"), progression=False),
    _ld("facility_remote_mines", "5 remote mines", "facility", "ITEM_REMOTEMINE", "PROP_CHRREMOTEMINE",
        ("AMMO_REMOTEMINE", 5), gives=("remote_mines", "explosives"), progression=False),
    _ld("jungle_remote_mines", "6 remote mines", "jungle", "ITEM_REMOTEMINE", "PROP_CHRREMOTEMINE",
        ("AMMO_REMOTEMINE", 6), gives=("remote_mines", "explosives"), progression=False),
    _ld("caverns_timed_mines", "6 timed mines", "caverns", "ITEM_TIMEDMINE", "PROP_CHRTIMEDMINE",
        ("AMMO_TIMEDMINE", 6), gives=("explosives",), progression=False),
    # (plain guns from start loadouts - sniper rifle, D5K, ZMG - are not items:
    # guards drop guns anyway, Rayan 10-31)
]

BY_KEY = {it.key: it for it in POOL}
