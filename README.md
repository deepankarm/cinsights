# cinsights

LLM-powered insights from coding agent sessions.

Every coding agent tracks its own usage in silos. Claude Code has `/insights`, Cursor has analytics, Codex has logs — but none of them talk to each other. cinsights gives you the unified view: it indexes sessions across agents and projects, runs LLM analysis to surface friction points, wins, and patterns, and generates cross-session digests with actionable recommendations per developer and per project.

<!-- screenshot: dashboard-overview -->

## What you get

- **Quality metrics** — read:edit ratio, error rate, context pressure, repeated edits, and more. Computed from tool call sequences, zero LLM cost.
- **Per-session insights** — friction points, wins, recommendations, patterns, and skill proposals extracted by LLM analysis.
- **Cross-session digests** — developer personas, CLAUDE.md suggestions, workflow patterns, friction analysis, and feature recommendations aggregated across sessions.
- **Web dashboard** — browse sessions, drill into insights, view project and developer profiles, track trends.

<!-- screenshot: session-detail -->

## Quick start

```bash
git clone https://github.com/deepankarm/cinsights.git
cd cinsights
make init
export ANTHROPIC_API_KEY=sk-ant-...

# Index local Claude Code / Codex sessions + LLM-analyze
uv run cinsights refresh --source local --hours 8760

# Generate a project digest
uv run cinsights digest project my-project --days 30

# Start the web UI
uv run cinsights serve
```

Open [http://localhost:8100](http://localhost:8100). See the [getting started guide](docs/getting-started.md) for the full walkthrough.

## Data sources

| Source | What it reads | Best for |
|--------|--------------|----------|
| [Local](docs/sources/local.md) | `~/.claude` and `~/.codex` session files | Try in 2 minutes. No external dependencies. |
| [Entire.io](docs/sources/entireio.md) | Git-based checkpoints across Claude Code, Cursor, Codex | Cross-agent and cross-machine coverage. |
| [Phoenix](docs/sources/phoenix.md) | Arize Phoenix traces | You already run Phoenix for observability. |

## How it works

Three-stage pipeline: **index** (discover sessions, compute quality metrics, score — zero LLM cost) → **analyze** (LLM extracts per-session insights) → **digest** (LLM synthesizes cross-session report). See [concepts](docs/concepts.md) for details.

## Documentation

- [Getting started](docs/getting-started.md) — install, configure, first run
- [Concepts](docs/concepts.md) — pipeline, quality metrics, scoring, insights, digests
- [Configuration](docs/configuration.md) — env vars, config file, CLI reference
- **Sources**: [Local](docs/sources/local.md) · [Entire.io](docs/sources/entireio.md) · [Phoenix](docs/sources/phoenix.md)

## Requirements

- Python 3.11+
- Node.js 20+ (for the UI)
- An LLM API key (Anthropic by default, any pydantic-ai provider works)

## License

Apache-2.0
