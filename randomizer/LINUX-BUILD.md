# Building the Linux package

How to turn a fresh copy of this repo (git clone or GitHub "Download ZIP") into
`dist/GoldenEye-Randomizer-<version>-linux.tar.gz`: one folder a Linux player
extracts, drops their own ROM into, and runs. Written for whoever builds it,
human or coding agent, on an x86-64 Linux machine.

The Windows package is made the same way with `--platform win64`
(`tools_pc/bundle-win.sh`). The Linux one has not been built before, so expect
to fix small things along the way, and test it before sending it.

## 1. Tools

Ubuntu/Debian names; use the equivalents on other distros.

```sh
sudo apt install build-essential cmake git pkg-config patchelf \
                 libsdl2-dev zlib1g-dev libgl1-mesa-dev \
                 python3 python3-venv python3-tk
python3 -m venv .venv && . .venv/bin/activate
pip install pyinstaller
```

The game build does not need the ROM or the asset extraction in
`docs/building.md` (that only regenerates files already committed).

A ZIP download has no `.git`, so `git describe` falls back to `0.0.0-dev`; the
version is passed explicitly below, so that is fine. If the scripts are not
executable after unzipping: `chmod +x build-pc.sh tools_pc/*.sh randomizer/n64/*.sh`.

## 2. Build the game

```sh
./build-pc.sh ntsc-final          # -> build-pc/ge007.x86_64
```

`GE_RANDOMIZER` is on by default (CMake option), so this is the randomizer
build, not the plain port.

## 3. Freeze the first-run ROM converter

The game runs this once on a player's machine to build its files from their ROM.

```sh
python3 -m PyInstaller --onefile --name ge007-convert \
    --distpath tools_pc/dist/prepare-assets \
    tools_pc/dist/prepare-assets/prepare-assets.py
```

## 4. Bundle and package

The release name comes from `randomizer/version.py` (`RELEASE = "r6"`, say):

```sh
tools_pc/bundle-linux.sh rando-r6                     # -> dist/goldeneye-pc-port-rando-r6-linux-x86_64/
python3 -m randomizer.package --platform linux       # -> dist/GoldenEye-Randomizer-r6-linux.tar.gz
pip install certifi                                   # optional: bundled as the update check's TLS fallback
```

`bundle-linux.sh` copies SDL2 next to the game and sets its rpath, so players
need no packages. `package.py` adds the launcher (tkinter, frozen with
PyInstaller), `START HERE.txt` and an empty `data/`, and refuses to package if
a ROM ended up inside.

## 5. Publish

One GitHub release holds both platforms. The Windows zip is usually published
first, from another machine, and that creates the release and its tag. Build
the Linux package from that same tag, then add it:

```sh
git fetch --tags && git checkout r6                   # the tag = RELEASE in randomizer/version.py
# ... build and package (steps 2-4) ...
python3 -m randomizer.release --platform linux --dry-run
python3 -m randomizer.release --platform linux        # adds the tar.gz + .sha256 to release r6
```

If the release doesn't exist yet, the same command creates it (tagging this
commit, notes from `CHANGELOG.md`) and the Windows zip gets added later. It
needs the GitHub CLI logged in to the repo's account (`gh auth login`, or
`GH_TOKEN`), and refuses a checkout with uncommitted changes or one that isn't
the tagged commit. The launcher's update check only offers a release that has
a package for its own platform, checked against the `.sha256`.

## 6. Test before sending

In a new empty folder, outside the repo:

1. Extract the tarball.
2. Copy a US ROM into its `data/` as `ge007.ntsc-final.z64`.
3. Run `./GoldenEye\ Randomizer`. Generate a seed and press PLAY. The first
   launch converts the ROM (takes a while), then the game should start in a
   randomizer level with the seed loaded.

Notes:

- The WSplit timer box only exists on Windows; the launcher hides it on Linux.
- Long folder paths can break the first-run converter; keep it near `~`.
- glibc of the build machine sets the minimum for players. Building on an
  older distro (e.g. Ubuntu 22.04) makes the package run on more machines.
- Never commit or package a ROM.
