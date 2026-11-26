# Listing research: Rent Drops, US apartment concession benchmark (Google / AI search)

Date: 2026-11-26
Store: Google Search and AI answer engines (ChatGPT, Perplexity, Google AI Overviews). This is a static page set, not a store listing.

## Search terms
- austin apartment concessions 2026: rank before: not found of 10 (pages not live yet; results led by locators and local news)
- [metro] apartments weeks free: rank before: not found of 10
- net effective rent calculator: rank before: not found of 10 (results are standalone calculators)
- [metro] net effective rent 1 bedroom: rank before: not found of 10
- apartment concession rate by city: rank before: not found of 10

## Rivals
- [Apartment List National Rent Report](https://www.apartmentlist.com/research/national-rent-data): monthly national and metro rent index with a concession indicator; free; leads with the national median and a prose "key stats" list. Monthly, no property rows, no CSV.
- [Redfin Rental Market Tracker](https://www.redfin.com/news/redfin-rental-report/): monthly asking-rent article; free; leads with a year-over-year headline and a summary table. No concessions, no bedroom net-effective split.
- [HelloData](https://www.hellodata.ai/pricing): multifamily comps with concessions; $300 per user a month; leads with "Multifamily Market Analysis: Automated" and a demo/trial CTA.
- [RentCast](https://www.rentcast.io/api): rent estimates and API; free to $449 a month with overages; leads with address lookup. Strong on single-family.
- [Paylode net effective rent](https://paylode.com/articles/net-effective-rent): formula article and calculator; free; leads with the formula and worked example. No market data.
- [Austin Apartment Locators calculator](https://austinapartmentlocators.com/net-effective-rent-calculator/): Austin calculator from a locator; free; leads with renter savings. One city, locator-sourced figures.

## Applied
- Title: "<Metro> apartment concessions & net-effective rent (<snapshot date>)"; hub "US apartment concessions & net-effective rents: 50 metros (<date>)".
- Headline: "<Metro> apartment concessions and net-effective rents".
- Description: share of properties with a concrete special, 1BR asking vs net-effective, plus Studio-3BR medians, free 25-row CSV and calculator.
- Why: the rivals split into free monthly indexes without concessions or rows, and paid seats ($300/user) with them. Locators publish weeks-free ranges without a method. We lead with a dated, counted concession share and net-effective rents per bedroom, with the method visible and the rows downloadable.

## Feature baseline
- Dated metro summary in prose: baseline (3 of 6 rivals); ours: yes, tested by tests/test_build_rent_drops.py Summary + e2e hub flow (one snapshot date)
- Bedroom split of asking rent: baseline (4 of 6); ours: yes, tested by e2e "metro page numbers match the snapshot"
- Concession share / prevalence: baseline (3 of 6: Apartment List indicator, HelloData, locators); ours: yes, strict-regex share, same e2e flow
- Net-effective rent calculator: baseline (3 of 6); ours: yes, tested by tests/rent_drops_calc.test.mjs + e2e calculator flow
- Renewal jump after the special ends: differentiator (Paylode, onlinetoolhubs); ours: yes, tested by calc unit test + e2e calculator flow
- Downloadable rows without login: differentiator (none of the free rivals); ours: yes, e2e CSV flow
- Per-property comps dashboard: differentiator (HelloData, RentCast, paid); ours: no (the paid feed and Listingrail API cover it)
- Week-over-week rent cuts: differentiator (HelloData); ours: locked until 4 weekly snapshots, no figure before (tests: RedLines.test_locked_cuts_publish_no_count_anywhere)
- Cross-site price gap (Zumper vs Apartments.com): differentiator (none); ours: yes, unit + page check

## AI search (GEO/AEO)
- "Which US cities have the most apartment concessions right now?": answered by the hub summary and the first FAQ (top 5 metros with shares and the snapshot date).
- "How many Austin apartments are offering free rent?": answered by the metro summary block and FAQ ("N of M priced Apartments.com properties, X%").
- "What is net effective rent for a 1 bedroom in <metro>?": answered by the metro FAQ and bedroom table (asking, net-effective, n).
- "How do you calculate net effective rent with weeks free?": answered by the method block and FAQ (52/12 weeks a month, lease term as divisor, fees separate).
- "Where can I download apartment concession data as CSV?": answered by the sample section and FAQ (25 rows free, feed from $199/mo, Listingrail free 250 listings/mo).

## Rank after live
(day 7 and day 30 reads are appended here by the engine)
