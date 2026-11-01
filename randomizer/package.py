"""Package the randomizer for sharing (race buddies): one folder, one zip.

    python -m randomizer.package [--platform win64|linux] [--version r1]

Takes the port's own release bundle (tools_pc/bundle-win.sh or
bundle-linux.sh output in dist/: engine, runtime libraries, the first-run ROM
converter; no ROM, no game assets) and adds the randomizer launcher, frozen
with PyInstaller together with randomizer/data/world.json. Each player
supplies their own US ROM; the first launch converts it.

Run it on the platform you are packaging for (PyInstaller does not cross-build).
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

START_HERE = """GoldenEye Randomizer
====================

0. Extract this folder somewhere with a short path, like your Desktop or
   Downloads (very long folder paths can make the first-run setup fail).
1. Put your own GoldenEye 007 US ROM in the data folder, named
   ge007.ntsc-final.z64  (only the US / NTSC-U ROM works).
2. Open "{launcher}".
3. Generate a seed (or paste a race code from your opponent and press
   "Load race seed"), then press PLAY.
   The very first launch takes a little longer: the game builds its files
   from your ROM once.

Racing: one player generates, presses "Copy race code" and sends the code.
The other pastes it under "Race". Both should see the same check words
before you start; if they differ, you are not on the same seed.

Your progress is saved per seed. The game's own settings are in
data/ge007.ini; the randomizer's files are in data/rando/.
"""


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--platform", choices=["win64", "linux"], default="win64" if sys.platform == "win32" else "linux")
    ap.add_argument("--version", default="r1")
    args = ap.parse_args()

    suffix = "win64" if args.platform == "win64" else "linux-x86_64"   # the bundle scripts' names
    base = ROOT / "dist" / f"goldeneye-pc-port-rando-{args.version}-{suffix}"
    if not base.is_dir():
        script = "bundle-win.sh" if args.platform == "win64" else "bundle-linux.sh"
        raise SystemExit(f"{base} not found: run tools_pc/{script} rando-{args.version} first")

    work = ROOT / "dist" / "_launcher-build"   # outside the package, or PyInstaller misresolves it
    name = "GoldenEye Randomizer"
    # entry script outside the package, so PyInstaller imports `randomizer` as a package
    work.mkdir(parents=True, exist_ok=True)
    entry = work / "goldeneye_randomizer.py"
    entry.write_text("from randomizer.launcher import main\n\nmain()\n", encoding="utf-8")
    sep = ";" if args.platform == "win64" else ":"
    run([sys.executable, "-m", "PyInstaller", "--onefile", "--windowed", "--noconfirm", "--name", name,
         "--distpath", str(work / "dist"), "--workpath", str(work / "build"), "--specpath", str(work),
         "--paths", str(ROOT), "--hidden-import", "randomizer.launcher",
         "--add-data", f"{ROOT / 'randomizer' / 'data' / 'world.json'}{sep}randomizer/data",
         str(entry)], cwd=ROOT)
    launcher = work / "dist" / (name + (".exe" if args.platform == "win64" else ""))

    out = ROOT / "dist" / f"GoldenEye-Randomizer-{args.version}-{args.platform}"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(base, out)
    shutil.copy2(launcher, out / launcher.name)
    (out / "data" / "rando").mkdir(parents=True, exist_ok=True)
    (out / "data" / "PUT YOUR ROM HERE.txt").write_text(
        "Copy your GoldenEye 007 US ROM into this folder as ge007.ntsc-final.z64\n", encoding="utf-8")
    (out / "START HERE.txt").write_text(START_HERE.format(launcher=launcher.name), encoding="utf-8")

    if list(out.rglob("*.z64")) or list(out.rglob("*.n64")) or list(out.rglob("*.v64")):
        raise SystemExit("refusing to package: a ROM image is inside the bundle")

    archive = shutil.make_archive(str(out), "zip" if args.platform == "win64" else "gztar",
                                  root_dir=out.parent, base_dir=out.name)
    print(f"\n{archive}")


if __name__ == "__main__":
    main()
