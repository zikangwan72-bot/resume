import { expect, test, type Page } from '@playwright/test'

async function loginAsAdmin(page: Page) {
  await page.goto('/login')
  await page.locator('input[autocomplete="username"]').fill('admin@demo.local')
  await page.locator('input[autocomplete="current-password"]').fill('Demo@2026!')
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

test('audit logs are fetched page by page with a total', async ({ page }) => {
  await loginAsAdmin(page)
  const firstPage = page.waitForResponse((response) => response.url().includes('/api/v1/audit-logs?') && response.url().includes('page=1'))
  await page.goto('/audit-logs')
  const body = await (await firstPage).json()
  expect(body.pagination).toMatchObject({ page: 1, page_size: 20 })
  await expect(page.getByText(`共 ${body.pagination.total} 条`)).toBeVisible()
})

test('service desk tickets are paged on the server and filters reset to page one', async ({ page }) => {
  await loginAsAdmin(page)
  const firstPage = page.waitForResponse((response) => response.url().includes('/api/v1/service-desk/tickets?') && response.url().includes('page=1'))
  await page.goto('/modules/service-desk')
  const body = await (await firstPage).json()
  expect(body.pagination).toMatchObject({ page: 1, page_size: 10 })
  await expect(page.getByText(`共 ${body.pagination.total} 张`)).toBeVisible()

  const filtered = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.pathname === '/api/v1/service-desk/tickets' && url.searchParams.get('scope') === 'all' && url.searchParams.get('page') === '1'
  })
  await page.locator('.service-ticket-toolbar').getByText('全部工单', { exact: true }).click()
  expect((await (await filtered).json()).pagination.page).toBe(1)
})
