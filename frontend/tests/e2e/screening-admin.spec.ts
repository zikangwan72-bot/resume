import { expect, test } from '@playwright/test'

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.locator('input[autocomplete="username"]').fill('admin@demo.local')
  await page.locator('input[autocomplete="current-password"]').fill('Demo@2026!')
  await page.getByRole('button', { name: /安全进入/ }).click()
  await expect(page).toHaveURL(/dashboard/)
}

test('screening admin covers shell, dashboard, jobs, upload and result detail', async ({ page }) => {
  let reviewPayload: Record<string, unknown> | undefined
  let deleteMethod = ''
  let jobRows = [
    { id: 1, name: '高级产品经理', required_skills: ['产品设计'], preferred_skills: ['AI'], status: 'active' },
    { id: 2, name: '可删除岗位', required_skills: ['SQL'], preferred_skills: [], status: 'inactive' },
  ]
  await page.route('**/api/v1/screening/overview', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: { summary: { job_count: 2, resume_count: 12, pending_count: 3, reviewed_count: 9, job_distribution: [{ id: 1, name: '高级产品经理', count: 7 }, { id: 2, name: '后端工程师', count: 5 }] }, jobs: [{ id: 1, name: '高级产品经理', required_skills: ['产品设计'], preferred_skills: ['AI'], scoring_weights: { required_skills: 0.7, preferred_skills: 0.3 }, status: 'active' }], pending_results: [{ id: 42, filename: 'candidate.pdf', job_name: '高级产品经理', score: 86, recommendation: '建议面试', human_status: 'pending' }] } }) }))
  await page.route('**/api/v1/screening/results', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [{ id: 42, filename: 'candidate.pdf', job_name: '高级产品经理', score: 86, recommendation: '建议面试', human_status: 'pending_review' }] }) }))
  await page.route(/\/api\/v1\/screening\/jobs$/, (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: jobRows }) }))
  await page.route('**/api/v1/screening/jobs/2', (route) => {
    deleteMethod = route.request().method()
    jobRows = jobRows.filter((job) => job.id !== 2)
    return route.fulfill({ status: 204, body: '' })
  })
  await page.route('**/api/v1/screening/resumes', (route) => route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ data: { id: 7, filename: 'candidate.pdf' } }) }))
  await page.route('**/api/v1/screening/resumes/7/screen?job_id=1', (route) => route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ data: { id: 77, filename: 'candidate.pdf', score: 91 } }) }))
  await page.route('**/api/v1/screening/results/77', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: { id: 77, filename: 'candidate.pdf', job_name: '高级产品经理', score: 91, recommendation: '建议面试', human_status: 'pending_review' } }) }))
  await page.route('**/api/v1/screening/results/42/review', (route) => {
    reviewPayload = route.request().postDataJSON()
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: { id: 42, human_status: reviewPayload?.human_status } }) })
  })
  await page.route('**/api/v1/screening/results/42', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: { id: 42, filename: 'candidate.pdf', job_name: '高级产品经理', score: 86, recommendation: '建议面试', human_status: 'pending_review', extracted_text: '个人信息：张三 13800000000\n求职意向：高级产品经理\n教育背景：某大学 本科\n工作经历：负责企业产品规划与交付\n项目经历：主导 AI 招聘系统上线' } }) }))
  await page.route('**/api/v1/screening/jobs/suggest-tags', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: { tags: ['AI产品经验', '跨团队协作', '项目交付'] } }) }))

  await login(page)
  await page.goto('/modules/resume-screening')
  await expect(page.getByRole('heading', { name: 'AI 简历筛选' })).toBeVisible()
  await expect(page.getByText('待跟进', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('cell', { name: '高级产品经理' })).toBeVisible()
  await expect(page.locator('input[type="file"]')).toHaveAttribute('accept', /^\.pdf,\.docx/)
  await page.getByLabel('选择岗位标准').click()
  await page.locator('.ant-select-item-option-content').filter({ hasText: '高级产品经理' }).click()
  await page.locator('input[type="file"]').setInputFiles({ name: 'candidate.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') })
  await page.getByRole('button', { name: /开始上传筛选/ }).click()
  await expect(page).toHaveURL(/screening\/results\/77/)

  await page.goto('/screening/jobs')
  await expect(page.getByRole('heading', { name: '岗位标准' })).toBeVisible()
  await expect(page.locator('.job-action-grid')).toHaveCount(2)
  await expect(page.locator('.job-action-grid').first().locator('.job-action-slot')).toHaveCount(3)
  const deleteRow = page.getByRole('row').filter({ hasText: '可删除岗位' })
  await deleteRow.getByRole('button', { name: '删除' }).click()
  await page.getByRole('tooltip').getByRole('button', { name: /删\s*除/ }).click()
  await expect.poll(() => deleteMethod).toBe('DELETE')
  await expect(page.getByRole('row').filter({ hasText: '可删除岗位' })).toHaveCount(0)
  await page.getByRole('button', { name: /新建岗位标准/ }).click()
  await expect(page.getByRole('dialog')).toContainText('新建岗位标准')
  await expect(page.getByRole('dialog')).toContainText('岗位画像')
  await expect(page.getByRole('dialog')).toContainText('岗位加分标签')
  await expect(page.getByRole('dialog')).toContainText('AI 生成岗位标签')
  await expect(page.getByRole('dialog')).not.toContainText('AI 评分侧重')
  const requiredSection = page.locator('.required-skills-section')
  const requiredSectionBox = await requiredSection.boundingBox()
  const requiredTextareaBox = await requiredSection.locator('textarea').boundingBox()
  expect(requiredSectionBox).not.toBeNull()
  expect(requiredTextareaBox).not.toBeNull()
  expect(requiredTextareaBox!.width).toBeGreaterThan(requiredSectionBox!.width - 60)
  await page.getByRole('dialog').locator('.ant-form-item').filter({ hasText: '岗位名称' }).locator('input').fill('高级产品经理')
  await page.getByRole('button', { name: 'AI 生成岗位标签' }).click()
  await expect(page.getByRole('dialog')).toContainText('AI产品经验')
  await page.keyboard.press('Escape')

  await page.goto('/screening/results/42')
  await expect(page.getByRole('heading', { name: 'candidate.pdf' })).toBeVisible()
  await expect(page.getByText('AI 综合评分')).toBeVisible()
  await expect(page.getByText('待跟进', { exact: true }).first()).toBeVisible()
  await expect(page.locator('.resume-section')).toHaveCount(5)
  const actionGrid = page.locator('.result-action-grid')
  const recommendationBox = await actionGrid.locator('.recommendation-panel').boundingBox()
  const reviewBox = await actionGrid.locator('.review-panel').boundingBox()
  expect(recommendationBox).not.toBeNull()
  expect(reviewBox).not.toBeNull()
  expect(Math.abs(recommendationBox!.height - reviewBox!.height)).toBeLessThanOrEqual(2)
  await expect(page.getByRole('button', { name: '保存复核' })).toBeVisible()
  await page.locator('.review-panel .ant-select').click()
  await page.locator('.ant-select-item-option-content').filter({ hasText: '待跟进' }).click()
  await page.getByRole('button', { name: '保存复核' }).click()
  await expect.poll(() => reviewPayload).toMatchObject({ human_status: 'needs_follow_up' })
  await expect(page).toHaveURL(/modules\/resume-screening/)
})

test('unsupported resume type is rejected before upload', async ({ page }) => {
  await page.route('**/api/v1/screening/overview', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: { summary: {}, jobs: [{ id: 1, name: '岗位标准', status: 'active' }], pending_results: [] } }) }))
  await login(page)
  await page.goto('/modules/resume-screening')
  await page.locator('input[type="file"]').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('not a resume') })
  await expect(page.getByText('仅支持 PDF、DOCX')).toBeVisible()
})

test('resume picker appends files selected in multiple batches', async ({ page }) => {
  await page.route('**/api/v1/screening/overview', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: { summary: {}, jobs: [{ id: 1, name: '岗位标准', status: 'active' }], pending_results: [] } }) }))
  await page.route('**/api/v1/screening/results', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) }))
  await login(page)
  await page.goto('/modules/resume-screening')
  const picker = page.locator('input[type="file"]')
  await picker.setInputFiles({ name: 'first.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') })
  await picker.setInputFiles({ name: 'second.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') })
  await expect(page.locator('.file-queue li')).toHaveCount(2)
})

test('mobile inventory QR route renders its login handoff outside the admin shell', async ({ page }) => {
  await page.goto('/assets/mobile-inventory?asset_uuid=test-asset&token=test-token')
  await expect(page).toHaveURL(/assets\/mobile-inventory/)
  await expect(page.getByText('需要员工登录')).toBeVisible()
  await expect(page.locator('.app-shell')).toHaveCount(0)
})
