def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "healthy"
    assert response.json()["data"]["supabase"] == "not_configured"
    assert response.json()["data"]["supabase_details"]["database"] is False
    assert response.json()["data"]["supabase_details"]["auth"] is False
    assert response.json()["data"]["supabase_details"]["storage"] is False


def test_supabase_status_requires_active_database_auth_and_storage_probes(monkeypatch):
    from app.integrations import supabase

    class FakeResponse:
        status_code = 200

    monkeypatch.setattr(supabase.settings, "supabase_url", "https://demo.supabase.co")
    monkeypatch.setattr(supabase.settings, "supabase_service_role_key", "service-role")
    monkeypatch.setattr(supabase.httpx, "get", lambda *args, **kwargs: FakeResponse())

    status = supabase.get_supabase_status()
    assert status.configured is True
    assert status.database is True
    assert status.auth is True
    assert status.storage is True


def test_protected_route_rejects_anonymous(client):
    response = client.get("/api/v1/modules")
    assert response.status_code == 401


def test_admin_can_view_all_modules(client, admin_headers):
    response = client.get("/api/v1/modules", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()["data"]) == 4


def test_demo_accounts_expose_twenty_role_based_trial_accounts(client):
    response = client.get("/api/v1/auth/demo-accounts")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["password"] == "Demo@2026!"
    assert len(payload["accounts"]) == 20
    assert {account["role"] for account in payload["accounts"]} == {
        "platform_admin",
        "recruitment_admin",
        "asset_admin",
        "department_manager",
        "approval_finance",
        "employee",
    }
    assert all("password_hash" not in account for account in payload["accounts"])


def test_trial_account_can_login_with_email_and_password(client):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "asset01@demo.local", "password": "Demo@2026!"},
    )
    assert login.status_code == 200
    assert login.json()["data"]["user"]["role"] == "asset_admin"
    token = login.json()["data"]["access_token"]
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "asset01@demo.local"


def test_trial_account_rejects_wrong_password(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "asset01@demo.local", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_product_user_cannot_view_audit(client):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "employee01@demo.local", "password": "Demo@2026!"},
    )
    token = login.json()["data"]["access_token"]
    response = client.get(
        "/api/v1/audit-logs", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_auditor_demo_role_is_not_available(client):
    response = client.post("/api/v1/auth/demo-login", json={"role": "auditor"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown demo role"


def test_demo_auth_is_disabled_outside_development(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    assert client.get("/api/v1/auth/demo-accounts").status_code == 404
    assert client.post("/api/v1/auth/demo-login", json={"role": "platform_admin"}).status_code == 404


def test_module_summary(client, admin_headers):
    response = client.get("/api/v1/modules/service-desk/summary", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["data"]["stage"] == "Available"

