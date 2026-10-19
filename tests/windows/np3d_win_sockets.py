"""pytest plugin: let the Windows event loop build its internal socketpair.

pytest-homeassistant-custom-component bans socket creation outright in its
pytest_runtest_setup hook (pytest_socket.disable_socket). On Windows asyncio's
ProactorEventLoop needs a loopback socketpair for its self-pipe, so without this plugin
every single test errors out in setup with SocketBlockedError - before it has run a line.

We turn that ban into a no-op. The host allow list that phacc installs right before it
(socket_allow_hosts(["127.0.0.1"])) stays in force, so a test still reaches nothing but
loopback; it may only create a socket object. Load it with -p np3d_win_sockets, see
tests/windows/README.md.
"""

import pytest_socket

_real_disable_socket = pytest_socket.disable_socket


def _allow_socket_creation(allow_unix_socket: bool = False) -> None:
    pytest_socket.enable_socket()


def pytest_configure(config) -> None:
    pytest_socket.disable_socket = _allow_socket_creation


def pytest_unconfigure(config) -> None:
    pytest_socket.disable_socket = _real_disable_socket
