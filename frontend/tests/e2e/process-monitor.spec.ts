import { expect, test, type Page } from '@playwright/test'

const users = [
  { id: 'u-1', email: 'zhangsan@example.com', display_name: '张三', department: '产品研发部', position: '产品经理', role: 'department_manager', is_active: true, created_at: '2026-07-23T10:00:00Z' },
  { id: 'u-2', email: 'lisi@example.com', display_name: '李四', department: '财务管理部', position: '财务专员', role: 'finance', is_active: true, created_at: '2026-07-23T10:01:00Z' },
]

const monitorItem = {
  id: 88,
  title: '采购申请 - 高价值',
  status: 'pending',
  submitted_at: '2026-07-24T09:00:00Z',
  created_at: '2026-07-24T09:00:00Z',
  process_app: { id: 3, code: 'purchase', name: '采购申请', version_id: 13, version_number: 1 },
  applicant: { id: 'u-1', name: '张三', email: 'zhangsan@example.com', department: '产品研发部', position: '产品经理' },
  current_node: { id: 1, node_index: 2, node_key: 'sign', name: '领导会签', status: 'pending', timeout_hours: 24, created_at: '2026-07-23T08:00:00Z' },
  current_approvers: [
    { id: 'u-1', name: '张三', email: 'zhangsan@example.com', department: '产品研发部', position: '产品经理' },
    { id: 'u-2', name: '李四', email: 'lisi@example.com', department: '财务管理部', position: '财务专员' },
  ],
  current_approver: { id: 'u-1', name: '张三', email: 'zhangsan@example.com', department: '产品研发部', position: '产品经理' },
  overdue: true,
}

const detail = {
  id: 88,
  process_app_id: 3,
  process_version_id: 13,
  applicant_id: 'u-1',
  applicant_name: '张三',
  applicant_snapshot: { display_name: '张三', email: 'zhangsan@example.com', department: '产品研发部', position: '产品经理' },
  title: monitorItem.title,
  form_data: { amount: 120000 },
  form_schema_snapshot: { fields: [{ id: 'amount', key: 'amount', label: '采购金额', type: 'money', required: true }] },
  idempotency_key: 'request-88',
  status: 'pending',
  current_node_index: 2,
  flow_snapshot: [
    { id: 'start', index: 0, type: 'start', name: '开始' },
    { id: 'sign', index: 2, type: 'countersign', name: '领导会签' },
    { id: 'end', index: 3, type: 'end', name: '结束' },
  ],
  nodes: [
    { id: 1, node_index: 2, node_key: 'sign', timeout_hours: 24, approver_id: 'u-1', approver_name: '张三', status: 'pending', comment: null, acted_at: null },
    { id: 2, node_index: 2, node_key: 'sign', timeout_hours: 24, approver_id: 'u-2', approver_name: '李四', status: 'pending', comment: null, acted_at: null },
  ],
  actions: [{ id: 1, node_id: 1, actor_id: 'u-2', actor_name: '李四', action: 'approve', comment: '材料完整', created_at: '2026-07-24T10:00:00Z' }],
  created_at: '2026-07-24T09:00:00Z',
  updated_at: '2026-07-24T10:00:00Z',
  submitted_at: '2026-07-24T09:00:00Z',
  completed_at: null,
}

async function loginAsAdmin(page: Page) {
  await page.goto('/login')
  await page.evaluate(() => {
    localStorage.removeItem('enterprise_ai_token')
    localStorage.removeItem('enterprise_ai_user')
  })
  await page.reload()
  await page.getByRole('button', { name: /平台管理员 · 平台管理员 admin@demo\.local/ }).click()
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

async function setupMonitorApi(page: Page, options: { summaryStatus?: number } = {}) {
  const requestQueries: URLSearchParams[] = []
  let mutations = 0
  await page.route('**/api/v1/admin/process-apps', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [{ id: 3, code: 'purchase', name: '采购申请' }] }) }))
  await page.route('**/api/v1/admin/users', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: users }) }))
  await page.route('**/api/v1/admin/process-monitor/summary', route => route.fulfill({ status: options.summaryStatus || 200, contentType: 'application/json', body: JSON.stringify(options.summaryStatus && options.summaryStatus >= 400 ? { detail: '统计失败' } : { data: { total: 12, pending: 4, approved: 3, rejected: 2, revoked: 1, overdue: 2 } }) }))
  await page.route('**/api/v1/admin/process-monitor/requests**', route => {
    requestQueries.push(new URL(route.request().url()).searchParams)
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: { items: [monitorItem], total: 31, page: 1, page_size: 20 } }) })
  })
  await page.route('**/api/v1/approvals/**', route => {
    if (route.request().method() !== 'GET') mutations += 1
    return route.fulfill({ status: 405, contentType: 'application/json', body: JSON.stringify({ detail: '只读' }) })
  })
  await page.route('**/api/v1/approvals/requests/88', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: detail }) }))
  return { requestQueries, mutations: () => mutations }
}

test('keeps request data visible when only the summary endpoint fails', async ({ page }) => {
  await setupMonitorApi(page, { summaryStatus: 500 })
  await loginAsAdmin(page)
  await page.goto('/admin/process-monitor')

  await expect(page.getByText('统计汇总暂时不可用，流程实例仍可正常查看')).toBeVisible()
  await expect(page.getByRole('row', { name: /采购申请.*张三.*领导会签.*张三.*李四/ })).toBeVisible()
  await expect(page.getByText('流程实例加载失败')).toHaveCount(0)
})

test('monitors processes with all typed filters and a read-only request drawer', async ({ page }) => {
  test.setTimeout(60_000)
  const api = await setupMonitorApi(page)
  await loginAsAdmin(page)
  await page.goto('/admin/process-monitor')

  await expect(page.getByRole('heading', { name: '流程监控' })).toBeVisible()
  await expect(page.locator('.ant-statistic')).toHaveCount(6)
  await expect(page.getByText('审批类型', { exact: true })).toHaveCount(0)
  await expect(page.getByText('表单模板', { exact: true })).toHaveCount(0)
  await expect(page.getByText('流程模板', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('row', { name: /采购申请.*张三.*领导会签.*张三.*李四/ })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '已运行' })).toBeVisible()
  await expect(page.getByLabel('流程实例列表').getByText('已超时', { exact: true })).toBeVisible()

  await page.getByLabel('流程应用筛选').click()
  await page.getByText('采购申请', { exact: true }).last().click()
  await page.getByLabel('运行状态筛选').click()
  await page.getByText('审批中', { exact: true }).last().click()
  await page.getByPlaceholder('开始日期').click()
  const picker = page.locator('.ant-picker-dropdown:not(.ant-picker-dropdown-hidden)')
  const selectDate = async (title: string) => {
    let cell = picker.locator(`td[title="${title}"] .ant-picker-cell-inner`)
    if (await cell.count() === 0) {
      await picker.locator('.ant-picker-header-prev-btn').first().click()
      cell = picker.locator(`td[title="${title}"] .ant-picker-cell-inner`)
    }
    await expect(cell).toHaveCount(1)
    await cell.click()
  }
  await selectDate('2026-07-20')
  await selectDate('2026-07-24')
  await page.getByLabel('申请部门筛选').fill('产品研发部')
  await page.getByLabel('申请人筛选').fill('张三')
  await page.getByLabel('当前审批人筛选').click()
  await page.getByText('李四 | 财务管理部 | 财务专员', { exact: true }).click()
  await page.getByLabel('是否超时筛选').click()
  await page.getByText('是', { exact: true }).last().click()
  await page.getByRole('button', { name: /查\s*询/ }).click()
  await expect.poll(() => api.requestQueries.at(-1)?.get('process_app_id')).toBe('3')
  expect(api.requestQueries.at(-1)?.get('status')).toBe('pending')
  expect(api.requestQueries.at(-1)?.get('department')).toBe('产品研发部')
  expect(api.requestQueries.at(-1)?.get('applicant')).toBe('张三')
  expect(api.requestQueries.at(-1)?.get('current_approver_id')).toBe('u-2')
  expect(api.requestQueries.at(-1)?.get('overdue')).toBe('true')

  await page.getByRole('button', { name: /重\s*置/ }).click()
  await expect.poll(() => api.requestQueries.at(-1)?.get('process_app_id')).toBeNull()
  await page.locator('.ant-pagination-item-2').click()
  await expect.poll(() => api.requestQueries.at(-1)?.get('page')).toBe('2')

  await page.getByRole('button', { name: '查看详情' }).click()
  const drawer = page.locator('.ant-drawer').filter({ hasText: '流程实例详情' })
  await expect(drawer.getByText('申请人和流程版本')).toBeVisible()
  await expect(drawer.getByText('采购金额')).toBeVisible()
  await expect(drawer.getByText('当前审批人')).toBeVisible()
  await expect(drawer.getByText('领导会签')).toBeVisible()
  await expect(drawer.getByText('材料完整')).toBeVisible()
  await expect(drawer.getByRole('button', { name: /同意|驳回|撤回|催办|转审/ })).toHaveCount(0)
  await drawer.getByRole('link', { name: '打开申请详情' }).click()
  await expect(page).toHaveURL('/modules/approval-center/88')
  expect(api.mutations()).toBe(0)
})

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
]) {
  test(`keeps process monitor within ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await setupMonitorApi(page)
    await loginAsAdmin(page)
    await page.goto('/admin/process-monitor')
    await expect(page.getByRole('table')).toBeVisible()
    const layout = await page.evaluate(() => ({ viewport: window.innerWidth, scrollWidth: document.documentElement.scrollWidth }))
    expect(layout.scrollWidth).toBeLessThanOrEqual(layout.viewport)
    await page.screenshot({ path: `../artifacts/process-monitor-${viewport.width}x${viewport.height}.png`, fullPage: true })
  })
}

test('removes all legacy approval-admin routes while retaining platform audit logs', async ({ page }) => {
  await loginAsAdmin(page)
  for (const path of ['/admin/approval-types', '/admin/form-templates', '/admin/flow-templates', '/admin/roles', '/admin/approval-logs']) {
    await page.goto(path)
    await expect(page.getByText('页面不存在')).toBeVisible()
  }
  await page.goto('/audit-logs')
  await expect(page.getByRole('heading', { name: '审计日志' })).toBeVisible()
})
