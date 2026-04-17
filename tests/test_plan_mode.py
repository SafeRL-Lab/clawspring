"""Tests for plan mode tools."""
from pathlib import Path

import runtime


def _make_config(tmp_path):
    return {"session_id": "test_session", "permission_mode": "normal"}


class TestEnterPlanMode:
    def test_sets_plan_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from tools.plan_mode import _enter_plan_mode

        config = _make_config(tmp_path)
        result = _enter_plan_mode({}, config)
        ctx = runtime.get_ctx(config)
        assert ctx.plan_file is not None
        assert "test_session.md" in str(ctx.plan_file)
        assert config["permission_mode"] == "plan"
        assert "Entered plan mode" in result

    def test_with_task_description(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from tools.plan_mode import _enter_plan_mode

        config = _make_config(tmp_path)
        result = _enter_plan_mode({"task_description": "Refactor X"}, config)
        assert "Refactor X" in result


class TestWritePlan:
    def test_writes_content(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from tools.plan_mode import _enter_plan_mode, _write_plan

        config = _make_config(tmp_path)
        _enter_plan_mode({}, config)
        result = _write_plan({"content": "# My Plan\n\nStep 1..."}, config)
        ctx = runtime.get_ctx(config)
        assert "Plan saved" in result
        assert ctx.plan_file.read_text(encoding="utf-8") == "# My Plan\n\nStep 1..."

    def test_rejects_empty_content(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from tools.plan_mode import _enter_plan_mode, _write_plan

        config = _make_config(tmp_path)
        _enter_plan_mode({}, config)
        result = _write_plan({"content": ""}, config)
        assert "Error" in result

    def test_fails_outside_plan_mode(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from tools.plan_mode import _write_plan

        config = _make_config(tmp_path)
        result = _write_plan({"content": "text"}, config)
        assert "Error" in result


class TestExitPlanMode:
    def test_restores_permission(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from tools.plan_mode import _enter_plan_mode, _write_plan, _exit_plan_mode

        config = _make_config(tmp_path)
        _enter_plan_mode({}, config)
        _write_plan({"content": "# Plan content"}, config)
        result = _exit_plan_mode({}, config)
        assert config["permission_mode"] == "normal"
        assert "Exited plan mode" in result

    def test_rejects_empty_plan(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from tools.plan_mode import _enter_plan_mode, _exit_plan_mode

        config = _make_config(tmp_path)
        _enter_plan_mode({}, config)
        ctx = runtime.get_ctx(config)
        ctx.plan_file.parent.mkdir(parents=True, exist_ok=True)
        ctx.plan_file.write_text("", encoding="utf-8")
        result = _exit_plan_mode({}, config)
        assert "Error" in result

    def test_fails_outside_plan_mode(self, tmp_path, monkeypatch):
        from tools.plan_mode import _exit_plan_mode

        config = _make_config(tmp_path)
        result = _exit_plan_mode({}, config)
        assert "Error" in result
