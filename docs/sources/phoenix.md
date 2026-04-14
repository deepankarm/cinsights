# Phoenix source

If you already run [Arize Phoenix](https://github.com/Arize-ai/phoenix) for LLM observability, cinsights can read coding agent sessions from it.

Phoenix gives you span-level observability. cinsights gives you session-level insights. They complement each other — Phoenix is the microscope, cinsights is the dashboard.

## Prerequisites

- Arize Phoenix running (locally or hosted)
- [Arize Claude Code Plugin](https://github.com/Arize-ai/arize-claude-code-plugin) configured so Claude Code sends traces to Phoenix

## Setup

```bash
export CINSIGHTS_SOURCE=phoenix
export CINSIGHTS_PHOENIX_ENDPOINT=http://localhost:6006
export CINSIGHTS_PHOENIX_PROJECT=claude-code
```

## Running

```bash
# Index last 24h of sessions
cinsights index

# Index + analyze
cinsights refresh --hours 24

# Generate project digest
cinsights digest project my-app --days 30
```

Phoenix is the default source, so no `--source` flag is needed.

## When to use Phoenix vs. other sources

| Source | Best for |
|--------|----------|
| [Local](local.md) | Simplest path. No external dependencies. Try in 2 minutes. |
| [Entire.io](entireio.md) | Cross-agent (Claude Code + Cursor + Codex) and cross-machine coverage. |
| **Phoenix** | You already run Phoenix and want trace-level spans alongside cinsights' session-level insights. |
