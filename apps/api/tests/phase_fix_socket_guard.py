"""Test-only socket guard; permit CPython's own local socketpair construction.

Windows uses a loopback TCP connection for socket.socketpair().  Blocking every
socket.connect call prevents asyncio from creating its internal wakeup pipe.
The exception here is limited to the executing thread, the socketpair call,
and a literal loopback address.  Normal loopback and remote connects stay
blocked.  This module is never imported by the real collector.
"""
from contextlib import contextmanager
import socket
from threading import local


class OfflineSocketGuard:
    def __init__(self):
        self._scope = local()
        self.socketpair_calls = 0
        self.allowed_pair_connects = 0
        self.blocked_connects = 0

    @property
    def inside_socketpair(self):
        return bool(getattr(self._scope, "depth", 0))

    @contextmanager
    def _socketpair_scope(self):
        previous = getattr(self._scope, "depth", 0)
        self._scope.depth = previous + 1
        try:
            yield
        finally:
            self._scope.depth = previous

    def check(self, sock, address):
        permitted = (
            self.inside_socketpair
            and sock.family in (socket.AF_INET, socket.AF_INET6)
            and isinstance(address, tuple)
            and len(address) >= 2
            and address[0] in ("127.0.0.1", "::1")
            and type(address[1]) is int
            and 0 < address[1] < 65536
        )
        if not permitted:
            self.blocked_connects += 1
            raise AssertionError("NETWORK_FORBIDDEN_IN_OFFLINE_TESTS")
        self.allowed_pair_connects += 1


def install_offline_socket_guard(monkeypatch, *, force_socketpair_fallback=False):
    """Install a reversible pytest guard without changing asyncio's policy."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_socketpair = (
        socket._fallback_socketpair if force_socketpair_fallback else socket.socketpair
    )
    guard = OfflineSocketGuard()

    def guarded_connect(sock, address):
        guard.check(sock, address)
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        guard.check(sock, address)
        return original_connect_ex(sock, address)

    def guarded_socketpair(*args, **kwargs):
        guard.socketpair_calls += 1
        with guard._socketpair_scope():
            return original_socketpair(*args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "socketpair", guarded_socketpair)
    return guard
