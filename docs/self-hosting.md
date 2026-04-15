# Self-hosting

cinsights is designed to run on your infrastructure. Session transcripts, insights, and all derived data stay on your network.

## Data privacy

Depending on which source you use, session data can stay entirely within your control:

- **Phoenix path** - self-host Phoenix on your infrastructure. Developer traces go to your Phoenix instance, never to a third party. cinsights reads from your Phoenix.
- **Entire.io path** - checkpoints live in your git repos. cinsights reads them locally or from your git server.
- **Local path** - everything stays on the developer's machine.

cinsights itself never phones home. The only external call is to your configured LLM provider for generating insights.

## LLM provider

You choose which LLM generates the insights. cinsights supports any provider that pydantic-ai supports:

- Anthropic (default)
- OpenAI
- Google
- Any OpenAI-compatible API (self-hosted models, internal gateways)
- Ollama for local inference (no API key needed — useful for evaluation or environments without external API access)

Configure via `cinsights setup --provider <name> --model <model> --base-url <url>`. For internal gateways that require auth headers, use `--extra-headers`.

## Database

cinsights uses SQLite by default - a single `cinsights.db` file with no external dependencies. For team deployments, you can point it at PostgreSQL or any other SQL-compatible database:

```bash
export CINSIGHTS_DATABASE_URL=postgresql://user:pass@host:5432/cinsights
```

All session metadata, quality metrics, insights, and digests are stored here. The schema is managed by SQLModel (SQLAlchemy under the hood).

## Multi-tenant isolation

The `CINSIGHTS_TENANT_ID` environment variable scopes all database queries. Multiple teams or environments can share the same database without seeing each other's data.

## What's coming

- Docker Compose setup for running cinsights + Phoenix together
- Helm chart for Kubernetes deployments
- Setup guide for connecting teams to a shared Phoenix instance

---

**[← Previous: Phoenix Source](./sources/phoenix.md)**
