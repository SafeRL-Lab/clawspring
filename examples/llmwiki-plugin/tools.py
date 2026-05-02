"""llmwiki plugin tools — wraps the `wiki` CLI for AI tool use."""
from __future__ import annotations

import os
import subprocess
from tool_registry import ToolDef


def _run(args: list[str], stdin: str | None = None) -> tuple[int, str]:
    """Run the wiki CLI and return (returncode, stdout+stderr)."""
    try:
        import shutil
        wiki_bin = shutil.which("wiki") or "wiki"
        result = subprocess.run(
            [wiki_bin, *args],
            input=stdin,
            capture_output=True,
            text=True,
            env={**os.environ},
        )
        output = result.stdout
        if result.returncode != 0 and result.stderr:
            output = result.stderr.strip()
        return result.returncode, output
    except FileNotFoundError:
        return 1, (
            "The `wiki` command was not found. Install llmwiki-py with:\n"
            "  pip install \"git+https://github.com/yamaceay/llmwiki-py.git#egg=llmwiki\""
        )


def _wiki_read(params: dict, config: dict) -> str:
    _, out = _run(["read", params["path"]])
    return out or "(empty page)"


def _wiki_write(params: dict, config: dict) -> str:
    _, out = _run(["write", params["path"]], stdin=params["content"])
    return out


def _wiki_append(params: dict, config: dict) -> str:
    _, out = _run(["append", params["path"]], stdin=params["content"])
    return out


def _wiki_search(params: dict, config: dict) -> str:
    args = ["search", params["query"]]
    if "limit" in params:
        args += ["--limit", str(params["limit"])]
    _, out = _run(args)
    return out or "No results."


def _wiki_list(params: dict, config: dict) -> str:
    args = ["list", "--tree"]
    if params.get("dir"):
        args.append(params["dir"])
    _, out = _run(args)
    return out or "(wiki is empty)"


def _wiki_status(params: dict, config: dict) -> str:
    _, out = _run(["status"])
    return out


TOOL_DEFS = [
    ToolDef(
        name="WikiRead",
        schema={
            "name": "WikiRead",
            "description": "Read a page from the wiki knowledge base.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Wiki page path, e.g. 'concepts/auth.md'",
                    }
                },
                "required": ["path"],
            },
        },
        func=_wiki_read,
        read_only=True,
        concurrent_safe=True,
    ),
    ToolDef(
        name="WikiWrite",
        schema={
            "name": "WikiWrite",
            "description": "Write (create or overwrite) a wiki page with new content.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Wiki page path, e.g. 'concepts/auth.md'",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full Markdown content to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
        func=_wiki_write,
        read_only=False,
        concurrent_safe=False,
    ),
    ToolDef(
        name="WikiAppend",
        schema={
            "name": "WikiAppend",
            "description": "Append content to an existing wiki page without overwriting it.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Wiki page path",
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown content to append",
                    },
                },
                "required": ["path", "content"],
            },
        },
        func=_wiki_append,
        read_only=False,
        concurrent_safe=False,
    ),
    ToolDef(
        name="WikiSearch",
        schema={
            "name": "WikiSearch",
            "description": "Full-text search across all wiki pages. Returns matching pages with snippets.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
        func=_wiki_search,
        read_only=True,
        concurrent_safe=True,
    ),
    ToolDef(
        name="WikiList",
        schema={
            "name": "WikiList",
            "description": "List all wiki pages as a directory tree.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "dir": {
                        "type": "string",
                        "description": "Subdirectory to list (optional, defaults to root)",
                    }
                },
            },
        },
        func=_wiki_list,
        read_only=True,
        concurrent_safe=True,
    ),
    ToolDef(
        name="WikiStatus",
        schema={
            "name": "WikiStatus",
            "description": "Show wiki health: page count, index status, git backend status.",
            "input_schema": {
                "type": "object",
                "properties": {},
            },
        },
        func=_wiki_status,
        read_only=True,
        concurrent_safe=True,
    ),
]
