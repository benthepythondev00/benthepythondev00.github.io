// Net-effective rent & concession maths for /rent-drops/. Pure functions: used by the page and by tests/rent_drops_calc.test.mjs.
// Same formulas as the snapshot method: weeks convert to months at 52/12 weeks a month, the lease term is the divisor,
// and waived fees are a one-time saving that does not change the rent.

export const WEEKS_PER_MONTH = 52 / 12

const num = (v) => {
  if (v === '' || v === null || v === undefined) return 0
  const n = typeof v === 'number' ? v : Number(String(v).replace(/[$,\s]/g, ''))
  return Number.isFinite(n) ? n : NaN
}

/**
 * @param {{asking:number|string, leaseMonths:number|string, kind:'weeks'|'months'|'dollars'|'none', amount:number|string, waivedFees:number|string}} input
 */
export function netEffective(input) {
  const asking = num(input.asking)
  const lease = num(input.leaseMonths)
  const amount = num(input.amount)
  const fees = num(input.waivedFees)
  const kind = input.kind || 'none'

  if (!(asking > 0)) return { ok: false, field: 'asking', error: 'Enter the advertised monthly rent, for example 1,450.' }
  if (asking > 100000) return { ok: false, field: 'asking', error: 'That rent looks too high for one apartment. Check the number.' }
  if (!(lease >= 1 && lease <= 36) || !Number.isInteger(lease)) return { ok: false, field: 'lease', error: 'Lease term must be a whole number of months from 1 to 36.' }
  if (!(amount >= 0)) return { ok: false, field: 'amount', error: 'The concession amount cannot be negative.' }
  if (!(fees >= 0)) return { ok: false, field: 'fees', error: 'Waived fees cannot be negative.' }

  let freeMonths = 0
  if (kind === 'weeks') freeMonths = amount / WEEKS_PER_MONTH
  else if (kind === 'months') freeMonths = amount
  else if (kind === 'dollars') freeMonths = amount / asking

  if (freeMonths >= lease) return { ok: false, field: 'amount', error: 'The free time is as long as the whole lease. Lower the concession or lengthen the lease.' }

  const rentSaving = asking * freeMonths
  const net = asking - rentSaving / lease
  const monthlyDiscount = asking - net
  return {
    ok: true,
    asking,
    lease,
    freeMonths: round(freeMonths, 2),
    net: round(net, 2),
    monthlyDiscount: round(monthlyDiscount, 2),
    discountPct: round((monthlyDiscount / asking) * 100, 2),
    rentSaving: round(rentSaving, 2),
    waivedFees: round(fees, 2),
    totalSaving: round(rentSaving + fees, 2),
    leaseTotal: round(asking * lease - rentSaving, 2),
    // Rent rise at renewal if the landlord keeps the same asking rent and drops the special.
    renewalJumpPct: round(((asking - net) / net) * 100, 1),
  }
}

export function round(x, d) {
  const f = 10 ** d
  return Math.round((x + Number.EPSILON) * f) / f
}

export const usd = (x) => '$' + Math.round(x).toLocaleString('en-US')

// Browser wiring: any <form data-ner> on the page.
if (typeof document !== 'undefined') {
  const wire = (form) => {
    const out = (k) => form.querySelector(`[data-out="${k}"]`)
    const err = form.querySelector('[data-error]')
    const unit = form.querySelector('[data-unit]')
    const amountField = form.querySelector('[name="amount"]')
    const render = () => {
      const fd = new FormData(form)
      const kind = String(fd.get('kind'))
      if (unit) unit.textContent = { weeks: 'weeks free', months: 'months free', dollars: 'dollars off', none: '' }[kind] || ''
      if (amountField) amountField.disabled = kind === 'none'
      const r = netEffective({ asking: fd.get('asking'), leaseMonths: fd.get('lease'), kind, amount: fd.get('amount'), waivedFees: fd.get('fees') })
      form.querySelectorAll('[aria-invalid]').forEach((el) => el.removeAttribute('aria-invalid'))
      if (!r.ok) {
        err.textContent = r.error
        err.hidden = false
        const bad = form.querySelector(`[name="${r.field}"]`)
        if (bad) bad.setAttribute('aria-invalid', 'true')
        form.dataset.state = 'error'
        return
      }
      err.hidden = true
      form.dataset.state = 'ok'
      out('net').textContent = usd(r.net)
      out('discount').textContent = `${usd(r.monthlyDiscount)} a month (${r.discountPct.toFixed(1)}%)`
      out('free').textContent = `${r.freeMonths.toFixed(2)} months`
      out('rent-saving').textContent = usd(r.rentSaving)
      out('total-saving').textContent = usd(r.totalSaving)
      out('lease-total').textContent = usd(r.leaseTotal)
      out('renewal').textContent = `+${r.renewalJumpPct.toFixed(1)}% (${usd(r.asking)} a month)`
      const bar = form.querySelector('[data-bar]')
      if (bar) bar.style.setProperty('--net', String(Math.max(0, Math.min(1, r.net / r.asking))))
    }
    form.addEventListener('input', render)
    form.addEventListener('change', render)
    form.addEventListener('submit', (e) => { e.preventDefault(); render() })
    form.querySelectorAll('[data-preset]').forEach((b) => b.addEventListener('click', () => {
      const p = JSON.parse(b.dataset.preset)
      for (const [k, v] of Object.entries(p)) { const f = form.elements.namedItem(k); if (f) f.value = String(v) }
      render()
    }))
    render()
  }
  document.querySelectorAll('form[data-ner]').forEach(wire)

  // Sortable hub table
  document.querySelectorAll('table[data-sortable]').forEach((table) => {
    const body = table.tBodies[0]
    table.querySelectorAll('th button[data-key]').forEach((btn) => btn.addEventListener('click', () => {
      const key = btn.dataset.key
      const th = btn.closest('th')
      const cur = th.getAttribute('aria-sort')
      const next = cur ? (cur === 'ascending' ? 'descending' : 'ascending') : (btn.dataset.type === 'text' ? 'ascending' : 'descending')
      const asc = next === 'ascending'
      table.querySelectorAll('th').forEach((h) => h.removeAttribute('aria-sort'))
      th.setAttribute('aria-sort', asc ? 'ascending' : 'descending')
      const rows = [...body.rows]
      const val = (r) => {
        const v = r.dataset[key]
        return btn.dataset.type === 'text' ? v : (v === '' ? -Infinity : Number(v))
      }
      rows.sort((a, b) => {
        const x = val(a), y = val(b)
        const c = typeof x === 'string' ? x.localeCompare(y) : x - y
        return asc ? c : -c
      })
      rows.forEach((r) => body.appendChild(r))
    }))
  })
}
