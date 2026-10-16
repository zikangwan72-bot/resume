from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

APPROVAL_DB_PATH = Path(__file__).resolve().parents[2] / "approval.db"
APPROVAL_DB_URL = (
    settings.approval_database_url
    or (settings.database_url if not settings.database_url.startswith("sqlite") else "")
    or f"sqlite:///{APPROVAL_DB_PATH.as_posix()}"
)


class ApprovalBase(DeclarativeBase):
    pass


approval_engine_options = {}
if APPROVAL_DB_URL.startswith("sqlite"):
    approval_engine_options["connect_args"] = {"check_same_thread": False}
elif APPROVAL_DB_URL.startswith("postgresql+psycopg"):
    approval_engine_options["connect_args"] = {"prepare_threshold": None}

if APPROVAL_DB_URL == settings.database_url and not APPROVAL_DB_URL.startswith("sqlite"):
    # Deployment keeps both model groups in one PostgreSQL database. Sharing the
    # pool avoids opening and checking a second remote connection per request.
    from app.db.database import engine as approval_engine
else:
    approval_engine = create_engine(
        APPROVAL_DB_URL,
        pool_pre_ping=True,
        **approval_engine_options,
    )
ApprovalSessionLocal = sessionmaker(bind=approval_engine, autoflush=False, expire_on_commit=False)


def get_approval_db() -> Generator[Session, None, None]:
    db = ApprovalSessionLocal()
    try:
        yield db
    finally:
        db.close()
