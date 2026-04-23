"""Tests that alembic migrations work correctly for pip-installed users."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text


@pytest.fixture
def fresh_db(tmp_path):
    """Return a sqlite URL pointing to a non-existent DB file."""
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def migrated_db(fresh_db):
    """Return a sqlite URL after running migrations."""
    from cinsights.db.engine import _ensure_schema_current_sync

    _ensure_schema_current_sync(fresh_db)
    return fresh_db


def test_auto_migrate_creates_all_tables(migrated_db):
    """First run on empty DB should create all tables via alembic."""
    engine = create_engine(migrated_db)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    expected = {
        "alembic_version",
        "coding_session",
        "tool_call",
        "insight",
        "session_daily_trend",
        "session_baseline",
        "digest",
        "digest_section",
        "scope_stats",
        "llm_call_log",
        "refresh_run",
    }
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


def test_auto_migrate_is_idempotent(migrated_db):
    """Running migrate on an already-current DB should be a no-op."""
    from cinsights.db.engine import _ensure_schema_current_sync

    # Run again — should not raise or change anything
    _ensure_schema_current_sync(migrated_db)

    engine = create_engine(migrated_db)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar()
    engine.dispose()
    assert rows == 1


def test_alembic_head_matches_models(tmp_path):
    """Detect drift between SQLModel models and the alembic migration head.

    Migrates a fresh DB to head, then diffs against current models. If the
    diff is non-empty, someone changed a model without creating a migration.
    """
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from sqlmodel import SQLModel

    # Import all models so metadata is populated
    from cinsights.db.models import (  # noqa: F401
        CodingSession,
        Digest,
        DigestSection,
        Insight,
        RefreshRun,
        ToolCall,
    )

    db_url = f"sqlite:///{tmp_path / 'drift.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.attributes["_cinsights_url_set"] = True
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        mc = MigrationContext.configure(conn)
        diffs = compare_metadata(mc, SQLModel.metadata)
    engine.dispose()

    assert diffs == [], f"Models out of sync with migrations:\n{diffs}"


def test_package_includes_alembic_files():
    """alembic.ini and versions/ must exist in the installed package."""
    import cinsights

    pkg_dir = Path(cinsights.__file__).parent
    alembic_dir = pkg_dir / "alembic"
    versions_dir = alembic_dir / "versions"

    assert alembic_dir.exists(), f"alembic/ not found in {pkg_dir}"
    assert (alembic_dir / "env.py").exists(), "alembic/env.py missing"
    assert versions_dir.exists(), "alembic/versions/ missing"

    migrations = [m for m in versions_dir.glob("*.py") if m.name != "__init__.py"]
    assert len(migrations) >= 1, "No migration files found"


def test_static_files_findable():
    """Static UI files must be findable — either ui/build (dev) or package/static (pip).

    Skipped on CI where ui/build hasn't been built yet.
    """
    import cinsights

    pkg_dir = Path(cinsights.__file__).parent
    dev_static = pkg_dir.parent.parent / "ui" / "build"
    pip_static = pkg_dir / "static"

    if not dev_static.is_dir() and not pip_static.is_dir():
        pytest.skip("UI not built (run 'cd ui && npm run build' or install via pip)")

    static = dev_static if dev_static.is_dir() else pip_static
    assert (static / "index.html").exists(), "index.html missing from static dir"
    assert (static / "_app").is_dir(), "_app/ missing from static dir"


def test_package_alembic_ini_exists():
    """alembic.ini must be findable — either repo root or package dir."""
    import cinsights

    pkg_dir = Path(cinsights.__file__).parent
    assert Path("alembic.ini").exists() or (pkg_dir / "alembic.ini").exists()
