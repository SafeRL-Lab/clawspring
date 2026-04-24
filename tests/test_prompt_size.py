"""Enforce the 150-line soft cap on base prompt files.

Rationale (from the Gemini 3 prompting guide):

    "Once a system instruction becomes a 300-line constitution, you can
    no longer tell what's working and what's superstition."

CheetahClaws sets a stricter cap at 150 lines to keep base prompts
auditable and per-run token cost predictable.  If you genuinely need
more, extract into ``prompts/fragments/*.md`` and append conditionally
from ``context.build_system_prompt``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_BASE_DIR = Path(__file__).parent.parent / "prompts" / "base"

# Keep this in sync with prompts/README.md.  Bump deliberately, not by accident.
MAX_BASE_PROMPT_LINES = 150


def _base_files() -> list[Path]:
    return sorted(_BASE_DIR.glob("*.md"))


def test_base_prompt_directory_exists():
    assert _BASE_DIR.is_dir(), f"missing directory: {_BASE_DIR}"
    assert _base_files(), "expected at least one base prompt file"


@pytest.mark.parametrize("path", _base_files(), ids=lambda p: p.name)
def test_base_prompt_under_line_cap(path: Path):
    line_count = len(path.read_text(encoding="utf-8").splitlines())
    assert line_count <= MAX_BASE_PROMPT_LINES, (
        f"{path.name} has {line_count} lines, cap is {MAX_BASE_PROMPT_LINES}. "
        f"Extract long-lived content into prompts/fragments/*.md and append "
        f"conditionally from context.build_system_prompt."
    )
