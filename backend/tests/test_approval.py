from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.approval import router as approval_router
from app.approval.database import ApprovalSessionLocal
from app.approval.models import ApprovalAction, ApprovalUser, ProcessVersion

PRODUCT_USER_ID = "22222222-2222-2222-2222-222222222222"
DIRECTOR_USER_ID = "11111111-1111-1111-1111-111111111111"
FINANCE_USER_ID = "77777777-7777-7777-7777-777777777777"


def _headers(client, role: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/demo-login", json={"role": role})
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_and_publish_app(client, admin_headers, definition: dict) -> dict:
    created = client.post("/api/v1/admin/process-apps", headers=admin_headers, json=definition)
    assert created.status_code == 201
    app = created.json()["data"]
    published = client.post(
        f"/api/v1/admin/process-apps/{app['id']}/publish", headers=admin_headers
    )
    assert published.status_code == 200
    return published.json()["data"]


def _branching_definition() -> dict:
    return {
        "code": f"purchase-{uuid4().hex[:8]}",
        "name": "采购申请",
        "category": "采购审批",
        "description": "带金额分支的采购流程",
        "form_schema": {
            "fields": [
                {"id": "amount", "label": "金额", "type": "money", "required": True},
                {"id": "item_name", "label": "采购物品", "type": "text", "required": True},
            ]
        },
        "flow_schema": {
            "nodes": [
                {"id": "start", "type": "start"},
                {
                    "id": "manager",
                    "type": "approval",
                    "approval_type": "single",
                    "approver_id": PRODUCT_USER_ID,
                },
                {"id": "amount_gate", "type": "condition"},
                {
                    "id": "director",
                    "type": "approval",
                    "approval_type": "single",
                    "approver_id": DIRECTOR_USER_ID,
                },
                {
                    "id": "finance",
                    "type": "approval",
                    "approval_type": "single",
                    "approver_id": FINANCE_USER_ID,
                },
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"source": "start", "target": "manager"},
                {"source": "manager", "target": "amount_gate"},
                {
                    "source": "amount_gate",
                    "target": "director",
                    "condition": {"field_id": "amount", "operator": "gte", "value": 100000},
                },
                {"source": "amount_gate", "target": "finance", "default": True},
                {"source": "director", "target": "finance"},
                {"source": "finance", "target": "end"},
            ],
        },
    }


def _countersign_definition() -> dict:
    definition = _branching_definition()
    definition["code"] = f"countersign-{uuid4().hex[:8]}"
    definition["flow_schema"] = {
        "nodes": [
            {"id": "start", "type": "start"},
            {
                "id": "manager",
                "type": "approval",
                "approval_type": "single",
                "approver_id": PRODUCT_USER_ID,
            },
            {
                "id": "directors",
                "type": "countersign",
                "approval_type": "counter_sign",
                "approver_ids": [DIRECTOR_USER_ID, PRODUCT_USER_ID],
            },
            {
                "id": "finance",
                "type": "approval",
                "approval_type": "single",
                "approver_id": FINANCE_USER_ID,
            },
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "manager"},
            {"source": "manager", "target": "directors"},
            {"source": "directors", "target": "finance"},
            {"source": "finance", "target": "end"},
        ],
    }
    return definition


def _single_step_definition() -> dict:
    definition = _branching_definition()
    definition["code"] = f"single-{uuid4().hex[:8]}"
    definition["flow_schema"] = {
        "nodes": [
            {"id": "start", "type": "start"},
            {
                "id": "manager",
                "type": "approval",
                "approval_type": "single",
                "approver_id": PRODUCT_USER_ID,
                "allow_transfer": False,
            },
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "manager"},
            {"source": "manager", "target": "end"},
        ],
    }
    return definition


def _rich_form_definition() -> dict:
    definition = _single_step_definition()
    definition["code"] = f"rich-form-{uuid4().hex[:8]}"
    definition["form_schema"] = {
        "fields": [
            {"id": "subject", "label": "主题", "type": "text", "required": True},
            {"id": "amount", "label": "金额", "type": "money", "required": True},
            {
                "id": "category",
                "label": "类别",
                "type": "select",
                "required": True,
                "options": ["hardware", "software"],
            },
            {
                "id": "tags",
                "label": "标签",
                "type": "checkbox",
                "required": True,
                "options": ["urgent", "budgeted"],
            },
            {"id": "period", "label": "期间", "type": "date_range", "required": True},
            {
                "id": "items",
                "label": "明细",
                "type": "detail_table",
                "required": True,
                "columns": [
                    {"id": "name", "label": "名称", "type": "text", "required": True},
                    {"id": "quantity", "label": "数量", "type": "number", "required": True},
                    {
                        "id": "kind",
                        "label": "分类",
                        "type": "select",
                        "required": True,
                        "options": ["server", "storage"],
                    },
                ],
            },
        ]
    }
    return definition


def _rich_form_data() -> dict:
    return {
        "subject": "基础设施采购",
        "amount": 120000,
        "category": "hardware",
        "tags": ["urgent"],
        "period": ["2026-07-01", "2026-07-31"],
        "items": [{"name": "服务器", "quantity": 2, "kind": "server"}],
    }


def _top_level_types_definition() -> dict:
    definition = _single_step_definition()
    definition["code"] = f"top-level-{uuid4().hex[:8]}"
    definition["form_schema"] = {
        "fields": [
            {"id": "notes", "label": "说明", "type": "textarea", "required": True},
            {"id": "due_date", "label": "日期", "type": "date", "required": True},
            {
                "id": "priority",
                "label": "优先级",
                "type": "radio",
                "required": True,
                "options": ["high", "normal"],
            },
            {"id": "requester", "label": "申请人", "type": "user", "required": True},
            {"id": "team", "label": "部门", "type": "department", "required": True},
            {"id": "proof", "label": "附件", "type": "attachment", "required": True},
        ]
    }
    return definition


def _top_level_types_data() -> dict:
    return {
        "notes": "采购说明",
        "due_date": "2026-07-31",
        "priority": "high",
        "requester": PRODUCT_USER_ID,
        "team": "产品研发部",
        "proof": "https://files.example/proof.pdf",
    }


def _submit_body(app_id: int, *, key: str = "purchase-001") -> dict:
    return {
        "process_app_id": app_id,
        "title": "高额采购",
        "form_data": {"amount": 120000, "item_name": "服务器"},
        "idempotency_key": key,
    }


def test_apps_lists_only_active_published_apps_usable_by_applicants(client, admin_headers):
    published = _create_and_publish_app(client, admin_headers, _branching_definition())
    draft = client.post(
        "/api/v1/admin/process-apps", headers=admin_headers, json=_branching_definition()
    )
    assert draft.status_code == 201

    response = client.get("/api/v1/approvals/apps", headers=_headers(client, "product_demo_user"))

    assert response.status_code == 200
    apps = response.json()["data"]
    assert published["id"] in {app["id"] for app in apps}
    assert draft.json()["data"]["id"] not in {app["id"] for app in apps}
    assert all(
        app["status"] == "published" and app["version_status"] == "published" for app in apps
    )


def test_submit_snapshots_applicant_and_resolved_high_value_path(client, admin_headers):
    app = _create_and_publish_app(client, admin_headers, _branching_definition())

    response = client.post(
        "/api/v1/approvals/requests", headers=admin_headers, json=_submit_body(app["id"])
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["process_app_id"] == app["id"]
    assert data["process_version_id"] == app["version_id"]
    assert data["applicant_snapshot"]["position"]
    assert data["form_data"] == {"amount": 120000, "item_name": "服务器"}
    assert [node["node_key"] for node in data["nodes"]] == ["manager", "director", "finance"]
    assert [node["node_index"] for node in data["nodes"]] == [0, 1, 2]


def test_submit_rejects_unpublished_or_invalid_form_data(client, admin_headers):
    draft = client.post(
        "/api/v1/admin/process-apps", headers=admin_headers, json=_branching_definition()
    )
    assert draft.status_code == 201
    unpublished = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json=_submit_body(draft.json()["data"]["id"]),
    )
    assert unpublished.status_code == 400

    inactive_app = _create_and_publish_app(client, admin_headers, _branching_definition())
    deactivated = client.post(
        f"/api/v1/admin/process-apps/{inactive_app['id']}/deactivate", headers=admin_headers
    )
    assert deactivated.status_code == 200
    inactive = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json=_submit_body(inactive_app["id"], key="inactive-app"),
    )
    assert inactive.status_code == 400

    app = _create_and_publish_app(client, admin_headers, _branching_definition())
    invalid = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json={
            **_submit_body(app["id"], key="missing-item"),
            "form_data": {"amount": 120000},
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_form_data"


def test_duplicate_idempotency_key_returns_same_request(client, admin_headers):
    app = _create_and_publish_app(client, admin_headers, _branching_definition())
    body = _submit_body(app["id"])

    first = client.post("/api/v1/approvals/requests", headers=admin_headers, json=body)
    second = client.post("/api/v1/approvals/requests", headers=admin_headers, json=body)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]


def test_idempotency_integrity_error_fallback_returns_the_existing_request(
    client, admin_headers, monkeypatch
):
    app = _create_and_publish_app(client, admin_headers, _branching_definition())
    body = _submit_body(app["id"], key="integrity-fallback")
    created = client.post("/api/v1/approvals/requests", headers=admin_headers, json=body)
    assert created.status_code == 201

    from app.approval import router as approval_router

    original_lookup = approval_router._existing_idempotent_request
    lookup_count = 0

    def race_lookup(db, applicant_id, idempotency_key):
        nonlocal lookup_count
        lookup_count += 1
        if lookup_count == 1:
            return None
        return original_lookup(db, applicant_id, idempotency_key)

    monkeypatch.setattr(approval_router, "_existing_idempotent_request", race_lookup)
    retried = client.post("/api/v1/approvals/requests", headers=admin_headers, json=body)

    assert retried.status_code == 200
    assert retried.json()["data"]["id"] == created.json()["data"]["id"]


def test_countersign_requires_every_configured_approver_before_advancing(client, admin_headers):
    app = _create_and_publish_app(client, admin_headers, _countersign_definition())
    request = client.post(
        "/api/v1/approvals/requests", headers=admin_headers, json=_submit_body(app["id"])
    ).json()["data"]
    manager_node = request["nodes"][0]

    manager_approval = client.post(
        f"/api/v1/approvals/nodes/{manager_node['id']}/approve",
        headers=_headers(client, "product_demo_user"),
        json={"comment": "同意"},
    )
    assert manager_approval.status_code == 200
    detail = manager_approval.json()["data"]
    director_nodes = [node for node in detail["nodes"] if node["node_key"] == "directors"]
    assert len(director_nodes) == 2

    first_countersign = client.post(
        f"/api/v1/approvals/nodes/{director_nodes[0]['id']}/approve",
        headers=admin_headers,
        json={"comment": "同意"},
    )
    assert first_countersign.status_code == 200
    assert first_countersign.json()["data"]["current_node_index"] == 1

    second_countersign = client.post(
        f"/api/v1/approvals/nodes/{director_nodes[1]['id']}/approve",
        headers=_headers(client, "product_demo_user"),
        json={"comment": "同意"},
    )
    assert second_countersign.status_code == 200
    assert second_countersign.json()["data"]["current_node_index"] == 2


def test_countersign_rejection_finishes_request_and_cancels_remaining_siblings(
    client, admin_headers
):
    app = _create_and_publish_app(client, admin_headers, _countersign_definition())
    request = client.post(
        "/api/v1/approvals/requests", headers=admin_headers, json=_submit_body(app["id"])
    ).json()["data"]
    manager_node = request["nodes"][0]
    client.post(
        f"/api/v1/approvals/nodes/{manager_node['id']}/approve",
        headers=_headers(client, "product_demo_user"),
        json={"comment": "同意"},
    )
    countersign_nodes = [
        node
        for node in client.get(
            f"/api/v1/approvals/requests/{request['id']}", headers=admin_headers
        ).json()["data"]["nodes"]
        if node["node_key"] == "directors"
    ]

    rejected = client.post(
        f"/api/v1/approvals/nodes/{countersign_nodes[0]['id']}/reject",
        headers=admin_headers,
        json={"comment": "不同意"},
    )

    assert rejected.status_code == 200
    detail = rejected.json()["data"]
    assert detail["status"] == "rejected"
    assert detail["completed_at"] is not None
    assert detail["current_node_index"] == 1
    assert [node["status"] for node in detail["nodes"] if node["node_key"] == "directors"] == [
        "rejected",
        "cancelled",
    ]
    assert detail["nodes"][0]["status"] == "approved"


@pytest.mark.parametrize(
    ("form_data", "field_id"),
    [
        ({**_rich_form_data(), "unknown": "x"}, "unknown"),
        ({**_rich_form_data(), "tags": "urgent"}, "tags"),
        ({**_rich_form_data(), "tags": ["not-configured"]}, "tags"),
        ({**_rich_form_data(), "period": ["2026-07-31", "2026-07-01"]}, "period"),
        ({**_rich_form_data(), "period": ["bad-date", "2026-07-01"]}, "period"),
        ({**_rich_form_data(), "items": {"name": "服务器"}}, "items"),
        (
            {**_rich_form_data(), "items": [{"quantity": "two", "kind": "server"}]},
            "items.0.name",
        ),
        (
            {
                **_rich_form_data(),
                "items": [{"name": "服务器", "quantity": 2, "kind": "bad"}],
            },
            "items.0.kind",
        ),
    ],
)
def test_submit_rejects_invalid_dynamic_form_values(client, admin_headers, form_data, field_id):
    app = _create_and_publish_app(client, admin_headers, _rich_form_definition())

    response = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json={
            "process_app_id": app["id"],
            "title": "动态表单校验",
            "form_data": form_data,
            "idempotency_key": f"invalid-{uuid4().hex}",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_form_data"
    assert response.json()["detail"]["field_id"] == field_id


def test_submit_accepts_a_valid_detail_table(client, admin_headers):
    app = _create_and_publish_app(client, admin_headers, _rich_form_definition())

    response = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json={
            "process_app_id": app["id"],
            "title": "有效动态表单",
            "form_data": _rich_form_data(),
            "idempotency_key": "valid-dynamic-form",
        },
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    ("form_data", "field_id"),
    [
        ({**_top_level_types_data(), "notes": 1}, "notes"),
        ({**_top_level_types_data(), "due_date": "not-a-date"}, "due_date"),
        ({**_top_level_types_data(), "priority": "urgent"}, "priority"),
        ({**_top_level_types_data(), "requester": [PRODUCT_USER_ID]}, "requester"),
        ({**_top_level_types_data(), "team": {"name": "产品研发部"}}, "team"),
        ({**_top_level_types_data(), "proof": [1]}, "proof"),
    ],
)
def test_submit_rejects_invalid_top_level_field_types(client, admin_headers, form_data, field_id):
    app = _create_and_publish_app(client, admin_headers, _top_level_types_definition())

    response = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json={
            "process_app_id": app["id"],
            "title": "顶层字段校验",
            "form_data": form_data,
            "idempotency_key": f"top-level-{uuid4().hex}",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field_id"] == field_id


def test_submit_rejects_malformed_options_shape_with_field_detail(
    client, admin_headers, db_session
):
    app = _create_and_publish_app(client, admin_headers, _top_level_types_definition())
    version = db_session.get(ProcessVersion, app["version_id"])
    schema = deepcopy(version.form_schema)
    schema["fields"][2]["options"] = "high"
    version.form_schema = schema
    db_session.commit()

    response = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json={
            "process_app_id": app["id"],
            "title": "选项形状校验",
            "form_data": _top_level_types_data(),
            "idempotency_key": "malformed-options",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field_id"] == "priority"


def test_submit_rejects_missing_choice_options_in_a_published_snapshot(
    client, admin_headers, db_session
):
    app = _create_and_publish_app(client, admin_headers, _top_level_types_definition())
    version = db_session.get(ProcessVersion, app["version_id"])
    schema = deepcopy(version.form_schema)
    schema["fields"][2].pop("options")
    version.form_schema = schema
    db_session.commit()

    response = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json={
            "process_app_id": app["id"],
            "title": "历史选项缺失",
            "form_data": _top_level_types_data(),
            "idempotency_key": "missing-options",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field_id"] == "priority"


def test_submit_rejects_ambiguous_process_and_legacy_selectors(client, admin_headers):
    app = _create_and_publish_app(client, admin_headers, _branching_definition())

    response = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json={**_submit_body(app["id"]), "type_id": 1},
    )

    assert response.status_code == 422


def test_transfer_requires_enabled_target_and_node_permission(client, admin_headers, db_session):
    disallowed_app = _create_and_publish_app(client, admin_headers, _single_step_definition())
    disallowed_request = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json=_submit_body(disallowed_app["id"], key="transfer-disallowed"),
    ).json()["data"]
    disallowed = client.post(
        f"/api/v1/approvals/nodes/{disallowed_request['nodes'][0]['id']}/transfer",
        headers=_headers(client, "product_demo_user"),
        json={"target_user_id": DIRECTOR_USER_ID},
    )
    assert disallowed.status_code == 400

    transferable_definition = _single_step_definition()
    transferable_definition["flow_schema"]["nodes"][1]["allow_transfer"] = True
    transferable_app = _create_and_publish_app(client, admin_headers, transferable_definition)
    inactive_target = db_session.get(ApprovalUser, DIRECTOR_USER_ID)
    inactive_target.is_active = False
    db_session.commit()
    transferable_request = client.post(
        "/api/v1/approvals/requests",
        headers=_headers(client, "product_demo_user"),
        json=_submit_body(transferable_app["id"], key="transfer-inactive"),
    ).json()["data"]
    self_transfer = client.post(
        f"/api/v1/approvals/nodes/{transferable_request['nodes'][0]['id']}/transfer",
        headers=_headers(client, "product_demo_user"),
        json={"target_user_id": PRODUCT_USER_ID},
    )
    inactive = client.post(
        f"/api/v1/approvals/nodes/{transferable_request['nodes'][0]['id']}/transfer",
        headers=_headers(client, "product_demo_user"),
        json={"target_user_id": DIRECTOR_USER_ID},
    )
    assert self_transfer.status_code == 400
    assert inactive.status_code == 400


def test_low_value_branch_skips_director_and_duplicate_approval_writes_one_action(
    client, admin_headers, db_session
):
    app = _create_and_publish_app(client, admin_headers, _branching_definition())
    request = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json={
            **_submit_body(app["id"], key="low-value"),
            "form_data": {"amount": 1000, "item_name": "键盘"},
        },
    ).json()["data"]
    assert [node["node_key"] for node in request["nodes"]] == ["manager", "finance"]

    first = client.post(
        f"/api/v1/approvals/nodes/{request['nodes'][0]['id']}/approve",
        headers=_headers(client, "product_demo_user"),
        json={"comment": "同意"},
    )
    second = client.post(
        f"/api/v1/approvals/nodes/{request['nodes'][0]['id']}/approve",
        headers=_headers(client, "product_demo_user"),
        json={"comment": "再次同意"},
    )

    assert first.status_code == 200
    assert second.status_code == 400
    actions = db_session.scalars(
        select(ApprovalAction).where(ApprovalAction.node_id == request["nodes"][0]["id"])
    ).all()
    assert len(actions) == 1


def test_revoke_and_urge_remain_available_for_process_app_requests(client, admin_headers):
    app = _create_and_publish_app(client, admin_headers, _branching_definition())
    request = client.post(
        "/api/v1/approvals/requests", headers=admin_headers, json=_submit_body(app["id"])
    ).json()["data"]

    urged = client.put(f"/api/v1/approvals/requests/{request['id']}/urge", headers=admin_headers)
    revoked = client.put(
        f"/api/v1/approvals/requests/{request['id']}/revoke", headers=admin_headers
    )

    assert urged.status_code == 200
    assert revoked.status_code == 200
    assert revoked.json()["data"]["status"] == "revoked"


def test_terminal_revoke_and_urge_return_conflict_without_new_urge_action(
    client, admin_headers, db_session
):
    app = _create_and_publish_app(client, admin_headers, _single_step_definition())
    request = client.post(
        "/api/v1/approvals/requests", headers=admin_headers, json=_submit_body(app["id"])
    ).json()["data"]
    approved = client.post(
        f"/api/v1/approvals/nodes/{request['nodes'][0]['id']}/approve",
        headers=_headers(client, "product_demo_user"),
        json={"comment": "同意"},
    )
    assert approved.status_code == 200
    actions_before = db_session.scalars(
        select(ApprovalAction).where(ApprovalAction.request_id == request["id"])
    ).all()

    stale_revoke = client.put(
        f"/api/v1/approvals/requests/{request['id']}/revoke", headers=admin_headers
    )
    stale_urge = client.put(
        f"/api/v1/approvals/requests/{request['id']}/urge", headers=admin_headers
    )

    assert stale_revoke.status_code == 409
    assert stale_urge.status_code == 409
    db_session.expire_all()
    actions_after = db_session.scalars(
        select(ApprovalAction).where(ApprovalAction.request_id == request["id"])
    ).all()
    assert len(actions_after) == len(actions_before)


def test_concurrent_approvals_consume_once_and_countersign_advances_once(
    client, admin_headers, db_session, monkeypatch
):
    original_consume = approval_router._consume_pending_node

    def concurrent_approvals(node_user_pairs):
        barrier = Barrier(len(node_user_pairs))

        def synchronized_consume(db, node, *args):
            barrier.wait(timeout=5)
            return original_consume(db, node, *args)

        monkeypatch.setattr(approval_router, "_consume_pending_node", synchronized_consume)

        def approve(item):
            node_id, actor_id, actor_name = item
            with ApprovalSessionLocal() as db:
                try:
                    approval_router.approve_node(
                        node_id,
                        approval_router.ApproveRejectBody(comment="同意"),
                        SimpleNamespace(id=actor_id, display_name=actor_name),
                        db,
                    )
                    return 200
                except HTTPException as exc:
                    db.rollback()
                    return exc.status_code

        try:
            with ThreadPoolExecutor(max_workers=len(node_user_pairs)) as executor:
                futures = [executor.submit(approve, item) for item in node_user_pairs]
                return [future.result(timeout=10) for future in futures]
        finally:
            monkeypatch.setattr(approval_router, "_consume_pending_node", original_consume)

    app_definition = _single_step_definition()
    app_definition["flow_schema"]["nodes"][1]["allow_transfer"] = True
    app_data = _create_and_publish_app(client, admin_headers, app_definition)
    request = client.post(
        "/api/v1/approvals/requests", headers=admin_headers, json=_submit_body(app_data["id"])
    ).json()["data"]
    duplicate_results = concurrent_approvals(
        [
            (request["nodes"][0]["id"], PRODUCT_USER_ID, "产品演示用户"),
            (request["nodes"][0]["id"], PRODUCT_USER_ID, "产品演示用户"),
        ]
    )

    assert sorted(duplicate_results) == [200, 400]
    duplicate_actions = db_session.scalars(
        select(ApprovalAction).where(ApprovalAction.node_id == request["nodes"][0]["id"])
    ).all()
    assert len(duplicate_actions) == 1

    countersign_app = _create_and_publish_app(client, admin_headers, _countersign_definition())
    countersign_request = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json=_submit_body(countersign_app["id"], key="concurrent-countersign"),
    ).json()["data"]
    client.post(
        f"/api/v1/approvals/nodes/{countersign_request['nodes'][0]['id']}/approve",
        headers=_headers(client, "product_demo_user"),
        json={"comment": "同意"},
    )
    detail = client.get(
        f"/api/v1/approvals/requests/{countersign_request['id']}", headers=admin_headers
    ).json()["data"]
    countersign_nodes = [node for node in detail["nodes"] if node["node_key"] == "directors"]
    countersign_results = concurrent_approvals(
        [
            (countersign_nodes[0]["id"], DIRECTOR_USER_ID, "平台管理员"),
            (countersign_nodes[1]["id"], PRODUCT_USER_ID, "产品演示用户"),
        ]
    )

    assert countersign_results == [200, 200]
    current = client.get(
        f"/api/v1/approvals/requests/{countersign_request['id']}", headers=admin_headers
    ).json()["data"]
    assert current["status"] == "pending"
    assert current["current_node_index"] == 2


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_transfer_race_prevents_stale_approver_from_consuming_reassigned_node(
    client, admin_headers, monkeypatch, action
):
    definition = _single_step_definition()
    definition["flow_schema"]["nodes"][1]["allow_transfer"] = True
    app_data = _create_and_publish_app(client, admin_headers, definition)
    request = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json=_submit_body(app_data["id"], key=f"transfer-race-{action}"),
    ).json()["data"]
    node_id = request["nodes"][0]["id"]
    old_action_ready = Event()
    release_old_action = Event()
    original_consume = approval_router._consume_pending_node

    def paused_consume(db, node, *args):
        old_action_ready.set()
        assert release_old_action.wait(timeout=5)
        return original_consume(db, node, *args)

    monkeypatch.setattr(approval_router, "_consume_pending_node", paused_consume)

    def stale_action():
        with ApprovalSessionLocal() as db:
            try:
                handler = (
                    approval_router.approve_node
                    if action == "approve"
                    else approval_router.reject_node
                )
                handler(
                    node_id,
                    approval_router.ApproveRejectBody(comment="处理意见"),
                    SimpleNamespace(id=PRODUCT_USER_ID, display_name="产品演示用户"),
                    db,
                )
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=1) as executor:
        stale_future = executor.submit(stale_action)
        assert old_action_ready.wait(timeout=5)
        with ApprovalSessionLocal() as db:
            transferred = approval_router.transfer_node(
                node_id,
                approval_router.TransferBody(target_user_id=DIRECTOR_USER_ID),
                SimpleNamespace(id=PRODUCT_USER_ID, display_name="产品演示用户"),
                db,
            )
            assert transferred["data"]["nodes"][0]["approver_id"] == DIRECTOR_USER_ID
        release_old_action.set()
        stale_status = stale_future.result(timeout=10)

    assert stale_status == 400
    response = client.get(
        f"/api/v1/approvals/requests/{request['id']}", headers=admin_headers
    )
    detail = response.json()["data"]
    assert detail["status"] == "pending"
    assert detail["nodes"][0]["approver_id"] == DIRECTOR_USER_ID
    assert detail["nodes"][0]["status"] == "pending"
    assert [item["action"] for item in detail["actions"]] == ["transfer"]


def test_revoke_racing_terminal_approval_preserves_revoked_status(
    client, admin_headers, monkeypatch
):
    app_data = _create_and_publish_app(client, admin_headers, _single_step_definition())
    request = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json=_submit_body(app_data["id"], key="revoke-approve-race"),
    ).json()["data"]
    approval_ready = Event()
    release_approval = Event()
    original_consume = approval_router._consume_pending_node

    def paused_consume(db, node, *args):
        approval_ready.set()
        assert release_approval.wait(timeout=5)
        return original_consume(db, node, *args)

    monkeypatch.setattr(approval_router, "_consume_pending_node", paused_consume)

    def approve():
        with ApprovalSessionLocal() as db:
            try:
                approval_router.approve_node(
                    request["nodes"][0]["id"],
                    approval_router.ApproveRejectBody(comment="同意"),
                    SimpleNamespace(id=PRODUCT_USER_ID, display_name="产品演示用户"),
                    db,
                )
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=1) as executor:
        approval_future = executor.submit(approve)
        assert approval_ready.wait(timeout=5)
        revoked = client.put(
            f"/api/v1/approvals/requests/{request['id']}/revoke", headers=admin_headers
        )
        release_approval.set()
        approval_status = approval_future.result(timeout=10)

    assert revoked.status_code == 200
    assert approval_status == 400
    response = client.get(
        f"/api/v1/approvals/requests/{request['id']}", headers=admin_headers
    )
    detail = response.json()["data"]
    assert detail["status"] == "revoked"
    assert [item["action"] for item in detail["actions"]] == ["revoke"]


def test_legacy_submission_remains_available(client, admin_headers):
    response = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json={
            "type_id": 1,
            "title": "兼容请假申请",
            "form_data": {
                "leave_type": "年假",
                "start_date": "2026-07-01",
                "end_date": "2026-07-02",
                "days": 2,
                "reason": "休假",
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["type_id"] == 1


def test_current_node_authorization_and_request_transitions_use_process_apps(client, admin_headers):
    app = _create_and_publish_app(client, admin_headers, _branching_definition())
    request = client.post(
        "/api/v1/approvals/requests", headers=admin_headers, json=_submit_body(app["id"])
    ).json()["data"]
    manager_node, director_node = request["nodes"][:2]

    early_approval = client.post(
        f"/api/v1/approvals/nodes/{director_node['id']}/approve",
        headers=admin_headers,
        json={"comment": "提前同意"},
    )
    assert early_approval.status_code == 400
    assert early_approval.json()["detail"] == "该节点还未轮到处理"

    manager_approval = client.post(
        f"/api/v1/approvals/nodes/{manager_node['id']}/approve",
        headers=_headers(client, "product_demo_user"),
        json={"comment": "同意"},
    )
    assert manager_approval.status_code == 200
    assert manager_approval.json()["data"]["current_node_index"] == 1

    pending = client.get("/api/v1/approvals/pending", headers=admin_headers)
    assert [item["node_id"] for item in pending.json()["data"]] == [director_node["id"]]


def test_submission_does_not_modify_the_published_definition(client, admin_headers, db_session):
    app = _create_and_publish_app(client, admin_headers, _branching_definition())
    version = db_session.get(ProcessVersion, app["version_id"])
    original_form = deepcopy(version.form_schema)
    original_flow = deepcopy(version.flow_schema)

    response = client.post(
        "/api/v1/approvals/requests", headers=admin_headers, json=_submit_body(app["id"])
    )

    assert response.status_code == 201
    revised_schema = deepcopy(original_form)
    revised_schema["fields"].append({"id": "supplier", "label": "供应商", "type": "text"})
    revised = client.put(
        f"/api/v1/admin/process-apps/{app['id']}",
        headers=admin_headers,
        json={"form_schema": revised_schema},
    )
    assert revised.status_code == 200
    published = client.post(
        f"/api/v1/admin/process-apps/{app['id']}/publish", headers=admin_headers
    )
    assert published.status_code == 200
    detail = client.get(
        f"/api/v1/approvals/requests/{response.json()['data']['id']}", headers=admin_headers
    ).json()["data"]
    db_session.expire_all()
    version = db_session.get(ProcessVersion, app["version_id"])
    assert version.form_schema == original_form
    assert version.flow_schema == original_flow
    assert detail["process_version_id"] == app["version_id"]
    assert detail["form_schema_snapshot"] == original_form


def test_submission_rejects_a_published_flow_with_a_newly_inactive_approver(
    client, admin_headers, db_session
):
    app = _create_and_publish_app(client, admin_headers, _single_step_definition())
    manager = db_session.get(ApprovalUser, PRODUCT_USER_ID)
    manager.is_active = False
    db_session.commit()

    response = client.post(
        "/api/v1/approvals/requests",
        headers=admin_headers,
        json=_submit_body(app["id"], key="inactive-approver"),
    )

    assert response.status_code == 400
