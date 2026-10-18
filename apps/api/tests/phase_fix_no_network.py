"""Opt-in pytest plugin for the release's fully offline checks."""
import pytest
from phase_fix_socket_guard import install_offline_socket_guard


@pytest.fixture(autouse=True)
def forbid_service_connections(monkeypatch):
    # Also exercises the Windows socketpair fallback under Linux.
    return install_offline_socket_guard(monkeypatch, force_socketpair_fallback=True)
