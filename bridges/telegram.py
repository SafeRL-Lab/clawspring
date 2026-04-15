"""
bridges/telegram.py — Telegram bot bridge for CheetahClaws.

Provides:
  - _tg_api / _tg_send / _tg_typing_loop  (HTTP helpers)
  - _tg_poll_loop  (long-polling loop, runs in daemon thread)
  - cmd_telegram   (/telegram slash command)
"""
from __future__ import annotations

import json
import threading
import time as _time_mod

from ui.render import clr, info, ok, warn, err
import runtime
import logging_utils as _log
import jobs as _jobs

_telegram_thread: threading.Thread | None = None
_telegram_stop = threading.Event()

# ── Per-bridge job queue ───────────────────────────────────────────────────
# When the AI is processing a query, new messages are queued rather than dropped.
_tg_queue: list[tuple[str, str, int]] = []   # [(prompt, token, chat_id), ...]
_tg_queue_lock = threading.Lock()
_tg_busy = threading.Event()   # set while a query is running


# ── HTTP helpers ───────────────────────────────────────────────────────────

def _tg_api(token: str, method: str, params: dict = None):
    """Call Telegram Bot API. Returns parsed JSON or None on error."""
    import urllib.request
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        data = json.dumps(params).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _tg_send(token: str, chat_id: int, text: str):
    """Send a message to a Telegram chat, splitting if too long."""
    MAX = 4000
    chunks = [text[i:i+MAX] for i in range(0, len(text), MAX)]
    for chunk in chunks:
        result = _tg_api(token, "sendMessage", {"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"})
        if not result or not result.get("ok"):
            _tg_api(token, "sendMessage", {"chat_id": chat_id, "text": chunk})


def _tg_typing_loop(token: str, chat_id: int, stop_event: threading.Event):
    """Send 'typing...' indicator every 4 seconds until stop_event is set."""
    while not stop_event.is_set():
        _tg_api(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"})
        stop_event.wait(4)


# ── Poll loop ──────────────────────────────────────────────────────────────

def _tg_poll_loop(token: str, chat_id: int, config: dict) -> str:
    """Long-polling loop that reads Telegram messages and feeds them to run_query.

    Returns:
      "stopped"    — clean stop via _telegram_stop or /stop command
      "auth_error" — token rejected by Telegram (don't reconnect)
    Raises on unexpected fatal errors so the supervisor can reconnect.
    """
    from tools import _tg_thread_local
    session_ctx = runtime.get_session_ctx(config.get("_session_id", "default"))
    run_query_cb = session_ctx.run_query
    # Flush old messages
    flush = _tg_api(token, "getUpdates", {"offset": -1, "timeout": 0})
    if flush and flush.get("ok") and flush.get("result"):
        offset = flush["result"][-1]["update_id"] + 1
    else:
        offset = 0
    _tg_send(token, chat_id, "🟢 cheetahclaws is online.\nSend me a message and I'll process it.")

    while not _telegram_stop.is_set():
        try:
            result = _tg_api(token, "getUpdates", {
                "offset": offset,
                "timeout": 30,
                "allowed_updates": ["message"]
            })
            if not result or not result.get("ok"):
                if result:
                    tg_err = result.get("error_code")
                    desc   = result.get("description", "")
                    if tg_err == 401 or "unauthorized" in desc.lower():
                        _log.warn("bridge_auth_error", bridge="telegram", description=desc[:100])
                        return "auth_error"
                _telegram_stop.wait(5)
                continue

            for update in result.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                msg_chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")

                if msg_chat_id != chat_id:
                    _tg_api(token, "sendMessage", {
                        "chat_id": msg_chat_id,
                        "text": "⛔ Unauthorized."
                    })
                    continue

                # Handle photo messages
                photo_list = msg.get("photo")
                if photo_list:
                    caption = msg.get("caption", "").strip() or "What do you see in this image? Describe it in detail."
                    file_id = photo_list[-1]["file_id"]
                    try:
                        file_info = _tg_api(token, "getFile", {"file_id": file_id})
                        if file_info and file_info.get("ok"):
                            file_path = file_info["result"]["file_path"]
                            import urllib.request, base64
                            url = f"https://api.telegram.org/file/bot{token}/{file_path}"
                            with urllib.request.urlopen(url, timeout=30) as resp:
                                img_bytes = resp.read()
                            b64 = base64.b64encode(img_bytes).decode("utf-8")
                            size_kb = len(img_bytes) / 1024
                            sctx = runtime.get_ctx(config)
                            sctx.pending_image = b64
                            text = caption
                            print(clr(f"\n  📩 Telegram: 📷 image ({size_kb:.0f} KB) + \"{caption[:50]}\"", "cyan"))
                        else:
                            _tg_send(token, chat_id, "⚠ Could not download image.")
                            continue
                    except Exception as e:
                        _tg_send(token, chat_id, f"⚠ Image error: {e}")
                        continue

                # Handle voice messages
                voice_msg = msg.get("voice") or msg.get("audio")
                if voice_msg and not text:
                    file_id = voice_msg["file_id"]
                    duration = voice_msg.get("duration", 0)
                    try:
                        file_info = _tg_api(token, "getFile", {"file_id": file_id})
                        if file_info and file_info.get("ok"):
                            file_path = file_info["result"]["file_path"]
                            import urllib.request
                            url = f"https://api.telegram.org/file/bot{token}/{file_path}"
                            with urllib.request.urlopen(url, timeout=30) as resp:
                                audio_bytes = resp.read()
                            size_kb = len(audio_bytes) / 1024
                            _tg_send(token, chat_id, f"🎙 Voice received ({duration}s, {size_kb:.0f} KB) — transcribing...")
                            print(clr(f"\n  📩 Telegram: 🎙 voice ({duration}s, {size_kb:.0f} KB)", "cyan"))
                            from voice import transcribe_audio_file
                            suffix = ".ogg" if msg.get("voice") else ".mp3"
                            transcribed = transcribe_audio_file(audio_bytes, suffix=suffix)
                            if transcribed:
                                _tg_send(token, chat_id, f"📝 Transcribed: \"{transcribed}\"")
                                text = transcribed
                            else:
                                _tg_send(token, chat_id, "⚠ No speech detected in voice message.")
                                continue
                        else:
                            _tg_send(token, chat_id, "⚠ Could not download voice message.")
                            continue
                    except Exception as e:
                        _tg_send(token, chat_id, f"⚠ Voice error: {e}")
                        continue

                if not text:
                    continue

                # Intercept text if a permission prompt is waiting
                evt = session_ctx.tg_input_event
                if evt:
                    session_ctx.tg_input_value = text
                    evt.set()
                    continue

                # ── Interactive PTY session (e.g. !claude, !python, !bash) ─
                from bridges.interactive_session import get_session, set_session, remove_session, InteractiveSession
                _sess_key = f"tg_{chat_id}"
                _active_sess = get_session(_sess_key)

                if _active_sess:
                    stripped = text.strip().lower()
                    # Normalize: "! exit" → "!exit" (handle accidental spaces)
                    _norm = stripped.replace(" ", "")
                    # Exit commands (with or without space after !)
                    _exit_set = {"!exit", "!quit", "!stop", "/exit", "/quit"}
                    if stripped in _exit_set or _norm in _exit_set or stripped == "/exit_session":
                        remove_session(_sess_key)
                        _tg_send(token, chat_id, "⏹ Interactive session ended.")
                        continue
                    # Force-refresh screen (useful when output stalled)
                    if stripped in ("!ping", "!screen", "!refresh") or _norm in ("!ping", "!screen", "!refresh"):
                        _tg_send(token, chat_id, "🔄 Refreshing screen…")
                        _active_sess.force_flush()
                        continue
                    # Route all input to the running process
                    _active_sess.send_input(text)
                    # Small acknowledgement so user knows input was received
                    _tg_send(token, chat_id, f"⌨ `{text[:60]}`")
                    continue

                # ── !agent sub-commands (remote agent control) ────────────
                if text.strip().lower().startswith("!agent"):
                    agent_args = text.strip()[6:].strip()
                    def _agent_ctrl(aargs, chat_token, cid):
                        try:
                            from agent_runner import list_runners, stop_runner, stop_all, get_runner
                            subcmd_parts = aargs.split(None, 1)
                            subcmd = subcmd_parts[0].lower() if subcmd_parts else "list"
                            rest = subcmd_parts[1] if len(subcmd_parts) > 1 else ""
                            if subcmd in ("list", "ls"):
                                runners = list_runners()
                                if not runners:
                                    _tg_send(chat_token, cid, "ℹ No agents running.")
                                else:
                                    lines = [f"🤖 {len(runners)} agent(s):"]
                                    for r in runners:
                                        lines.append(f"  • {r.name}: {r.status}")
                                        recs = r.recent_log(1)
                                        if recs:
                                            lines.append(f"    {recs[-1].summary[:80]}")
                                    _tg_send(chat_token, cid, "\n".join(lines))
                            elif subcmd == "stop":
                                target = rest.strip()
                                if not target:
                                    _tg_send(chat_token, cid, "Usage: !agent stop <name> | all")
                                elif target.lower() == "all":
                                    n = stop_all()
                                    _tg_send(chat_token, cid, f"⏹ Stopped {n} agent(s).")
                                else:
                                    ok = stop_runner(target)
                                    _tg_send(chat_token, cid, f"⏹ '{target}' stopped." if ok else f"ℹ No agent '{target}'.")
                            elif subcmd == "status":
                                name = rest.strip()
                                r = get_runner(name)
                                if r:
                                    _tg_send(chat_token, cid, r.summary_text())
                                else:
                                    _tg_send(chat_token, cid, f"ℹ No agent '{name}'.")
                            else:
                                _tg_send(chat_token, cid, "Usage: !agent list | !agent stop <name> | !agent status <name>")
                        except Exception as e:
                            _tg_send(chat_token, cid, f"⚠ agent error: {e}")
                    threading.Thread(target=_agent_ctrl,
                                     args=(agent_args, token, chat_id),
                                     daemon=True).start()
                    continue

                # Start a new interactive session with !cmd
                if text.strip().startswith("!"):
                    raw_cmd = text.strip()[1:].strip()
                    if not raw_cmd or raw_cmd.lower() == "stop":
                        from bridges.terminal_runner import stop_terminal
                        killed = stop_terminal(_sess_key)
                        _tg_send(token, chat_id, "🛑 Stopped." if killed else "ℹ Nothing running.")
                        continue
                    # Detect interactive programs → use PTY session
                    _interactive_progs = ("claude", "python", "python3", "ipython",
                                          "bash", "sh", "zsh", "node", "irb", "pry",
                                          "sqlite3", "psql", "mysql", "redis-cli")
                    _base = raw_cmd.split()[0].split("/")[-1]
                    if _base in _interactive_progs:
                        def _start_pty(cmd, chat_token, cid, skey):
                            def _send(out): _tg_send(chat_token, cid, out)
                            try:
                                sess = InteractiveSession(cmd, _send, session_key=skey)
                                set_session(skey, sess)
                                _tg_send(chat_token, cid,
                                         f"▶ `{cmd}` started.\n"
                                         f"Type normally to interact. Send `!exit` to end.")
                            except Exception as e:
                                _tg_send(chat_token, cid, f"⚠ Could not start session: {e}")
                        threading.Thread(target=_start_pty,
                                         args=(raw_cmd, token, chat_id, _sess_key),
                                         daemon=True).start()
                        continue
                    # Non-interactive command → run and stream output
                    def _terminal_runner(cmd, chat_token, cid, skey):
                        from bridges.terminal_runner import run_terminal
                        _tg_send(chat_token, cid, f"▶ `{cmd}`")
                        run_terminal(cmd, lambda out: _tg_send(chat_token, cid, out),
                                     session_key=skey, stop_event=_telegram_stop)
                    threading.Thread(target=_terminal_runner,
                                     args=(raw_cmd, token, chat_id, _sess_key),
                                     daemon=True).start()
                    continue

                # Handle Telegram bot commands
                if text.strip().startswith("/"):
                    tg_cmd = text.strip().lower()
                    if tg_cmd in ("/stop", "/off"):
                        _tg_send(token, chat_id, "🔴 Telegram bridge stopped.")
                        _telegram_stop.set()
                        break
                    elif tg_cmd == "/start":
                        _tg_send(token, chat_id, "🟢 cheetahclaws bridge is active. Send me anything.")
                        continue
                    slash_cb = session_ctx.handle_slash
                    if slash_cb:
                        def _slash_runner(_slash_text, _token, _chat_id):
                            _tg_thread_local.active = True
                            try:
                                cmd_type = slash_cb(_slash_text)
                            except Exception as e:
                                _tg_send(_token, _chat_id, f"⚠ Error: {e}")
                                return
                            finally:
                                _tg_thread_local.active = False
                            if cmd_type == "simple":
                                cmd_name = _slash_text.strip().split()[0]
                                _tg_send(_token, _chat_id, f"✅ {cmd_name} executed.")
                                return
                            tg_state = session_ctx.agent_state
                            if tg_state and tg_state.messages:
                                for m in reversed(tg_state.messages):
                                    if m.get("role") == "assistant":
                                        content = m.get("content", "")
                                        if isinstance(content, list):
                                            parts = []
                                            for block in content:
                                                if isinstance(block, dict) and block.get("type") == "text":
                                                    parts.append(block["text"])
                                                elif isinstance(block, str):
                                                    parts.append(block)
                                            content = "\n".join(parts)
                                        if content:
                                            _tg_send(_token, _chat_id, content)
                                        break
                        threading.Thread(target=_slash_runner, args=(text, token, chat_id), daemon=True).start()
                    continue

                print(clr(f"\n  📩 Telegram: {text}", "cyan"))

                # ── Job dashboard & control commands ───────────────────────
                stripped_lower = text.strip().lower()
                if stripped_lower in ("!jobs", "!j", "!status"):
                    _tg_send(token, chat_id, _jobs.format_dashboard())
                    continue

                if stripped_lower.startswith("!job "):
                    jid = text.strip().split(None, 1)[1].lstrip("#").strip()
                    _tg_send(token, chat_id, _jobs.format_detail(jid))
                    continue

                if stripped_lower.startswith("!retry "):
                    jid = text.strip().split(None, 1)[1].lstrip("#").strip()
                    original = _jobs.get(jid)
                    if not original:
                        _tg_send(token, chat_id, f"❓ Job #{jid} not found.")
                        continue
                    retry_job = _jobs.create(original.prompt, source="telegram",
                                             retry_of=original.id)
                    _tg_send(token, chat_id,
                             f"↩ Retrying #{jid} as #{retry_job.id}:\n\"{original.title}\"")
                    _dispatch_tg_job(retry_job, original.prompt, token, chat_id,
                                     run_query_cb, session_ctx, config)
                    continue

                if stripped_lower in ("!cancel", "!kill"):
                    running = _jobs.list_running()
                    if running:
                        for j in running:
                            _jobs.cancel(j.id)
                        _tg_send(token, chat_id,
                                 f"🚫 Cancelled {len(running)} job(s).")
                    else:
                        _tg_send(token, chat_id, "ℹ No running jobs to cancel.")
                    continue

                if stripped_lower.startswith("!cancel ") or stripped_lower.startswith("!kill "):
                    jid = text.strip().split(None, 1)[1].lstrip("#").strip()
                    j = _jobs.get(jid)
                    if j:
                        _jobs.cancel(jid)
                        _tg_send(token, chat_id, f"🚫 Job #{jid} cancelled.")
                    else:
                        _tg_send(token, chat_id, f"❓ Job #{jid} not found.")
                    continue

                # ── !command: run shell command and stream output ──────────
                if text.strip().startswith("!"):
                    raw_cmd = text.strip()[1:].strip()
                    sess_key = f"tg_{chat_id}"

                    if raw_cmd.lower() in ("stop", ""):
                        from bridges.terminal_runner import stop_terminal
                        killed = stop_terminal(sess_key)
                        _tg_send(token, chat_id, "🛑 Command stopped." if killed else "ℹ No command running.")
                        continue

                    def _terminal_runner(cmd, chat_token, cid, skey):
                        from bridges.terminal_runner import run_terminal
                        _tg_send(chat_token, cid, f"▶ `{cmd}`")
                        run_terminal(cmd, lambda out: _tg_send(chat_token, cid, out),
                                     session_key=skey, stop_event=_telegram_stop)

                    threading.Thread(target=_terminal_runner,
                                     args=(raw_cmd, token, chat_id, sess_key),
                                     daemon=True).start()
                    continue

                # ── Wizard / interactive input pending ────────────────────
                # If a /monitor or other interactive command is waiting for
                # user input, route this message to it instead of the AI.
                _pending_evt = getattr(session_ctx, "tg_input_event", None)
                if _pending_evt is not None:
                    session_ctx.tg_input_value = text
                    _pending_evt.set()
                    continue

                # ── Claude query: create job, queue if busy, else run now ──
                job = _jobs.create(text, source="telegram")

                if _tg_busy.is_set():
                    with _tg_queue_lock:
                        _tg_queue.append((job.id, text, token, chat_id))
                    queue_pos = len(_tg_queue)
                    _tg_send(token, chat_id,
                             f"⏳ Queued as job #{job.id} (position {queue_pos})\n"
                             f"\"{job.title}\"\n"
                             f"Use !jobs to check status.")
                    continue

                _dispatch_tg_job(job, text, token, chat_id,
                                 run_query_cb, session_ctx, config)

        except Exception:
            _telegram_stop.wait(5)

    return "stopped"


# ── Job dispatch & background runner ──────────────────────────────────────

def _dispatch_tg_job(job, q_text: str, token: str, chat_id: int,
                     run_query_cb, session_ctx, config: dict) -> None:
    """Fire job in a background thread, then drain the queue."""
    def _run():
        _tg_busy.set()
        try:
            _bg_runner(job, q_text, token, chat_id, run_query_cb, session_ctx, config)
        finally:
            _tg_busy.clear()
            _drain_tg_queue(run_query_cb, session_ctx, config)
    threading.Thread(target=_run, daemon=True).start()


def _drain_tg_queue(run_query_cb, session_ctx, config: dict) -> None:
    """Run the next queued job, if any."""
    with _tg_queue_lock:
        if not _tg_queue:
            return
        job_id, prompt, token, chat_id = _tg_queue.pop(0)

    job = _jobs.get(job_id)
    if not job or job.status == "cancelled":
        # Skip cancelled jobs, try next
        _drain_tg_queue(run_query_cb, session_ctx, config)
        return

    remaining = len(_tg_queue)
    pos_msg = f" ({remaining} more in queue)" if remaining else ""
    _tg_send(token, chat_id,
             f"▶ Starting job #{job_id}{pos_msg}:\n\"{job.title}\"")
    _dispatch_tg_job(job, prompt, token, chat_id, run_query_cb, session_ctx, config)


def _bg_runner(job, q_text: str, chat_token: str, chat_id: int,
               run_query_cb, session_ctx, config: dict) -> None:
    """Execute one AI query with full job tracking + live streaming."""

    _jobs.start(job.id)

    # Post placeholder message; we'll edit it live as chunks arrive
    init_resp = _tg_api(chat_token, "sendMessage", {
        "chat_id": chat_id,
        "text": f"⏳ Job #{job.id} running…",
    })
    msg_id = (
        (init_resp or {}).get("result", {}).get("message_id")
        if init_resp and init_resp.get("ok") else None
    )

    _chunks: list[str] = []
    _last_edit = [0.0]
    _stream_lock = threading.Lock()
    _step_lines: list[str] = []     # running list of tool invocations for progress view

    def _edit_msg(force: bool = False):
        text_so_far = "".join(_chunks)
        if not text_so_far or not msg_id:
            return
        _tg_api(chat_token, "editMessageText", {
            "chat_id": chat_id,
            "message_id": msg_id,
            "text": text_so_far[-4000:],
        })
        _last_edit[0] = _time_mod.monotonic()

    def _on_chunk(chunk: str):
        _chunks.append(chunk)
        _jobs.stream_result(job.id, chunk)
        with _stream_lock:
            if _time_mod.monotonic() - _last_edit[0] >= 1.2:
                _edit_msg()

    def _on_tool_start(name: str, inputs: dict):
        preview = str(inputs.get("command",
                      inputs.get("file_path",
                      inputs.get("pattern",
                      inputs.get("query", ""))))).strip()[:60]
        _jobs.add_step(job.id, name, preview)
        step_label = f"🔧 {name}" + (f": `{preview}`" if preview else "")
        _step_lines.append(step_label)
        # Send compact progress message (not one per tool, batched)
        if len(_step_lines) == 1 or len(_step_lines) % 3 == 0:
            _tg_send(chat_token, chat_id, step_label)

    def _on_tool_end(name: str, result: str):
        _jobs.finish_step(job.id, name, result[:80] if result else "")

    session_ctx.on_text_chunk = _on_chunk
    session_ctx.on_tool_start = _on_tool_start
    session_ctx.on_tool_end   = _on_tool_end   # ← now wired!

    try:
        sctx = runtime.get_ctx(config)
        sctx.telegram_incoming = True
        run_query_cb(q_text)
    except Exception as e:
        _jobs.fail(job.id, str(e))
        _tg_send(chat_token, chat_id,
                 f"❌ Job #{job.id} failed: {e}\n↩ Retry with: !retry {job.id}")
        return
    finally:
        session_ctx.on_text_chunk = None
        session_ctx.on_tool_start = None
        session_ctx.on_tool_end   = None
        sctx.telegram_incoming = False

    # Finalize
    _edit_msg(force=True)

    final_text = "".join(_chunks).strip()
    if not final_text:
        # Pure tool-use turn: grab last assistant message
        state = session_ctx.agent_state
        if state and state.messages:
            for m in reversed(state.messages):
                if m.get("role") == "assistant":
                    content = m.get("content", "")
                    if isinstance(content, list):
                        content = "\n".join(
                            b.get("text", "") if isinstance(b, dict) and b.get("type") == "text"
                            else (b if isinstance(b, str) else "")
                            for b in content
                        )
                    if content:
                        final_text = content
                        _tg_send(chat_token, chat_id, content)
                    break

    _jobs.complete(job.id, final_text)

    # Send completion summary
    j = _jobs.get(job.id)
    if j and j.step_count > 0:
        dur = f"  {j.duration_s:.0f}s" if j.duration_s else ""
        _tg_send(chat_token, chat_id,
                 f"✅ Job #{job.id} done ({j.step_count} steps{dur})")


# ── Supervisor (auto-reconnect) ────────────────────────────────────────────

_TG_BACKOFF_INITIAL = 2.0
_TG_BACKOFF_MAX     = 120.0


def _tg_supervisor(token: str, chat_id: int, config: dict) -> None:
    """Wrap _tg_poll_loop with exponential-backoff reconnect on unexpected exit."""
    global _telegram_thread
    backoff = _TG_BACKOFF_INITIAL
    attempt = 0
    while not _telegram_stop.is_set():
        attempt += 1
        try:
            reason = _tg_poll_loop(token, chat_id, config)
        except Exception as exc:
            if _telegram_stop.is_set():
                break
            _log.warn("bridge_crash", bridge="telegram", attempt=attempt,
                      error=str(exc)[:200], backoff_s=backoff)
            print(clr(f"\n  ⚠ Telegram bridge crashed (attempt {attempt}), "
                      f"reconnecting in {backoff:.0f}s…", "yellow"))
            _telegram_stop.wait(backoff)
            backoff = min(backoff * 2, _TG_BACKOFF_MAX)
            continue

        if reason == "auth_error":
            print(clr("\n  ⚠ Telegram: invalid token — stopping bridge.", "yellow"))
            _log.warn("bridge_auth_error_stop", bridge="telegram")
            break
        # Clean stop or _telegram_stop set
        break

    _telegram_thread = None


# ── Slash command ──────────────────────────────────────────────────────────

def cmd_telegram(args: str, _state, config) -> bool:
    """Telegram bot bridge — receive and respond to messages via Telegram.

    Usage: /telegram <bot_token> <chat_id>   — start the bridge
           /telegram stop                    — stop the bridge
           /telegram status                  — show current status
    """
    global _telegram_thread, _telegram_stop
    from config import save_config

    parts = args.strip().split()

    if parts and parts[0].lower() in ("stop", "off"):
        if _telegram_thread and _telegram_thread.is_alive():
            _telegram_stop.set()
            _telegram_thread.join(timeout=5)
            _telegram_thread = None
            ok("Telegram bridge stopped.")
        else:
            warn("Telegram bridge is not running.")
        return True

    if parts and parts[0].lower() == "status":
        running = _telegram_thread and _telegram_thread.is_alive()
        token = config.get("telegram_token", "")
        chat_id = config.get("telegram_chat_id", 0)
        if running:
            ok(f"Telegram bridge is running. Chat ID: {chat_id}")
        elif token:
            info("Configured but not running. Use /telegram to start.")
        else:
            info("Not configured. Use /telegram <bot_token> <chat_id>")
        return True

    if len(parts) >= 2:
        token = parts[0]
        try:
            chat_id = int(parts[1])
        except ValueError:
            err("Chat ID must be a number.")
            return True
        config["telegram_token"] = token
        config["telegram_chat_id"] = chat_id
        save_config(config)
        ok("Telegram config saved.")
    else:
        token = config.get("telegram_token", "")
        chat_id = config.get("telegram_chat_id", 0)

    if not token or not chat_id:
        err("No config found. Usage: /telegram <bot_token> <chat_id>")
        return True

    if _telegram_thread and _telegram_thread.is_alive():
        warn("Telegram bridge is already running. Use /telegram stop first.")
        return True

    me = _tg_api(token, "getMe")
    if not me or not me.get("ok"):
        err("Invalid bot token. Check your token from @BotFather.")
        return True

    bot_name = me["result"].get("username", "unknown")
    ok(f"Connected to @{bot_name}. Starting bridge...")

    _telegram_stop = threading.Event()
    _telegram_thread = threading.Thread(
        target=_tg_supervisor, args=(token, chat_id, config), daemon=True,
        name="telegram-bridge"
    )
    _telegram_thread.start()
    ok(f"Telegram bridge active. Chat ID: {chat_id}")
    info("Send messages to your bot — they'll be processed here.")
    info("Stop with /telegram stop or send /stop in Telegram.")
    return True
