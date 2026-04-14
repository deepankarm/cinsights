# Local source

Reads session files directly from your machine. No external services needed. This is the quickest way to try cinsights - if you've used Claude Code or Codex, you already have the data.

## What it reads

- **Claude Code**: `~/.claude/projects/*/sessions/*/` JSONL files
- **Codex**: `~/.codex/sessions/` JSONL files

cinsights parses the JSONL conversation logs to reconstruct tool call timelines, extract metadata (user, project, model, timestamps), and compute [quality metrics](../concepts.md#quality-metrics).

## Setup

Nothing to install. If you've used Claude Code or Codex, the files already exist.

```bash
# Pass --source on each command
cinsights index --source local

# Or set it globally
export CINSIGHTS_SOURCE=local
```

## Customizing session directories

By default, cinsights scans `~/.claude` and `~/.codex`. To add additional directories (e.g., a work profile):

```json
// ~/.cinsights/config.json
{
  "claude_code_homes": ["~/.claude", "~/.claude-work"],
  "codex_homes": ["~/.codex"]
}
```

See [configuration](../configuration.md#config-file) for the full config reference.

## Running

```bash
# Index all local sessions (--hours 8760 = ~1 year)
cinsights index --source local --hours 8760

# Index + analyze in one shot
cinsights refresh --source local --hours 8760

# Generate a project digest
cinsights digest project my-app --days 30
```

Makefile shortcuts: `make index-local`, `make refresh-local`.

## Limitations

- **Single machine** - reads files from this machine only. No syncing across machines.
- **Session retention** - Claude Code can prune old session files. Historical data depends on what's still on disk.

For cross-machine or cross-agent coverage, use [Entire.io](entireio.md). For centralized team observability, use [Phoenix](phoenix.md).

---

**[← Previous: Configuration](../configuration.md)**

<div align="right">

**[Next: Entire.io Source →](./entireio.md)**

</div>
