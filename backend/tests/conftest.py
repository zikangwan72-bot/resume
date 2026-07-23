import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_enterprise_ai.db"
os.environ["APPROVAL_DATABASE_URL"] = "sqlite:///./test_approval.db"
os.environ["JWT_SECRET"] = "test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.approval.database import ApprovalBase, ApprovalSessionLocal, approval_engine
from app.approval.seed import initialize_approval_db
from app.db.database import Base, engine
from app.db.seed import initialize_database
from app.main import app


@pytest.fixture(autouse=True)
def database():
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    ApprovalBase.metadata.drop_all(bind=approval_engine)
    initialize_database()
    initialize_approval_db()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    ApprovalBase.metadata.drop_all(bind=approval_engine)


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin_headers(client):
    response = client.post("/api/v1/auth/demo-login", json={"role": "platform_admin"})
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def db_session():
    with ApprovalSessionLocal() as db:
        yield db
