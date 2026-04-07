from functools import lru_cache

from sqlmodel import Session, SQLModel, create_engine

from cinsights.config import get_settings


@lru_cache
def get_engine():
    settings = get_settings()
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(settings.database_url, connect_args=connect_args)


def init_db():
    SQLModel.metadata.create_all(get_engine())


def get_db():
    with Session(get_engine()) as session:
        yield session
