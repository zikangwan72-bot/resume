import { expect, test } from '@playwright/test'

async function loginAsAdmin(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.locator('input[autocomplete="username"]').fill('admin@demo.local')
  await page.locator('input[autocomplete="current-password"]').fill('Demo@2026!')
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

test('recruitment candidate and management portals use separate entry routes', async ({ page }) => {
  await page.goto('/recruitment/student')
  await expect(page.getByRole('heading', { name: '岗位投递' })).toBeVisible()

  await loginAsAdmin(page)
  await page.goto('/recruitment/admin')
  await expect(page).toHaveURL(/recruitment\/admin/)
  await expect(page.getByRole('heading', { name: '招聘管理端' })).toBeVisible()
})

test('dashboard provides direct entries to asset and AI resume screening', async ({ page }) => {
  await loginAsAdmin(page)
  // 等工作台的健康状态加载完再点击，避免页面重排时点击落空
  await expect(page.getByText(/已就绪/)).toBeVisible()

  const assetCard = page.locator('.module-card').filter({ hasText: '全资产管理' })
  await expect(assetCard).toBeVisible()
  await assetCard.getByRole('button', { name: '进入全资产管理' }).click()
  await expect(page).toHaveURL(/modules\/asset-management/)
  await expect(page.getByRole('heading', { name: '全资产管理' })).toBeVisible()

  await page.goto('/dashboard')
  const screeningCard = page.locator('.module-card').filter({ hasText: 'AI 简历筛选' })
  await expect(screeningCard).toBeVisible()
  await screeningCard.getByRole('button', { name: '进入AI 简历筛选' }).click()
  await expect(page).toHaveURL(/modules\/resume-screening/)
  await expect(page.getByRole('heading', { name: 'AI 简历筛选' })).toBeVisible()
})

test('integrated business pages remain readable at tablet and mobile widths', async ({ page }) => {
  await loginAsAdmin(page)
  const routes = [
    ['/modules/asset-management', '全资产管理', 'asset'],
    ['/modules/resume-screening', 'AI 简历筛选', 'resume-screening'],
    ['/modules/approval-center', '流程审批中心', 'approval-center'],
  ] as const

  for (const viewport of [{ width: 1024, height: 768 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport)
    for (const [route, heading, slug] of routes) {
      await page.goto(route)
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()

      const layout = await page.evaluate(() => {
        const cards = [...document.querySelectorAll<HTMLElement>('.metric-card')]
        const heading = document.querySelector<HTMLElement>('.page-heading')
        return {
          viewport: window.innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          headingRight: heading?.getBoundingClientRect().right ?? 0,
          metricRows: new Set(cards.map((card) => Math.round(card.getBoundingClientRect().top))).size,
          metricCount: cards.length,
        }
      })

      expect(layout.scrollWidth).toBeLessThanOrEqual(layout.viewport)
      expect(layout.headingRight).toBeLessThanOrEqual(layout.viewport)
      if (viewport.width === 390 && layout.metricCount > 1) {
        expect(layout.metricRows).toBe(layout.metricCount)
      }
      await page.screenshot({
        path: `../artifacts/screenshots/${slug}-${viewport.width}.png`,
        fullPage: true,
      })
    }
  }
})

test('asset management reads real records and supports mutation entry points', async ({ page }) => {
  await loginAsAdmin(page)
  await page.goto('/modules/asset-management')

  await expect(page.getByRole('heading', { name: '全资产管理' })).toBeVisible()
  await expect(page.getByText('资产总值')).toBeVisible()
  await expect(page.getByText('资产盘点工作流')).toBeVisible()
  await expect(page.getByText('建立盘点任务')).toBeVisible()
  await expect(page.getByText('扫码盘点', { exact: true })).toBeVisible()
  await expect(page.getByText('差异复核', { exact: true })).toBeVisible()
  await expect(page.getByText('处置归档', { exact: true })).toBeVisible()

  await page.getByRole('tab', { name: '资产台账' }).click()
  await expect(page.getByText('资产编号')).toBeVisible()
  await expect(page.getByText('BYD-LAP-2026-001')).toBeVisible()

  await page.getByRole('tab', { name: '异常处置' }).click()
  await expect(page.getByText('盘亏待核实')).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '描述' })).toBeVisible()
})

test('inventory task supports real scan records and difference review', async ({ page }) => {
  await loginAsAdmin(page)
  await page.goto('/modules/asset-management')
  await page.getByRole('tab', { name: '盘点工作台' }).click()

  const taskCard = page.locator('.task-card').filter({ hasText: '深圳办公与研发资产' })
  await expect(taskCard).toBeVisible()
  await taskCard.getByRole('button', { name: '进入盘点' }).click()
  await expect(page.getByRole('heading', { name: '扫码盘点监控台' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '盘点结果' })).toBeVisible()

  const recordRow = page.getByRole('row').filter({ hasText: 'BYD-LAP-2026-001' })
  await expect(recordRow).toBeVisible()
  await expect(recordRow.getByText('未盘点', { exact: true })).toBeVisible()
  await expect(recordRow.getByRole('button', { name: '打印码' })).toBeVisible()
  await recordRow.getByRole('button', { name: /二维码/ }).click()
  const qrDialog = page.getByRole('dialog', { name: '资产二维码' })
  await expect(qrDialog).toBeVisible()
  await expect(page.getByAltText('资产二维码')).toBeVisible()
  await qrDialog.getByRole('button', { name: 'Close' }).click()
  await expect(qrDialog).not.toBeVisible()

  await page.getByRole('button', { name: '关闭盘点抽屉' }).click()
  await taskCard.getByRole('button', { name: '差异复核' }).click()
  await expect(page.getByRole('tab', { name: '异常处置', selected: true })).toBeVisible()
})

test('business forms block incomplete submissions with clear messages', async ({ page }) => {
  await loginAsAdmin(page)

  await page.goto('/modules/asset-management')
  await page.getByRole('tab', { name: '资产台账' }).click()
  await page.getByRole('button', { name: '新增资产' }).click()
  await page.getByRole('button', { name: '保存资产' }).click()
  await expect(page.getByText('请完整填写资产必填信息')).toBeVisible()
  await page.keyboard.press('Escape')

  await page.getByRole('button', { name: '新建盘点任务' }).click()
  await expect(page.getByLabel('盘点范围')).toBeVisible()
  await expect(page.getByLabel('负责人')).toBeVisible()
  await expect(page.getByPlaceholder('选择截止日期')).toBeVisible()
  await page.getByLabel('盘点范围').click()
  const allAssetsOption = page.locator('.ant-select-dropdown:visible .ant-select-item-option-content').filter({ hasText: '全部资产' })
  await expect(allAssetsOption).toBeVisible()
  await allAssetsOption.click()
  await page.getByLabel('负责人').click()
  const adminOption = page.locator('.ant-select-dropdown:visible .ant-select-item-option-content').filter({ hasText: '平台管理员' })
  await expect(adminOption).toBeVisible()
  await adminOption.click()
  await page.getByRole('button', { name: '创建任务' }).click()
  await expect(page.getByText('请选择盘点范围、负责人和截止日期')).toBeVisible()
  await page.screenshot({ path: '../artifacts/inventory-task-selectors.png', fullPage: true })
  await page.keyboard.press('Escape')

})
