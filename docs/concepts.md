# Concepts

## The pipeline

cinsights processes coding agent sessions in three stages. Each stage is independently runnable.

```
index ──→ analyze ──→ digest
(free)    (tokens)    (tokens)
```

**Index** (`cinsights index`) discovers sessions from the configured source, parses tool call timelines, computes quality metrics, and scores each session against the developer's baseline. Zero LLM cost. This is the stage you can run as often as you want.

**Analyze** (`cinsights analyze`) sends scored sessions to the LLM for per-session insight extraction — friction points, wins, recommendations, patterns, and skill proposals. Costs tokens, but only runs on sessions above the score threshold.

**Digest** (`cinsights digest project <name>` or `cinsights digest user <id>`) aggregates analyzed sessions into a cross-session report scoped to a project or developer. Runs three concurrent LLM calls to produce a narrative, actionable recommendations, and forward-looking patterns.

`cinsights refresh` chains index and analyze in one shot. Run digest separately per project or user.

Index is free. Analyze and digest cost tokens. They're separate so you can run index as often as you want and only spend tokens when it matters.

## Quality metrics

Computed during indexing from tool call sequences alone. No LLM needed.

| Metric | What it measures | Good | Degraded |
|--------|-----------------|------|----------|
| `read_edit_ratio` | Read calls / Edit calls — how much the agent researches before modifying | ~6.6 | ~2.0 |
| `edits_without_read_pct` | % of Edit calls where the file was not Read first | ~6% | ~34% |
| `research_mutation_ratio` | All research calls (Read+Grep+Glob) / all mutations (Edit+Write) | ~8.7 | ~2.8 |
| `write_vs_edit_pct` | Full-file Write calls as % of all mutations | ~5% | ~11% |
| `error_rate` | % of tool calls that failed | low | high |
| `repeated_edits_count` | Consecutive edits to the same file (thrashing indicator) | 0-1 | 5+ |
| `tokens_per_useful_edit` | Total tokens / successful Edit+Write calls | low | high |
| `context_pressure_score` | Fraction of turns where prompt tokens grew by >50% (0-1) | <0.1 | >0.5 |
| `subagent_spawn_rate` | Agent/Task tool calls as % of total | varies | — |
| `turn_count` | Number of conversation turns | — | — |
| `tool_calls_per_turn` | Average tool calls per turn | — | — |

Quality metrics are the smoke detectors. They tell you something is off before you spend tokens figuring out what.

## Scoring and budget modes

Not every session is worth analyzing with an LLM. cinsights scores sessions on "interestingness" — how much they deviate from the developer's baseline.

**Scoring signals** (weighted 0-1 each):
- Error rate deviation from baseline (15%)
- New project / cold start (15%)
- Read:Edit ratio drop (10%)
- Blind edit rate deviation (10%)
- Repeated edits / thrashing (10%)
- New agent type (10%)
- Turn count deviation (7%)
- Duration deviation (7%)
- Context pressure (6%)
- Research:mutation ratio drop (5%)
- Session abandonment (5%)

Routine sessions cluster at 0.2-0.4. Interesting ones land at 0.6+.

**Budget modes** control what gets analyzed:

| Mode | Threshold | Use case |
|------|-----------|----------|
| `frugal` | top ~10% | Minimize spend, surface only clear outliers |
| `balanced` | score >= 0.4 (default) | Good coverage without waste |
| `thorough` | top ~50% | Deeper analysis, higher token cost |
| `all` | everything | Full coverage, use for small teams or audits |

**Cold start**: the first N sessions per (user, project) pair are always analyzed regardless of score (default: 10). This builds the baseline before scoring kicks in.

Most coding sessions are routine. Budget modes exist because your LLM bill should scale with how much you learn, not how much you code.

## Per-session insights

What the LLM extracts from each analyzed session:

| Category | What it captures |
|----------|-----------------|
| **Summary** | 2-3 sentences on what happened — interaction efficiency, tool usage, overall flow |
| **Friction** | Where the developer-agent interaction broke down — wrong approaches, permission blocks, wasted reads, token waste |
| **Wins** | Efficient moments — multi-step tasks in one shot, good tool selection, effective sub-agent usage |
| **Recommendations** | How to configure the coding agent better — CLAUDE.md rules, skills, hooks, permissions |
| **Patterns** | Usage patterns — tool preferences, interaction style, session types |
| **Skill proposals** | Repeated workflows that could become custom slash commands |

Each insight has a severity: `info`, `warning`, or `critical`.

## Cross-session digest

The digest aggregates analyzed sessions over a time window (default: 7 days) for a specific project or developer. It runs three concurrent LLM calls:

**Narrative** — at-a-glance summary (what's working, what's hindering, quick wins, ambitious ideas), detected work areas, and a developer persona narrative.

**Actions** — friction analysis with categories and severity, copy-paste-ready CLAUDE.md suggestions with explanations, and feature recommendations for tools the developer might not know about.

**Forward-looking** — impressive wins worth repeating, workflow patterns codified as starter prompts, and ambitious automation ideas.

The digest is the product. Individual session insights are evidence. If you only look at one thing, look at the digest.
