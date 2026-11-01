"""Crash check for the N64 ROM: every level of a few seeds, booted straight in
under Mupen64Plus (Windows console build). Each run must log entering the right
level and reach five seconds of play (the in-game "check" line) with no
emulator error; level-heap use is reported per level.

    python -m randomizer.n64.validate --base build/ge007-rando-base.z64 \
        --emulator C:/path/mupen64plus/Release [--seeds 3] [--difficulty agent] [--levels dam,facility]
        [--no-expansion]

The test ROMs carry the tokens -level_NN -hardN -rlog (see rando.c
randoBootTokens): the game boots into the level and logs to the IS-Viewer port,
which Mupen64Plus prints as "IS64: ...". Normal ROMs carry no tokens.
"""

import argparse
import concurrent.futures
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .. import generate as gen, levels, n64rom, world as worlddata

STAGE_IDS = {"dam": 33, "facility": 34, "runway": 35, "surface1": 36, "bunker1": 9, "silo": 20, "frigate": 26,
             "surface2": 43, "bunker2": 27, "statue": 22, "archives": 24, "streets": 29, "depot": 30, "train": 25,
             "jungle": 37, "control": 23, "caverns": 39, "cradle": 41, "aztec": 28, "egyptian": 32}
FRAMES = 2400          # past the intro and five seconds of play on every level
TIMEOUT = 240          # seconds of wall clock before a run counts as hung


def run_level(emu, rom, work, expansion, name):
    """One emulator run of level `name`: (ok, summary, heap line or '')."""
    work.mkdir(parents=True, exist_ok=True)
    cmd = [str(emu / "mupen64plus-ui-console.exe"), "--configdir", str(work), "--datadir", str(emu),
           "--plugindir", str(emu), "--nosaveoptions", "--noosd", "--windowed", "--resolution", "320x240",
           "--emumode", "2", "--gfx", "mupen64plus-video-glide64mk2.dll", "--audio", "dummy",
           "--input", "mupen64plus-input-sdl.dll", "--rsp", "mupen64plus-rsp-hle.dll",
           "--set", f"Core[ScreenshotPath]={work}", "--set", f"Core[SaveSRAMPath]={work}",
           "--set", f"Core[DisableExtraMem]={'False' if expansion else 'True'}",
           "--testshots", str(FRAMES), str(rom)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=TIMEOUT).stdout
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return False, "hung (no frame %d within %ds)" % (FRAMES, TIMEOUT), last_log(out)
    log = [ln.split("IS64: ", 1)[1] for ln in out.splitlines() if "IS64: " in ln]
    errors = [ln for ln in out.splitlines() if "Core Error" in ln and "config file" not in ln]
    heap = next((ln.strip() for ln in log if ln.strip().startswith("heap:")), "")
    if errors:
        return False, errors[0], heap
    entered = next((ln for ln in log if ln.startswith("--> Enter")), None)
    if entered is None:
        return False, "never entered the level", heap
    if not entered.startswith(f"--> Enter {name} ("):
        return False, "patched as the wrong level: " + entered.split(".")[0], heap
    if not any(ln.strip().startswith("check:") for ln in log):
        return False, "didn't reach five seconds of play", heap
    if "Captured screenshot for frame" not in out:
        return False, "no frame %d" % FRAMES, heap
    return True, next(ln for ln in log if ln.startswith("--> Enter")).split(".")[0], heap


def last_log(out):
    log = [ln for ln in (out or "").splitlines() if "IS64: " in ln]
    return log[-1].split("IS64: ", 1)[1] if log else ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="the randomizer base ROM")
    ap.add_argument("--emulator", required=True, help="folder with mupen64plus-ui-console.exe and its plugins")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--difficulty", choices=gen.DIFFS, default="agent")
    ap.add_argument("--levels", help="comma-separated level keys (default: all 20)")
    ap.add_argument("--no-expansion", action="store_true", help="4 MB, no Expansion Pak")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args(argv)

    emu = Path(a.emulator)
    base = Path(a.base).read_bytes()
    world = worlddata.load()
    keys = a.levels.split(",") if a.levels else [lv.key for lv in levels.ALL]
    tmp = Path(tempfile.mkdtemp(prefix="ge-n64-validate-"))
    jobs, results = [], []
    for seed in range(a.first_seed, a.first_seed + a.seeds):
        settings = gen.Settings(difficulty=a.difficulty, tier="advanced", placement="original", goal="codes",
                                containers=False, show_handover=False, glow_items=False)
        res = gen.generate(seed, settings, world)
        blob = gen.to_seedfile(res).pack()
        for key in keys:
            # the game reads exactly two digits ("-level_09", not "-level_9")
            tokens = f"-level_{STAGE_IDS[key]:02d} -hard{gen.DIFFS.index(a.difficulty)} -rlog"
            rom = tmp / f"s{seed}-{key}.z64"
            rom.write_bytes(n64rom.patch(base, blob, tokens))
            jobs.append((res["code"], key, rom, tmp / f"s{seed}-{key}"))

    with concurrent.futures.ThreadPoolExecutor(a.jobs) as pool:
        names = {lv.key: lv.name for lv in levels.ALL}
        futures = {pool.submit(run_level, emu, rom, work, not a.no_expansion, names[key]): (code, key)
                   for code, key, rom, work in jobs}
        for fut in concurrent.futures.as_completed(futures):
            code, key = futures[fut]
            ok, summary, heap = fut.result()
            results.append((code, key, ok, summary, heap))
            print(f"{'ok  ' if ok else 'FAIL'} {code} {key:9} {summary[:70]:70} {heap}", flush=True)

    bad = [r for r in results if not r[2]]
    print(f"\n{len(results) - len(bad)} of {len(results)} level runs fine"
          f" ({'4 MB' if a.no_expansion else 'Expansion Pak'}, {a.difficulty})")
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
