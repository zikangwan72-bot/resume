import { expect, test, type Page } from '@playwright/test'

async function loginAsAdmin(page: Page) {
  await page.goto('/login')
  await page.locator('input[autocomplete="username"]').fill('admin@demo.local')
  await page.locator('input[autocomplete="current-password"]').fill('Demo@2026!')
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

test('frequent pages become interactive within the local navigation budget', async ({ page }) => {
  const routes = [
    ['AI简历筛选', 'AI 简历筛选'],
    ['流程审批中心', '流程审批中心'],
    ['全资产管理', '全资产管理'],
    ['流程应用', '流程应用'],
    ['流程监控', '流程监控'],
    ['员工管理', '员工与审批角色'],
  ] as const
  const timings: Record<string, number> = {}

  await loginAsAdmin(page)
  await page.waitForTimeout(1_000)

  for (const [menuLabel, heading] of routes) {
    const startedAt = Date.now()
    await page.locator('.app-menu').getByText(menuLabel, { exact: true }).click()
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    await expect(page.locator('.ant-spin-spinning')).toHaveCount(0)
    await expect(page.locator('.ant-skeleton')).toHaveCount(0)
    timings[menuLabel] = Date.now() - startedAt
  }

  console.log(`Navigation timings: ${JSON.stringify(timings)}`)
  for (const duration of Object.values(timings)) expect(duration).toBeLessThan(1_500)
})
