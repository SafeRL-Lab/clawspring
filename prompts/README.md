# `prompts/` — system prompt assets

This directory holds the raw Markdown used to build every system prompt
CheetahClaws sends to an LLM.  The code in
[`prompts/select.py`](select.py) loads and routes these files; the
assembly logic (dynamic blocks, environment info, memory injection)
lives in [`context.py`](../context.py).

## Layout

```
prompts/
├── __init__.py
├── select.py              # pick_base_prompt + load_fragment (lru_cache'd)
├── README.md              # this file
├── base/
│   ├── default.md         # fallback — used for any model not matched by family
│   ├── anthropic.md       # Claude family
│   ├── openai.md          # GPT / o1 / o3 / o4 / codex
│   ├── gemini.md          # Gemini family
│   ├── kimi.md            # Moonshot Kimi
│   └── deepseek.md        # DeepSeek chat + reasoner (see note below)
└── fragments/
    ├── tmux.md            # appended when tmux is available
    └── plan.md            # appended when permission_mode == "plan"
```

## Routing — by model family, not by provider

`pick_base_prompt(provider, model_id)` returns the base prompt for the
**model family**, not the runtime or API gateway.  Qwen-3 served by
Alibaba DashScope, Ollama on your laptop, vLLM on a GPU cluster, or
OpenRouter is the same model — it gets the same prompt regardless of
how it's being served.

Concretely: matching is a case-insensitive substring check against the
**last path segment** of `model_id` (so `custom/anthropic/claude-sonnet-4-5`
strips to `claude-sonnet-4-5` and matches `claude`).  See `_FAMILY_RULES`
in [`select.py`](select.py) for the authoritative order.

The `provider` argument is consulted **only as a fallback** when
`model_id` is empty or carries no family keyword (e.g. unusual custom
deployments).  We deliberately do **not** ship a `ollama.md` or similar
runtime-level prompt — if the model family can't be identified, the
honest fallback is `default.md`, not "pretend it's a small local
model".

### Current state

- `default.md` is the stable baseline.  Changing it invalidates the
  regression golden fixture — do so deliberately.
- `anthropic.md`, `openai.md`, `gemini.md` carry **family-specific**
  content sourced from each provider's public prompt-engineering
  guidance (Anthropic XML-tag structuring + "keep solutions minimal";
  OpenAI CTCO framework + explicit stop conditions; Gemini explicit
  agentic-mode loop + parallel-batching emphasis).
- `deepseek.md` and `kimi.md` currently duplicate `default.md`
  byte-for-byte; they will differentiate when concrete quirks emerge
  from real-model testing.

Families that don't yet have a dedicated file (Qwen, Llama, Mistral,
Gemma, Phi, GLM, MiniMax) route to `default.md`.  When a concrete
difference emerges, add `base/<family>.md` and enable the
commented-out entry in `_FAMILY_RULES`.

### 150-line soft cap

Keep base prompts **under ~150 lines**.  Rationale (from the [Gemini 3
prompting guide](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/gemini-3-prompting-guide)):

> "Once a system instruction becomes a 300-line constitution, you can
> no longer tell what's working and what's superstition."

If a prompt is getting long, extract the long-lived parts into a
`fragments/*.md` file and append it conditionally from
`build_system_prompt()`.

## Fragments

`load_fragment(name)` reads `fragments/<name>.md`.  Fragments may
contain `{placeholder}` tokens that the caller formats at render time
(e.g. `plan.md` carries `{plan_file}`, filled in by
`context._render_plan_fragment`).  Literal `{` / `}` in a fragment must
be doubled (`{{` / `}}`).

Base prompts **must not** use placeholders — they are loaded verbatim.
Per-run environment data (`date`, `cwd`, git info, CLAUDE.md) is
rendered separately by `context._render_env_block` and appended to the
base prompt.

## Adding a new model family

1. Add `base/<family>.md` (copy `default.md` as a starting point,
   then differentiate).
2. Add a new rule tuple to `_FAMILY_RULES` in [`select.py`](select.py).
   Put more-specific keywords before broader ones in the same tuple.
3. Add a case to `tests/test_prompt_selection.py::test_model_family_routing`
   with a representative model ID.

## Adding a new fragment

1. Add `fragments/<name>.md`.
2. Append it conditionally in `context.build_system_prompt`.
3. Add a case to `tests/test_prompt_assembly.py`.

## What NOT to do

- **Don't read prompt files directly** from application code.  Go
  through `pick_base_prompt` / `load_fragment` so the cache stays
  coherent.
- **Don't put runtime state** (current cwd, git branch, CLAUDE.md) into
  a base prompt.  Those live in `context._render_env_block` and are
  assembled fresh every turn.
- **Don't route by provider / runtime.**  A runtime ("ollama",
  "lmstudio", "custom", "vllm") is *how* a model is served; a family
  ("claude", "qwen", "deepseek") is *what* the model is.  Prompts
  follow the latter.
- **Don't introduce a template engine** (jinja2, mustache, ...).  The
  design is deliberately "plain Markdown + maybe `.format()` on one
  explicit placeholder" — anything richer belongs in a separate RFC.

## Known gaps

- **DeepSeek-R1** recommends *no* system prompt (all instructions in
  the user role).  Supporting that requires a bypass mechanism in
  `providers.py`; tracked separately.  `deepseek.md` is V3-oriented for
  now.
- **OpenAI reasoning models** (o1/o3/gpt-5-codex) may benefit from a
  separate `openai-reasoning.md`, analogous to opencode's `beast.txt`.
  Not yet split; will be tackled when the first concrete need appears.
- **Many open-source families have no dedicated file yet** (Qwen,
  Llama, Mistral, Gemma, Phi, GLM, MiniMax).  They fall through to
  `default.md`.  The first family file to add once concrete quirks
  are observed will likely be `qwen.md`.
