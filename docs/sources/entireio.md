# Entire.io source

Cross-agent session capture. Indexes sessions from Claude Code, Cursor, and Codex through Entire.io's git-based checkpoints.

## What is Entire.io

[Entire.io](https://entire.io) captures coding agent checkpoints as commits on a git branch (`entire/checkpoints/v1`). Each checkpoint contains session metadata, conversation JSONL, and file diffs. When integrated into a repo, it records sessions from all supported agents automatically.

Git tracks *what* changed. Entire captures *how* — the reasoning, tool calls, and iterations that produced those changes. cinsights analyzes that data.

## Why use it

- **Cross-agent** — one unified view of Claude Code, Cursor, and Codex sessions in the same project
- **Cross-machine** — checkpoints are git commits, so they sync wherever the repo is pushed
- **Historical** — checkpoints persist even after local session files are pruned

## Setup

1. Install [Entire.io](https://entire.io) and configure it in your repo
2. Ensure the repo has the `entire/checkpoints/v1` branch with captured sessions
3. Point cinsights at the repo:

```bash
cinsights index --source entireio --repo /path/to/your/repo --hours 8760
```

Or set the env var:

```bash
export CINSIGHTS_ENTIREIO_REPO_PATH=/path/to/your/repo
```

## How it works

cinsights reads the checkpoint branch using dulwich (pure-Python git). It never modifies the repo.

For each checkpoint: reads the metadata, parses session JSONL files, reconstructs tool call timelines, and computes [quality metrics](../concepts.md#quality-metrics). Sessions are attributed to the developer and agent type recorded in the checkpoint metadata.

## Running

```bash
# Index all checkpoints
cinsights index --source entireio --repo /path/to/repo --hours 8760

# Index + analyze
cinsights refresh --source entireio --repo /path/to/repo --hours 8760

# Generate project digest
cinsights digest project my-app --days 30
```

Makefile shortcuts: `make index-entireio REPO=/path/to/repo`, `make refresh-entireio REPO=/path/to/repo`.

## Multiple repos

Run cinsights against each repo separately. Sessions from all repos coexist in the same database, so digests and the web UI show a unified view across all of them.

```bash
cinsights refresh --source entireio --repo /path/to/repo-a --hours 8760
cinsights refresh --source entireio --repo /path/to/repo-b --hours 8760
cinsights digest project repo-a --days 30
```
