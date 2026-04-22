<div align="center">

# cinsights

<img src="https://raw.githubusercontent.com/deepankarm/cinsights/main/.github/images/logo.svg" width="120" height="120" alt="cinsights logo">

**Coding agent insights for teams**

</div>

AI coding agents are transforming how teams build software. But when your team uses Claude Code, Cursor, and Codex across dozens of projects, you have no visibility into how they're being used, where the friction is, or whether things are getting better or worse over time.

cinsights helps engineering teams track, understand, and improve how their developers work with AI coding agents. Not per-session logs, but patterns across time, across agents, and across your whole team.

**Per-project digests** - what's working, what's hindering, quick wins, and ambitious ideas. Aggregated across sessions over days or weeks, not a single-run snapshot.

![Project insights - at a glance](.github/images/project-insights-summary.png)

**Grounded friction analysis** - recurring pain points linked to specific sessions with impact estimates. Copy-paste CLAUDE.md rules and feature recommendations generated from your team's actual friction patterns.

![Friction analysis with evidence](.github/images/project-insights-frictions.png)

**Per-developer profiles** - work areas, interaction style, tool preferences, and how each developer uses coding agents. Built from cross-session patterns, not self-reported surveys.

![Developer work areas and persona](.github/images/developer-insights-workareas.png)

Plus: [behavioral patterns](docs/concepts.md#behavioral-patterns) that surface how each developer interacts with agents, [mood quotes](docs/concepts.md#developer-mood-quotes) — the actual things developers say to their coding agents when frustrated, amused, or relieved, and [quality comparison](docs/concepts.md#quality-comparison) across the team.

## Quick start

```bash
# Install
pip install cinsights
# or: uvx cinsights

# Configure LLM (interactive)
cinsights setup
# No API key? Use Ollama instead:
# ollama pull qwen2.5:14b
# cinsights setup --provider openai --model qwen2.5:14b --base-url http://localhost:11434/v1

# Index local Claude Code / Codex sessions (free, no LLM calls)
cinsights index --source local --hours 8760

# Analyze sessions (shows cost estimate, asks for confirmation)
cinsights analyze --source local

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

## [Documentation](docs/README.md)

- [Getting started](docs/getting-started.md) - install, configure, first run
- [Concepts](docs/concepts.md) - pipeline, quality metrics, scoring, insights, digests
- [How it works](docs/how-it-works.md) - what data goes to the LLM, what stays local, cost breakdown
- [Configuration](docs/configuration.md) - env vars, config file, CLI reference
- [FAQ](docs/faq.md) - common questions and troubleshooting
- **Sources**: [Local](docs/sources/local.md) · [Entire.io](docs/sources/entireio.md) · [Phoenix](docs/sources/phoenix.md)
- [Self-hosting](docs/self-hosting.md) - run cinsights on your infrastructure
