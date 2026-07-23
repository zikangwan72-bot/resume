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

async function loginAsAdmin(page: Page) {
  await page.goto('/login')
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
