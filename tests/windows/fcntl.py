"""Stand-in for the POSIX fcntl module, so homeassistant.runner imports on Windows.

Home Assistant calls fcntl.flock only for its single-execution lock file, which the test
suite never takes. See tests/windows/README.md.
"""

import sys

if sys.platform != "win32":  # pragma: no cover - the real module is there
    raise ImportError("tests/windows is for Windows only; take it off PYTHONPATH")

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


def flock(fd: int, operation: int) -> None:
    raise OSError("fcntl.flock does not exist on Windows")


def fcntl(fd: int, cmd: int, arg: int = 0) -> int:
    raise OSError("fcntl.fcntl does not exist on Windows")


def ioctl(fd: int, request: int, arg: int = 0, mutate_flag: bool = True) -> int:
    raise OSError("fcntl.ioctl does not exist on Windows")
