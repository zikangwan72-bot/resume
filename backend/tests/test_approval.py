from copy import deepcopy
from uuid import uuid4

from app.approval.models import ProcessVersion

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
    db_session.expire_all()
    version = db_session.get(ProcessVersion, app["version_id"])
    assert version.form_schema == original_form
    assert version.flow_schema == original_flow
