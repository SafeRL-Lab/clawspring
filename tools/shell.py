"""tools_shell.py — Shell tool implementations: Bash, Grep."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


# ── Process tree kill ─────────────────────────────────────────────────────

def _kill_proc_tree(pid: int) -> None:
    """Kill a process and all its children."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True)
    else:
        import signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


# ── Bash ──────────────────────────────────────────────────────────────────

def _bash(command: str, timeout: int = 30, cwd: str = None,
          shell_policy: str = "allow", session_id: str = "default") -> str:
    if shell_policy == "deny":
        return "Error: Bash execution is disabled (shell_policy=deny)."
    if shell_policy == "log":
        print(
            f"[bash][session={session_id}] {command[:300]}",
            file=sys.stderr, flush=True,
        )
    kwargs = dict(
        shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=cwd or os.getcwd(),
    )
    if sys.platform != "win32":
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(command, **kwargs)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_proc_tree(proc.pid)
            proc.wait()
            return f"Error: timed out after {timeout}s (process killed)"
        out = stdout
        if stderr:
            out += ("\n" if out else "") + "[stderr]\n" + stderr
        return out.strip() or "(no output)"
    except Exception as e:
        return f"Error: {e}"


# ── Grep ──────────────────────────────────────────────────────────────────

def _has_rg() -> bool:
    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def _grep(
    pattern: str,
    path: str = None,
    glob: str = None,
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    context: int = 0,
    cwd: str = None,
) -> str:
    use_rg = _has_rg()
    cmd = ["rg" if use_rg else "grep", "--no-heading"]
    if case_insensitive:
        cmd.append("-i")
    if output_mode == "files_with_matches":
        cmd.append("-l")
    elif output_mode == "count":
        cmd.append("-c")
    else:
        cmd.append("-n")
        if context:
            cmd += ["-C", str(context)]
    if glob:
        cmd += (["--glob", glob] if use_rg else ["--include", glob])
    cmd.append(pattern)
    cmd.append(path or cwd or str(Path.cwd()))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        out = r.stdout.strip()
        return out[:20000] if out else "No matches found"
    except Exception as e:
        return f"Error: {e}"
