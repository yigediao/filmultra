from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import get_settings


settings = get_settings()


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return

    raw_path = database_url[len(prefix) :]
    if raw_path in {"", ":memory:"}:
        return

    Path(raw_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent_dir(settings.database_url)
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
