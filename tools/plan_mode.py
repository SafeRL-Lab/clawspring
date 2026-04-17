"""Plan mode tools — EnterPlanMode, WritePlan, ExitPlanMode.

Allows the LLM to enter a read-only planning phase before writing code.
"""
from pathlib import Path

from tool_registry import register_tool, ToolDef
import runtime


def _enter_plan_mode(params: dict, config: dict = None) -> str:
    config = config or {}
    ctx = runtime.get_ctx(config)
    plan_dir = Path.home() / ".cheetahclaws" / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    session_id = config.get("session_id", "default")
    ctx.plan_file = plan_dir / f"{session_id}.md"
    ctx.prev_permission_mode = config.get("permission_mode")
    config["permission_mode"] = "plan"
    task_desc = params.get("task_description", "")
    msg = f"Entered plan mode. Plan file: {ctx.plan_file}"
    if task_desc:
        msg += f"\nTask: {task_desc}"
    msg += "\nOnly the plan file is writable. Use WritePlan to save your plan."
    return msg


def _write_plan(params: dict, config: dict = None) -> str:
    config = config or {}
    ctx = runtime.get_ctx(config)
    if not ctx.plan_file:
        return "Error: not in plan mode. Call EnterPlanMode first."
    content = params.get("content", "")
    if not content.strip():
        return "Error: plan content is empty."
    ctx.plan_file.write_text(content, encoding="utf-8")
    return f"Plan saved to {ctx.plan_file}"


def _exit_plan_mode(params: dict, config: dict = None) -> str:
    config = config or {}
    ctx = runtime.get_ctx(config)
    if not ctx.plan_file:
        return "Error: not in plan mode."
    if not ctx.plan_file.exists():
        return "Error: plan file not found. Write a plan with WritePlan before exiting."
    if ctx.plan_file.stat().st_size == 0:
        return "Error: plan file is empty. Write a plan with WritePlan before exiting."
    config["permission_mode"] = ctx.prev_permission_mode or "normal"
    plan_path = ctx.plan_file
    ctx.plan_file = None
    ctx.prev_permission_mode = None
    return f"Exited plan mode. Plan at: {plan_path}\nAwaiting user approval before implementation."


# --- Schemas ---

_ENTER_SCHEMA = {
    "name": "EnterPlanMode",
    "description": (
        "Enter plan mode to analyze the codebase and create an implementation plan "
        "before writing code. In plan mode, only the plan file is writable."
    ),
    "properties": {
        "task_description": {
            "type": "string",
            "description": "Brief description of the task to plan for",
        },
    },
}

_WRITE_SCHEMA = {
    "name": "WritePlan",
    "description": "Write the implementation plan as a structured Markdown document.",
    "properties": {
        "content": {
            "type": "string",
            "description": "The complete implementation plan in Markdown format.",
        },
    },
    "required": ["content"],
}

_EXIT_SCHEMA = {
    "name": "ExitPlanMode",
    "description": (
        "Exit plan mode and present the plan for user approval. "
        "The user must approve the plan before implementation begins."
    ),
    "properties": {},
}

# --- Self-registration ---

register_tool(ToolDef(name="EnterPlanMode", schema=_ENTER_SCHEMA, func=_enter_plan_mode, read_only=True))
register_tool(ToolDef(name="WritePlan", schema=_WRITE_SCHEMA, func=_write_plan, read_only=False))
register_tool(ToolDef(name="ExitPlanMode", schema=_EXIT_SCHEMA, func=_exit_plan_mode, read_only=True))
