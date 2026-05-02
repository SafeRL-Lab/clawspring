"""system_methods.py — Always-available daemon-control RPC methods.

These ride on top of the spike's :mod:`cc_daemon.methods` (which carries
the demo and permission methods) so the contract surface is the same on
day one as it will be once the real ``agent.run`` integration lands.

  ``system.ping``      — returns the literal string ``"pong"``.
                          Same purpose as ``echo.ping`` but matches the
                          method name committed to in RFC 0001 and the
                          F-1 acceptance criteria.

  ``system.shutdown``  — triggers ``DaemonState.shutdown()`` which sets
                          ``shutdown_event``.  The cli.py serve loop
                          watches that event and, on a side thread,
                          invokes ``server.shutdown()`` so the ongoing
                          RPC response can finish writing before the
                          listener tears down.

                          This is the only cross-platform graceful
                          shutdown we have — Windows can't deliver
                          SIGTERM cleanly to another Python process, so
                          relying on signals would force users on Windows
                          to ``TerminateProcess`` (no clean cleanup).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .rpc import RpcRegistry

if TYPE_CHECKING:
    from .server import DaemonState


def register(registry: RpcRegistry, daemon_state: "DaemonState") -> None:
    def system_ping(_params, _ctx):
        return "pong"

    def system_shutdown(_params, _ctx):
        daemon_state.shutdown()
        return "shutdown_initiated"

    registry.register("system.ping", system_ping)
    registry.register("system.shutdown", system_shutdown)
