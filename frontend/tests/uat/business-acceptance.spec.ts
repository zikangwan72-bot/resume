import { expect, test, type Page } from '@playwright/test'

const evidenceDir = '../artifacts/uat-20260725'
const flowName = 'UAT-单节点审批-20260725'

async function login(page: Page, role: '平台管理员' | '产品演示用户') {
  await page.goto('/login')
  await page.getByRole('button', { name: new RegExp(role) }).click()
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

async function logout(page: Page) {
  await page.getByRole('button', { name: '账户菜单' }).click()
  await page.getByText('退出登录', { exact: true }).click()
  await expect(page).toHaveURL(/login/)
}

test.describe.serial('UAT real database acceptance', () => {
  test('retained recruitment and asset records remain visible after reload', async ({ page }) => {
    await login(page, '平台管理员')

    await page.goto('/recruitment/admin')
    await expect(page.getByText('UAT-AI产品经理实习生-20260725', { exact: true })).toBeVisible()
    const candidate = page.locator('.recruitment-candidate-table').getByRole('row').filter({ hasText: 'UAT候选人-20260725' })
    await expect(candidate).toContainText('待面试')
    await page.screenshot({ path: `${evidenceDir}/REC-success.png`, fullPage: true })

    await page.goto('/modules/asset-management')
    await page.getByRole('tab', { name: '资产台账' }).click()
    const asset = page.getByRole('row').filter({ hasText: 'UAT-ASSET-20260725-001' })
    await expect(asset).toContainText('UAT更新责任人')
    await expect(asset).toContainText('在用')
    await page.getByRole('tab', { name: '异常处置' }).click()
    await expect(page.getByRole('tabpanel', { name: '异常处置' }).getByRole('row').filter({ hasText: 'UAT验收笔记本' })).toContainText('已归档')
    await page.screenshot({ path: `${evidenceDir}/AST-success.png`, fullPage: true })
  })

  test('single-node approval completes across two real UI roles', async ({ page }) => {
    await login(page, '平台管理员')
    await page.goto('/modules/approval-center/requests')
    const request = page.getByRole('button').filter({ hasText: flowName }).first()
    await expect(request).toBeVisible()
    const requestText = await request.innerText()

    await logout(page)
    await login(page, '产品演示用户')
    if (requestText.includes('审批中')) {
      await page.goto('/modules/approval-center/pending')
      const pending = page.locator('.pending-card-full').filter({ hasText: flowName })
      await expect(pending).toBeVisible()
      await pending.getByRole('button', { name: /同\s*意/ }).click()
      await expect(page.getByText('已审批通过')).toBeVisible()
    }
    await page.goto('/modules/approval-center/handled')
    await expect(page.getByText(new RegExp(flowName))).toBeVisible()
    await page.screenshot({ path: `${evidenceDir}/APR-product-approved.png`, fullPage: true })

    await logout(page)
    await login(page, '平台管理员')
    await page.goto('/modules/approval-center/requests')
    await expect(page.getByRole('button').filter({ hasText: flowName }).first()).toContainText('已通过')
    await page.goto('/admin/process-monitor')
    await expect(page.getByText(flowName, { exact: true }).first()).toBeVisible()
    await page.screenshot({ path: `${evidenceDir}/APR-admin-complete.png`, fullPage: true })
  })

  test('permissions and responsive layouts meet acceptance boundaries', async ({ page }) => {
    await login(page, '产品演示用户')
    await expect(page.getByText('审计日志', { exact: true })).toHaveCount(0)
    await page.goto('/audit-logs')
    await expect(page).toHaveURL(/dashboard/)

    await page.setViewportSize({ width: 390, height: 844 })
    for (const [route, heading] of [
      ['/dashboard', '工作台'],
      ['/modules/asset-management', '全资产管理'],
      ['/modules/resume-screening', '招聘系统'],
      ['/modules/approval-center', '流程审批中心'],
    ] as const) {
      await page.goto(route)
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
      const width = await page.evaluate(() => ({
        viewport: window.innerWidth,
        content: document.documentElement.scrollWidth,
      }))
      expect(width.content).toBeLessThanOrEqual(width.viewport)
    }
    await page.screenshot({ path: `${evidenceDir}/UI-mobile-success.png`, fullPage: true })
  })
})
