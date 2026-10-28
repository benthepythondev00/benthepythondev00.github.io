// Real user flows on the Germany jobs page. The page is static, so these run on whatever data the last build wrote.
import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

const shots = process.env.SCREENSHOT_DIR || path.join('test-results', 'screens')
const ROUTE = '/jobs-in-germany/'

async function snap(page: Page, flow: string, step: number) {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width > 500 ? 900 : 844 })
    await page.screenshot({ path: path.join(shots, `${flow}-${step}-${width}.png`), fullPage: false })
  }
  await page.setViewportSize({ width: 1440, height: 900 })
}

const visibleWho = (page: Page) => page.locator('.job:visible').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.who))
const matchCount = async (page: Page) => Number((await page.locator('#count').textContent())!.split(' ')[0])

let errors: string[] = []

test.beforeEach(async ({ page }) => {
  errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  await page.goto(ROUTE)
})

test('first visit shows English listings with a who-can-apply tag and the original link', async ({ page }) => {
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Jobs in Germany for skilled workers from abroad')
  const first = page.locator('.job:visible').first()
  await expect(first.locator('h3')).not.toBeEmpty()
  await expect(first.locator('.who')).toHaveText(/welcome|residents only|work permit|doesn't say/)
  await expect(first.locator('a.orig')).toHaveAttribute('href', /^https:\/\/www\.arbeitsagentur\.de\/jobsuche\/jobdetail\//)
  await expect(first.locator('a.orig')).toHaveAttribute('target', '_blank')
  expect(await page.locator('.job:visible').count()).toBeLessThanOrEqual(24)
  await expect(page.getByText(/^Source: Bundesagentur für Arbeit/)).toBeVisible()
  await snap(page, 'first-visit', 1)
})

test('region filter: outside the EU hides EU-only and permit-only ads, EU residents see everything', async ({ page }) => {
  await expect(page.locator('#home')).toHaveValue('outside')
  const outside = await matchCount(page)
  expect(await visibleWho(page)).not.toContain('eu')
  expect(await visibleWho(page)).not.toContain('permit')
  await snap(page, 'region', 1)
  await page.selectOption('#home', 'eu')
  const eu = await matchCount(page)
  expect(eu).toBe(await page.locator('.job').count())
  expect(eu).toBeGreaterThanOrEqual(outside)
  await snap(page, 'region', 2)
})

test('only-welcome checkbox keeps ads whose employer sentence invites applicants from abroad', async ({ page }) => {
  await page.getByLabel('Only ads that say applicants from abroad are welcome').check()
  const who = await visibleWho(page)
  expect(who.length).toBeGreaterThan(0)
  expect(new Set(who)).toEqual(new Set(['abroad']))
  await expect(page.locator('.job:visible blockquote').first()).toBeVisible() // the employer's own sentence is quoted
  await snap(page, 'welcome', 1)
})

test('Blue Card and Opportunity Card filters keep only matching ads', async ({ page }) => {
  await page.getByLabel('Salary clears the Blue Card threshold').check()
  const bc = await page.locator('.job:visible').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.bc))
  expect(bc.length).toBeGreaterThan(0)
  expect(bc.every((v) => v === 'yes' || v === 'shortage')).toBe(true)
  await expect(page.locator('.job:visible .tag-bc').first()).toBeVisible()
  await snap(page, 'visa', 1)
  await page.getByLabel('Salary clears the Blue Card threshold').uncheck()
  await page.getByLabel('Opportunity Card friendly (part-time)').check()
  const oc = await page.locator('.job:visible').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.oc))
  expect(oc.length).toBeGreaterThan(0)
  expect(new Set(oc)).toEqual(new Set(['1']))
  await snap(page, 'visa', 2)
})

test('field filter, search and the empty state', async ({ page }) => {
  await page.selectOption('#field', 'Nursing')
  const fields = await page.locator('.job:visible').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.field))
  expect(new Set(fields)).toEqual(new Set(['Nursing']))
  await snap(page, 'search', 1)
  await page.getByLabel('Search title, employer or city').fill('zzzz-no-such-job')
  await expect(page.locator('#empty')).toBeVisible()
  await expect(page.locator('#count')).toHaveText('0 jobs match')
  await snap(page, 'search', 2)
})

test('show more reveals the next page of jobs', async ({ page }) => {
  await page.selectOption('#home', 'eu')
  const before = await page.locator('.job:visible').count()
  await page.getByRole('button', { name: 'Show more jobs' }).click()
  expect(await page.locator('.job:visible').count()).toBeGreaterThan(before)
  await snap(page, 'more', 1)
})

test.afterEach(async () => {
  expect(errors, 'console or page errors').toEqual([])
})

// Custom Apify actor page: coverage check, live quote and the prefilled email.
test.describe('custom actor page', () => {
  const CA = '/custom-apify-actor.html'
  const sendHref = async (page: Page) => decodeURIComponent((await page.locator('#send').getAttribute('href'))!)

  test('first visit shows the three fixed prices and the starter quote', async ({ page }) => {
    await page.goto(CA)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('A custom Apify actor for one website, delivered in 1 to 3 days.')
    await expect(page.locator('#actorCount')).toHaveText(/^\d[\d,]* public$/)
    for (const p of ['$150, delivered in 1 day', '$300, delivered in 2 days', '$600, delivered in 3 days']) await expect(page.getByText(p, { exact: true })).toBeVisible()
    await expect(page.locator('#tierPrice')).toHaveText('$150')
    await snap(page, 'custom-actor-first-visit', 1)
  })

  test('a covered site lists our actors and puts the closest one in the email', async ({ page }) => {
    await page.goto(CA)
    await expect(page.locator('#actorCount')).toHaveText(/public$/)
    await page.getByLabel('Website or URL you need data from').fill('https://www.yelp.com/biz/some-cafe')
    await expect(page.locator('#verdict')).toHaveText(/^Covered/)
    await expect(page.locator('#matches li').first()).toContainText('yelp')
    expect(await sendHref(page)).toContain('Closest existing actor: yelp-')
    await snap(page, 'custom-actor-covered', 1)
    await page.getByLabel('Website or URL you need data from').fill('zzqx-nosuchsite.com')
    await expect(page.locator('#verdict')).toHaveText('No public actor of ours reads that site yet, so this is a new build.')
    await expect(page.locator('#matches li')).toHaveCount(0)
    await snap(page, 'custom-actor-covered', 2)
  })

  test('pages, schedule, monitor and the Store option move the quote and the email code', async ({ page }) => {
    await page.goto(CA)
    await page.getByLabel('Pages per run (listings, profiles or result pages)').fill('3000')
    await expect(page.locator('#tierPrice')).toHaveText('$300')
    expect(await sendHref(page)).toContain('[WEB-ACTOR-STANDARD]')
    await page.getByLabel(/Add the 30-day break monitor/).check()
    await expect(page.locator('#tierPrice')).toHaveText('$600')
    await page.getByLabel(/A generic version may be published/).check()
    await expect(page.locator('#tierPrice')).toHaveText('$550')
    const href = await sendHref(page)
    expect(href).toContain('[WEB-ACTOR-PRODUCTION]')
    expect(href).toContain('Package: Production ($550)')
    await snap(page, 'custom-actor-quote', 1)
    await page.getByLabel('Pages per run (listings, profiles or result pages)').fill('90000')
    await expect(page.locator('#tierPrice')).toHaveText('Custom quote')
    expect(await sendHref(page)).toContain('[WEB-ACTOR-QUOTE]')
    await snap(page, 'custom-actor-quote', 2)
  })

  test('the FAQ opens and links to the managed feeds', async ({ page }) => {
    await page.goto(CA)
    await page.getByText('What happens when the site changes its layout?').click()
    await expect(page.getByText(/daily check run that emails you/).last()).toBeVisible()
    await expect(page.locator('details[open] a[href="./custom.html"]')).toBeVisible()
    await snap(page, 'custom-actor-faq', 1)
  })
})
