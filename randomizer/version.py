"""This copy's release name, as on GitHub (r1, r2, ...).

Bump it (r6 -> r7) before building the next release: the launcher's update
check compares it with the newest release that has a package for its platform,
and package.py names its zip/tar.gz after it. Windows and Linux packages built
from the same commit go on the same release (tag = RELEASE).
"""

RELEASE = "r6"
