# Phoenix source

[Arize Phoenix](https://github.com/Arize-ai/phoenix) is an observability platform for LLM applications. When used as a cinsights source, it enables centralized team-wide insights - every developer on your team sends their coding agent traces to a shared Phoenix instance, and cinsights analyzes all of them to produce per-project and per-developer insights.

## How Phoenix fits in

In a team setup, each developer configures their local coding agents (Claude Code, Codex, Cursor) to send traces to a centrally running Phoenix instance - either self-hosted or via Arize's cloud offering. Phoenix collects and stores all the trace data. cinsights then reads from this Phoenix instance and generates cross-developer, cross-project insights.

```
Developer A (Claude Code) ──→
Developer B (Codex)       ──→  Phoenix (central)  ──→  cinsights  ──→  insights
Developer C (Cursor)      ──→
```

Phoenix gives you span-level observability. cinsights gives you session-level insights. Phoenix is the microscope, cinsights is the dashboard.

## Agent integrations

The Phoenix team provides official integrations for sending coding agent traces:

- **Claude Code**: [arize-claude-code-plugin](https://github.com/Arize-ai/arize-claude-code-plugin) - hooks into Claude Code to send traces to Phoenix
- **Other agents**: [arize-agent-kit](https://github.com/Arize-ai/arize-agent-kit) - OpenTelemetry-based tracing for Codex, Cursor, and other agents

> **Note**: The Phoenix team is actively developing these integrations. Some coding agents have more mature support than others, so session data coverage may vary depending on the agent.

## Setup

1. Run Phoenix (locally or hosted) and configure your team's coding agents to send traces
2. Set the cinsights source:

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
| [Local](local.md) | Quickest way to try cinsights. No external dependencies. Single machine. |
| [Entire.io](entireio.md) | Cross-agent coverage via git. Works end-to-end today with many agents. |
| **Phoenix** | Centralized team observability. All developers send traces to one place. |

---

**[← Previous: Entire.io Source](./entireio.md)**

<div align="right">

**[Next: Self-hosting →](../self-hosting.md)**

</div>
