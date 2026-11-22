"""Update check and in-place update for the launcher.

Looks for the newest GitHub release of the randomizer that has a package for
this platform (GoldenEye-Randomizer-rN-win64.zip or -linux.tar.gz). When it
is newer than this copy (version.RELEASE), the launcher downloads it, checks
it against its .sha256 file and replaces its own folder's program files with
it, keeping the player's data/ (ROM, saves, settings, seeds), then restarts.

GE_RANDO_UPDATE_FEED=<url> (a file:// JSON in the releases-API shape works)
replaces the GitHub address, for testing an update without publishing one.
"""

import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import tarfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .version import RELEASE

REPO = "rayanisran/goldeneye-randomizer"
API = os.environ.get("GE_RANDO_UPDATE_FEED") or f"https://api.github.com/repos/{REPO}/releases?per_page=30"
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


def _curl_download(url, dest, size, progress):
    """The system curl into dest, with progress from the growing file's size."""
    import time
    exe = shutil.which("curl")
    if exe is None:
        raise OSError("no way to make a secure connection on this machine")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([exe, "-fsSL", "-A", AGENT, "-o", str(dest), url],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=flags)
    while proc.poll() is None:
        if progress and size and Path(dest).exists():
            progress(min(Path(dest).stat().st_size / size, 1.0))
        time.sleep(0.2)
    if proc.returncode:
        raise OSError(f"download failed ({proc.stderr.read().decode(errors='replace').strip()})")


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
    _curl_download(url, dest, size, progress)
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




# ------------------------------------------------------------ in-place update
#
# 1. stage(): the running launcher downloads the package into <root>/.update,
#    checks it and unpacks it there.
# 2. It starts the staged launcher with --finish-update <root> <pid> and quits.
# 3. The staged launcher waits for it to exit, apply()s its own folder over
#    <root> (the player's data stays) and starts <root>'s launcher with
#    --cleanup, which deletes .update once the staged one has exited.

STAGE_DIR = ".update"
PLAYER_DATA_RESET = ("pccg-*", "pcmodels-*", "ge007.shaders")   # rebuilt from the ROM / by the game


def stage(rel, root, progress=None):
    """Download, verify and unpack rel under root/.update. progress(fraction)
    covers the download (0-0.95) and unpacking (to 1.0). Returns the unpacked
    package folder."""
    st = Path(root).resolve() / STAGE_DIR
    shutil.rmtree(st, ignore_errors=True)
    st.mkdir(parents=True)
    archive = st / rel.asset
    got = download(rel.url, archive, rel.size, (lambda f: progress(f * 0.95)) if progress else None)
    if rel.sha_url:
        expected = fetch(rel.sha_url).decode("utf-8", "replace").split()[0].lower()
        if got != expected:
            raise ValueError("the download is damaged; try again")
    unpacked = st / "new"
    unpacked.mkdir()
    if rel.asset.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(unpacked)
    else:
        with tarfile.open(archive) as t:
            t.extractall(unpacked, members=_safe_members(t, unpacked))
    archive.unlink()
    if progress:
        progress(1.0)
    tops = list(unpacked.iterdir())
    return tops[0] if len(tops) == 1 and tops[0].is_dir() else unpacked


def wait_for_exit(pid, timeout=30.0):
    """Block until process pid has exited (or timeout)."""
    import time
    end = time.time() + timeout
    if os.name == "nt":
        import ctypes
        SYNCHRONIZE = 0x00100000
        h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if h:
            ctypes.windll.kernel32.WaitForSingleObject(h, int(timeout * 1000))
            ctypes.windll.kernel32.CloseHandle(h)
        return
    while time.time() < end:
        try:
            os.kill(int(pid), 0)
        except OSError:
            return
        time.sleep(0.1)


def _copy_retrying(src, dst, tries=50):
    import time
    for i in range(tries):
        try:
            shutil.copy2(src, dst)
            return
        except PermissionError:   # Windows: a file still open for a moment
            if i == tries - 1:
                raise
            time.sleep(0.2)


class FilesInUse(RuntimeError):
    """The game is open: nothing was replaced, the old version reopens."""


def _check_writable(paths, timeout=20.0):
    """Every program file about to be replaced can be written (the old launcher
    has fully exited, the game isn't running), so nothing is half-replaced."""
    import time
    end = time.time() + timeout
    for dst in paths:
        if not dst.is_file() or dst.is_symlink():
            continue
        while True:
            try:
                with open(dst, "r+b"):
                    break
            except PermissionError:
                if time.time() > end:
                    raise FilesInUse(str(dst))
                time.sleep(0.25)


def apply(staged, root, progress=None):
    """Copy the unpacked package over root. Program files are replaced; in
    data/ only files the player doesn't have yet are added (ROM, saves,
    settings, seeds stay), and the files built from the ROM are removed so the
    new version builds its own on first start (a few seconds)."""
    staged, root = Path(staged), Path(root)
    files = [f for f in staged.rglob("*") if f.is_file() or f.is_symlink()]
    _check_writable([root / f.relative_to(staged) for f in files
                     if f.relative_to(staged).parts[0] != "data"])
    for n, f in enumerate(files):
        rel = f.relative_to(staged)
        dst = root / rel
        if rel.parts[0] == "data" and dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if f.is_symlink():
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            os.symlink(os.readlink(f), dst)
        else:
            _copy_retrying(f, dst)
        if progress:
            progress((n + 1) / len(files))
    for pattern in PLAYER_DATA_RESET:
        for old in (root / "data").glob(pattern):
            if old.is_dir():
                shutil.rmtree(old, ignore_errors=True)
            else:
                old.unlink(missing_ok=True)


def cleanup(stage_dir, timeout=60.0):
    """Delete .update once the staged launcher has let go of it."""
    import time
    end = time.time() + timeout
    while time.time() < end:
        shutil.rmtree(stage_dir, ignore_errors=True)
        if not Path(stage_dir).exists():
            return
        time.sleep(0.5)


def launcher_in(root):
    for name in ("GoldenEye Randomizer.exe", "GoldenEye Randomizer"):
        if (Path(root) / name).exists():
            return Path(root) / name
    return None


def start_detached(args, cwd):
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen([str(a) for a in args], cwd=str(cwd), creationflags=flags,
                            start_new_session=os.name != "nt", close_fds=True)
