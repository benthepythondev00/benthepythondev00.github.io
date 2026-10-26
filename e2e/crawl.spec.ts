// Income Engine QA crawler. Copy to e2e/crawl.spec.ts unchanged and list every route in e2e/routes.json
// (["/", "/settings", ...]; a Chrome extension: "chrome-extension://{ext}/popup.html", EXT_ID set by your fixture).
// Each route at 1440 and 390 px: a full-page screenshot <route>-<width>.png in $SCREENSHOT_DIR, then every visible
// button, link, tab, menu item, summary and form field is used once. Fails on a control that does nothing (no DOM
// change, no request, no navigation, no dialog, no validation message), a console error, an uncaught page error, a
// failed request (4xx/5xx) and sideways overflow at 390 px. Mark a control that must not be clicked with data-qa-skip.
import { expect, test, type Locator, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const routes: string[] = JSON.parse(fs.readFileSync(path.join(__dirname, 'routes.json'), 'utf8'))
const shots = process.env.SCREENSHOT_DIR || path.join('test-results', 'screens')
const CONTROLS = 'button, a[href], [role=button], [role=tab], [role=menuitem], [role=switch], [role=checkbox], summary, input, select, textarea'
const slug = (r: string) => r.replace(/^[a-z-]+:\/\/[^/]+/, '').replace(/^\/|\/$/g, '').replace(/[^a-z0-9]+/gi, '-').toLowerCase() || 'home'
const url = (r: string) => r.replace('{ext}', process.env.EXT_ID ?? '{ext}')

function watch(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console error: ${m.text()}`) })
  page.on('pageerror', (e) => errors.push(`page error: ${e.message}`))
  page.on('response', (r) => { if (r.status() >= 400) errors.push(`${r.status()} ${r.request().method()} ${r.url()}`) })
  page.on('dialog', (d) => d.dismiss().catch(() => {}))
  return errors
}

async function open(page: Page, route: string) {
  await page.goto(url(route))
  await page.waitForLoadState('networkidle').catch(() => {})
}

/** One use of a control; true when the page reacted. */
async function use(page: Page, el: Locator): Promise<boolean> {
  const tag = await el.evaluate((e) => e.tagName.toLowerCase())
  const type = (await el.getAttribute('type')) ?? ''
  if (tag === 'select') {
    const n = await el.locator('option').count()
    if (n < 2) return true
    await el.selectOption({ index: 1 })
    return true
  }
  if ((tag === 'input' && !['checkbox', 'radio', 'submit', 'button', 'file', 'hidden', 'range', 'color'].includes(type)) || tag === 'textarea') {
    await el.fill(type === 'email' ? 'qa@example.com' : type === 'number' ? '3' : type === 'url' ? 'https://example.com' : 'QA test')
    return (await el.inputValue()) !== ''
  }
  const before = page.url()
  await page.evaluate(() => {
    const w = window as unknown as { __qa: number; __qaObs?: MutationObserver }
    w.__qa = 0
    w.__qaObs?.disconnect()
    w.__qaObs = new MutationObserver((m) => { w.__qa += m.length })
    w.__qaObs.observe(document, { subtree: true, childList: true, attributes: true, characterData: true })
  }).catch(() => {})
  let requests = 0
  const count = () => { requests++ }
  page.on('request', count)
  const popup = page.context().waitForEvent('page', { timeout: 1500 }).catch(() => null)
  await el.click({ timeout: 3000 })
  await page.waitForTimeout(600)
  page.off('request', count)
  const opened = await popup
  if (opened) await opened.close()
  if (page.url() !== before || requests || opened) return true
  return await page.evaluate(() => {
    const w = window as unknown as { __qa: number }
    return w.__qa > 0 || !!document.querySelector(':invalid')
  }).catch(() => true) // the page went away: it navigated
}

for (const width of [1440, 390]) {
  for (const route of routes) {
    test(`crawl ${route} at ${width}px`, async ({ page }) => {
      test.setTimeout(300_000)
      await page.setViewportSize({ width, height: width > 500 ? 900 : 844 })
      const errors = watch(page)
      await open(page, route)
      fs.mkdirSync(shots, { recursive: true })
      await page.screenshot({ path: path.join(shots, `${slug(route)}-${width}.png`), fullPage: true })
      if (width === 390) {
        const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
        expect.soft(over, `${route} scrolls sideways at 390 px by ${over} px`).toBeLessThanOrEqual(1)
      }
      const dead: string[] = []
      const total = await page.locator(CONTROLS).count()
      for (let i = 0; i < total; i++) {
        const el = page.locator(CONTROLS).nth(i)
        if (!(await el.isVisible().catch(() => false)) || (await el.getAttribute('data-qa-skip')) !== null) continue
        if (await el.isDisabled().catch(() => false)) continue
        const name = (await el.evaluate((e) => (e.getAttribute('aria-label') || e.textContent || e.outerHTML).trim().slice(0, 80)))
        const href = await el.getAttribute('href')
        if (href !== null && (href === '' || href === '#')) { dead.push(`link "${name}" has no target`); continue }
        try {
          if (!(await use(page, el))) dead.push(`"${name}" does nothing`)
        } catch (e) {
          dead.push(`"${name}" could not be used: ${(e as Error).message.split('\n')[0]}`)
        }
        if (page.url() !== url(route) && !page.url().startsWith(url(route) + '#')) await open(page, route) // back for the next control
      }
      expect.soft(dead, `dead controls on ${route} at ${width}px`).toEqual([])
      expect([...new Set(errors)], `errors on ${route} at ${width}px`).toEqual([])
    })
  }
}
