import { expect, test, type Page } from '@playwright/test'

const authenticatedRoutes = [
  ['/dashboard', '工作台', 'dashboard'],
  ['/modules/resume-screening', 'AI 简历筛选', 'resume-screening'],
  ['/modules/approval-center', '流程审批中心', 'approval-home'],
  ['/modules/approval-center/requests', '我的申请', 'approval-requests'],
  ['/modules/approval-center/new', '发起申请', 'approval-new'],
  ['/modules/approval-center/pending', '待我审批', 'approval-pending'],
  ['/modules/approval-center/handled', '我已审批', 'approval-handled'],
  ['/modules/asset-management', '全资产管理', 'asset-management'],
  ['/admin/users', '员工与审批角色', 'admin-users'],
  ['/admin/process-apps', '流程应用', 'process-apps'],
  ['/admin/process-monitor', '流程监控', 'process-monitor'],
  ['/modules/service-desk', '企业IT服务台', 'service-desk'],
  ['/notifications', '通知中心', 'notifications'],
  ['/ai-runs', 'AI运行记录', 'ai-runs'],
  ['/audit-logs', '审计日志', 'audit-logs'],
  ['/profile', '个人资料', 'profile'],
] as const

const mobileRoutes = authenticatedRoutes.filter(([route]) => [
  '/dashboard',
  '/modules/resume-screening',
  '/modules/approval-center',
  '/modules/approval-center/new',
  '/modules/asset-management',
  '/admin/users',
  '/admin/process-apps',
  '/admin/process-monitor',
  '/profile',
].includes(route))

async function loginAsAdmin(page: Page) {
  await page.goto('/login')
  await page.locator('input[autocomplete="username"]').fill('admin@demo.local')
  await page.locator('input[autocomplete="current-password"]').fill('Demo@2026!')
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

async function assertVisualHealth(page: Page, heading: string) {
  await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
  await expect(page.locator('.ant-spin-spinning')).toHaveCount(0)
  await expect(page.locator('.ant-skeleton')).toHaveCount(0)
  const health = await page.evaluate(() => {
    const clippedControls = [...document.querySelectorAll<HTMLElement>('.ant-btn:not(.ant-btn-icon-only), .ant-tabs-tab-btn, .page-heading h1')]
      .filter((element) => element.offsetParent !== null && element.scrollWidth > element.clientWidth + 1)
      .map((element) => element.textContent?.trim() || element.className)
    return {
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      clippedControls,
    }
  })
  expect(health.documentWidth).toBeLessThanOrEqual(health.viewportWidth + 1)
  expect(health.clippedControls).toEqual([])
}

test('all production routes keep a consistent Ant Design desktop shell', async ({ page }) => {
  test.setTimeout(90_000)
  const runtimeIssues: string[] = []
  page.on('pageerror', (error) => runtimeIssues.push(`pageerror: ${error.message}`))
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') runtimeIssues.push(`${message.type()}: ${message.text()}`)
  })

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: '企业AI工作流平台' })).toBeVisible()
  await page.screenshot({ path: '../artifacts/final-ui-audit/00-login-desktop.png', fullPage: true })
  await loginAsAdmin(page)

  for (const [route, heading, slug] of authenticatedRoutes) {
    await page.goto(route)
    await assertVisualHealth(page, heading)
    await expect(page.locator('.app-shell')).toBeVisible()
    await expect(page.locator('.ant-layout-sider')).toBeVisible()
    await page.screenshot({ path: `../artifacts/final-ui-audit/desktop-${slug}.png`, fullPage: true })
  }

  expect(runtimeIssues).toEqual([])
})

test('core production routes reflow cleanly on mobile', async ({ page }) => {
  const runtimeIssues: string[] = []
  page.on('pageerror', (error) => runtimeIssues.push(`pageerror: ${error.message}`))
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') runtimeIssues.push(`${message.type()}: ${message.text()}`)
  })

  await page.setViewportSize({ width: 390, height: 844 })
  await loginAsAdmin(page)
  for (const [route, heading, slug] of mobileRoutes) {
    await page.goto(route)
    await assertVisualHealth(page, heading)
    await expect(page.locator('.app-sider')).toHaveCount(0)
    await page.screenshot({ path: `../artifacts/final-ui-audit/mobile-${slug}.png`, fullPage: true })
  }
  expect(runtimeIssues).toEqual([])
})
