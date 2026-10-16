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

    task = client.post("/api/v1/assets/inventory-tasks", json={"name": "测试盘点", "scope": "部门：测试部", "owner": "测试人", "due_date": "2026-08-20"}, headers=admin_headers)
    assert task.status_code == 201
    task_id = task.json()["data"]["id"]
    assert task.json()["data"]["total_count"] == 1

    started = client.post(f"/api/v1/assets/inventory-tasks/{task_id}/start", headers=admin_headers)
    assert started.status_code == 200
    assert started.json()["data"]["status"] == "进行中"

    records = client.get(f"/api/v1/assets/inventory-tasks/{task_id}/records", headers=admin_headers)
    assert records.status_code == 200
    assert records.json()["data"]
    assert {row["department"] for row in records.json()["data"]} == {"测试部"}
    record_id = records.json()["data"][0]["id"]

    checked = client.patch(
        f"/api/v1/assets/inventory-records/{record_id}",
        json={"result": "位置不符", "actual_location": "测试仓库", "remark": "现场位置与台账不一致"},
        headers=admin_headers,
    )
    assert checked.status_code == 200
    assert checked.json()["data"]["result"] == "位置不符"

    refreshed_task = next(row for row in client.get("/api/v1/assets/inventory-tasks", headers=admin_headers).json()["data"] if row["id"] == task_id)
    assert refreshed_task["checked_count"] == 1
    assert refreshed_task["exception_count"] == 1

    exceptions = client.get("/api/v1/assets/exceptions", headers=admin_headers).json()["data"]
    assert exceptions

    overview = client.get("/api/v1/assets/overview", headers=admin_headers)
    assert overview.status_code == 200
    overview_data = overview.json()["data"]
    assert overview_data["summary"]["asset_count"] >= 1
    assert 0 <= overview_data["summary"]["inventory_completion"] <= 100
    assert any(row["id"] == asset_id for row in overview_data["assets"])
    assert any(row["id"] == task_id for row in overview_data["tasks"])
    assert overview_data["exceptions"][0]["asset_code"] == "E2E-ASSET-001"
    assert overview_data["inventory_owners"]

    resolved = client.post(f"/api/v1/assets/exceptions/{exceptions[0]['id']}/resolve", json={"resolution": "完成复核"}, headers=admin_headers)
    assert resolved.status_code == 200
    assert resolved.json()["data"]["status"] == "已归档"


def test_management_write_endpoints_require_manage_permissions(client):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "employee01@demo.local", "password": "Demo@2026!"},
    )
    employee_headers = {
        "Authorization": f"Bearer {login.json()['data']['access_token']}"
    }

    asset = client.post(
        "/api/v1/assets",
        headers=employee_headers,
        json={
            "asset_code": "DENIED-ASSET-001",
            "name": "无权新增资产",
            "category": "IT设备",
            "department": "测试部",
            "owner": "员工一",
            "location": "深圳",
            "status": "在用",
            "value": 1000,
        },
    )
    inventory = client.post(
        "/api/v1/assets/inventory-tasks",
        headers=employee_headers,
        json={"name": "无权盘点", "scope": "全部资产", "owner": "员工一"},
    )
    recruitment = client.post(
        "/api/v1/recruitment/jobs",
        headers=employee_headers,
        json={
            "title": "无权新增岗位",
            "department": "测试部",
            "location": "深圳",
            "employment_type": "社招",
            "description": "权限测试",
            "requirements": "权限测试",
            "status": "开放",
        },
    )

    assert asset.status_code == 403
    assert inventory.status_code == 403
    assert recruitment.status_code == 403


def test_asset_import_preview_commit_and_qr_mobile_inventory(client, admin_headers):
    csv_content = (
        "资产编号,资产名称,类别,所属部门,责任人,位置,状态,资产价值\n"
        "BATCH-ASSET-001,批量导入笔记本,IT设备,测试部,员工一,上海,在用,8800\n"
        "BATCH-ASSET-002,批量导入显示器,办公设备,测试部,员工二,上海,在用,1200\n"
        "BYD-LAP-2026-001,重复资产,IT设备,测试部,员工三,上海,在用,100\n"
    )
    preview = client.post(
        "/api/v1/assets/import/preview",
        files={"file": ("assets.csv", csv_content.encode("utf-8"), "text/csv")},
        headers=admin_headers,
    )
    assert preview.status_code == 200
    rows = preview.json()["data"]["rows"]
    assert preview.json()["data"]["valid_count"] == 2
    assert rows[-1]["valid"] is False

    commit = client.post(
        "/api/v1/assets/import/commit",
        json={"rows": [row for row in rows if row["valid"]]},
        headers=admin_headers,
    )
    assert commit.status_code == 201
    assert commit.json()["data"]["created_count"] == 2

    asset = next(
        row
        for row in client.get("/api/v1/assets", headers=admin_headers).json()["data"]
        if row["asset_code"] == "BATCH-ASSET-001"
    )
    assert asset["asset_uuid"]

    qr = client.get(f"/api/v1/assets/{asset['id']}/qr", headers=admin_headers)
    assert qr.status_code == 200
    qr_data = qr.json()["data"]
    assert qr_data["asset_uuid"] == asset["asset_uuid"]
    assert qr_data["qr_image"].startswith("data:image/svg+xml")
    assert qr_data["mobile_url"].startswith("http")
    assert "/assets/mobile-inventory" in qr_data["mobile_url"]

    employee_login = client.post(
        "/api/v1/auth/login",
        json={"email": "employee01@demo.local", "password": "Demo@2026!"},
    )
    employee_headers = {
        "Authorization": f"Bearer {employee_login.json()['data']['access_token']}"
    }

    no_task_scan = client.post(
        "/api/v1/assets/mobile-inventory/scan",
        json={
            "asset_uuid": qr_data["asset_uuid"],
            "token": qr_data["token"],
            "result": "正常",
            "actual_location": "上海",
            "current_owner": "员工一",
            "photo_url": "data:image/jpeg;base64,AAAA",
        },
        headers=employee_headers,
    )
    assert no_task_scan.status_code == 409
    assert no_task_scan.json()["detail"] == "暂无进行中的盘点任务"

    inventory_task = client.post(
        "/api/v1/assets/inventory-tasks",
        json={"name": "批量资产扫码盘点", "scope": "部门：测试部", "owner": "员工一", "due_date": "2026-08-20"},
        headers=admin_headers,
    )
    assert inventory_task.status_code == 201
    task_id = inventory_task.json()["data"]["id"]
    assert client.post(f"/api/v1/assets/inventory-tasks/{task_id}/start", headers=admin_headers).status_code == 200

    mobile_before_scan = client.get(
        "/api/v1/assets/mobile-inventory/asset",
        params={"asset_uuid": qr_data["asset_uuid"], "token": qr_data["token"]},
        headers=employee_headers,
    )
    assert mobile_before_scan.status_code == 200
    assert mobile_before_scan.json()["data"]["locked"] is False
    assert mobile_before_scan.json()["data"]["active_record"]["result"] == "未盘点"

    scanned = client.post(
        "/api/v1/assets/mobile-inventory/scan",
        json={
            "asset_uuid": qr_data["asset_uuid"],
            "token": qr_data["token"],
            "task_id": task_id,
            "result": "正常",
            "actual_location": "上海",
            "current_owner": "员工一",
            "remark": "员工手机扫码自盘",
            "photo_url": "data:image/jpeg;base64,AAAA",
        },
        headers=employee_headers,
    )
    assert scanned.status_code == 200
    assert scanned.json()["data"]["photo_url"] == "data:image/jpeg;base64,AAAA"
    assert "员工一" in scanned.json()["data"]["remark"]

    duplicate_scan = client.post(
        "/api/v1/assets/mobile-inventory/scan",
        json={
            "asset_uuid": qr_data["asset_uuid"],
            "token": qr_data["token"],
            "task_id": task_id,
            "result": "正常",
            "actual_location": "上海",
            "current_owner": "员工一",
            "photo_url": "data:image/jpeg;base64,BBBB",
        },
        headers=employee_headers,
    )
    assert duplicate_scan.status_code == 409
    assert duplicate_scan.json()["detail"] == "本次盘点任务已完成，不能重复提交"

    mobile_asset = client.get(
        "/api/v1/assets/mobile-inventory/asset",
        params={"asset_uuid": qr_data["asset_uuid"], "token": qr_data["token"]},
        headers=employee_headers,
    )
    assert mobile_asset.status_code == 200
    assert mobile_asset.json()["data"]["asset"]["asset_code"] == "BATCH-ASSET-001"
    assert mobile_asset.json()["data"]["locked"] is True
    assert mobile_asset.json()["data"]["active_record"]["photo_url"] == "data:image/jpeg;base64,AAAA"

    abnormal_asset = next(
        row
        for row in client.get("/api/v1/assets", headers=admin_headers).json()["data"]
        if row["asset_code"] == "BATCH-ASSET-002"
    )
    abnormal_qr = client.get(f"/api/v1/assets/{abnormal_asset['id']}/qr", headers=admin_headers).json()["data"]
    abnormal_scan = client.post(
        "/api/v1/assets/mobile-inventory/scan",
        json={
            "asset_uuid": abnormal_qr["asset_uuid"],
            "token": abnormal_qr["token"],
            "task_id": task_id,
            "result": "损坏",
            "actual_location": "上海仓库",
            "current_owner": "员工二",
            "remark": "屏幕破损",
            "photo_url": "data:image/jpeg;base64,CCCC",
        },
        headers=employee_headers,
    )
    assert abnormal_scan.status_code == 200
    exceptions = client.get("/api/v1/assets/exceptions", headers=admin_headers).json()["data"]
    assert any(row["asset_code"] == "BATCH-ASSET-002" and row["type"] == "损坏" for row in exceptions)

    completed_task_scan = client.get(
        "/api/v1/assets/mobile-inventory/asset",
        params={"asset_uuid": qr_data["asset_uuid"], "token": qr_data["token"]},
        headers=employee_headers,
    )
    assert completed_task_scan.status_code == 200
    assert completed_task_scan.json()["data"]["active_record"] is None
    assert completed_task_scan.json()["data"]["message"] == "暂无进行中的盘点任务"

    next_task = client.post(
        "/api/v1/assets/inventory-tasks",
        json={"name": "下一轮扫码盘点", "scope": "部门：测试部", "owner": "员工一", "due_date": "2026-09-20"},
        headers=admin_headers,
    )
    next_task_id = next_task.json()["data"]["id"]
    assert client.post(f"/api/v1/assets/inventory-tasks/{next_task_id}/start", headers=admin_headers).status_code == 200
    next_scan = client.post(
        "/api/v1/assets/mobile-inventory/scan",
        json={
            "asset_uuid": qr_data["asset_uuid"],
            "token": qr_data["token"],
            "task_id": next_task_id,
            "result": "正常",
            "actual_location": "上海",
            "current_owner": "员工一",
            "photo_url": "data:image/jpeg;base64,DDDD",
        },
        headers=employee_headers,
    )
    assert next_scan.status_code == 200
    assert next_scan.json()["data"]["photo_url"] == "data:image/jpeg;base64,DDDD"

    rotated = client.post(f"/api/v1/assets/{asset['id']}/qr/rotate", headers=admin_headers)
    assert rotated.status_code == 200
    assert rotated.json()["data"]["token"] != qr_data["token"]
    old_scan = client.post(
        "/api/v1/assets/mobile-inventory/scan",
        json={
            "asset_uuid": qr_data["asset_uuid"],
            "token": qr_data["token"],
            "actual_location": "上海",
            "photo_url": "data:image/jpeg;base64,BBBB",
        },
        headers=employee_headers,
    )
    assert old_scan.status_code == 404


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


def test_recruitment_job_crud_and_delete_guard(client, admin_headers):
    created = client.post(
        "/api/v1/recruitment/jobs",
        json={
            "title": "测试岗位CRUD",
            "department": "人才发展部",
            "location": "Shanghai",
            "employment_type": "社招",
            "description": "负责招聘系统验收流程",
            "requirements": "熟悉岗位维护、候选人推进和面试协作",
            "status": "开放",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    job_id = created.json()["data"]["id"]

    updated = client.patch(
        f"/api/v1/recruitment/jobs/{job_id}",
        json={"title": "测试岗位CRUD-已编辑", "status": "暂停"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["title"] == "测试岗位CRUD-已编辑"
    assert updated.json()["data"]["status"] == "暂停"

    deleted = client.delete(f"/api/v1/recruitment/jobs/{job_id}", headers=admin_headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/recruitment/jobs/{job_id}", headers=admin_headers).status_code == 404

    guarded_job = client.get("/api/v1/recruitment/jobs?status=开放", headers=admin_headers).json()["data"][0]
    client.post(
        "/api/v1/recruitment/applications",
        json={
            "job_id": guarded_job["id"],
            "name": "岗位删除保护候选人",
            "email": "delete-guard@example.com",
            "resume_text": "岗位删除保护测试",
        },
        headers=admin_headers,
    )
    guarded = client.delete(f"/api/v1/recruitment/jobs/{guarded_job['id']}", headers=admin_headers)
    assert guarded.status_code == 409
    assert "不能删除" in guarded.json()["detail"]


def test_recruitment_ai_screening_is_explainable_and_human_reviewed(client, admin_headers):
    job_id = client.get("/api/v1/recruitment/jobs?status=开放", headers=admin_headers).json()["data"][0]["id"]
    created = client.post(
        "/api/v1/recruitment/applications",
        json={
            "job_id": job_id,
            "name": "AI筛选候选人",
            "email": "ai-screen@example.com",
            "school": "NUS",
            "major": "Information Systems",
            "graduation_year": 2027,
            "resume_text": "SQL Python RAG LLM B端产品 工作流 项目 原型 API Vue 沟通 协作",
        },
        headers=admin_headers,
    )
    application_id = created.json()["data"]["id"]
    screened = client.post(
        f"/api/v1/recruitment/applications/{application_id}/screen",
        headers=admin_headers,
    )
    assert screened.status_code == 200
    data = screened.json()["data"]
    assert data["ai_status"] == "已筛选"
    assert data["ai_score"] >= 70
    assert data["status"] == "待初筛"
    assert data["ai_evidence"]["human_review_required"] is True
    assert data["ai_evidence"]["interview_questions"]


def test_public_recruitment_only_exposes_open_jobs_and_application_submission(client):
    jobs = client.get("/api/v1/recruitment/public/jobs")
    assert jobs.status_code == 200
    assert jobs.json()["data"]
    assert all(row["status"] == "开放" for row in jobs.json()["data"])

    job_id = jobs.json()["data"][0]["id"]
    submitted = client.post(
        "/api/v1/recruitment/public/applications",
        json={
            "job_id": job_id,
            "name": "公开投递候选人",
            "email": "public-candidate@example.com",
            "resume_text": "企业AI产品项目",
        },
    )
    assert submitted.status_code == 201
    assert submitted.json()["data"] == {"application_id": submitted.json()["data"]["application_id"], "status": "待初筛"}

    assert client.get("/api/v1/recruitment/applications").status_code == 401
