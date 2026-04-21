"""Shared test fixtures for agent-loop e2e tests."""

from __future__ import annotations

import pytest

from agent import AssistantTurn


# --------------- quota stub (avoids ImportError on CI for calc_cost) --------

@pytest.fixture(autouse=True)
def _no_quota(monkeypatch):
    """Disable quota.record_usage so tests never hit the real billing path."""
    import quota
    monkeypatch.setattr(quota, "record_usage", lambda *a, **kw: None)


# --------------- scripted LLM stream helper --------------------------------

def scripted_stream(captured_schemas: list, turns: list[dict]):
    """Return a fake ``stream()`` callable that yields pre-defined turns.

    *captured_schemas* receives the ``tool_schemas`` kwarg from each call,
    letting tests assert on schema injection.  *turns* is a list of dicts,
    each with optional ``text`` and ``tool_calls`` keys.
    """
    cursor = iter(turns)

    def fake_stream(**kwargs):
        captured_schemas.append(kwargs.get("tool_schemas") or [])
        spec = next(cursor)
        yield AssistantTurn(
            text=spec.get("text", ""),
            tool_calls=spec.get("tool_calls") or [],
            in_tokens=1,
            out_tokens=1,
        )

    return fake_stream
