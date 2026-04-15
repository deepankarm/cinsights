# Configuration

Start with defaults. The only thing you need to set on day one is your API key.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | - | Anthropic API key (required for default LLM config; not needed with Ollama) |
| `CINSIGHTS_SOURCE` | `phoenix` | Data source: `phoenix`, `local`, or `entireio` |
| `CINSIGHTS_DATABASE_URL` | `sqlite:///cinsights.db` | Database connection string |
| `CINSIGHTS_BUDGET_MODE` | `balanced` | Scoring budget: `frugal`, `balanced`, `thorough`, `all` |
| `CINSIGHTS_COLD_START_SESSIONS` | `10` | Always analyze first N sessions per (user, project) |
| `CINSIGHTS_MIN_SESSION_TOOL_COUNT` | `10` | Minimum tool calls to include session in digest evidence |
| `CINSIGHTS_PHOENIX_ENDPOINT` | `http://localhost:6006` | Phoenix API URL |
| `CINSIGHTS_PHOENIX_PROJECT` | `claude-code` | Phoenix project name |
| `CINSIGHTS_ENTIREIO_REPO_PATH` | - | Path to git repo with Entire.io checkpoints |
| `CINSIGHTS_ENTIREIO_BRANCH` | `entire/checkpoints/v1` | Checkpoint branch name |
| `CINSIGHTS_HOST` | `127.0.0.1` | Web server bind address |
| `CINSIGHTS_PORT` | `8100` | Web server port |
| `CINSIGHTS_TENANT_ID` | `default` | Multi-tenant isolation ID |

You can also set these in a `.env` file in the project root.

## Config file

`~/.cinsights/config.json` controls the LLM provider, session directories, and prompt limits.

```json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-haiku-4-5-20251001",
    "base_url": null,
    "extra_headers": {},
    "use_json_schema_mode": false
  },
  "claude_code_homes": ["~/.claude"],
  "codex_homes": ["~/.codex"],
  "limits": {
    "max_timeline_spans": 200,
    "timeline_head_tail": 30,
    "max_digest_session_summaries": 30,
    "max_digest_session_health": 50,
    "small_project_threshold": 5,
    "min_coverage_per_user_project": 2,
    "min_coverage_per_project": 3
  }
}
```

Ollama example:

```json
{
  "llm": {
    "provider": "openai",
    "model": "qwen2.5:14b",
    "base_url": "http://localhost:11434/v1"
  }
}
```

**`llm`** - Provider and model. Uses pydantic-ai's `provider:model` namespace, so any provider that pydantic-ai supports works. API keys come from environment variables, never stored here. When `base_url` points to localhost, cinsights auto-detects it as a local model and uses Ollama-compatible structured output. Set `use_json_schema_mode: true` explicitly for non-localhost endpoints that need the same treatment (e.g. a remote Ollama instance).

**`claude_code_homes` / `codex_homes`** - Directories to scan when using the [local source](sources/local.md).

**`limits`** - Context window and coverage tuning. Defaults are sized for Haiku-class models. Increase `max_timeline_spans` if using a model with a larger context window.

## LLM provider setup

Interactive (prompts for each value):

```bash
cinsights setup
```

One-shot:

```bash
cinsights setup --provider anthropic --model claude-haiku-4-5-20251001
```

Validate current config:

```bash
cinsights setup --validate
```

Any provider that pydantic-ai supports works - Anthropic, OpenAI, Google, etc. For custom gateways or proxies, use `--base-url` and `--extra-headers`.

For Ollama:

```bash
cinsights setup --provider openai --model qwen2.5:14b --base-url http://localhost:11434/v1
```

Recommended local models: `qwen2.5:14b` (best quality, needs ~16GB RAM) or `qwen2.5:7b` (faster, ~8GB RAM).

## CLI reference

| Command | Description | Key flags |
|---------|-------------|-----------|
| `cinsights index` | Discover sessions, compute metrics, score. Zero LLM cost. | `--hours 24`, `--limit 50`, `--force`, `--source`, `--repo` |
| `cinsights score` | Re-score existing sessions, show distribution. | `--user`, `--project`, `--min-score` |
| `cinsights analyze` | LLM-analyze scored sessions above threshold. | `--limit 50`, `--force`, `--concurrency 5`, `--min-score`, `--source`, `--repo` |
| `cinsights digest` | Generate cross-session report for a project or user. | `project <name>` or `user <id>`, `--days 7`, `--stats-only` |
| `cinsights refresh` | Index + analyze in one shot. | `--hours 24`, `--days 7`, `--limit 50`, `--min-score 0.4`, `--source`, `--repo` |
| `cinsights serve` | Start the web server. | `--host`, `--port` |
| `cinsights setup` | Configure LLM provider. | `--provider`, `--model`, `--base-url`, `--validate` |

Makefile shortcuts: `make index`, `make analyze`, `make refresh`, `make index-local`, `make refresh-entireio REPO=/path`, etc. Run `make help` for the full list.

## Running on a schedule

cinsights works well as a cron job. Example - refresh daily at 9am, then generate digests:

```bash
# Index + analyze last 24h of sessions
0 9 * * * cd /path/to/cinsights && cinsights refresh --hours 24

# Generate project digest (run after refresh)
5 9 * * * cd /path/to/cinsights && cinsights digest project my-app --days 30
```

---

**[← Previous: Concepts](./concepts.md)**

<div align="right">

**[Next: Local Source →](./sources/local.md)**

</div>
