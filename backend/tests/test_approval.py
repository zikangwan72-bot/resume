from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select

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
