# Readable WYSIWYG Approval Process Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a low-cost, readable approval-process editor with automatic codes, grouped categories, true runtime-form preview, three understandable flow rules, and local-return workflow actions.

**Architecture:** Keep the existing FastAPI approval domain and Vue four-step editor. Add focused backend helpers for code generation and a separate return-context table so existing approval tables do not need destructive alteration. Extract shared runtime field and action components, then reuse them in design, preview, launch, and approval-detail views.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, Vue 3, TypeScript, Ant Design Vue, Vitest-free Playwright E2E, pytest.

## Global Constraints

- Only expose single-person approval, countersign, and condition branch as business node types.
- Process codes use `CATEGORY-YYYYMMDD-XXXX`, where `XXXX` is four uppercase letters or digits.
- Built-in categories are 人事、财务、采购、行政、通用; custom category strings remain supported.
- Design, preview, launch, and approval-detail views share the same runtime field renderer.
- A return is local rework and must resume at the node that issued the return.
- A rejection ends the current request and requires a new request to continue.
- Preserve existing process versions, snapshots, request history, and unrelated modules.
- Do not introduce BPMN, free-form edge drawing, loops, script conditions, or nested detail tables.
- Keep cards at 8px radius or less; use existing Ant Design Vue icons and controls.

---

## File Structure

**Backend**

- `backend/app/approval/codegen.py`: category-prefix normalization and unique process-code generation.
- `backend/app/approval/models.py`: add `ApprovalReturnContext` as a new table; avoid altering existing request rows.
- `backend/app/approval/schemas.py`: make create code server-owned; add return/resubmit request bodies.
- `backend/app/approval/admin_router.py`: generate codes during process creation and keep update codes immutable.
- `backend/app/approval/router.py`: return and resubmit transaction rules.
- `backend/app/approval/serializers.py`: expose active return context and action labels.
- `backend/tests/test_process_admin.py`: automatic-code and category coverage.
- `backend/tests/test_approval.py`: return/resubmit/reject/transfer state-machine coverage.

**Frontend**

- `frontend/src/components/approval/ApprovalFieldControl.vue`: render one real field control, including attachment and detail-table behavior.
- `frontend/src/components/approval/DynamicApprovalForm.vue`: validation and whole-form composition using `ApprovalFieldControl`.
- `frontend/src/components/approval/FormSchemaDesigner.vue`: three-column WYSIWYG design chrome around shared field controls.
- `frontend/src/components/approval/FlowSchemaDesigner.vue`: top-to-bottom inline-add flow and readable branch lanes.
- `frontend/src/components/approval/ApprovalActionBar.vue`: shared preview/runtime approval actions.
- `frontend/src/views/approval/AdminProcessEditor.vue`: automatic code display, custom categories, dual-role preview, targeted validation summary.
- `frontend/src/views/approval/ApprovalNew.vue`: category-grouped process selection.
- `frontend/src/views/approval/ApprovalDetail.vue`: editable rework state and four approval actions.
- `frontend/src/types/approval.ts`: process code optionality and return-context types.
- `frontend/tests/e2e/process-app.spec.ts`: editor, code, category, field, flow, and preview coverage.
- `frontend/tests/e2e/approval-workflow.spec.ts`: local-return and action visibility coverage.

---

### Task 1: Server-Owned Process Codes and Grouped Categories

**Files:**

- Create: `backend/app/approval/codegen.py`
- Modify: `backend/app/approval/schemas.py`
- Modify: `backend/app/approval/admin_router.py`
- Modify: `frontend/src/types/approval.ts`
- Modify: `frontend/src/views/approval/AdminProcessEditor.vue`
- Modify: `frontend/src/views/approval/ApprovalNew.vue`
- Test: `backend/tests/test_process_admin.py`
- Test: `frontend/tests/e2e/process-app.spec.ts`

**Interfaces:**

- Produces: `generate_process_code(db: Session, category: str, now: datetime | None = None) -> str`.
- Produces: `ProcessAppCreate.code: None`; create responses still return `ProcessApp.code: str`.
- Produces: `groupedApps: Array<{ category: string; apps: ProcessApp[] }>` in `ApprovalNew.vue`.

- [ ] **Step 1: Add failing backend tests for generated code**

```python
def test_process_app_create_generates_category_code(client, admin_headers):
    response = client.post(
        "/api/v1/admin/process-apps",
        headers=admin_headers,
        json={"name": "入职申请", "category": "人事", "description": "", "form_schema": {"fields": []}, "flow_schema": {"nodes": [], "edges": []}},
    )
    assert response.status_code == 201
    assert re.fullmatch(r"HR-\d{8}-[A-Z0-9]{4}", response.json()["data"]["code"])


def test_custom_category_uses_custom_prefix_and_unique_codes(client, admin_headers):
    payload = {"name": "项目申请", "category": "项目管理", "form_schema": {"fields": []}, "flow_schema": {"nodes": [], "edges": []}}
    first = client.post("/api/v1/admin/process-apps", headers=admin_headers, json=payload).json()["data"]
    second = client.post("/api/v1/admin/process-apps", headers=admin_headers, json={**payload, "name": "项目申请二"}).json()["data"]
    assert first["code"].startswith("CUS-")
    assert first["code"] != second["code"]
```

- [ ] **Step 2: Run the tests and verify schema rejection fails first**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_admin.py -k "generates_category_code or custom_category" -q`

Expected: FAIL because `ProcessAppCreate.code` is required.

- [ ] **Step 3: Implement deterministic category prefixes and random suffix generation**

```python
BUILTIN_PREFIXES = {"人事": "HR", "财务": "FIN", "采购": "PUR", "行政": "ADM", "通用": "GEN", "通用审批": "GEN"}
ALPHABET = string.ascii_uppercase + string.digits


def generate_process_code(db: Session, category: str, now: datetime | None = None) -> str:
    prefix = BUILTIN_PREFIXES.get(category.strip(), "CUS")
    date_part = (now or datetime.now(UTC)).strftime("%Y%m%d")
    for _ in range(64):
        suffix = "".join(secrets.choice(ALPHABET) for _ in range(4))
        code = f"{prefix}-{date_part}-{suffix}"
        if db.scalar(select(ProcessApp.id).where(ProcessApp.code == code)) is None:
            return code
    raise HTTPException(status_code=503, detail="流程编号生成失败，请重试")
```

Change `ProcessAppCreate` so `code` is not accepted. In `create_process_app`, call `generate_process_code(db, body.category)`. Keep `ProcessAppUpdate.code` only for backward-compatible payload parsing but reject any changed value with `400 已生成的流程编号不可修改`.

- [ ] **Step 4: Run backend tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_admin.py -q`

Expected: PASS.

- [ ] **Step 5: Add failing E2E assertions for read-only code and category groups**

```ts
await page.goto('/admin/process-apps/new')
await expect(page.getByLabel('流程编号')).toBeDisabled()
await page.getByLabel('流程分类').fill('项目管理')
await page.getByRole('button', { name: '保存草稿' }).click()
expect(createPayload).not.toHaveProperty('code')
await expect(page.getByLabel('流程编号')).toHaveValue(/^CUS-\d{8}-[A-Z0-9]{4}$/)

await page.goto('/modules/approval-center/new')
await expect(page.getByRole('heading', { name: '人事' })).toBeVisible()
await expect(page.getByRole('heading', { name: '财务' })).toBeVisible()
```

- [ ] **Step 6: Implement frontend code display, custom category input, and grouped launch page**

Use an `a-auto-complete` for category with built-in options and free text. For new drafts, show `保存后自动生成`; after create, display the returned code in a disabled input. Remove `code` from POST payloads and keep it in PUT payloads only as unchanged display data if the API type requires it.

```ts
const groupedApps = computed(() => Object.entries(
  activeApps.value.reduce<Record<string, ProcessApp[]>>((groups, app) => {
    (groups[app.category] ||= []).push(app)
    return groups
  }, {}),
).map(([category, apps]) => ({ category, apps: apps.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN')) })))
```

- [ ] **Step 7: Run frontend checks and commit**

Run: `npm.cmd run typecheck`

Run: `npm.cmd run test:e2e -- tests/e2e/process-app.spec.ts`

Expected: PASS.

```bash
git add backend/app/approval/codegen.py backend/app/approval/schemas.py backend/app/approval/admin_router.py backend/tests/test_process_admin.py frontend/src/types/approval.ts frontend/src/views/approval/AdminProcessEditor.vue frontend/src/views/approval/ApprovalNew.vue frontend/tests/e2e/process-app.spec.ts
git commit -m "feat: generate process codes and group categories"
```

### Task 2: Shared Runtime Field Controls

**Files:**

- Create: `frontend/src/components/approval/ApprovalFieldControl.vue`
- Modify: `frontend/src/components/approval/DynamicApprovalForm.vue`
- Test: `frontend/tests/e2e/process-app.spec.ts`

**Interfaces:**

- Produces props: `field: FormField`, `modelValue: Value`, `readonly?: boolean`, `preview?: boolean`.
- Produces events: `update:modelValue`, `validationChange` remains owned by `DynamicApprovalForm`.
- Consumes existing `FormField`, `DetailColumn`, and stable `id || key` values.

- [ ] **Step 1: Add a failing E2E field matrix**

Create one schema containing every supported field type. Assert real controls exist by accessible label and that detail rows, attachment names, date ranges, and readonly values render.

```ts
for (const label of ['单行文本', '多行文本', '数字', '金额', '日期', '日期范围', '单选', '多选', '下拉选择', '人员', '部门', '附件']) {
  await expect(page.getByLabel(label)).toBeVisible()
}
await page.getByRole('button', { name: '添加明细行' }).click()
await expect(page.getByLabel('费用明细 第1行 金额')).toBeVisible()
```

- [ ] **Step 2: Run the focused test and verify designer/runtime mismatch**

Run: `npm.cmd run test:e2e -- tests/e2e/process-app.spec.ts -g "field matrix"`

Expected: FAIL because the designer center does not render runtime controls.

- [ ] **Step 3: Extract one-field rendering**

Move field-specific templates and detail-table row operations from `DynamicApprovalForm.vue` into `ApprovalFieldControl.vue`. Do not move whole-form validation.

```vue
<ApprovalFieldControl
  v-if="field.type !== 'section'"
  :field="field"
  :model-value="modelValue[keyOf(field)]"
  :readonly="readonly"
  :preview="preview"
  @update:model-value="setValue(keyOf(field), $event)"
/>
```

Preview attachments must remain local and never upload. Readonly detail tables render columns and rows instead of JSON text.

- [ ] **Step 4: Run typecheck and field test**

Run: `npm.cmd run typecheck`

Run: `npm.cmd run test:e2e -- tests/e2e/process-app.spec.ts -g "field matrix"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/approval/ApprovalFieldControl.vue frontend/src/components/approval/DynamicApprovalForm.vue frontend/tests/e2e/process-app.spec.ts
git commit -m "refactor: share approval field rendering"
```

### Task 3: WYSIWYG Form Designer

**Files:**

- Modify: `frontend/src/components/approval/FormSchemaDesigner.vue`
- Modify: `frontend/src/styles.css`
- Test: `frontend/tests/e2e/process-app.spec.ts`

**Interfaces:**

- Consumes: `ApprovalFieldControl` from Task 2.
- Keeps: `v-model` value type `FormSchema` and stable field IDs.
- Produces: design-only selected state without changing saved schema.

- [ ] **Step 1: Add failing tests for live properties and ordering**

```ts
await page.locator('[data-field-type="text"]').click()
await expect(page.getByLabel('单行文本')).toBeVisible()
await page.getByLabel('字段名称').fill('出差地点')
await expect(page.getByLabel('出差地点')).toBeVisible()
await page.getByLabel('必填').check()
await expect(page.getByLabel('出差地点')).toHaveAttribute('aria-required', 'true')
```

Add assertions for duplicate, delete, up/down, drag reorder, option editing, attachment, and detail-table column editing.

- [ ] **Step 2: Run focused tests and verify the old field-card canvas fails**

Run: `npm.cmd run test:e2e -- tests/e2e/process-app.spec.ts -g "WYSIWYG form designer"`

Expected: FAIL because the center only shows field metadata.

- [ ] **Step 3: Replace center field rows with runtime controls**

Wrap each `ApprovalFieldControl` with design chrome containing selection, duplicate, delete, up/down, and a drag handle. Use a local `previewValues` record so controls can be exercised without polluting `form_schema`.

```vue
<article :data-field-id="field.id" :class="['design-field', { selected: selectedId === field.id }]" @click="selectedId = field.id">
  <ApprovalFieldControl :field="field" v-model="previewValues[field.id]" preview />
  <div class="design-field-actions">...</div>
</article>
```

Use native pointer/drag events only for reordering. Maintain button alternatives for keyboard and low-cost operation.

- [ ] **Step 4: Verify narrow-screen layout**

At widths below `900px`, stack component library, live form, and property panel. Do not hide controls or let field labels overlap actions.

Run: `npm.cmd run test:e2e -- tests/e2e/process-app.spec.ts -g "WYSIWYG form designer"`

Run: `npm.cmd run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/approval/FormSchemaDesigner.vue frontend/src/styles.css frontend/tests/e2e/process-app.spec.ts
git commit -m "feat: add wysiwyg approval form designer"
```

### Task 4: Readable Three-Rule Flow Designer

**Files:**

- Modify: `frontend/src/components/approval/FlowSchemaDesigner.vue`
- Test: `frontend/tests/e2e/process-app.spec.ts`

**Interfaces:**

- Keeps persisted `FlowSchema { nodes, edges }` unchanged.
- Produces inline insertion: `insertAfter(anchorId: string, type: 'approval' | 'countersign' | 'condition')`.
- Keeps `validationChange` and `focusTarget(id)` APIs used by `AdminProcessEditor`.

- [ ] **Step 1: Add failing tests for inline add and readable conditions**

```ts
await page.getByLabel('在 开始 后添加节点').click()
await page.getByRole('menuitem', { name: '单人审批' }).click()
await expect(page.getByText('全部同意后继续')).toHaveCount(0)

await page.getByLabel('在 部门审批 后添加节点').click()
await page.getByRole('menuitem', { name: '条件分支' }).click()
await expect(page.getByText('其他情况')).toBeVisible()
await expect(page.getByText(/金额.*大于等于.*5,000/)).toBeVisible()
```

- [ ] **Step 2: Run focused flow tests**

Run: `npm.cmd run test:e2e -- tests/e2e/process-app.spec.ts -g "readable flow designer"`

Expected: FAIL because additions currently live in the top toolbar and branches expose generic labels.

- [ ] **Step 3: Implement top-to-bottom business flow presentation**

Render start, business nodes, inline add controls, branch lanes, automatic merge, and end. Keep graph normalization functions internal. Remove visible “受控流程图”, edge terminology, and global node-add buttons.

```text
开始
  + 添加下一步
部门审批 · 王五
  + 添加下一步
采购金额判断
  金额大于等于 5,000 元 | 其他情况
  财务会签                | 部门经理审批
  自动汇合
结束
```

The node drawer only shows name, approver(s), allow transfer, timeout, and condition expression when applicable.

- [ ] **Step 4: Keep saved graph compatibility and validation**

Run existing graph payload assertions and add one legacy-flow fixture. Assert opening and saving the legacy definition preserves stable node and edge IDs.

Run: `npm.cmd run test:e2e -- tests/e2e/process-app.spec.ts -g "flow|branch|legacy"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/approval/FlowSchemaDesigner.vue frontend/tests/e2e/process-app.spec.ts
git commit -m "feat: simplify approval flow design"
```

### Task 5: Dual-Role Preview and Shared Action Bar

**Files:**

- Create: `frontend/src/components/approval/ApprovalActionBar.vue`
- Modify: `frontend/src/views/approval/AdminProcessEditor.vue`
- Modify: `frontend/src/views/approval/ApprovalDetail.vue`
- Test: `frontend/tests/e2e/process-app.spec.ts`

**Interfaces:**

- `ApprovalActionBar` props: `preview?: boolean`, `canTransfer: boolean`, `loading?: boolean`, `users: ApprovalUser[]`.
- Events: `return`, `reject`, `transfer(targetUserId)`, `approve`.
- Preview mode emits nothing and marks controls as disabled/demo controls.

- [ ] **Step 1: Add failing dual-role preview tests**

```ts
await page.getByRole('tab', { name: '发起人视角' }).click()
await expect(page.getByRole('button', { name: '提交申请' })).toBeVisible()
await page.getByRole('tab', { name: '审批人视角' }).click()
for (const action of ['退回上一步', '驳回发起人', '转审', '同意并提交']) {
  await expect(page.getByRole('button', { name: action })).toBeVisible()
}
```

- [ ] **Step 2: Run focused preview test**

Run: `npm.cmd run test:e2e -- tests/e2e/process-app.spec.ts -g "dual-role preview"`

Expected: FAIL because preview currently shows metadata only.

- [ ] **Step 3: Build shared action bar and real previews**

Render `DynamicApprovalForm` in both tabs. The initiator tab uses editable preview values and non-submitting Save/Submit buttons. The approver tab uses readonly values plus `ApprovalActionBar preview`.

Replace the hand-written action controls in `ApprovalDetail.vue` with the same action bar. Keep destructive action colors restrained: reject is danger; return is neutral; submit is primary.

- [ ] **Step 4: Add clickable validation summary**

Display one top summary with error count. Each item calls existing `focusIssue(issue)` and puts an inline error beside the target field or node.

Run: `npm.cmd run typecheck`

Run: `npm.cmd run test:e2e -- tests/e2e/process-app.spec.ts -g "preview|validation"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/approval/ApprovalActionBar.vue frontend/src/views/approval/AdminProcessEditor.vue frontend/src/views/approval/ApprovalDetail.vue frontend/tests/e2e/process-app.spec.ts
git commit -m "feat: add dual-role approval preview"
```

### Task 6: Local Return and Resubmit State Machine

**Files:**

- Modify: `backend/app/approval/models.py`
- Modify: `backend/app/approval/schemas.py`
- Modify: `backend/app/approval/router.py`
- Modify: `backend/app/approval/serializers.py`
- Modify: `frontend/src/types/approval.ts`
- Modify: `frontend/src/views/approval/ApprovalDetail.vue`
- Test: `backend/tests/test_approval.py`
- Test: `frontend/tests/e2e/approval-workflow.spec.ts`

**Interfaces:**

- Produces table `approval_return_contexts` with `request_id`, `source_node_index`, `target_node_index`, `target_user_id`, `reason`, `status`, timestamps.
- Produces `POST /api/v1/approvals/nodes/{node_id}/return` body `{ comment: string }`.
- Produces `POST /api/v1/approvals/requests/{request_id}/resubmit` body `{ form_data: Record<string, unknown>; comment?: string }`.
- Request detail adds `return_context: ApprovalReturnContextOut | null`.

- [ ] **Step 1: Add failing backend tests for first-node return**

```python
returned = client.post(
    f"/api/v1/approvals/nodes/{node_id}/return",
    headers=approver_headers,
    json={"comment": "补充证明"},
)
assert returned.status_code == 200
assert returned.json()["data"]["status"] == "revision"
assert returned.json()["data"]["return_context"]["target_user_id"] == applicant_id
```

Then resubmit as applicant and assert request status returns to `pending`, the original source node is pending again, and actions are `return` then `resubmit`.

- [ ] **Step 2: Add failing backend tests for middle-node return**

Approve the first node, return from the second, and assert the return target is the most recent actual actor from the previous business node. Resubmit as that actor and assert execution resumes at the second node, not the first or third.

Also test: missing return reason, unauthorized resubmit, duplicate resubmit, countersign siblings, reject still ends, and transfer still works after a completed revision.

- [ ] **Step 3: Run tests and verify endpoints are missing**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_approval.py -k "return or resubmit" -q`

Expected: FAIL with `404` for new endpoints.

- [ ] **Step 4: Add return context model and schemas**

```python
class ApprovalReturnContext(ApprovalBase):
    __tablename__ = "approval_return_contexts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(Integer, index=True)
    source_node_index: Mapped[int] = mapped_column(Integer)
    target_node_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_user_id: Mapped[str] = mapped_column(String(36), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

New-table creation is handled by existing `ApprovalBase.metadata.create_all`; do not alter or drop existing tables.

- [ ] **Step 5: Implement transactional return**

Rules:

1. Require current pending approver and non-empty comment.
2. Resolve previous business-node actor from the latest `ApprovalAction(action='approve')`; if none, target the applicant.
3. Mark every pending sibling at the source index `returned` so countersign cannot continue in parallel.
4. Set request status `revision`, keep `current_node_index` at the source index, create one active return context, and append action `return`.
5. Reject a second return while an active context exists.

- [ ] **Step 6: Implement transactional resubmit**

Validate the submitted `form_data` against `form_schema_snapshot`. Require the active context target user. Mark context completed, reset all source-index nodes to `pending` with cleared comment/actor timestamps, set request status `pending`, preserve source index, update form data, and append action `resubmit`.

- [ ] **Step 7: Run backend tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_approval.py -q`

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests -q`

Expected: PASS.

- [ ] **Step 8: Add failing frontend workflow tests**

Mock a request with `status: 'revision'` and active return context. Assert only the target user sees an editable form and `修改后重新提交`. Mock a pending approver and assert all four actions show, while `转审` hides when `allow_transfer` is false.

- [ ] **Step 9: Implement returned-request UI**

Use `DynamicApprovalForm` with a cloned form-data record for the return target. Submit to `/requests/{id}/resubmit`. Use `ApprovalActionBar` for pending approvers and rename action copy exactly:

- `退回上一步`
- `驳回发起人`
- `转审`
- `同意并提交`

Map timeline actions to Chinese labels instead of exposing raw backend action names.

- [ ] **Step 10: Run frontend checks and commit**

Run: `npm.cmd run typecheck`

Run: `npm.cmd run test:e2e -- tests/e2e/approval-workflow.spec.ts`

Expected: PASS.

```bash
git add backend/app/approval/models.py backend/app/approval/schemas.py backend/app/approval/router.py backend/app/approval/serializers.py backend/tests/test_approval.py frontend/src/types/approval.ts frontend/src/views/approval/ApprovalDetail.vue frontend/tests/e2e/approval-workflow.spec.ts
git commit -m "feat: support local approval rework"
```

### Task 7: Integrated Verification and Visual Acceptance

**Files:**

- Modify as failures require: files already listed in Tasks 1-6 only.
- Test: `backend/tests/`
- Test: `frontend/tests/e2e/process-app.spec.ts`
- Test: `frontend/tests/e2e/approval-workflow.spec.ts`

**Interfaces:**

- Consumes all prior tasks.
- Produces a running local application on ports `5173` and `8000`.

- [ ] **Step 1: Run backend lint and full tests**

Run: `backend/.venv/Scripts/python.exe -m ruff check backend/app/approval backend/tests/test_approval.py backend/tests/test_process_admin.py`

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests -q`

Expected: all checks pass.

- [ ] **Step 2: Run frontend static checks and focused E2E**

Run: `npm.cmd run typecheck`

Run: `npm.cmd run build`

Run: `npm.cmd run test:e2e -- tests/e2e/process-app.spec.ts tests/e2e/approval-workflow.spec.ts`

Expected: all checks pass.

- [ ] **Step 3: Restart real services and probe health**

Run from project root: `powershell -ExecutionPolicy Bypass -File scripts/restart.ps1`

Verify: `http://127.0.0.1:8000/api/v1/health` returns `data.status = healthy`.

Verify: `http://127.0.0.1:5173/admin/process-apps` returns HTTP 200.

- [ ] **Step 4: Perform Playwright visual checks**

Capture desktop `1440x900`, tablet `1024x768`, and mobile `390x844` screenshots for:

- grouped launch page
- WYSIWYG form design
- readable condition branch
- initiator preview
- approver preview
- returned-request editing

Check text fit, no overlap, stable controls, visible selected state, branch readability, and horizontal table scrolling.

- [ ] **Step 5: Run exact acceptance scenario**

Create an HR flow, verify server-generated code, add text/attachment/detail table, configure amount condition, publish, submit, return, edit, resubmit, approve, transfer, and countersign. Confirm history and old process instances remain readable.

- [ ] **Step 6: Commit final fixes only if verification changed code**

```bash
git add backend/app/approval frontend/src/components/approval frontend/src/views/approval frontend/src/types/approval.ts backend/tests/test_approval.py backend/tests/test_process_admin.py frontend/tests/e2e/process-app.spec.ts frontend/tests/e2e/approval-workflow.spec.ts
git commit -m "fix: complete approval editor acceptance"
```

Do not commit generated screenshots, runtime databases, logs, uploads, or unrelated dirty-worktree files.
