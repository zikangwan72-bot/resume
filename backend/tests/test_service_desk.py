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


def ticket_url(ticket):
    return f"/api/v1/service-desk/tickets/{ticket['id']}"


def test_it_support_claims_requests_info_and_transfers(client, admin_headers):
    employee = login(client, "employee03@demo.local")
    it01 = login(client, "it01@demo.local")
    it02 = login(client, "it02@demo.local")
    ticket = create_ticket(client, employee, title="Outlook 收不到外部邮件")
    url = ticket_url(ticket)

    pool = client.get("/api/v1/service-desk/tickets?scope=pool", headers=it01).json()["data"]
    assert any(row["id"] == ticket["id"] for row in pool)
    assert any(item["title"] == "新的IT服务工单" for item in client.get("/api/v1/notifications", headers=it02).json()["data"])

    claimed = client.post(f"{url}/assign", json={}, headers=it01).json()["data"]
    assert claimed["status"] == "处理中"
    assert claimed["assignee_name"] == "IT运维工程师"
    assert claimed["available_actions"] == ["transfer", "request_info", "resolve", "comment"]

    # 不是当前处理人，也不是主管：不能抢单、不能解决
    assert client.post(f"{url}/assign", json={}, headers=it02).status_code == 403
    assert client.post(f"{url}/resolve", json={"resolution": "抢着解决"}, headers=it02).status_code == 403

    asked = client.post(f"{url}/request-info", json={"content": "请截图报错提示"}, headers=it01).json()["data"]
    assert asked["status"] == "待补充"
    assert asked["sla_state"] == "不计时"
    assert client.post(f"{url}/resolve", json={"resolution": "先关掉"}, headers=it01).status_code == 409
    assert client.post(f"{url}/reply", json={"content": "截图如下"}, headers=it02).status_code == 403
    employee_view = client.get(url, headers=employee).json()["data"]
    assert "reply" in employee_view["available_actions"]

    replied = client.post(f"{url}/reply", json={"content": "提示 550 拒收"}, headers=employee).json()["data"]
    assert replied["status"] == "处理中"

    it02_id = client.get("/api/v1/auth/me", headers=it02).json()["data"]["id"]
    transferred = client.post(f"{url}/assign", json={"assignee_id": it02_id, "reason": "邮件网关归桌面支持"}, headers=it01).json()["data"]
    assert transferred["assignee_name"] == "IT桌面支持"
    assert client.post(f"{url}/resolve", json={"resolution": "旧处理人"}, headers=it01).status_code == 403
    assert client.post(f"{url}/resolve", json={"resolution": "放行外部域名"}, headers=it02).json()["data"]["status"] == "已解决"

    events = [event["content"] for event in client.get(url, headers=employee).json()["data"]["events"]]
    assert "请求补充信息：请截图报错提示" in events
    assert "补充信息：提示 550 拒收" in events
    assert any(item.startswith("由 IT运维工程师 转派给 IT桌面支持") for item in events)
    audit = client.get("/api/v1/audit-logs", headers=admin_headers).json()["data"]
    assert any(item["action"] == "service_ticket_transferred" for item in audit)


def test_only_manager_can_assign_to_others(client, admin_headers):
    employee = login(client, "employee04@demo.local")
    it01 = login(client, "it01@demo.local")
    it02_id = client.get("/api/v1/auth/me", headers=login(client, "it02@demo.local")).json()["data"]["id"]
    ticket = create_ticket(client, employee, title="新员工开通 VPN")
    url = ticket_url(ticket)

    assert client.post(f"{url}/assign", json={"assignee_id": it02_id}, headers=it01).status_code == 403
    assigned = client.post(f"{url}/assign", json={"assignee_id": it02_id}, headers=admin_headers).json()["data"]
    assert assigned["assignee_name"] == "IT桌面支持"
    assert client.post(f"{url}/assign", json={"assignee_id": it02_id}, headers=admin_headers).status_code == 409

    # IT 人员能看全部工单，普通员工不能
    assert client.get("/api/v1/service-desk/tickets?scope=all", headers=it01).status_code == 200
    assert client.get(url, headers=it01).status_code == 200
    assert client.get("/api/v1/service-desk/agents", headers=it01).status_code == 200
    assert client.get("/api/v1/service-desk/agents", headers=employee).status_code == 403
    overview = client.get("/api/v1/service-desk/overview", headers=it01).json()["data"]
    assert overview["can_handle"] is True and overview["can_manage"] is False


def test_resolved_ticket_auto_closes_after_72_hours(client, admin_headers):
    from datetime import UTC, datetime, timedelta

    from app.business.models import ServiceTicket
    from app.db.database import SessionLocal

    employee = login(client, "employee05@demo.local")
    ticket = create_ticket(client, employee, title="打印机卡纸")
    url = ticket_url(ticket)
    client.post(f"{url}/assign", json={}, headers=admin_headers)
    resolved = client.post(f"{url}/resolve", json={"resolution": "已清理卡纸"}, headers=admin_headers).json()["data"]
    assert resolved["auto_close_at"] is not None
    assert client.get(url, headers=employee).json()["data"]["status"] == "已解决"

    with SessionLocal() as db:
        row = db.get(ServiceTicket, ticket["id"])
        row.resolved_at = datetime.now(UTC) - timedelta(hours=73)
        db.commit()

    detail = client.get(url, headers=employee).json()["data"]
    assert detail["status"] == "已关闭"
    assert detail["events"][-1]["actor_name"] == "System"
    assert any(item["title"] == "工单已自动关闭" for item in client.get("/api/v1/notifications", headers=employee).json()["data"])


def test_sla_state_and_asset_link(client):
    from datetime import UTC, datetime, timedelta

    from app.business.models import ServiceTicket
    from app.db.database import SessionLocal

    employee = login(client, "employee01@demo.local")
    assets = client.get("/api/v1/service-desk/assets?keyword=笔记本", headers=employee).json()["data"]
    assert assets
    ticket = create_ticket(client, employee, title="笔记本键盘失灵", priority="紧急", asset_id=assets[0]["id"])
    assert ticket["asset_code"] == assets[0]["asset_code"]
    assert ticket["sla_state"] == "正常"

    bad = client.post("/api/v1/service-desk/tickets", json={"title": "无效资产", "description": "资产编号不存在", "category": "硬件设备", "asset_id": 999999}, headers=employee)
    assert bad.status_code == 400

    with SessionLocal() as db:
        row = db.get(ServiceTicket, ticket["id"])
        row.created_at = datetime.now(UTC) - timedelta(hours=3, minutes=30)
        row.due_at = datetime.now(UTC) + timedelta(minutes=30)
        db.commit()
    assert client.get(ticket_url(ticket), headers=employee).json()["data"]["sla_state"] == "即将超时"

    with SessionLocal() as db:
        row = db.get(ServiceTicket, ticket["id"])
        row.due_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    assert client.get(ticket_url(ticket), headers=employee).json()["data"]["sla_state"] == "已超时"
