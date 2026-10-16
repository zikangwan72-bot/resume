import { expect, test, type Page } from '@playwright/test'

async function login(page: Page, email: string) {
  await page.goto('/login')
  await page.locator('input[autocomplete="username"]').fill(email)
  await page.locator('input[autocomplete="current-password"]').fill('Demo@2026!')
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

async function openTicketForm(page: Page, title: string) {
  await page.goto('/modules/service-desk')
  await page.getByRole('button', { name: /提交工单/ }).first().click()
  const form = page.getByRole('dialog', { name: '提交 IT 工单' })
  await form.getByPlaceholder('例如：VPN 连上后无法访问内网').fill(title)
  await form.getByPlaceholder('发生了什么、什么时候开始、已经尝试过什么').fill('会话过期后重新登录，表单内容应保留。')
  return form
}

async function expireToken(page: Page) {
  await page.evaluate(() => localStorage.setItem('enterprise_ai_token', 'expired-token'))
}

test('expired session asks for the password in place and keeps the unsaved form', async ({ page }) => {
  const title = `E2E 会话过期 ${Date.now()}`
  await login(page, 'employee01@demo.local')
  const form = await openTicketForm(page, title)
  await expireToken(page)

  await form.getByRole('button', { name: /提\s*交/ }).click()

  const relogin = page.getByRole('dialog', { name: '登录已过期' })
  await expect(relogin).toBeVisible()
  await expect(relogin.locator('input[disabled]')).toHaveValue('employee01@demo.local')
  await expect(page).toHaveURL(/\/modules\/service-desk$/)
  await expect(form.getByPlaceholder('例如：VPN 连上后无法访问内网')).toHaveValue(title)

  await relogin.locator('input[autocomplete="current-password"]').fill('wrong-password')
  await relogin.getByRole('button', { name: /重新登录/ }).click()
  await expect(relogin.getByText('密码不正确。')).toBeVisible()

  await relogin.locator('input[autocomplete="current-password"]').fill('Demo@2026!')
  await relogin.getByRole('button', { name: /重新登录/ }).click()

  await expect(relogin).toBeHidden()
  // The original submit was retried with the new token.
  await expect(page.getByText(title)).toBeVisible()
  await expect(page).toHaveURL(/\/modules\/service-desk$/)
})

test('switching account from the expired-session dialog goes to the login page', async ({ page }) => {
  await login(page, 'employee01@demo.local')
  const form = await openTicketForm(page, `E2E 切换账号 ${Date.now()}`)
  await expireToken(page)

  await form.getByRole('button', { name: /提\s*交/ }).click()
  const relogin = page.getByRole('dialog', { name: '登录已过期' })
  await relogin.getByRole('button', { name: /切换账号/ }).click()

  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => localStorage.getItem('enterprise_ai_token'))).toBeNull()
})
