from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cinsights.settings import SourceType

if TYPE_CHECKING:
    from cinsights.settings import Settings


def create_source(settings: Settings):
    """Create a trace source based on settings.source."""
    match settings.source:
        case SourceType.ENTIREIO:
            from cinsights.sources.entireio import EntireioSource

            if not settings.entireio_repo_path:
                raise ValueError(
                    "Repo path required for entireio source. "
                    "Use --repo /path/to/repo or set CINSIGHTS_ENTIREIO_REPO_PATH"
                )
            return EntireioSource(
                repo_path=Path(settings.entireio_repo_path),
                branch=settings.entireio_branch,
            )

        case SourceType.LOCAL:
            from cinsights.sources.local import LocalSource

            cc_homes, codex_homes = _resolve_local_homes(settings)
            return LocalSource(claude_code_homes=cc_homes, codex_homes=codex_homes)

        case SourceType.PHOENIX:
            from cinsights.sources.phoenix import PhoenixSource

            return PhoenixSource(
                base_url=settings.phoenix_endpoint,
                project=settings.phoenix_project,
            )


def _resolve_local_homes(settings: Settings) -> tuple[list[Path], list[Path]]:
    """Resolve agent-specific home directories from ~/.cinsights/config.json.

    Returns (claude_code_homes, codex_homes) where each home is a base
    directory (e.g. ~/.claude-personal). The source appends /projects or
    /sessions as needed.
    """
    from cinsights.settings import get_config

    config = get_config()
    return config.resolved_claude_code_homes, config.resolved_codex_homes
