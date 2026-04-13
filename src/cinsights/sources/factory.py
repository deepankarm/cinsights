from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cinsights.settings import SourceType

if TYPE_CHECKING:
    from cinsights.settings import Settings


_DEFAULT_LOCAL_PATHS = [
    Path.home() / ".claude" / "projects",
    Path.home() / ".codex" / "sessions",
]


def create_source(settings: Settings):
    """Create a trace source based on settings.source."""
    if settings.source == SourceType.ENTIREIO:
        from cinsights.sources.entireio import EntireioSource

        if not settings.entireio_repo_path:
            raise ValueError("CINSIGHTS_ENTIREIO_REPO_PATH is required when source=entireio")
        return EntireioSource(
            repo_path=Path(settings.entireio_repo_path),
            branch=settings.entireio_branch,
        )

    if settings.source == SourceType.LOCAL:
        from cinsights.sources.local import LocalSource

        paths = _resolve_local_paths(settings)
        return LocalSource(paths=paths)

    from cinsights.sources.phoenix import PhoenixSource

    return PhoenixSource(
        base_url=settings.phoenix_endpoint,
        project=settings.phoenix_project,
    )


def _resolve_local_paths(settings: Settings) -> list[Path]:
    if settings.local_paths:
        return [Path(p.strip()).expanduser() for p in settings.local_paths.split(",") if p.strip()]
    return [p for p in _DEFAULT_LOCAL_PATHS if p.is_dir()]
