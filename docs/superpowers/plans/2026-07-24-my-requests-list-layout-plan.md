# “我的申请”列表布局修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复“我的申请”列表项被 Ant Design 按钮固定高度压扁的问题，让标题、时间和状态形成稳定、可点击、可键盘操作的卡片布局。

**Architecture:** 保留页面的数据请求、筛选、状态映射和路由逻辑，只把承担卡片角色的 `a-button` 换成原生语义化按钮，并在页面局部样式中完整定义卡片几何与交互状态。使用独立 Playwright 用例以模拟申请数据并验证两行布局、状态位置和键盘导航。

**Tech Stack:** Vue 3、TypeScript、Ant Design Vue 4、Playwright

## Global Constraints

- 不修改审批接口、数据结构或状态含义。
- 不重构其他审批列表页面。
- 不改变筛选器、返回按钮或“发起申请”按钮。
- 不引入新的 UI 依赖或全局视觉主题。
- 左侧标题在上、创建时间在下，右侧状态标签垂直居中。
- 整张卡片支持鼠标点击、键盘聚焦以及 Enter/Space 激活。

---

### Task 1: 修复申请卡片布局并增加回归测试

**Files:**
- Create: `frontend/tests/e2e/my-requests-layout.spec.ts`
- Modify: `frontend/src/views/approval/ApprovalMyRequests.vue:55-60`

**Interfaces:**
- Consumes: `GET /api/v1/approvals/requests` 返回 `{ data: ApprovalRequestDetail[] }`；详情路由格式为 `/modules/approval-center/:id`。
- Produces: `.request-card` 原生按钮卡片，内部保留 `.request-info > strong + small` 和 `.ant-tag` DOM 约定，供布局测试与页面样式使用。

- [ ] **Step 1: 写入失败的布局回归测试**

创建 `frontend/tests/e2e/my-requests-layout.spec.ts`：

```ts
import { expect, test } from '@playwright/test'

async function loginAsAdmin(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: /平台管理员/ }).click()
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

test('my requests card keeps title and time on separate rows', async ({ page }) => {
  await page.route('**/api/v1/approvals/requests', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      data: [{ id: 77, title: '业务验收测试流程 - 2026/7/24', status: 'pending', created_at: '2026-07-24T06:09:00' }],
    }),
  }))

  await loginAsAdmin(page)
  await page.goto('/modules/approval-center/requests')

  const card = page.getByRole('button', { name: /业务验收测试流程/ })
  const title = card.locator('.request-info strong')
  const date = card.locator('.request-info small')
  const tag = card.locator('.ant-tag')
  await expect(card).toBeVisible()

  const [cardBox, titleBox, dateBox, tagBox] = await Promise.all([
    card.boundingBox(), title.boundingBox(), date.boundingBox(), tag.boundingBox(),
  ])
  expect(cardBox).not.toBeNull()
  expect(titleBox).not.toBeNull()
  expect(dateBox).not.toBeNull()
  expect(tagBox).not.toBeNull()
  expect(cardBox!.height).toBeGreaterThan(52)
  expect(dateBox!.y).toBeGreaterThanOrEqual(titleBox!.y + titleBox!.height)
  expect(tagBox!.x).toBeGreaterThan(titleBox!.x)
  expect(Math.abs((tagBox!.y + tagBox!.height / 2) - (cardBox!.y + cardBox!.height / 2))).toBeLessThan(4)

  await card.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/approval-center\/77/)
})
```

- [ ] **Step 2: 运行测试并确认因旧按钮高度而失败**

Run:

```powershell
npm.cmd run test:e2e -- tests/e2e/my-requests-layout.spec.ts
```

Expected: FAIL，`cardBox.height` 不大于 `52`，证明旧 `a-button` 固定高度复现了截图中的压缩问题。

- [ ] **Step 3: 用原生按钮实现最小修复**

把 `ApprovalMyRequests.vue` 的列表模板替换为：

```vue
<a-list v-else class="record-list" :data-source="requests">
  <template #renderItem="{ item }">
    <a-list-item>
      <button type="button" class="request-card" @click="router.push(`/modules/approval-center/${item.id}`)">
        <span class="request-info">
          <strong>{{ item.title }}</strong>
          <small>{{ item.created_at.slice(0, 16).replace('T', ' ') }}</small>
        </span>
        <a-tag :color="statusTagMap[item.status]">{{ statusTextMap[item.status] }}</a-tag>
      </button>
    </a-list-item>
  </template>
</a-list>
```

把页面局部样式替换为：

```css
.request-card {
  width: 100%;
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fff;
  color: inherit;
  font: inherit;
  text-align: left;
  white-space: normal;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s, box-shadow 0.2s;
}

.request-card:hover {
  border-color: #91caff;
  background: #f5faff;
}

.request-card:focus-visible {
  border-color: #1677ff;
  outline: 2px solid rgba(22, 119, 255, 0.2);
  outline-offset: 2px;
}

.request-info {
  min-width: 0;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 4px;
}

.request-info strong {
  color: #1677ff;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.request-info small {
  color: #8c8c8c;
  font-size: 12px;
  line-height: 1.5;
}

.request-card .ant-tag {
  flex: 0 0 auto;
  margin-inline-end: 0;
}
```

- [ ] **Step 4: 运行布局测试并确认通过**

Run:

```powershell
npm.cmd run test:e2e -- tests/e2e/my-requests-layout.spec.ts
```

Expected: `1 passed`，卡片高度、两行信息、状态居中和 Enter 导航全部满足断言。

- [ ] **Step 5: 运行相关回归、类型检查与生产构建**

Run:

```powershell
npm.cmd run test:e2e -- tests/e2e/foundation.spec.ts tests/e2e/my-requests-layout.spec.ts
npm.cmd run typecheck
npm.cmd run build
```

Expected: Playwright 用例全部通过；`vue-tsc --noEmit` 退出码为 `0`；`vite build` 完成且退出码为 `0`。

- [ ] **Step 6: 在本地运行页面做视觉检查**

打开 `http://127.0.0.1:5173/modules/approval-center/requests`，使用桌面视口和至少一条模拟申请数据确认：标题和时间没有重叠、标签在右侧居中、悬停和键盘焦点清晰，浏览器控制台没有新增错误。

- [ ] **Step 7: 提交实现**

```powershell
git add -- frontend/tests/e2e/my-requests-layout.spec.ts frontend/src/views/approval/ApprovalMyRequests.vue
git commit -m "fix: repair my requests card layout"
```
