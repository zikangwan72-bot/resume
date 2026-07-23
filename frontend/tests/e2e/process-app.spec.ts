import { expect, test } from '@playwright/test'

async function loginAsAdmin(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: /平台管理员/ }).click()
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

test('admin validates the required position when creating an approval user', async ({ page }) => {
  await loginAsAdmin(page)
  await page.goto('/admin/users')
  await page.getByRole('button', { name: '新增员工' }).click()
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText('请输入职位')).toBeVisible()
})
