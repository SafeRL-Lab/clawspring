"""
bridges/wechat.py — WeChat (iLink Bot API) bridge for CheetahClaws.

Uses Tencent's iLink Bot API to receive/send WeChat messages.
Authentication via QR code scan.

Setup: /wechat login  — scan QR code with WeChat to authenticate
       /wechat        — re-start bridge using saved credentials
       /wechat stop   — stop the bridge
       /wechat status — show current status

Prerequisite: enable the "ClawBot" plugin inside WeChat
  (WeChat → Me → Settings → Plugins → ClawBot)
"""
from __future__ import annotations

import json
import threading
import base64 as _b64_mod
import struct as _struct_mod
import secrets as _secrets_mod

from ui.render import clr, info, ok, warn, err
import runtime
import logging_utils as _log

_wechat_thread: threading.Thread | None = None
_wechat_stop = threading.Event()

_ILINK_BASE_URL         = "https://ilinkai.weixin.qq.com"
_ILINK_APP_ID           = "bot"
_ILINK_CLIENT_VERSION   = (2 << 16) | (2 << 8) | 0
_ILINK_CHANNEL_VERSION  = "2.2.0"
_ILINK_DEFAULT_BOT_TYPE = "3"

_WX_EP_GET_UPDATES   = "ilink/bot/getupdates"
_WX_EP_SEND_MESSAGE  = "ilink/bot/sendmessage"
_WX_EP_SEND_TYPING   = "ilink/bot/sendtyping"
_WX_EP_GET_BOT_QR    = "ilink/bot/get_bot_qrcode"
_WX_EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"

_WX_LONG_POLL_TIMEOUT = 37
_WX_API_TIMEOUT       = 15
_WX_QR_TIMEOUT        = 37

_WX_MSG_TYPE_BOT   = 2
_WX_MSG_STATE_DONE = 2
_WX_ITEM_TEXT      = 1
_WX_TYPING_START   = 1

_wx_context_tokens: dict = {}
_wx_seen_msgids: set = set()


# ── HTTP helpers ───────────────────────────────────────────────────────────

def _wx_random_uin() -> str:
    value = _struct_mod.unpack(">I", _secrets_mod.token_bytes(4))[0]
    return _b64_mod.b64encode(str(value).encode()).decode("ascii")

def _wx_app_headers() -> dict:
    return {
        "iLink-App-Id": _ILINK_APP_ID,
        "iLink-App-ClientVersion": str(_ILINK_CLIENT_VERSION),
    }

def _wx_auth_headers(token: str, body: str) -> dict:
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _wx_random_uin(),
        **_wx_app_headers(),
    }

def _wx_get(base_url: str, endpoint: str, timeout: int = _WX_QR_TIMEOUT) -> dict | None:
    import urllib.request
    url = f"{base_url.rstrip('/')}/{endpoint}"
    req = urllib.request.Request(url, headers=_wx_app_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None

def _wx_post(base_url: str, endpoint: str, token: str, payload: dict,
             timeout: int = _WX_API_TIMEOUT) -> dict | None:
    import urllib.request
    payload["base_info"] = {"channel_version": _ILINK_CHANNEL_VERSION}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    url = f"{base_url.rstrip('/')}/{endpoint}"
    data = body.encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_wx_auth_headers(token, body))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None

def _wx_get_updates(base_url: str, token: str, sync_buf: str) -> dict | None:
    import urllib.request, socket as _socket
    payload = {
        "get_updates_buf": sync_buf,
        "base_info": {"channel_version": _ILINK_CHANNEL_VERSION},
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    url = f"{base_url.rstrip('/')}/{_WX_EP_GET_UPDATES}"
    data = body.encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_wx_auth_headers(token, body))
    try:
        with urllib.request.urlopen(req, timeout=_WX_LONG_POLL_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (_socket.timeout, TimeoutError):
        return {"ret": 0, "errcode": 0, "msgs": [], "get_updates_buf": sync_buf}
    except Exception:
        return None

def _wx_print_qr(url_or_value: str) -> None:
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url_or_value)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        print(f"\n  {url_or_value}\n")
        info("(Install 'qrcode' for inline QR rendering: pip install qrcode)")

def _wx_send(user_id: str, text: str, config: dict) -> None:
    import uuid as _uuid
    token    = config.get("wechat_token", "")
    base_url = config.get("wechat_base_url", _ILINK_BASE_URL)
    if not token or not user_id:
        return
    ctx_token = _wx_context_tokens.get(user_id)
    MAX = 2000
    chunks = [text[i:i+MAX] for i in range(0, max(len(text), 1), MAX)]
    for chunk in chunks:
        msg: dict = {
            "from_user_id": "",
            "to_user_id": user_id,
            "client_id": str(_uuid.uuid4()),
            "message_type": _WX_MSG_TYPE_BOT,
            "message_state": _WX_MSG_STATE_DONE,
            "item_list": [{"type": _WX_ITEM_TEXT, "text_item": {"text": chunk}}],
        }
        if ctx_token:
            msg["context_token"] = ctx_token
        _wx_post(base_url, _WX_EP_SEND_MESSAGE, token, {"msg": msg})

def _wx_typing(user_id: str, config: dict) -> None:
    ticket = config.get(f"_wx_typing_ticket_{user_id}")
    if not ticket:
        return
    token    = config.get("wechat_token", "")
    base_url = config.get("wechat_base_url", _ILINK_BASE_URL)
    _wx_post(base_url, _WX_EP_SEND_TYPING, token, {
        "ilink_user_id": user_id,
        "typing_ticket": ticket,
        "status": _WX_TYPING_START,
    }, timeout=5)

def _wx_typing_loop(user_id: str, stop_event: threading.Event, config: dict) -> None:
    while not stop_event.is_set():
        _wx_typing(user_id, config)
        stop_event.wait(4)


# ── QR login ───────────────────────────────────────────────────────────────

def _wx_qr_login(config: dict, bot_type: str = _ILINK_DEFAULT_BOT_TYPE,
                 timeout_seconds: int = 480) -> bool:
    from config import save_config
    import time as _time

    info("Fetching WeChat QR code from iLink...")
    base_url = _ILINK_BASE_URL

    qr_resp = _wx_get(base_url, f"{_WX_EP_GET_BOT_QR}?bot_type={bot_type}")
    if not qr_resp:
        err("Could not reach iLink API. Check your network connection.")
        return False

    qrcode_value = str(qr_resp.get("qrcode") or "")
    qrcode_img   = str(qr_resp.get("qrcode_img_content") or "")
    if not qrcode_value:
        err("iLink returned an empty QR code. Try again later.")
        return False

    print()
    print(clr("  请用微信扫描以下二维码 / Scan with WeChat:", "cyan"))
    _wx_print_qr(qrcode_img or qrcode_value)
    print(clr("  等待扫码中... / Waiting for scan...", "cyan"))

    deadline      = _time.time() + timeout_seconds
    refresh_count = 0
    current_base  = base_url

    while _time.time() < deadline:
        status_resp = _wx_get(
            current_base,
            f"{_WX_EP_GET_QR_STATUS}?qrcode={qrcode_value}",
        )
        if status_resp is None:
            _time.sleep(1)
            continue

        status = str(status_resp.get("status") or "wait")

        if status == "wait":
            print(".", end="", flush=True)
        elif status == "scaned":
            print()
            info("已扫码，请在微信里点击确认 / Scanned — confirm in WeChat...")
        elif status == "scaned_but_redirect":
            redirect_host = str(status_resp.get("redirect_host") or "")
            if redirect_host:
                current_base = f"https://{redirect_host}"
        elif status == "expired":
            refresh_count += 1
            if refresh_count > 3:
                print()
                err("二维码多次过期 / QR code expired too many times. Please try again.")
                return False
            print()
            info(f"二维码已过期，正在刷新... ({refresh_count}/3) / QR expired, refreshing...")
            qr_resp = _wx_get(base_url, f"{_WX_EP_GET_BOT_QR}?bot_type={bot_type}")
            if not qr_resp:
                err("Failed to refresh QR code.")
                return False
            qrcode_value = str(qr_resp.get("qrcode") or "")
            qrcode_img   = str(qr_resp.get("qrcode_img_content") or "")
            _wx_print_qr(qrcode_img or qrcode_value)
        elif status == "confirmed":
            token    = str(status_resp.get("bot_token") or "")
            new_base = str(status_resp.get("baseurl") or base_url)
            acct_id  = str(status_resp.get("ilink_bot_id") or "")
            if not token:
                err("iLink confirmed but returned no token. Try again.")
                return False
            print()
            config["wechat_token"]    = token
            config["wechat_base_url"] = new_base
            if acct_id:
                config["wechat_account_id"] = acct_id
            save_config(config)
            ok(f"微信登录成功 / WeChat authenticated (account: {acct_id or 'unknown'})")
            return True

        _time.sleep(1)

    print()
    err("登录超时 / WeChat QR login timed out. Please try again.")
    return False


# ── Poll loop ──────────────────────────────────────────────────────────────

def _wx_poll_loop(token: str, base_url: str, config: dict) -> str:
    """Returns "stopped", "auth_error", or raises on unexpected fatal error."""
    from tools import _wx_thread_local
    session_ctx = runtime.get_session_ctx(config.get("_session_id", "default"))
    run_query_cb = session_ctx.run_query
    sync_buf = ""
    consecutive_failures = 0

    session_ctx.wx_send = lambda uid, txt: _wx_send(uid, txt, config)

    while not _wechat_stop.is_set():
        try:
            result = _wx_get_updates(base_url, token, sync_buf)
            if result is None:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    print(clr("\n  ⚠ WeChat: repeated connection failures, retrying in 30s...", "yellow"))
                    _wechat_stop.wait(30)
                    consecutive_failures = 0
                else:
                    _wechat_stop.wait(2)
                continue
            consecutive_failures = 0

            ret     = result.get("ret",     0)
            errcode = result.get("errcode", 0)
            if ret not in (0, None) or errcode not in (0, None):
                if ret == -14 or errcode == -14:
                    print(clr("\n  ⚠ WeChat: session expired — re-authenticate with /wechat login", "yellow"))
                    config.pop("wechat_token", None)
                    config.pop("wechat_base_url", None)
                    from config import save_config
                    save_config(config)
                    _log.warn("bridge_auth_error", bridge="wechat", ret=ret, errcode=errcode)
                    session_ctx.wx_send = None
                    return "auth_error"
                errmsg = result.get("errmsg", "")
                print(clr(f"\n  ⚠ WeChat: API error ret={ret} errcode={errcode} {errmsg}, retrying...", "yellow"))
                _wechat_stop.wait(5)
                continue

            new_buf = result.get("get_updates_buf")
            if new_buf:
                sync_buf = new_buf

            for msg in result.get("msgs") or []:
                ctx_tok  = msg.get("context_token")
                from_uid = str(msg.get("from_user_id") or "").strip()
                if ctx_tok and from_uid:
                    _wx_context_tokens[from_uid] = ctx_tok

                msg_id = msg.get("message_id") or msg.get("seq") or msg.get("client_id") or ""
                if msg_id and msg_id in _wx_seen_msgids:
                    continue
                if msg_id:
                    _wx_seen_msgids.add(msg_id)
                    if len(_wx_seen_msgids) > 2000:
                        oldest = list(_wx_seen_msgids)[:500]
                        for k in oldest:
                            _wx_seen_msgids.discard(k)

                if msg.get("message_type") == 2:
                    continue

                text = ""
                for item in msg.get("item_list") or []:
                    if item.get("type") == _WX_ITEM_TEXT:
                        text = (item.get("text_item") or {}).get("text", "").strip()
                        break
                if not text:
                    text = str(msg.get("content") or msg.get("text") or "").strip()

                if not text or not from_uid:
                    continue

                evt = session_ctx.wx_input_event
                if evt and config.get("_wx_current_user_id") == from_uid:
                    session_ctx.wx_input_value = text
                    evt.set()
                    continue

                print(clr(f"\n  📩 WeChat [{from_uid[:8]}]: {text}", "cyan"))

                # ── Interactive PTY session ────────────────────────────────
                from bridges.interactive_session import get_session, set_session, remove_session, InteractiveSession
                _sess_key = f"wx_{from_uid}"
                _active_sess = get_session(_sess_key)

                if _active_sess:
                    stripped = text.strip().lower()
                    _norm = stripped.replace(" ", "")
                    _exit_set = {"!exit", "!quit", "!stop", "/exit", "/quit"}
                    if stripped in _exit_set or _norm in _exit_set or stripped == "/exit_session":
                        remove_session(_sess_key)
                        _wx_send(from_uid, "⏹ Interactive session ended.", config)
                        continue
                    if stripped in ("!ping", "!screen", "!refresh") or _norm in ("!ping", "!screen", "!refresh"):
                        _wx_send(from_uid, "🔄 Refreshing screen…", config)
                        _active_sess.force_flush()
                        continue
                    _active_sess.send_input(text)
                    _wx_send(from_uid, f"⌨ `{text[:60]}`", config)
                    continue

                if text.strip().startswith("!"):
                    raw_cmd = text.strip()[1:].strip()
                    if not raw_cmd or raw_cmd.lower() == "stop":
                        from bridges.terminal_runner import stop_terminal
                        killed = stop_terminal(_sess_key)
                        _wx_send(from_uid, "🛑 Stopped." if killed else "ℹ Nothing running.", config)
                        continue
                    _interactive_progs = ("claude", "python", "python3", "ipython",
                                          "bash", "sh", "zsh", "node", "irb",
                                          "sqlite3", "psql", "mysql", "redis-cli")
                    _base = raw_cmd.split()[0].split("/")[-1]
                    if _base in _interactive_progs:
                        def _start_pty_wx(cmd, uid, skey):
                            def _send(out): _wx_send(uid, out, config)
                            try:
                                sess = InteractiveSession(cmd, _send, session_key=skey)
                                set_session(skey, sess)
                                _wx_send(uid,
                                         f"▶ {cmd} 已启动\n发消息即可交互，发 !exit 结束会话",
                                         config)
                            except Exception as e:
                                _wx_send(uid, f"⚠ 无法启动: {e}", config)
                        threading.Thread(target=_start_pty_wx,
                                         args=(raw_cmd, from_uid, _sess_key),
                                         daemon=True).start()
                        continue
                    def _wx_terminal(cmd, uid, skey):
                        from bridges.terminal_runner import run_terminal
                        _wx_send(uid, f"▶ {cmd}", config)
                        run_terminal(cmd, lambda out: _wx_send(uid, out, config),
                                     session_key=skey, stop_event=_wechat_stop)
                    threading.Thread(target=_wx_terminal,
                                     args=(raw_cmd, from_uid, _sess_key),
                                     daemon=True).start()
                    continue

                if text.strip().lower() in ("/stop", "/off"):
                    _wx_send(from_uid, "🔴 cheetahclaws bridge stopped.", config)
                    _wechat_stop.set()
                    break

                if text.strip().lower() == "/start":
                    _wx_send(from_uid, "🟢 cheetahclaws bridge is active. Send me anything.", config)
                    continue

                if text.strip().startswith("/"):
                    slash_cb = session_ctx.handle_slash
                    if slash_cb:
                        def _wx_slash_runner(_slash_text, _uid):
                            _wx_thread_local.active = True
                            config["_wx_current_user_id"] = _uid
                            try:
                                cmd_type = slash_cb(_slash_text)
                            except Exception as e:
                                _wx_send(_uid, f"⚠ Error: {e}", config)
                                return
                            finally:
                                _wx_thread_local.active = False
                                config.pop("_wx_current_user_id", None)
                            if cmd_type == "simple":
                                cmd_name = _slash_text.strip().split()[0]
                                _wx_send(_uid, f"✅ {cmd_name} executed.", config)
                                return
                            wx_state = session_ctx.agent_state
                            if wx_state and wx_state.messages:
                                for m in reversed(wx_state.messages):
                                    if m.get("role") == "assistant":
                                        content = m.get("content", "")
                                        if isinstance(content, list):
                                            parts = [
                                                b.get("text", "") if isinstance(b, dict) and b.get("type") == "text"
                                                else (b if isinstance(b, str) else "")
                                                for b in content
                                            ]
                                            content = "\n".join(p for p in parts if p)
                                        if content:
                                            _wx_send(_uid, content, config)
                                        break
                        threading.Thread(
                            target=_wx_slash_runner, args=(text, from_uid), daemon=True
                        ).start()
                    continue

                # ── !command: run shell command and stream output ──────────
                if text.strip().startswith("!"):
                    raw_cmd = text.strip()[1:].strip()
                    sess_key = f"wx_{from_uid}"

                    if raw_cmd.lower() in ("stop", ""):
                        from bridges.terminal_runner import stop_terminal
                        killed = stop_terminal(sess_key)
                        _wx_send(from_uid, "🛑 Command stopped." if killed else "ℹ No command running.", config)
                        continue

                    def _wx_terminal(cmd, uid, skey):
                        from bridges.terminal_runner import run_terminal
                        _wx_send(uid, f"▶ {cmd}", config)
                        run_terminal(cmd, lambda out: _wx_send(uid, out, config),
                                     session_key=skey, stop_event=_wechat_stop)

                    threading.Thread(target=_wx_terminal,
                                     args=(raw_cmd, from_uid, sess_key),
                                     daemon=True).start()
                    continue

                # ── Claude query: stream in timed paragraphs ───────────────
                # WeChat does not support message editing, so we buffer chunks
                # and send a new message every ~3 seconds as text arrives.
                def _wx_bg_runner(q_text, uid):
                    import time as _time

                    _typing_stop = threading.Event()
                    _typing_t = threading.Thread(
                        target=_wx_typing_loop, args=(uid, _typing_stop, config), daemon=True
                    )
                    _typing_t.start()

                    _chunks: list[str] = []
                    _last_send = [_time.monotonic()]
                    _stream_lock = threading.Lock()
                    _WX_STREAM_INTERVAL = 3.0   # send partial response every 3 s
                    _WX_STREAM_MIN_LEN  = 80    # don't send tiny fragments

                    def _flush_chunks():
                        text_so_far = "".join(_chunks)
                        if len(text_so_far) >= _WX_STREAM_MIN_LEN:
                            _wx_send(uid, text_so_far[-2000:], config)
                            _chunks.clear()
                        _last_send[0] = _time.monotonic()

                    def _on_chunk(chunk: str):
                        _chunks.append(chunk)
                        with _stream_lock:
                            if _time.monotonic() - _last_send[0] >= _WX_STREAM_INTERVAL:
                                _flush_chunks()

                    def _on_tool_start(name: str, inputs: dict):
                        cmd_preview = str(inputs.get("command", inputs.get("file_path", ""))).strip()[:60]
                        label = f"🔧 {name}" + (f": {cmd_preview}" if cmd_preview else "")
                        _wx_send(uid, label, config)

                    session_ctx.on_text_chunk = _on_chunk
                    session_ctx.on_tool_start = _on_tool_start
                    session_ctx.on_tool_end   = None

                    config["_wx_current_user_id"] = uid
                    config["_in_wechat_turn"] = True
                    try:
                        if run_query_cb:
                            run_query_cb(q_text)
                    except Exception as e:
                        _typing_stop.set()
                        _wx_send(uid, f"⚠ Error: {e}", config)
                        return
                    finally:
                        session_ctx.on_text_chunk = None
                        session_ctx.on_tool_start = None
                        config.pop("_in_wechat_turn", None)
                        config.pop("_wx_current_user_id", None)

                    _typing_stop.set()
                    # Send whatever remains in the chunk buffer
                    remaining = "".join(_chunks).strip()
                    if remaining:
                        _wx_send(uid, remaining, config)
                    elif not _chunks:
                        # Nothing streamed — fall back to state.messages
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
                                        _wx_send(uid, content, config)
                                    break

                threading.Thread(target=_wx_bg_runner, args=(text, from_uid), daemon=True).start()

        except Exception:
            _wechat_stop.wait(5)

    session_ctx.wx_send = None
    return "stopped"


_WX_BACKOFF_INITIAL = 2.0
_WX_BACKOFF_MAX     = 120.0


def _wx_supervisor(token: str, base_url: str, config: dict) -> None:
    """Wrap _wx_poll_loop with exponential-backoff reconnect on unexpected exit."""
    global _wechat_thread
    backoff = _WX_BACKOFF_INITIAL
    attempt = 0
    while not _wechat_stop.is_set():
        attempt += 1
        try:
            reason = _wx_poll_loop(token, base_url, config)
        except Exception as exc:
            if _wechat_stop.is_set():
                break
            _log.warn("bridge_crash", bridge="wechat", attempt=attempt,
                      error=str(exc)[:200], backoff_s=backoff)
            print(clr(f"\n  ⚠ WeChat bridge crashed (attempt {attempt}), "
                      f"reconnecting in {backoff:.0f}s…", "yellow"))
            _wechat_stop.wait(backoff)
            backoff = min(backoff * 2, _WX_BACKOFF_MAX)
            continue

        if reason == "auth_error":
            print(clr("\n  ⚠ WeChat: session expired — stopping bridge. Use /wechat login.", "yellow"))
            _log.warn("bridge_auth_error_stop", bridge="wechat")
            break
        break

    _wechat_thread = None


def _wx_start_bridge(config) -> None:
    global _wechat_thread, _wechat_stop
    token    = config.get("wechat_token", "")
    base_url = config.get("wechat_base_url", _ILINK_BASE_URL)
    _wechat_stop = threading.Event()
    _wechat_thread = threading.Thread(
        target=_wx_supervisor, args=(token, base_url, config), daemon=True,
        name="wechat-bridge"
    )
    _wechat_thread.start()
    ok("WeChat bridge started.")
    info("Send a message from WeChat — it will be processed here.")
    info("Stop with /wechat stop or send /stop from WeChat.")


# ── Slash command ──────────────────────────────────────────────────────────

def cmd_wechat(args: str, _state, config) -> bool:
    """WeChat bridge via Tencent iLink Bot API — authenticate with QR code scan.

    Prerequisites:
      Enable "ClawBot" in WeChat: Me → Settings → Plugins → ClawBot

    Usage:
      /wechat login      — scan QR code with WeChat to authenticate & start
      /wechat            — start bridge using saved credentials (login if needed)
      /wechat stop       — stop the bridge
      /wechat status     — show current status
      /wechat logout     — clear saved credentials
    """
    global _wechat_thread, _wechat_stop
    from config import save_config

    sub = args.strip().split()[0].lower() if args.strip() else ""

    if sub in ("stop", "off"):
        if _wechat_thread and _wechat_thread.is_alive():
            _wechat_stop.set()
            _wechat_thread.join(timeout=5)
            _wechat_thread = None
            ok("WeChat bridge stopped.")
        else:
            warn("WeChat bridge is not running.")
        return True

    if sub == "status":
        running  = _wechat_thread and _wechat_thread.is_alive()
        token    = config.get("wechat_token", "")
        base_url = config.get("wechat_base_url", _ILINK_BASE_URL)
        acct     = config.get("wechat_account_id", "")
        if running:
            ok(f"WeChat bridge running  (account: {acct or 'unknown'}, iLink: {base_url})")
        elif token:
            info("Configured but not running. Use /wechat to start.")
        else:
            info("Not authenticated. Use /wechat login to scan the QR code.")
        return True

    if sub == "logout":
        if _wechat_thread and _wechat_thread.is_alive():
            _wechat_stop.set()
            _wechat_thread.join(timeout=5)
            _wechat_thread = None
        config.pop("wechat_token", None)
        config.pop("wechat_base_url", None)
        config.pop("wechat_account_id", None)
        save_config(config)
        ok("WeChat credentials cleared.")
        return True

    if sub == "login":
        if _wechat_thread and _wechat_thread.is_alive():
            warn("Bridge is already running. Use /wechat stop first.")
            return True
        if not _wx_qr_login(config):
            return True
        _wx_start_bridge(config)
        return True

    if _wechat_thread and _wechat_thread.is_alive():
        warn("WeChat bridge is already running. Use /wechat stop first.")
        return True

    token = config.get("wechat_token", "")
    if not token:
        info("No saved credentials — starting QR login flow.")
        if not _wx_qr_login(config):
            return True
        _wx_start_bridge(config)
        return True

    base_url = config.get("wechat_base_url", _ILINK_BASE_URL)
    probe = _wx_post(base_url, _WX_EP_GET_UPDATES, token, {"get_updates_buf": ""}, timeout=8)
    if probe is not None and probe.get("ret") == -14:
        warn("Session expired. Re-authenticating via QR code...")
        config.pop("wechat_token", None)
        config.pop("wechat_base_url", None)
        save_config(config)
        if not _wx_qr_login(config):
            return True

    _wx_start_bridge(config)
    return True
