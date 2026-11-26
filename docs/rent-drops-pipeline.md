# /rent-drops/ weekly snapshot pipeline

`scripts/fetch_rent_drops.py` (logic in `scripts/rent_drops_lib.py`, tests in `tests/test_rent_drops.py`).

- Source: Listingrail API, `source=apartments-com` and `source=zumper`, `type=rent`, `limit=100`, location `"<City>, <ST>"`.
- Roster: 65 ordered candidate metros; the first 50 with >= 60 priced listings (both portals combined, wrong-state rows dropped) are kept. Never padded.
- Output (public on GitHub Pages, so ids and numbers only, no raw blobs, agent names, phones or emails):
  - `data/rent-drops/latest.json`: per-metro concession share, bedroom (Studio-3BR) headline vs net-effective medians (n >= 20, per-bed/co-living plans removed), $/sqft, Zumper vs Apartments.com spread (n >= 20 both), 30-day rent cuts, 25-row sample, and a `method` block with the labelling text.
  - `data/rent-drops/history/<date>.json`: listing id -> asking rent per source plus plan-level rentMin.
  - `data/rent-drops/samples/<slug>.csv`: 25-row sanitized CSV (18 Apartments.com floor plans + 7 Zumper).
- Concessions: strict regex (weeks/months free, %-off for N months, $-off, look & lease, waived fees). Generic taglines, gift cards, reduced fees and "starting at $X" prices do not count. "Rates reflect/include N weeks" is flagged already-net and never discounted twice.
- Rent cuts: locked (`count: null`) until 4 distinct ISO weeks exist in the last 30 days; same-week reruns overwrite.
- Schedule: `.github/workflows/rent-drops.yml`, Thursdays, needs repo secret `LISTINGRAIL_API_KEY` (fails loudly without it). About 13k credits a run, ~40 min with 6 workers.
- Local: `python3 scripts/fetch_rent_drops.py --cache-dir $TMPDIR/rd-cache` (reuses raw responses outside the repo).
