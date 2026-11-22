"""This copy's release name, as on GitHub: rMAJOR or rMAJOR.MINOR.

- Major (r6 -> r7): a normal release. Race codes may change (LOGIC_VERSION),
  so everyone in a race needs the same major number.
- Minor (r6 -> r6.1): a hotfix that changes no race code and no save. r6.1
  races r6, and LOGIC_VERSION must stay the same.

Bump it before building the next release: the launcher's update check
compares it with the newest release that has a package for its platform, and
package.py names its zip/tar.gz after it. Windows and Linux packages built
from the same commit go on the same release (tag = RELEASE). Add the release
to CHANGELOG.md at the same time.
"""

RELEASE = "r6.1"
