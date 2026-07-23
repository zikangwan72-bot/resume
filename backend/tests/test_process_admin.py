from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.approval.database import ApprovalSessionLocal, approval_engine, get_approval_db
from app.approval.models import ApprovalRequest, ApprovalUser, ProcessApp, ProcessVersion
from app.main import app


@pytest.fixture
def valid_definition() -> dict:
    code = f"travel-{uuid4().hex[:8]}"
    return {
        "code": code,
        "name": "差旅申请",
        "category": "行政审批",
        "description": "员工差旅申请",
        "form_schema": {
            "fields": [
                {"id": "amount", "label": "预算金额", "type": "money"},
                {"id": "reason", "label": "出差事由", "type": "textarea"},
            ]
        },
        "flow_schema": {
            "nodes": [
                {"id": "start", "type": "start"},
                {
                    "id": "manager",
                    "type": "approval",
                    "approval_type": "single",
                    "approver_id": "22222222-2222-2222-2222-222222222222",
                },
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"source": "start", "target": "manager"},
                {"source": "manager", "target": "end"},
            ],
        },
    }


def _create_process_app(client, admin_headers, definition: dict) -> dict:
    response = client.post("/api/v1/admin/process-apps", headers=admin_headers, json=definition)

    assert response.status_code == 201
    return response.json()["data"]


def test_seed_creates_three_published_process_apps(db_session):
    apps = db_session.scalars(select(ProcessApp)).all()
    assert {app.code for app in apps} == {"expense", "leave", "purchase"}
    assert len(apps) == 3
    assert all(app.status == "published" for app in apps)
    assert all(app.current_version_id for app in apps)
    versions = {version.id: version for version in db_session.scalars(select(ProcessVersion)).all()}
    assert all(
        (version := versions[app.current_version_id]).process_app_id == app.id
        and version.version_number == 1
        and version.status == "published"
        for app in apps
    )
    assert all(
        all(field["id"].strip() for field in version.form_schema["fields"])
        and all(node["id"].strip() for node in version.flow_schema["nodes"])
        for version in versions.values()
    )


def test_seed_users_have_required_positions(db_session):
    users = db_session.scalars(select(ApprovalUser)).all()
    assert users
    assert all(user.position.strip() for user in users)


def test_legacy_type_id_is_nullable_for_process_app_requests():
    assert ApprovalRequest.__table__.c.type_id.nullable


def test_request_idempotency_key_is_unique_per_applicant():
    unique_constraints = inspect(approval_engine).get_unique_constraints("approval_requests")
    assert any(
        constraint["column_names"] == ["applicant_id", "idempotency_key"]
        for constraint in unique_constraints
    )


def test_admin_process_app_routes_require_an_approval_manager(client):
    anonymous = client.get("/api/v1/admin/process-apps")
    assert anonymous.status_code == 401

    login = client.post("/api/v1/auth/demo-login", json={"role": "product_demo_user"})
    response = client.get(
        "/api/v1/admin/process-apps",
        headers={"Authorization": f"Bearer {login.json()['data']['access_token']}"},
    )
    assert response.status_code == 403


def test_admin_creates_draft_and_publishes_version(client, admin_headers, valid_definition):
    created = _create_process_app(client, admin_headers, valid_definition)
    assert created["status"] == "draft"
    assert created["version_number"] == 1

    published = client.post(
        f"/api/v1/admin/process-apps/{created['id']}/publish", headers=admin_headers
    )
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "published"
    assert published.json()["data"]["version_number"] == 1


def test_publishing_returns_exact_structured_definition_validation_error(
    client, admin_headers, valid_definition
):
    invalid_definition = deepcopy(valid_definition)
    invalid_definition["flow_schema"]["nodes"][1]["approver_id"] = "inactive-user"
    created = _create_process_app(client, admin_headers, invalid_definition)

    response = client.post(
        f"/api/v1/admin/process-apps/{created['id']}/publish", headers=admin_headers
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "definition_invalid",
            "errors": [
                {
                    "code": "inactive_approver",
                    "message": "审批人必须是启用员工",
                    "target_id": "manager",
                }
            ],
        }
    }


def test_editing_a_published_app_creates_an_isolated_next_draft_version(
    client, admin_headers, db_session, valid_definition
):
    created = _create_process_app(client, admin_headers, valid_definition)
    app_id = created["id"]
    client.post(f"/api/v1/admin/process-apps/{app_id}/publish", headers=admin_headers)

    update = {
        "name": "差旅申请（修订版）",
        "form_schema": {
            "fields": [
                *valid_definition["form_schema"]["fields"],
                {"id": "destination", "label": "目的地", "type": "text"},
            ]
        },
    }
    response = client.put(
        f"/api/v1/admin/process-apps/{app_id}", headers=admin_headers, json=update
    )

    assert response.status_code == 200
    assert response.json()["data"]["version_number"] == 2
    assert response.json()["data"]["version_status"] == "draft"

    versions = db_session.scalars(
        select(ProcessVersion)
        .where(ProcessVersion.process_app_id == app_id)
        .order_by(ProcessVersion.version_number)
    ).all()
    assert [(version.version_number, version.status) for version in versions] == [
        (1, "published"),
        (2, "draft"),
    ]
    assert [field["id"] for field in versions[0].form_schema["fields"]] == ["amount", "reason"]
    assert [field["id"] for field in versions[1].form_schema["fields"]] == [
        "amount",
        "reason",
        "destination",
    ]


def test_copy_creates_uniquely_coded_draft_apps(client, admin_headers, valid_definition):
    created = _create_process_app(client, admin_headers, valid_definition)

    first_copy = client.post(
        f"/api/v1/admin/process-apps/{created['id']}/copy", headers=admin_headers
    )
    second_copy = client.post(
        f"/api/v1/admin/process-apps/{created['id']}/copy", headers=admin_headers
    )

    assert first_copy.status_code == 201
    assert second_copy.status_code == 201
    assert first_copy.json()["data"]["status"] == "draft"
    assert first_copy.json()["data"]["code"].startswith(f"{valid_definition['code']}-copy")
    assert first_copy.json()["data"]["code"] != second_copy.json()["data"]["code"]


def test_deactivation_changes_only_the_process_app_status(
    client, admin_headers, db_session, valid_definition
):
    created = _create_process_app(client, admin_headers, valid_definition)
    app_id = created["id"]
    client.post(f"/api/v1/admin/process-apps/{app_id}/publish", headers=admin_headers)
    before = db_session.get(ProcessApp, app_id)
    version_id = before.current_version_id

    response = client.post(f"/api/v1/admin/process-apps/{app_id}/deactivate", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "inactive"
    db_session.expire_all()
    app = db_session.get(ProcessApp, app_id)
    version = db_session.get(ProcessVersion, version_id)
    assert app.current_version_id == version_id
    assert version.status == "published"


def test_editing_an_inactive_app_creates_draft_v2_and_preserves_v1_after_republish(
    client, admin_headers, db_session, valid_definition
):
    created = _create_process_app(client, admin_headers, valid_definition)
    app_id = created["id"]
    client.post(f"/api/v1/admin/process-apps/{app_id}/publish", headers=admin_headers)
    published_v1 = db_session.get(ProcessVersion, created["version_id"])
    v1_form_schema = deepcopy(published_v1.form_schema)
    v1_flow_schema = deepcopy(published_v1.flow_schema)

    deactivated = client.post(
        f"/api/v1/admin/process-apps/{app_id}/deactivate", headers=admin_headers
    )
    assert deactivated.status_code == 200

    updated = client.put(
        f"/api/v1/admin/process-apps/{app_id}",
        headers=admin_headers,
        json={
            "form_schema": {
                "fields": [
                    *valid_definition["form_schema"]["fields"],
                    {"id": "destination", "label": "目的地", "type": "text"},
                ]
            }
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["version_number"] == 2
    assert updated.json()["data"]["version_status"] == "draft"

    republished = client.post(
        f"/api/v1/admin/process-apps/{app_id}/publish", headers=admin_headers
    )
    assert republished.status_code == 200
    assert republished.json()["data"]["version_number"] == 2
    assert republished.json()["data"]["status"] == "published"

    db_session.expire_all()
    versions = db_session.scalars(
        select(ProcessVersion)
        .where(ProcessVersion.process_app_id == app_id)
        .order_by(ProcessVersion.version_number)
    ).all()
    assert [(version.version_number, version.status) for version in versions] == [
        (1, "published"),
        (2, "published"),
    ]
    assert versions[0].form_schema == v1_form_schema
    assert versions[0].flow_schema == v1_flow_schema
    assert [field["id"] for field in versions[1].form_schema["fields"]] == [
        "amount",
        "reason",
        "destination",
    ]


def test_process_admin_database_constraints_are_declared():
    constraints = inspect(approval_engine).get_unique_constraints("approval_users")
    assert any(constraint["column_names"] == ["email"] for constraint in constraints)

    version_constraints = inspect(approval_engine).get_unique_constraints("process_versions")
    assert any(
        constraint["column_names"] == ["process_app_id", "version_number"]
        for constraint in version_constraints
    )


def test_process_app_create_race_returns_409_and_rolls_back(
    client, admin_headers, monkeypatch, valid_definition
):
    with ApprovalSessionLocal() as db:
        rollback_called = False
        original_rollback = db.rollback

        def failing_commit() -> None:
            raise IntegrityError("INSERT", {}, Exception("unique constraint failed"))

        def recording_rollback() -> None:
            nonlocal rollback_called
            rollback_called = True
            original_rollback()

        monkeypatch.setattr(db, "commit", failing_commit)
        monkeypatch.setattr(db, "rollback", recording_rollback)
        app.dependency_overrides[get_approval_db] = lambda: db
        try:
            response = client.post(
                "/api/v1/admin/process-apps", headers=admin_headers, json=valid_definition
            )
        finally:
            app.dependency_overrides.pop(get_approval_db, None)

        assert response.status_code == 409
        assert rollback_called
        assert db.scalar(select(ProcessApp.id).limit(1)) is not None


def test_process_app_copy_race_returns_409_and_rolls_back(
    client, admin_headers, monkeypatch, valid_definition
):
    created = _create_process_app(client, admin_headers, valid_definition)

    with ApprovalSessionLocal() as db:
        rollback_called = False
        original_rollback = db.rollback

        def failing_commit() -> None:
            raise IntegrityError("INSERT", {}, Exception("unique constraint failed"))

        def recording_rollback() -> None:
            nonlocal rollback_called
            rollback_called = True
            original_rollback()

        monkeypatch.setattr(db, "commit", failing_commit)
        monkeypatch.setattr(db, "rollback", recording_rollback)
        app.dependency_overrides[get_approval_db] = lambda: db
        try:
            response = client.post(
                f"/api/v1/admin/process-apps/{created['id']}/copy", headers=admin_headers
            )
        finally:
            app.dependency_overrides.pop(get_approval_db, None)

        assert response.status_code == 409
        assert rollback_called
        assert db.scalar(select(ProcessApp.id).limit(1)) is not None


def test_next_process_version_conflict_returns_409_and_rolls_back(
    client, admin_headers, monkeypatch, valid_definition
):
    created = _create_process_app(client, admin_headers, valid_definition)
    app_id = created["id"]
    client.post(f"/api/v1/admin/process-apps/{app_id}/publish", headers=admin_headers)

    with ApprovalSessionLocal() as db:
        rollback_called = False
        original_rollback = db.rollback

        def failing_commit() -> None:
            raise IntegrityError("INSERT", {}, Exception("unique constraint failed"))

        def recording_rollback() -> None:
            nonlocal rollback_called
            rollback_called = True
            original_rollback()

        monkeypatch.setattr(db, "commit", failing_commit)
        monkeypatch.setattr(db, "rollback", recording_rollback)
        app.dependency_overrides[get_approval_db] = lambda: db
        try:
            response = client.put(
                f"/api/v1/admin/process-apps/{app_id}",
                headers=admin_headers,
                json={"name": "并发修订"},
            )
        finally:
            app.dependency_overrides.pop(get_approval_db, None)

        assert response.status_code == 409
        assert rollback_called
        assert db.scalar(select(ProcessVersion.id).where(ProcessVersion.process_app_id == app_id))


def test_each_test_starts_with_only_the_seed_process_apps(db_session):
    apps = db_session.scalars(select(ProcessApp)).all()
    assert len(apps) == 3
    assert {app.code for app in apps} == {"expense", "leave", "purchase"}


def test_legacy_admin_routes_are_removed(client, admin_headers):
    response = client.get("/api/v1/admin/approval-types", headers=admin_headers)
    assert response.status_code == 404


def test_admin_lists_creates_and_updates_users_with_position_and_active_status(
    client, admin_headers
):
    listed = client.get("/api/v1/admin/users", headers=admin_headers)
    assert listed.status_code == 200
    assert {"position", "is_active"} <= listed.json()["data"][0].keys()

    email = f"new-{uuid4().hex[:8]}@example.com"
    created = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "display_name": "测试员工",
            "email": email,
            "department": "研发部",
            "position": "后端工程师",
            "role": "employee",
        },
    )
    assert created.status_code == 201
    user = created.json()["data"]
    assert user["email"] == email
    assert user["position"] == "后端工程师"
    assert user["is_active"] is True

    updated = client.put(
        f"/api/v1/admin/users/{user['id']}",
        headers=admin_headers,
        json={"position": "高级后端工程师", "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["position"] == "高级后端工程师"
    assert updated.json()["data"]["is_active"] is False


def test_user_create_and_update_require_position_and_reject_duplicate_email(client, admin_headers):
    missing_position = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "display_name": "测试员工",
            "email": "new@example.com",
            "department": "研发部",
            "role": "employee",
        },
    )
    assert missing_position.status_code == 422

    duplicate_email = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "display_name": "重复邮箱员工",
            "email": "admin@demo.local",
            "department": "研发部",
            "position": "工程师",
            "role": "employee",
        },
    )
    assert duplicate_email.status_code == 409

    user_id = "22222222-2222-2222-2222-222222222222"
    missing_position_on_update = client.put(
        f"/api/v1/admin/users/{user_id}", headers=admin_headers, json={"is_active": False}
    )
    assert missing_position_on_update.status_code == 422
