// Income Engine QA crawler. Copy to e2e/crawl.spec.ts unchanged and list every route in e2e/routes.json
// (["/", "/settings", ...]; a Chrome extension: "chrome-extension://{ext}/popup.html", EXT_ID set by your fixture).
// Use pass, each route at 1440 and 390 px: a full-page screenshot <route>-<width>.png in $SCREENSHOT_DIR, then every visible
// button, link, tab, menu item, summary and form field is used once, and so is every control it opens (a dialog, menu or
// sheet). Fails on a control that does nothing (no DOM change, no request, no navigation, no dialog, no validation
// message), a console error, an uncaught page error, a failed request (4xx/5xx), a close or back control that stays on
// the route (each route is opened cold, as from a deep link) and unfilled text ({word}, undefined, NaN).
// Look pass, each route at 375, 430, 768 and 1024 px and in dark mode at 390 and 1440 (<route>-<width>[-dark].png): fails
// on sideways overflow, a broken image or video, a label that spills out of its button or badge, text the same colour as
// its background and, below 500 px, a control under 24 px.
// Every pass checks overflow and unfilled text. Mark a control that must not be clicked with data-qa-skip.
import { expect, test, type Locator, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const routes: string[] = JSON.parse(fs.readFileSync(path.join(__dirname, 'routes.json'), 'utf8'))
const shots = process.env.SCREENSHOT_DIR || path.join('test-results', 'screens')
const CONTROLS = 'button, a[href], [role=button], [role=tab], [role=menuitem], [role=switch], [role=checkbox], summary, input, select, textarea'
const OPENED = CONTROLS.split(', ').map((s) => `${s}:not([data-qa-seen])`).join(', ')
const CLOSE = /^(close|back|cancel|done|dismiss|schließen|zurück|abbrechen|fertig|×|✕)$/i
const LOOK: [number, 'light' | 'dark'][] = [[375, 'light'], [430, 'light'], [768, 'light'], [1024, 'light'], [390, 'dark'], [1440, 'dark']]
const slug =(r: string) => r.replace(/^[a-z-]+:\/\/[^/]+/, '').replace(/^\/|\/$/g, '').replace(/[^a-z0-9]+/gi, '-').toLowerCase() || 'home'
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
  await page.evaluate((sel) => document.querySelectorAll(sel).forEach((e) => e.getClientRects().length && e.setAttribute('data-qa-seen', '')), CONTROLS).catch(() => {})
}

/** Screenshot plus what can be seen without clicking: overflow, unfilled text, broken images, invisible text, tiny controls. */
async function look(page: Page, route: string, name: string, width: number) {
  fs.mkdirSync(shots, { recursive: true })
  await page.screenshot({ path: path.join(shots, `${slug(route)}-${name}.png`), fullPage: true })
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect.soft(over, `${route} scrolls sideways at ${name} by ${over} px`).toBeLessThanOrEqual(1)
  const bad = await page.evaluate((phone) => {
    const out: string[] = []
    const seen = (e: Element) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden' }
    const label = (e: Element) => ((e as HTMLElement).innerText || e.getAttribute('aria-label') || e.outerHTML).trim().slice(0, 60)
    out.push(...(document.body.innerText.match(/\{\w+\}|\bundefined\b|\bNaN\b/g) ?? []).map((h) => `unfilled text "${h}"`))
    for (const img of Array.from(document.querySelectorAll('img'))) if (seen(img) && img.complete && img.naturalWidth === 0) out.push(`broken image ${img.currentSrc || img.src}`)
    // an expired outside media link shows an empty player (Ad Radar #27)
    for (const v of Array.from(document.querySelectorAll('video'))) if (seen(v) && (v.error || v.networkState === 3)) out.push(`broken video ${v.currentSrc || v.src || v.poster}`)
    // a label that spills out of its button or badge (Ad Radar #24: "Alert me on new ads" wrapped past its outline)
    for (const e of Array.from(document.querySelectorAll('button, a[href], [role=button], [role=tab], [role=status], .badge'))) {
      if (!seen(e) || !(e as HTMLElement).innerText.trim() || getComputedStyle(e).overflow !== 'visible') continue  // clipped on purpose (ellipsis)
      const r = e.getBoundingClientRect(), t = document.createRange()
      t.selectNodeContents(e)
      const b = t.getBoundingClientRect()
      if (b.height && (b.right > r.right + 1 || b.bottom > r.bottom + 1 || b.left < r.left - 1 || b.top < r.top - 1)) out.push(`text spills out of "${label(e)}"`)
    }
    const rgb = (s: string) => (s.match(/[\d.]+/g) ?? []).map(Number)
    const lum = (c: number[]) => c.slice(0, 3).map((v) => (v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4).reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0)
    const ground = (e: Element | null): number[] | null => { // the first solid background behind it; an image or gradient: unknown
      for (; e; e = e.parentElement) {
        const s = getComputedStyle(e)
        if (s.backgroundImage !== 'none') return null
        const c = rgb(s.backgroundColor)
        if (c.length === 3 || c[3] > 0.5) return c
      }
      return null
    }
    for (const e of Array.from(document.querySelectorAll('body *'))) {
      if (!Array.from(e.childNodes).some((n) => n.nodeType === 3 && n.textContent!.trim()) || !seen(e)) continue
      const fg = rgb(getComputedStyle(e).color), bg = ground(e)
      if (!bg || (fg.length > 3 && fg[3] < 0.1)) continue
      const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x)
      if ((a + 0.05) / (b + 0.05) < 1.5) out.push(`invisible text "${label(e)}"`)
    }
    if (phone) for (const e of Array.from(document.querySelectorAll('button, [role=button], [role=tab], [role=switch], select, input:not([type=hidden]):not([type=checkbox]):not([type=radio])'))) {
      const r = e.getBoundingClientRect()
      if (seen(e) && !e.hasAttribute('data-qa-skip') && (r.width < 24 || r.height < 24)) out.push(`control "${label(e)}" is ${Math.round(r.width)}x${Math.round(r.height)} px (under 24)`)
    }
    return out
  }, width < 500)
  expect.soft([...new Set(bad)], `${route} at ${name}`).toEqual([])
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

/** Uses el; a dead one goes into dead. Returns its name when it reacted and stayed on the page. */
async function tryUse(page: Page, el: Locator, dead: string[], parent = ''): Promise<string | null> {
  if (!(await el.isVisible().catch(() => false)) || (await el.getAttribute('data-qa-skip').catch(() => null)) !== null) return null
  if (await el.isDisabled().catch(() => false)) return null
  const name = parent + (await el.evaluate((e) => (e.getAttribute('aria-label') || e.textContent || e.outerHTML).trim().slice(0, 80)))
  const href = await el.getAttribute('href')
  if (href !== null && (href === '' || href === '#')) { dead.push(`link "${name}" has no target`); return null }
  const at = page.url()
  try {
    if (!(await use(page, el))) dead.push(`"${name}" does nothing`)
    // a close or back control reacts (press feedback) yet stays put when the screen was opened cold, e.g. from a deep link
    else if (CLOSE.test(name.slice(parent.length)) && page.url() === at && (await el.isVisible().catch(() => false))) dead.push(`"${name}" does not leave the screen`)
    else return page.url() === at ? name : null
  } catch (e) {
    dead.push(`"${name}" could not be used: ${(e as Error).message.split('\n')[0]}`)
  }
  return null
}

for (const width of [1440, 390]) {
  for (const route of routes) {
    test(`crawl ${route} at ${width}px`, async ({ page }) => {
      test.setTimeout(600_000)
      await page.setViewportSize({ width, height: width > 500 ? 900 : 844 })
      const errors = watch(page)
      await open(page, route)
      await look(page, route, String(width), width)
      const dead: string[] = []
      const total = await page.locator(CONTROLS).count()
      for (let i = 0; i < total; i++) {
        const name = await tryUse(page, page.locator(CONTROLS).nth(i), dead)
        // what it opened (a dialog, menu or sheet): each control shown since the route opened, once, one level deep, then the route fresh again
        const n = name ? await page.evaluate((sel) => Array.from(document.querySelectorAll(sel)).filter((e) => e.getClientRects().length).map((e, k) => e.setAttribute('data-qa-n', String(k))).length, OPENED) : 0
        for (let k = 0; k < Math.min(n, 30); k++) await tryUse(page, page.locator(`[data-qa-n="${k}"]`).first(), dead, `${name} › `)
        if (n || page.url() !== url(route) && !page.url().startsWith(url(route) + '#')) await open(page, route) // back for the next control
      }
      expect.soft(dead, `dead controls on ${route} at ${width}px`).toEqual([])
      expect([...new Set(errors)], `errors on ${route} at ${width}px`).toEqual([])
    })
  }
}

for (const [width, scheme] of LOOK) {
  for (const route of routes) {
    test(`look ${route} at ${width}px ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await page.setViewportSize({ width, height: width > 500 ? 900 : 844 })
      const errors = watch(page)
      await open(page, route)
      await look(page, route, scheme === 'dark' ? `${width}-dark` : String(width), width)
      expect([...new Set(errors)], `errors on ${route} at ${width}px ${scheme}`).toEqual([])
    })
  }
}
