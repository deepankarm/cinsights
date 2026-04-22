# FAQ

## General

### What data does cinsights send to the LLM?

A compressed summary of each session — not the full transcript. Tool call names, truncated input/output (500 chars max), developer queries (200 chars), and pre-computed metrics. Your source code and full conversation history are never sent. See [How it works](how-it-works.md) for the full breakdown.

### How much does it cost to run?

Indexing is free. A typical daily refresh (index + analyze ~50 sessions) costs **$0.05-0.15** with Gemini Flash Lite. A project digest costs **$0.03-0.10**. Use Ollama for completely free local inference (slower but works offline). See [How it works — cost breakdown](how-it-works.md#cost-breakdown-by-operation).

### Can I use it without an API key?

Yes. Install [Ollama](https://ollama.com), pull `qwen2.5:14b`, and configure cinsights to use it. Analysis takes ~2-3 minutes per digest instead of seconds, but it's free and fully offline.

### Which coding agents are supported?

- **Claude Code** — via local session files or Entire.io checkpoints
- **Codex** — via local session files or Entire.io checkpoints
- **Cursor** — via Entire.io checkpoints
- Any agent that sends traces to **Arize Phoenix**

### Does cinsights phone home?

No. The only external call is to your configured LLM provider when you run `analyze` or `digest`. Indexing, the web UI, and all metric computation are fully local.

## Sessions and analysis

### Why are some sessions not analyzed?

cinsights scores sessions on "interestingness" and only analyzes those above the threshold. Routine sessions (score 0.2-0.4) are skipped to save tokens. Change the threshold with `--min-score` or switch to `CINSIGHTS_BUDGET_MODE=all` to analyze everything. See [Concepts — scoring](concepts.md#scoring-and-budget-modes).

### How do I re-analyze a session?

```bash
cinsights analyze --force <session-id>
```

The `--force` flag re-analyzes even if the session was already processed.

### How do I re-analyze all sessions?

```bash
cinsights analyze --force --limit 500
```

Adjust `--limit` based on how many sessions you have. Be mindful of token costs.

### Why does a developer have no behavioral patterns?

Behavioral patterns require analyzed sessions. If a developer only has indexed (not analyzed) sessions, run `analyze` first. For developers with very few sessions (1-5), patterns may be sparse.

### Why does a developer have no digest?

Digests are generated per-project or per-developer on demand:

```bash
cinsights digest user <user-id> --days 30
```

The web UI shows activity charts and mood quotes even without a digest, since those come from per-session analysis and pre-computed scope stats.

### What's the difference between "indexed" and "analyzed"?

**Indexed** sessions have metadata, quality metrics, and interestingness scores — all computed locally for free. **Analyzed** sessions were additionally processed by an LLM to extract friction points, wins, recommendations, patterns, and mood quotes.

## Troubleshooting

### Sessions show 0 tool calls

The session file may be too short or contain only text messages without tool use. cinsights requires at least 1 tool call to compute meaningful metrics. Sessions below `CINSIGHTS_MIN_SESSION_TOOL_COUNT` (default: 10) are excluded from digest evidence.

### Ollama is very slow

Use `qwen2.5:14b` for best quality/speed tradeoff (~16GB RAM). The `7b` variant is faster but produces lower quality structured output. Digest generation takes 2-3 minutes with local models vs seconds with cloud APIs — this is expected.

### "No sessions found" when indexing

Check that the source is correct:
- **Local**: session files exist in `~/.claude/projects/*/sessions/` or `~/.codex/sessions/`
- **Entire.io**: the `--repo` path is correct and the `entire/checkpoints/v1` branch exists
- **Phoenix**: the endpoint is reachable and the project name matches

Also check the `--hours` flag — it defaults to 24 hours. Use `--hours 8760` for a full year.

### Digest says "0 analyzed sessions"

Run `analyze` before `digest`. The digest aggregates insights from analyzed sessions — it doesn't trigger analysis itself. Use `cinsights refresh` to chain index + analyze, then run digest separately.

### Quality metrics look wrong

Metrics are computed from tool call sequences. If the session parser doesn't recognize certain tool calls (e.g., from a new agent version), metrics may be incomplete. Re-index with `--force` after updating cinsights.

---

**[← Previous: Configuration](./configuration.md)**

<div align="right">

**[Next: Local Source →](./sources/local.md)**

</div>
