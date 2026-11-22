"""Run stats from a seed's progress log (data/rando/log-<run id>.txt).

Play time counts only time inside levels: each visit's own mission timer when
the log has it ("<-- Leave X: ... [N s]", from r6 on), else the time between
its Enter and Leave lines. Menus and breaks between sessions don't count.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

_TS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)  (.*)$")
_ENTER = re.compile(r"^--> Enter (.+?) \(")
_LEAVE = re.compile(r"^<-- Leave (.+?): (\w+)(?:.*\[(\d+) s\])?")
_DIED = re.compile(r"^\s*DIED on (.+)$")
_FOUND = re.compile(r"^\s*FOUND item #\d+ on (.+?): (.*)$")
_LETTER = re.compile(r"code letter keycard (\w)", re.I)
_RUN = re.compile(r"\[run (\d+) s\]")   # the in-game run timer (from r6 on)
_ARMOR = re.compile(r"^\s*picked up #\d+ on .+? (?:again )?\((?:respawned )?armor ")


@dataclass
class LevelStats:
    name: str
    seconds: float = 0.0
    visits: int = 0
    deaths: int = 0
    beaten: bool = False


@dataclass
class RunStats:
    seconds: float = 0.0
    deaths: int = 0
    found: int = 0
    armor: int = 0
    letters: list = field(default_factory=list)   # (letter, play seconds when found)
    levels: dict = field(default_factory=dict)    # name -> LevelStats, in first-visit order
    finished_at: float = None                     # play seconds when Cradle was beaten
    run_letters: list = field(default_factory=list)   # (letter, run-timer seconds), when logged
    run_total: float = None                       # run timer when Cradle was beaten

    def timeline(self):
        """(letters with their times, finish time, total): the run timer's when
        the log has it, else play time."""
        if self.run_total or any(t for _, t in self.run_letters):
            return self.run_letters, self.run_total, self.run_total or max(t for _, t in self.run_letters)
        return self.letters, self.finished_at, self.seconds


def parse(text):
    st = RunStats()
    cur, enter_ts, last_ts, done = None, None, None, 0.0   # done: play time of closed visits

    def level(name):
        return st.levels.setdefault(name, LevelStats(name))

    def close(seconds=None):
        nonlocal cur, done
        if cur is None:
            return
        spent = seconds if seconds is not None else max((last_ts - enter_ts).total_seconds(), 0)
        lv = level(cur)
        lv.seconds += spent
        done += spent
        cur = None

    def now():   # play seconds at the current line
        return done + (max((last_ts - enter_ts).total_seconds(), 0) if cur else 0)

    for line in text.splitlines():
        m = _TS.match(line)
        if not m:
            continue
        ts, body = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), m.group(2)
        if body.startswith("=== seed") or body.startswith("--> Enter"):
            close()             # a visit the game was quit out of has no Leave line
        last_ts = ts
        if (e := _ENTER.match(body)):
            cur, enter_ts = e.group(1), ts
            level(cur).visits += 1
        elif (e := _LEAVE.match(body)):
            if cur:
                if e.group(2) == "COMPLETED":
                    level(cur).beaten = True
                close(float(e.group(3)) if e.group(3) else None)
        elif (e := _DIED.match(body)):
            st.deaths += 1
            level(e.group(1)).deaths += 1
        elif (e := _FOUND.match(body)):
            st.found += 1
            if (l := _LETTER.search(e.group(2))):
                st.letters.append((l.group(1).upper(), now()))
                if (r := _RUN.search(body)):
                    st.run_letters.append((l.group(1).upper(), float(r.group(1))))
        elif _ARMOR.match(body):
            st.armor += 1
        elif "CRADLE BEATEN" in body:
            st.finished_at = now()
            if (r := _RUN.search(body)) and int(r.group(1)):
                st.run_total = float(r.group(1))
    close()
    st.seconds = done
    return st


def clock(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
