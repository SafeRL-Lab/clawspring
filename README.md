

<div align="center">
  <a href="https://github.com/SafeRL-Lab/nano-claude-code">
    <img src="https://github.com/SafeRL-Lab/nano-claude-code/blob/main/docs/demo.gif" alt="Logo" width="800"> 
  </a>
  
<h1 align="center" style="font-size: 30px;"><strong><em>Nano Claude Code</em></strong>: A Minimal Python Reimplementation (~1300 Lines)</h1>
<p align="center">
    <a href="https://github.com/chauncygu/collection-claude-code-source-code">The newest source of Claude Code</a>
    ·
    <a href="https://github.com/SafeRL-Lab/nano-claude-code/issues">Issue</a>
  </p>
</div>


## 🔥🔥🔥 News (Pacific Time)
- Apr 01, 2026: Support more closed-source models and open-source models.


# Nano Claude Code

![demo](demo.gif)

A minimal Python implementation of Claude Code in ~1300 lines, supporting Claude, GPT, Gemini, Kimi, Qwen, Zhipu, DeepSeek, and local open-source models via Ollama or any OpenAI-compatible endpoint.

---


## Features

| Feature | Details |
|---|---|
| Multi-provider | Anthropic · OpenAI · Gemini · Kimi · Qwen · Zhipu · DeepSeek · Ollama · LM Studio · Custom endpoint |
| Interactive REPL | readline history, Tab-complete slash commands |
| Agent loop | Streaming API + automatic tool-use loop |
| 8 built-in tools | Read · Write · Edit · Bash · Glob · Grep · WebFetch · WebSearch |
| Permission system | `auto` / `accept-all` / `manual` modes |
| 14 slash commands | `/model` · `/config` · `/save` · `/cost` · … |
| Context injection | Auto-loads `CLAUDE.md`, git status, cwd |
| Session persistence | Save / load conversations to `~/.nano_claude/sessions/` |
| Extended Thinking | Toggle on/off (Claude models only) |
| Cost tracking | Token usage + estimated USD cost |
| Non-interactive mode | `--print` flag for scripting / CI |

---

## Supported Models

### Closed-Source (API)

| Provider | Model | Context | Strengths | API Key Env |
|---|---|---|---|---|
| **Anthropic** | `claude-opus-4-6` | 200k | Most capable, best for complex reasoning | `ANTHROPIC_API_KEY` |
| **Anthropic** | `claude-sonnet-4-6` | 200k | Balanced speed & quality | `ANTHROPIC_API_KEY` |
| **Anthropic** | `claude-haiku-4-5-20251001` | 200k | Fast, cost-efficient | `ANTHROPIC_API_KEY` |
| **OpenAI** | `gpt-4o` | 128k | Strong multimodal & coding | `OPENAI_API_KEY` |
| **OpenAI** | `gpt-4o-mini` | 128k | Fast, cheap | `OPENAI_API_KEY` |
| **OpenAI** | `o3-mini` | 200k | Strong reasoning | `OPENAI_API_KEY` |
| **OpenAI** | `o1` | 200k | Advanced reasoning | `OPENAI_API_KEY` |
| **Google** | `gemini-2.5-pro-preview-03-25` | 1M | Long context, multimodal | `GEMINI_API_KEY` |
| **Google** | `gemini-2.0-flash` | 1M | Fast, large context | `GEMINI_API_KEY` |
| **Google** | `gemini-1.5-pro` | 2M | Largest context window | `GEMINI_API_KEY` |
| **Moonshot (Kimi)** | `moonshot-v1-8k` | 8k | Chinese & English | `MOONSHOT_API_KEY` |
| **Moonshot (Kimi)** | `moonshot-v1-32k` | 32k | Chinese & English | `MOONSHOT_API_KEY` |
| **Moonshot (Kimi)** | `moonshot-v1-128k` | 128k | Long context | `MOONSHOT_API_KEY` |
| **Alibaba (Qwen)** | `qwen-max` | 32k | Best Qwen quality | `DASHSCOPE_API_KEY` |
| **Alibaba (Qwen)** | `qwen-plus` | 128k | Balanced | `DASHSCOPE_API_KEY` |
| **Alibaba (Qwen)** | `qwen-turbo` | 1M | Fast, cheap | `DASHSCOPE_API_KEY` |
| **Alibaba (Qwen)** | `qwq-32b` | 32k | Strong reasoning | `DASHSCOPE_API_KEY` |
| **Zhipu (GLM)** | `glm-4-plus` | 128k | Best GLM quality | `ZHIPU_API_KEY` |
| **Zhipu (GLM)** | `glm-4` | 128k | General purpose | `ZHIPU_API_KEY` |
| **Zhipu (GLM)** | `glm-4-flash` | 128k | Free tier available | `ZHIPU_API_KEY` |
| **DeepSeek** | `deepseek-chat` | 64k | Strong coding | `DEEPSEEK_API_KEY` |
| **DeepSeek** | `deepseek-reasoner` | 64k | Chain-of-thought reasoning | `DEEPSEEK_API_KEY` |

### Open-Source (Local via Ollama)

| Model | Size | Strengths | Pull Command |
|---|---|---|---|
| `llama3.3` | 70B | General purpose, strong reasoning | `ollama pull llama3.3` |
| `llama3.2` | 3B / 11B | Lightweight | `ollama pull llama3.2` |
| `qwen2.5-coder` | 7B / 32B | **Best for coding tasks** | `ollama pull qwen2.5-coder` |
| `qwen2.5` | 7B / 72B | Chinese & English | `ollama pull qwen2.5` |
| `deepseek-r1` | 7B–70B | Reasoning, math | `ollama pull deepseek-r1` |
| `deepseek-coder-v2` | 16B | Coding | `ollama pull deepseek-coder-v2` |
| `mistral` | 7B | Fast, efficient | `ollama pull mistral` |
| `mixtral` | 8x7B | Strong MoE model | `ollama pull mixtral` |
| `phi4` | 14B | Microsoft, strong reasoning | `ollama pull phi4` |
| `gemma3` | 4B / 12B / 27B | Google open model | `ollama pull gemma3` |
| `codellama` | 7B / 34B | Code generation | `ollama pull codellama` |

> **Note:** Tool calling requires a model that supports function calling. Recommended local models: `qwen2.5-coder`, `llama3.3`, `mistral`, `phi4`.

---

## Installation

```bash
git clone <repo-url>
cd nano_claude_code

pip install -r requirements.txt
# or manually:
pip install anthropic openai httpx rich
```

---

## Usage: Closed-Source API Models

### Anthropic Claude

Get your API key at [console.anthropic.com](https://console.anthropic.com).

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...

# Default model (claude-opus-4-6)
python nano_claude.py

# Choose a specific model
python nano_claude.py --model claude-sonnet-4-6
python nano_claude.py --model claude-haiku-4-5-20251001

# Enable Extended Thinking
python nano_claude.py --model claude-opus-4-6 --thinking --verbose
```

### OpenAI GPT

Get your API key at [platform.openai.com](https://platform.openai.com).

```bash
export OPENAI_API_KEY=sk-...

python nano_claude.py --model gpt-4o
python nano_claude.py --model gpt-4o-mini
python nano_claude.py --model o3-mini
```

### Google Gemini

Get your API key at [aistudio.google.com](https://aistudio.google.com).

```bash
export GEMINI_API_KEY=AIza...

python nano_claude.py --model gemini/gemini-2.0-flash
python nano_claude.py --model gemini/gemini-1.5-pro
python nano_claude.py --model gemini/gemini-2.5-pro-preview-03-25
```

### Kimi (Moonshot AI)

Get your API key at [platform.moonshot.cn](https://platform.moonshot.cn).

```bash
export MOONSHOT_API_KEY=sk-...

python nano_claude.py --model kimi/moonshot-v1-32k
python nano_claude.py --model kimi/moonshot-v1-128k
```

### Qwen (Alibaba DashScope)

Get your API key at [dashscope.aliyun.com](https://dashscope.aliyun.com).

```bash
export DASHSCOPE_API_KEY=sk-...

python nano_claude.py --model qwen/qwen-max
python nano_claude.py --model qwen/qwq-32b
python nano_claude.py --model qwen/qwen2.5-coder-32b-instruct
```

### Zhipu GLM

Get your API key at [open.bigmodel.cn](https://open.bigmodel.cn).

```bash
export ZHIPU_API_KEY=...

python nano_claude.py --model zhipu/glm-4-plus
python nano_claude.py --model zhipu/glm-4-flash   # free tier
```

### DeepSeek

Get your API key at [platform.deepseek.com](https://platform.deepseek.com).

```bash
export DEEPSEEK_API_KEY=sk-...

python nano_claude.py --model deepseek/deepseek-chat
python nano_claude.py --model deepseek/deepseek-reasoner
```

---

## Usage: Open-Source Models (Local)

### Option A — Ollama (Recommended)

Ollama runs models locally with zero configuration. No API key required.

**Step 1: Install Ollama**

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Or download from https://ollama.com/download
```

**Step 2: Pull a model**

```bash
# Best for coding (recommended)
ollama pull qwen2.5-coder          # 4.7 GB (7B)
ollama pull qwen2.5-coder:32b      # 19 GB (32B)

# General purpose
ollama pull llama3.3               # 42 GB (70B)
ollama pull llama3.2               # 2.0 GB (3B)

# Reasoning
ollama pull deepseek-r1            # 4.7 GB (7B)
ollama pull deepseek-r1:32b        # 19 GB (32B)

# Other
ollama pull phi4                   # 9.1 GB (14B)
ollama pull mistral                # 4.1 GB (7B)
```

**Step 3: Start Ollama server** (runs automatically on macOS; on Linux run manually)

```bash
ollama serve     # starts on http://localhost:11434
```

**Step 4: Run nano claude**

```bash
python nano_claude.py --model ollama/qwen2.5-coder
python nano_claude.py --model ollama/llama3.3
python nano_claude.py --model ollama/deepseek-r1
```

**List your locally available models:**

```bash
ollama list
```

Then use any model from the list:

```bash
python nano_claude.py --model ollama/<model-name>
```

---

### Option B — LM Studio

LM Studio provides a GUI to download and run models, with a built-in OpenAI-compatible server.

**Step 1:** Download [LM Studio](https://lmstudio.ai) and install it.

**Step 2:** Search and download a model inside LM Studio (GGUF format).

**Step 3:** Go to **Local Server** tab → click **Start Server** (default port: 1234).

**Step 4:**

```bash
python nano_claude.py --model lmstudio/<model-name>
# e.g.:
python nano_claude.py --model lmstudio/phi-4-GGUF
python nano_claude.py --model lmstudio/qwen2.5-coder-7b
```

The model name should match what LM Studio shows in the server status bar.

---

### Option C — vLLM / Self-Hosted OpenAI-Compatible Server

For self-hosted inference servers (vLLM, TGI, llama.cpp server, etc.) that expose an OpenAI-compatible API:

```bash
# Example: vLLM serving Qwen2.5-Coder-32B
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-Coder-32B-Instruct \
    --port 8000

# Then run nano claude pointing to your server:
python nano_claude.py
```

Inside the REPL:

```
/config custom_base_url=http://localhost:8000/v1
/config custom_api_key=token-abc123    # skip if no auth
/model custom/Qwen2.5-Coder-32B-Instruct
```

Or set via environment:

```bash
export CUSTOM_BASE_URL=http://localhost:8000/v1
export CUSTOM_API_KEY=token-abc123

python nano_claude.py --model custom/Qwen2.5-Coder-32B-Instruct
```

For a remote GPU server:

```bash
/config custom_base_url=http://192.168.1.100:8000/v1
/model custom/your-model-name
```

---

## Model Name Format

Three equivalent formats are supported:

```bash
# 1. Auto-detect by prefix (works for well-known models)
python nano_claude.py --model gpt-4o
python nano_claude.py --model gemini-2.0-flash
python nano_claude.py --model deepseek-chat

# 2. Explicit provider prefix with slash
python nano_claude.py --model ollama/qwen2.5-coder
python nano_claude.py --model kimi/moonshot-v1-128k

# 3. Explicit provider prefix with colon (also works)
python nano_claude.py --model kimi:moonshot-v1-32k
python nano_claude.py --model qwen:qwen-max
```

**Auto-detection rules:**

| Model prefix | Detected provider |
|---|---|
| `claude-` | anthropic |
| `gpt-`, `o1`, `o3` | openai |
| `gemini-` | gemini |
| `moonshot-`, `kimi-` | kimi |
| `qwen`, `qwq-` | qwen |
| `glm-` | zhipu |
| `deepseek-` | deepseek |
| `llama`, `mistral`, `phi`, `gemma`, `mixtral`, `codellama` | ollama |

---

## CLI Reference

```
python nano_claude.py [OPTIONS] [PROMPT]

Options:
  -p, --print          Non-interactive: run prompt and exit
  -m, --model MODEL    Override model (e.g. gpt-4o, ollama/llama3.3)
  --accept-all         Auto-approve all operations (no permission prompts)
  --verbose            Show thinking blocks and per-turn token counts
  --thinking           Enable Extended Thinking (Claude only)
  --version            Print version and exit
  -h, --help           Show help
```

**Examples:**

```bash
# Interactive REPL with default model
python nano_claude.py

# Switch model at startup
python nano_claude.py --model gpt-4o
python nano_claude.py -m ollama/deepseek-r1:32b

# Non-interactive / scripting
python nano_claude.py --print "Write a Python fibonacci function"
python nano_claude.py -p "Explain the Rust borrow checker in 3 sentences" -m gemini/gemini-2.0-flash

# CI / automation (no permission prompts)
python nano_claude.py --accept-all --print "Initialize a Python project with pyproject.toml"

# Debug mode (see tokens + thinking)
python nano_claude.py --thinking --verbose
```

---

## Slash Commands (REPL)

Type `/` and press **Tab** to autocomplete.

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/clear` | Clear conversation history |
| `/model` | Show current model + list all available models |
| `/model <name>` | Switch model (takes effect immediately) |
| `/config` | Show all current config values |
| `/config key=value` | Set a config value (persisted to disk) |
| `/save` | Save session (auto-named by timestamp) |
| `/save <filename>` | Save session to named file |
| `/load` | List all saved sessions |
| `/load <filename>` | Load a saved session |
| `/history` | Print full conversation history |
| `/context` | Show message count and token estimate |
| `/cost` | Show token usage and estimated USD cost |
| `/verbose` | Toggle verbose mode (tokens + thinking) |
| `/thinking` | Toggle Extended Thinking (Claude only) |
| `/permissions` | Show current permission mode |
| `/permissions <mode>` | Set permission mode: `auto` / `accept-all` / `manual` |
| `/cwd` | Show current working directory |
| `/cwd <path>` | Change working directory |
| `/exit` / `/quit` | Exit |

**Switching models inside a session:**

```
[myproject] ❯ /model
  Current model: claude-opus-4-6  (provider: anthropic)

  Available models by provider:
    anthropic     claude-opus-4-6, claude-sonnet-4-6, ...
    openai        gpt-4o, gpt-4o-mini, o3-mini, ...
    ollama        llama3.3, llama3.2, phi4, mistral, ...
    ...

[myproject] ❯ /model gpt-4o
  Model set to gpt-4o  (provider: openai)

[myproject] ❯ /model ollama/qwen2.5-coder
  Model set to ollama/qwen2.5-coder  (provider: ollama)
```

---

## Configuring API Keys

### Method 1: Environment Variables (recommended)

```bash
# Add to ~/.bashrc or ~/.zshrc
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export GEMINI_API_KEY=AIza...
export MOONSHOT_API_KEY=sk-...       # Kimi
export DASHSCOPE_API_KEY=sk-...      # Qwen
export ZHIPU_API_KEY=...             # Zhipu GLM
export DEEPSEEK_API_KEY=sk-...       # DeepSeek
```

### Method 2: Set Inside the REPL (persisted)

```
/config anthropic_api_key=sk-ant-...
/config openai_api_key=sk-...
/config gemini_api_key=AIza...
/config kimi_api_key=sk-...
/config qwen_api_key=sk-...
/config zhipu_api_key=...
/config deepseek_api_key=sk-...
```

Keys are saved to `~/.nano_claude/config.json` and loaded automatically on next launch.

### Method 3: Edit the Config File Directly

```json
// ~/.nano_claude/config.json
{
  "model": "qwen/qwen-max",
  "max_tokens": 8192,
  "permission_mode": "auto",
  "verbose": false,
  "thinking": false,
  "qwen_api_key": "sk-...",
  "kimi_api_key": "sk-...",
  "deepseek_api_key": "sk-..."
}
```

---

## Permission System

| Mode | Behavior |
|---|---|
| `auto` (default) | Read-only operations always allowed. Prompts before Bash commands and file writes. |
| `accept-all` | Never prompts. All operations proceed automatically. |
| `manual` | Prompts before every single operation, including reads. |

**When prompted:**

```
  Allow: Run: git commit -am "fix bug"  [y/N/a(ccept-all)]
```

- `y` — approve this one action
- `n` or Enter — deny
- `a` — approve and switch to `accept-all` for the rest of the session

**Commands always auto-approved in `auto` mode:**
`ls`, `cat`, `head`, `tail`, `wc`, `pwd`, `echo`, `git status`, `git log`, `git diff`, `git show`, `find`, `grep`, `rg`, `python`, `node`, `pip show`, `npm list`, and other read-only shell commands.

---

## Built-in Tools

| Tool | Description | Key Parameters |
|---|---|---|
| `Read` | Read file with line numbers | `file_path`, `limit`, `offset` |
| `Write` | Create or overwrite file | `file_path`, `content` |
| `Edit` | Exact string replacement in file | `file_path`, `old_string`, `new_string`, `replace_all` |
| `Bash` | Execute shell command | `command`, `timeout` (default 30s) |
| `Glob` | Find files by glob pattern | `pattern` (e.g. `**/*.py`), `path` |
| `Grep` | Regex search in files (uses ripgrep if available) | `pattern`, `path`, `glob`, `output_mode` |
| `WebFetch` | Fetch and extract text from URL | `url`, `prompt` |
| `WebSearch` | Search the web via DuckDuckGo | `query` |

---

## CLAUDE.md Support

Place a `CLAUDE.md` file in your project to give the model persistent context about your codebase. Nano Claude automatically finds and injects it into the system prompt.

```
~/.claude/CLAUDE.md          # Global — applies to all projects
/your/project/CLAUDE.md      # Project-level — found by walking up from cwd
```

**Example `CLAUDE.md`:**

```markdown
# Project: FastAPI Backend

## Stack
- Python 3.12, FastAPI, PostgreSQL, SQLAlchemy 2.0, Alembic
- Tests: pytest, coverage target 90%

## Conventions
- Format with black, lint with ruff
- Full type annotations required
- New endpoints must have corresponding tests

## Important Notes
- Never hard-code credentials — use environment variables
- Do not modify existing Alembic migration files
- The `staging` branch deploys automatically to staging on push
```

---

## Session Management

```bash
# Inside REPL:
/save                          # auto-name: session_20260401_143022.json
/save debug_auth_bug           # named save

/load                          # list all saved sessions
/load debug_auth_bug           # resume a session
/load session_20260401_143022.json
```

Sessions are stored as JSON in `~/.nano_claude/sessions/`.

---

## Project Structure

```
nano_claude_code/
├── nano_claude.py   # Entry point: REPL + slash commands + output rendering  (~580 lines)
├── agent.py         # Agent loop: neutral message format + tool dispatch      (~160 lines)
├── providers.py     # Multi-provider: adapters + message format conversion    (~480 lines)
├── tools.py         # 8 tool implementations + JSON schemas                  (~360 lines)
├── context.py       # System prompt builder: CLAUDE.md + git + cwd           (~100 lines)
├── config.py        # Config load/save/defaults                               (~70 lines)
├── demo.py          # Demo script (requires API key)
├── make_demo.py     # Generates demo.gif and screenshot.png
├── demo.gif         # Animated demo
├── screenshot.png   # Static screenshot
└── requirements.txt
```

---

## FAQ

**Q: Tool calls don't work with my local Ollama model.**

Not all models support function calling. Use one of the recommended tool-calling models: `qwen2.5-coder`, `llama3.3`, `mistral`, or `phi4`.

```bash
ollama pull qwen2.5-coder
python nano_claude.py --model ollama/qwen2.5-coder
```

**Q: How do I connect to a remote GPU server running vLLM?**

```
/config custom_base_url=http://your-server-ip:8000/v1
/config custom_api_key=your-token
/model custom/your-model-name
```

**Q: How do I check my API cost?**

```
/cost

  Input tokens:  3,421
  Output tokens:   892
  Est. cost:     $0.0648 USD
```

**Q: Can I use multiple API keys in the same session?**

Yes. Set all the keys you need upfront (via env vars or `/config`). Then switch models freely — each call uses the key for the active provider.

**Q: How do I make a model available across all projects?**

Add keys to `~/.bashrc` or `~/.zshrc`. Set the default model in `~/.nano_claude/config.json`:

```json
{ "model": "claude-sonnet-4-6" }
```

**Q: Qwen / Zhipu returns garbled text.**

Ensure your `DASHSCOPE_API_KEY` / `ZHIPU_API_KEY` is correct and the account has sufficient quota. Both providers use UTF-8 and handle Chinese well.

**Q: Can I pipe input to nano claude?**

```bash
echo "Explain this file" | python nano_claude.py --print --accept-all
cat error.log | python nano_claude.py -p "What is causing this error?"
```

**Q: How do I run it as a CLI tool from anywhere?**

```bash
# Add an alias to ~/.bashrc or ~/.zshrc
alias nc='python /path/to/nano_claude_code/nano_claude.py'

# Or install as a script
pip install -e .   # if setup.py exists
```
