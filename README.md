# cinsights

LLM-powered insights from coding agent sessions.

Analyzes Claude Code session traces from Arize Phoenix and generates actionable insights — friction points, wins, CLAUDE.md recommendations, skill proposals, and usage patterns.

## Quick Start

```bash
# Install
uv sync
cd ui && npm install

# Initialize database
cinsights init-db

# Analyze recent sessions (requires Phoenix running locally)
cinsights analyze

# Start the web UI
cinsights serve
```

## Requirements

- Python 3.11+
- Node.js 20+ (for the UI)
- [Arize Phoenix](https://github.com/Arize-ai/phoenix) running locally
- [Arize Claude Code Plugin](https://github.com/Arize-ai/arize-claude-code-plugin) configured
- `ANTHROPIC_API_KEY` environment variable set

## License

Apache-2.0
