"""Backward-compatibility shim — real implementation is in multi_agent/."""
from multi_agent.definitions import (  # noqa: F401
    AgentDefinition,
    load_agent_definitions,
    get_agent_definition,
    _BUILTIN_AGENTS,
)
from multi_agent.manager import SubAgentManager  # noqa: F401
from multi_agent.task import (  # noqa: F401
    SubAgentTask,
    _extract_final_text,
    _agent_run,
)
