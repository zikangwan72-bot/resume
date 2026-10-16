import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings, settings
from app.db.database import SessionLocal
from app.db.models import User
from app.main import app


@pytest.mark.parametrize(
    ("app_env", "seed_demo", "expected"),
    [
        ("development", None, True),
        ("test", None, True),
        ("production", None, False),
        ("staging", None, False),
        ("development", False, False),
        ("production", True, True),
    ],
)
def test_should_seed_demo(app_env, seed_demo, expected):
    assert Settings(app_env=app_env, seed_demo=seed_demo).should_seed_demo is expected


def _mark_admin(value: str) -> None:
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@demo.local"))
        admin.display_name = value
        db.commit()


def _admin_name() -> str:
    with SessionLocal() as db:
        return db.scalar(select(User.display_name).where(User.email == "admin@demo.local"))


def test_startup_skips_demo_seed_when_disabled(monkeypatch):
    _mark_admin("edited by user")
    monkeypatch.setattr(settings, "seed_demo", False)
    with TestClient(app):
        pass
    assert _admin_name() == "edited by user"


def test_startup_reseeds_demo_users_when_enabled(monkeypatch):
    _mark_admin("edited by user")
    monkeypatch.setattr(settings, "seed_demo", True)
    with TestClient(app):
        pass
    assert _admin_name() != "edited by user"
