# Memory Management with llmwiki-py — Setup Tutorial

This guide walks you through every step: cloning the repo, initialising a wiki, wiring credentials, installing the CheetahClaws plugin, and running your first memory operation.

Estimated time: ~10 minutes.

---

## Prerequisites

- Python 3.11+
- `pip` on your `PATH`
- CheetahClaws installed and working (`cheetahclaws` launches the REPL)
- Git (for cloning and for the optional git-backend)

---

## Step 1 — Install llmwiki-py

Install directly from GitHub — no manual clone needed:

```bash
pip install "git+https://github.com/yamaceay/llmwiki-py.git#egg=llmwiki"
```

Verify the CLI landed on your PATH:

```bash
wiki --help
```

Expected first line: `Usage: wiki [OPTIONS] COMMAND [ARGS]...`

> **Python mismatch warning.** If you run CheetahClaws with a specific interpreter (e.g. `python3.11 cheetahclaws.py`), install with the same one:
> ```bash
> python3.11 -m pip install "git+https://github.com/yamaceay/llmwiki-py.git#egg=llmwiki"
> ```

> **Want a local editable copy instead?** If you prefer to clone and hack on the source:
> ```bash
> git clone https://github.com/yamaceay/llmwiki-py
> pip install -e ./llmwiki-py
> ```

---

## Step 3 — Create and initialise a wiki

### 3a. Choose a directory

The wiki root is just a folder on disk. Create it wherever you like:

```bash
mkdir -p ~/my-wiki
```

### 3b. Set the active wiki

llmwiki-py resolves the active wiki through three mechanisms in order:

1. `--wiki <id>` CLI flag (per-command override)
2. `.llmwiki.yaml` found by walking up from the current directory
3. Registry default (`~/.config/llmwiki/registry.yaml`)

`wiki init` registers the wiki automatically. Make it the default:

```bash
wiki use openclaude-memory
```

> **Note on `LLMWIKI_WIKI_ROOT`:** this env var is only read when calling the Python API directly (`Wiki(root=None)`). The `wiki` CLI ignores it — registry default is what controls the CLI.

### 3c. Initialise

```bash
wiki init "$LLMWIKI_WIKI_ROOT" --name "my-wiki" --domain general
```

This creates `~/my-wiki/.llmwiki.yaml` — the wiki's config file. Check it:

```bash
cat ~/my-wiki/.llmwiki.yaml
```

Expected output:

```yaml
backend: filesystem
created: '2026-04-30'
domain: general
name: my-wiki
paths:
  raw: raw
  schema: SCHEMA.md
  wiki: wiki
```

The `wiki/` subdirectory (at `~/my-wiki/wiki/`) is where all pages live. The `raw/` subdirectory holds unprocessed source material.

---

## Step 4 — Credentials (git backend only)

If you chose `--backend filesystem` (the default above) **skip this step entirely** — no credentials needed.

If you want the wiki backed by a GitHub repo so it survives across machines:

### 4a. Create a GitHub Personal Access Token

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Click **Generate new token**
3. Scopes needed: `Contents: Read and Write` on the target repo
4. Copy the token — you will not see it again

### 4b. Store the token

Never put a token in `.llmwiki.yaml` — it would end up in git history. Use an env var instead. llmwiki-py checks these in order:

| Env var | Notes |
|---|---|
| `LLMWIKI_GIT_TOKEN` | llmwiki-specific, takes highest priority |
| `GITHUB_TOKEN` | standard CI variable, works if already set |
| `GIT_TOKEN` | generic fallback |

Add to your shell profile:

```bash
echo 'export LLMWIKI_GIT_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"' >> ~/.zshrc
```

Replace `ghp_xxxx…` with your actual token. Then reload:

```bash
source ~/.zshrc
```

### 4c. Re-initialise with git backend

```bash
wiki init "$LLMWIKI_WIKI_ROOT" \
  --name "my-wiki" \
  --domain general \
  --backend git \
  --git-repo "yourusername/your-wiki-repo"
```

The token is read from the env var at runtime — do **not** pass `--git-token` on the command line (it would appear in shell history).

---

## Step 5 — Verify the wiki works

Run a quick smoke test before involving CheetahClaws:

```bash
# Check status
wiki status

# Write a test page
echo "# Hello\n\nFirst wiki page." | wiki write concepts/hello.md

# Read it back
wiki read concepts/hello.md

# List all pages
wiki list --tree

# Search
wiki search "hello"
```

All five commands should succeed without errors. If `wiki status` complains about a missing wiki, double-check that `LLMWIKI_WIKI_ROOT` is set in the current shell session.

---

## Step 6 — Install the CheetahClaws plugin

### 6a. Copy the plugin manifest

```bash
cp -r ~/aicore/openclaude/examples/llmwiki-plugin \
      ~/.cheetahclaws/plugins/llmwiki
```

The plugin directory must be named `llmwiki`. Verify:

```bash
ls ~/.cheetahclaws/plugins/llmwiki/
# plugin.json  tools.py  README.md
```

### 6b. Enable the plugin

Launch CheetahClaws and run:

```
/plugin enable llmwiki
```

Then confirm it's registered:

```
/plugin
```

Expected line: `llmwiki [user] enabled   Persistent memory management via llmwiki-py`

Restart CheetahClaws if the tools don't appear immediately.

---

## Step 7 — First memory operation

Inside the CheetahClaws REPL, tell the AI to write something:

```
remember that the auth service uses JWT with a 24h expiry
```

The AI will call `WikiWrite` to persist this. Then verify it was stored:

```
show me everything you know about auth
```

The AI will call `WikiSearch` and `WikiRead` and surface the note.

You can also check the file directly:

```bash
wiki list --tree
wiki read <path shown above>
```

---

## Step 8 — Update llmwiki-py

```bash
pip install --upgrade "git+https://github.com/yamaceay/llmwiki-py.git#egg=llmwiki"
```

If you installed from a local clone instead:

```bash
cd ~/aicore/llmwiki-py
git pull
```

No CheetahClaws restart needed after updating the package.

To pick up a newer plugin manifest from openclaude (e.g. after a `git pull` in openclaude):

```bash
cp -r ~/aicore/openclaude/examples/llmwiki-plugin \
      ~/.cheetahclaws/plugins/llmwiki
```

Then restart CheetahClaws.

---

## Setting environment variables via openclaude

You do not need to set variables in your shell profile. openclaude loads a `.env` file from its own directory at startup — before any plugin code runs — so variables defined there are available to every tool, including the wiki CLI subprocess.

Create the file (it is already in `.gitignore`, so it will never be committed):

```bash
# ~/aicore/openclaude/.env
LLMWIKI_WIKI_ROOT=/Users/you/my-wiki
LLMWIKI_GIT_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx   # only needed for git backend
```

Rules:
- One `KEY=VALUE` per line, no quotes needed around values
- Lines starting with `#` are comments
- If the variable is already set in your shell, the shell value takes precedence (`.env` is a fallback, not an override)

After editing `.env`, restart CheetahClaws once for the values to take effect.

---

## Environment variable reference

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `LLMWIKI_WIKI_ROOT` | Yes (simplest path) | — | Points directly at a wiki directory |
| `LLMWIKI_WIKI` | No | registry default | Selects a named wiki from the registry |
| `LLMWIKI_CONFIG_DIR` | No | `~/.config/llmwiki` | Location of `registry.yaml` |
| `LLMWIKI_GIT_TOKEN` | Only for git backend | — | GitHub PAT for push/pull |
| `GITHUB_TOKEN` | No | — | Fallback git token (standard CI var) |
| `GIT_TOKEN` | No | — | Second fallback git token |
| `LLMWIKI_GITHUB_API_URL` | No | `https://api.github.com` | Override for GitHub Enterprise |

All variables go in your shell profile (`~/.zshrc` or `~/.bashrc`) and take effect after `source ~/.zshrc` or opening a new terminal.

---

## Troubleshooting

**`wiki: command not found`**

```bash
# Find where pip installed it
python -m llmwiki.cli.main --help
# Add its bin dir to PATH, or use the module form:
alias wiki="python -m llmwiki.cli.main"
```

**`Error: no wiki found. Run 'wiki init' first.`**

`LLMWIKI_WIKI_ROOT` is not set in the current shell. Run `echo $LLMWIKI_WIKI_ROOT` to check, then `source ~/.zshrc` to reload your profile.

**`WikiRead` / `WikiWrite` return `"wiki command not found"` inside CheetahClaws**

CheetahClaws launched in a shell environment where `wiki` is not on `PATH`. Fix by using an absolute path in the plugin's `tools.py`, or ensure your shell profile exports `PATH` correctly and CheetahClaws inherits it.

**Tools disappear after a restart**

The plugin is enabled but CheetahClaws is losing the state. Check `~/.cheetahclaws/plugins.json` — the `llmwiki` entry should have `"enabled": true`.

**Git backend: authentication failed**

`LLMWIKI_GIT_TOKEN` is not reaching the process. Verify with `printenv LLMWIKI_GIT_TOKEN`. If empty, re-source your profile in the same terminal where you launch CheetahClaws.

---

## Reference

- [Plugin authoring guide](./plugin-authoring.md) — how the plugin system works
- [llmwiki-py repo](https://github.com/yamaceay/llmwiki-py) — source and issue tracker
- Plugin manifest: `examples/llmwiki-plugin/plugin.json`
- Plugin tools: `examples/llmwiki-plugin/tools.py`
