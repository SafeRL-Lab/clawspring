"""
commands/core.py — Core utility commands for CheetahClaws.

Commands: /help, /clear, /context, /cost, /compact, /init, /export,
          /copy, /status, /doctor, /proactive, /image
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Union

from ui.render import clr, info, ok, warn, err

# VERSION is imported lazily from cheetahclaws to avoid circular imports
_VERSION_STR = ""

def _get_version() -> str:
    global _VERSION_STR
    if not _VERSION_STR:
        try:
            import importlib
            cc = importlib.import_module("cheetahclaws")
            _VERSION_STR = getattr(cc, "VERSION", "?")
        except Exception:
            _VERSION_STR = "?"
    return _VERSION_STR


def cmd_help(_args: str, _state, config) -> bool:
    try:
        import cheetahclaws
        print(cheetahclaws.__doc__)
    except Exception:
        info("CheetahClaws — type /model, /save, /load, /history, /context, /exit for commands.")
    return True


def cmd_clear(_args: str, state, config) -> bool:
    state.messages.clear()
    state.turn_count = 0
    ok("Conversation cleared.")
    return True


def cmd_context(_args: str, state, config) -> bool:
    msg_chars = sum(len(str(m.get("content", ""))) for m in state.messages)
    est_tokens = msg_chars // 4
    info(f"Messages:         {len(state.messages)}")
    info(f"Estimated tokens: ~{est_tokens:,}")
    info(f"Model:            {config['model']}")
    info(f"Max tokens:       {config['max_tokens']:,}")
    return True


def cmd_cost(_args: str, state, config) -> bool:
    from config import calc_cost
    cost = calc_cost(config["model"],
                     state.total_input_tokens,
                     state.total_output_tokens)
    info(f"Input tokens:  {state.total_input_tokens:,}")
    info(f"Output tokens: {state.total_output_tokens:,}")
    info(f"Est. cost:     ${cost:.4f} USD")
    return True


def cmd_compact(args: str, state, config) -> bool:
    """Manually compact conversation history."""
    from compaction import manual_compact
    focus = args.strip()
    if focus:
        info(f"Compacting with focus: {focus}")
    else:
        info("Compacting conversation...")
    success, msg = manual_compact(state, config, focus=focus)
    if success:
        info(msg)
    else:
        err(msg)
    return True


def cmd_init(args: str, state, config) -> bool:
    """Initialize a CLAUDE.md file in the current directory."""
    target = Path.cwd() / "CLAUDE.md"
    if target.exists():
        err(f"CLAUDE.md already exists at {target}")
        info("Edit it directly or delete it first.")
        return True

    project_name = Path.cwd().name
    template = (
        f"# {project_name}\n\n"
        "## Project Overview\n"
        "<!-- Describe what this project does -->\n\n"
        "## Tech Stack\n"
        "<!-- Languages, frameworks, key dependencies -->\n\n"
        "## Conventions\n"
        "<!-- Coding style, naming conventions, patterns to follow -->\n\n"
        "## Important Files\n"
        "<!-- Key entry points, config files, etc. -->\n\n"
        "## Testing\n"
        "<!-- How to run tests, testing conventions -->\n\n"
    )
    target.write_text(template, encoding="utf-8")
    info(f"Created {target}")
    info("Edit it to give Claude context about your project.")
    return True


def cmd_export(args: str, state, config) -> bool:
    """Export conversation history to a file."""
    if not state.messages:
        err("No conversation to export.")
        return True

    arg = args.strip()
    if arg:
        out_path = Path(arg)
    else:
        export_dir = Path.cwd() / ".nano_claude" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = export_dir / f"conversation_{ts}.md"

    is_json = out_path.suffix.lower() == ".json"

    if is_json:
        out_path.write_text(
            json.dumps(state.messages, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    else:
        lines = []
        for m in state.messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, list):
                content = "(structured content)"
            if role == "user":
                lines.append(f"## User\n\n{content}\n")
            elif role == "assistant":
                lines.append(f"## Assistant\n\n{content}\n")
            elif role == "tool":
                name = m.get("name", "tool")
                lines.append(f"### Tool: {name}\n\n```\n{content[:2000]}\n```\n")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")

    info(f"Exported {len(state.messages)} messages to {out_path}")
    return True


def cmd_copy(args: str, state, config) -> bool:
    """Copy the last assistant response to clipboard."""
    last_reply = None
    for m in reversed(state.messages):
        if m.get("role") == "assistant":
            content = m.get("content", "")
            if isinstance(content, str) and content.strip():
                last_reply = content
                break

    if not last_reply:
        err("No assistant response to copy.")
        return True

    try:
        import subprocess as _sp
        if sys.platform == "win32":
            proc = _sp.Popen(["clip"], stdin=_sp.PIPE)
            proc.communicate(last_reply.encode("utf-16le"))
        elif sys.platform == "darwin":
            proc = _sp.Popen(["pbcopy"], stdin=_sp.PIPE)
            proc.communicate(last_reply.encode("utf-8"))
        else:
            for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
                try:
                    proc = _sp.Popen(cmd, stdin=_sp.PIPE)
                    proc.communicate(last_reply.encode("utf-8"))
                    break
                except FileNotFoundError:
                    continue
            else:
                err("No clipboard tool found. Install xclip or xsel.")
                return True
        info(f"Copied {len(last_reply)} chars to clipboard.")
    except Exception as e:
        err(f"Failed to copy: {e}")
    return True


def cmd_status(args: str, state, config) -> bool:
    """Show current session status."""
    from providers import detect_provider
    from compaction import estimate_tokens, get_context_limit

    model = config.get("model", "unknown")
    provider = detect_provider(model)
    perm_mode = config.get("permission_mode", "auto")
    session_id = config.get("_session_id", "N/A")
    turn_count = getattr(state, "turn_count", 0)
    msg_count = len(getattr(state, "messages", []))
    tokens_in = getattr(state, "total_input_tokens", 0)
    tokens_out = getattr(state, "total_output_tokens", 0)
    est_ctx = estimate_tokens(getattr(state, "messages", []))
    ctx_limit = get_context_limit(model)
    ctx_pct = (est_ctx / ctx_limit * 100) if ctx_limit else 0
    plan_mode = config.get("permission_mode") == "plan"

    print(f"  Version:     {_get_version()}")
    print(f"  Model:       {model} ({provider})")
    print(f"  Permissions: {perm_mode}" + (" [PLAN MODE]" if plan_mode else ""))
    print(f"  Session:     {session_id}")
    print(f"  Turns:       {turn_count}")
    print(f"  Messages:    {msg_count}")
    print(f"  Tokens:      ~{tokens_in} in / ~{tokens_out} out")
    print(f"  Context:     ~{est_ctx} / {ctx_limit} ({ctx_pct:.0f}%)")
    return True


def cmd_doctor(args: str, state, config) -> bool:
    """Diagnose installation health and connectivity."""
    import subprocess as _sp
    from providers import PROVIDERS, detect_provider, get_api_key

    ok_n = warn_n = fail_n = 0

    def _print_safe(s):
        try:
            print(s)
        except UnicodeEncodeError:
            print(s.encode("ascii", errors="replace").decode())

    def _ok(msg):
        nonlocal ok_n; ok_n += 1
        _print_safe(clr("  [PASS] ", "green") + msg)

    def _warn(msg):
        nonlocal warn_n; warn_n += 1
        _print_safe(clr("  [WARN] ", "yellow") + msg)

    def _fail(msg):
        nonlocal fail_n; fail_n += 1
        _print_safe(clr("  [FAIL] ", "red") + msg)

    info("Running diagnostics...")
    print()

    v = sys.version_info
    if v >= (3, 10):
        _ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _fail(f"Python {v.major}.{v.minor}.{v.micro} (need ≥3.10)")

    try:
        r = _sp.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            _ok(f"Git: {r.stdout.strip()}")
        else:
            _fail("Git: not working")
    except Exception:
        _fail("Git: not found")

    try:
        r = _sp.run(["git", "rev-parse", "--is-inside-work-tree"],
                    capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            _ok("Inside a git repository")
        else:
            _warn("Not inside a git repository")
    except Exception:
        _warn("Could not check git repo status")

    model = config.get("model", "")
    provider = detect_provider(model)
    key = get_api_key(provider, config)

    if key:
        _ok(f"API key for {provider}: set ({key[:4]}...{key[-4:]})")
    elif provider in ("ollama", "lmstudio"):
        _ok(f"Provider {provider}: no key needed (local)")
    else:
        _fail(f"API key for {provider}: NOT SET")

    if key or provider in ("ollama", "lmstudio"):
        print(f"  ... testing {provider} API connectivity...")
        try:
            import urllib.request, urllib.error
            prov = PROVIDERS.get(provider, {})
            ptype = prov.get("type", "openai")

            if ptype == "anthropic":
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=json.dumps({
                        "model": model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    }).encode(),
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                )
                try:
                    urllib.request.urlopen(req, timeout=10)
                    _ok(f"Anthropic API: reachable, model {model} works")
                except urllib.error.HTTPError as e:
                    if e.code == 401:
                        _fail("Anthropic API: invalid API key (401)")
                    elif e.code == 404:
                        _fail(f"Anthropic API: model {model} not found (404)")
                    elif e.code == 429:
                        _warn("Anthropic API: rate limited (429) — key is valid")
                    else:
                        _warn(f"Anthropic API: HTTP {e.code}")
                except Exception as e:
                    _fail(f"Anthropic API: connection error — {e}")
            elif ptype == "ollama":
                base = prov.get("base_url", "http://localhost:11434")
                try:
                    urllib.request.urlopen(f"{base}/api/tags", timeout=5)
                    _ok(f"Ollama: reachable at {base}")
                except Exception:
                    _fail(f"Ollama: cannot reach {base} — is Ollama running?")
            else:
                base = prov.get("base_url", "")
                if provider == "custom":
                    base = config.get("custom_base_url", base or "")
                if base:
                    models_url = base.rstrip("/") + "/models"
                    req = urllib.request.Request(
                        models_url,
                        headers={"Authorization": f"Bearer {key}"},
                    )
                    try:
                        urllib.request.urlopen(req, timeout=10)
                        _ok(f"{provider} API: reachable")
                    except urllib.error.HTTPError as e:
                        if e.code == 401:
                            _fail(f"{provider} API: invalid API key (401)")
                        elif e.code == 429:
                            _warn(f"{provider} API: rate limited (429) — key is valid")
                        else:
                            _warn(f"{provider} API: HTTP {e.code}")
                    except Exception as e:
                        _fail(f"{provider} API: connection error — {e}")
                else:
                    _warn(f"{provider}: no base_url configured")
        except Exception as e:
            _warn(f"API test skipped: {e}")

    print()
    for pname, pdata in PROVIDERS.items():
        if pname == provider:
            continue
        env_var = pdata.get("api_key_env")
        if env_var and os.environ.get(env_var, ""):
            _ok(f"{pname} key ({env_var}): set")

    print()
    for mod, desc in [
        ("rich", "Rich (live markdown rendering)"),
        ("PIL", "Pillow (clipboard image /image)"),
        ("sounddevice", "sounddevice (voice recording)"),
        ("faster_whisper", "faster-whisper (local STT)"),
    ]:
        try:
            __import__(mod)
            _ok(desc)
        except ImportError:
            _warn(f"{desc}: not installed")

    print()
    claude_md = Path.cwd() / "CLAUDE.md"
    global_md = Path.home() / ".claude" / "CLAUDE.md"
    if claude_md.exists():
        _ok(f"Project CLAUDE.md: {claude_md}")
    else:
        _warn("No project CLAUDE.md (run /init to create)")
    if global_md.exists():
        _ok(f"Global CLAUDE.md: {global_md}")

    ckpt_root = Path.home() / ".nano_claude" / "checkpoints"
    if ckpt_root.exists():
        total = sum(f.stat().st_size for f in ckpt_root.rglob("*") if f.is_file())
        mb = total / (1024 * 1024)
        sessions = sum(1 for d in ckpt_root.iterdir() if d.is_dir())
        if mb > 100:
            _warn(f"Checkpoints: {mb:.1f} MB ({sessions} sessions)")
        else:
            _ok(f"Checkpoints: {mb:.1f} MB ({sessions} sessions)")

    perm = config.get("permission_mode", "auto")
    if perm == "accept-all":
        _warn(f"Permission mode: {perm} (all operations auto-approved)")
    else:
        _ok(f"Permission mode: {perm}")

    print()
    total = ok_n + warn_n + fail_n
    summary = f"  {ok_n} passed, {warn_n} warnings, {fail_n} failures ({total} checks)"
    if fail_n:
        _print_safe(clr(summary, "red"))
    elif warn_n:
        _print_safe(clr(summary, "yellow"))
    else:
        _print_safe(clr(summary, "green"))

    return True


def cmd_proactive(args: str, state, config) -> bool:
    """Manage proactive background polling.

    /proactive            — show current status
    /proactive 5m         — enable, trigger after 5 min of inactivity
    /proactive 30s / 1h   — enable with custom interval
    /proactive off        — disable
    """
    args = args.strip().lower()

    import runtime
    sctx = runtime.get_ctx(config)

    if not args:
        if sctx.proactive_enabled:
            interval = sctx.proactive_interval
            info(f"Proactive background polling: ON  (triggering every {interval}s of inactivity)")
        else:
            info("Proactive background polling: OFF  (use /proactive 5m to enable)")
        return True

    if args == "off":
        sctx.proactive_enabled = False
        info("Proactive background polling: OFF")
        return True

    multiplier = 1
    val_str = args
    if args.endswith("m"):
        multiplier = 60
        val_str = args[:-1]
    elif args.endswith("h"):
        multiplier = 3600
        val_str = args[:-1]
    elif args.endswith("s"):
        val_str = args[:-1]

    try:
        val = int(val_str)
        sctx.proactive_interval = val * multiplier
    except ValueError:
        err(f"Invalid duration: '{args}'. Use '5m', '30s', '1h', or 'off'.")
        return True

    sctx.proactive_enabled = True
    sctx.last_interaction_time = time.time()
    info(f"Proactive background polling: ON  (triggering every {sctx.proactive_interval}s of inactivity)")
    return True


def cmd_image(args: str, state, config) -> Union[bool, tuple]:
    """Grab image from clipboard and send to vision model with optional prompt."""
    try:
        from PIL import ImageGrab
        import io, base64
    except ImportError:
        err("Pillow is required for /image. Install with: pip install cheetahclaws[vision]")
        if sys.platform == "linux":
            err("On Linux, clipboard support also requires xclip: sudo apt install xclip")
        return True

    img = ImageGrab.grabclipboard()
    if img is None:
        if sys.platform == "linux":
            err("No image found in clipboard. On Linux, xclip is required (sudo apt install xclip). "
                "Copy an image with Flameshot, GNOME Screenshot, or: xclip -selection clipboard -t image/png -i file.png")
        elif sys.platform == "darwin":
            err("No image found in clipboard. Copy an image first "
                "(Cmd+Ctrl+Shift+4 captures a screenshot region to clipboard).")
        else:
            err("No image found in clipboard. Copy an image first "
                "(Win+Shift+S captures a screenshot region to clipboard).")
        return True

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    size_kb = len(buf.getvalue()) / 1024

    info(f"📷 Clipboard image captured ({size_kb:.0f} KB, {img.size[0]}x{img.size[1]})")
    import runtime
    runtime.get_ctx(config).pending_image = b64

    prompt = args.strip() if args.strip() else "What do you see in this image? Describe it in detail."
    return ("__image__", prompt)
