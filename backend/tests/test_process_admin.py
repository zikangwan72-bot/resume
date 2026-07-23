from sqlalchemy import select

from app.approval.models import ApprovalUser, ProcessApp


def test_seed_creates_three_published_process_apps(db_session):
    apps = db_session.scalars(select(ProcessApp).order_by(ProcessApp.code)).all()
    assert [app.code for app in apps] == ["expense", "leave", "purchase"]
    assert all(app.status == "published" for app in apps)
    assert all(app.current_version_id for app in apps)


def test_seed_users_have_required_positions(db_session):
    users = db_session.scalars(select(ApprovalUser)).all()
    assert users
    assert all(user.position.strip() for user in users)
