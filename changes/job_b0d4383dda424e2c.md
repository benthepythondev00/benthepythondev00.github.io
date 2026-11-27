---
date: 2026-11-27
job: job_b0d4383dda424e2c
repo: benthepythondev00.github.io
kind: venture_build
---
Added the /rent-drops/ page builder (step 2): a hub and one page per metro, generated from data/rent-drops/latest.json. Each page has a dated 130-170 word summary, Studio-3BR headline vs net-effective tables (n>=20, held buckets show the count only), concession share, a net-effective rent calculator, locked 30-day cuts, the Zumper gap, a 25-row sample with a CSV link, a Listingrail snippet, UTM CTAs, Dataset + visible FAQPage JSON-LD and the asking-rent label.
Files: scripts/build_rent_drops.py, rent-drops/ (calc.mjs, style.css, fonts, 51 generated pages from the 2026-11-26 snapshot), .github/workflows/rent-drops.yml (rebuilds pages after each weekly fetch), tests/test_build_rent_drops.py, tests/rent_drops_calc.test.mjs, e2e/flows-rent-drops.spec.ts, e2e/crawl.spec.ts (qa_kit copy), e2e/routes.json, docs/rent-drops/
Deploy: GitHub Pages on merge; pages are noindex until step 3 sets RENT_DROPS_INDEX=1 after the pSEO audit
Blocker: none (step 1 merged in #57; builder accepts its already_net sample column)
Next: step 3: pseo.py audit and cannibal check, then index and sitemap
