"""Tests for multi_agent package split (PR5).

Verifies that the 3-module split (definitions, manager, task) works correctly
and the backward-compat shim re-exports everything.
"""

import textwrap
from pathlib import Path

import pytest

from multi_agent.definitions import (
    AgentDefinition,
    _parse_agent_md,
    get_agent_definition,
    load_agent_definitions,
)
from multi_agent.manager import SubAgentManager
from multi_agent.task import SubAgentTask, TaskStatus, _extract_final_text


# --- definitions.py tests ---


def test_builtin_agents_loaded():
    agents = load_agent_definitions(config_dir=Path("nonexistent_dir"))
    assert "general-purpose" in agents
    assert "coder" in agents
    assert "reviewer" in agents
    assert "researcher" in agents
    assert "tester" in agents


def test_get_agent_definition_valid():
    defn = get_agent_definition("coder", config_dir=Path("nonexistent_dir"))
    assert defn.name == "coder"
    assert isinstance(defn.tools, list)
    assert "Read" in defn.tools


def test_get_agent_definition_invalid():
    with pytest.raises(ValueError, match="Unknown agent type"):
        get_agent_definition("nonexistent_type", config_dir=Path("nonexistent_dir"))


def test_parse_agent_md(tmp_path):
    md = tmp_path / "custom.md"
    md.write_text(textwrap.dedent("""\
        ---
        tools: Read, Write, Bash
        model: gpt-4
        description: A custom agent
        ---
        You are a custom agent for testing.
    """), encoding="utf-8")
    defn = _parse_agent_md(md)
    assert defn.name == "custom"
    assert defn.tools == ["Read", "Write", "Bash"]
    assert defn.model == "gpt-4"
    assert defn.description == "A custom agent"
    assert "custom agent for testing" in defn.system_prompt


def test_parse_agent_md_no_frontmatter(tmp_path):
    md = tmp_path / "simple.md"
    md.write_text("Just a system prompt.", encoding="utf-8")
    defn = _parse_agent_md(md)
    assert defn.name == "simple"
    assert defn.system_prompt == "Just a system prompt."
    assert defn.tools == []


def test_custom_agents_loaded_from_dir(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "mybot.md").write_text("---\ndescription: My bot\n---\nHello!", encoding="utf-8")
    agents = load_agent_definitions(config_dir=tmp_path)
    assert "mybot" in agents
    assert agents["mybot"].description == "My bot"
    assert "general-purpose" in agents  # builtins still there


# --- task.py tests ---


def test_extract_final_text_simple():
    text = "line1\nline2\nline3\n"
    result = _extract_final_text(text)
    assert "line3" in result


def test_extract_final_text_with_blanks():
    text = "intro\n\nresult line 1\nresult line 2\n"
    result = _extract_final_text(text)
    assert "result line 1" in result
    assert "result line 2" in result


def test_extract_final_text_empty():
    assert _extract_final_text("") == ""


def test_task_status_enum():
    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.RUNNING.value == "running"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.FAILED.value == "failed"


def test_task_creation():
    task = SubAgentTask(prompt="Do something", agent_type="coder", name="test-agent")
    assert len(task.id) == 12
    assert task.prompt == "Do something"
    assert task.agent_type == "coder"
    assert task.name == "test-agent"
    assert task.status == TaskStatus.PENDING


def test_task_messaging():
    task = SubAgentTask(prompt="test")
    task.send_message("hello")
    task.send_message("world")
    msgs = task.get_pending_messages()
    assert msgs == ["hello", "world"]
    assert task.get_pending_messages() == []  # cleared


def test_task_to_dict():
    task = SubAgentTask(prompt="Do X", agent_type="coder", name="bob")
    d = task.to_dict()
    assert d["name"] == "bob"
    assert d["agent_type"] == "coder"
    assert d["status"] == "pending"


# --- manager.py tests ---


def test_manager_creation():
    mgr = SubAgentManager(config_dir=Path("nonexistent"))
    assert mgr._tasks == {}


def test_manager_list_agent_types():
    mgr = SubAgentManager(config_dir=Path("nonexistent"))
    types = mgr.list_agent_types()
    names = [t["name"] for t in types]
    assert "general-purpose" in names
    assert "coder" in names


# --- backward compat shim ---


def test_backward_compat_imports():
    """The subagent.py shim re-exports all public names."""
    import subagent
    assert hasattr(subagent, "AgentDefinition")
    assert hasattr(subagent, "SubAgentTask")
    assert hasattr(subagent, "SubAgentManager")
    assert hasattr(subagent, "load_agent_definitions")
    assert hasattr(subagent, "get_agent_definition")
    assert hasattr(subagent, "_extract_final_text")
    assert hasattr(subagent, "_agent_run")
