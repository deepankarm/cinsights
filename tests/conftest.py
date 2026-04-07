import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# Force test settings before any app imports
os.environ["CINSIGHTS_DATABASE_URL"] = "sqlite://"
os.environ["CINSIGHTS_PHOENIX_ENDPOINT"] = "http://localhost:6006"
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture
def db_engine():
    # StaticPool ensures all connections share the same in-memory database
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(db_engine):
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def client(db_engine):
    from cinsights.api.sessions import router as sessions_router
    from cinsights.db.engine import get_db

    @asynccontextmanager
    async def noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.include_router(sessions_router)

    def override_get_db():
        with Session(db_engine) as session:
            yield session

    test_app.dependency_overrides[get_db] = override_get_db

    with TestClient(test_app) as c:
        yield c
