"""Tests for :mod:`prompts.select` — model-family routing + fragment loading."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from prompts import pick_base_prompt, load_fragment
from prompts import select as _select


# ── Core claim: route by model family, not by provider/runtime ───────────
#
# Same Qwen model served through DashScope, Ollama, vLLM, or OpenRouter
# must produce the same base prompt.  Same for every other family.

_FAMILY_CASES = [
    # (model_id, expected_filename, comment)
    # --- Anthropic family ---
    ("claude-opus-4-7",                          "anthropic.md", "native Anthropic"),
    ("claude-sonnet-4-5",                        "anthropic.md", "native Anthropic"),
    ("custom/anthropic/claude-sonnet-4-5",       "anthropic.md", "Claude via OpenRouter"),
    # --- OpenAI family ---
    ("gpt-5",                                    "openai.md",    "native OpenAI"),
    ("gpt-4o",                                   "openai.md",    "native OpenAI"),
    ("o3-mini",                                  "openai.md",    "o-series reasoning"),
    ("o1",                                       "openai.md",    "o1 reasoning"),
    ("custom/openai/gpt-5",                      "openai.md",    "GPT via OpenRouter"),
    ("gpt-5-codex",                              "openai.md",    "codex variant"),
    # --- Gemini family ---
    ("gemini/gemini-2.5-pro",                    "gemini.md",    "native Gemini"),
    ("gemini-3.1-pro-preview",                   "gemini.md",    "Gemini 3"),
    ("custom/google/gemini-2.5-pro",             "gemini.md",    "Gemini via OpenRouter"),
    # --- Kimi / Moonshot family ---
    ("kimi/moonshot-v1-128k",                    "kimi.md",      "Kimi native"),
    ("moonshot-v1-32k",                          "kimi.md",      "Moonshot keyword"),
    ("custom/moonshotai/kimi-k2",                "kimi.md",      "Kimi via OpenRouter"),
    # --- DeepSeek family ---
    ("deepseek/deepseek-chat",                   "deepseek.md",  "DeepSeek native"),
    ("ollama/deepseek-r1:32b",                   "deepseek.md",  "DeepSeek via Ollama"),
    ("custom/deepseek/deepseek-chat-v3.2",       "deepseek.md",  "DeepSeek via OpenRouter"),
    # --- Unrecognized families fall through to default.md ---
    ("ollama/qwen2.5-coder:32b",                 "default.md",   "Qwen has no file yet"),
    ("qwen/Qwen3-MAX",                           "default.md",   "Qwen native → default"),
    ("ollama/llama3.3",                          "default.md",   "Llama → default"),
    ("ollama/gemma4:e4b",                        "default.md",   "Gemma → default"),
    ("custom/my-private-finetune",               "default.md",   "unknown model"),
    ("",                                         "default.md",   "empty model id"),
]


@pytest.mark.parametrize("model_id,expected,comment", _FAMILY_CASES,
                          ids=[c[2] for c in _FAMILY_CASES])
def test_model_family_routing(model_id: str, expected: str, comment: str):
    """Each model ID resolves to the expected family file regardless of runtime."""
    text = pick_base_prompt(model_id=model_id)
    expected_text = (_select._BASE_DIR / expected).read_text(encoding="utf-8")
    assert text == expected_text, (
        f"[{comment}] model_id={model_id!r} expected to route to {expected} "
        f"but picked a different file"
    )


def test_runtime_is_irrelevant_for_family_routing():
    """Qwen served three different ways → same prompt (currently default, as no qwen.md yet)."""
    via_ollama     = pick_base_prompt(model_id="ollama/qwen2.5-coder")
    via_dashscope  = pick_base_prompt(model_id="qwen/Qwen3-MAX")
    via_openrouter = pick_base_prompt(model_id="custom/qwen/Qwen3-MAX")
    assert via_ollama == via_dashscope == via_openrouter


def test_claude_routing_is_runtime_agnostic():
    native     = pick_base_prompt(model_id="claude-opus-4-7")
    openrouter = pick_base_prompt(model_id="custom/anthropic/claude-opus-4-7")
    assert native == openrouter


# ── Provider fallback (only consulted when model_id is empty) ────────────


def test_provider_fallback_when_model_id_empty():
    """With no model_id, the provider kwarg picks the family file."""
    assert pick_base_prompt(provider="anthropic") == \
           (_select._BASE_DIR / "anthropic.md").read_text(encoding="utf-8")
    assert pick_base_prompt(provider="openai") == \
           (_select._BASE_DIR / "openai.md").read_text(encoding="utf-8")
    assert pick_base_prompt(provider="gemini") == \
           (_select._BASE_DIR / "gemini.md").read_text(encoding="utf-8")


def test_local_providers_do_not_fall_back_to_a_runtime_file():
    """ollama / lmstudio / custom without a model_id must hit default, not a runtime-specific prompt.

    This encodes the invariant that prompts never depend on how a model is served.
    """
    assert pick_base_prompt(provider="ollama") == \
           (_select._BASE_DIR / "default.md").read_text(encoding="utf-8")
    assert pick_base_prompt(provider="lmstudio") == \
           (_select._BASE_DIR / "default.md").read_text(encoding="utf-8")
    assert pick_base_prompt(provider="custom") == \
           (_select._BASE_DIR / "default.md").read_text(encoding="utf-8")


def test_model_id_takes_precedence_over_provider():
    """If model_id carries a family keyword, provider fallback is ignored."""
    # Caller passes provider="custom" (OpenRouter) but the model is Claude.
    assert pick_base_prompt(provider="custom",
                             model_id="custom/anthropic/claude-sonnet-4-5") == \
           (_select._BASE_DIR / "anthropic.md").read_text(encoding="utf-8")


def test_unknown_provider_with_no_model_falls_back_to_default():
    assert pick_base_prompt(provider="some-unknown-provider") == \
           (_select._BASE_DIR / "default.md").read_text(encoding="utf-8")


def test_pick_base_prompt_no_args_returns_default():
    assert pick_base_prompt() == \
           (_select._BASE_DIR / "default.md").read_text(encoding="utf-8")


# ── Fragment loading ──────────────────────────────────────────────────────


def test_load_fragment_tmux():
    text = load_fragment("tmux")
    assert "tmux" in text.lower()
    assert "TmuxNewSession" in text


def test_load_fragment_plan_keeps_placeholder():
    """plan.md must keep the {plan_file} placeholder unformatted."""
    text = load_fragment("plan")
    assert "{plan_file}" in text, "plan fragment must carry its placeholder for caller to format"
    assert "Plan Mode" in text


def test_load_fragment_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_fragment("no-such-fragment-does-not-exist")


# ── Cache behavior ────────────────────────────────────────────────────────


def test_repeated_calls_hit_cache(monkeypatch):
    """Second call to pick_base_prompt must NOT re-read the file."""
    _select.clear_cache()

    call_count = {"n": 0}
    original_read_text = _select.Path.read_text

    def counting_read_text(self, *a, **kw):
        call_count["n"] += 1
        return original_read_text(self, *a, **kw)

    monkeypatch.setattr(_select.Path, "read_text", counting_read_text)

    pick_base_prompt(model_id="claude-opus-4-7")
    first = call_count["n"]
    pick_base_prompt(model_id="claude-opus-4-7")
    pick_base_prompt(model_id="claude-opus-4-7")
    assert call_count["n"] == first, "lru_cache should prevent further reads"


# ── Regression: the ollama.md file must NOT exist ────────────────────────


def test_ollama_md_is_not_shipped():
    """Guarding against re-introduction of a runtime-level prompt file.

    Runtime ('ollama', 'lmstudio', 'custom') is never a valid prompt
    dimension — see prompts/README.md and select.py docstring.
    """
    assert not (_select._BASE_DIR / "ollama.md").exists(), (
        "prompts/base/ollama.md should not exist — a model's prompt "
        "must depend on the family (qwen / llama / deepseek / …), not "
        "on how it's being served."
    )
