"""
tools_interaction.py — Interactive input tools: AskUserQuestion, SleepTimer,
and bridge-routing helpers (Telegram / WeChat / Slack).
"""
from __future__ import annotations

import threading
from typing import Optional

# ── Bridge turn-detection (thread-local) ──────────────────────────────────

_tg_thread_local    = threading.local()
_wx_thread_local    = threading.local()
_slack_thread_local = threading.local()


def _is_in_tg_turn(config: dict) -> bool:
    import runtime
    return (getattr(_tg_thread_local, "active", False)
            or bool(runtime.get_ctx(config).in_telegram_turn))


def _is_in_wx_turn(config: dict) -> bool:
    import runtime
    return (getattr(_wx_thread_local, "active", False)
            or bool(runtime.get_ctx(config).in_wechat_turn))


def _is_in_slack_turn(config: dict) -> bool:
    import runtime
    return (getattr(_slack_thread_local, "active", False)
            or bool(runtime.get_ctx(config).in_slack_turn))


# ── AskUserQuestion state ─────────────────────────────────────────────────

_pending_questions: list[dict] = []
_ask_lock = threading.Lock()

_INPUT_WAIT_TIMEOUT = 300  # seconds before a remote input request times out


def _ask_user_question(
    question: str,
    options: list[dict] | None = None,
    allow_freetext: bool = True,
) -> str:
    """Block the agent loop and surface a question to the user in the terminal."""
    event         = threading.Event()
    result_holder: list[str] = []
    entry = {
        "question":     question,
        "options":      options or [],
        "allow_freetext": allow_freetext,
        "event":        event,
        "result":       result_holder,
    }
    with _ask_lock:
        _pending_questions.append(entry)

    event.wait(timeout=300)

    if result_holder:
        return result_holder[0]
    return "(no answer — timeout)"


# ── ask_input_interactive (bridge routing) ────────────────────────────────

def ask_input_interactive(prompt: str, config: dict,
                          menu_text: str = None) -> str:
    """Route input prompt to Telegram / WeChat / Slack bridge or terminal."""
    import re as _re
    import threading as _threading
    import runtime as _runtime

    _session_ctx = _runtime.get_session_ctx(config.get("_session_id", "default"))

    # ── Slack ──────────────────────────────────────────────────────────────
    if _is_in_slack_turn(config) and _session_ctx.slack_send is not None:
        clean_prompt = _re.sub(r'\x1b\[[0-9;]*m', '', prompt).strip()
        payload = ""
        if menu_text:
            payload += _re.sub(r'\x1b\[[0-9;]*m', '', menu_text).strip() + "\n\n"
        payload += f"❓ Input Required\n{clean_prompt}"
        slack_channel = (_runtime.get_ctx(config).slack_current_channel
                         or config.get("slack_channel", ""))
        _session_ctx.slack_send(slack_channel, payload)
        evt = _threading.Event()
        _session_ctx.slack_input_event = evt
        if not evt.wait(timeout=_INPUT_WAIT_TIMEOUT):
            _session_ctx.slack_input_event = None
            return "(timeout: no input received)"
        text = _session_ctx.slack_input_value.strip()
        _session_ctx.slack_input_event = None
        _session_ctx.slack_input_value = ""
        return text

    # ── WeChat ─────────────────────────────────────────────────────────────
    if _is_in_wx_turn(config) and _session_ctx.wx_send is not None:
        clean_prompt = _re.sub(r'\x1b\[[0-9;]*m', '', prompt).strip()
        payload = ""
        if menu_text:
            payload += _re.sub(r'\x1b\[[0-9;]*m', '', menu_text).strip() + "\n\n"
        payload += f"❓ 需要输入\n{clean_prompt}"
        _session_ctx.wx_send(_runtime.get_ctx(config).wx_current_user_id or "", payload)
        evt = _threading.Event()
        _session_ctx.wx_input_event = evt
        if not evt.wait(timeout=_INPUT_WAIT_TIMEOUT):
            _session_ctx.wx_input_event = None
            return "(timeout: no input received)"
        text = _session_ctx.wx_input_value.strip()
        _session_ctx.wx_input_event = None
        _session_ctx.wx_input_value = ""
        return text

    # ── Telegram ───────────────────────────────────────────────────────────
    if _is_in_tg_turn(config) and _session_ctx.tg_send is not None:
        token   = config.get("telegram_token")
        chat_id = config.get("telegram_chat_id")
        clean_prompt = _re.sub(r'\x1b\[[0-9;]*m', '', prompt).strip()
        payload = ""
        if menu_text:
            payload += _re.sub(r'\x1b\[[0-9;]*m', '', menu_text).strip() + "\n\n"
        payload += f"❓ *Input Required*\n{clean_prompt}"
        _session_ctx.tg_send(token, chat_id, payload)
        evt = _threading.Event()
        _session_ctx.tg_input_event = evt
        if not evt.wait(timeout=_INPUT_WAIT_TIMEOUT):
            _session_ctx.tg_input_event = None
            return "(timeout: no input received)"
        text = _session_ctx.tg_input_value.strip()
        _session_ctx.tg_input_event = None
        _session_ctx.tg_input_value = ""
        return text

    # ── Terminal ────────────────────────────────────────────────────────────
    try:
        rl_prompt = _re.sub(r'(\x1b\[[0-9;]*m)', r'\001\1\002', prompt)
        return input(rl_prompt)
    except (KeyboardInterrupt, EOFError):
        print()
        return ""


# ── drain_pending_questions ───────────────────────────────────────────────

def drain_pending_questions(config: dict) -> bool:
    """Render any pending AskUserQuestion calls and collect user answers."""
    with _ask_lock:
        pending = list(_pending_questions)
        _pending_questions.clear()

    if not pending:
        return False

    for entry in pending:
        question = entry["question"]
        options  = entry["options"]
        allow_ft = entry["allow_freetext"]
        event    = entry["event"]
        result   = entry["result"]

        print()
        print("\033[1;35m❓ Question from assistant:\033[0m")
        print(f"   {question}")

        if options:
            print()
            for i, opt in enumerate(options, 1):
                label = opt.get("label", "")
                desc  = opt.get("description", "")
                line  = f"  [{i}] {label}"
                if desc:
                    line += f" — {desc}"
                print(line)
            if allow_ft:
                print("  [0] Type a custom answer")
            print()

            while True:
                raw = ask_input_interactive(
                    "Your choice (number or text): ", config
                ).strip()
                if not raw:
                    break
                if raw.isdigit():
                    idx = int(raw)
                    if 1 <= idx <= len(options):
                        raw = options[idx - 1]["label"]
                        break
                    elif idx == 0 and allow_ft:
                        raw = ask_input_interactive("Your answer: ", config).strip()
                        break
                    else:
                        print(f"Invalid option: {idx}")
                        raw = ""
                        continue
                elif allow_ft:
                    break
        else:
            print()
            raw = ask_input_interactive("Your answer: ", config).strip()

        result.append(raw)
        event.set()

    return True


# ── SleepTimer ────────────────────────────────────────────────────────────

def _sleeptimer(seconds: int, config: dict) -> str:
    import runtime
    session_ctx = runtime.get_session_ctx(config.get("_session_id", "default"))
    cb = session_ctx.run_query
    if not cb:
        return "Error: No active REPL session (run_query not set for this session)"

    def worker():
        import time
        time.sleep(seconds)
        cb(
            "(System Automated Event): The timer has finished. "
            "Please wake up, perform any pending monitoring checks "
            "and report to the user now."
        )

    threading.Thread(target=worker, daemon=True).start()
    return (
        f"Timer successfully scheduled for {seconds} seconds. "
        "You can output your final thoughts and end your turn. "
        "You will be automatically awakened."
    )
