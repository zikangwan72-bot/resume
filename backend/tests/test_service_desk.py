def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "Demo@2026!"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def create_ticket(client, headers, **overrides):
    payload = {"title": "笔记本无法连接打印机", "description": "三楼打印机一直显示脱机，重启无效。", "category": "硬件设备", "priority": "高", **overrides}
    response = client.post("/api/v1/service-desk/tickets", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()["data"]


def test_ticket_full_lifecycle(client, admin_headers):
    employee = login(client, "employee01@demo.local")
    ticket = create_ticket(client, employee)
    assert ticket["status"] == "待受理"
    assert ticket["ticket_no"].startswith("IT-")
    assert ticket["requester_name"] == "员工一"
    assert ticket["overdue"] is False

    assigned = client.post(f"/api/v1/service-desk/tickets/{ticket['id']}/assign", json={}, headers=admin_headers)
    assert assigned.status_code == 200
    assert assigned.json()["data"]["status"] == "处理中"
    assert assigned.json()["data"]["assignee_name"] == "平台管理员"

    comment = client.post(f"/api/v1/service-desk/tickets/{ticket['id']}/comments", json={"content": "打印机型号是 HP M428"}, headers=employee)
    assert comment.status_code == 201

    resolved = client.post(f"/api/v1/service-desk/tickets/{ticket['id']}/resolve", json={"resolution": "重新安装驱动后恢复"}, headers=admin_headers)
    assert resolved.json()["data"]["status"] == "已解决"

    reopened = client.post(f"/api/v1/service-desk/tickets/{ticket['id']}/reopen", json={"reason": "第二天又脱机了"}, headers=employee)
    assert reopened.json()["data"]["status"] == "处理中"
    assert reopened.json()["data"]["resolved_at"] is None

    client.post(f"/api/v1/service-desk/tickets/{ticket['id']}/resolve", json={"resolution": "更换网口并固定 IP"}, headers=admin_headers)
    closed = client.post(f"/api/v1/service-desk/tickets/{ticket['id']}/close", json={"rating": 5}, headers=employee)
    assert closed.status_code == 200
    assert closed.json()["data"]["status"] == "已关闭"
    assert closed.json()["data"]["rating"] == 5

    detail = client.get(f"/api/v1/service-desk/tickets/{ticket['id']}", headers=employee).json()["data"]
    contents = [event["content"] for event in detail["events"]]
    assert contents[0].startswith("提交工单")
    assert "打印机型号是 HP M428" in contents
    assert any(item.startswith("重新打开") for item in contents)
    assert contents[-1].startswith("确认解决并关闭")

    notifications = client.get("/api/v1/notifications", headers=employee).json()["data"]
    assert any(item["title"] == "工单已解决，请确认" for item in notifications)
    audit = client.get("/api/v1/audit-logs", headers=admin_headers).json()["data"]
    assert any(item["action"] == "service_ticket_closed" for item in audit)


def test_invalid_transitions_are_rejected(client, admin_headers):
    employee = login(client, "employee02@demo.local")
    ticket = create_ticket(client, employee, priority="低")
    url = f"/api/v1/service-desk/tickets/{ticket['id']}"

    assert client.post(f"{url}/resolve", json={"resolution": "跳过受理"}, headers=admin_headers).status_code == 409
    assert client.post(f"{url}/close", json={}, headers=employee).status_code == 409
    client.post(f"{url}/assign", json={}, headers=admin_headers)
    client.post(f"{url}/resolve", json={"resolution": "已处理"}, headers=admin_headers)
    assert client.post(f"{url}/close", json={}, headers=admin_headers).status_code == 403

    cancelable = create_ticket(client, employee, title="重复提交的工单")
    cancelled = client.post(f"/api/v1/service-desk/tickets/{cancelable['id']}/cancel", json={"reason": "重复提交"}, headers=employee)
    assert cancelled.json()["data"]["status"] == "已取消"
    assert client.post(f"/api/v1/service-desk/tickets/{cancelable['id']}/comments", json={"content": "还在吗"}, headers=employee).status_code == 409


def test_permissions_and_visibility(client, admin_headers):
    owner = login(client, "employee01@demo.local")
    other = login(client, "employee02@demo.local")
    recruiter = login(client, "recruit01@demo.local")
    ticket = create_ticket(client, owner)

    assert client.get(f"/api/v1/service-desk/tickets/{ticket['id']}", headers=other).status_code == 404
    assert all(row["requester_name"] == "员工二" for row in client.get("/api/v1/service-desk/tickets", headers=other).json()["data"])
    assert client.get("/api/v1/service-desk/tickets?scope=all", headers=other).status_code == 403
    assert client.post(f"/api/v1/service-desk/tickets/{ticket['id']}/assign", json={}, headers=other).status_code == 403
    assert client.get("/api/v1/service-desk/tickets", headers=recruiter).status_code == 403

    all_rows = client.get("/api/v1/service-desk/tickets?scope=all", headers=admin_headers).json()["data"]
    assert any(row["id"] == ticket["id"] for row in all_rows)
    assert any(row["ticket_no"].startswith("IT-SEED-") for row in all_rows)

    agents = client.get("/api/v1/service-desk/agents", headers=admin_headers).json()["data"]
    assert agents and all(agent["id"] for agent in agents)
    employee_id = client.get("/api/v1/auth/me", headers=other).json()["data"]["id"]
    bad_assign = client.post(f"/api/v1/service-desk/tickets/{ticket['id']}/assign", json={"assignee_id": employee_id}, headers=admin_headers)
    assert bad_assign.status_code == 400

    overview = client.get("/api/v1/service-desk/overview", headers=admin_headers).json()["data"]
    assert overview["can_manage"] is True
    assert overview["open_count"] >= 2
    mine = client.get("/api/v1/service-desk/overview", headers=owner).json()["data"]
    assert mine["can_manage"] is False
    assert mine["total"] >= 2


def test_validation_rejects_unknown_category(client):
    employee = login(client, "employee01@demo.local")
    response = client.post("/api/v1/service-desk/tickets", json={"title": "测试", "description": "描述内容足够长", "category": "咖啡机"}, headers=employee)
    assert response.status_code == 422
