import { expect, test } from '@playwright/test'

async function loginAsAdmin(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: /平台管理员/ }).click()
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

test('admin can enter the four-module foundation on desktop and mobile', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: '企业AI工作流平台' })).toBeVisible()
  await page.getByRole('button', { name: /平台管理员/ }).click()
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
  await expect(page.getByRole('heading', { name: '工作台' })).toBeVisible()
  await expect(page.locator('.ant-layout-sider')).toHaveCSS('background-color', 'rgb(0, 21, 41)')
  await expect(page.locator('.ant-card').first()).toBeVisible()
  await expect(page.locator('.ant-btn-primary').first()).toHaveCSS('background-color', 'rgb(22, 119, 255)')
  await expect(page.locator('.module-card')).toHaveCount(4)
  await page.screenshot({
    path: '../artifacts/screenshots/dashboard-desktop.png',
    fullPage: true,
  })

  const modules = [
    ['resume-screening', 'AI简历筛选'],
    ['asset-management', '全资产管理'],
    ['service-desk', '企业IT服务台'],
  ]
  for (const [key, title] of modules) {
    await page.goto(`/modules/${key}`)
    await expect(page.getByRole('heading', { name: title })).toBeVisible()
    await expect(page.getByText('Foundation only')).toBeVisible()
  }

  await page.goto('/modules/approval-center')
  await expect(page.getByRole('heading', { name: '流程审批中心' })).toBeVisible()

  await page.goto('/dashboard')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  await expect(page.getByRole('heading', { name: '工作台' })).toBeVisible()
  await expect(page.locator('.app-sider')).toHaveCount(0)
  await page.getByRole('button', { name: '切换导航' }).click()
  await expect(page.locator('.ant-drawer')).toBeVisible()
  await expect(page.getByText('业务模块', { exact: true })).toBeVisible()
  await page.locator('.mobile-nav-drawer .ant-drawer-close').click()
  await expect(page.locator('.mobile-nav-drawer .ant-menu-item-group-title').first()).not.toBeVisible()
  const layout = await page.evaluate(() => ({
    viewport: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    cards: [...document.querySelectorAll('.module-card')].map((node) => {
      const box = node.getBoundingClientRect()
      return { width: box.width, height: box.height }
    }),
  }))
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.viewport)
  expect(layout.cards).toHaveLength(4)
  for (const card of layout.cards) {
    expect(card.width).toBeLessThanOrEqual(358)
    expect(card.height).toBeGreaterThanOrEqual(260)
  }
  await page.screenshot({
    path: '../artifacts/screenshots/dashboard-mobile.png',
    fullPage: true,
  })
})

test('governance views render mocked AI values and smoke headings', async ({ page }) => {
  await page.route('**/api/v1/ai-runs', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ data: [{ id: 1, module: '简历筛选', task_type: '候选人排序', model: 'gpt-5', status: 'completed', latency_ms: 248, human_review: true, created_at: '2026-07-23 10:00' }] }),
  }))
  await loginAsAdmin(page)
  await page.goto('/ai-runs')
  for (const value of ['简历筛选', '候选人排序', 'gpt-5', '248', '2026-07-23 10:00', 'completed', '需要']) {
    await expect(page.getByText(value, { exact: true })).toBeVisible()
  }
  await page.goto('/audit-logs')
  await expect(page.getByRole('heading', { name: '审计日志' })).toBeVisible()
  await page.goto('/profile')
  await expect(page.getByRole('heading', { name: '个人资料' })).toBeVisible()
})

test('profile card body uses the available width instead of collapsing into the avatar column', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await loginAsAdmin(page)
  await page.goto('/profile')

  const layout = await page.evaluate(() => {
    const card = document.querySelector('.profile-sheet')!.getBoundingClientRect()
    const body = document.querySelector('.profile-sheet .ant-card-body')!.getBoundingClientRect()
    const main = document.querySelector('.profile-main')!.getBoundingClientRect()
    const name = document.querySelector('.profile-main h2')!.getBoundingClientRect()
    return { cardWidth: card.width, bodyWidth: body.width, mainWidth: main.width, nameHeight: name.height }
  })

  expect(layout.bodyWidth).toBeGreaterThan(layout.cardWidth * 0.9)
  expect(layout.mainWidth).toBeGreaterThan(layout.cardWidth * 0.7)
  expect(layout.nameHeight).toBeLessThan(40)
})

test('approval and module failures stay distinct from empty responses and rows support keyboards', async ({ page }) => {
  let approvalAttempts = 0
  await page.route('**/api/v1/approvals/requests', (route) => {
    approvalAttempts += 1
    const payload = approvalAttempts === 1
      ? { message: '服务异常' }
      : { data: approvalAttempts === 2 ? [] : [{ id: 77, title: '采购申请', status: 'pending', created_at: '2026-07-23T10:00:00' }] }
    return route.fulfill({ status: approvalAttempts === 1 ? 500 : 200, contentType: 'application/json', body: JSON.stringify(payload) })
  })
  await page.route('**/api/v1/modules/asset-management/summary', (route) => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ message: '模块服务暂不可用' }) }))
  await loginAsAdmin(page)
  await page.goto('/modules/asset-management')
  await expect(page.getByText('模块服务暂不可用')).toBeVisible()
  await expect(page.getByRole('button', { name: /重\s*试/ })).toBeVisible()

  await page.goto('/modules/approval-center/requests')
  await expect(page.getByText('申请记录加载失败')).toBeVisible()
  await page.getByRole('button', { name: /重\s*试/ }).click()
  await expect(page.getByText('暂无申请记录')).toBeVisible()
  await page.reload()
  const approvalRow = page.getByRole('button', { name: /采购申请/ })
  await approvalRow.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/approval-center\/77/)

  await page.route('**/api/v1/notifications', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [{ id: 9, title: '审批已发布', content: '请查看流程', category: 'approval', read_at: null, created_at: '2026-07-23' }] }) }))
  await page.route('**/api/v1/notifications/9/read', (route) => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ message: '写入失败' }) }))
  await page.goto('/notifications')
  const notification = page.getByRole('button', { name: /审批已发布/ })
  await notification.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByText('标记通知已读失败')).toBeVisible()
})

test('product demo role is blocked from audit API and menu', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: /产品演示用户/ }).click()
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
  await expect(page.getByText('审计日志', { exact: true })).toHaveCount(0)

  const token = await page.evaluate(() => localStorage.getItem('enterprise_ai_token'))
  const response = await page.request.get('http://127.0.0.1:8000/api/v1/audit-logs', {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(response.status()).toBe(403)
})
