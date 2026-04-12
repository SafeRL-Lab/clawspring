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

from ui.render import clr, info, ok, warn, err
import runtime
import logging_utils as _log

_telegram_thread: threading.Thread | None = None
_telegram_stop = threading.Event()


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
                            config["_pending_image"] = b64
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

                # ── Claude query: stream response back live ────────────────
                def _bg_runner(q_text, chat_token, chat_id):
                    import time as _time

                    # Post placeholder; we'll edit it as chunks arrive
                    init_resp = _tg_api(chat_token, "sendMessage", {
                        "chat_id": chat_id, "text": "⏳",
                    })
                    msg_id = (
                        (init_resp or {}).get("result", {}).get("message_id")
                        if init_resp and init_resp.get("ok") else None
                    )

                    # Streaming state
                    _chunks: list[str] = []
                    _last_edit = [0.0]
                    _stream_lock = threading.Lock()

                    def _edit_msg():
                        text_so_far = "".join(_chunks)
                        if not text_so_far or not msg_id:
                            return
                        # Telegram max message length: 4096 chars
                        _tg_api(chat_token, "editMessageText", {
                            "chat_id": chat_id,
                            "message_id": msg_id,
                            "text": text_so_far[-4000:],
                        })
                        _last_edit[0] = _time.monotonic()

                    def _on_chunk(chunk: str):
                        _chunks.append(chunk)
                        with _stream_lock:
                            if _time.monotonic() - _last_edit[0] >= 1.2:  # Telegram: ≤1 edit/sec
                                _edit_msg()

                    def _on_tool_start(name: str, inputs: dict):
                        cmd_preview = str(inputs.get("command", inputs.get("file_path", ""))).strip()[:60]
                        label = f"🔧 {name}" + (f": `{cmd_preview}`" if cmd_preview else "")
                        _tg_send(chat_token, chat_id, label)

                    session_ctx.on_text_chunk  = _on_chunk
                    session_ctx.on_tool_start  = _on_tool_start
                    session_ctx.on_tool_end    = None

                    try:
                        config["_telegram_incoming"] = True
                        run_query_cb(q_text)
                    except Exception as e:
                        _tg_send(chat_token, chat_id, f"⚠ Error: {e}")
                        return
                    finally:
                        session_ctx.on_text_chunk = None
                        session_ctx.on_tool_start = None
                        config.pop("_telegram_incoming", None)

                    # Final edit to ensure the complete response is shown
                    _edit_msg()
                    # If nothing was streamed (pure tool-use turn), send final assistant msg
                    if not _chunks:
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
                                        _tg_send(chat_token, chat_id, content)
                                    break

                threading.Thread(target=_bg_runner, args=(text, token, chat_id), daemon=True).start()

        except Exception:
            _telegram_stop.wait(5)

    return "stopped"


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
