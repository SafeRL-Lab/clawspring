"""Core agent loop: neutral message format, multi-provider streaming."""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Generator

from tool_registry import get_tool_schemas
from tools import execute_tool
import tools as _tools_init  # ensure built-in tools are registered on import
from providers import stream, AssistantTurn, TextChunk, ThinkingChunk, detect_provider
from compaction import maybe_compact, estimate_tokens, get_context_limit, compact_messages
import logging_utils as _log
import quota as _quota
from circuit_breaker import CircuitOpenError as _CircuitOpenError
import runtime

# ── Re-export event types (used by cheetahclaws.py) ────────────────────────
__all__ = [
    "AgentState", "run",
    "TextChunk", "ThinkingChunk",
    "ToolStart", "ToolEnd", "TurnDone", "PermissionRequest",
]


@dataclass
class AgentState:
    """Mutable session state. messages use the neutral provider-independent format."""
    messages: list = field(default_factory=list)
    total_input_tokens:  int = 0
    total_output_tokens: int = 0
    turn_count: int = 0


@dataclass
class ToolStart:
    name:   str
    inputs: dict

@dataclass
class ToolEnd:
    name:      str
    result:    str
    permitted: bool = True

@dataclass
class TurnDone:
    input_tokens:  int
    output_tokens: int

@dataclass
class PermissionRequest:
    description: str
    granted: bool = False


# ── Agent loop ─────────────────────────────────────────────────────────────

def run(
    user_message: str,
    state: AgentState,
    config: dict,
    system_prompt: str,
    depth: int = 0,
    cancel_check=None,
) -> Generator:
    """
    Multi-turn agent loop (generator).
    Yields: TextChunk | ThinkingChunk | ToolStart | ToolEnd |
            PermissionRequest | TurnDone

    Args:
        depth: sub-agent nesting depth, 0 for top-level
        cancel_check: callable returning True to abort the loop early
    """
    # Append user turn in neutral format
    user_msg = {"role": "user", "content": user_message}
    # Attach pending image from /image command if present
    sctx = runtime.get_ctx(config)
    pending_img = sctx.pending_image
    sctx.pending_image = None
    if pending_img:
        user_msg["images"] = [pending_img]
    state.messages.append(user_msg)

    # Inject runtime metadata into config so tools (e.g. Agent) can access it
    config = {**config, "_depth": depth, "_system_prompt": system_prompt}
    session_id = config.get("_session_id", "default")

    # Wire up structured logging from config (idempotent, cheap)
    _log.configure_from_config(config)

    while True:
        if cancel_check and cancel_check():
            return
        state.turn_count += 1
        assistant_turn: AssistantTurn | None = None

        # Compact context if approaching window limit
        maybe_compact(state, config)

        # ── Quota check — before spending tokens ──────────────────────────
        try:
            _quota.check_quota(session_id, config)
        except _quota.QuotaExceeded as qe:
            _log.warn("quota_exceeded", session_id=session_id, reason=qe.reason)
            yield TextChunk(f"\n[Quota exceeded — {qe.reason}]\n")
            break

        # Stream from provider — retry on ANY error (never crash the session)
        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                for event in stream(
                    model=config["model"],
                    system=system_prompt,
                    messages=state.messages,
                    tool_schemas=get_tool_schemas(),
                    config=config,
                ):
                    if isinstance(event, (TextChunk, ThinkingChunk)):
                        yield event
                    elif isinstance(event, AssistantTurn):
                        assistant_turn = event
                        # Record usage for quota tracking
                        _quota.record_usage(
                            session_id, config["model"],
                            event.in_tokens, event.out_tokens,
                        )
                break  # success — exit retry loop

            except _CircuitOpenError as e:
                _log.warn("circuit_open_skip", session_id=session_id,
                          error=str(e)[:200])
                yield TextChunk(f"\n[{e}]\n")
                return  # circuit manages its own cooldown — don't retry

            except Exception as e:
                if attempt >= max_retries:
                    _log.error("api_failed", session_id=session_id,
                               error_type=type(e).__name__,
                               error=_truncate_err(str(e)))
                    yield TextChunk(f"\n[Failed after {max_retries} retries — {_truncate_err(str(e))}. Please retry manually.]\n")
                    break  # give up gracefully instead of crashing

                err_str  = str(e).lower()
                err_type = type(e).__name__

                is_context_too_long = any(s in err_str for s in [
                    "context_length", "context window", "too many tokens",
                    "input is too long", "prompt is too long",
                    "request too large", "token limit",
                ])
                is_overloaded = "overloaded" in err_str or "overloaded_error" in err_type
                is_rate_limit = "rate_limit" in err_str or e.__class__.__name__ == "RateLimitError"

                if is_context_too_long:
                    _force_compact(state, config)
                    yield TextChunk(f"\n[Context too long — compacted and retrying (attempt {attempt+1}/{max_retries})]\n")
                    continue

                # All other errors: backoff + retry (overloaded/rate-limit get longer backoff)
                if is_overloaded or is_rate_limit:
                    backoff = min(30, 2 ** (attempt + 2))  # 4s, 8s, 16s
                else:
                    backoff = 2 ** (attempt + 1)  # 2s, 4s, 8s
                _log.warn("api_retry", session_id=session_id,
                          attempt=attempt + 1, max_retries=max_retries,
                          error_type=err_type,
                          error=_truncate_err(str(e)),
                          backoff_s=backoff)
                yield TextChunk(f"\n[Retry {attempt+1}/{max_retries} after {backoff}s — {err_type}: {_truncate_err(str(e))}]\n")
                time.sleep(backoff)

        if assistant_turn is None:
            break

        # Record assistant turn in neutral format
        state.messages.append({
            "role":       "assistant",
            "content":    assistant_turn.text,
            "tool_calls": assistant_turn.tool_calls,
        })

        state.total_input_tokens  += assistant_turn.in_tokens
        state.total_output_tokens += assistant_turn.out_tokens
        yield TurnDone(assistant_turn.in_tokens, assistant_turn.out_tokens)

        if not assistant_turn.tool_calls:
            break   # No tools → conversation turn complete

        # ── Execute tools ────────────────────────────────────────────────
        for tc in assistant_turn.tool_calls:
            yield ToolStart(tc["name"], tc["input"])
            _log.debug("tool_start", session_id=session_id,
                       tool=tc["name"], input_keys=list(tc["input"].keys()))

            # Permission gate
            permitted = _check_permission(tc, config)
            if not permitted:
                if config.get("permission_mode") == "plan":
                    # Plan mode: silently deny writes (no user prompt)
                    permitted = False
                else:
                    req = PermissionRequest(description=_permission_desc(tc))
                    yield req
                    permitted = req.granted

            if not permitted:
                if config.get("permission_mode") == "plan":
                    plan_file = runtime.get_ctx(config).plan_file or ""
                    result = (
                        f"[Plan mode] Write operations are blocked except to the plan file: {plan_file}\n"
                        "Finish your analysis and write the plan to the plan file. "
                        "The user will run /plan done to exit plan mode and begin implementation."
                    )
                else:
                    result = "Denied: user rejected this operation"
            else:
                result = execute_tool(
                    tc["name"], tc["input"],
                    permission_mode="accept-all",  # already gate-checked above
                    config=config,
                )

            _log.debug("tool_end", session_id=session_id,
                       tool=tc["name"], permitted=permitted,
                       result_len=len(result))
            yield ToolEnd(tc["name"], result, permitted)

            # Append tool result in neutral format
            state.messages.append({
                "role":         "tool",
                "tool_call_id": tc["id"],
                "name":         tc["name"],
                "content":      result,
            })


# ── Helpers ───────────────────────────────────────────────────────────────

def _check_permission(tc: dict, config: dict) -> bool:
    """Return True if operation is auto-approved (no need to ask user)."""
    perm_mode = config.get("permission_mode", "auto")
    name = tc["name"]

    # Plan mode tools are always auto-approved
    if name in ("EnterPlanMode", "ExitPlanMode"):
        return True

    if perm_mode == "accept-all":
        return True
    if perm_mode == "manual":
        return False   # always ask

    if perm_mode == "plan":
        # Allow writes ONLY to the plan file
        if name in ("Write", "Edit"):
            plan_file = runtime.get_ctx(config).plan_file or ""
            target = tc["input"].get("file_path", "")
            if plan_file and target and \
               os.path.normpath(target) == os.path.normpath(plan_file):
                return True
            return False
        if name == "NotebookEdit":
            return False
        if name == "Bash":
            from tools import _is_safe_bash
            return _is_safe_bash(tc["input"].get("command", ""))
        return True  # reads are fine

    # "auto" mode: only ask for writes and non-safe bash
    if name in ("Read", "Glob", "Grep", "WebFetch", "WebSearch"):
        return True
    if name == "Bash":
        from tools import _is_safe_bash
        return _is_safe_bash(tc["input"].get("command", ""))
    return False   # Write, Edit → ask


def _permission_desc(tc: dict) -> str:
    name = tc["name"]
    inp  = tc["input"]
    if name == "Bash":   return f"Run: {inp.get('command', '')}"
    if name == "Write":  return f"Write to: {inp.get('file_path', '')}"
    if name == "Edit":   return f"Edit: {inp.get('file_path', '')}"
    return f"{name}({list(inp.values())[:1]})"


def _force_compact(state: AgentState, config: dict) -> bool:
    """Force compaction regardless of threshold. Used when API rejects for context too long."""
    limit = get_context_limit(config.get("model", ""))
    before = estimate_tokens(state.messages)
    if before <= 0:
        return False
    from compaction import snip_old_tool_results
    snip_old_tool_results(state.messages, max_chars=1000, preserve_last_n_turns=3)
    if estimate_tokens(state.messages) < limit * 0.9:
        return True
    state.messages = compact_messages(state.messages, config)
    from compaction import _restore_plan_context
    state.messages.extend(_restore_plan_context(config))
    after = estimate_tokens(state.messages)
    return after < before


def _truncate_err(s: str, max_len: int = 120) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."
