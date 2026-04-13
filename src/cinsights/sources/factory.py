from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cinsights.settings import SourceType

if TYPE_CHECKING:
    from cinsights.settings import Settings


def create_source(settings: Settings):
    """Create a trace source based on settings.source."""
    if settings.source == SourceType.ENTIREIO:
        from cinsights.sources.entireio import EntireioSource

        if not settings.entireio_repo_path:
            raise ValueError(
                "CINSIGHTS_ENTIREIO_REPO_PATH is required when source=entireio"
            )
        return EntireioSource(
            repo_path=Path(settings.entireio_repo_path),
            branch=settings.entireio_branch,
        )

    from cinsights.sources.phoenix import PhoenixSource

    return PhoenixSource(
        base_url=settings.phoenix_endpoint,
        project=settings.phoenix_project,
    )
