from sqlalchemy import inspect, select

from app.approval.database import approval_engine
from app.approval.models import ApprovalRequest, ApprovalUser, ProcessApp, ProcessVersion


def test_seed_creates_three_published_process_apps(db_session):
    apps = db_session.scalars(select(ProcessApp).order_by(ProcessApp.code)).all()
    assert [app.code for app in apps] == ["expense", "leave", "purchase"]
    assert all(app.status == "published" for app in apps)
    assert all(app.current_version_id for app in apps)
    versions = {
        version.id: version
        for version in db_session.scalars(select(ProcessVersion)).all()
    }
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
