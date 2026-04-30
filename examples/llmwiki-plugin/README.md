# llmwiki plugin

Memory management for CheetahClaws via [llmwiki-py](https://github.com/yamaceay/llmwiki-py).

## Quick install

```bash
# 1. Install llmwiki-py (once, from its source directory)
cd /path/to/llmwiki-py
pip install -e .

# 2. Create and initialise a wiki
export LLMWIKI_WIKI_ROOT="$HOME/my-wiki"
wiki init

# 3. Copy this plugin into CheetahClaws
cp -r /path/to/openclaude/examples/llmwiki-plugin ~/.cheetahclaws/plugins/llmwiki

# 4. Enable it
cheetahclaws
/plugin enable llmwiki
```

## Tools registered

| Tool | What it does |
|---|---|
| `WikiRead` | Read a page by path |
| `WikiWrite` | Create or overwrite a page |
| `WikiAppend` | Append to an existing page |
| `WikiSearch` | Full-text search with snippets |
| `WikiList` | Directory tree of all pages |
| `WikiStatus` | Wiki health check |

## Updating llmwiki-py

```bash
cd /path/to/llmwiki-py
git pull
pip install -e .   # only if dependencies changed
```

## Full documentation

See [docs/guides/llmwiki.md](../../docs/guides/llmwiki.md).
