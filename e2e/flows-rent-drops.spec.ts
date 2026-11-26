// Real visitor flows on /rent-drops/. Static pages, so every number is checked against data/rent-drops/latest.json,
// the snapshot the pages were built from.
import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

const shots = process.env.SCREENSHOT_DIR || path.join('test-results', 'screens')
const usd = (x: number) => '$' + Math.round(x).toLocaleString('en-US')

const frame = (page: Page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null)))))

async function snap(page: Page, flow: string, step: number) {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width > 500 ? 900 : 844 })
    await frame(page)
    const file = path.join(shots, `rd-${flow}-${step}-${width}.png`)
    for (let attempt = 1; ; attempt++) {
      // Headless Chromium on a loaded box can refuse a capture before the resized frame is composited; retry a little.
      try { await page.screenshot({ path: file }); break } catch (e) {
        if (attempt === 4) throw e
        await page.waitForTimeout(400 * attempt)
        await frame(page)
      }
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 })
}

let errors: string[] = []
test.beforeEach(async ({ page }) => {
  errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
})
test.afterEach(() => expect(errors).toEqual([]))

async function snapshot(page: Page) {
  const res = await page.request.get('/data/rent-drops/latest.json')
  expect(res.ok()).toBeTruthy()
  return res.json()
}

test('@live hub lists every metro with its concession share and one snapshot date', async ({ page }) => {
  const data = await snapshot(page)
  await page.goto('/rent-drops/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText(`${data.metros.length} US metros`)
  const rows = page.locator('table.hub tbody tr')
  await expect(rows).toHaveCount(data.metros.length)
  const top = [...data.metros].sort((a: any, b: any) => (b.concessions.share_pct ?? -1) - (a.concessions.share_pct ?? -1))[0]
  await expect(rows.first().locator('th')).toHaveText(top.label)
  await expect(rows.first().locator('td').first()).toHaveText(`${Math.round(top.concessions.share_pct)}%`)
  const dates = await page.locator('time').evaluateAll((els) => [...new Set(els.map((e) => e.getAttribute('datetime')))])
  expect(dates).toEqual([data.snapshot_date])
  await snap(page, 'hub', 1)

  await page.getByRole('button', { name: 'Metro' }).click()
  const names = await rows.locator('th').allTextContents()
  expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b)))
  await snap(page, 'hub', 2)
})

test('@live metro page numbers match the snapshot and held buckets show no median', async ({ page }) => {
  const data = await snapshot(page)
  for (const m of data.metros.slice(0, 1).concat(data.metros.filter((x: any) => Object.values(x.bedrooms).some((b: any) => !b.published)).slice(0, 1))) {
    await page.goto(`/rent-drops/${m.slug}/`)
    await expect(page.getByRole('heading', { level: 1 })).toContainText(m.label)
    const rows = page.locator('table.beds tbody tr')
    for (const [i, b] of ['0', '1', '2', '3'].entries()) {
      const e = m.bedrooms[b]
      const row = rows.nth(i)
      if (e.published) {
        await expect(row.locator('td').nth(0)).toHaveText(usd(e.headline_median))
        await expect(row.locator('td').nth(1)).toHaveText(usd(e.net_effective_median))
      } else {
        await expect(row).toContainText(`Not shown: ${e.n} floor plan`)
        await expect(row).not.toContainText('$')
      }
    }
    if (m.concessions.share_pct !== null) await expect(page.locator('.share-num')).toHaveText(`${Math.round(m.concessions.share_pct)}%`)
    if (!m.rent_cuts_30d.unlocked) {
      await expect(page.locator('#rent-cuts')).toContainText(`${m.rent_cuts_30d.weeks_collected} of 4 weekly snapshots collected`)
      await expect(page.locator('#rent-cuts .cuts-num')).toHaveCount(0)
    }
    await expect(page.locator('#method')).toContainText(data.method.label)
    await snap(page, `metro-${m.slug}`, 1)
  }
})

test('@live calculator turns a special into net-effective rent, worked by hand', async ({ page }) => {
  const data = await snapshot(page)
  await page.goto(`/rent-drops/${data.metros[0].slug}/`)
  const form = page.locator('form[data-ner]')
  await form.locator('[name=asking]').fill('1500')
  await form.locator('[name=lease]').fill('12')
  await form.locator('[name=kind]').selectOption('weeks')
  await form.locator('[name=amount]').fill('6')
  await form.locator('[name=fees]').fill('250')
  // 6 weeks = 1.3846 months; 1500 * 1.3846 = 2076.92 saved; 1500 - 2076.92 / 12 = 1326.92
  await expect(form.locator('[data-out=net]')).toHaveText('$1,327')
  await expect(form.locator('[data-out=rent-saving]')).toHaveText('$2,077')
  await expect(form.locator('[data-out=total-saving]')).toHaveText('$2,327')
  await expect(form.locator('[data-out=discount]')).toHaveText('$173 a month (11.5%)')
  // (1500 - 1326.92) / 1326.92 = 13.04% rise when the special ends
  await expect(form.locator('[data-out=renewal]')).toHaveText('+13.0% ($1,500 a month)')
  await snap(page, 'calc', 1)

  await form.locator('[name=kind]').selectOption('months')
  await form.locator('[name=amount]').fill('12')
  await expect(form.locator('[data-error]')).toContainText('whole lease')
  await expect(form.locator('[name=amount]')).toHaveAttribute('aria-invalid', 'true')
  await snap(page, 'calc', 2)

  await form.locator('[name=amount]').fill('1')
  await expect(form.locator('[data-error]')).toBeHidden()
  await expect(form.locator('[data-out=net]')).toHaveText('$1,375')
})

test('@live free CSV sample downloads with no login and matches the page', async ({ page }) => {
  const data = await snapshot(page)
  const m = data.metros[0]
  await page.goto(`/rent-drops/${m.slug}/`)
  const link = page.getByRole('link', { name: `Download ${m.slug}.csv` })
  const href = await link.getAttribute('href')
  const res = await page.request.get(href!)
  expect(res.status()).toBe(200)
  const lines = (await res.text()).trim().split(/\r?\n/)
  expect(lines.length).toBe(26)
  expect(lines[0]).not.toMatch(/email|phone|agent/i)
  await expect(page.locator('table.sample tbody tr')).toHaveCount(25)
  await expect(page.locator('table.sample tbody tr').first().locator('td').nth(4)).toHaveText(usd(m.sample_rows[0].asking_rent))
})

test('@live CTAs carry UTM tags to feeds, Listingrail and Apify', async ({ page }) => {
  const data = await snapshot(page)
  const slug = data.metros[0].slug
  await page.goto(`/rent-drops/${slug}/`)
  await expect(page.getByRole('link', { name: 'See feed plans' })).toHaveAttribute('href', `/feeds/?utm_source=rent_drops&utm_medium=cta&utm_campaign=${slug}#real-estate`)
  await expect(page.getByRole('link', { name: 'Listingrail pricing' })).toHaveAttribute('href', `https://listingrail.com/pricing/?utm_source=rent_drops&utm_medium=cta&utm_campaign=${slug}`)
  await expect(page.getByRole('link', { name: 'Open on Apify' })).toHaveAttribute('href', /apify\.com\/benthepythondev\/zumper-rental-scraper\?utm_source=rent_drops/)
  await page.getByRole('link', { name: 'See feed plans' }).click()
  await expect(page).toHaveURL(/\/feeds\//)
  await expect(page.locator('#real-estate')).toBeVisible()
})
