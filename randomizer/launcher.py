"""GoldenEye Randomizer launcher: pick settings or paste a race code, play.

    python -m randomizer.launcher          (or the bundled "GoldenEye Randomizer" app)

Looks for the game next to itself: the bundle layout (ge007.x86_64[.exe] and
data/ in the same folder) or the dev tree (build-pc/ and data/).
"""

import os
import struct
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import generate as gen
from . import levels, n64rom, updater, world as worlddata, wsplit
from .version import RELEASE

APP_TITLE = "GoldenEye Randomizer"
DIFF_LABELS = {"agent": "Agent", "secret": "Secret Agent", "00agent": "00 Agent", "ltk": "LTK", "dltk": "DLTK"}
# Normal and Advanced are the same logic today (every trick is a Normal one), so
# the launcher offers Easy and Advanced; codes with Normal still load.
TIERS = [("easy", "Easy", "no tricks needed"),
         ("advanced", "Advanced", "known tricks may be needed (keycard skips, cell warp...)")]
GOAL_CHOICES = {"codes": f"Find the {gen.CODE_WORD} code letter keycards", "all": "Beat every level"}
NOTE = "#555"
ALERT = "#c00000"
WRAP = 720   # pixels: the current-seed summary wraps here instead of widening the window


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


class ProgressWindow(tk.Toplevel):
    """A bar, the percentage and the time left; nothing else."""

    def __init__(self, master, title):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)   # runs to the end
        self.bar = ttk.Progressbar(self, length=320, maximum=1000)
        self.bar.grid(row=0, column=0, padx=16, pady=(16, 6))
        self.text = tk.StringVar(value="0%")
        ttk.Label(self, textvariable=self.text).grid(row=1, column=0, pady=(0, 14))
        self.start, self.last = None, 0.0
        if master is not None and master.winfo_viewable():
            self.transient(master)
            self.geometry(f"+{master.winfo_rootx() + 120}+{master.winfo_rooty() + 120}")
            self.grab_set()

    def set(self, fraction):
        import time
        fraction = max(self.last, min(fraction, 1.0))
        self.last = fraction
        now = time.monotonic()
        if self.start is None and fraction > 0:
            self.start = (now, fraction)
        self.bar["value"] = fraction * 1000
        text = f"{fraction * 100:.0f}%"
        if self.start and fraction < 1.0 and now - self.start[0] > 1.0 and fraction > self.start[1]:
            left = (now - self.start[0]) / (fraction - self.start[1]) * (1.0 - fraction)
            text += f"  -  about {left:.0f} s left" if left < 90 else f"  -  about {left / 60:.0f} min left"
        self.text.set(text)


def finish_update(root, pid):
    """Run by the freshly downloaded launcher: replace the old copy's files,
    then open it (see updater.py)."""
    staged = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    app = tk.Tk()
    app.withdraw()
    bar = ProgressWindow(app, f"Updating to {RELEASE}")
    progress, out = [0.0], {}

    def work():
        try:
            updater.wait_for_exit(pid)
            updater.apply(staged, root, lambda f: progress.__setitem__(0, f))
        except Exception as e:
            out["error"] = e

    t = threading.Thread(target=work, daemon=True)
    t.start()

    def poll():
        bar.set(progress[0])
        if t.is_alive():
            app.after(100, poll)
            return
        if "error" in out and not isinstance(out["error"], updater.FilesInUse):
            messagebox.showerror(APP_TITLE, f"The update didn't work: {out['error']}", parent=bar)
        # the updated copy, or the old one untouched when it failed
        exe = updater.launcher_in(root)
        if exe:
            updater.start_detached([exe, "--cleanup", Path(root) / updater.STAGE_DIR], cwd=root)
        app.destroy()

    app.after(100, poll)
    app.mainloop()


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} {RELEASE}")
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
        self.tier = tk.StringVar(value="advanced")
        self.containers = tk.BooleanVar(value=False)
        self.handover = tk.BooleanVar(value=False)
        self.mirror = tk.StringVar(value="off")
        self.drop_ammo = tk.IntVar(value=gen.DROP_AMMO)
        self.armor_respawn = tk.BooleanVar(value=False)
        self.jp_armor = tk.BooleanVar(value=False)
        self.jp_autoaim = tk.BooleanVar(value=False)
        self.new_locks = tk.IntVar(value=0)
        self.glow_items = tk.BooleanVar(value=True)
        self.carriers = tk.StringVar(value="greyer")
        self.placement = tk.StringVar(value="anywhere")
        self.goal = tk.StringVar(value="codes")
        self.seed_text = tk.StringVar()
        self.race_text = tk.StringVar()
        self.status = tk.StringVar()

        self.columnconfigure(0, weight=1)
        self.build_settings().grid(row=0, column=0, sticky="nsew", padx=8, pady=(6, 2))

        cur = ttk.LabelFrame(self, text="Current seed")
        cur.grid(row=2, column=0, sticky="nsew", padx=8, pady=2)
        cur.columnconfigure(3, weight=1)
        ttk.Label(cur, textvariable=self.status, justify="left", wraplength=WRAP).grid(
            row=0, column=0, columnspan=6, sticky="w", padx=8, pady=(2, 4))
        ttk.Button(cur, text="Copy race code", command=self.copy_code).grid(row=1, column=0, sticky="w", padx=(8, 4), pady=(0, 6))
        ttk.Button(cur, text="Spoiler log...", command=self.open_spoiler).grid(row=1, column=1, sticky="w", padx=(0, 4), pady=(0, 6))
        ttk.Button(cur, text="Load N64 ROM", command=self.make_n64_rom).grid(row=1, column=2, sticky="w", pady=(0, 6))
        ttk.Button(cur, text="PLAY", command=self.play).grid(row=1, column=5, sticky="e", padx=8, pady=(0, 6))

        note = ("Each level opens when you find its clearance, or when you beat the level before it.\n"
                "The covert modem (Dam) and the tracking bug (Frigate) are the same item: either one works for both levels.\n"
                "The camera works for both Bunker 1 and Silo the same way.")
        ttk.Label(self, text=note, foreground=NOTE).grid(row=4, column=0, sticky="w", padx=12, pady=(2, 8))

        self.game = None
        self.timer = wsplit.Timer()
        if wsplit.supported():
            self.build_timer_box()
        self.build_update_row()
        self.refresh()

    def build_settings(self):
        """New-seed settings in two columns of group boxes, seed entry below."""
        outer = ttk.LabelFrame(self, text="New seed")
        left, right = ttk.Frame(outer), ttk.Frame(outer)
        left.grid(row=0, column=0, sticky="nsew", padx=(6, 3))
        right.grid(row=0, column=1, sticky="nsew", padx=(3, 6))
        gap = dict(sticky="nsew", pady=(0, 4))

        box = ttk.LabelFrame(left, text="Difficulty")
        box.grid(row=0, column=0, **gap)
        for i, (key, label) in enumerate(DIFF_LABELS.items()):
            ttk.Radiobutton(box, text=label, value=key, variable=self.diff).grid(row=0, column=i, sticky="w", padx=(8, 4), pady=2)

        box = ttk.LabelFrame(left, text="Logic")
        box.grid(row=1, column=0, **gap)
        for r, (key, label, help_text) in enumerate(TIERS):
            ttk.Radiobutton(box, text=label, value=key, variable=self.tier).grid(row=r, column=0, sticky="w", padx=8)
            ttk.Label(box, text=help_text, foreground=NOTE).grid(row=r, column=1, sticky="w", padx=(0, 8))

        box = ttk.LabelFrame(left, text="Items")
        box.grid(row=2, column=0, **gap)
        ttk.Label(box, text="Item locations").grid(row=0, column=0, sticky="w", padx=8)
        for i, key in enumerate(gen.PLACEMENTS):
            ttk.Radiobutton(box, text=gen.PLACEMENT_LABELS[key], value=key, variable=self.placement).grid(
                row=0, column=1 + i, sticky="w", padx=(0, 8))
        ttk.Checkbutton(box, text="Hide items inside crates and barrels (boxsanity)", variable=self.containers).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=8)
        ttk.Label(box, text="Ammo in dropped guns").grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))
        digits = (self.register(lambda s: s == "" or (s.isdigit() and len(s) <= 2)), "%P")
        ttk.Spinbox(box, from_=gen.DROP_AMMO_RANGE.start, to=gen.DROP_AMMO_RANGE.stop - 1, textvariable=self.drop_ammo,
                    width=4, validate="key", validatecommand=digits).grid(row=2, column=2, sticky="w", pady=(0, 4))

        box = ttk.LabelFrame(left, text="Handicaps")
        box.grid(row=3, column=0, **gap)
        ttk.Checkbutton(box, text="Body armor respawns when you re-enter a level", variable=self.armor_respawn).grid(
            row=0, column=0, sticky="w", padx=8)
        ttk.Checkbutton(box, text="Use JP BAs", variable=self.jp_armor).grid(row=1, column=0, sticky="w", padx=8)
        ttk.Checkbutton(box, text="Use JP auto-aim", variable=self.jp_autoaim).grid(
            row=2, column=0, sticky="w", padx=8, pady=(0, 4))

        box = ttk.LabelFrame(right, text="Goal and locks")
        box.grid(row=0, column=0, **gap)
        for r, key in enumerate(gen.GOALS):
            ttk.Radiobutton(box, text=GOAL_CHOICES[key], value=key, variable=self.goal).grid(
                row=r, column=0, columnspan=2, sticky="w", padx=8)
        ttk.Checkbutton(box, text="Include Aztec and Egyptian", variable=self.bonus).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=8)
        ttk.Label(box, text="New locks on normally open doors").grid(row=4, column=0, sticky="w", padx=8, pady=(0, 4))
        ttk.Spinbox(box, from_=0, to=10, textvariable=self.new_locks, width=4, state="readonly").grid(
            row=4, column=1, sticky="w", padx=(0, 8), pady=(0, 4))

        box = ttk.LabelFrame(right, text="Mirror mode (PC only)")
        box.grid(row=1, column=0, **gap)
        for i, key in enumerate(gen.MIRRORS):
            ttk.Radiobutton(box, text=gen.MIRROR_LABELS[key], value=key, variable=self.mirror).grid(
                row=0, column=i, sticky="w", padx=(8, 0), pady=2)

        box = ttk.LabelFrame(right, text="Display")
        box.grid(row=2, column=0, **gap)
        ttk.Checkbutton(box, text="Keys and gadgets glow gold until you pick them up", variable=self.glow_items).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=8)
        ttk.Checkbutton(box, text="Announce carried items when a level starts", variable=self.handover).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=8)
        ttk.Label(box, text="Guards carrying an item").grid(row=2, column=0, sticky="w", padx=8, pady=(0, 4))
        for i, key in enumerate(gen.CARRIERS):
            ttk.Radiobutton(box, text=gen.CARRIER_LABELS[key], value=key, variable=self.carriers).grid(
                row=2, column=1 + i, sticky="w", padx=(0, 8), pady=(0, 4))

        for col in (left, right):
            col.columnconfigure(0, weight=1)
        seed = ttk.Frame(outer)
        seed.grid(row=1, column=0, sticky="ew", padx=(6, 3), pady=(2, 6))
        ttk.Label(seed, text="Seed (blank = random)").grid(row=0, column=0, sticky="w", padx=(2, 6))
        ttk.Entry(seed, textvariable=self.seed_text, width=16).grid(row=0, column=1, sticky="ew")
        seed.columnconfigure(1, weight=1)
        ttk.Button(seed, text="Generate", command=self.generate_new).grid(row=0, column=2, sticky="e", padx=(6, 0))
        race = ttk.Frame(outer)
        race.grid(row=1, column=1, sticky="ew", padx=(3, 6), pady=(2, 6))
        ttk.Label(race, text="Race code").grid(row=0, column=0, sticky="w", padx=(2, 6))
        ttk.Entry(race, textvariable=self.race_text, width=16).grid(row=0, column=1, sticky="ew")
        race.columnconfigure(1, weight=1)
        ttk.Button(race, text="Load race seed", command=self.generate_race).grid(row=0, column=2, sticky="e", padx=(6, 0))
        return outer

    # ------------------------------------------------------------ updates

    def build_update_row(self):
        """Bottom-right corner: this copy's version and the update button. The
        check runs once at start; a newer release turns both red."""
        row = ttk.Frame(self)
        row.grid(row=5, column=0, sticky="e", padx=8, pady=(0, 6))
        self.update_text = tk.StringVar(value=f"Version {RELEASE}")
        self.update_label = ttk.Label(row, textvariable=self.update_text, foreground=NOTE)
        self.update_label.grid(row=0, column=0, padx=(0, 6))
        style = ttk.Style(self)
        style.configure("Update.TButton", foreground=ALERT)
        style.map("Update.TButton", foreground=[("!disabled", ALERT)])
        self.update_button = ttk.Button(row, text="Check for updates", command=self.check_updates)
        self.update_button.grid(row=0, column=1)
        self.update_release = None
        self.update_busy = False
        self.check_updates(quiet=True)
        self.watch_game()

    def game_running(self):
        return self.game is not None and self.game.poll() is None

    def watch_game(self):
        """Never interrupt a run: updating is off while the game is open."""
        busy = self.game_running()
        if busy != self.update_button.instate(["disabled"]):
            self.update_button.state(["disabled"] if busy else ["!disabled"])
        self.after(1000, self.watch_game)

    def run_in_background(self, work, done, tick=None):
        """work() in a thread; done(result, error) back on the Tk thread."""
        out = {}

        def run():
            try:
                out["result"] = work()
            except Exception as e:   # network, disk, a damaged download...
                out["error"] = e

        t = threading.Thread(target=run, daemon=True)
        t.start()

        def poll():
            if t.is_alive():
                if tick:
                    tick()
                self.after(200, poll)
            else:
                done(out.get("result"), out.get("error"))

        self.after(200, poll)

    def check_updates(self, quiet=False):
        if updater.is_newer(self.update_release):
            self.get_update()
            return
        if self.update_busy:
            return
        self.update_busy = True
        if not quiet:
            self.update_text.set("Checking for updates...")

        def done(rel, err):
            self.update_busy = False
            if err is not None:
                self.update_text.set(f"Version {RELEASE}" if quiet else
                                     f"Version {RELEASE}: couldn't reach GitHub to check")
            elif updater.is_newer(rel):
                self.update_release = rel
                self.update_text.set(f"New update available: {rel.tag}")
                self.update_label.configure(foreground=ALERT)
                self.update_button.configure(text=f"Get {rel.tag}", style="Update.TButton")
                if os.environ.get("GE_RANDO_UPDATE_AUTOCLICK"):   # testing: updater.py GE_RANDO_UPDATE_FEED
                    self.get_update()
            else:
                self.update_text.set(f"Version {RELEASE}" if quiet else f"Version {RELEASE}: up to date")

        self.run_in_background(updater.latest, done)

    def get_update(self):
        """One click: download with a progress bar, then the new version
        replaces this one in the same folder and opens."""
        rel = self.update_release
        if not getattr(sys, "frozen", False):
            webbrowser.open(rel.page)   # running from the source code: nothing to replace
            return
        if self.game_running():
            return   # the button is greyed out while the game runs (watch_game)
        bar = ProgressWindow(self, f"Updating to {rel.tag}")
        progress = [0.0]

        def done(staged, err):
            if err is not None:
                bar.destroy()
                messagebox.showerror(APP_TITLE, f"The update didn't work: {err}")
                return
            bar.set(1.0)
            exe = updater.launcher_in(staged)
            updater.start_detached([exe, "--finish-update", self.root, os.getpid()], cwd=staged)
            self.destroy()

        self.run_in_background(lambda: updater.stage(rel, self.root, lambda f: progress.__setitem__(0, f)),
                               done, lambda: bar.set(progress[0]))

    def build_timer_box(self):
        s = wsplit.load_settings(self.rando)
        self.timer_open = tk.BooleanVar(value=s["open"])
        self.timer_start = tk.BooleanVar(value=s["start"])
        self.timer_path = tk.StringVar(value=s["path"])
        self.timer_note = tk.StringVar()
        box = ttk.LabelFrame(self, text="Timer")
        box.grid(row=3, column=0, sticky="nsew", padx=8, pady=2)
        box.columnconfigure(1, weight=1)
        checks = ttk.Frame(box)
        checks.grid(row=0, column=0, columnspan=3, sticky="w", padx=8)
        ttk.Checkbutton(checks, text="Open WSplit when you press PLAY", variable=self.timer_open).grid(
            row=0, column=0, sticky="w", padx=(0, 12))
        self.timer_start_check = ttk.Checkbutton(
            checks, text="Start the timer with the game, pause it when the game closes", variable=self.timer_start)
        self.timer_start_check.grid(row=0, column=1, sticky="w")
        ttk.Label(box, text="WSplit location").grid(row=1, column=0, sticky="w", padx=8, pady=(2, 4))
        ttk.Entry(box, textvariable=self.timer_path).grid(row=1, column=1, sticky="ew", pady=(2, 4))
        ttk.Button(box, text="Browse...", command=self.browse_timer).grid(row=1, column=2, sticky="e", padx=8, pady=(2, 4))
        self.timer_note_label = ttk.Label(box, textvariable=self.timer_note, foreground=NOTE)
        self.timer_note_label.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))
        for var in (self.timer_open, self.timer_start, self.timer_path):
            var.trace_add("write", lambda *_: self.timer_changed())
        self.show_timer_state()

    def show_timer_state(self):
        on = self.timer_open.get()
        self.timer_start_check.config(state="normal" if on else "disabled")
        missing = on and not Path(self.timer_path.get()).is_file()
        self.timer_note.set("WSplit isn't at this location, so PLAY will start the game without it." if missing else "")
        if missing:
            self.timer_note_label.grid()
        else:
            self.timer_note_label.grid_remove()   # no empty row when there's nothing to say

    def timer_changed(self):
        self.show_timer_state()
        try:
            wsplit.save_settings(self.rando, {"path": self.timer_path.get(), "open": self.timer_open.get(),
                                              "start": self.timer_start.get()})
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"Could not save the timer settings: {e}")

    def browse_timer(self):
        picked = filedialog.askopenfilename(title="WSplit", filetypes=[("WSplit", "WSplit.exe"), ("Programs", "*.exe")])
        if picked:
            self.timer_path.set(str(Path(picked)))

    # -------------------------------------------------------------- actions

    def settings(self):
        return gen.Settings(self.diff.get(), self.bonus.get(), self.tier.get(),
                            self.containers.get(), self.handover.get(), int(self.new_locks.get()),
                            self.glow_items.get(), self.carriers.get(), self.placement.get(), self.goal.get(), self.mirror.get(),
                            self.ammo_drop(), self.armor_respawn.get(), self.jp_armor.get(),
                            self.jp_autoaim.get())

    def ammo_drop(self):
        """The typed ammo amount, kept within the range the game takes."""
        try:
            n = int(self.drop_ammo.get())
        except (tk.TclError, ValueError):
            n = gen.DROP_AMMO
        n = min(max(n, gen.DROP_AMMO_RANGE.start), gen.DROP_AMMO_RANGE.stop - 1)
        self.drop_ammo.set(n)
        return n

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
        if self.game and self.game.poll() is None:
            messagebox.showinfo(APP_TITLE, "The game is already running.")
            return
        problem = self.timer.open(self.rando)
        if problem:
            messagebox.showwarning(APP_TITLE, f"{problem}\n\nThe game will start without it.")
        self.game = subprocess.Popen([str(exe)], cwd=str(self.root))
        self.timer.run_with(self.game)


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
    if len(sys.argv) > 3 and sys.argv[1] == "--finish-update":
        finish_update(Path(sys.argv[2]), int(sys.argv[3]))
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--cleanup":
        threading.Thread(target=updater.cleanup, args=(sys.argv[2],), daemon=True).start()
    Launcher().mainloop()


if __name__ == "__main__":
    main()
