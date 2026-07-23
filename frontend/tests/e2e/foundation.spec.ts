import { expect, test } from '@playwright/test'

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
  await page.waitForTimeout(400)
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
