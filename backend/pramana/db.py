from collections.abc import Iterator
import time
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_sqlite = _settings.db_url.startswith("sqlite")

# SQLite needs cross-thread connections and a busy timeout; PostgreSQL gets an enterprise-ready checked pool
if _sqlite:
    engine = create_engine(
        _settings.db_url,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=False,
    )
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
else:
    engine = create_engine(
        _settings.db_url,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health(db: Session | None = None) -> dict[str, Any]:
    """Evaluates database connectivity, latency, and dialect health."""
    start_time = time.perf_counter()
    session_provided = db is not None
    session = db or SessionLocal()
    try:
        session.execute(text("SELECT 1")).scalar()
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        dialect_name = engine.dialect.name
        return {
            "status": "HEALTHY",
            "dialect": dialect_name,
            "latency_ms": elapsed_ms,
            "is_sqlite": dialect_name == "sqlite",
            "is_postgres": dialect_name in ("postgresql", "postgres"),
            "connected": True,
        }
    except Exception as err:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "UNHEALTHY",
            "dialect": engine.dialect.name,
            "latency_ms": elapsed_ms,
            "connected": False,
            "error": str(err),
        }
    finally:
        if not session_provided:
            session.close()


def init_db() -> None:
    from . import models  # noqa: F401  registers tables
    from .conversation import models as _conversation  # noqa: F401
    from .handoff import models as _handoff  # noqa: F401
    from .history import models as _history  # noqa: F401
    from .offline import models as _offline  # noqa: F401
    from .trust import models as _trust  # noqa: F401
    from .distributed import models as _distributed  # noqa: F401
    from .integrations import models as _integrations  # noqa: F401

    Base.metadata.create_all(engine)


def drop_all() -> None:
    """Remove every table; the seed script uses it on a database server, where there is no file to delete."""
    from . import models  # noqa: F401  registers tables
    from .conversation import models as _conversation  # noqa: F401
    from .handoff import models as _handoff  # noqa: F401
    from .history import models as _history  # noqa: F401
    from .offline import models as _offline  # noqa: F401
    from .trust import models as _trust  # noqa: F401
    from .distributed import models as _distributed  # noqa: F401
    from .integrations import models as _integrations  # noqa: F401

    Base.metadata.drop_all(engine)

