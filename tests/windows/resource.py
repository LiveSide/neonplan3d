"""Stand-in for the POSIX resource module, so homeassistant.util.resource imports on Windows.

Home Assistant raises its own file descriptor limit at start-up. Windows has no such limit,
so getrlimit reports one that is already high enough and setrlimit does nothing.
See tests/windows/README.md.
"""

import sys

if sys.platform != "win32":  # pragma: no cover - the real module is there
    raise ImportError("tests/windows is for Windows only; take it off PYTHONPATH")

RLIMIT_NOFILE = 7
RLIM_INFINITY = -1


def getrlimit(which: int) -> tuple[int, int]:
    return (8192, 8192)


def setrlimit(which: int, limits: tuple[int, int]) -> None:
    return None


def getrusage(who: int) -> None:
    raise OSError("resource.getrusage does not exist on Windows")
