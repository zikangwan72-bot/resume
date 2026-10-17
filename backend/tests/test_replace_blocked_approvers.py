import copy
import json

from sqlalchemy import func, select
from test_user_merge import _merge

from app.approval.database import ApprovalSessionLocal
from app.approval.models import (
    ApprovalNode,
    ApprovalRequest,
    FlowTemplate,
    ProcessApp,
    ProcessVersion,
)
from scripts.replace_blocked_approvers import main as replace_cli
from scripts.replace_blocked_approvers import replace_ids

ADMIN_ID = "11111111-1111-1111-1111-111111111111"
BLOCKED = {
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
    "77777777-7777-7777-7777-777777777777",
    "88888888-8888-8888-8888-888888888888",
}


def _live_flows_and_templates():
    with ApprovalSessionLocal() as db:
        flows = [
            db.get(ProcessVersion, app.current_version_id).flow_schema
            for app in db.scalars(select(ProcessApp)).all()
            if app.current_version_id
        ]
        templates = [t.nodes for t in db.scalars(select(FlowTemplate)).all()]
    return flows, templates


def _counts():
    with ApprovalSessionLocal() as db:
        return tuple(db.scalar(select(func.count()).select_from(m)) for m in (ApprovalRequest, ApprovalNode, ProcessVersion))


def test_replace_ids_dedupes_counter_sign_lists():
    nodes = {"approver_ids": ["a", "b", "x"], "approver_id": "a", "name": "a"}
    assert replace_ids(nodes, {"a", "b"}, "x") == {"approver_ids": ["x"], "approver_id": "x", "name": "x"}


def test_blocked_approvers_are_replaced_by_admin_and_rerun_is_a_no_op(capsys):
    _merge()  # disables the legacy approvers as logins
    flows, templates = _live_flows_and_templates()
    affected = sum(bool(BLOCKED & set(json.dumps(f).split('"'))) for f in flows)
    affected_templates = sum(bool(BLOCKED & set(json.dumps(t).split('"'))) for t in templates)
    assert affected and affected_templates
    before = _counts()

    assert replace_cli(["--apply", "--expect-versions", str(affected), "--expect-templates", str(affected_templates)]) == 0
    flows, templates = _live_flows_and_templates()
    text = json.dumps(flows + templates)
    assert not any(i in text for i in BLOCKED)
    assert ADMIN_ID in text
    assert _counts() == before

    capsys.readouterr()
    assert replace_cli(["--expect-versions", "0", "--expect-templates", "0"]) == 0


def test_count_guard_aborts_without_writing(capsys):
    _merge()
    flows_before, templates_before = _live_flows_and_templates()
    assert replace_cli(["--apply", "--expect-versions", "99"]) == 1
    assert "ABORTED" in capsys.readouterr().err
    assert _live_flows_and_templates() == (flows_before, templates_before)


def test_only_an_identical_unused_stray_draft_is_removed():
    _merge()
    with ApprovalSessionLocal() as db:
        app = next(
            a for a in db.scalars(select(ProcessApp)).all()
            if a.current_version_id and BLOCKED & set(json.dumps(db.get(ProcessVersion, a.current_version_id).flow_schema).split('"'))
        )
        current = db.get(ProcessVersion, app.current_version_id)
        stray = ProcessVersion(
            process_app_id=app.id, version_number=90, status="draft",
            form_schema=copy.deepcopy(current.form_schema),
            flow_schema=replace_ids(copy.deepcopy(current.flow_schema), BLOCKED, ADMIN_ID),
        )
        edited = ProcessVersion(
            process_app_id=app.id, version_number=91, status="draft",
            form_schema=copy.deepcopy(current.form_schema), flow_schema={"nodes": [], "edges": []},
        )
        db.add_all([stray, edited])
        db.commit()
        stray_id, edited_id = stray.id, edited.id

    assert replace_cli(["--apply", "--expect-drafts", "1"]) == 0
    with ApprovalSessionLocal() as db:
        assert db.get(ProcessVersion, stray_id) is None
        assert db.get(ProcessVersion, edited_id) is not None
