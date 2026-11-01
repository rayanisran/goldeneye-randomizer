#!/bin/bash
# The randomizer's N64 base ROM, built on Linux or WSL:
#   the original decomp (commit ef209c11, which builds byte-identical to the US ROM)
#   + game.patch (the randomizer's hooks into the game, 16K EEPROM support in the
#     1997 libultra, room for its data in the compressed data segment, linker entries)
#   + src/game/rando.c and rando.h from this repo,
# compiled with the IDO 5.3 recompilation the decomp uses.
#
#   bash randomizer/n64/build_base.sh BASEROM.z64 [OUT.z64]
#
# BASEROM is your own GoldenEye 007 (US) ROM. Needs (Ubuntu):
#   apt install binutils-mips-linux-gnu build-essential python3 git curl
# The decomp tree lives in $GE_N64_WORK (default ~/ge-n64).
# Seeds are added to the base ROM afterwards: python -m randomizer.n64rom.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
ROM=$1
OUT=${2:-$HERE/build/ge007-rando-base.z64}
WORK=${GE_N64_WORK:-$HOME/ge-n64}
UPSTREAM=ef209c11
ROM_SHA1=abe01e4aeb033b6c0836819f549c791b26cfde83
IDO_URL=https://github.com/decompals/ido-static-recomp/releases/download/v1.2/ido-5.3-recomp-linux.tar.gz
DATA_ROOM=$((0x14000))   # game.patch's c_data_array size

if [ -z "$ROM" ] || [ ! -f "$ROM" ]; then
    echo "usage: build_base.sh BASEROM.z64 [OUT.z64]"; exit 1
fi
if [ "$(sha1sum < "$ROM" | cut -c1-40)" != "$ROM_SHA1" ]; then
    echo "$ROM is not the GoldenEye 007 US ROM (.z64, sha1 $ROM_SHA1)"; exit 1
fi

# the original decomp (its history is in the randomizer repo)
if [ ! -d "$WORK/.git" ]; then
    git clone -q https://github.com/rayanisran/goldeneye-randomizer.git "$WORK"
fi
cd "$WORK"
git checkout -q -f "$UPSTREAM"

# IDO 5.3, statically recompiled for Linux
if [ ! -x tools/ido5.3_recomp/cc ]; then
    curl -sL -o /tmp/ido53.tar.gz "$IDO_URL"
    tar -xzf /tmp/ido53.tar.gz -C tools/ido5.3_recomp
fi

# the game's assets, extracted from your ROM once
cp "$ROM" baserom.u.z64
if [ ! -f .rando-assets-extracted ]; then
    bash scripts/extract_baserom.u.sh > /tmp/ge-n64-extract.log 2>&1
    touch .rando-assets-extracted
fi
make -C tools -j8 > /tmp/ge-n64-tools.log 2>&1

# the randomizer
git apply "$HERE/game.patch"
tr -d '\r' < "$REPO/src/game/rando.c" > src/game/rando.c
tr -d '\r' < "$REPO/src/game/rando.h" > src/game/rando.h

DEFS="-DVERSION_US -DLANG_US -DREFRESH_NTSC -DLEFTOVERDEBUG -DLEFTOVERSPECTRUM -DBUGFIX_R0 -DBYTEMATCH -DGE_RANDOMIZER"
# the first build of a fresh tree can trip over the decomp's model-file
# conversion racing ahead of make; the second run picks up where it stopped
make -j"$(nproc)" VERSION=US COMPARE=0 "LCDEFS=$DEFS" > /tmp/ge-n64-build.log 2>&1 \
    || make -j"$(nproc)" VERSION=US COMPARE=0 "LCDEFS=$DEFS" > /tmp/ge-n64-build.log 2>&1 \
    || { grep -E "Error|error|\*\*\*" /tmp/ge-n64-build.log | head -20; exit 1; }

# the decomp injects the compressed data segment without checking its room:
# too big, it overwrites the decompressor and the ROM hangs at boot
RZ=$(stat -c%s build/u/data_seg.rz)
if [ "$RZ" -gt "$DATA_ROOM" ]; then
    echo "compressed data segment $RZ bytes, room for $DATA_ROOM: grow c_data_array in game.patch"; exit 1
fi

mkdir -p "$(dirname "$OUT")"
cp build/u/ge007.u.z64 "$OUT"
echo "$OUT (compressed data $RZ of $DATA_ROOM bytes)"
git checkout -q -f "$UPSTREAM"
