# Unified Approval Process App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the separate approval-type, form-template, and flow-template administration with one versioned low-code process application, add flexible employee approvers and read-only process monitoring, and unify the complete suite under Ant Design Vue.

**Architecture:** The backend introduces versioned `ProcessApp` and `ProcessVersion` aggregates, a pure validation/path-resolution engine, and separate employee/admin API routers. Submission resolves a DAG condition path once and snapshots the applicant, form, and approval route. The Vue frontend uses one Ant Design Vue theme and shared approval components for process editing, dynamic forms, and monitoring.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic, SQLite, pytest, Vue 3, TypeScript, Vite, Pinia, Vue Router, Axios, Ant Design Vue, ECharts, Playwright.

## Global Constraints

- Use Ant Design Vue for buttons, forms, tables, cards, statistics, steps, drawers, modals, tags, alerts, empty states, descriptions, and pagination whenever a matching component exists.
- Apply one `ConfigProvider` theme to every module: Ant primary blue `#1677ff`, neutral layout background `#f5f5f5`, dark Ant sidebar `#001529`, 6px component radius, and standard system Chinese fonts.
- Do not implement new page, function, or data-permission separation; retain the existing `approval:view` and `approval:manage` guards.
- Do not implement manager hierarchy or a department tree. Process authors select any active employee as approver.
- `position` is required when creating or updating an approval user.
- Flow MVP supports serial approval, countersign, and simple conditional branches in a directed acyclic graph.
- Process monitoring is read-only; it cannot urge, transfer, force-approve, or terminate requests.
- Back up `backend/approval.db` before the one-time production migration. Never delete it from ordinary application startup.
- Preserve the leave, expense, and purchase examples as published `v1` process applications.
- Add no AI, RAG, Copilot, or Agent behavior in this implementation.

---

## Planned File Structure

### Backend

- Modify `backend/app/approval/models.py`: unified persistence models and request snapshots.
- Create `backend/app/approval/schemas.py`: typed API payloads and schema contracts.
- Create `backend/app/approval/engine.py`: definition validation, condition evaluation, and path resolution.
- Create `backend/app/approval/serializers.py`: stable API response construction.
- Modify `backend/app/approval/router.py`: employee request and task APIs using process apps.
- Create `backend/app/approval/admin_router.py`: users, process apps, versions, and monitoring APIs.
- Modify `backend/app/approval/seed.py`: seed active users with positions and three published process apps.
- Modify `backend/app/main.py`: register the new admin router.
- Create `backend/scripts/migrate_approval_v2.py`: backup-first one-time migration.
- Modify `backend/tests/conftest.py`: clean v2 database setup.
- Replace `backend/tests/test_approval.py`: runtime behavior tests.
- Create `backend/tests/test_process_engine.py`: pure engine tests.
- Create `backend/tests/test_process_admin.py`: app lifecycle, user, and monitoring tests.

### Frontend

- Modify `frontend/src/App.vue`: global Ant Design Vue `ConfigProvider`.
- Modify `frontend/src/styles.css`: shared Ant-style layout tokens and responsive rules.
- Modify `frontend/src/layouts/AppLayout.vue`: three approval admin entries and consistent icons.
- Modify `frontend/src/router/index.ts`: new admin routes and removal of legacy template routes.
- Create `frontend/src/types/approval.ts`: process, schema, user, request, and monitor contracts.
- Modify `frontend/src/types.ts`: re-export approval contracts and add user position.
- Create `frontend/src/components/approval/ProcessStatusTag.vue`: shared status presentation.
- Create `frontend/src/components/approval/FormSchemaDesigner.vue`: component-based form designer.
- Create `frontend/src/components/approval/FlowSchemaDesigner.vue`: serial/countersign/condition DAG editor.
- Create `frontend/src/components/approval/DynamicApprovalForm.vue`: employee form renderer.
- Create `frontend/src/views/approval/AdminUsers.vue`: user CRUD with required position.
- Create `frontend/src/views/approval/AdminProcessApps.vue`: process list and lifecycle actions.
- Create `frontend/src/views/approval/AdminProcessEditor.vue`: four-step editor and publish validation.
- Create `frontend/src/views/approval/AdminProcessMonitor.vue`: summary, filters, table, and detail drawer.
- Modify `frontend/src/views/approval/ApprovalNew.vue`: published-app selection and dynamic submission.
- Modify `frontend/src/views/approval/ApprovalDetail.vue`: version and snapshot display.
- Delete legacy admin views after router replacement: `AdminTypes.vue`, `AdminFormTemplates.vue`, `AdminFlowTemplates.vue`, `AdminLogs.vue`, `AdminRoles.vue`.
- Modify `frontend/tests/e2e/foundation.spec.ts`: new navigation and global UI checks.
- Create `frontend/tests/e2e/process-app.spec.ts`: end-to-end low-code and request flow.

---

### Task 1: Unified Persistence Models and Seed Data

**Files:**
- Modify: `backend/app/approval/models.py`
- Modify: `backend/app/approval/seed.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_process_admin.py`

**Interfaces:**
- Produces: `ProcessApp`, `ProcessVersion`, updated `ApprovalUser`, `ApprovalRequest`, and `ApprovalNode` ORM classes.
- Produces: three published process apps with immutable `v1` definitions.

- [ ] **Step 1: Write failing persistence tests**

```python
def test_seed_creates_three_published_process_apps(db_session):
    apps = db_session.scalars(select(ProcessApp).order_by(ProcessApp.code)).all()
    assert [app.code for app in apps] == ["expense", "leave", "purchase"]
    assert all(app.status == "published" for app in apps)
    assert all(app.current_version_id for app in apps)


def test_seed_users_have_required_positions(db_session):
    users = db_session.scalars(select(ApprovalUser)).all()
    assert users
    assert all(user.position.strip() for user in users)
```

- [ ] **Step 2: Run the tests and verify model failures**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_admin.py -q`

Expected: FAIL because `ProcessApp`, `ProcessVersion`, and `ApprovalUser.position` do not exist.

- [ ] **Step 3: Implement the v2 models**

Use these persisted contracts:

```python
class ProcessApp(ApprovalBase):
    __tablename__ = "process_apps"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80), default="通用审批")
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    current_version_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class ProcessVersion(ApprovalBase):
    __tablename__ = "process_versions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    process_app_id: Mapped[int] = mapped_column(Integer, index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    form_schema: Mapped[dict] = mapped_column(JSON)
    flow_schema: Mapped[dict] = mapped_column(JSON)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
```

Add `ApprovalUser.position`, request app/version IDs, applicant/form snapshots, `idempotency_key`, and node `node_key`/`timeout_hours`. Seed the three examples using stable field and node IDs.

- [ ] **Step 4: Run focused tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_admin.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/approval/models.py backend/app/approval/seed.py backend/tests/conftest.py backend/tests/test_process_admin.py
git commit -m "feat: add unified approval process models"
```

### Task 2: Definition Validation and Conditional Path Engine

**Files:**
- Create: `backend/app/approval/schemas.py`
- Create: `backend/app/approval/engine.py`
- Test: `backend/tests/test_process_engine.py`

**Interfaces:**
- Produces: `validate_process_definition(form_schema, flow_schema, active_user_ids) -> list[DefinitionError]`.
- Produces: `resolve_execution_path(form_data, flow_schema) -> list[dict]`.

- [ ] **Step 1: Write failing engine tests**

```python
def test_amount_condition_selects_high_value_branch():
    path = resolve_execution_path({"amount": 120000}, FLOW_WITH_AMOUNT_BRANCH)
    assert [node["id"] for node in path] == ["manager", "director", "finance"]


def test_validator_rejects_cycle_and_inactive_approver():
    errors = validate_process_definition(FORM_SCHEMA, CYCLIC_FLOW, {"active-user"})
    assert {error.code for error in errors} == {"flow_cycle", "inactive_approver"}


def test_default_branch_is_required():
    errors = validate_process_definition(FORM_SCHEMA, FLOW_WITHOUT_DEFAULT, {"u1"})
    assert any(error.code == "missing_default_branch" for error in errors)
```

- [ ] **Step 2: Run and verify failures**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_engine.py -q`

Expected: FAIL because the engine module does not exist.

- [ ] **Step 3: Implement pure validation and traversal**

```python
@dataclass(frozen=True)
class DefinitionError:
    code: str
    message: str
    target_id: str | None = None


def compare_value(actual: object, operator: str, expected: object) -> bool:
    operations = {
        "eq": lambda a, b: a == b,
        "ne": lambda a, b: a != b,
        "gt": lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
        "lt": lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
        "contains": lambda a, b: str(b) in str(a),
        "not_contains": lambda a, b: str(b) not in str(a),
    }
    return operations[operator](actual, expected)
```

Validate stable IDs, field references, approvers, graph connectivity, DAG cycles, start/end nodes, countersign cardinality, default branches, and all paths reaching end. Resolve condition edges in declared order and exclude start/condition/end nodes from the returned approval path.

- [ ] **Step 4: Run engine tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_engine.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/approval/schemas.py backend/app/approval/engine.py backend/tests/test_process_engine.py
git commit -m "feat: validate and resolve approval process graphs"
```

### Task 3: Process Application and User Administration APIs

**Files:**
- Create: `backend/app/approval/admin_router.py`
- Create: `backend/app/approval/serializers.py`
- Modify: `backend/app/approval/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_process_admin.py`

**Interfaces:**
- Produces: `/api/v1/admin/process-apps`, `/process-apps/{id}`, `/publish`, `/copy`, `/deactivate`.
- Produces: `/api/v1/admin/users` GET/POST/PUT with position and active status.

- [ ] **Step 1: Add failing lifecycle and user API tests**

```python
def test_admin_creates_draft_and_publishes_version(client, admin_headers, valid_definition):
    created = client.post("/api/v1/admin/process-apps", headers=admin_headers, json=valid_definition)
    assert created.status_code == 201
    app_id = created.json()["data"]["id"]
    published = client.post(f"/api/v1/admin/process-apps/{app_id}/publish", headers=admin_headers)
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "published"
    assert published.json()["data"]["version_number"] == 1


def test_position_is_required_when_creating_user(client, admin_headers):
    response = client.post("/api/v1/admin/users", headers=admin_headers, json={
        "display_name": "测试员工", "email": "new@example.com", "department": "研发部", "role": "员工"
    })
    assert response.status_code == 422
```

- [ ] **Step 2: Run and verify 404/422 failures**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_admin.py -q`

Expected: FAIL because the new endpoints are missing.

- [ ] **Step 3: Implement typed admin endpoints**

Use `ProcessAppCreate`, `ProcessAppUpdate`, `ApprovalUserCreate`, and `ApprovalUserUpdate` Pydantic models. Remove the legacy `/approval-types`, `/form-templates`, `/flow-templates`, `/users`, and `/logs` admin handlers from `router.py` in the same task before registering `admin_router.py`, so FastAPI never has duplicate `/api/v1/admin/users` routes. Publishing calls `validate_process_definition`; when errors exist, return HTTP 422 as:

```json
{"detail":{"code":"definition_invalid","errors":[{"code":"missing_approver","message":"审批节点未选择审批人","target_id":"node-2"}]}}
```

Editing a published app creates the next draft version. Copying creates a new draft app with a unique `-copy` code. Deactivation changes only the app status.

- [ ] **Step 4: Run admin tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_admin.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/approval/admin_router.py backend/app/approval/serializers.py backend/app/approval/router.py backend/app/main.py backend/tests/test_process_admin.py
git commit -m "feat: add process application administration APIs"
```

### Task 4: Runtime Submission and Approval Tasks

**Files:**
- Modify: `backend/app/approval/router.py`
- Test: `backend/tests/test_approval.py`

**Interfaces:**
- Produces: `GET /api/v1/approvals/apps` and `POST /api/v1/approvals/requests` with `process_app_id`, `form_data`, and `idempotency_key`.
- Preserves: pending, handled, detail, approve, reject, transfer, revoke, and urge behavior.

- [ ] **Step 1: Replace runtime tests with process-app scenarios**

```python
def test_submit_snapshots_applicant_and_resolved_high_value_path(client, admin_headers):
    response = client.post("/api/v1/approvals/requests", headers=admin_headers, json={
        "process_app_id": 3,
        "title": "高额采购",
        "form_data": {"amount": 120000, "item_name": "服务器"},
        "idempotency_key": "purchase-001",
    })
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["applicant_snapshot"]["position"]
    assert [node["node_key"] for node in data["nodes"]] == ["manager", "director", "finance"]


def test_duplicate_idempotency_key_returns_same_request(client, admin_headers):
    first = client.post("/api/v1/approvals/requests", headers=admin_headers, json=REQUEST_BODY)
    second = client.post("/api/v1/approvals/requests", headers=admin_headers, json=REQUEST_BODY)
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
```

- [ ] **Step 2: Run and verify old-contract failures**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_approval.py -q`

Expected: FAIL because runtime still expects `type_id`.

- [ ] **Step 3: Implement snapshot-based runtime**

Replace approval-type lookup with the current published process version. Validate form data, resolve the branch once, snapshot applicant/form/flow, and expand only approval nodes from the selected path. Preserve current-node authorization and transaction boundaries.

- [ ] **Step 4: Run runtime tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_approval.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/approval/router.py backend/tests/test_approval.py
git commit -m "feat: run approvals from versioned process apps"
```

### Task 5: Read-Only Monitoring APIs

**Files:**
- Modify: `backend/app/approval/admin_router.py`
- Test: `backend/tests/test_process_admin.py`

**Interfaces:**
- Produces: `GET /api/v1/admin/process-monitor/summary`.
- Produces: paginated `GET /api/v1/admin/process-monitor/requests`.

- [ ] **Step 1: Add failing monitor tests**

```python
def test_monitor_filters_pending_requests_and_reports_overdue(client, admin_headers, overdue_request):
    summary = client.get("/api/v1/admin/process-monitor/summary", headers=admin_headers)
    assert summary.status_code == 200
    assert summary.json()["data"]["overdue"] == 1
    rows = client.get(
        "/api/v1/admin/process-monitor/requests?status=pending&overdue=true&page=1&page_size=20",
        headers=admin_headers,
    )
    assert rows.json()["data"]["total"] == 1
```

- [ ] **Step 2: Run and verify endpoint failures**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_admin.py -q`

Expected: FAIL with 404 for monitor endpoints.

- [ ] **Step 3: Implement summary and paginated filters**

Return summary keys `total`, `pending`, `approved`, `rejected`, `revoked`, and `overdue`. Filters are `process_app_id`, `status`, `submitted_from`, `submitted_to`, `department`, `applicant`, `current_approver_id`, and `overdue`. Overdue means the current pending node has `timeout_hours > 0` and its age exceeds that value.

- [ ] **Step 4: Run monitor tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_admin.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/approval/admin_router.py backend/tests/test_process_admin.py
git commit -m "feat: add read-only approval process monitoring"
```

### Task 6: Global Ant Design Vue UI Foundation

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/layouts/AppLayout.vue`
- Modify: `frontend/src/views/DashboardView.vue`
- Modify: `frontend/src/views/ModuleView.vue`
- Modify: `frontend/src/views/LoginView.vue`
- Modify: `frontend/src/views/NotificationsView.vue`
- Modify: `frontend/src/views/AIRunsView.vue`
- Modify: `frontend/src/views/AuditLogsView.vue`
- Modify: `frontend/src/views/ProfileView.vue`
- Modify: `frontend/src/views/approval/ApprovalHome.vue`
- Modify: `frontend/src/views/approval/ApprovalMyRequests.vue`
- Modify: `frontend/src/views/approval/ApprovalPending.vue`
- Modify: `frontend/src/views/approval/ApprovalHandled.vue`
- Test: `frontend/tests/e2e/foundation.spec.ts`

**Interfaces:**
- Produces: one global theme and consistent page surfaces for all modules.
- Preserves existing admin routes until their replacement pages exist in Tasks 7, 8, and 12.

- [ ] **Step 1: Add failing UI contract assertions**

```ts
await expect(page.locator('.ant-layout-sider')).toHaveCSS('background-color', 'rgb(0, 21, 41)')
await expect(page.locator('.ant-card').first()).toBeVisible()
await expect(page.locator('.ant-btn-primary').first()).toHaveCSS('background-color', 'rgb(22, 119, 255)')
```

- [ ] **Step 2: Run the E2E test and verify failures**

Run: `cd frontend; npm.cmd run test:e2e -- foundation.spec.ts`

Expected: FAIL because the old teal shell and custom module cards remain.

- [ ] **Step 3: Apply the global Ant theme**

```vue
<script setup lang="ts">
import zhCN from 'ant-design-vue/es/locale/zh_CN'

const theme = {
  token: {
    colorPrimary: '#1677ff',
    colorBgLayout: '#f5f5f5',
    borderRadius: 6,
    fontFamily: '"Segoe UI", "Microsoft YaHei", sans-serif',
  },
}
</script>

<template>
  <a-config-provider :locale="zhCN" :theme="theme">
    <router-view />
  </a-config-provider>
</template>
```

Set sidebar to `#001529`, remove module-specific dominant accent styling, and standardize page width, typography, spacing, loading, empty, and error states. Convert dashboard, generic module, login, notification, AI run, audit, profile, approval home, request list, pending, and handled surfaces to Ant `a-card`, `a-statistic`, `a-table`, `a-list`, `a-tag`, `a-alert`, `a-empty`, `a-skeleton`, and `a-space` components. Keep the existing admin route targets until their replacement pages are created. Do not place cards inside cards.

- [ ] **Step 4: Run typecheck and foundation E2E**

Run: `cd frontend; npm.cmd run typecheck; npm.cmd run test:e2e -- foundation.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/App.vue frontend/src/styles.css frontend/src/layouts/AppLayout.vue frontend/src/views/DashboardView.vue frontend/src/views/ModuleView.vue frontend/src/views/LoginView.vue frontend/src/views/NotificationsView.vue frontend/src/views/AIRunsView.vue frontend/src/views/AuditLogsView.vue frontend/src/views/ProfileView.vue frontend/src/views/approval/ApprovalHome.vue frontend/src/views/approval/ApprovalMyRequests.vue frontend/src/views/approval/ApprovalPending.vue frontend/src/views/approval/ApprovalHandled.vue frontend/tests/e2e/foundation.spec.ts
git commit -m "style: unify suite with Ant Design Vue"
```

### Task 7: Frontend Approval Types and User Management

**Files:**
- Create: `frontend/src/types/approval.ts`
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/views/approval/AdminUsers.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/AppLayout.vue`

**Interfaces:**
- Produces: `ApprovalUser`, `ProcessApp`, `ProcessVersion`, `FormSchema`, `FlowSchema`, `ApprovalRequestDetail`, and monitor types.
- Consumes: `/api/v1/admin/users`.

- [ ] **Step 1: Add a failing E2E user creation scenario**

```ts
await page.goto('/admin/users')
await page.getByRole('button', { name: '新增员工' }).click()
await page.getByRole('button', { name: '保存' }).click()
await expect(page.getByText('请输入职位')).toBeVisible()
```

- [ ] **Step 2: Run and verify route/page failure**

Run: `cd frontend; npm.cmd run test:e2e -- process-app.spec.ts`

Expected: FAIL because `/admin/users` and the page do not exist.

- [ ] **Step 3: Implement contracts and Ant user page**

Use `a-card`, `a-table`, `a-form`, `a-input`, `a-select`, `a-switch`, `a-modal`, `a-tag`, and `a-popconfirm`. Replace the old role-management route/menu entry with `/admin/users` only after `AdminUsers.vue` exists. The form model is:

```ts
type UserForm = {
  display_name: string
  email: string
  department: string
  position: string
  role: string
  is_active: boolean
}
```

Validate all five text fields before POST/PUT. Deactivation replaces destructive deletion in the normal UI.

- [ ] **Step 4: Run typecheck and focused E2E**

Run: `cd frontend; npm.cmd run typecheck; npm.cmd run test:e2e -- process-app.spec.ts`

Expected: user scenario PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/types/approval.ts frontend/src/types.ts frontend/src/views/approval/AdminUsers.vue frontend/src/router/index.ts frontend/src/layouts/AppLayout.vue frontend/tests/e2e/process-app.spec.ts
git commit -m "feat: add approval user administration"
```

### Task 8: Process Application List and Lifecycle UI

**Files:**
- Create: `frontend/src/components/approval/ProcessStatusTag.vue`
- Create: `frontend/src/views/approval/AdminProcessApps.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/AppLayout.vue`
- Test: `frontend/tests/e2e/process-app.spec.ts`

**Interfaces:**
- Consumes: process app list, copy, and deactivate endpoints.
- Produces: navigation to `/admin/process-apps/new` and `/:id/edit`.

- [ ] **Step 1: Add failing list assertions**

```ts
await page.goto('/admin/process-apps')
await expect(page.getByRole('heading', { name: '流程应用' })).toBeVisible()
await expect(page.getByText('请假申请')).toBeVisible()
await expect(page.getByText('报销申请')).toBeVisible()
await expect(page.getByText('采购申请')).toBeVisible()
```

- [ ] **Step 2: Run and verify page failure**

Run: `cd frontend; npm.cmd run test:e2e -- process-app.spec.ts`

Expected: FAIL because the page is absent.

- [ ] **Step 3: Implement the Ant list page**

Use an un-nested `a-card` containing filters and `a-table`. Columns are name/category, field count, approval node count, current version, status, and updated time. Actions use `a-dropdown` for preview, edit, copy, and deactivate. Use `a-empty` when no rows exist. Add `/admin/process-apps` only after the page exists, then remove the three legacy template menu entries while their files remain available until final cleanup.

- [ ] **Step 4: Run typecheck and list E2E**

Run: `cd frontend; npm.cmd run typecheck; npm.cmd run test:e2e -- process-app.spec.ts`

Expected: list scenario PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/approval/ProcessStatusTag.vue frontend/src/views/approval/AdminProcessApps.vue frontend/src/router/index.ts frontend/src/layouts/AppLayout.vue frontend/tests/e2e/process-app.spec.ts
git commit -m "feat: add process application administration page"
```

### Task 9: Low-Code Form Schema Designer

**Files:**
- Create: `frontend/src/components/approval/FormSchemaDesigner.vue`
- Create: `frontend/src/views/approval/AdminProcessEditor.vue`
- Modify: `frontend/src/router/index.ts`
- Test: `frontend/tests/e2e/process-app.spec.ts`

**Interfaces:**
- `FormSchemaDesigner` consumes `modelValue: FormSchema` and emits `update:modelValue`.
- The editor owns `draft: ProcessAppDraft` across all four steps.

- [ ] **Step 1: Add failing form-designer scenario**

```ts
await page.goto('/admin/process-apps/new')
await page.getByLabel('流程名称').fill('差旅申请')
await page.getByLabel('流程编号').fill('travel')
await page.getByRole('button', { name: '下一步' }).click()
await page.getByRole('button', { name: '金额' }).click()
await page.getByLabel('字段名称').fill('预计金额')
await expect(page.getByText('预计金额')).toBeVisible()
```

- [ ] **Step 2: Run and verify editor failure**

Run: `cd frontend; npm.cmd run test:e2e -- process-app.spec.ts`

Expected: FAIL because the editor and designer are absent.

- [ ] **Step 3: Implement the three-column designer**

Use Ant `a-steps` for the four editor stages, `a-card`/`a-list` for the component palette, `a-form` for properties, and icon buttons with tooltips for duplicate/delete/move. Generate stable IDs with `crypto.randomUUID()`. Always render a locked applicant information section. Support text, textarea, number, money, date, date range, radio, checkbox, select, user, department, attachment, section, and detail table; detail columns are text, number, money, date, or select. Add the new/edit editor routes only after `AdminProcessEditor.vue` exists.

- [ ] **Step 4: Run typecheck and designer E2E**

Run: `cd frontend; npm.cmd run typecheck; npm.cmd run test:e2e -- process-app.spec.ts`

Expected: form-designer scenario PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/approval/FormSchemaDesigner.vue frontend/src/views/approval/AdminProcessEditor.vue frontend/src/router/index.ts frontend/tests/e2e/process-app.spec.ts
git commit -m "feat: add low-code approval form designer"
```

### Task 10: Flow Schema Designer and Publishing

**Files:**
- Create: `frontend/src/components/approval/FlowSchemaDesigner.vue`
- Modify: `frontend/src/views/approval/AdminProcessEditor.vue`
- Test: `frontend/tests/e2e/process-app.spec.ts`

**Interfaces:**
- `FlowSchemaDesigner` consumes `modelValue: FlowSchema`, `users: ApprovalUser[]`, and `fields: FormFieldDefinition[]`.
- Emits `update:modelValue` and `validationChange`.

- [ ] **Step 1: Add failing condition/countersign scenario**

```ts
await page.getByRole('button', { name: '流程设计' }).click()
await page.getByRole('button', { name: '单人审批' }).click()
await page.getByLabel('节点名称').fill('部门审批')
await page.getByRole('button', { name: '条件分支' }).click()
await page.getByLabel('条件字段').selectOption({ label: '预计金额' })
await page.getByLabel('比较方式').selectOption({ label: '大于' })
await page.getByLabel('比较值').fill('100000')
await page.getByRole('button', { name: '会签' }).click()
```

- [ ] **Step 2: Run and verify flow-designer failure**

Run: `cd frontend; npm.cmd run test:e2e -- process-app.spec.ts`

Expected: FAIL because condition nodes are unsupported.

- [ ] **Step 3: Implement the controlled DAG editor**

Render fixed start/end nodes, approval cards, condition branches, and arrow connectors. Use Ant buttons and drawers for configuration; do not expose JSON mode. Keep graph editing controlled: add node after a selected node, add true/default branches from a condition, reorder nodes within a branch, and delete only when remaining edges can reconnect safely. The publish page calls the backend validation endpoint and renders `a-alert` items that focus the target field/node.

- [ ] **Step 4: Run typecheck and publish E2E**

Run: `cd frontend; npm.cmd run typecheck; npm.cmd run test:e2e -- process-app.spec.ts`

Expected: flow editor and publish scenario PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/approval/FlowSchemaDesigner.vue frontend/src/views/approval/AdminProcessEditor.vue frontend/tests/e2e/process-app.spec.ts
git commit -m "feat: add conditional approval flow designer"
```

### Task 11: Employee Dynamic Form and Request Details

**Files:**
- Create: `frontend/src/components/approval/DynamicApprovalForm.vue`
- Modify: `frontend/src/views/approval/ApprovalNew.vue`
- Modify: `frontend/src/views/approval/ApprovalDetail.vue`
- Test: `frontend/tests/e2e/process-app.spec.ts`

**Interfaces:**
- `DynamicApprovalForm` consumes `schema`, `modelValue`, `applicant`, and `readonly`.
- Submission sends `process_app_id`, `title`, `form_data`, and a generated `idempotency_key`.

- [ ] **Step 1: Add failing employee scenario**

```ts
await page.goto('/modules/approval-center/new')
await page.getByText('采购申请', { exact: true }).click()
await expect(page.getByText('申请人信息')).toBeVisible()
await expect(page.getByText('平台管理员')).toBeVisible()
await page.getByLabel('采购金额').fill('120000')
await page.getByRole('button', { name: '提交申请' }).click()
await expect(page).toHaveURL(/approval-center\/requests/)
```

- [ ] **Step 2: Run and verify old type-contract failure**

Run: `cd frontend; npm.cmd run test:e2e -- process-app.spec.ts`

Expected: FAIL because `ApprovalNew` still consumes `/types` and `form_template`.

- [ ] **Step 3: Implement Ant dynamic rendering**

Map schema types to Ant inputs: `a-input`, `a-textarea`, `a-input-number`, `a-date-picker`, `a-range-picker`, `a-radio-group`, `a-checkbox-group`, `a-select`, `a-upload`, and editable `a-table`. Use `a-descriptions` for applicant snapshots and `a-timeline` plus `a-steps` for request details.

- [ ] **Step 4: Run typecheck and employee E2E**

Run: `cd frontend; npm.cmd run typecheck; npm.cmd run test:e2e -- process-app.spec.ts`

Expected: employee scenario PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/approval/DynamicApprovalForm.vue frontend/src/views/approval/ApprovalNew.vue frontend/src/views/approval/ApprovalDetail.vue frontend/tests/e2e/process-app.spec.ts
git commit -m "feat: submit requests from dynamic process forms"
```

### Task 12: Monitor UI, Legacy Cleanup, Migration, and Full Verification

**Files:**
- Create: `frontend/src/views/approval/AdminProcessMonitor.vue`
- Create: `backend/scripts/migrate_approval_v2.py`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/AppLayout.vue`
- Modify: `frontend/tests/e2e/process-app.spec.ts`
- Delete: five legacy admin views listed in Planned File Structure.

**Interfaces:**
- Consumes: monitor summary/list and existing request-detail endpoints.
- Produces: backup-first migration command and final user-visible module.

- [ ] **Step 1: Add failing monitor and legacy-removal assertions**

```ts
await page.goto('/admin/process-monitor')
await expect(page.getByRole('heading', { name: '流程监控' })).toBeVisible()
await expect(page.locator('.ant-statistic')).toHaveCount(6)
await expect(page.getByText('审批类型', { exact: true })).toHaveCount(0)
await expect(page.getByText('表单模板', { exact: true })).toHaveCount(0)
await expect(page.getByText('流程模板', { exact: true })).toHaveCount(0)
```

- [ ] **Step 2: Run and verify monitor failure**

Run: `cd frontend; npm.cmd run test:e2e -- process-app.spec.ts`

Expected: FAIL because monitor UI is missing.

- [ ] **Step 3: Implement monitor and migration script**

Use `a-row`/`a-col` with six `a-statistic` cards, an inline `a-form` filter bar, paginated `a-table`, and read-only `a-drawer` containing `a-descriptions` and `a-timeline`. Build the migration script with explicit paths:

```python
source = Path(__file__).resolve().parents[1] / "approval.db"
backup = source.with_name(f"approval.backup-{datetime.now():%Y%m%d-%H%M%S}.db")
shutil.copy2(source, backup)
```

The script must verify zero runtime requests before rebuilding, seed v2 data, assert three published apps, run SQLite `PRAGMA integrity_check`, and print the backup path. It must abort without changing the source database when any precondition fails.

- [ ] **Step 4: Run full verification**

Run:

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

Expected:

- Ruff: no errors.
- Pytest: all tests pass.
- Vue typecheck: no errors.
- Vite production build: exit 0.
- Playwright: all desktop/mobile and process-app scenarios pass.
- No horizontal overflow at 1440x900, 1024x768, and 390x844.

- [ ] **Step 5: Run production migration after verification**

Run:

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend
.\.venv\Scripts\python.exe .\scripts\migrate_approval_v2.py
```

Expected: output contains `integrity_check=ok`, `published_apps=3`, and an absolute backup path.

- [ ] **Step 6: Commit**

```powershell
git add backend/scripts/migrate_approval_v2.py frontend/src/views/approval/AdminProcessMonitor.vue frontend/src/router/index.ts frontend/src/layouts/AppLayout.vue frontend/tests/e2e/process-app.spec.ts
git add -u frontend/src/views/approval
git commit -m "feat: complete unified approval process application"
```

---

## Final Acceptance Checklist

- [ ] User creation requires a position and supports active/inactive status.
- [ ] The administrator sees only Users, Process Apps, and Process Monitor for approval administration.
- [ ] Leave, expense, and purchase appear as published `v1` process apps.
- [ ] Form fields can be added, configured, duplicated, deleted, and reordered without JSON editing.
- [ ] Process nodes support single approver, countersign, and amount-based conditional branches.
- [ ] Any active employee can be selected as an approver.
- [ ] Submission snapshots applicant name, department, position, time, form schema, version, and selected path.
- [ ] Monitoring is read-only and supports the agreed filters and six metrics.
- [ ] Published versions are immutable and new edits create the next draft version.
- [ ] Every module uses the same Ant Design Vue theme and responsive layout rules.
- [ ] The production database is backed up before migration and passes integrity verification afterward.
