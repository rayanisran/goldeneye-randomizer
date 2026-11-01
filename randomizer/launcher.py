"""GoldenEye Randomizer launcher: pick settings or paste a race code, play.

    python -m randomizer.launcher          (or the bundled "GoldenEye Randomizer" app)

Looks for the game next to itself: the bundle layout (ge007.x86_64[.exe] and
data/ in the same folder) or the dev tree (build-pc/ and data/).
"""

import os
import struct
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import generate as gen
from . import levels, n64rom, world as worlddata

APP_TITLE = "GoldenEye Randomizer"
DIFF_LABELS = {"agent": "Agent", "secret": "Secret Agent", "00agent": "00 Agent"}
TIER_LABELS = {"easy": "Easy", "normal": "Normal", "advanced": "Advanced"}
TIER_HELP = ("Easy: no tricks needed.  Normal: known tricks may be needed (keycard skips, guards\n"
             "opening doors, the Bunker 2 cell warp...).  Advanced: Normal plus glitches.")


def game_root():
    """Folder holding data/ and the game executable."""
    here = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    for cand in (here, here.parent, Path.cwd()):
        if (cand / "data").is_dir() or any((cand / n).exists() for n in exe_names()):
            return cand
    return here


def exe_names():
    return ["ge007.x86_64.exe", "build-pc/ge007.x86_64.exe"] if os.name == "nt" else \
           ["ge007.x86_64", "build-pc/ge007.x86_64"]


def find_exe(root):
    for n in exe_names():
        if (root / n).exists():
            return root / n
    return None


def read_progress(rando, code):
    """(levels beaten, levels total, items found, items total, code letters found
    as "J A _ _ _" or None) from the save, or None."""
    seed_path = rando / "seed.bin"
    if not seed_path.exists():
        return None
    b = seed_path.read_bytes()
    lo, hi = struct.unpack_from("<II", b, 8)
    nitems = struct.unpack_from("<H", b, 22)[0]
    total = 20 if b[7] & 1 else 18
    letters = {b[68 + i * 64 + 61]: i for i in range(nitems) if b[68 + i * 64 + 7] == 6}   # KIND_LETTER
    save = rando / f"save-{(hi << 32) | lo:016x}.bin"
    bits = struct.unpack_from("<8I", save.read_bytes(), 20) if save.exists() else (0,) * 8
    beaten = bin(struct.unpack_from("<I", save.read_bytes(), 16)[0]).count("1") if save.exists() else 0
    found = sum(bin(x).count("1") for x in bits)
    placed = sum(1 for i in range(nitems) if b[68 + i * 64 + 8] != 0xFF)   # 0xFF: left out of the run
    code = " ".join(c if letters.get(n) is not None and bits[letters[n] >> 5] >> (letters[n] & 31) & 1 else "_"
                    for n, c in enumerate(gen.CODE_WORD)) if letters else None
    return beaten, total, found, placed, code


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.resizable(False, False)
        self.root = game_root()
        self.rando = self.root / "data" / "rando"
        try:
            self.world = worlddata.load()
        except SystemExit as e:
            messagebox.showerror(APP_TITLE, str(e))
            raise

        self.diff = tk.StringVar(value="agent")
        self.bonus = tk.BooleanVar(value=True)
        self.tier = tk.StringVar(value="normal")
        self.containers = tk.BooleanVar(value=False)
        self.handover = tk.BooleanVar(value=False)
        self.new_locks = tk.IntVar(value=0)
        self.glow_items = tk.BooleanVar(value=True)
        self.carriers = tk.StringVar(value="greyer")
        self.placement = tk.StringVar(value="anywhere")
        self.goal = tk.StringVar(value="codes")
        self.seed_text = tk.StringVar()
        self.race_text = tk.StringVar()
        self.status = tk.StringVar()

        pad = dict(padx=10, pady=4)
        box = ttk.LabelFrame(self, text="New seed")
        box.grid(row=0, column=0, sticky="nsew", **pad)
        ttk.Label(box, text="Difficulty").grid(row=0, column=0, sticky="w", padx=8)
        for i, (key, label) in enumerate(DIFF_LABELS.items()):
            ttk.Radiobutton(box, text=label, value=key, variable=self.diff).grid(row=0, column=1 + i, sticky="w")
        ttk.Label(box, text="Logic").grid(row=1, column=0, sticky="w", padx=8)
        for i, (key, label) in enumerate(TIER_LABELS.items()):
            ttk.Radiobutton(box, text=label, value=key, variable=self.tier).grid(row=1, column=1 + i, sticky="w")
        ttk.Label(box, text=TIER_HELP, foreground="#555").grid(row=2, column=0, columnspan=4, sticky="w", padx=8)
        checks = [
            (self.bonus, "Include Aztec and Egyptian"),
            (self.containers, "Hide items inside crates and barrels"),
            (self.handover, "Announce carried items when a level starts (hints where they're used)"),
            (self.glow_items, "Small items still to find glow gold (keys, keycards, mines...)"),
        ]
        for r, (var, text) in enumerate(checks, start=4):
            ttk.Checkbutton(box, text=text, variable=var).grid(row=r, column=0, columnspan=4, sticky="w", padx=8)
        ttk.Label(box, text="Item locations").grid(row=3, column=0, sticky="w", padx=8)
        for i, key in enumerate(gen.PLACEMENTS):
            ttk.Radiobutton(box, text=gen.PLACEMENT_LABELS[key], value=key, variable=self.placement).grid(
                row=3, column=1 + 2 * i, columnspan=2, sticky="w")
        ttk.Label(box, text="Guards carrying an item").grid(row=8, column=0, sticky="w", padx=8)
        for i, key in enumerate(gen.CARRIERS):
            ttk.Radiobutton(box, text=gen.CARRIER_LABELS[key], value=key, variable=self.carriers).grid(
                row=8, column=1 + i, sticky="w")
        ttk.Label(box, text="New locks").grid(row=9, column=0, sticky="w", padx=8)
        ttk.Spinbox(box, from_=0, to=10, textvariable=self.new_locks, width=4, state="readonly").grid(
            row=9, column=1, sticky="w")
        ttk.Label(box, text="doors that are normally open get locked; each new key is named for its level",
                  foreground="#555").grid(row=9, column=2, columnspan=2, sticky="w")
        ttk.Label(box, text="Goal").grid(row=10, column=0, sticky="nw", padx=8)
        for i, key in enumerate(gen.GOALS):
            ttk.Radiobutton(box, text=gen.GOAL_LABELS[key], value=key, variable=self.goal).grid(
                row=10 + i, column=1, columnspan=3, sticky="w")
        ttk.Label(box, text="Seed (blank = random)").grid(row=12, column=0, sticky="w", padx=8, pady=(6, 2))
        ttk.Entry(box, textvariable=self.seed_text, width=22).grid(row=12, column=1, columnspan=2, sticky="w", pady=(6, 2))
        ttk.Button(box, text="Generate", command=self.generate_new).grid(row=12, column=3, sticky="e", padx=8, pady=(6, 6))

        race = ttk.LabelFrame(self, text="Race: paste the code your opponent sends you")
        race.grid(row=1, column=0, sticky="nsew", **pad)
        ttk.Entry(race, textvariable=self.race_text, width=40).grid(row=0, column=0, padx=8, pady=6)
        ttk.Button(race, text="Load race seed", command=self.generate_race).grid(row=0, column=1, padx=8)

        cur = ttk.LabelFrame(self, text="Current seed")
        cur.grid(row=2, column=0, sticky="nsew", **pad)
        ttk.Label(cur, textvariable=self.status, justify="left").grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=4)
        ttk.Button(cur, text="Copy race code", command=self.copy_code).grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Button(cur, text="Spoiler log...", command=self.open_spoiler).grid(row=1, column=1, sticky="w", pady=6)
        ttk.Button(cur, text="N64 ROM...", command=self.make_n64_rom).grid(row=1, column=2, sticky="w", pady=6)
        ttk.Button(cur, text="PLAY", command=self.play).grid(row=1, column=3, sticky="e", padx=8, pady=6)

        note = ("Each level opens when you find its clearance, or when you beat the level before it.\n"
                "Good to know: the covert modem (Dam) and the tracking bug (Frigate) are the same item, so either\n"
                "one works for both levels. The camera is shared by Bunker 1 and Silo the same way.")
        ttk.Label(self, text=note, foreground="#555").grid(row=3, column=0, sticky="w", padx=12, pady=(0, 10))

        self.refresh()

    # -------------------------------------------------------------- actions

    def settings(self):
        return gen.Settings(self.diff.get(), self.bonus.get(), self.tier.get(),
                            self.containers.get(), self.handover.get(), int(self.new_locks.get()),
                            self.glow_items.get(), self.carriers.get(), self.placement.get(), self.goal.get())

    def run(self, seed, settings):
        if (self.rando / "seed.bin").exists() and not messagebox.askyesno(
                APP_TITLE, "Replace the current seed? Its progress stays saved, but the game will load the new one."):
            return
        self.config(cursor="watch")
        self.update()
        try:
            res = gen.generate(seed, settings, self.world)
            gen.write(res, self.rando)
        except gen.GenerationError as e:
            messagebox.showerror(APP_TITLE, f"Could not build that seed: {e}")
        finally:
            self.config(cursor="")
        self.refresh()

    def generate_new(self):
        text = self.seed_text.get().strip()
        try:
            seed = int(text) if text else gen.new_seed()
        except ValueError:
            messagebox.showerror(APP_TITLE, "The seed has to be a whole number (or blank for a random one).")
            return
        self.run(seed, self.settings())

    def generate_race(self):
        try:
            seed, settings = gen.parse_race_code(self.race_text.get(), self.world)
        except (ValueError, IndexError) as e:
            messagebox.showerror(APP_TITLE, f"That race code doesn't work here: {e}")
            return
        self.run(seed, settings)

    def current(self):
        p = self.rando / "current.txt"
        if not p.exists():
            return None, None
        lines = p.read_text(encoding="utf-8").splitlines()
        return (lines + ["", ""])[0], (lines + ["", ""])[1]

    def refresh(self):
        code, words = self.current()
        if not code:
            self.status.set("No seed yet: generate one or load a race code.")
            return
        prog = read_progress(self.rando, code)
        try:
            _, s = gen.parse_race_code(code, self.world)
            desc = gen.describe(s)
        except ValueError:
            desc = "(made by a different randomizer version)"
        text = f"Race code:  {code}\nCheck words:  {words}\n{desc}"
        if prog:
            text += f"\nProgress: {prog[0]} of {prog[1]} levels beaten, {prog[2]} of {prog[3]} items found"
            if prog[4]:
                text += f", code {prog[4]}"
        self.status.set(text)

    def copy_code(self):
        code, words = self.current()
        if code:
            self.clipboard_clear()
            self.clipboard_append(code)
            messagebox.showinfo(APP_TITLE, f"Copied {code}\n\nBoth racers should see the check words:\n{words}")

    def open_spoiler(self):
        code, _ = self.current()
        path = self.rando / f"spoiler-{code}.txt" if code else None
        if not path or not path.exists():
            messagebox.showinfo(APP_TITLE, "No spoiler log for this seed.")
            return
        if messagebox.askyesno(APP_TITLE, "Open the spoiler log? It shows where every item is."):
            if os.name == "nt":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", str(path)])

    def make_n64_rom(self):
        """The current seed as an N64 ROM (EverDrive / emulator): the base ROM
        from randomizer/n64/build_base.sh plus this seed."""
        code, _ = self.current()
        if not code:
            messagebox.showinfo(APP_TITLE, "Generate a seed or load a race code first.")
            return
        try:
            seed, settings = gen.parse_race_code(code, self.world)
        except ValueError:
            messagebox.showerror(APP_TITLE, "The current seed was made by a different randomizer version.")
            return
        base = n64rom.find_base(self.root)
        if base is None:
            if not messagebox.askokcancel(
                    APP_TITLE, "Pick the N64 base ROM (ge007-rando-base.z64).\n\nIt's built once from your own "
                               "GoldenEye ROM with randomizer/n64/build_base.sh (Linux or WSL), see the README."):
                return
            picked = filedialog.askopenfilename(title="N64 base ROM", filetypes=[("N64 ROM", "*.z64")])
            if not picked:
                return
            base = Path(picked)
        out = filedialog.asksaveasfilename(title="Save the N64 ROM", defaultextension=".z64",
                                           initialfile=f"goldeneye-rando-{code}.z64",
                                           filetypes=[("N64 ROM", "*.z64")])
        if not out:
            return
        self.config(cursor="watch")
        self.update()
        try:
            res = gen.generate(seed, settings, self.world)
            Path(out).write_bytes(n64rom.patch(base.read_bytes(), gen.to_seedfile(res).pack()))
        except (gen.GenerationError, ValueError, OSError) as e:
            messagebox.showerror(APP_TITLE, f"Could not make the N64 ROM: {e}")
            return
        finally:
            self.config(cursor="")
        messagebox.showinfo(APP_TITLE, f"Saved {out}\n\nExperimental, not yet tested on a real N64. It needs an "
                                       "Expansion Pak, and the save type set to EEPROM 16K (EverDrive OS 3.x "
                                       "picks that up from the ROM). Items don't glow on the N64.")

    def play(self):
        exe = find_exe(self.root)
        if exe is None:
            messagebox.showerror(APP_TITLE, f"Can't find the game next to {self.root}.")
            return
        rom = self.root / "data" / "ge007.ntsc-final.z64"
        if not rom.exists():
            messagebox.showerror(APP_TITLE, "Put your GoldenEye US ROM in the data folder as\n"
                                            f"{rom}\nThe first launch then builds the game files from it.")
            return
        if not (self.rando / "seed.bin").exists():
            messagebox.showinfo(APP_TITLE, "Generate a seed or load a race code first.")
            return
        subprocess.Popen([str(exe)], cwd=str(self.root))


def selftest(path):
    """--selftest FILE: generate one seed with the built-in world data, no window."""
    try:
        world = worlddata.load()
        res = gen.generate(1, gen.Settings(), world)
        Path(path).write_text(f"ok {res['code']} {gen.check_words(gen.to_seedfile(res).pack())}\n")
    except Exception as e:   # report anything, this runs without a console
        Path(path).write_text(f"fail {e!r}\n")


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
        return
    Launcher().mainloop()


if __name__ == "__main__":
    main()
