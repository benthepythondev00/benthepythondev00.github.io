// Coverage check and quote builder for custom-apify-actor.html. Pure functions, tested with `node --test tests/*.mjs`.

const TWO_PART_SUFFIXES = new Set(['co.uk', 'org.uk', 'ac.uk', 'com.au', 'net.au', 'co.nz', 'co.za', 'co.jp', 'co.in', 'com.br', 'com.mx', 'com.tr', 'com.sg', 'co.kr'])

export const TIERS = {
  starter: { code: 'WEB-ACTOR-STARTER', label: 'Starter', price: 150, days: 1, pages: 1000 },
  standard: { code: 'WEB-ACTOR-STANDARD', label: 'Standard', price: 300, days: 2, pages: 5000 },
  production: { code: 'WEB-ACTOR-PRODUCTION', label: 'Production', price: 600, days: 3, pages: 50000 },
}
export const PUBLIC_DISCOUNT = 50

// "https://www.yelp.co.uk/biz/x" -> ["yelp"]; "google maps reviews" -> ["google", "maps", "reviews"]
export function queryTokens(input) {
  const raw = String(input || '').trim().toLowerCase()
  if (!raw) return []
  if (/^[a-z]+:\/\//.test(raw) || /^[^\s]+\.[a-z]{2,}(\/|$)/.test(raw)) {
    let host
    try { host = new URL(raw.includes('://') ? raw : `https://${raw}`).hostname } catch { return [] }
    const parts = host.replace(/^www\./, '').split('.').filter(Boolean)
    if (parts.length < 2) return parts
    const cut = TWO_PART_SUFFIXES.has(parts.slice(-2).join('.')) ? 3 : 2
    return [parts[Math.max(0, parts.length - cut)]]
  }
  return raw.split(/[^a-z0-9]+/).filter((w) => w.length >= 2 && !['scraper', 'scraping', 'scrape', 'data', 'the', 'and', 'from'].includes(w))
}

// Actors whose name or title holds every token as a whole word, most used first.
export function findActors(actors, input, limit = 6) {
  const tokens = queryTokens(input)
  if (!tokens.length) return []
  const res = tokens.map((t) => new RegExp(`(^|[^a-z0-9])${t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z0-9]|$)`))
  return actors
    .filter((a) => { const hay = `${a.name} ${a.title}`.toLowerCase().replace(/-/g, ' '); return res.every((r) => r.test(hay)) })
    .sort((a, b) => (b.users30d || 0) - (a.users30d || 0))
    .slice(0, limit)
}

// The cheapest tier that covers the request; null when it needs a custom quote.
export function pickTier({ pages = 0, schedule = false, monitor = false } = {}) {
  const n = Number(pages) || 0
  if (n > TIERS.production.pages) return null
  if (monitor) return 'production'
  if (schedule || n > TIERS.starter.pages) return n > TIERS.standard.pages ? 'production' : 'standard'
  return 'starter'
}

export function quote(opts = {}) {
  const tier = pickTier(opts)
  if (!tier) return null
  const t = TIERS[tier]
  return { tier, ...t, total: t.price - (opts.publicOk ? PUBLIC_DISCOUNT : 0) }
}

export function mailtoHref({ site = '', pages = 0, schedule = false, monitor = false, publicOk = false, actor = '' } = {}) {
  const q = quote({ pages, schedule, monitor, publicOk })
  const code = q ? q.code : 'WEB-ACTOR-QUOTE'
  const subject = `[${code}] Custom Apify actor${site ? `: ${site}` : ''}`
  const body = [
    'Inquiry source: owned custom-actor page',
    `Offer code: ${code}`,
    `Package: ${q ? `${q.label} ($${q.total})` : 'Custom quote (over 50,000 pages per run)'}`,
    '',
    `Site or URL: ${site}`,
    `Closest existing actor: ${actor || 'none found'}`,
    `Pages per run: ${pages || ''}`,
    `Scheduled runs: ${schedule ? 'yes' : 'no'}`,
    `Break monitor: ${monitor ? 'yes' : 'no'}`,
    `Generic version may be published on our Apify Store page: ${publicOk ? 'yes' : 'no'}`,
    'Fields you need:',
    'Delivery (JSON/CSV/Sheet/webhook):',
    'Intended use:',
  ].join('\n')
  return `mailto:benthepythondev0@gmail.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
}
