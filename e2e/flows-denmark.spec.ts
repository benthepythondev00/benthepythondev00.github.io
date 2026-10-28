// Real user flows on the Denmark Fast-Track jobs page. The page is static, so these run on whatever data the last build wrote.
import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

const shots = process.env.SCREENSHOT_DIR || path.join('test-results', 'screens')
const ROUTE = '/jobs-in-denmark/'

async function snap(page: Page, flow: string, step: number) {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width > 500 ? 900 : 844 })
    await page.screenshot({ path: path.join(shots, `dk-${flow}-${step}-${width}.png`), fullPage: false })
  }
  await page.setViewportSize({ width: 1440, height: 900 })
}

const matchCount = async (page: Page) => Number((await page.locator('#count').textContent())!.split(' ')[0])
let errors: string[] = []

test.beforeEach(async ({ page }) => {
  errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  await page.goto(ROUTE)
})

test.afterEach(() => expect(errors).toEqual([]))

test('first visit shows certified employers by name with a direct apply link', async ({ page }) => {
  await expect(page.getByRole('heading', { level: 1 })).toHaveText("English jobs at Denmark's Fast\u2011Track employers")
  const first = page.locator('.job:visible').first()
  await expect(first.locator('h3')).not.toBeEmpty()
  await expect(first.locator('.where')).not.toBeEmpty() // the employer name is shown, not paywalled
  await expect(first.locator('.sum')).toContainText(/Fast-Track certified employer \(CVR \d{8}\)/)
  await expect(first.locator('a.orig')).toHaveAttribute('href', /^https:\/\//)
  await expect(first.locator('a.orig')).toHaveAttribute('target', '_blank')
  expect(await page.locator('.job:visible').count()).toBeLessThanOrEqual(24)
  await expect(page.locator('footer')).toContainText('Certified companies')
  await snap(page, 'first-visit', 1)
})

test('search and employer filter narrow the list, clearing restores it', async ({ page }) => {
  const all = await matchCount(page)
  const employer = await page.locator('#employer option').nth(1).getAttribute('value')
  await page.selectOption('#employer', employer!)
  const one = await matchCount(page)
  expect(one).toBeGreaterThan(0)
  expect(one).toBeLessThanOrEqual(all)
  const shown = await page.locator('.job:visible').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.employer))
  expect(new Set(shown)).toEqual(new Set([employer]))
  await snap(page, 'employer', 1)
  await page.selectOption('#employer', '')
  await page.fill('#q', 'zzzz-no-such-job')
  await expect(page.locator('#empty')).toBeVisible()
  await snap(page, 'search', 1)
  await page.fill('#q', '')
  expect(await matchCount(page)).toBe(all)
})

test('pay limit filter keeps only posted salaries that reach DKK 552,000', async ({ page }) => {
  await page.getByLabel('Posted salary reaches the DKK 552,000 pay limit').check()
  const pay = await page.locator('.job:visible').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.pay))
  expect(pay.every((v) => v === 'clears' || v === 'maybe')).toBe(true)
  if (pay.length) await expect(page.locator('.job:visible .tags').first()).toContainText('DKK 552,000')
  else await expect(page.locator('#empty')).toBeVisible()
  await snap(page, 'pay', 1)
})

test('show more loads the next 24 jobs', async ({ page }) => {
  const total = await matchCount(page)
  test.skip(total <= 24, 'fewer than 25 jobs today')
  await page.getByRole('button', { name: 'Show more jobs' }).click()
  expect(await page.locator('.job:visible').count()).toBe(Math.min(48, total))
  await snap(page, 'more', 1)
})

test('weekly alert sign-up opens a coded email', async ({ page }) => {
  const cta = page.getByRole('link', { name: 'Email me the weekly alert' })
  await cta.scrollIntoViewIfNeeded()
  await expect(cta).toHaveAttribute('href', /^mailto:.*subject=WEB-DK-ALERT/)
  await snap(page, 'alert', 1)
})
