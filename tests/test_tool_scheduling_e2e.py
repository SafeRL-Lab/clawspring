"""End-to-end: the LLM sees `tool_call_alias` + `depends_on` in every tool
schema, it uses them in a tool call, and the stripping wrapper removes those
fields before the tool handler runs.

Only the LLM provider is mocked (via monkeypatching agent.stream). The tool
registry, schema injection and param stripping all run for real.
"""
from __future__ import annotations

import pytest

import tools as _tools_init  # noqa: F401 - force built-in tool registration
from agent import AgentState, run
from providers import AssistantTurn
from tool_registry import ToolDef, register_tool


@pytest.fixture(autouse=True)
def _no_quota(monkeypatch):
    """Disable quota tracking — these tests exercise scheduling, not billing."""
    monkeypatch.setattr("quota.record_usage", lambda *a, **kw: None)


def _scripted_stream(captured_schemas, turns):
    cursor = iter(turns)

    def fake_stream(**kwargs):
        captured_schemas.append(kwargs.get("tool_schemas") or [])
        spec = next(cursor)
        yield AssistantTurn(
            text=spec.get("text", ""),
            tool_calls=spec.get("tool_calls") or [],
            in_tokens=1, out_tokens=1,
        )

    return fake_stream


@pytest.fixture
def receiver_tool():
    """Register a tool that captures whatever params it receives."""
    received = {}
    from tool_registry import _registry
    had_before = "receiver" in _registry
    register_tool(ToolDef(
        name="receiver",
        schema={
            "name": "receiver",
            "description": "records params for assertions",
            "input_schema": {
                "type": "object",
                "properties": {"msg": {"type": "string"}},
                "required": ["msg"],
            },
        },
        func=lambda params, _cfg: received.setdefault("seen", dict(params)) and "ok",
        read_only=True, concurrent_safe=True,
    ))
    yield received
    if not had_before:
        _registry.pop("receiver", None)


def test_schemas_sent_to_llm_include_scheduling_props(monkeypatch, receiver_tool):
    """Every schema the LLM sees must carry tool_call_alias + depends_on."""
    captured = []
    monkeypatch.setattr(
        "agent.stream",
        _scripted_stream(captured, [{"text": "nothing to do"}]),
    )

    list(run("hi", AgentState(), {"model": "test", "permission_mode": "accept-all",
                                    "_session_id": "sch", "disabled_tools": ["Agent"]},
              "sys"))

    assert captured, "stream was not called"
    for schema in captured[0]:
        props = schema.get("properties") or schema.get("input_schema", {}).get("properties", {})
        assert "tool_call_alias" in props, f"{schema.get('name')} missing tool_call_alias"
        assert "depends_on" in props, f"{schema.get('name')} missing depends_on"


def test_scheduling_params_stripped_before_reaching_tool(monkeypatch, receiver_tool):
    """tool_call_alias + depends_on must be gone by the time the handler runs."""
    captured_schemas = []
    turns = [
        {"tool_calls": [{
            "id": "r1",
            "name": "receiver",
            "input": {
                "msg": "hello",
                "tool_call_alias": "step-1",
                "depends_on": ["w1", "w2"],
            },
        }]},
        {"text": "done"},
    ]
    monkeypatch.setattr("agent.stream", _scripted_stream(captured_schemas, turns))

    list(run("go", AgentState(), {"model": "test", "permission_mode": "accept-all",
                                   "_session_id": "sch2", "disabled_tools": ["Agent"]},
              "sys"))

    assert "seen" in receiver_tool, "receiver handler was never called"
    seen = receiver_tool["seen"]
    assert seen.get("msg") == "hello"
    assert "tool_call_alias" not in seen
    assert "depends_on" not in seen


def test_id_reuse_across_turns_gets_remapped(monkeypatch, receiver_tool):
    """When LLM reuses an id from a prior turn, uniquify rewrites it."""
    captured_schemas = []
    turns = [
        # Turn 1: tool call with id "r1"
        {"tool_calls": [{
            "id": "r1",
            "name": "receiver",
            "input": {"msg": "turn1"},
        }]},
        # Turn 2: LLM reuses "r1" — uniquify must remap
        {"tool_calls": [{
            "id": "r1",
            "name": "receiver",
            "input": {"msg": "turn2"},
        }]},
        {"text": "done"},
    ]
    monkeypatch.setattr("agent.stream", _scripted_stream(captured_schemas, turns))

    state = AgentState()
    events = list(run("go", state, {"model": "test", "permission_mode": "accept-all",
                                     "_session_id": "sch3", "disabled_tools": ["Agent"]},
                       "sys"))

    # Collect tool_call_ids from assistant turns only
    assistant_ids = []
    for msg in state.messages:
        if msg["role"] == "assistant":
            for tc in msg.get("tool_calls") or []:
                assistant_ids.append(tc["id"])

    # Both tool calls must exist and have UNIQUE ids
    assert len(assistant_ids) == 2, f"Expected 2 tool calls, got {assistant_ids}"
    assert assistant_ids[0] != assistant_ids[1], (
        f"IDs must be unique across turns but got duplicates: {assistant_ids}"
    )

    # Tool results must match their corresponding assistant tool_call ids
    tool_results = [m for m in state.messages if m["role"] == "tool"]
    assert len(tool_results) == 2
    assert tool_results[0]["tool_call_id"] == assistant_ids[0]
    assert tool_results[1]["tool_call_id"] == assistant_ids[1]
