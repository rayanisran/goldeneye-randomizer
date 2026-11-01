# GoldenEye 007 Randomizer

A randomizer for *GoldenEye 007* (N64), running on the native
[GoldenEye 007 PC port](https://github.com/jkdansereau/goldeneye-pc-port)
(built from the [007 decompilation](https://github.com/n64decomp/007); no
emulator). Every seed shuffles the campaign's keys, keycards, gadgets,
objective items, body armor and guns between levels, and hides a clearance
for each level, so any check can open new levels. The goal is to find the
five letters of the code word **JANUS** and the GoldenEye Key, which open
Cradle. Every seed is checked by the generator before you play it so it can
always be beaten. Seeds can be shared as short race codes, so two players
can race the same game.

> **PC only for now.** A real N64 ROM (or a `.bps` patch for your own ROM, for
> emulators and flashcarts) is **planned but not built yet**. The game-side
> code is already shared with the N64 build, but loading the seed from the
> ROM, saving progress to EEPROM, and N64 versions of the item glow and the
> found-items list haven't been written yet.

No ROM and no game data are included. You need your own *GoldenEye 007*
**US (NTSC-U)** ROM, which the game converts on its first launch.

---

## How a run works

- **Start:** three random levels are open, never two next to each other,
  so the run spreads out. You start with a random light loadout (usually
  the PP7, sometimes a DD44, Klobb, ZMG or D5K, and maybe a second gun) and
  a supply of 9 mm.
- **Unlocking:** every other level (except Cradle) has a **clearance**
  hidden somewhere. Finding it opens that level right away. Beating a
  campaign level still opens the next one in the normal order too, so
  either way works. When Aztec and Egyptian are on, each one is also opened
  by beating a randomly chosen campaign level.
- **The goal (satellite codes, the default):** find the five code letters
  **J A N U S** and the GoldenEye Key. Together they open Cradle; beat
  Cradle to win. You don't have to play every level, only the ones your
  route needs. Picking up a letter shows your progress, like
  `Code letter N:  J A N _ _`. Letters can share a level, but all five in
  one level is very rare. The generator makes every seed take you through
  at least 10 of the 20 levels (about 14 to 16 on a typical seed).
- **The other goal (beat every level):** Cradle opens once every other
  level is beaten and you've found the GoldenEye Key.
- The GoldenEye Key on the table in Bunker 1 is a different one: it's there
  for that level's "copy the key" objective and doesn't open Cradle.
- **Items:** door decoders, keycards, keys, the plane ignition key, the bug
  and covert modem, the camera, the key analyser, the laser and magnet
  watches, the DAT, the black boxes, the circuit boards, the explosive
  floppy, the Golden Gun and so on (51 needed items), plus the clearances
  (16, or 14 without the bonus levels) and the code letters. Any of them
  can end up in any level.
- **Body armor and guns:** each level's own body armor and the guns lying
  in the open are shuffled too, so a rocket launcher can turn up in
  Facility. They're never required. There are about 74 on Agent, 58 on
  Secret Agent and 43 on 00 Agent (harder difficulties have less armor).
  Extra mine packs are placed as well. Grenades the levels' scripts use
  stay where they are.
- **Where items go:** at a hiding spot in a level, carried by a guard (kill
  them to get it), inside a safe, in your start loadout for that level (like
  Q's gadgets), or inside crates and barrels if that option is on. Characters
  who hand you something in the original game always still do: Dr. Doak in
  Facility and Mishkin in Archives each give you a shuffled item. On
  Surface 1 and 2, floor spots are only used inside huts and buildings, so
  you never have to sweep the open snowfield.
- **Every seed is beatable.** The generator uses an "assumed fill": each
  required item is placed only where it can be reached without it. It then
  plays the whole seed through on paper before writing it, so you can't get
  locked out by an item behind its own door. Every item can be collected,
  including the spare ones (no safe holds its own key). It also requires the run to
  unfold over at least four steps, so seeds don't fall open on the first
  level, and places the code letters and the GoldenEye Key before anything
  else so they can land anywhere in the game.
- **Items stay found.** An item counts the moment you pick it up, even if
  you then die or quit the level, so you can go in for one check and leave.
- **No resupply:** ammo and gadget charges are yours to manage. Mines and
  grenades you use up can be farmed back from guards.
- **Progress is saved per seed.** You can switch seeds and come back to one
  later.

Good to know: the covert modem (Dam) and the tracking bug (Frigate) are the
same game item, so finding either one works for both levels. The camera is
shared by Bunker 1 and Silo the same way.

## Settings

All settings are in the launcher and are part of the race code.

| Setting | Options | What it does |
|---|---|---|
| **Difficulty** | Agent / Secret Agent / 00 Agent | The game difficulty. Harder difficulties have more objectives and so need more items (00 Agent Dam and Frigate each use up a bug, for example). |
| **Logic** | Easy / Normal / Advanced | Which tricks a seed is allowed to *require*. **Easy:** none. **Normal:** known skips (Facility scientists opening keycard doors, guards opening the doors in Silo, Bunker 1 and Aztec, the Bunker 2 cell warp, Caverns blast doors A and B, Surface 2's comms objective done with any explosive, leaving the Archives interrogation room without the key, Train's door key). **Advanced:** Normal plus glitches. No glitch tricks are listed yet, so for now it behaves like Normal. Each seed relies on a random ~55% of its tier's tricks. The rest still work, the generator just never counts on them. The spoiler log lists which ones a seed may need. |
| **Goal** | Satellite codes / Beat every level | **Satellite codes:** J A N U S and the GoldenEye Key open Cradle. **Beat every level:** every other level beaten and the GoldenEye Key open Cradle. Clearances are in both. |
| **Item locations** | Anywhere / Original locations only | **Anywhere:** hiding spots across the level and any guard. **Original:** items go only where the original game has an item: the keys, documents and gadgets, the guards who carry them, the safes, and every body armor and gun lying in the open (about 110 places on Agent, 95 on Secret Agent, 82 on 00 Agent). There are more items than places, since clearances and code letters have no place of their own: needed items always get one, and the spare body armor and guns that don't fit are left out of the run (listed at the end of the spoiler log). |
| **Include Aztec and Egyptian** | on / off | Adds the two bonus levels (and their items) to the run. |
| **Hide items inside crates and barrels** | on / off | Crates and barrels become hiding spots. Shoot them open. |
| **Announce carried items** | on / off | When a level starts, tells you which items it hands you. That hints at where they're used. |
| **Small items glow gold** | on / off | Small items still to find (keys, keycards, mines...) glow gold and stay visible from further away. Briefcases and guns are left as they are. |
| **Guards carrying an item** | Slightly greyer / Look the same | Whether a guard holding an item looks a little different. |
| **New locks** | 0-10 | Locks doors that are normally open. Each new lock gets a new key, named after its level, hidden like any other item. |
| **Seed** | number, or blank | Blank picks a random seed. |

## In-game

- Picking up an item shows "Picked up ..." with the item's name, and it
  appears in Bond's watch inventory.
- **Found-items list:** on the menus, press **I** (keyboard) or **L / R**
  (controller) to show every item found so far, clearances and code letters
  included (body armor and guns aren't listed). Press again for the next
  page.
- The level select only lets you start levels the seed has opened. A
  clearance you find opens its level there straight away.
- Best times on the mission status screen belong to the seed: a new seed
  starts with none. The save folder's own times are left alone.
- Everything else (controls, video options, the F10 settings overlay,
  60 fps, mouse aim) is the PC port's. See [PC-PORT.md](PC-PORT.md).

---

## Playing (Windows)

Download `GoldenEye-Randomizer-<version>-win64.zip` from the releases, then:

1. Extract it somewhere with a short path, like the Desktop. Very long paths
   can make the first-run setup fail.
2. Put your own US ROM in the `data` folder, named exactly
   `ge007.ntsc-final.z64`.
3. Run **GoldenEye Randomizer.exe**. Windows SmartScreen may warn about an
   unsigned app: click *More info*, then *Run anyway*.
4. Generate a seed (or paste a race code), then press **PLAY**. The very
   first launch takes longer while the game builds its files from your ROM.

No Python and nothing else to install.

To check your ROM: `certutil -hashfile ge007.ntsc-final.z64 SHA1` should
print `abe01e4aeb033b6c0836819f549c791b26cfde83`.

## Racing

1. One player sets up a seed and presses **Copy race code**. A code looks like
   `11-e978-A3-4FNP1QRP` and holds the randomizer version, the world-data
   fingerprint, all the settings and the seed.
2. The other players paste it under **Race** and press **Load race seed**.
3. Before you start, everyone compares the four **check words** (for
   example *Train Plastique Keycard Baron*). If they match, you're on the
   same seed.

The same code gives the same game on every machine (the generator uses its
own RNG, not Python's). A code from a different randomizer version is
refused rather than quietly giving a different seed, so **all racers need the
same release.**

The **Spoiler log...** button shows where every item is, for when you're
stuck. It asks you to confirm first.

---

## Running from source (testing)

Build the game first (see [docs/building.md](docs/building.md); on Windows
that's `./build-pc.sh` in the MSYS2 MINGW64 shell), put your ROM at
`data/ge007.ntsc-final.z64`, then from the repo root:

```sh
python -m randomizer.launcher
```

It needs Python 3 with tkinter (tested on 3.11), and it finds `build-pc/ge007.x86_64[.exe]`
and `data/` on its own. Seeds can also be made without the GUI:

```sh
python -m randomizer.generate --difficulty secret --logic normal --containers --goal codes
python -m randomizer.generate --race 11-e978-A3-4FNP1QRP
```

Seed files land in `data/rando/` (`seed.bin` for the game,
`spoiler-<code>.txt`, and a per-seed save and log).

## Building a Windows release

In the MSYS2 MINGW64 shell, from the repo root (needs Python with
`pip install pyinstaller`):

```sh
./build-pc.sh ntsc-final
tools_pc/bundle-win.sh rando-r1
python -m randomizer.package --platform win64 --version r1
```

The output is `dist/GoldenEye-Randomizer-r1-win64.zip`. If only the
randomizer's Python changed, the last command alone is enough.

## Building a Linux release

This has to run on Linux, because PyInstaller can't cross-build. It's the
same toolchain the PC port's CI uses. On Debian / Ubuntu:

```sh
# 1. Dependencies
sudo apt install build-essential cmake git patchelf \
                 libsdl2-dev zlib1g-dev libgl1-mesa-dev \
                 python3 python3-tk python3-venv

# 2. Source, plus a Python environment for PyInstaller
git clone https://github.com/rayanisran/goldeneye-randomizer.git
cd goldeneye-randomizer
python3 -m venv .venv && . .venv/bin/activate
pip install pyinstaller

# 3. ROM-asset symbol file and the first-run ROM converter
python3 scripts/gen_romassets.py u
python3 -m PyInstaller --onefile --noconfirm --clean --name ge007-convert \
    --distpath tools_pc/dist/prepare-assets \
    --workpath build-pyinst --specpath build-pyinst \
    tools_pc/dist/prepare-assets/prepare-assets.py

# 4. The game, its bundle, and the randomizer package
./build-pc.sh ntsc-final
tools_pc/bundle-linux.sh rando-r1
python3 -m randomizer.package --platform linux --version r1
```

The output is `dist/GoldenEye-Randomizer-r1-linux.tar.gz`. Players extract
it, put their ROM in `data/` as `ge007.ntsc-final.z64`, and run
`./GoldenEye\ Randomizer`. SDL2 is bundled. zlib and OpenGL come from the
system, which every desktop distro and SteamOS already has. A build made on
a new distro needs an equally new glibc on the player's machine, so build
on an older release (for example Ubuntu 22.04) if you want it to run in
more places.

To just play from source on Linux, steps 1 and 3 (without PyInstaller) plus
`./build-pc.sh ntsc-final` are enough. Then run `python3 -m randomizer.launcher`.

---

## How it's put together

| Part | Where | What it does |
|---|---|---|
| Generator | `randomizer/generate.py`, `logic.py`, `items.py`, `spots.py`, `rng.py` | Item pool, per-level requirements and tricks, hiding spots, assumed-fill placement, race codes, spoiler logs. |
| World data | `randomizer/data/world.json`, `survey.py`, `setupparse.py` | Each level's objects, guards, safes and containers, surveyed from the level setups. |
| Seed file | `randomizer/seedfile.py` | Writes `data/rando/seed.bin`, the binary format the game reads. |
| Launcher | `randomizer/launcher.py` | The tkinter GUI. `randomizer/package.py` freezes it into the release bundle. |
| Game runtime | `src/game/rando.c` / `rando.h` | Loads the seed, moves and creates items at level load, handles pickups, locks, level unlocks and the per-seed save. Hooks in the game code are under `#ifdef GE_RANDOMIZER`. |
| PC extras | `port/src/optionsoverlay.c`, `port/src/input.c`, `port/fast3d/gfx_opengl.cpp` | The found-items list, its buttons, and the gold item glow. |

## Roadmap

- **N64 ROM / patch:** seed stored in the ROM, saves in EEPROM, N64 versions
  of the glow and the item list, and a `.bps` patch so each player applies it
  to their own ROM.
- **Linux release** built and tested.
- **Perfect Dark** randomizer, on the same approach.

## Credits and license

Built on the [GoldenEye 007 PC port](https://github.com/jkdansereau/goldeneye-pc-port)
by jkdansereau and contributors, and the
[n64decomp/007](https://github.com/n64decomp/007) decompilation. The
original port documentation is in [PC-PORT.md](PC-PORT.md), and its build
guide is in [docs/building.md](docs/building.md).

The code is MIT licensed (see [LICENSE](LICENSE) and [NOTICE](NOTICE)).
*GoldenEye 007* is the property of its rights holders. This project
contains no ROM and no game assets, and none are distributed with it.
