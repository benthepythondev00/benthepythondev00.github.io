// node --test tests/*.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { queryTokens, findActors, pickTier, quote, mailtoHref } from '../custom-apify-actor.mjs'

const { actors } = JSON.parse(readFileSync(new URL('../data/actors.json', import.meta.url)))

test('queryTokens reads the site name from URLs, bare hosts and words', () => {
  assert.deepEqual(queryTokens('https://www.yelp.com/biz/some-cafe'), ['yelp'])
  assert.deepEqual(queryTokens('shop.example.co.uk/products'), ['example'])
  assert.deepEqual(queryTokens('zillow.com'), ['zillow'])
  assert.deepEqual(queryTokens('Google Maps reviews scraper'), ['google', 'maps', 'reviews'])
  assert.deepEqual(queryTokens('   '), [])
  assert.deepEqual(queryTokens('http://'), [])
})

test('findActors matches whole words in the real catalog, most used first', () => {
  const yelp = findActors(actors, 'https://www.yelp.com/biz/x')
  assert.ok(yelp.length >= 1 && yelp.every((a) => /yelp/.test(a.name)))
  const reddit = findActors(actors, 'reddit.com')
  assert.ok(reddit.length > 1)
  for (let i = 1; i < reddit.length; i++) assert.ok((reddit[i - 1].users30d || 0) >= (reddit[i].users30d || 0))
  assert.ok(findActors(actors, 'reddit', 3).length <= 3)
  assert.deepEqual(findActors(actors, 'zzqx-nosuchsite.com'), [])
  // whole word: "eba" must not match "ebay"
  assert.deepEqual(findActors([{ name: 'ebay-scraper', title: 'eBay' }], 'eba'), [])
})

test('pickTier picks the cheapest tier that covers pages, schedule and monitor', () => {
  assert.equal(pickTier({ pages: 800 }), 'starter')
  assert.equal(pickTier({ pages: 1000 }), 'starter')
  assert.equal(pickTier({ pages: 1001 }), 'standard')
  assert.equal(pickTier({ pages: 200, schedule: true }), 'standard')
  assert.equal(pickTier({ pages: 5001 }), 'production')
  assert.equal(pickTier({ pages: 100, monitor: true }), 'production')
  assert.equal(pickTier({ pages: 50001 }), null)
})

test('quote applies the public-build discount and mailto carries the offer code', () => {
  assert.equal(quote({ pages: 500 }).total, 150)
  assert.equal(quote({ pages: 500, publicOk: true }).total, 100)
  assert.equal(quote({ pages: 90000 }), null)
  const href = mailtoHref({ site: 'yelp.com', pages: 3000, actor: 'yelp-intelligence-scraper' })
  const subject = decodeURIComponent(href.match(/subject=([^&]*)/)[1])
  const body = decodeURIComponent(href.match(/body=(.*)$/)[1])
  assert.equal(subject, '[WEB-ACTOR-STANDARD] Custom Apify actor: yelp.com')
  assert.match(body, /Package: Standard \(\$300\)/)
  assert.match(body, /Closest existing actor: yelp-intelligence-scraper/)
  assert.match(mailtoHref({ pages: 60000 }), /WEB-ACTOR-QUOTE/)
})
