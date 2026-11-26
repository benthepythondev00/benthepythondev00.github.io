---
date: 2026-11-26
job: job_ebd4afa63a3243b6
repo: benthepythondev00.github.io
kind: portfolio
---
Homepage rebuilt as static HTML hubs so crawlers find every sitemap URL: 5 H2 verticals (Managed B2B Data Feeds, EU & US Rental Yield Benchmarks, Reddit Archive Data Samples, Paid Telegram Memberships, Apify & RapidAPI Scrapers), all 54 yield markets, both Reddit sample pages, 5 API kits and /memberwall/ linked from the root, top 48 Actors pre-rendered. Before: 64 of 108 sitemap URLs unreachable from the homepage; after: 108 of 108 at click depth 1. Static words 1,232 to ~3,850. ItemList JSON-LD added next to the unchanged WebSite/Person nodes; root /llms.txt added; homepage sitemap lastmod.
Files: index.html, scripts/build_home_hubs.py, scripts/check_reachability.py, tests/test_home_hubs.py, llms.txt, sitemap.xml, .github/workflows/sync-catalog.yml
Deploy: GitHub Pages on merge to main; the hourly catalog sync re-renders the generated blocks.
Blocker: none
Next: on 2026-12-17 compare Search Console indexed pages (baseline 0/100) and Bing indexed pages (baseline 0).
