# Real-Data Asset and Recruitment MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将全资产管理和招聘系统从前端假数据展示改造成后端 SQLite 持久化、前后端分离、可操作的多页面 MVP。

**Architecture:** 在现有 FastAPI + SQLAlchemy + SQLite 基础上增加独立的资产与招聘领域模型和 API 路由。Vue 页面通过 Axios 请求 API，资产系统按台账/盘点/异常拆页，招聘系统按学生端/管理端拆页；所有新增、编辑、投递和状态变更都以数据库返回值为准。

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue, Axios, FastAPI, Pydantic v2, SQLAlchemy 2, SQLite, Pytest, Playwright。

## Global Constraints

- 不在 Vue 中硬编码业务列表。
- 不接入 AI、RAG、Copilot、Agent。
- 不重做企业 IT 服务台。
- 继续使用本地演示登录和现有权限体系。
- 所有写接口提交数据库事务后返回最新记录。
- 删除、重复资产编号、重复投递由后端校验。
- 使用 Ant Design Vue 统一页面风格。
- HTML 原型在中途交付，可通过本地浏览器查看。

### Task 1: 建立领域模型与数据库种子

**Files:**
- Create: `backend/app/business/__init__.py`
- Create: `backend/app/business/models.py`
- Create: `backend/app/business/schemas.py`
- Modify: `backend/app/db/seed.py`
- Test: `backend/tests/test_business_models.py`

**Interfaces:**
- `Asset`, `InventoryTask`, `InventoryRecord`, `AssetException`, `JobOpening`, `CandidateApplication` SQLAlchemy models。
- `asset_to_dict`, `inventory_task_to_dict`, `exception_to_dict`, `job_to_dict`, `application_to_dict` 序列化函数。
- `initialize_database()` 首次运行写入数据库中的可操作演示记录，不覆盖已有业务数据。

- [ ] **Step 1: Write failing model and seed tests**

```python
def test_business_tables_are_created_and_seeded(client):
    response = client.get("/api/v1/assets")
    assert response.status_code == 200
    assert response.json()["data"]

def test_recruitment_jobs_are_seeded(client):
    response = client.get("/api/v1/recruitment/jobs")
    assert response.status_code == 200
    assert response.json()["data"]
```

- [ ] **Step 2: Run tests and confirm missing business routes/models fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_business_models.py -q`

Expected: FAIL because business models and routes do not exist.

- [ ] **Step 3: Add models and explicit schemas**

Use typed SQLAlchemy fields matching the design document. Use string statuses: asset `在用/闲置/维修中/待处置`, inventory `草稿/进行中/已完成`, exception `待核实/处理中/已归档`, job `开放/暂停`, application `待初筛/待面试/已通过/不合适`.

- [ ] **Step 4: Add idempotent seed records**

Seed only when each table is empty. Use stable business identifiers such as `BYD-LAP-2026-001`, `INV-2026-07-SZ`, `JOB-AIPM-001`. Do not delete or overwrite user-created rows.

- [ ] **Step 5: Run model tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_business_models.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/business backend/app/db/seed.py backend/tests/test_business_models.py
git commit -m "feat: add asset and recruitment business models"
```

### Task 2: Implement asset management API

**Files:**
- Create: `backend/app/business/asset_router.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_asset_api.py`

**Interfaces:**
- `GET /api/v1/assets/summary`
- `GET /api/v1/assets`
- `POST /api/v1/assets`
- `PATCH /api/v1/assets/{id}`
- `DELETE /api/v1/assets/{id}`
- `GET /api/v1/assets/inventory-tasks`
- `POST /api/v1/assets/inventory-tasks`
- `PATCH /api/v1/assets/inventory-tasks/{id}`
- `GET /api/v1/assets/exceptions`
- `POST /api/v1/assets/exceptions/{id}/resolve`

- [ ] **Step 1: Write API tests for read and write flows**

```python
def test_asset_crud_and_duplicate_code_are_rejected(client):
    payload = {"asset_code": "TEST-001", "name": "测试设备", "category": "IT设备", "department": "测试部", "owner": "测试人", "location": "深圳", "status": "在用", "value": 1000}
    assert client.post("/api/v1/assets", json=payload).status_code == 201
    assert client.post("/api/v1/assets", json=payload).status_code == 409

def test_inventory_task_and_exception_resolution(client):
    task = client.post("/api/v1/assets/inventory-tasks", json={"name": "测试盘点", "scope": "测试范围", "owner": "测试人", "due_date": "2026-08-20"})
    assert task.status_code == 201
    exceptions = client.get("/api/v1/assets/exceptions").json()["data"]
    if exceptions:
        resolved = client.post(f"/api/v1/assets/exceptions/{exceptions[0]['id']}/resolve", json={"resolution": "完成复核"})
        assert resolved.status_code == 200
```

- [ ] **Step 2: Run tests and confirm they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_asset_api.py -q`

Expected: FAIL because endpoints do not exist.

- [ ] **Step 3: Implement validated CRUD endpoints**

Require the existing authenticated user. Query filters support `keyword`, `status`, `category`, and `department`. Return `{ "data": ... }` consistently. Check asset code uniqueness before insert/update. Use 404 for missing records and 409 for duplicate codes.

- [ ] **Step 4: Implement inventory and exception endpoints**

Creating a task stores a real task. Updating a task stores status and checked count. Resolving an exception stores resolution, resolver name, resolver ID, timestamp, and status `已归档`.

- [ ] **Step 5: Run asset API tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_asset_api.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/business/asset_router.py backend/app/api/v1/router.py backend/tests/test_asset_api.py
git commit -m "feat: add persistent asset management APIs"
```

### Task 3: Implement recruitment API

**Files:**
- Create: `backend/app/business/recruitment_router.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_recruitment_api.py`

**Interfaces:**
- `GET /api/v1/recruitment/jobs`
- `POST /api/v1/recruitment/jobs`
- `PATCH /api/v1/recruitment/jobs/{id}`
- `GET /api/v1/recruitment/jobs/{id}`
- `POST /api/v1/recruitment/applications`
- `GET /api/v1/recruitment/applications`
- `GET /api/v1/recruitment/applications/{id}`
- `PATCH /api/v1/recruitment/applications/{id}/status`

- [ ] **Step 1: Write recruitment flow tests**

```python
def test_student_can_apply_and_admin_can_update_status(client):
    jobs = client.get("/api/v1/recruitment/jobs?status=开放").json()["data"]
    job_id = jobs[0]["id"]
    payload = {"job_id": job_id, "name": "真实测试候选人", "email": "candidate@example.com", "phone": "17700000000", "school": "University of Malaya", "major": "Data Science", "graduation_year": 2027, "resume_text": "SQL; Python; B端产品项目", "cover_note": "申请实习"}
    application = client.post("/api/v1/recruitment/applications", json=payload)
    assert application.status_code == 201
    application_id = application.json()["data"]["id"]
    changed = client.patch(f"/api/v1/recruitment/applications/{application_id}/status", json={"status": "待面试", "review_note": "通过人工初筛"})
    assert changed.status_code == 200

def test_duplicate_application_is_rejected(client):
    response = client.post("/api/v1/recruitment/applications", json={"job_id": 1, "name": "重复候选人", "email": "existing@example.com"})
    assert response.status_code in (201, 409)
```

- [ ] **Step 2: Run tests and confirm they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_recruitment_api.py -q`

Expected: FAIL because recruitment endpoints do not exist.

- [ ] **Step 3: Implement job APIs**

Allow admin users to create/update jobs. Public student page reads only `开放` jobs; management query can include `暂停`. Validate non-empty title, description, and requirements.

- [ ] **Step 4: Implement application APIs**

Validate email, required name/job/email fields, job existence, and duplicate `(job_id, email)` before insert. Management list supports job and status filters. Status changes record reviewer identity and time.

- [ ] **Step 5: Run recruitment API tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_recruitment_api.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/business/recruitment_router.py backend/app/api/v1/router.py backend/tests/test_recruitment_api.py
git commit -m "feat: add persistent recruitment APIs"
```

### Task 4: Deliver the first HTML prototype checkpoint

**Files:**
- Create: `artifacts/real-data-mvp-prototype.html`
- Modify: `README.md`

- [ ] **Step 1: Build a standalone clickable HTML prototype**

Include separate sections for asset overview, asset ledger, inventory tasks, exceptions, student job list, application form, admin jobs, and candidate pool. Use local in-memory interaction only for visual review; clearly label it as prototype and do not use it as production data.

- [ ] **Step 2: Verify the prototype**

Open the file in Chrome and verify that navigation, tabs, forms, and dialogs respond. The prototype is a visual checkpoint only; the Vue application remains the source of truth.

- [ ] **Step 3: Commit**

```bash
git add artifacts/real-data-mvp-prototype.html README.md
git commit -m "docs: add clickable real-data MVP prototype"
```

### Task 5: Replace asset frontend arrays with API-backed pages

**Files:**
- Modify: `frontend/src/views/AssetManagementView.vue`
- Create: `frontend/src/views/assets/AssetLedgerView.vue`
- Create: `frontend/src/views/assets/InventoryTaskView.vue`
- Create: `frontend/src/views/assets/AssetExceptionView.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/tests/e2e/asset-management-real-data.spec.ts`

- [ ] **Step 1: Add E2E tests for real interactions**

```ts
test('asset records are loaded from API and new asset appears in ledger', async ({ page }) => {
  await page.goto('/modules/asset-management')
  await expect(page.getByText('资产台账')).toBeVisible()
  await page.getByRole('button', { name: '新增资产' }).click()
  await page.getByLabel('资产编号').fill('E2E-ASSET-001')
  await page.getByLabel('资产名称').fill('E2E测试设备')
  await page.getByRole('button', { name: '保存资产' }).click()
  await expect(page.getByText('E2E-ASSET-001')).toBeVisible()
})
```

- [ ] **Step 2: Run the E2E test and confirm it fails**

Run: `cd frontend; npm.cmd run test:e2e -- tests/e2e/asset-management-real-data.spec.ts`

Expected: FAIL because the current page uses local arrays and has no working form.

- [ ] **Step 3: Split pages and load API data**

Use `api.get`, `api.post`, `api.patch`, and `api.delete`. Add loading, empty, error, and success states. Keep all display text in Chinese and all page styling within the existing Ant Design Vue system.

- [ ] **Step 4: Add working asset drawer and task/exception actions**

Validate fields before submit. After a successful mutation, reload the affected table from the API. Add delete confirmation and exception resolve confirmation.

- [ ] **Step 5: Run frontend typecheck/build/E2E**

Run: `cd frontend; npm.cmd run typecheck; npm.cmd run build; npm.cmd run test:e2e -- tests/e2e/asset-management-real-data.spec.ts`

Expected: all commands pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/AssetManagementView.vue frontend/src/views/assets frontend/src/router/index.ts frontend/src/api/client.ts frontend/tests/e2e/asset-management-real-data.spec.ts
git commit -m "feat: connect asset pages to persistent APIs"
```

### Task 6: Replace recruitment frontend arrays with separated student/admin pages

**Files:**
- Modify: `frontend/src/views/ResumeScreeningView.vue`
- Create: `frontend/src/views/recruitment/RecruitmentStudentView.vue`
- Create: `frontend/src/views/recruitment/RecruitmentAdminView.vue`
- Create: `frontend/src/views/recruitment/RecruitmentApplicationView.vue`
- Modify: `frontend/src/router/index.ts`
- Test: `frontend/tests/e2e/recruitment-real-data.spec.ts`

- [ ] **Step 1: Add E2E tests for student-to-admin flow**

```ts
test('student application appears in admin candidate pool', async ({ page }) => {
  await page.goto('/recruitment/student')
  await page.getByRole('button', { name: '查看详情' }).first().click()
  await page.getByRole('button', { name: '立即投递' }).click()
  await page.getByLabel('姓名').fill('E2E候选人')
  await page.getByLabel('邮箱').fill('e2e@example.com')
  await page.getByRole('button', { name: '提交投递' }).click()
  await expect(page.getByText('投递成功')).toBeVisible()

  await page.goto('/recruitment/admin')
  await expect(page.getByText('E2E候选人')).toBeVisible()
})
```

- [ ] **Step 2: Run the E2E test and confirm it fails**

Run: `cd frontend; npm.cmd run test:e2e -- tests/e2e/recruitment-real-data.spec.ts`

Expected: FAIL because the current recruitment page is one mixed view and does not persist applications.

- [ ] **Step 3: Create separate student and admin routes**

Student route lists only open jobs and owns application form/records. Admin route lists all jobs and candidate applications, with status filters. Keep the old module route as a compatibility entry that links to the two new pages.

- [ ] **Step 4: Implement job editor and application flow**

Use Ant Design Vue Drawer/Modal. Submit applications through the API. Show duplicate-application errors from the server. Admin status changes use a select plus review note and reload the candidate row.

- [ ] **Step 5: Run frontend typecheck/build/E2E**

Run: `cd frontend; npm.cmd run typecheck; npm.cmd run build; npm.cmd run test:e2e -- tests/e2e/recruitment-real-data.spec.ts`

Expected: all commands pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/ResumeScreeningView.vue frontend/src/views/recruitment frontend/src/router/index.ts frontend/tests/e2e/recruitment-real-data.spec.ts
git commit -m "feat: add separated recruitment student and admin flows"
```

### Task 7: Full verification and business walkthrough

**Files:**
- Modify: `README.md`
- Test: `frontend/tests/e2e/business-modules.spec.ts`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Run backend full suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests -q`

Expected: PASS.

- [ ] **Step 2: Run frontend full suite and build**

Run: `cd frontend; npm.cmd run typecheck; npm.cmd run build; npm.cmd run test:e2e`

Expected: PASS.

- [ ] **Step 3: Perform Chrome business walkthrough**

Verify these exact flows: create asset, edit asset, filter ledger, create inventory task, resolve exception, browse open job, submit application, view application in admin, change candidate status.

- [ ] **Step 4: Update README with URLs and test login**

Document frontend URL, API URL, demo accounts, HTML prototype path, and the fact that data is stored in SQLite.

- [ ] **Step 5: Commit final verification updates**

```bash
git add README.md frontend/tests/e2e/business-modules.spec.ts backend/tests/test_api.py
git commit -m "test: verify real-data asset and recruitment flows"
```
