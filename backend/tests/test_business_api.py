def test_asset_crud_inventory_and_exception_flow(client, admin_headers):
    payload = {
        "asset_code": "E2E-ASSET-001",
        "name": "测试设备",
        "category": "IT设备",
        "department": "测试部",
        "owner": "测试人",
        "location": "深圳",
        "status": "在用",
        "value": 1000,
    }
    created = client.post("/api/v1/assets", json=payload, headers=admin_headers)
    assert created.status_code == 201
    asset_id = created.json()["data"]["id"]
    assert client.post("/api/v1/assets", json=payload, headers=admin_headers).status_code == 409

    updated = client.patch(f"/api/v1/assets/{asset_id}", json={"status": "闲置"}, headers=admin_headers)
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "闲置"
    assert any(row["asset_code"] == "E2E-ASSET-001" for row in client.get("/api/v1/assets", headers=admin_headers).json()["data"])

    task = client.post("/api/v1/assets/inventory-tasks", json={"name": "测试盘点", "scope": "测试范围", "owner": "测试人", "due_date": "2026-08-20"}, headers=admin_headers)
    assert task.status_code == 201

    exceptions = client.get("/api/v1/assets/exceptions", headers=admin_headers).json()["data"]
    assert exceptions
    resolved = client.post(f"/api/v1/assets/exceptions/{exceptions[0]['id']}/resolve", json={"resolution": "完成复核"}, headers=admin_headers)
    assert resolved.status_code == 200
    assert resolved.json()["data"]["status"] == "已归档"


def test_recruitment_student_to_admin_flow_and_duplicate_rejection(client, admin_headers):
    jobs = client.get("/api/v1/recruitment/jobs?status=开放", headers=admin_headers).json()["data"]
    assert jobs
    job_id = jobs[0]["id"]
    payload = {
        "job_id": job_id,
        "name": "测试候选人",
        "email": "candidate@example.com",
        "phone": "17700000000",
        "school": "University of Malaya",
        "major": "Data Science",
        "graduation_year": 2027,
        "resume_text": "SQL; Python; B端产品项目",
        "cover_note": "申请实习",
    }
    created = client.post("/api/v1/recruitment/applications", json=payload, headers=admin_headers)
    assert created.status_code == 201
    assert client.post("/api/v1/recruitment/applications", json=payload, headers=admin_headers).status_code == 409
    application_id = created.json()["data"]["id"]

    changed = client.patch(f"/api/v1/recruitment/applications/{application_id}/status", json={"status": "待面试", "review_note": "通过人工初筛"}, headers=admin_headers)
    assert changed.status_code == 200
    assert changed.json()["data"]["status"] == "待面试"
    rows = client.get("/api/v1/recruitment/applications", headers=admin_headers).json()["data"]
    assert any(row["name"] == "测试候选人" and row["status"] == "待面试" for row in rows)
