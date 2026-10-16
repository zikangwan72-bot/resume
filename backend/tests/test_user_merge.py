import pytest
from sqlalchemy import select
from test_approval import _branching_definition, _create_and_publish_app, _headers, _submit_body

from app.approval.database import ApprovalSessionLocal
from app.approval.models import ApprovalNode, ApprovalRequest, ApprovalUser
from app.db.database import SessionLocal
from app.db.models import User
from app.db.user_merge import MergeAbort, apply_merge, plan_merge, verify_merge
from scripts.merge_user_tables import main as merge_cli

SHARED_ID = "44444444-4444-4444-4444-444444444444"  # login user manager04
LEGACY_APPROVERS = {"lisi@demo.local", "wangwu@demo.local", "zhaoliu@demo.local", "sunqi@demo.local"}


def _merge() -> dict[str, int]:
    with SessionLocal() as main_db, ApprovalSessionLocal() as approval_db:
        plan = plan_merge(main_db, approval_db)
        apply_merge(main_db, approval_db, plan)
        assert verify_merge(main_db, approval_db) == []
        approval_db.commit()
        main_db.commit()
        return plan.summary()


def _approval_user(email: str) -> ApprovalUser | None:
    with ApprovalSessionLocal() as db:
        return db.scalar(select(ApprovalUser).where(ApprovalUser.email == email))


def _make_conflict_with_history() -> int:
    """Recreate the production situation: the shared id carries another person's
    profile on the approval side and already has approval history."""
    with ApprovalSessionLocal() as db:
        row = db.get(ApprovalUser, SHARED_ID)
        row.email, row.display_name, row.department, row.position = "zhangsan@demo.local", "张三", "产品研发部", "产品经理"
        request = ApprovalRequest(
            applicant_id=SHARED_ID, applicant_name="张三", title="历史申请", form_data={},
            status="approved", current_node_index=0, flow_snapshot=[],
        )
        db.add(request)
        db.flush()
        db.add(ApprovalNode(request_id=request.id, node_index=0, node_key="manager", approver_id=SHARED_ID, approver_name="张三", status="approved"))
        db.commit()
        return request.id


def test_seeded_tables_merge_and_rerun_is_a_no_op():
    with SessionLocal() as main_db, ApprovalSessionLocal() as approval_db:
        before = plan_merge(main_db, approval_db).summary()
        login_users = len(main_db.scalars(select(User)).all())
        approval_users = len(approval_db.scalars(select(ApprovalUser)).all())
    assert before["conflicts"] == 0
    assert before["orphans_imported"] == len(LEGACY_APPROVERS)
    assert before["approval_rows_added"] == login_users - (approval_users - len(LEGACY_APPROVERS))

    _merge()
    assert _merge() == {"conflicts": 0, "synced": 0, "orphans_imported": 0, "approval_rows_added": 0}
    # A rerun must not deactivate the imported approvers that flows route to.
    assert all(_approval_user(email).is_active for email in LEGACY_APPROVERS)


def test_conflicting_id_takes_the_login_identity_and_keeps_its_history():
    request_id = _make_conflict_with_history()
    with SessionLocal() as main_db, ApprovalSessionLocal() as approval_db:
        assert plan_merge(main_db, approval_db).conflicts == [SHARED_ID]

    _merge()

    row = _approval_user("manager04@demo.local")
    assert row.id == SHARED_ID
    assert (row.display_name, row.department, row.position) == ("流程创新经理", "流程创新中心", "部门经理")
    assert _approval_user("zhangsan@demo.local") is None
    with ApprovalSessionLocal() as db:
        request = db.get(ApprovalRequest, request_id)
        node = db.scalar(select(ApprovalNode).where(ApprovalNode.request_id == request_id))
        # History keeps its ids and the names recorded at the time.
        assert (request.applicant_id, request.applicant_name) == (SHARED_ID, "张三")
        assert (node.approver_id, node.approver_name) == (SHARED_ID, "张三")
        assert db.get(ApprovalUser, request.applicant_id).email == "manager04@demo.local"


def test_approval_only_people_become_disabled_logins_but_stay_approvers(client):
    _merge()
    with SessionLocal() as db:
        imported = db.scalars(select(User).where(User.email.in_(LEGACY_APPROVERS))).all()
    assert {u.email for u in imported} == LEGACY_APPROVERS
    assert all(not u.is_active and u.password_hash is None and u.permissions == [] for u in imported)
    assert all(_approval_user(email).is_active for email in LEGACY_APPROVERS)
    response = client.post("/api/v1/auth/login", json={"email": "lisi@demo.local", "password": "Demo@2026!"})
    assert response.status_code == 401


def test_users_missing_from_approvals_can_submit_after_merge(client, admin_headers):
    app = _create_and_publish_app(client, admin_headers, _branching_definition())
    employee = _headers(client, "employee01@demo.local")

    before = client.post("/api/v1/approvals/requests", headers=employee, json=_submit_body(app["id"], key="merge-before"))
    assert before.status_code == 400
    assert before.json()["detail"] == "申请人不存在或已停用"

    _merge()

    after = client.post("/api/v1/approvals/requests", headers=employee, json=_submit_body(app["id"], key="merge-after"))
    assert after.status_code == 201
    assert after.json()["data"]["applicant_snapshot"]["email"] == "employee01@demo.local"


def test_merge_aborts_when_an_email_is_taken_by_a_different_approval_user():
    with ApprovalSessionLocal() as db:
        db.get(ApprovalUser, "55555555-5555-5555-5555-555555555555").email = "employee01@demo.local"
        db.commit()
    with SessionLocal() as main_db, ApprovalSessionLocal() as approval_db, pytest.raises(MergeAbort):
        plan_merge(main_db, approval_db)


def test_cli_dry_run_writes_nothing_and_count_guard_blocks_apply(capsys):
    assert merge_cli([]) == 0
    assert '"mode": "dry-run"' in capsys.readouterr().out
    with ApprovalSessionLocal() as db:
        assert db.scalar(select(ApprovalUser).where(ApprovalUser.email == "employee01@demo.local")) is None

    assert merge_cli(["--apply", "--expect-orphans", "99"]) == 1
    assert "ABORTED" in capsys.readouterr().err
    with ApprovalSessionLocal() as db:
        assert db.scalar(select(ApprovalUser).where(ApprovalUser.email == "employee01@demo.local")) is None
