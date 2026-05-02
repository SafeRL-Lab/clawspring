"""cli.py — `cheetahclaws spike-daemon` subcommand.

Subcommands:
  serve [--listen unix|tcp://...]   Start the daemon. Default unix socket.
  status                             Print daemon status / pidfile.
  stop                               Send SIGTERM to the running daemon.
  rotate-token                       Regenerate the TCP bearer token.
"""
from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Optional

from .auth import load_or_create_token, rotate_token

DEFAULT_DATA_DIR = Path.home() / ".cheetahclaws"
DEFAULT_RUN_DIR = DEFAULT_DATA_DIR / "run"
DEFAULT_UNIX_SOCKET = DEFAULT_RUN_DIR / "daemon.sock"
DEFAULT_TOKEN_PATH = DEFAULT_DATA_DIR / "daemon_token"
DEFAULT_PID_FILE = DEFAULT_RUN_DIR / "daemon.pid"


def _parse_listen(spec: str) -> tuple[str, object]:
    """Return ('unix', Path) or ('tcp', (host, port))."""
    if spec.startswith("unix://"):
        return "unix", Path(spec[len("unix://"):]).expanduser()
    if spec.startswith("tcp://"):
        host_port = spec[len("tcp://"):]
        if ":" not in host_port:
            raise ValueError(f"tcp listen must be tcp://host:port, got {spec!r}")
        host, port = host_port.rsplit(":", 1)
        return "tcp", (host, int(port))
    raise ValueError(f"unknown listen spec {spec!r}; use unix://path or tcp://host:port")


def _write_pidfile(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()))


def _read_pidfile(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import make_tcp_server, make_unix_server

    listen = args.listen or f"unix://{DEFAULT_UNIX_SOCKET}"
    transport, addr = _parse_listen(listen)
    data_dir = Path(args.data_dir).expanduser()
    pid_file = DEFAULT_PID_FILE if args.data_dir == str(DEFAULT_DATA_DIR) else data_dir / "run" / "daemon.pid"

    existing = _read_pidfile(pid_file)
    if existing and _is_pid_alive(existing):
        print(f"daemon already running (pid={existing})", file=sys.stderr)
        return 1

    audit_enabled = not args.no_audit
    if transport == "unix":
        server = make_unix_server(addr, data_dir=data_dir, audit_enabled=audit_enabled)
        listen_repr = f"unix://{addr}"
    else:
        token = load_or_create_token(Path(args.token_path).expanduser())
        host, port = addr  # type: ignore
        server = make_tcp_server(host, port, data_dir=data_dir, token=token, audit_enabled=audit_enabled)
        listen_repr = f"tcp://{host}:{port}"
        if args.print_token:
            print(f"token: {token}")

    _write_pidfile(pid_file)
    print(f"cheetahclaws-daemon listening on {listen_repr} (pid={os.getpid()})")
    if audit_enabled:
        print(f"audit log: {data_dir / 'logs' / 'auth.jsonl'}")

    def _shutdown(_signo, _frame):
        print("shutdown requested", file=sys.stderr)
        server.daemon_state.shutdown()
        # ThreadingMixIn server.shutdown() must be called from a different
        # thread than the one running serve_forever. We're in a signal
        # handler, which runs on the main thread (the same one in
        # serve_forever) — schedule shutdown on a side thread.
        import threading as _t
        _t.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        try:
            server.server_close()
        except Exception:
            pass
        if transport == "unix":
            try:
                Path(addr).unlink()
            except FileNotFoundError:
                pass
        try:
            pid_file.unlink()
        except FileNotFoundError:
            pass
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    pid = _read_pidfile(DEFAULT_PID_FILE)
    if pid and _is_pid_alive(pid):
        print(f"running (pid={pid})")
        return 0
    print("not running")
    return 1


def cmd_stop(args: argparse.Namespace) -> int:
    pid = _read_pidfile(DEFAULT_PID_FILE)
    if not pid or not _is_pid_alive(pid):
        print("not running", file=sys.stderr)
        return 1
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if not _is_pid_alive(pid):
            print(f"stopped (pid={pid})")
            return 0
        time.sleep(0.1)
    print(f"timed out waiting for pid {pid}; sending SIGKILL", file=sys.stderr)
    os.kill(pid, signal.SIGKILL)
    return 0


def cmd_rotate_token(args: argparse.Namespace) -> int:
    token = rotate_token(Path(args.token_path).expanduser())
    print(f"new token written to {args.token_path}")
    if args.print_token:
        print(f"token: {token}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cheetahclaws spike-daemon")
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("serve", help="Start the daemon")
    s.add_argument("--listen", default=None,
                   help=f"unix://path or tcp://host:port (default unix://{DEFAULT_UNIX_SOCKET})")
    s.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    s.add_argument("--token-path", default=str(DEFAULT_TOKEN_PATH))
    s.add_argument("--no-audit", action="store_true",
                   help="Disable audit log (default: on for both transports per RFC review)")
    s.add_argument("--print-token", action="store_true",
                   help="Print the TCP bearer token to stdout (TCP only)")
    s.set_defaults(func=cmd_serve)

    st = sp.add_parser("status", help="Print daemon status")
    st.set_defaults(func=cmd_status)

    stop = sp.add_parser("stop", help="Stop the running daemon")
    stop.set_defaults(func=cmd_stop)

    rt = sp.add_parser("rotate-token", help="Regenerate TCP bearer token")
    rt.add_argument("--token-path", default=str(DEFAULT_TOKEN_PATH))
    rt.add_argument("--print-token", action="store_true")
    rt.set_defaults(func=cmd_rotate_token)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
