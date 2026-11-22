# Changelog

All notable changes to the GoldenEye 007 Randomizer, newest first.
Downloads are on the [releases page](https://github.com/rayanisran/goldeneye-randomizer/releases).

**Versions.** Releases are named **rMAJOR** or **rMAJOR.MINOR**:

- **r6, r7, …** Normal releases. Race codes may change, so everyone in a race
  needs the same major number. The first number of a race code (`16-e978-…`)
  is the logic version, which changes whenever a code would make a different
  seed.
- **r6.1, r6.2, …** Hotfixes. They keep every race code and save working, so
  r6.1 can race r6.

## [r6.1](https://github.com/rayanisran/goldeneye-randomizer/releases/tag/r6.1) (2026-11-22, Windows and Linux)

Race codes and saves are the same as r6: r6.1 races r6.

- **Changed:** *Item locations* starts on *Original locations only*.

## [r6](https://github.com/rayanisran/goldeneye-randomizer/releases/tag/r6) (2026-11-22, Windows and Linux)

**Race codes changed:** r5 codes (starting `15-e978-`) don't load in r6, and
r6 codes start with `16-e978-`. A run you already started keeps working:
copy your `data/rando` folder into the r6 folder.

### New

- **LTK and DLTK difficulties.** The game's 007 mode on 00 Agent's levels,
  with fixed settings so every racer plays the same. LTK: enemy health 0
  (one shot kills), enemy damage, accuracy and reaction speed at maximum.
  DLTK: all four at maximum.
- **Handicaps** (all off by default, all part of the race code):
  - *Body armors respawn when you re-enter a level* (moved here from Items).
  - *Use JP BAs:* the Japanese release loads every body armor on every
    difficulty. 00 Agent goes from 19 to 50 armors (Agent has 50, Secret
    Agent 34).
  - *Use JP auto-aim:* the Japanese release's wider auto-aim lock-on on the
    harder difficulties: x1.1 on Secret Agent (US x0.75), x0.75 on 00 Agent
    (US x0.2). Agent and 007 are the same in both.
- **Mirror mode: Off / 50% of levels / Every level.**
- **Seed timer in game.** A timer in the top-left corner, in levels and on
  the menus. It starts when your first level starts, pauses while the game
  is closed and stops (in green) when Cradle is beaten. Turn it off with
  *Display seed timer in game*. It replaces the WSplit option.
- **Stats.** The *Stats* button (and, by itself, closing the game after
  beating Cradle) shows your time, deaths, item percentage, levels beaten,
  when you found each JANUS letter on a timeline, and time per level with an
  icon for each item found there and a dot for each death.
- **Updates.** The launcher checks for a newer release when it starts. If
  there is one, the bottom-right corner turns red; one click downloads it,
  checks it and replaces this copy in the same folder, keeping your ROM,
  saves, settings and seeds. Updating is off while the game is running.
  This starts with r6: older copies need r6 downloaded once by hand.
- **Found-items list:** the JANUS keycards get their own section at the top,
  filling in as you find them.

### Changed

- **The difficulty page only offers the seed's difficulty.**
- **Logic: Easy / Advanced.** Normal and Advanced were the same, since every
  trick in the logic is a Normal one. Codes that say Normal still load.
- Wording: *Extra locks on normally open doors*; no description line under
  the difficulties.

### Fixed

- Playing a seed on a different difficulty than its own (the difficulty page
  allowed it) loaded that difficulty's own body armor and objectives.

## [r5](https://github.com/rayanisran/goldeneye-randomizer/releases/tag/r5) (2026-11-22, Linux)

**Race codes changed:** r4 codes (`13-e978-`) don't load in r5; r5 codes start
with `15-e978-`.

- **New:** *Body armor respawns when you re-enter a level* (off by default):
  armor you picked up lies there again on every entry. Guns don't come back.
- **Changed:** the explosive floppy is now called the Guidance Data.
- **Changed:** found-items list paging: L, R or I open and close it from any
  page, A or Z next page, B previous page.
- **Fixed:** Egyptian ends again when you bring the Golden Gun in from
  another level.
- **Fixed:** no more crash in the end credits after beating Cradle.

## [r4](https://github.com/rayanisran/goldeneye-randomizer/releases/tag/r4) (2026-11-21, Linux)

**Race codes changed:** r3 codes (`11-e978-`) don't load in r4; r4 codes start
with `13-e978-`.

- **New:** the first Linux download (64-bit x86, glibc 2.34 or newer).
- **New:** mirror mode (Off / On): the seed mirrors about half the levels,
  the same ones every time.
- **New:** *Ammo in dropped guns* (1–30, default 5).
- **Changed:** the JANUS code letters are code letter keycards, and the
  GoldenEye Key is no longer an item: Cradle opens with the five letters, or
  once every level is beaten.
- **Changed:** the launcher's settings are in two columns of boxes; clearer
  wording; *Load N64 ROM* button (experimental).
- **Fixed:** beating Caverns no longer lets you walk into a locked Cradle.
- **Fixed:** the launcher won't start a second copy of the game.

## [r3](https://github.com/rayanisran/goldeneye-randomizer/releases/tag/r3) (2026-11-01, Windows)

**Race codes changed:** r2 codes (`9-5339-`) don't load in r3; r3 codes start
with `11-e978-`.

- **New goal:** find the code word JANUS. Five code letters are hidden across
  the levels; *Beat every level* is still available.
- **New:** every level except Cradle has a clearance that opens it. Starting
  levels are fully random, and every seed makes you visit at least 10 levels.
- **New:** body armor, the guns lying in the open and Aztec's DAT are
  shuffled too.
- **Changed:** *Original locations* uses only places where the original game
  has an item; spare armor and guns that don't fit are left out of the run.
- **Fixed:** a crash in Facility's labs when Dr. Doak held a gadget; Bunker 2's
  safe and Statue's flight recorder drop now hold their replacement items
  correctly; best times belong to the seed.

## [r2](https://github.com/rayanisran/goldeneye-randomizer/releases/tag/r2) (2026-11-01, Windows)

**Race codes changed:** r1 codes (`8-2029-`) don't load in r2; r2 codes start
with `9-5339-`.

- **Fixed:** a crash when entering any level after finding the Golden Gun.
- **Fixed:** the loud beep at the start of levels.
- **Fixed:** items placed in safes sit inside them, and no key is ever locked
  inside the safe it opens.
- **Fixed:** Dr. Doak and Mishkin always hand you a shuffled item.

## [r1](https://github.com/rayanisran/goldeneye-randomizer/releases/tag/r1) (2026-11-01, Windows)

The first release. Keys, keycards, gadgets and objective items are shuffled
between levels, every seed is checked to be beatable, and race codes let
everyone play the same seed.
