"""Update check for the launcher.

Looks for the newest GitHub release of the randomizer that has a package for
this platform (GoldenEye-Randomizer-rN-win64.zip or -linux.tar.gz) and, when
it is newer than this copy (version.RELEASE), downloads it, checks it against
its .sha256 file, unpacks it next to this copy and copies the player's ROM,
game settings and seeds into it. This copy is left as it was.
"""

import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .version import RELEASE

REPO = "rayanisran/goldeneye-randomizer"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
PAGE = f"https://github.com/{REPO}/releases"
AGENT = "goldeneye-randomizer-launcher"


def release_number(tag):
    m = re.fullmatch(r"r(\d+)", (tag or "").strip().lower())
    return int(m.group(1)) if m else -1


CURRENT = release_number(RELEASE)


def package_suffix():
    return "-win64.zip" if os.name == "nt" else "-linux.tar.gz"


@dataclass
class Release:
    tag: str
    number: int
    asset: str        # file name
    url: str          # its download URL
    size: int
    sha_url: str      # the .sha256 next to it, or ""
    page: str         # the release's web page


def _contexts():
    """TLS setups to try in turn: the system's certificates, then certifi's
    (some Windows machines lack an intermediate certificate Python won't fetch)."""
    yield None
    try:
        import certifi   # bundled into the frozen launcher when installed at build time
        yield ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass


def _open(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/vnd.github+json"})
    err = None
    for ctx in _contexts():
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except urllib.error.URLError as e:
            if not isinstance(getattr(e, "reason", None), ssl.SSLError):
                raise
            err = e
    raise err


def _curl(url, timeout, out=None):
    """Last resort: the system curl (Windows 10+ and most Linux have one), which
    uses the system's own certificate handling."""
    exe = shutil.which("curl")
    if exe is None:
        raise OSError("no way to make a secure connection on this machine")
    cmd = [exe, "-fsSL", "--max-time", str(max(timeout, 600) if out else timeout), "-A", AGENT, url]
    if out:
        cmd[1:1] = ["-o", str(out)]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(cmd, check=True, capture_output=True, creationflags=flags).stdout


def fetch(url, timeout=15):
    try:
        with _open(url, timeout) as r:
            return r.read()
    except urllib.error.URLError as e:
        if not isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise
        return _curl(url, timeout)


def download(url, dest, size=0, progress=None, timeout=30):
    """Save url to dest; returns its sha256 hex digest."""
    digest = hashlib.sha256()
    try:
        with _open(url, timeout) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or size or 0)
            done = 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(min(done / total, 1.0))
        return digest.hexdigest()
    except urllib.error.URLError as e:
        if not isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise
    _curl(url, timeout, out=dest)   # no progress this way
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    if progress:
        progress(1.0)
    return digest.hexdigest()


def latest(timeout=8):
    """Newest published release with a package for this platform, or None."""
    releases = json.loads(fetch(API, timeout))
    best = None
    for rel in releases:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        num = release_number(rel.get("tag_name"))
        assets = {a["name"]: a for a in rel.get("assets", [])}
        pkg = next((a for name, a in assets.items() if name.endswith(package_suffix())), None)
        if num < 0 or pkg is None or (best and best.number >= num):
            continue
        sha = assets.get(pkg["name"] + ".sha256")
        best = Release(rel["tag_name"], num, pkg["name"], pkg["browser_download_url"], pkg.get("size", 0),
                       sha["browser_download_url"] if sha else "", rel.get("html_url") or PAGE)
    return best


def is_newer(rel):
    return rel is not None and rel.number > CURRENT


def _safe_members(tar, dest):
    dest = dest.resolve()
    for m in tar.getmembers():
        target = (dest / m.name).resolve()
        if dest not in target.parents and target != dest:
            raise ValueError(f"unsafe path in the download: {m.name}")
        if m.issym() or m.islnk():
            link = (target.parent / m.linkname).resolve()
            if dest not in link.parents:
                raise ValueError(f"unsafe link in the download: {m.name}")
    return tar.getmembers()


def install(rel, current_root, progress=None):
    """Download rel, unpack it next to current_root and carry the player's files
    over. Returns the new folder. progress(fraction) is called while downloading."""
    parent = Path(current_root).resolve().parent
    tmp = Path(tempfile.mkdtemp(prefix="ge-rando-update-", dir=parent))
    try:
        archive = tmp / rel.asset
        got = download(rel.url, archive, rel.size, progress)
        if rel.sha_url:
            expected = fetch(rel.sha_url).decode("utf-8", "replace").split()[0].lower()
            if got != expected:
                raise ValueError("the download is damaged (checksum mismatch); try again")

        unpacked = tmp / "unpacked"
        unpacked.mkdir()
        if rel.asset.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                z.extractall(unpacked)
        else:
            with tarfile.open(archive) as t:
                t.extractall(unpacked, members=_safe_members(t, unpacked))
        tops = [p for p in unpacked.iterdir()]
        top = tops[0] if len(tops) == 1 and tops[0].is_dir() else unpacked

        new_root = parent / (top.name if top is not unpacked else rel.asset.split(".")[0])
        if new_root.exists():
            new_root = parent / f"{new_root.name}-{os.getpid()}"
        shutil.move(str(top), str(new_root))
        carry_over(Path(current_root), new_root)
        return new_root
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def carry_over(old, new):
    """The player's ROM, game settings and randomizer seeds/saves; the new copy
    builds its own game files from the ROM on first start."""
    old_data, new_data = old / "data", new / "data"
    new_data.mkdir(exist_ok=True)
    if not old_data.is_dir():
        return
    for f in old_data.iterdir():
        if f.is_file() and (f.suffix.lower() in (".z64", ".n64", ".v64") or f.name == "ge007.ini"):
            if not (new_data / f.name).exists():
                shutil.copy2(f, new_data / f.name)
    if (old_data / "rando").is_dir():
        shutil.copytree(old_data / "rando", new_data / "rando", dirs_exist_ok=True)


def launcher_in(root):
    for name in ("GoldenEye Randomizer.exe", "GoldenEye Randomizer"):
        if (root / name).exists():
            return root / name
    return None
