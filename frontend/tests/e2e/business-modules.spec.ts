import { expect, test } from '@playwright/test'

async function loginAsAdmin(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: /平台管理员/ }).click()
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

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

test('recruitment separates student and admin pages', async ({ page }) => {
  await loginAsAdmin(page)
  await page.goto('/modules/resume-screening')

  await expect(page.getByRole('heading', { name: '招聘系统' })).toBeVisible()
  await page.getByRole('button', { name: '进入学生端' }).click()
  await expect(page).toHaveURL(/recruitment\/student/)
  await expect(page.getByRole('heading', { name: '学生投递端' })).toBeVisible()
  await expect(page.getByRole('button', { name: '查看详情并投递' }).first()).toBeVisible()

  await page.goto('/recruitment/admin')
  await expect(page.getByRole('heading', { name: '招聘管理端' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '岗位管理' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '候选人池' })).toBeVisible()
})

test('student application is visible in admin candidate pool', async ({ page }) => {
  await loginAsAdmin(page)
  const email = `e2e-${Date.now()}@example.com`
  const candidateName = `E2E候选人-${Date.now()}`
  await page.goto('/recruitment/student')
  await page.getByRole('button', { name: '查看详情并投递' }).first().click()
  await page.getByLabel('姓名').fill(candidateName)
  await page.getByLabel('邮箱').fill(email)
  await page.getByLabel('简历内容').fill('SQL、Python、企业AI项目')
  await page.getByRole('button', { name: '提交投递' }).click()
  await expect(page.getByText('投递成功')).toBeVisible()
  await page.goto('/recruitment/admin')
  await expect(page.getByText(candidateName, { exact: true })).toBeVisible()
})
