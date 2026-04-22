# How it works

What data does cinsights read, what gets sent to an LLM, and what stays local.

## The short version

cinsights reads coding agent session files (JSONL conversation logs from Claude Code, Codex, Cursor). It extracts tool call sequences and computes quality metrics locally — no LLM needed. Then, for sessions worth a closer look, it sends a **compressed summary** (not the full transcript) to an LLM for insight extraction. Your code, file contents, and full conversation history never leave your machine unless you choose to analyze that session.

## What stays local (zero cost)

**Indexing** parses session files and computes everything from tool call metadata alone:

- Tool call counts and sequences (Read, Edit, Bash, Grep, etc.)
- Success/failure rates
- Timing (duration, turns, tokens)
- Quality metrics (read:edit ratio, error rate, context pressure, etc.)
- Interestingness scoring against the developer's baseline

This runs on your machine. No network calls. No tokens. You can index thousands of sessions for free.

## What gets sent to the LLM (costs tokens)

**Analysis** sends a compressed representation of each session. Here's exactly what the LLM sees:

### Per-session analysis prompt

| Section | What's included | Truncation |
|---------|----------------|------------|
| **Header** | Model name, duration, tool call count, error count, total tokens | None |
| **Quality metrics** | Pre-computed metrics with benchmark values | None |
| **Tool distribution** | Tool names and counts, sorted by frequency | None |
| **Turn exchanges** | Developer queries (first 200 chars each) and agent responses | Responses truncated to ~300 chars. Skipped entirely for non-error turns when session has >20 turns. |
| **Timeline** | Chronological tool calls with timestamps, durations, success/error | Max **75 spans** sampled. Tool input/output truncated to **500 chars** each. |

### What's NOT sent

- Full file contents (only tool call names and truncated I/O)
- Your source code
- Full conversation transcripts
- Git diffs or commit history
- Environment variables or secrets

### How spans are sampled

Sessions can have hundreds of tool calls. cinsights samples up to 75 spans using this priority:

1. **All error spans** — every failed tool call is always included
2. **First 15 spans** — session start (setup, initial reads)
3. **Last 15 spans** — session end (final edits, verification)
4. **Stratified sample** — remaining successful spans up to the 75 limit

This ensures the LLM sees friction (errors), context (start), outcomes (end), and a representative middle — without sending everything.

### Digest prompt

The digest aggregates multiple analyzed sessions. It sends:

- Pre-computed quality metrics (aggregated across sessions)
- Session summaries from prior analysis (up to 30 sessions)
- Session health entries (up to 50 sessions)
- Weekly quality trends

Three concurrent LLM calls produce the narrative, actions, and forward-looking sections.

## Which sessions get analyzed?

Not every session is worth spending tokens on. cinsights scores each session on "interestingness" — how much it deviates from that developer's baseline.

**Scoring signals** (11 weighted factors):

| Signal | Weight | What it catches |
|--------|--------|----------------|
| Error rate deviation | 15% | Sessions with unusually high failures |
| New project / cold start | 15% | First sessions in a project (no baseline yet) |
| Read:Edit ratio drop | 10% | Agent editing without researching first |
| Blind edit rate deviation | 10% | Files edited without being read |
| Repeated edits / thrashing | 10% | Same file edited 5+ times in a row |
| New agent type | 10% | Developer switching to an unfamiliar agent |
| Turn count deviation | 7% | Unusually long or short sessions |
| Duration deviation | 7% | Sessions that took much longer than typical |
| Context pressure | 6% | Prompt size growing rapidly (context stuffing) |
| Research:mutation ratio drop | 5% | Low research relative to mutations |
| Session abandonment | 5% | Long duration but few turns (developer gave up) |

Routine sessions score 0.2-0.4. Interesting ones land at 0.6+.

**Budget modes** control the threshold:

| Mode | What gets analyzed | Typical cost |
|------|-------------------|-------------|
| `frugal` | Top ~10% only | ~$0.02-0.05 per refresh |
| `balanced` (default) | Score >= 0.4 | ~$0.10-0.30 per refresh |
| `thorough` | Top ~50% | ~$0.50-1.00 per refresh |
| `all` | Everything | Varies by session count |

Cost estimates assume Gemini Flash Lite and ~50 sessions per refresh.

**Cold start**: The first 10 sessions per (developer, project) pair are always analyzed regardless of score, because there's no baseline yet.

## Cost breakdown by operation

| Operation | LLM calls | Typical cost | When to run |
|-----------|-----------|-------------|-------------|
| `index` | 0 | Free | As often as you want |
| `analyze` (50 sessions, balanced) | 10-20 | $0.10-0.30 | Daily or after significant work |
| `digest` (1 project, 30 days) | 3 concurrent | $0.05-0.15 | Weekly or on-demand |
| `refresh` (index + analyze) | Same as analyze | Same as analyze | Daily cron |

All costs assume Gemini Flash Lite. Using Ollama makes everything free (but slower — a digest takes ~2-3 minutes vs seconds).

## Data flow diagram

```
Session files (JSONL)
    │
    ▼
┌─────────┐
│  Index   │  Local only. Parses tool calls, computes metrics, scores sessions.
│  (free)  │  Stores: session metadata, quality metrics, interestingness score.
└────┬─────┘
     │ Sessions above score threshold
     ▼
┌──────────┐
│ Analyze  │  Sends compressed summary to LLM (75 sampled spans, truncated I/O).
│ (tokens) │  Stores: friction, wins, recommendations, patterns, mood quotes.
└────┬─────┘
     │ Analyzed sessions grouped by project or developer
     ▼
┌──────────┐
│  Digest  │  Sends aggregated summaries to LLM (3 concurrent calls).
│ (tokens) │  Stores: narrative, actions, forward-looking report.
└──────────┘
     │
     ▼
┌──────────┐
│  Serve   │  Web UI at localhost:8100. Reads from local SQLite database.
│  (free)  │  Nothing leaves your machine.
└──────────┘
```

## Configuring limits

All truncation limits are configurable in `~/.cinsights/config.json`:

```json
{
  "limits": {
    "max_timeline_spans": 75,
    "timeline_head_tail": 15,
    "max_digest_session_summaries": 30,
    "max_digest_session_health": 50
  }
}
```

Increase these if using a model with a larger context window.

---

**[← Previous: Concepts](./concepts.md)**

<div align="right">

**[Next: Configuration →](./configuration.md)**

</div>
