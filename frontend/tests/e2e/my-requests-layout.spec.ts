import { expect, test } from '@playwright/test'

async function loginAsAdmin(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: /平台管理员/ }).click()
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

test('my requests card keeps title and time on separate rows', async ({ page }) => {
  await page.route('**/api/v1/approvals/requests', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      data: [{ id: 77, title: '业务验收测试流程 - 2026/7/24', status: 'pending', created_at: '2026-07-24T06:09:00' }],
    }),
  }))

  await loginAsAdmin(page)
  await page.goto('/modules/approval-center/requests')

  const card = page.getByRole('button', { name: /业务验收测试流程/ })
  const title = card.locator('.request-info strong')
  const date = card.locator('.request-info small')
  const tag = card.locator('.ant-tag')
  await expect(card).toBeVisible()

  const [cardBox, titleBox, dateBox, tagBox] = await Promise.all([
    card.boundingBox(), title.boundingBox(), date.boundingBox(), tag.boundingBox(),
  ])
  expect(cardBox).not.toBeNull()
  expect(titleBox).not.toBeNull()
  expect(dateBox).not.toBeNull()
  expect(tagBox).not.toBeNull()
  expect(cardBox!.height).toBeGreaterThan(52)
  expect(dateBox!.y).toBeGreaterThanOrEqual(titleBox!.y + titleBox!.height)
  expect(tagBox!.x).toBeGreaterThan(titleBox!.x)
  expect(Math.abs((tagBox!.y + tagBox!.height / 2) - (cardBox!.y + cardBox!.height / 2))).toBeLessThan(4)

  await card.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/approval-center\/77/)
})
