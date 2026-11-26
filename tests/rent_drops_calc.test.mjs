// node --test tests/*.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { netEffective, WEEKS_PER_MONTH, usd } from '../rent-drops/calc.mjs'

test('6 weeks free on $1,500 over 12 months, worked by hand', () => {
  // 6 weeks = 6 / (52/12) = 1.3846 months; saving 1500 * 1.3846 = 2076.92; net = 1500 - 2076.92/12 = 1326.92
  const r = netEffective({ asking: 1500, leaseMonths: 12, kind: 'weeks', amount: 6, waivedFees: 0 })
  assert.equal(r.ok, true)
  assert.equal(r.freeMonths, 1.38)
  assert.equal(r.net, 1326.92)
  assert.equal(r.rentSaving, 2076.92)
  assert.equal(r.discountPct, 11.54)
  assert.equal(r.leaseTotal, 15923.08)
})

test('1 month free on $1,200 over 12 months is 1/12 off', () => {
  const r = netEffective({ asking: 1200, leaseMonths: 12, kind: 'months', amount: 1 })
  assert.equal(r.net, 1100)
  assert.equal(r.monthlyDiscount, 100)
})

test('lease term is the divisor: 2 months free on a 15-month lease', () => {
  const r = netEffective({ asking: 1800, leaseMonths: 15, kind: 'months', amount: 2 })
  assert.equal(r.net, 1560) // 1800 - 3600/15
})

test('dollar amount off spreads over the lease', () => {
  const r = netEffective({ asking: '$1,500', leaseMonths: '12', kind: 'dollars', amount: '600' })
  assert.equal(r.net, 1450)
  assert.equal(r.rentSaving, 600)
})

test('waived fees add to the total saving but never change the rent', () => {
  const a = netEffective({ asking: 1500, leaseMonths: 12, kind: 'months', amount: 1, waivedFees: 0 })
  const b = netEffective({ asking: 1500, leaseMonths: 12, kind: 'months', amount: 1, waivedFees: 350 })
  assert.equal(a.net, b.net)
  assert.equal(b.totalSaving, a.totalSaving + 350)
})

test('no concession leaves the rent unchanged', () => {
  const r = netEffective({ asking: 1500, leaseMonths: 12, kind: 'none', amount: 8 })
  assert.equal(r.net, 1500)
  assert.equal(r.freeMonths, 0)
})

test('weeks convert at 52/12', () => {
  assert.equal(WEEKS_PER_MONTH, 52 / 12)
  const r = netEffective({ asking: 1200, leaseMonths: 12, kind: 'weeks', amount: 52 / 12 })
  assert.equal(r.net, 1100)
})

test('bad input names the field and the fix', () => {
  assert.deepEqual(
    [netEffective({ asking: '', leaseMonths: 12, kind: 'none' }).field,
      netEffective({ asking: 'abc', leaseMonths: 12, kind: 'none' }).field,
      netEffective({ asking: 1500, leaseMonths: 0, kind: 'none' }).field,
      netEffective({ asking: 1500, leaseMonths: 12.5, kind: 'none' }).field,
      netEffective({ asking: 1500, leaseMonths: 12, kind: 'weeks', amount: -1 }).field,
      netEffective({ asking: 1500, leaseMonths: 12, kind: 'none', waivedFees: -5 }).field],
    ['asking', 'asking', 'lease', 'lease', 'amount', 'fees'])
  const r = netEffective({ asking: 1500, leaseMonths: 6, kind: 'months', amount: 6 })
  assert.equal(r.ok, false)
  assert.match(r.error, /whole lease/)
})

test('usd formats whole dollars', () => {
  assert.equal(usd(1326.92), '$1,327')
})

test('renewal jump: 6 weeks free on $2,000 jumps 13.0% when the special ends (matches published worked examples)', () => {
  // net = 2000 - 2000 * (6 / (52/12)) / 12 = 1769.23; (2000 - 1769.23) / 1769.23 = 13.04%
  const r = netEffective({ asking: 2000, leaseMonths: 12, kind: 'weeks', amount: 6 })
  assert.equal(r.net, 1769.23)
  assert.equal(r.renewalJumpPct, 13)
})
