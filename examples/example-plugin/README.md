# Example CheetahClaws Plugin

A minimal, working plugin template. Copy this directory to start building your own plugin.

## Quick Start

```bash
# Copy to your plugins directory
cp -r examples/example-plugin ~/.cheetahclaws/plugins/my-plugin

# Edit plugin.json — change name, description, etc.
# Edit tools.py — add your tool logic
# Edit cmd.py — add your slash commands

# Restart cheetahclaws and verify
cheetahclaws
/plugin              # should show your plugin
/example status      # test the example command
```

## What's Included

| File | Purpose |
|------|---------|
| `plugin.json` | Plugin manifest (name, version, what to load) |
| `tools.py` | Two example tools (`ExampleSearch`, `ExampleStatus`) |
| `cmd.py` | One example command (`/example` with `status` and `greet` subcommands) |
| `skills/example-skill.md` | One example skill prompt template |

## Learn More

- [Plugin Authoring Guide](../../docs/guides/plugin-authoring.md) — full documentation
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — project architecture and conventions
