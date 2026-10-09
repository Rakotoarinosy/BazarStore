"""Connexion à la base : engine, fabrique de sessions, Base déclarative et dépendance `get_db`."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.infrastructure.config import get_settings


class Base(DeclarativeBase):
    """Base commune à tous les modèles SQLAlchemy (voir models.py)."""


def create_db_engine(database_url: str) -> Engine:
    # SQLite interdit par défaut l'usage d'une connexion depuis un autre thread (FastAPI en utilise).
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}

    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)

    if database_url.startswith("sqlite"):
        # SQLite n'applique pas les clés étrangères (ni ON DELETE) sans ce PRAGMA, contrairement à PostgreSQL.
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = create_db_engine(get_settings().database_url)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête, toujours fermée à la fin."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> sessionmaker[Session]:
    """Dépendance FastAPI pour les traitements longs (flux SSE) qui ouvrent leurs propres sessions."""
    return SessionLocal
