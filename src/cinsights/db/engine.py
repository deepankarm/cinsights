from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import create_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.settings import get_settings


def _async_url(database_url: str) -> str:
    """Translate a sync DB URL to its async equivalent.

    Settings store a single canonical URL (the sync form, e.g.
    ``sqlite:///cinsights.db``). The application engine is async, alembic stays
    sync; we translate at the boundary so the user never has to think about it.
    """
    if database_url.startswith("sqlite+aiosqlite://"):
        return database_url
    if database_url.startswith("sqlite://"):
        return database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


def _sync_url(database_url: str) -> str:
    """Translate an async DB URL back to sync. Used for the schema-current
    check at startup (which runs before any event loop) and by alembic.
    """
    if database_url.startswith("sqlite+aiosqlite://"):
        return database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return database_url


@lru_cache
def get_engine() -> AsyncEngine:
    """Return the application's AsyncEngine, creating it on first call.

    Also runs a one-shot synchronous schema-current check using a temporary
    sync connection, so misconfigurations fail fast at startup with an
    actionable error rather than mid-request.
    """
    settings = get_settings()
    async_url = _async_url(settings.database_url)
    is_sqlite = async_url.startswith("sqlite")

    connect_args: dict = {}
    if is_sqlite:
        # aiosqlite shares connections across coroutines; check_same_thread off
        # plus a 30s write-lock timeout matches the prior sync engine config.
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30

    engine = create_async_engine(async_url, connect_args=connect_args)

    if is_sqlite:
        # WAL + busy_timeout: same backstop as before, attached via the sync
        # event API on the underlying sync engine. SQLAlchemy's async engines
        # expose the sync engine for exactly this purpose.
        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

    # Ensure DB parent directory exists for SQLite (e.g. ~/.cinsights/)
    if is_sqlite:
        from pathlib import Path

        db_path = settings.database_url.replace("sqlite:///", "", 1)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _ensure_schema_current_sync(settings.database_url)
    return engine


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the cached AsyncSession factory bound to the application engine."""
    return async_sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


def _ensure_schema_current_sync(database_url: str) -> None:
    """Auto-migrate the DB to the latest alembic head.

    On first run, creates all tables. On upgrade, applies pending migrations.
    This runs synchronously at startup so the app is always on the latest schema.
    """
    import logging
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    log = logging.getLogger("cinsights.db")

    # Locate alembic config — either repo root (dev) or inside the installed package.
    repo_ini = Path("alembic.ini")
    pkg_dir = Path(__file__).resolve().parent.parent
    pkg_ini = pkg_dir / "alembic.ini"

    if repo_ini.exists():
        cfg = Config(str(repo_ini))
    elif pkg_ini.exists():
        cfg = Config(str(pkg_ini))
        cfg.set_main_option("script_location", str(pkg_dir / "alembic"))
    else:
        raise RuntimeError("Cannot find alembic.ini — reinstall cinsights.")

    cfg.set_main_option("sqlalchemy.url", _sync_url(database_url))

    script = ScriptDirectory.from_config(cfg)
    head_rev = script.get_current_head()

    sync_url = _sync_url(database_url)
    probe_engine = create_engine(sync_url)
    try:
        inspector = inspect(probe_engine)
        needs_migrate = True

        if inspector.has_table("alembic_version"):
            with probe_engine.connect() as conn:
                row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            current_rev = row[0] if row else None
            if current_rev == head_rev:
                needs_migrate = False

        if needs_migrate:
            from alembic import command

            log.info("Migrating database to latest schema...")
            command.upgrade(cfg, "head")
            log.info("Database migration complete.")
    finally:
        probe_engine.dispose()


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession.

    Each request gets its own session bound to the shared engine pool.
    Commits/rollbacks are the caller's responsibility — we just guarantee
    cleanup on exit.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
