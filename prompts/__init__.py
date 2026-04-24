"""System prompt assets + selection.

Base prompts live in ``prompts/base/<provider>.md``.  Fragments that are
conditionally appended (tmux, plan mode) live in ``prompts/fragments/``.
See ``prompts/README.md`` for contributor guidance (including the 150-line
per-file cap rationale).

Selection logic is in :mod:`prompts.select`.  Callers should not read .md
files directly — always go through ``pick_base_prompt`` / ``load_fragment``.
"""
from prompts.select import pick_base_prompt, load_fragment  # noqa: F401

__all__ = ["pick_base_prompt", "load_fragment"]
