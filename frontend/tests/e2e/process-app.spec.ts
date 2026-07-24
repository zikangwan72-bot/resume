import { expect, test, type Page, type Route } from '@playwright/test'

type MockUser = {
  id: string
  email: string
  display_name: string
  department: string
  position: string
  role: string
  is_active: boolean
  created_at: string
}

const seededUsers: MockUser[] = [
  { id: 'u-1', email: 'zhangsan@example.com', display_name: '张三', department: '产品研发部', position: '产品经理', role: 'department_manager', is_active: true, created_at: '2026-07-23T10:00:00Z' },
  { id: 'u-2', email: 'lisi@example.com', display_name: '李四', department: '财务管理部', position: '财务专员', role: 'finance', is_active: true, created_at: '2026-07-23T10:01:00Z' },
  { id: 'u-3', email: 'inactive@example.com', display_name: '停用员工', department: '人力资源部', position: 'HR专员', role: 'hr', is_active: false, created_at: '2026-07-23T10:02:00Z' },
]

type MockProcessApp = {
  id: number
  code: string
  name: string
  category: string
  description: string | null
  status: 'draft' | 'published' | 'inactive'
  version_id: number
  version_number: number
  version_status: 'draft' | 'published'
  current_version_id: number
  draft_version_number?: number | null
  has_draft?: boolean
  field_count: number
  approval_node_count: number
  form_schema: { fields: unknown[] }
  flow_schema: { nodes: unknown[]; edges: unknown[] }
  published_at: string | null
  created_at: string
  updated_at: string
}

const seededProcessApps: MockProcessApp[] = [
  { id: 1, code: 'leave', name: '请假申请', category: '人事', description: '员工请假流程', status: 'published', version_id: 11, version_number: 1, version_status: 'published', current_version_id: 11, field_count: 4, approval_node_count: 1, form_schema: { fields: [] }, flow_schema: { nodes: [], edges: [] }, published_at: '2026-07-20T08:00:00Z', created_at: '2026-07-20T08:00:00Z', updated_at: '2026-07-23T08:00:00Z' },
  { id: 2, code: 'expense', name: '报销申请', category: '财务', description: '费用报销流程', status: 'published', version_id: 10, version_number: 1, version_status: 'published', current_version_id: 10, draft_version_number: 2, has_draft: true, field_count: 6, approval_node_count: 2, form_schema: { fields: [] }, flow_schema: { nodes: [], edges: [] }, published_at: '2026-07-19T08:00:00Z', created_at: '2026-07-19T08:00:00Z', updated_at: '2026-07-22T08:00:00Z' },
  { id: 3, code: 'purchase', name: '采购申请', category: '采购', description: '采购审批流程', status: 'published', version_id: 13, version_number: 1, version_status: 'published', current_version_id: 13, field_count: 6, approval_node_count: 2, form_schema: { fields: [] }, flow_schema: { nodes: [], edges: [] }, published_at: '2026-07-18T08:00:00Z', created_at: '2026-07-18T08:00:00Z', updated_at: '2026-07-21T08:00:00Z' },
]

async function loginAsAdmin(page: Page) {
  await page.goto('/login')
  await page.evaluate(() => {
    localStorage.removeItem('enterprise_ai_token')
    localStorage.removeItem('enterprise_ai_user')
  })
  await page.reload()
  await page.getByRole('button', { name: /平台管理员/ }).click()
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

async function setupUserApi(page: Page, initialUsers = seededUsers) {
  const users = initialUsers.map((user) => ({ ...user }))
  let getAttempts = 0
  let getHandler: ((route: Route) => Promise<void>) | undefined

  await page.route('**/api/v1/admin/users**', async (route) => {
    if (getHandler && route.request().method() === 'GET') return getHandler(route)
    const request = route.request()
    const method = request.method()
    if (method === 'GET') {
      getAttempts += 1
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: users }) })
    }
    if (method === 'POST') {
      const body = request.postDataJSON() as MockUser
      if (users.some((user) => user.email === body.email)) {
        return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: '邮箱已存在' }) })
      }
      const created = { ...body, id: `u-${users.length + 1}`, created_at: '2026-07-23T11:00:00Z' }
      users.push(created)
      return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ data: created }) })
    }
    if (method === 'PUT') {
      const id = request.url().split('/').pop()
      const body = request.postDataJSON() as Partial<MockUser>
      const index = users.findIndex((user) => user.id === id)
      if (index < 0) return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: '用户不存在' }) })
      users[index] = { ...users[index], ...body }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: users[index] }) })
    }
    return route.continue()
  })

  return {
    users,
    attempts: () => getAttempts,
    setGetHandler: (handler: (route: Route) => Promise<void>) => { getHandler = handler },
  }
}

async function setupProcessAppApi(page: Page, initialApps = seededProcessApps, actionErrors: { copy?: boolean; deactivate?: boolean } = {}) {
  const apps = initialApps.map((app) => ({ ...app }))
  let getAttempts = 0
  await page.route('**/api/v1/admin/process-apps**', async (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      getAttempts += 1
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: apps }) })
    }
    const id = Number(route.request().url().match(/process-apps\/(\d+)/)?.[1])
    const app = apps.find((item) => item.id === id)
    if (!app) return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: '流程应用不存在' }) })
    if (method === 'POST' && route.request().url().endsWith('/copy')) {
      if (actionErrors.copy) return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: '复制失败' }) })
      const copy = { ...app, id: apps.length + 10, code: `${app.code}-copy`, name: `${app.name}（副本）`, status: 'draft' as const, version_id: apps.length + 20, current_version_id: apps.length + 20, version_status: 'draft' as const, updated_at: '2026-07-23T12:00:00Z' }
      apps.push(copy)
      return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ data: copy }) })
    }
    if (method === 'POST' && route.request().url().endsWith('/deactivate')) {
      if (actionErrors.deactivate) return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: '停用失败' }) })
      app.status = 'inactive'
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: app }) })
    }
    return route.continue()
  })
  return { apps, attempts: () => getAttempts }
}

async function openCreate(page: Page) {
  await page.getByRole('button', { name: '新增员工' }).click()
  await expect(page.getByRole('dialog', { name: '新增员工' })).toBeVisible()
}

async function fillUserForm(page: Page, values: { name?: string; email?: string; department?: string; position?: string } = {}) {
  await page.getByRole('textbox', { name: '* 姓名' }).fill(values.name || '王五')
  await page.getByRole('textbox', { name: '* 邮箱' }).fill(values.email || 'wangwu@example.com')
  await page.getByRole('textbox', { name: '* 部门' }).fill(values.department || '财务管理部')
  await page.getByRole('textbox', { name: '* 职位' }).fill(values.position || '财务专员')
}

test('shows seeded users, filters them, and replaces the legacy role route/menu', async ({ page }) => {
  await setupUserApi(page)
  await loginAsAdmin(page)
  await page.goto('/admin/users')
  await expect(page.getByRole('row', { name: /张三/ })).toBeVisible()
  await expect(page.getByText('角色管理', { exact: true })).toHaveCount(0)
  await expect(page.getByText('员工与角色', { exact: true })).toBeVisible()

  await page.getByRole('textbox', { name: '搜索员工' }).fill('张三')
  await expect(page.getByRole('row', { name: /张三/ })).toBeVisible()
  await expect(page.getByRole('row', { name: /李四/ })).toHaveCount(0)
  await page.getByText('已停用', { exact: true }).click()
  await expect(page.getByRole('row', { name: /暂无匹配员工/ })).toHaveCount(0)
  await expect(page.getByText('暂无匹配员工')).toBeVisible()
})

test('creates a user, validates position, and maps duplicate email to the email field', async ({ page }) => {
  await setupUserApi(page)
  await loginAsAdmin(page)
  await page.goto('/admin/users')
  await openCreate(page)
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText('请输入职位')).toBeVisible()

  await fillUserForm(page)
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText('员工已创建')).toBeVisible()
  await expect(page.getByRole('row', { name: /王五/ })).toBeVisible()

  await openCreate(page)
  await fillUserForm(page, { email: 'zhangsan@example.com' })
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText('邮箱已存在')).toHaveCount(2)
  await expect(page.getByRole('dialog').getByText('邮箱已存在').last()).toBeVisible()
})

test('edits a user and confirms deactivate then activate transitions', async ({ page }) => {
  await setupUserApi(page)
  await loginAsAdmin(page)
  await page.goto('/admin/users')
  const zhangRow = page.getByRole('row', { name: /张三/ })
  await zhangRow.getByRole('button', { name: '编辑' }).click()
  await page.getByRole('textbox', { name: '* 职位' }).fill('高级产品经理')
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText('员工信息已更新')).toBeVisible()
  await expect(page.getByRole('row', { name: /高级产品经理/ })).toBeVisible()

  await page.getByRole('switch', { name: '停用 张三' }).click()
  await expect(page.getByText('停用这名员工？')).toBeVisible()
  await page.getByRole('button', { name: /停\s*用/ }).click()
  await expect(page.getByRole('row', { name: /张三/ }).getByText('停用')).toBeVisible()

  await page.getByRole('switch', { name: '启用 停用员工' }).click()
  await expect(page.getByRole('row', { name: /停用员工/ }).getByText('启用')).toBeVisible()
})

test('renders loading, retries errors, and shows one empty state', async ({ page }) => {
  const api = await setupUserApi(page)
  let release: (() => void) | undefined
  api.setGetHandler(async (route) => {
    await new Promise<void>((resolve) => { release = resolve })
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: seededUsers }) })
  })
  await loginAsAdmin(page)
  const navigation = page.goto('/admin/users')
  await expect(page.locator('.ant-skeleton')).toBeVisible()
  release?.()
  await navigation
  await expect(page.getByRole('row', { name: /张三/ })).toBeVisible()

  await page.unroute('**/api/v1/admin/users**')
  let attempts = 0
  await page.route('**/api/v1/admin/users**', async (route) => {
    attempts += 1
    if (attempts === 1) return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: '服务异常' }) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [] }) })
  })
  await page.reload()
  await expect(page.getByText('员工列表加载失败')).toBeVisible()
  await page.getByRole('button', { name: /重\s*试/ }).click()
  await expect(page.getByText('暂无匹配员工')).toBeVisible()
  await expect(page.getByText('暂无数据')).toHaveCount(0)
})

test('keeps the users table and modal usable on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await setupUserApi(page)
  await loginAsAdmin(page)
  await page.goto('/admin/users')
  await expect(page.getByRole('table')).toBeVisible()
  await openCreate(page)
  await expect(page.getByRole('dialog', { name: '新增员工' })).toBeVisible()
  const layout = await page.evaluate(() => ({ viewport: window.innerWidth, scrollWidth: document.documentElement.scrollWidth }))
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.viewport)
})

test('lists seeded process apps with filters and lifecycle actions', async ({ page }) => {
  const api = await setupProcessAppApi(page)
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps')
  await expect(page.getByRole('heading', { name: '流程应用' })).toBeVisible()
  await expect(page.getByText('请假申请')).toBeVisible()
  await expect(page.getByText('报销申请')).toBeVisible()
  await expect(page.getByText('采购申请')).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '字段数' })).toBeVisible()
  await expect(page.getByRole('table').getByText('已发布', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('row', { name: /报销申请/ })).toContainText('v1')
  await expect(page.getByRole('row', { name: /报销申请/ })).toContainText('有草稿')

  await page.getByRole('textbox', { name: '搜索流程应用' }).fill('报销')
  await expect(page.getByRole('row', { name: /报销申请/ })).toBeVisible()
  await expect(page.getByRole('row', { name: /请假申请/ })).toHaveCount(0)
  await page.getByRole('textbox', { name: '搜索流程应用' }).fill('')
  await page.getByLabel('流程分类筛选').click()
  await page.getByText('财务', { exact: true }).last().click()
  await expect(page.getByRole('row', { name: /报销申请/ })).toBeVisible()
  await expect(page.getByRole('row', { name: /请假申请/ })).toHaveCount(0)

  await page.getByLabel('流程分类筛选').click()
  await page.getByText('全部分类', { exact: true }).last().click()
  await page.getByRole('textbox', { name: '搜索流程应用' }).fill('采购')
  await page.getByRole('row', { name: /采购申请/ }).getByRole('button', { name: '更多操作' }).click()
  await page.locator('.ant-dropdown:not(.ant-dropdown-hidden)').getByRole('menuitem', { name: '停用' }).last().click()
  await expect(page.getByText('停用流程应用？')).toBeVisible()
  await page.getByRole('button', { name: /停\s*用/ }).last().click()
  await expect(page.getByRole('row', { name: /采购申请/ }).getByText('已停用')).toBeVisible()

  await page.getByRole('textbox', { name: '搜索流程应用' }).fill('报销')
  await page.getByRole('row', { name: /报销申请/ }).getByRole('button', { name: '更多操作' }).click()
  await page.getByRole('menuitem', { name: '复制' }).click()
  await expect(page).toHaveURL(/\/admin\/process-apps\/\d+\/edit/)
  expect(api.apps.some((app) => app.name.includes('副本'))).toBeTruthy()
})

test('renders process app loading, retry, empty, and lifecycle API errors', async ({ page }) => {
  let attempts = 0
  let release: (() => void) | undefined
  await loginAsAdmin(page)
  await page.route('**/api/v1/admin/process-apps**', async (route) => {
    await new Promise<void>((resolve) => { release = resolve })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: seededProcessApps }) })
  })
  const navigation = page.goto('/admin/process-apps')
  await expect(page.locator('.ant-skeleton')).toBeVisible()
  release?.()
  await navigation
  await expect(page.getByText('请假申请')).toBeVisible()
  await page.unroute('**/api/v1/admin/process-apps**')
  await page.route('**/api/v1/admin/process-apps**', async (route) => {
    attempts += 1
    if (attempts === 1) return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: '服务异常' }) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [] }) })
  })
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps')
  await expect(page.getByText('流程应用列表加载失败')).toBeVisible()
  await page.getByRole('button', { name: /重\s*试/ }).click()
  await expect(page.getByText('暂无流程应用')).toBeVisible()
})

test('keeps the process-app table usable on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await setupProcessAppApi(page)
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps')
  await expect(page.getByRole('table')).toBeVisible()
})

test('supports preview and future new/edit routes and reports lifecycle errors', async ({ page }) => {
  await setupProcessAppApi(page, seededProcessApps, { copy: true, deactivate: true })
  await loginAsAdmin(page)
  await page.route('**/api/v1/admin/logs', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [] }) })
  })
  await expect(page.getByText('审批日志', { exact: true })).toBeVisible()
  await expect(page.getByText('审批类型', { exact: true })).toHaveCount(0)
  await page.goto('/admin/approval-logs')
  await expect(page.getByRole('heading', { name: '审批日志' })).toBeVisible()
  await page.goto('/admin/process-apps')
  await page.getByRole('row', { name: /请假申请/ }).getByRole('button', { name: '更多操作' }).click()
  await page.getByRole('menuitem', { name: '预览' }).click()
  await expect(page.getByRole('dialog', { name: /请假申请.*预览/ })).toBeVisible()
  await page.locator('.ant-modal-close').click()
  await page.getByRole('button', { name: /新建流程应用/ }).click()
  await expect(page).toHaveURL('/admin/process-apps/new')
  await page.goto('/admin/process-apps')
  await page.getByRole('row', { name: /请假申请/ }).getByRole('button', { name: '更多操作' }).click()
  await page.getByRole('menuitem', { name: '编辑' }).click()
  await expect(page).toHaveURL('/admin/process-apps/1/edit')
  await page.goto('/admin/process-apps')
  await page.getByRole('row', { name: /请假申请/ }).getByRole('button', { name: '更多操作' }).click()
  await page.getByRole('menuitem', { name: '复制' }).click()
  await expect(page.getByText('复制失败')).toBeVisible()
  await page.getByRole('row', { name: /采购申请/ }).getByRole('button', { name: '更多操作' }).click()
  await page.locator('.ant-dropdown:not(.ant-dropdown-hidden)').getByRole('menuitem', { name: '停用' }).last().click()
  await expect(page.getByText('停用流程应用？')).toBeVisible()
  await page.getByRole('button', { name: /停\s*用/ }).last().click()
  await expect(page.getByText('停用失败')).toBeVisible()
})

test('creates a draft, designs a form, and preserves stable field identifiers', async ({ page }) => {
  await setupProcessAppApi(page)
  let saved = false
  await page.route('**/api/v1/admin/process-apps', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    saved = true
    const body = route.request().postDataJSON()
    return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ data: { ...seededProcessApps[0], ...body, id: 99, version_id: 99, current_version_id: 99, form_schema: body.form_schema } }) })
  })
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps/new')

  await page.getByLabel('流程名称').fill('差旅申请')
  await page.getByLabel('流程编号').fill('travel')
  await page.getByRole('button', { name: '下一步' }).click()
  await page.locator('[data-field-type="money"]').click()
  await page.getByLabel('字段名称').fill('预计金额')
  await expect(page.getByText('预计金额', { exact: true })).toBeVisible()

  const field = page.locator('[data-field-id]').last()
  const firstId = await field.getAttribute('data-field-id')
  await field.getByRole('button', { name: '复制字段' }).click()
  const ids = await page.locator('[data-field-id]').evaluateAll((elements) => elements.map((element) => element.getAttribute('data-field-id')))
  expect(ids).toContain(firstId)
  expect(new Set(ids).size).toBe(ids.length)
  await page.locator('[data-field-id]').first().getByRole('button', { name: '下移字段' }).click()
  await page.locator('[data-field-id]').first().getByRole('button', { name: '删除字段' }).click()
  await expect(page.locator('[data-field-id]')).toHaveCount(1)
  await page.screenshot({ path: '../artifacts/task-9-editor-desktop.png', fullPage: true })

  await page.getByRole('button', { name: '上一环节' }).click()
  await expect(page.getByLabel('流程名称')).toHaveValue('差旅申请')
  await page.getByRole('button', { name: '下一步' }).click()
  await expect(page.getByText('预计金额', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保存草稿' }).click()
  await expect(page).toHaveURL('/admin/process-apps/99/edit')
  expect(saved).toBeTruthy()
})

test('edits an app, configures choices and detail columns, and surfaces save failures', async ({ page }) => {
  const app = {
    ...seededProcessApps[0],
    form_schema: { fields: [{ id: 'reason', key: 'reason', type: 'text', label: '请假事由', required: true }] },
  }
  let saveFailed = false
  let updatePayload: any
  await page.route('**/api/v1/admin/process-apps/**', async (route) => {
    const method = route.request().method()
    if (method === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: app }) })
    if (method === 'PUT') {
      saveFailed = true
      updatePayload = route.request().postDataJSON()
      return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: '流程编号已存在' }) })
    }
    return route.continue()
  })
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps/1/edit')
  await expect(page.getByLabel('流程名称')).toHaveValue('请假申请')
  await page.getByRole('button', { name: '下一步' }).click()
  await page.locator('[data-field-type="radio"]').click()
  await page.getByLabel('字段名称').fill('出行方式')
  await page.getByRole('textbox', { name: '选项' }).fill('飞机')
  await page.getByRole('button', { name: '添加选项' }).click()
  await page.getByRole('textbox', { name: '选项' }).last().fill('火车')
  await page.locator('[data-field-type="detail_table"]').click()
  await page.getByLabel('字段名称').fill('费用明细')
  await page.getByRole('button', { name: '新增明细列' }).click()
  await page.getByLabel('明细列名称').last().fill('金额')
  await page.getByRole('button', { name: '保存草稿' }).click()
  await expect(page.getByText('流程编号已存在')).toBeVisible()
  expect(saveFailed).toBeTruthy()
  expect(updatePayload.form_schema.fields.find((field: any) => field.id === 'reason')).toMatchObject({ key: 'reason', label: '请假事由' })
  expect(updatePayload.form_schema.fields.find((field: any) => field.type === 'detail_table').columns[0]).toMatchObject({ key: expect.any(String), label: '金额' })
})

test('keeps the process editor within the mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await setupProcessAppApi(page)
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps/new')
  await page.getByLabel('流程名称').fill('移动端流程')
  await page.getByLabel('流程编号').fill('mobile-flow')
  await page.getByRole('button', { name: '下一步' }).click()
  await expect(page.getByText('申请人信息')).toBeVisible()
  await page.screenshot({ path: '../artifacts/task-9-editor-mobile.png', fullPage: true })
  const layout = await page.evaluate(() => ({ viewport: window.innerWidth, scrollWidth: document.documentElement.scrollWidth }))
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.viewport)
})

test('normalizes form options and detail columns before posting every palette field', async ({ page }) => {
  let payload: any
  await page.route('**/api/v1/admin/process-apps', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    payload = route.request().postDataJSON()
    return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ data: { ...seededProcessApps[0], ...payload, id: 101, version_id: 101, current_version_id: 101 } }) })
  })
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps/new')
  await page.getByLabel('流程名称').fill('完整表单')
  await page.getByLabel('流程编号').fill('complete-form')
  await page.getByRole('button', { name: '下一步' }).click()
  for (const type of ['text', 'textarea', 'number', 'money', 'date', 'date_range', 'radio', 'checkbox', 'select', 'user', 'department', 'attachment', 'section', 'detail_table']) await page.locator(`[data-field-type="${type}"]`).click()
  await expect(page.locator('[data-field-id]')).toHaveCount(14)
  const detail = page.locator('[data-field-id]').last()
  await detail.getByRole('button', { name: '选择字段' }).click()
  await page.getByRole('button', { name: '新增明细列' }).click()
  await page.getByLabel('明细列编号').fill('cost_type')
  await page.getByLabel('明细列名称').fill('费用类型')
  await page.getByLabel('明细列类型').click()
  await page.getByText('下拉选择', { exact: true }).last().click()
  await page.getByRole('textbox', { name: '明细列选项' }).fill('  交通  ')
  await page.screenshot({ path: '../artifacts/task-9-review-desktop.png', fullPage: true })
  await page.getByRole('button', { name: '保存草稿' }).click()
  await expect(page).toHaveURL('/admin/process-apps/101/edit')
  expect(payload.form_schema.fields.every((field: any) => field.id && field.key === field.id)).toBeTruthy()
  const savedColumn = payload.form_schema.fields.find((field: any) => field.type === 'detail_table').columns[0]
  expect(savedColumn).toMatchObject({ id: 'cost_type', key: 'cost_type', label: '费用类型', type: 'select', options: ['交通'] })
})

test('blocks duplicate or blank choice options and keeps mobile properties reachable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps/new')
  await page.getByLabel('流程名称').fill('移动配置')
  await page.getByLabel('流程编号').fill('mobile-config')
  await page.getByRole('button', { name: '下一步' }).click()
  await page.locator('[data-field-type="select"]').click()
  await page.getByRole('textbox', { name: '选项' }).fill('   ')
  await expect(page.getByText('选项不能为空')).toBeVisible()
  await page.getByRole('textbox', { name: '选项' }).fill('项目')
  await page.getByRole('button', { name: '添加选项' }).click()
  await page.getByRole('textbox', { name: '选项' }).last().fill('项目')
  await expect(page.getByText('选项不能重复')).toBeVisible()
  await page.locator('[data-field-type="detail_table"]').click()
  await page.locator('[data-field-id]').last().getByRole('button', { name: '选择字段' }).click()
  await page.getByRole('button', { name: '新增明细列' }).click()
  await expect(page.getByLabel('明细列名称')).toBeVisible()
  await page.screenshot({ path: '../artifacts/task-9-review-mobile.png', fullPage: true })
  const layout = await page.evaluate(() => ({ viewport: window.innerWidth, scrollWidth: document.documentElement.scrollWidth }))
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.viewport)
})

test('normalizes legacy editor data and persists a successful PUT reload roundtrip', async ({ page }) => {
  const app: any = {
    ...seededProcessApps[0],
    name: '旧版流程', code: 'legacy-flow', category: '财务', description: '旧版说明',
    form_schema: {
      fields: [
        { id: 'legacy_text', key: 'legacy_text', type: 'text', label: null, placeholder: { legacy: true }, help: null, options: null, required: false },
        { id: 'legacy_items', key: 'legacy_items', type: 'detail_table', label: undefined, required: true, columns: [{ id: 'kind', key: 'kind', label: null, type: 'select', required: true, options: ['server'] }] },
      ],
    },
  }
  let putPayload: any
  await page.route('**/api/v1/admin/process-apps/1', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: app }) })
    if (route.request().method() === 'PUT') {
      putPayload = route.request().postDataJSON()
      Object.assign(app, putPayload)
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: app }) })
    }
    return route.continue()
  })
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps/1/edit')
  await expect(page.getByLabel('流程名称')).toHaveValue('旧版流程')
  await page.getByRole('button', { name: '下一步' }).click()
  await expect(page.getByText('legacy_text', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '选择字段 legacy_items' }).click()
  await expect(page.getByLabel('明细列名称')).toHaveValue('kind')
  await page.getByRole('button', { name: '保存草稿' }).click()
  await expect.poll(() => putPayload).toBeTruthy()
  expect(putPayload).toMatchObject({ name: '旧版流程', code: 'legacy-flow', category: '财务', description: '旧版说明' })
  expect(putPayload.form_schema.fields[0]).toMatchObject({ id: 'legacy_text', key: 'legacy_text', label: 'legacy_text', placeholder: { legacy: true }, help: null, options: null })
  expect(putPayload.form_schema.fields[1].columns[0]).toMatchObject({ id: 'kind', key: 'kind', label: 'kind', type: 'select', options: ['server'] })
  await page.reload()
  await expect(page.getByLabel('流程名称')).toHaveValue('旧版流程')
  await page.getByRole('button', { name: '下一步' }).click()
  await expect(page.getByText('legacy_text', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '选择字段 legacy_items' }).click()
  await expect(page.getByLabel('明细列名称')).toHaveValue('kind')
})

test('designs a serial, countersign, and conditional approval graph then saves its controlled payload', async ({ page }) => {
  let payload: any
  await setupUserApi(page)
  await page.route('**/api/v1/admin/process-apps', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    payload = route.request().postDataJSON()
    return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ data: { ...seededProcessApps[0], ...payload, id: 110, version_id: 110, current_version_id: 110 } }) })
  })
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps/new')
  await page.getByLabel('流程名称').fill('采购条件审批')
  await page.getByLabel('流程编号').fill('purchase-condition')
  await page.getByRole('button', { name: '下一步' }).click()
  await page.locator('[data-field-type="money"]').click()
  await page.getByLabel('字段名称').fill('预计金额')
  await page.getByRole('button', { name: '下一步' }).click()

  await page.getByRole('button', { name: '单人审批' }).click()
  await page.getByLabel('节点名称').fill('部门审批')
  await page.getByLabel('审批人').click()
  await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').getByText('张三 | 产品研发部 | 产品经理', { exact: true }).click()
  await page.getByRole('button', { name: '应用节点配置' }).click()
  await page.getByRole('button', { name: '条件分支' }).click()
  await page.getByLabel('条件字段').selectOption({ label: '预计金额' })
  await page.getByLabel('比较方式').selectOption('gt')
  await page.getByLabel('比较值').fill('100000')
  await page.getByRole('button', { name: '应用节点配置' }).click()
  await page.getByRole('button', { name: '会签' }).click()
  await page.getByLabel('节点名称').fill('财务会签')
  await page.getByLabel('审批人').click()
  await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').getByText('张三 | 产品研发部 | 产品经理', { exact: true }).click()
  await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').getByText('李四 | 财务管理部 | 财务专员', { exact: true }).click()
  await page.getByRole('button', { name: '应用节点配置' }).click()
  await expect(page.getByText('默认分支', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保存草稿' }).click()
  await expect(page).toHaveURL('/admin/process-apps/110/edit')
  expect(payload.flow_schema.nodes).toEqual(expect.arrayContaining([
    expect.objectContaining({ type: 'start' }),
    expect.objectContaining({ type: 'end' }),
    expect.objectContaining({ type: 'approval', approval_type: 'single', approver_id: 'u-1', allow_transfer: false }),
    expect.objectContaining({ type: 'countersign', approval_type: 'counter_sign', approver_ids: ['u-1', 'u-2'] }),
    expect.objectContaining({ type: 'condition' }),
  ]))
  expect(payload.flow_schema.edges).toEqual(expect.arrayContaining([
    expect.objectContaining({ default: true }),
    expect.objectContaining({ condition: { field_id: expect.any(String), operator: 'gt', value: 100000 } }),
  ]))
})

test('surfaces publish validation errors on their flow target and publishes a saved draft', async ({ page }) => {
  const app: any = {
    ...seededProcessApps[0], id: 120, version_id: 120, current_version_id: 120, status: 'draft', version_status: 'draft',
    form_schema: { fields: [{ id: 'amount', key: 'amount', type: 'money', label: '预计金额', required: true }] },
    flow_schema: {
      nodes: [
        { id: 'start', type: 'start', name: '开始' },
        { id: 'approval', type: 'approval', name: '部门审批', approval_type: 'single', approver_id: 'u-3', allow_transfer: false, timeout_hours: 0 },
        { id: 'end', type: 'end', name: '结束' },
      ], edges: [{ source: 'start', target: 'approval' }, { source: 'approval', target: 'end' }],
    },
  }
  let updates = 0
  let publishes = 0
  await setupUserApi(page)
  await page.route('**/api/v1/admin/process-apps/120', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: app }) })
    if (route.request().method() === 'PUT') { updates += 1; Object.assign(app, route.request().postDataJSON()); return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: app }) }) }
    return route.continue()
  })
  await page.route('**/api/v1/admin/process-apps/120/publish', async (route) => {
    publishes += 1
    if (publishes === 1) return route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'definition_invalid', errors: [{ code: 'inactive_approver', message: '审批人必须是启用员工', target_id: 'approval' }] } }) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: { ...app, status: 'published', version_number: 2, version_status: 'published' } }) })
  })
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps/120/edit')
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '发布流程' }).click()
  await expect(page.getByText('审批人必须是启用员工')).toBeVisible()
  await expect(page.getByRole('heading', { name: '流程设计' })).toBeVisible()
  await expect(page.locator('[data-flow-node-id="approval"]')).toBeFocused()
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '发布流程' }).click()
  await expect(page.getByText('流程已发布，当前版本 v2')).toBeVisible()
  expect(updates).toBeGreaterThan(0)
  expect(publishes).toBe(2)
})

test('shows local flow validation for a missing approver', async ({ page }) => {
  const app: any = {
    ...seededProcessApps[0], id: 130, version_id: 130, current_version_id: 130, status: 'draft', version_status: 'draft',
    form_schema: { fields: [{ id: 'amount', key: 'amount', type: 'money', label: '预计金额', required: true }] },
    flow_schema: { nodes: [{ id: 'start', type: 'start' }, { id: 'approval', type: 'approval', name: '待配置审批', approval_type: 'single', approver_id: '' }, { id: 'end', type: 'end' }], edges: [{ source: 'start', target: 'approval' }, { source: 'approval', target: 'end' }] },
  }
  await setupUserApi(page)
  await page.route('**/api/v1/admin/process-apps/130', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: app }) }))
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps/130/edit')
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await expect(page.getByText('审批人必须是启用员工')).toBeVisible()
  await page.getByText('审批人必须是启用员工').click()
  await expect(page.locator('[data-flow-node-id="approval"]')).toBeFocused()
})

test('reorders and deletes a serial approval node without breaking the saved graph', async ({ page }) => {
  const app: any = {
    ...seededProcessApps[0], id: 140, version_id: 140, current_version_id: 140, status: 'draft', version_status: 'draft',
    form_schema: { fields: [{ id: 'amount', key: 'amount', type: 'money', label: '预计金额', required: true }] },
    flow_schema: { nodes: [{ id: 'start', type: 'start' }, { id: 'first', type: 'approval', name: '第一审批', approval_type: 'single', approver_id: 'u-1' }, { id: 'second', type: 'approval', name: '第二审批', approval_type: 'single', approver_id: 'u-2' }, { id: 'end', type: 'end' }], edges: [{ source: 'start', target: 'first' }, { source: 'first', target: 'second' }, { source: 'second', target: 'end' }] },
  }
  let payload: any
  await setupUserApi(page)
  await page.route('**/api/v1/admin/process-apps/140', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: app }) })
    if (route.request().method() === 'PUT') { payload = route.request().postDataJSON(); Object.assign(app, payload); return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: app }) }) }
    return route.continue()
  })
  await loginAsAdmin(page)
  await page.goto('/admin/process-apps/140/edit')
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await page.locator('[data-flow-node-id="second"]').click()
  await page.getByLabel('上移节点').click()
  await page.getByLabel('删除节点').click()
  await page.getByRole('button', { name: '保存草稿' }).click()
  await expect.poll(() => payload).toBeTruthy()
  expect(payload.flow_schema.nodes.map((node: any) => node.id)).toEqual(expect.arrayContaining(['start', 'first', 'end']))
  expect(payload.flow_schema.nodes.map((node: any) => node.id)).not.toContain('second')
  expect(payload.flow_schema.edges).toEqual(expect.arrayContaining([{ source: 'start', target: 'first' }, { source: 'first', target: 'end' }]))
})
