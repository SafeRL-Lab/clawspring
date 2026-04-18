"""Model-driven context garbage collection for conversation history.

Lets the LLM trash consumed tool results, keep relevant snippets,
and persist notes across turns to manage its context window.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GCState:
    trashed_ids: set = field(default_factory=set)
    snippets: dict = field(default_factory=dict)
    notes: dict = field(default_factory=dict)
    compact_xml: bool = False


def process_gc_call(params: dict, config: dict) -> str:
    gc_state: GCState = config.get("_gc_state")
    if gc_state is None:
        return "Error: no GC state available"

    trashed = params.get("trash") or []
    snippets = params.get("keep_snippets") or []
    notes = params.get("notes") or []
    trash_notes = params.get("trash_notes") or []

    for tid in trashed:
        gc_state.trashed_ids.add(tid)
        gc_state.snippets.pop(tid, None)

    for snippet in snippets:
        sid = snippet.get("id")
        if sid and sid not in gc_state.trashed_ids:
            gc_state.snippets[sid] = snippet

    for note in notes:
        name = note.get("name")
        content = note.get("content", "")
        if name:
            gc_state.notes[name] = content

    for name in trash_notes:
        gc_state.notes.pop(name, None)

    if params.get("compact_xml"):
        gc_state.compact_xml = True

    parts = []
    if trashed:
        parts.append(f"trashed {len(trashed)} results")
    if snippets:
        parts.append(f"kept snippets for {len(snippets)} results")
    if notes:
        parts.append(f"{len(notes)} notes saved")
    if trash_notes:
        parts.append(f"{len(trash_notes)} notes removed")
    if params.get("compact_xml"):
        parts.append("XML compaction enabled")
    parts.append(f"{len(gc_state.notes)} active notes, {len(gc_state.trashed_ids)} total trashed")
    return "GC applied: " + ", ".join(parts)


def apply_gc(messages: list, gc_state: GCState) -> list:
    if not gc_state.trashed_ids and not gc_state.snippets and not gc_state.compact_xml:
        return messages

    _compact_all = None
    _compact_selective = None
    last_asst_idx = -1

    if gc_state.compact_xml:
        try:
            try:
                from followup_compaction import compact_assistant_xml
            except ImportError:
                compact_assistant_xml = None  # followup_compaction not available yet
            _compact_all = compact_assistant_xml
        except ImportError:
            pass
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                last_asst_idx = i
                break

    if gc_state.trashed_ids:
        try:
            try:
                from followup_compaction import compact_assistant_xml
            except ImportError:
                compact_assistant_xml = None  # followup_compaction not available yet
            _compact_selective = compact_assistant_xml_selective
        except ImportError:
            pass

    result = []
    for idx, msg in enumerate(messages):
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            if _compact_all and idx != last_asst_idx:
                stubbed = dict(msg)
                stubbed["content"] = _compact_all(msg["content"], msg["tool_calls"])
                result.append(stubbed)
                continue
            if _compact_selective:
                tc_ids = {tc.get("id") for tc in msg["tool_calls"]}
                targeted = tc_ids & gc_state.trashed_ids
                if targeted:
                    stubbed = dict(msg)
                    stubbed["content"] = _compact_selective(
                        msg["content"], msg["tool_calls"], targeted,
                    )
                    result.append(stubbed)
                    continue
            result.append(msg)
            continue
        if role != "tool":
            result.append(msg)
            continue
        tc_id = msg.get("tool_call_id", "")
        if tc_id in gc_state.trashed_ids:
            stubbed = dict(msg)
            name = msg.get("name", "tool")
            stubbed["content"] = f"[{name} result -- trashed by model]"
            result.append(stubbed)
        elif tc_id in gc_state.snippets:
            transformed = dict(msg)
            transformed["content"] = _apply_snippet(msg["content"], gc_state.snippets[tc_id])
            result.append(transformed)
        else:
            result.append(msg)
    return result


def _apply_snippet(content: str, snippet: dict) -> str:
    if not content:
        return content
    lines = content.split("\n")

    if "keep_after" in snippet:
        anchor = snippet["keep_after"]
        idx = _find_anchor_line(lines, anchor)
        if idx is None:
            return content + f"\n[GC warning: anchor {anchor!r} not found, kept full result]"
        kept = lines[idx:]
        trimmed = len(lines) - len(kept)
        return f"[{trimmed} lines trimmed, kept after {anchor!r}]\n" + "\n".join(kept)

    if "keep_before" in snippet:
        anchor = snippet["keep_before"]
        idx = _find_anchor_line(lines, anchor)
        if idx is None:
            return content + f"\n[GC warning: anchor {anchor!r} not found, kept full result]"
        kept = lines[:idx]
        trimmed = len(lines) - len(kept)
        return "\n".join(kept) + f"\n[{trimmed} lines trimmed at {anchor!r}]"

    if "keep_between" in snippet:
        anchors = snippet["keep_between"]
        if len(anchors) != 2:
            return content + "\n[GC warning: keep_between needs exactly 2 anchors]"
        start_anchor, end_anchor = anchors
        start_idx = _find_anchor_line(lines, start_anchor)
        if start_idx is None:
            return content + f"\n[GC warning: start anchor {start_anchor!r} not found]"
        end_idx = _find_anchor_line(lines, end_anchor, start_from=start_idx)
        if end_idx is None:
            return content + f"\n[GC warning: end anchor {end_anchor!r} not found]"
        kept = lines[start_idx:end_idx + 1]
        before = start_idx
        after = len(lines) - end_idx - 1
        header = f"[{before} lines trimmed before {start_anchor!r}]"
        footer = f"[{after} lines trimmed after {end_anchor!r}]"
        return header + "\n" + "\n".join(kept) + "\n" + footer

    return content


def _find_anchor_line(lines: list, text: str, start_from: int = 0) -> int | None:
    for i in range(start_from, len(lines)):
        if text in lines[i]:
            return i
    return None


def inject_notes(messages: list, notes: dict) -> list:
    if not notes:
        return messages
    parts = []
    for name, content in notes.items():
        parts.append(f"## {name}\n{content}")
    notes_block = "[Your working memory notes]\n" + "\n\n".join(parts) + "\n[/Notes]"
    result = list(messages)
    for i in range(len(result) - 1, -1, -1):
        if result[i].get("role") == "user":
            result[i] = dict(result[i])
            result[i]["content"] = notes_block + "\n\n" + result[i]["content"]
            break
    return result


def build_verbatim_audit_note(messages: list) -> str:
    from compaction import estimate_tokens
    lines = []
    for message in messages:
        if message.get("role") != "tool":
            continue
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        if "<tool_use_elided" in content or "trashed by model" in content:
            continue
        tool_call_id = message.get("tool_call_id", "?")
        tool_name = message.get("name", "?")
        size = estimate_tokens([{"content": content}])
        lines.append(f"- {tool_call_id} ({tool_name}): {size} tk")
    if not lines:
        return ""
    return (
        "[Verbatim tool_results still in your context -- trash any you've already consumed]\n"
        + "\n".join(lines)
        + "\n[/Verbatim audit]"
    )


def prepend_verbatim_audit(messages: list) -> list:
    note = build_verbatim_audit_note(messages)
    if not note:
        return messages
    result = list(messages)
    for i in range(len(result) - 1, -1, -1):
        if result[i].get("role") == "user":
            result[i] = dict(result[i])
            result[i]["content"] = note + "\n\n" + result[i]["content"]
            break
    return result
