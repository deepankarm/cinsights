from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from cinsights.api.sessions import router as sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from cinsights.db.engine import init_db

    init_db()
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

# Mount static files last (catch-all for SvelteKit SPA)
_static_dir = Path(__file__).parent.parent.parent / "ui" / "build"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="ui")
