"""Prompt file loading and model-family routing.

Public API:
    pick_base_prompt(provider: str, model_id: str = "") -> str
    load_fragment(name: str) -> str

Both functions are cached (:func:`functools.lru_cache`) so repeated calls
are a dict lookup, not disk I/O.

## Why route by *model family*, not by *provider*

``providers.detect_provider()`` returns the *runtime* / *API gateway* —
``anthropic``, ``openai``, ``ollama``, ``lmstudio``, ``custom`` (OpenRouter,
vLLM, any OpenAI-compatible endpoint).  That dimension is the right one
for **API plumbing** (base URL, auth, request shape) but the wrong one
for **system prompts**.

A model's prompt sensitivity follows the **model family**, not the
runtime: Qwen-3 exhibits the same strengths and quirks whether it's
served by Alibaba DashScope, Ollama on a laptop, vLLM on a GPU cluster,
or OpenRouter.  If we picked prompts by provider, ``ollama/qwen2.5-coder``
and ``qwen/Qwen3-MAX`` would get different instructions for the same
underlying model, which is both wrong and unmaintainable.

So: **routing is primarily a substring match on ``model_id``**; the
``provider`` argument is used only as a fallback when the model ID is
empty or carries no family keyword.

## Routing rules

Checked in order against the last path segment of ``model_id`` (after
stripping any ``provider/`` or ``provider/vendor/`` prefix):

    claude                                   → anthropic.md
    gpt / o1 / o3 / o4                       → openai.md
    gemini                                   → gemini.md
    qwen / qwq                               → qwen.md    (future)
    kimi / moonshot                          → kimi.md
    deepseek                                 → deepseek.md
    <nothing matches>                        → default.md

Fallback when ``model_id`` is empty: the ``provider`` kwarg maps to the
same family file (``anthropic`` → ``anthropic.md`` etc.) or default.

## What the current set of files ships

Six base files live in ``prompts/base/``:

    default.md     — stable baseline (used as fallback)
    anthropic.md   — Claude family: XML-tag structuring, "keep solutions
                      minimal" guard against known 4.x over-engineering,
                      parallel tool-call encouragement
    openai.md      — GPT family: CTCO framework, explicit stop
                      conditions, tool-use-with-examples
    gemini.md      — Gemini family: explicit agentic-mode loop
                      (explore → verify → act → report), batch-tool-calls
                      emphasis, less-verbose output style
    kimi.md        — currently identical to default.md
    deepseek.md    — currently identical to default.md

``qwen.md``, ``llama.md``, etc. are not created yet — any Qwen / Llama /
Mistral / Gemma / Phi model routes to ``default.md`` for now.  Family
files will be added as concrete quirks emerge from real-model testing.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_BASE_DIR = _PROMPTS_DIR / "base"
_FRAGMENTS_DIR = _PROMPTS_DIR / "fragments"


# ── Model-family detection ────────────────────────────────────────────────
#
# Ordered list of (substring-keywords, filename).  First hit wins.
# All matching is done case-insensitively on the *last segment* of the
# model ID (so "custom/anthropic/claude-sonnet-4-5" becomes
# "claude-sonnet-4-5" and still matches "claude").
#
# Extend this list — not the old _PROVIDER_MAP — when adding a new
# family file.  Keep more-specific keywords earlier (e.g. "moonshot"
# before a hypothetical "moon").
_FAMILY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("claude",),                          "anthropic.md"),
    (("gemini",),                          "gemini.md"),
    (("gpt-", "o1", "o3", "o4", "codex"),  "openai.md"),
    (("kimi", "moonshot"),                 "kimi.md"),
    (("deepseek",),                        "deepseek.md"),
    # Families that don't have a dedicated file yet all fall through to
    # default.md — listed here as a record of "known family, no file yet":
    # (("qwen", "qwq"),      "qwen.md"),       # add when qwen.md exists
    # (("llama",),           "llama.md"),
    # (("mistral", "mixtral"), "mistral.md"),
    # (("gemma",),           "gemma.md"),
    # (("phi-", "phi4"),     "phi.md"),
    # (("glm", "zhipu"),     "glm.md"),
    # (("minimax", "abab"),  "minimax.md"),
)

# Provider → filename fallback.  Only consulted when model_id is empty or
# has no family keyword.  Local-runtime providers (ollama / lmstudio /
# custom) deliberately do NOT map to a runtime-specific file — if we can't
# identify the family, default.md is the honest answer.
_PROVIDER_FALLBACK: dict[str, str] = {
    "anthropic": "anthropic.md",
    "openai":    "openai.md",
    "gemini":    "gemini.md",
    "kimi":      "kimi.md",
    "deepseek":  "deepseek.md",
    # qwen / zhipu / minimax providers intentionally omitted — they
    # don't yet have a dedicated file; default.md is the current answer.
}


def _family_file_for_model(model_id: str) -> str | None:
    """Return the family-specific filename for a model ID, or None."""
    if not model_id:
        return None
    tail = model_id.rsplit("/", 1)[-1].lower()
    for keywords, fname in _FAMILY_RULES:
        if any(k in tail for k in keywords):
            return fname
    return None


@lru_cache(maxsize=None)
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def pick_base_prompt(provider: str = "", model_id: str = "") -> str:
    """Return the base system prompt for the given model.

    Args:
        provider: provider name from ``providers.detect_provider()``.
                  Used only as a fallback when ``model_id`` carries no
                  family keyword.
        model_id: the full model identifier (may include a ``provider/``
                  or ``provider/vendor/`` prefix, e.g.
                  ``"ollama/qwen2.5-coder"`` or
                  ``"custom/anthropic/claude-sonnet-4-5"``).  Matched
                  against ``_FAMILY_RULES`` case-insensitively on its
                  last path segment.

    Returns:
        The raw Markdown body of the selected prompt file.  Never raises
        for unknown models — falls back to ``default.md``.
    """
    fname = (
        _family_file_for_model(model_id)
        or _PROVIDER_FALLBACK.get(provider)
        or "default.md"
    )
    path = _BASE_DIR / fname
    if not path.exists():
        # Defensive: a rule referenced a not-yet-created file.  The
        # family-file-for-model docstring guarantees these are commented
        # out until the file is added, but handle it anyway.
        path = _BASE_DIR / "default.md"
    return _read(path)


def load_fragment(name: str) -> str:
    """Return the raw Markdown body of a conditional fragment.

    Fragments are short reusable blocks appended to the system prompt
    under runtime conditions (e.g. tmux present, plan mode active).

    Args:
        name: stem of a file in ``prompts/fragments/`` (e.g. ``"tmux"``,
              ``"plan"``).

    Returns:
        The file contents.

    Raises:
        FileNotFoundError: if the fragment does not exist — this is a
            programming error, not a runtime condition, so it should be
            loud.
    """
    path = _FRAGMENTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt fragment not found: {path}")
    return _read(path)


def clear_cache() -> None:
    """Reset the prompt file cache.  Intended for tests only."""
    _read.cache_clear()
