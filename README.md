# cinsights

AI coding agents are transforming how teams build software. But when your team uses Claude Code, Cursor, and Codex across dozens of projects, a fundamental question goes unanswered: *is it actually working?*

cinsights is built for engineering teams that want to understand how their developers work with AI coding agents - not per-session logs, but patterns across time, across agents, and across your whole team. Which projects have the most friction? Which developers are getting the most value? What CLAUDE.md rules would help everyone? Where is token spend going and is it worth it?

<!-- screenshot: dashboard-overview -->

## What you get

**Per-project insights** - friction patterns, tool usage, quality metrics, and copy-paste-ready CLAUDE.md suggestions specific to each project. Updated as new sessions come in.

**Per-developer insights** - developer personas, workflow patterns, feature recommendations, and how each developer's interaction style compares to their own baseline over time.

**Friction analysis** - recurring pain points identified from tool call patterns, grounded in specific sessions, with actionable fixes. Not "you had errors" but "you have a repeated read-before-edit pattern on `src/auth/` that costs ~40 tool calls per session - here's the CLAUDE.md rule that fixes it."

**Quality metrics** - read:edit ratio, error rate, context pressure, repeated edits, tokens per useful edit. Computed from tool call sequences, zero LLM cost. The smoke detectors that tell you something is off before you spend tokens figuring out what.

**Cross-session digests** - aggregated over days or weeks, scoped to a project or developer. Not a snapshot: a running picture of how patterns evolve.

<!-- screenshot: session-detail -->

## Quick start

```bash
# Install
pip install cinsights
# or: uvx cinsights

# Configure LLM (interactive)
cinsights setup

# Index + analyze local Claude Code / Codex sessions
cinsights refresh --source local --hours 8760

# Generate a project digest
cinsights digest project my-project --days 30

# Start the web UI
cinsights serve
```

Open [http://localhost:8100](http://localhost:8100). See the [getting started guide](docs/getting-started.md) for the full walkthrough.

## Data sources

| Source | What it reads | Best for |
|--------|--------------|----------|
| [Local](docs/sources/local.md) | `~/.claude` and `~/.codex` session files | Try in 2 minutes. No external dependencies. |
| [Entire.io](docs/sources/entireio.md) | Git-based checkpoints across Claude Code, Cursor, Codex | Cross-agent and cross-machine coverage for teams. |
| [Phoenix](docs/sources/phoenix.md) | Arize Phoenix traces | Centralized team observability. |

## Documentation

- [Getting started](docs/getting-started.md) - install, configure, first run
- [Concepts](docs/concepts.md) - pipeline, quality metrics, scoring, insights, digests
- [Configuration](docs/configuration.md) - env vars, config file, CLI reference
- **Sources**: [Local](docs/sources/local.md) · [Entire.io](docs/sources/entireio.md) · [Phoenix](docs/sources/phoenix.md)
- [Self-hosting](docs/self-hosting.md) - run cinsights on your infrastructure
