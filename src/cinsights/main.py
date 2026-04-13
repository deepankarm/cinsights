from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from cinsights.api.digest import router as digest_router
from cinsights.api.projects import router as projects_router
from cinsights.api.sessions import router as sessions_router
from cinsights.api.stats import router as stats_router
from cinsights.api.trends import router as trends_router
from cinsights.api.users import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from cinsights.db.engine import get_engine

    # Force engine creation so SQLModel.metadata.create_all runs at startup.
    get_engine()
    yield


app = FastAPI(
    title="cinsights",
    version="0.1.0",
    description="LLM-powered insights from coding agent sessions",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # SvelteKit dev server
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router)
app.include_router(digest_router)
app.include_router(stats_router)
app.include_router(projects_router)
app.include_router(trends_router)
app.include_router(users_router)

# Serve SvelteKit SPA static files with proper fallback for client-side routing
_static_dir = Path(__file__).parent.parent.parent / "ui" / "build"
if _static_dir.is_dir():
    # Mount _app directory for immutable assets
    app.mount(
        "/_app",
        StaticFiles(directory=str(_static_dir / "_app")),
        name="svelte-app",
    )

    _index_html = _static_dir / "index.html"

    @app.get("/{path:path}")
    async def spa_fallback(request: Request, path: str):
        """Serve static files or fall back to index.html for SPA routing."""
        file_path = _static_dir / path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_index_html)
