"""Publish this platform's package to the GitHub release named in version.py.

    python -m randomizer.release --platform win64      (Windows PC)
    python -m randomizer.release --platform linux      (Linux PC)
    add --dry-run to see what it would do

One release (tag = version.RELEASE, e.g. r6) holds both platforms. Whichever
PC goes first creates it, tagging the commit it built, with the notes from
CHANGELOG.md; the other checks out that tag, builds and adds its own files.
Each package goes up with its .sha256, which the launcher's update check needs.

Needs the GitHub CLI logged in to the repo's account (`gh auth login`, or
GH_TOKEN set), and the package built first (randomizer/package.py).
"""

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .version import RELEASE

ROOT = Path(__file__).resolve().parent.parent
REPO = "rayanisran/goldeneye-randomizer"
SUFFIX = {"win64": "win64.zip", "linux": "linux.tar.gz"}


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def gh(*args, check=True):
    return subprocess.run(["gh", *args, "--repo", REPO], cwd=ROOT, capture_output=True, text=True, check=check)


def changelog_notes(tag):
    """The CHANGELOG.md section for this release (without its heading)."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## \[?{re.escape(tag)}\]?[ (].*?$\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        raise SystemExit(f"CHANGELOG.md has no section for {tag}: add one first")
    if "not released yet" in m.group(0).splitlines()[0]:
        print(f"note: CHANGELOG.md still says {tag} is not released yet; put the date in its heading")
    return m.group(1).strip() + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--platform", choices=sorted(SUFFIX), required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    tag = RELEASE

    # the package and its checksum
    pkg = ROOT / "dist" / f"GoldenEye-Randomizer-{tag}-{SUFFIX[args.platform]}"
    if not pkg.exists():
        raise SystemExit(f"{pkg} not found: build it first (randomizer/package.py --platform {args.platform})")
    digest = hashlib.sha256(pkg.read_bytes()).hexdigest()
    sha = pkg.with_name(pkg.name + ".sha256")
    sha.write_text(f"{digest}  {pkg.name}\n", encoding="utf-8", newline="\n")

    # the build must be the tagged commit, from a clean tree
    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("the working tree has uncommitted changes: release builds come from a clean checkout")
    head = git("rev-parse", "HEAD")
    remote_tag = git("ls-remote", "--tags", f"https://github.com/{REPO}.git", f"refs/tags/{tag}").split("\t")[0]
    if remote_tag and remote_tag != head:
        raise SystemExit(f"{tag} is commit {remote_tag[:8]} but this checkout is {head[:8]}: "
                         f"`git fetch --tags && git checkout {tag}`, rebuild, and run this again")

    exists = gh("release", "view", tag, check=False).returncode == 0
    files = [str(pkg), str(sha)]
    if exists:
        cmd = ["release", "upload", tag, *files, "--clobber"]
        what = f"add {pkg.name} to the existing release {tag}"
    else:
        notes = Path(tempfile.mkstemp(suffix=".md")[1])
        notes.write_text(changelog_notes(tag), encoding="utf-8")
        cmd = ["release", "create", tag, *files, "--target", head, "--title", f"GoldenEye Randomizer {tag}",
               "--notes-file", str(notes)]
        what = f"create release {tag} at {head[:8]} with {pkg.name} and the CHANGELOG notes"
    print(f"{'would ' if args.dry_run else ''}{what}\n  sha256 {digest}")
    if args.dry_run:
        return
    r = gh(*cmd, check=False)
    if r.returncode:
        sys.exit(r.stderr.strip() or "gh failed")
    print(r.stdout.strip() or "done")


if __name__ == "__main__":
    main()
