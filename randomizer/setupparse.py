"""Read the decomp's level setup sources (assets/obseg/setup) and text banks.

Everything here is read-only: the randomizer never edits these files. Seeds are
applied at level load by the game, so vanilla data stays the reference.
"""

import re
from pathlib import Path

SETUP_DIR = Path("assets/obseg/setup")
TEXT_DIR = Path("assets/obseg/text")
CONSTANTS = Path("src/bondconstants.h")


def _mkshort(a, b):
    return ((a << 8) | (b & 0xFF)) & 0xFFFF


def _mkword(a, b):
    return ((a << 16) | (b & 0xFFFF)) & 0xFFFFFFFF


_EVAL_NS = {"_mkword": _mkword, "_mkshort": _mkshort, "__builtins__": {}}
_FLOAT_SUFFIX = re.compile(r"(\d|\.)f\b")


def _split_top(text):
    """Split on commas that are not inside parentheses, braces or strings."""
    out, depth, cur, quoted, prev = [], 0, [], False, ""
    for ch in text:
        if ch == '"' and prev != "\\":
            quoted = not quoted
        prev = ch
        if quoted:
            cur.append(ch)
            continue
        if ch in "({":
            depth += 1
        elif ch in ")}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [t.strip() for t in out if t.strip()]


def _word(tok):
    tok = _FLOAT_SUFFIX.sub(r"\1", tok)
    val = eval(tok, _EVAL_NS)  # setup tokens are numeric literals and _mk* macros only
    if isinstance(val, float):
        return val
    return val & 0xFFFFFFFF


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def setup_path(root, stem):
    """US build prefers the u/ variant of a setup when one exists."""
    u = root / SETUP_DIR / "u" / f"{stem}.c"
    return u if u.exists() else root / SETUP_DIR / f"{stem}.c"


def _array_body(src, decl_regex):
    m = re.search(decl_regex + r"\s*=\s*\{", src)
    if not m:
        return None
    start = m.end()
    end = src.index("\n};", start)
    return src[start:end]


def _records(body):
    """Split a commented record array into [(type, index, [words])]."""
    out = []
    parts = re.split(r"/\*\s*Type = (\w+); index = (\d+)\s*\*/", body)
    for i in range(1, len(parts), 3):
        typ, idx, words = parts[i], int(parts[i + 1]), parts[i + 2]
        out.append((typ, idx, [_word(t) for t in _split_top(words)]))
    return out


_PAD_RE = re.compile(
    r"\{\s*\{([^}]*)\},\s*\{([^}]*)\},\s*\{([^}]*)\},\s*\"([^\"]*)\"\s*,\s*[^,{}]*(?:,\s*\{([^}]*)\})?\s*\}"
)


def _floats(s):
    return [float(_FLOAT_SUFFIX.sub(r"\1", x.strip())) for x in s.split(",")]


def _pads(body):
    pads = []
    if body is None:
        return pads
    for m in _PAD_RE.finditer(body):
        pad = {"pos": _floats(m.group(1)), "up": _floats(m.group(2)),
               "look": _floats(m.group(3)), "tile": m.group(4)}
        if m.group(5):
            pad["bbox"] = _floats(m.group(5))
        pads.append(pad)
    return pads


def _int_arrays(src, prefix):
    out = {}
    for m in re.finditer(r"s32 " + prefix + r"_(\d+)\[\]\s*=\s*\{([^}]*)\}", src):
        vals = [int(x, 0) for x in m.group(2).replace(" ", "").split(",") if x]
        out[int(m.group(1))] = [v for v in vals if v != -1]
    return out


def parse_setup(path):
    src = Path(path).read_text(encoding="utf-8", errors="replace")
    objects = _records(_array_body(src, r"s32 propDefs\[\]") or "")
    intro = _records(_array_body(src, r"s32 intro\[\]") or "")
    pads = _pads(_array_body(src, r"PadRecord padlist\[\]"))
    pads3d = _pads(_array_body(src, r"BoundPadRecord pad3dlist\[\]"))

    tables = _int_arrays(src, "path_table")
    waypoints = []
    body = _array_body(src, r"waypoint pathwaypoints\[\]") or ""
    for m in re.finditer(r"\{\s*(0x[0-9a-fA-F]+|-?\d+),\s*&path_table_(\d+),\s*(0x[0-9a-fA-F]+|-?\d+)", body):
        pad = int(m.group(1), 0)
        if pad & 0x80000000:
            break  # terminator
        waypoints.append({"pad": pad, "neighbours": tables.get(int(m.group(2)), []),
                          "group": int(m.group(3), 0)})

    neighbours = _int_arrays(src, "path_neighbors")
    members = _int_arrays(src, "path_indeces")
    groups = []
    body = _array_body(src, r"waygroup pathsets\[\]") or ""
    for m in re.finditer(r"&path_neighbors_(\d+),\s*&path_indeces_(\d+)", body):
        groups.append({"neighbours": neighbours.get(int(m.group(1)), []),
                       "waypoints": members.get(int(m.group(2)), [])})

    ai = {}
    body = _array_body(src, r"AIListRecord ailists\[\]") or ""
    for m in re.finditer(r"&(\w+),\s*([^}]+?)\s*\}", body):
        name = m.group(1)
        # Archives uses the readable AI dialect (bondconstants.h set*AIListID)
        expr = m.group(2)
        for macro, base in (("setGlobalAIListID", 0), ("setChrAIListID", 1025), ("setBGAIListID", 4096)):
            expr = re.sub(macro + r"\((\d+)\)", lambda x, b=base: str(int(x.group(1)) + b), expr)
        aid = int(expr, 0)
        script = _array_body(src, r"u8 " + name + r"\[\]") or ""
        lines = [ln.strip().rstrip(",") for ln in script.splitlines()]
        ai[aid] = [ln for ln in lines if ln and not ln.startswith("/*")]

    return {"objects": objects, "intro": intro, "pads": pads, "pads3d": pads3d,
            "waypoints": waypoints, "waygroups": groups, "ai": ai}


def parse_enum(root, enum_name):
    """Return the enum's names indexed by value (explicit values honoured)."""
    src = (root / CONSTANTS).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"typedef enum " + enum_name + r"\s*\{(.*?)\}\s*" + enum_name + ";", src, re.S)
    if not m:
        raise ValueError(f"enum {enum_name} not found")
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    # Conditional entries the ROM build does not define (PORT sentinels, the
    # ALL_BONDS extra Bond bodies) are not part of the ROM's numbering: drop
    # the whole block. Verified against setup data: Bunker 1's Boris is body
    # 6 (only right without the three extra Bonds).
    body = re.sub(r"#ifdef (PORT|ALL_BONDS)\b.*?#endif", "", body, flags=re.S)
    body = re.sub(r"^\s*#[^\n]*$", "", body, flags=re.M)
    names, val = {}, 0
    for item in body.split(","):
        item = item.strip()
        if not item or item.startswith("#"):
            continue
        if "=" in item:
            name, expr = (x.strip() for x in item.split("=", 1))
            by_name = {n: v for v, n in names.items()}
            if expr in by_name:  # alias of an earlier enumerator
                continue
            val = int(expr, 0)
        else:
            name = item
        names[val] = name
        val += 1
    return names


def load_textbanks(root):
    """bank index -> list of English strings. Text ID = bank << 10 | index."""
    src = (root / CONSTANTS).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"typedef enum TEXTBANK_LEVEL_INDEX\s*\{(.*?)\}", src, re.S)
    names = [re.sub(r"/\*.*?\*/", "", x).strip() for x in m.group(1).split(",")]
    names = [n for n in names if n]
    banks = {}
    for i, name in enumerate(names):
        stem = "L" + name[1:].lower() + "E"
        path = root / TEXT_DIR / f"{stem}.c"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        body = _array_body(text, r"char \*" + stem + r"\[\]")
        if body is None:
            continue
        entries = []
        for tok in _split_top(body):
            strs = re.findall(r'"((?:[^"\\]|\\.)*)"', tok)
            entries.append("".join(strs).replace("\\n", " ").strip() if strs else None)
        banks[i] = entries
    return banks


def text(banks, tid):
    if tid is None or tid <= 0:
        return None
    bank, idx = tid >> 10, tid & 0x3FF
    entries = banks.get(bank)
    if entries is None or idx >= len(entries):
        return None
    return entries[idx]


def load_tile_rooms(root, bg):
    """Floor tile name -> room number, from assets/obseg/stan/Tbg_<bg>_all_p_stanZ.c.
    A pad's tile is "p<name><suffix>"; the tile record's first word is name << 8."""
    path = Path(root) / "assets/obseg/stan" / f"Tbg_{bg}_all_p_stanZ.c"
    src = path.read_text(encoding="utf-8", errors="replace")
    return {int(n, 16) >> 8: int(r, 16)
            for n, r in re.findall(r"StandTile tile_\d+ = \{\s*0x([0-9a-fA-F]+), 0x([0-9a-fA-F]+),", src)}
