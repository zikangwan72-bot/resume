import { expect, test, type Page } from '@playwright/test'

async function login(page: Page, email: string) {
  await page.goto('/login')
  await page.locator('input[autocomplete="username"]').fill(email)
  await page.locator('input[autocomplete="current-password"]').fill('Demo@2026!')
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

async function logout(page: Page) {
  await page.evaluate(() => localStorage.clear())
}

test('employee submits a ticket, IT claims it, asks for details, resolves, employee confirms', async ({ page }) => {
  const title = `E2E 打印机脱机 ${Date.now()}`
  const drawer = page.locator('.service-ticket-drawer')

  await login(page, 'employee01@demo.local')
  await page.goto('/modules/service-desk')
  await expect(page.getByRole('heading', { name: '企业IT服务台' })).toBeVisible()
  await page.getByRole('button', { name: /提交工单/ }).first().click()
  const modal = page.locator('.ant-modal')
  await modal.getByPlaceholder('例如：VPN 连上后无法访问内网').fill(title)
  await modal.getByPlaceholder('发生了什么、什么时候开始、已经尝试过什么').fill('三楼打印机一直显示脱机，重启无效。')
  await modal.getByRole('button', { name: /提\s*交/ }).click()
  await expect(page.getByText(title)).toBeVisible()
  await page.screenshot({ path: '../artifacts/screenshots/service-desk-employee.png', fullPage: true })

  await logout(page)
  await login(page, 'it01@demo.local')
  await page.goto('/modules/service-desk')
  await page.getByText(title).click()
  await drawer.getByRole('button', { name: '我来接单' }).click()
  await expect(drawer.locator('.ant-tag', { hasText: '处理中' })).toBeVisible()
  await drawer.getByPlaceholder('需要提单人补充什么？例如：报错截图、设备编号').fill('请告诉我打印机贴纸上的资产编号')
  await drawer.getByRole('button', { name: '请提单人补充信息' }).click()
  await expect(drawer.locator('.ant-tag', { hasText: '待补充' })).toBeVisible()

  await logout(page)
  await login(page, 'employee01@demo.local')
  await page.goto('/modules/service-desk')
  await page.getByText(title).click()
  await drawer.getByPlaceholder('按处理人的要求补充说明').fill('资产编号 BYD-PRN-2026-007')
  await drawer.getByRole('button', { name: '提交补充信息' }).click()
  await expect(drawer.locator('.ant-tag', { hasText: '处理中' })).toBeVisible()

  await logout(page)
  await login(page, 'it01@demo.local')
  await page.goto('/modules/service-desk')
  await page.locator('.ant-radio-button-wrapper', { hasText: '我负责的' }).click()
  await page.getByText(title).click()
  await drawer.getByPlaceholder('处理结果，提单人会收到通知并确认').fill('重新安装打印机驱动后恢复')
  await drawer.getByRole('button', { name: '标记已解决' }).click()
  await expect(drawer.locator('.ant-tag', { hasText: '已解决' })).toBeVisible()
  await page.screenshot({ path: '../artifacts/screenshots/service-desk-admin-drawer.png', fullPage: true })

  await logout(page)
  await login(page, 'employee01@demo.local')
  await page.goto('/modules/service-desk')
  await page.getByText(title).click()
  await expect(drawer.getByText(/前未确认将自动关闭/)).toBeVisible()
  await drawer.getByRole('button', { name: '确认解决并关闭' }).click()
  await expect(drawer.locator('.ant-tag', { hasText: '已关闭' })).toBeVisible()
  await expect(drawer.getByText(/确认解决并关闭，评分 5 星/)).toBeVisible()
})

test('service desk is usable on a phone-width screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page, 'employee02@demo.local')
  await page.goto('/modules/service-desk')
  await expect(page.getByRole('heading', { name: '企业IT服务台' })).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(1)
  await page.screenshot({ path: '../artifacts/screenshots/service-desk-390.png', fullPage: true })
})
