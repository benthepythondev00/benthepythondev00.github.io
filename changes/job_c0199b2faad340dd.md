---
date: 2026-10-28
job: job_c0199b2faad340dd
repo: benthepythondev00.github.io
kind: build
---
New fixed-price service page for custom Apify actor builds ($150 / $300 / $600, 1 to 3 days, $50 off when a generic version may go on our Store page), with an in-browser coverage check against data/actors.json that names the closest existing actor and prefills a coded email (WEB-ACTOR-STARTER/STANDARD/PRODUCTION/QUOTE).

| Competitor | Price | Users / rating | Complaint | Ours |
|---|---|---|---|---|
| [Apify Professional Services](https://apify.com/professional-services) | from $1,000/month | 91,000 platform customers | Apify-maintained crawler broke after an update: "We are running this actor for production workloads. Please go back to 0.3.35 until you fix the issue" ([issue](https://apify.com/apify/website-content-crawler/issues/the-actor-stopped-wo-fxxMLpkwrcBbZOj8c)) | one-time from $150; Production tier adds a 30-day empty-row/empty-field monitor |
| [ScrapeHero](https://www.scrapehero.com/pricing/) | $550 minimum per site | Trustpilot 3.2 (2 reviews) | "laughing my **** off at $40 to download this miserable dataset about 29 Warehouses." ([Trustpilot](https://www.trustpilot.com/review/scrapehero.com)) | 1/4 of their minimum, sample before payment |
| [Grepsr](https://www.grepsr.com/pricing/) | from $100 one-time | no Trustpilot reviews | none found | buyer owns the actor and can rerun it |

Files: custom-apify-actor.html, custom-apify-actor.mjs, tests/custom_apify_actor.test.mjs, e2e/flows.spec.ts, e2e/routes.json, index.html, custom.html, sitemap.xml
Deploy: GitHub Pages on merge to main (https://benthepythondev00.github.io/custom-apify-actor.html)
Blocker: waits for Ben's approval (new product with prices)
Next: after merge, search the inbox for WEB-ACTOR-* codes on 2026-11-27; kill if 0 inquiries.
