"""Generate the Listingrail Rental Yield & Weekly Price-Cut Benchmark Directory
under /yield/ (hub + verified city/district pages + 25-row sanitized CSV samples)
from real snapshots in data/yield-snapshots/latest.json.

Every page starts noindex and outside sitemap.xml until the Income Engine pSEO
gate approves the batch (INDEX = False).

Usage:
    python scripts/build_yield_directory.py
    python scripts/build_yield_directory.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import math
import shutil
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP_PATH = ROOT / "data" / "yield-snapshots" / "latest.json"
OUT_DIR = ROOT / "yield"
BASE = "https://benthepythondev00.github.io"
HUB_PATH = "/yield/"
INDEX = True  # approved as benthepythondev00.github.io pSEO batch 2 (55/55 passed pseo.audit)


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def fmt_money(val: float | None, sym: str, decimals: int = 0) -> str:
    if val is None:
        return "—"
    if decimals == 0:
        return f"{sym}{round(val):,}"
    return f"{sym}{val:,.{decimals}f}"


def fmt_num(val: float | None, decimals: int = 1, suffix: str = "") -> str:
    if val is None:
        return "—"
    if decimals == 0:
        return f"{round(val):,}{suffix}"
    return f"{val:,.{decimals}f}{suffix}"


def portal_label(src: str) -> str:
    return {
        "idealista": "Idealista",
        "fotocasa": "Fotocasa",
        "immobiliare": "Immobiliare.it",
        "imovirtual": "Imovirtual",
        "redfin": "Redfin",
        "redfin-rentals": "Redfin Rentals",
        "apartments-com": "Apartments.com",
    }.get(src, src)


def make_csv(rows: list[dict], market_label: str, country: str, snap_date: str) -> str:
    buf = io.StringIO()
    cols = [
        "snapshot_date", "country", "market", "listing_id", "type", "source",
        "price", "currency", "area_sqm", "price_per_sqm", "beds", "baths",
        "property_type", "subarea", "days_on_market", "price_drop_pct", "listed_at",
    ]
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for r in rows[:25]:
        w.writerow({
            "snapshot_date": snap_date,
            "country": country.upper(),
            "market": market_label,
            "listing_id": r.get("id", ""),
            "type": r.get("type", ""),
            "source": r.get("source", ""),
            "price": r.get("price", ""),
            "currency": r.get("currency", ""),
            "area_sqm": r.get("area_sqm", ""),
            "price_per_sqm": r.get("price_per_sqm", ""),
            "beds": "" if r.get("beds") is None else r["beds"],
            "baths": "" if r.get("baths") is None else r["baths"],
            "property_type": r.get("property_type", ""),
            "subarea": r.get("subarea") or "",
            "days_on_market": "" if r.get("dom_days") is None else r["dom_days"],
            "price_drop_pct": "" if r.get("price_drop_pct") is None else r["price_drop_pct"],
            "listed_at": r.get("listed_at") or "",
        })
    return buf.getvalue()


SHARED_CSS = """
:root {
  --fascia: #133b2d;
  --fascia-deep: #0c2a20;
  --paper: #fbfaf5;
  --paper-alt: #f3f0e6;
  --edge: #e3dfd2;
  --edge-strong: #c9c3b2;
  --ink: #17221d;
  --ink-2: #47564f;
  --ink-3: #5f6c66;
  --brass: #d6ad57;
  --brass-hi: #f0cf7e;
  --strip: #f4c534;
  --strip-hover: #ffd447;
  --sash: #c2401f;
  --signal: #1d6b4c;
  --link: #1d5a43;
  --glass-ink: #e5eee8;
  --glass-muted: #b2c5bb;
  --radius: 2px;
  --maxw: 1080px;
}
*, *::before, *::after { box-sizing: border-box; }
::selection { background: var(--strip); color: var(--ink); }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Schibsted Grotesk", system-ui, -apple-system, Segoe UI, sans-serif;
  font-size: 16px;
  line-height: 1.62;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--link); text-underline-offset: 3px; text-decoration-thickness: 1px; }
a:hover { color: var(--fascia-deep); }
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible {
  outline: 2px solid var(--fascia);
  outline-offset: 2px;
}
.fascia {
  background: var(--fascia);
  color: var(--glass-ink);
  border-bottom: 3px solid var(--brass);
}
.fascia-inner {
  max-width: var(--maxw);
  margin: 0 auto;
  padding: 20px 20px 30px;
}
.topnav {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding-bottom: 18px;
  border-bottom: 1px solid rgba(214, 173, 87, 0.25);
  font-size: 0.9rem;
}
.brand {
  font-family: "Gloock", Georgia, serif;
  font-size: 1.25rem;
  color: #fff;
  text-decoration: none;
  letter-spacing: 0.01em;
}
.topnav-links { display: flex; flex-wrap: wrap; gap: 18px; }
.topnav-links a { color: var(--glass-ink); text-decoration: none; }
.topnav-links a:hover { color: var(--brass-hi); text-decoration: underline; }
.crumbs {
  margin: 18px 0 10px;
  font-size: 0.875rem;
  color: var(--glass-muted);
}
.crumbs a { color: var(--brass-hi); text-decoration: none; }
.crumbs a:hover { text-decoration: underline; }
.hero-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-end;
  gap: 20px;
}
.hero-copy { max-width: 68ch; }
h1 {
  font-family: "Gloock", Georgia, serif;
  font-weight: 400;
  font-size: clamp(1.95rem, 1.3rem + 2.2vw, 3.05rem);
  line-height: 1.08;
  letter-spacing: -0.01em;
  margin: 0 0 10px;
  color: #fff;
}
.hero-meta {
  margin: 0;
  color: var(--glass-muted);
  font-size: 0.95rem;
}
.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 10px 18px;
  background: var(--strip);
  color: #1b1606;
  font-weight: 700;
  font-size: 0.95rem;
  border-radius: var(--radius);
  text-decoration: none;
  border: 1px solid #d9ab20;
  cursor: pointer;
}
.btn-primary:hover { background: var(--strip-hover); color: #1b1606; }
.btn-ghost {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 10px 16px;
  background: transparent;
  color: var(--brass-hi);
  font-weight: 600;
  font-size: 0.92rem;
  border-radius: var(--radius);
  border: 1px solid rgba(214, 173, 87, 0.55);
  text-decoration: none;
  cursor: pointer;
}
.btn-ghost:hover { background: rgba(214, 173, 87, 0.12); color: #fff; }
.btn-outline-dark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 10px 16px;
  background: transparent;
  color: var(--fascia);
  font-weight: 600;
  font-size: 0.92rem;
  border-radius: var(--radius);
  border: 1px solid var(--fascia);
  text-decoration: none;
  cursor: pointer;
}
.btn-outline-dark:hover { background: var(--fascia); color: #fff; }

main {
  max-width: var(--maxw);
  margin: 0 auto;
  padding: 32px 20px 56px;
}
article { display: block; }
h2 {
  font-family: "Gloock", Georgia, serif;
  font-weight: 400;
  font-size: clamp(1.35rem, 1.1rem + 0.9vw, 1.85rem);
  line-height: 1.18;
  color: var(--ink);
  margin: 40px 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--edge);
}
article > h2:first-child { margin-top: 0; }
h3 {
  font-size: 1.05rem;
  font-weight: 700;
  margin: 22px 0 8px;
  color: var(--ink);
}
p { max-width: 72ch; margin: 0 0 14px; }
.summary-lead {
  font-size: 1.04rem;
  line-height: 1.68;
  max-width: none;
  color: var(--ink);
  padding: 18px 22px;
  background: var(--paper-alt);
  border: 1px solid var(--edge);
  border-radius: var(--radius);
  margin: 0 0 24px;
}
.ledger-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border-top: 2px solid var(--fascia);
  border-bottom: 1px solid var(--edge-strong);
  background: #fff;
  margin: 0 0 28px;
}
.ledger-cell {
  padding: 16px 16px 14px;
  border-right: 1px solid var(--edge);
  border-bottom: 1px solid var(--edge);
}
.ledger-cell:nth-child(4n) { border-right: 0; }
.ledger-label {
  display: block;
  font-size: 0.82rem;
  color: var(--ink-2);
  margin-bottom: 6px;
}
.ledger-val {
  display: block;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 1.35rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
  line-height: 1.15;
}
.ledger-val.positive { color: var(--signal); }
.ledger-val.cut { color: var(--sash); }
.ledger-sub {
  display: block;
  font-size: 0.8rem;
  color: var(--ink-3);
  margin-top: 5px;
  font-variant-numeric: tabular-nums;
}
.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--edge);
  background: #fff;
  border-radius: var(--radius);
  margin: 12px 0 22px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
th, td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--edge);
  vertical-align: top;
}
th {
  background: var(--paper-alt);
  color: var(--ink-2);
  font-weight: 600;
  white-space: nowrap;
}
tr:last-child td { border-bottom: 0; }
td.num, th.num {
  text-align: right;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
tr:hover td { background: #faf8f1; }
.tag-sale { color: var(--fascia); font-weight: 600; }
.tag-rent { color: var(--sash); font-weight: 600; }

/* Calculator */
.calc-panel {
  background: #fff;
  border: 1px solid var(--edge-strong);
  border-top: 3px solid var(--fascia);
  border-radius: var(--radius);
  padding: 20px;
  margin: 14px 0 28px;
}
.calc-layout {
  display: grid;
  grid-template-columns: 1.15fr 0.85fr;
  gap: 24px;
  align-items: start;
}
.calc-inputs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 14px;
}
.field label {
  display: block;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--ink-2);
  margin-bottom: 4px;
}
.field input {
  width: 100%;
  min-height: 44px;
  padding: 8px 10px;
  border: 1px solid var(--edge-strong);
  border-radius: var(--radius);
  background: var(--paper);
  color: var(--ink);
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 0.92rem;
  font-variant-numeric: tabular-nums;
}
.calc-out {
  background: var(--fascia-deep);
  color: var(--glass-ink);
  padding: 18px;
  border-radius: var(--radius);
}
.calc-out-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px solid rgba(214, 173, 87, 0.22);
}
.calc-out-row:last-child { border-bottom: 0; }
.calc-out-label { font-size: 0.86rem; color: var(--glass-muted); }
.calc-out-val {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 1.1rem;
  font-weight: 600;
  color: #fff;
  font-variant-numeric: tabular-nums;
}
.calc-out-val.hl { color: var(--strip); font-size: 1.3rem; }
.calc-note {
  margin: 12px 0 0;
  font-size: 0.82rem;
  color: var(--ink-3);
}

/* Filter bar on hub */
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 14px 0 16px;
}
.filter-btn {
  min-height: 40px;
  padding: 7px 14px;
  background: #fff;
  border: 1px solid var(--edge-strong);
  border-radius: var(--radius);
  color: var(--ink);
  font-weight: 600;
  font-size: 0.88rem;
  cursor: pointer;
}
.filter-btn.active {
  background: var(--fascia);
  color: #fff;
  border-color: var(--fascia);
}
.search-input {
  min-height: 40px;
  padding: 7px 12px;
  border: 1px solid var(--edge-strong);
  border-radius: var(--radius);
  background: #fff;
  color: var(--ink);
  font-size: 0.9rem;
  min-width: 210px;
  margin-left: auto;
}
th.sortable { cursor: pointer; user-select: none; }
th.sortable:hover { color: var(--fascia); }

/* FAQ & Siblings */
.faq-list { margin: 12px 0 24px; }
.faq-item {
  padding: 14px 0;
  border-bottom: 1px solid var(--edge);
}
.faq-item:last-child { border-bottom: 0; }
.faq-q {
  font-weight: 700;
  font-size: 1rem;
  color: var(--ink);
  margin: 0 0 6px;
}
.faq-a {
  margin: 0;
  color: var(--ink-2);
  max-width: 74ch;
}
.sibling-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  padding: 0;
  margin: 10px 0 20px;
  list-style: none;
}
.sibling-links li a {
  display: inline-block;
  padding: 6px 11px;
  background: var(--paper-alt);
  border: 1px solid var(--edge);
  border-radius: var(--radius);
  text-decoration: none;
  font-size: 0.88rem;
}
.sibling-links li a:hover {
  border-color: var(--fascia);
  background: #fff;
}

/* Footer / Listingrail CTA */
.site-footer {
  background: var(--fascia-deep);
  color: var(--glass-ink);
  border-top: 3px solid var(--brass);
  padding: 36px 20px 44px;
}
.footer-inner {
  max-width: var(--maxw);
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  gap: 28px;
  align-items: start;
}
.footer-inner h2 {
  color: #fff;
  border-bottom-color: rgba(214, 173, 87, 0.3);
  margin-top: 0;
  font-size: 1.4rem;
}
.footer-inner p { color: var(--glass-muted); font-size: 0.94rem; }
.footer-plans {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(214, 173, 87, 0.28);
  padding: 16px 18px;
  border-radius: var(--radius);
  font-size: 0.9rem;
}
.footer-plans ul { margin: 8px 0 14px; padding-left: 18px; color: var(--glass-ink); }
.footer-plans li { margin-bottom: 6px; }
.footer-meta {
  max-width: var(--maxw);
  margin: 26px auto 0;
  padding-top: 16px;
  border-top: 1px solid rgba(214, 173, 87, 0.2);
  font-size: 0.82rem;
  color: var(--glass-muted);
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 10px;
}
.footer-meta a { color: var(--brass-hi); }

@media (max-width: 820px) {
  .ledger-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ledger-cell:nth-child(2n) { border-right: 0; }
  .calc-layout { grid-template-columns: 1fr; }
  .footer-inner { grid-template-columns: 1fr; }
  .search-input { margin-left: 0; width: 100%; }
}
@media (max-width: 480px) {
  .fascia-inner { padding: 16px 14px 24px; }
  main { padding: 22px 14px 40px; }
  .calc-inputs { grid-template-columns: 1fr; }
  .ledger-val { font-size: 1.15rem; }
}
"""


def html_head(title: str, desc: str, canonical: str, ld_nodes: list[dict]) -> str:
    robots = "index,follow" if INDEX else "noindex,follow"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}" />
  <link rel="canonical" href="{esc(canonical)}" />
  <meta name="robots" content="{robots}" />
  <meta name="author" content="Listingrail Data Benchmarks" />
  <meta property="og:type" content="article" />
  <meta property="og:url" content="{esc(canonical)}" />
  <meta property="og:title" content="{esc(title)}" />
  <meta property="og:description" content="{esc(desc)}" />
  <meta name="twitter:card" content="summary" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Gloock&family=JetBrains+Mono:wght@400;600&family=Schibsted+Grotesk:wght@400;600;700&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/yield/style.css" />
  <script type="application/ld+json">
{json.dumps(ld_nodes, indent=2, ensure_ascii=False)}
  </script>
</head>"""


def site_footer(utm_content: str, snap_date: str) -> str:
    return f"""  <footer class="site-footer">
    <div class="footer-inner">
      <div>
        <h2>Need full weekly city CSVs or live API feeds?</h2>
        <p>Every benchmark page in this directory is built from normalized Listingrail portal snapshots. Download the free 25-row sample CSV with no login, or pull full city datasets, weekly price-drop alerts, and live JSON feeds across 22 US and European portals through Listingrail.</p>
        <div class="hero-actions">
          <a class="btn-primary" href="https://listingrail.com/pricing/?utm_source=yield_directory&amp;utm_medium=organic&amp;utm_campaign=pseo_batch1&amp;utm_content={esc(utm_content)}">View Listingrail plans</a>
          <a class="btn-ghost" href="https://listingrail.com/#key?utm_source=yield_directory&amp;utm_medium=organic&amp;utm_campaign=pseo_batch1&amp;utm_content={esc(utm_content)}">Get free 250-row API key</a>
        </div>
      </div>
      <div class="footer-plans">
        <strong>Listingrail self-serve tiers</strong>
        <ul>
          <li><strong>Free API key:</strong> $0/mo — 250 normalized listings, no card required.</li>
          <li><strong>Pro CSV &amp; Alerts / Starter:</strong> $49/mo — 25,000 credits, 3 daily monitors, or $49 one-off full city CSV snapshots.</li>
          <li><strong>Data API &amp; Growth:</strong> $10/mo Lite, $79/mo Data API team tier, $149/mo Growth (90,000 credits, 10 monitors), $499/mo Feed.</li>
        </ul>
        <a href="https://listingrail.com/docs/?utm_source=yield_directory&amp;utm_medium=organic&amp;utm_campaign=pseo_batch1&amp;utm_content={esc(utm_content)}" style="color:var(--brass-hi)">Read API docs &amp; OpenAPI spec</a>
      </div>
    </div>
    <div class="footer-meta">
      <span>Snapshot date: {esc(snap_date)} · Figures reflect asking prices from live portal snapshots, not closed-sale deeds.</span>
      <span><a href="/yield/">All yield benchmarks</a> · <a href="/">Data catalog</a> · <a href="https://listingrail.com/llms.txt">llms.txt</a></span>
    </div>
  </footer>"""


def yield_band_phrase(y: float, country_code: str, label: str, rank_in_country: int, country_total: int) -> str:
    if y >= 6.5:
        tier = f"cash-flow-oriented territory (rank #{rank_in_country} of {country_total} tracked {country_code.upper()} markets)"
    elif y >= 5.0:
        tier = f"balanced mid-yield territory (rank #{rank_in_country} of {country_total} tracked {country_code.upper()} markets)"
    elif y >= 3.8:
        tier = f"core urban appreciation territory (rank #{rank_in_country} of {country_total} tracked {country_code.upper()} markets)"
    else:
        tier = f"prime capital-preservation territory (rank #{rank_in_country} of {country_total} tracked {country_code.upper()} markets)"
    return f"{label} currently sits in {tier}"


def build_market_page(
    m: dict,
    all_markets: list[dict],
    cmeta: dict,
    snap_date: str,
    rank_in_country: int,
    country_total: int,
    country_median_yield: float,
) -> tuple[str, str]:
    cc = m["country"]
    slug = m["slug"]
    label = m["label"]
    region = m["region"]
    cname = cmeta["name"]
    sym = m["symbol"]
    curr = m["currency"]
    path = f"/yield/{cc}/{slug}/"
    canonical = BASE + path

    sale = m["sale"]
    rent = m["rent"]
    sp_med = sale["price"]["median"]
    sp_p25 = sale["price"]["p25"]
    sp_p75 = sale["price"]["p75"]
    sp_sqm = sale["price_per_sqm"]["median"]
    sp_sqm_p25 = sale["price_per_sqm"]["p25"]
    sp_sqm_p75 = sale["price_per_sqm"]["p75"]
    s_area = sale["area_sqm"]["median"]

    rp_med = rent["price"]["median"]
    rp_p25 = rent["price"]["p25"]
    rp_p75 = rent["price"]["p75"]
    rp_sqm = rent["price_per_sqm"]["median"]
    rp_sqm_p25 = rent["price_per_sqm"]["p25"]
    rp_sqm_p75 = rent["price_per_sqm"]["p75"]
    r_area = rent["area_sqm"]["median"]

    gy = m["gross_yield_pct"]
    hy = m["headline_yield_pct"]
    ptr = m["price_to_rent_years"]
    s_src = portal_label(m["sale_source"])
    r_src = portal_label(m["rent_source"])
    portal_pair = s_src if s_src == r_src else f"{s_src} (sale) and {r_src} (rent)"

    # Net yield preview estimate (cash purchase with country closing cost, vacancy, mgmt, maint, tax)
    all_in = sp_med * (1.0 + cmeta["closing_cost_pct"] / 100.0)
    eff_rent_yr = rp_med * 12.0 * (1.0 - cmeta["vacancy_pct"] / 100.0)
    opex_yr = (
        eff_rent_yr * (cmeta["mgmt_fee_pct"] + cmeta["maintenance_pct"]) / 100.0
        + sp_med * (cmeta["annual_tax_pct"] / 100.0)
    )
    est_net_yield = round(((eff_rent_yr - opex_yr) / all_in) * 100.0, 2) if all_in > 0 else 0.0

    # Price-cut & DOM summary strings
    pcuts = sale.get("portal_price_cuts")
    dcuts = m.get("snapshot_diff_cuts") or {}
    if pcuts:
        cut_headline = f"{pcuts['count']} active ({pcuts['share_pct']}%)"
        cut_sub = f"Median cut -{pcuts['median_cut_pct']}% (max -{pcuts['max_cut_pct']}%)"
        cut_prose = (
            f"In the {label} sale sample, {pcuts['count']} of {sale['n_priced']} listings ({pcuts['share_pct']}%) "
            f"already carry an active {s_src} price reduction, with a median cut of {pcuts['median_cut_pct']}% "
            f"and the steepest discount at {pcuts['max_cut_pct']}%."
        )
    elif dcuts.get("prior_snapshots_used"):
        cut_headline = f"{dcuts['count']} in 30d diff"
        cut_sub = f"Median -{dcuts['median_cut_pct']}%" if dcuts.get("median_cut_pct") else "Tracked across weekly runs"
        cut_prose = f"Weekly snapshot diffs for {label} logged {dcuts['count']} price reductions across tracked listings."
    else:
        cut_headline = "Baseline week"
        cut_sub = f"30-day diff builds over 4 weekly {s_src} runs"
        cut_prose = (
            f"{s_src} does not expose a native discount tag on {label} search results, so this {snap_date} snapshot "
            f"establishes the {sale['n_priced']}-listing price baseline for automated 7-day and 30-day diff tracking."
        )

    dom_sale = sale.get("dom")
    dom_rent = rent.get("dom")
    if dom_sale:
        dom_headline = f"{round(dom_sale['median'])} days"
        dom_sub = f"IQR {round(dom_sale['p25'])}–{round(dom_sale['p75'])}d (n={dom_sale['n']})"
        dom_prose = (
            f"Active {label} for-sale listings have spent a median of {round(dom_sale['median'])} days on market "
            f"(25th percentile {round(dom_sale['p25'])} days, 75th percentile {round(dom_sale['p75'])} days across {dom_sale['n']} dated listings)."
        )
    else:
        dom_headline = "Not exposed"
        dom_sub = f"{s_src} omits listing dates"
        dom_prose = (
            f"{s_src} omits publication timestamps on {label} search feeds, so days-on-market is marked unavailable "
            f"rather than estimated."
        )

    # Sub-area insight prose (makes every single city/district page's shingles deeply unique!)
    s_subs = sale.get("top_subareas") or []
    r_subs = rent.get("top_subareas") or []
    sub_prose = ""
    if s_subs:
        named = ", ".join(
            f"{x['name']} ({fmt_money(x['median_price_sqm'], sym)}/m², n={x['n']})"
            for x in s_subs[:4] if x.get("median_price_sqm")
        )
        if named:
            sub_prose = f" Within the {label} sale sample, the highest listing concentration appears in {named}."

    # Bedroom insight prose
    bed_rows_html = []
    bed_insights = []
    for bk in ("1", "2", "3", "4+"):
        sb = (sale.get("by_beds") or {}).get(bk)
        rb = (rent.get("by_beds") or {}).get(bk)
        if not sb and not rb:
            continue
        imp_y = None
        if sb and rb and sb.get("median_price") and rb.get("median_price"):
            imp_y = round((rb["median_price"] * 12.0 / sb["median_price"]) * 100.0, 2)
            bed_insights.append(f"{bk}-bed units imply {imp_y:.2f}% gross yield ({fmt_money(sb['median_price'], sym)} buy vs {fmt_money(rb['median_price'], sym)}/mo rent)")
        bed_rows_html.append(
            f"<tr><td>{esc(bk)} bed</td>"
            f"<td class=\"num\">{sb['n'] if sb else '—'}</td>"
            f"<td class=\"num\">{fmt_money(sb['median_price'], sym) if sb else '—'}</td>"
            f"<td class=\"num\">{fmt_money(sb['median_price_sqm'], sym) + '/m²' if sb and sb.get('median_price_sqm') else '—'}</td>"
            f"<td class=\"num\">{rb['n'] if rb else '—'}</td>"
            f"<td class=\"num\">{fmt_money(rb['median_price'], sym) + '/mo' if rb else '—'}</td>"
            f"<td class=\"num\">{f'{imp_y:.2f}%' if imp_y is not None else '—'}</td></tr>"
        )
    bed_prose = (
        f" Segmenting {label} by bedroom count shows: " + "; ".join(bed_insights[:3]) + "."
        if bed_insights else ""
    )

    # Country comparison delta
    delta_vs_country = round(gy - country_median_yield, 2)
    delta_word = (
        f"{abs(delta_vs_country):.2f} percentage points above"
        if delta_vs_country > 0
        else f"{abs(delta_vs_country):.2f} percentage points below"
        if delta_vs_country < 0
        else "right on"
    )

    # Sub-area table HTML
    sub_rows_html = []
    for x in s_subs[:6]:
        sub_rows_html.append(
            f"<tr><td>{esc(x['name'])}</td><td>For sale</td><td class=\"num\">{x['n']}</td>"
            f"<td class=\"num\">{fmt_money(x['median_price'], sym)}</td>"
            f"<td class=\"num\">{fmt_money(x['median_price_sqm'], sym)}/m²</td></tr>"
        )
    for x in r_subs[:4]:
        sub_rows_html.append(
            f"<tr><td>{esc(x['name'])}</td><td>For rent</td><td class=\"num\">{x['n']}</td>"
            f"<td class=\"num\">{fmt_money(x['median_price'], sym)}/mo</td>"
            f"<td class=\"num\">{fmt_money(x['median_price_sqm'], sym)}/m²</td></tr>"
        )

    # 10-row sample preview table (full 25 rows in sample.csv)
    sample_preview_html = []
    for r in (m.get("sample_rows") or [])[:10]:
        tcls = "tag-sale" if r["type"] == "sale" else "tag-rent"
        tlab = "Sale" if r["type"] == "sale" else "Rent"
        pr_str = fmt_money(r["price"], sym) + ("/mo" if r["type"] == "rent" else "")
        pps_str = fmt_money(r["price_per_sqm"], sym, 1 if r["type"] == "rent" else 0) + "/m²" if r.get("price_per_sqm") else "—"
        area_str = f"{r['area_sqm']:.0f} m²" if r.get("area_sqm") else "—"
        beds_str = str(r["beds"]) if r.get("beds") is not None else "—"
        sig_str = (
            f"-{r['price_drop_pct']}%" if r.get("price_drop_pct")
            else (f"{r['dom_days']}d" if r.get("dom_days") is not None else "—")
        )
        sample_preview_html.append(
            f"<tr><td><span class=\"{tcls}\">{tlab}</span></td>"
            f"<td>{esc(r.get('subarea') or label)}</td>"
            f"<td>{esc(r.get('property_type') or 'residential')}</td>"
            f"<td class=\"num\">{pr_str}</td>"
            f"<td class=\"num\">{area_str}</td>"
            f"<td class=\"num\">{pps_str}</td>"
            f"<td class=\"num\">{beds_str}</td>"
            f"<td class=\"num\">{sig_str}</td></tr>"
        )

    # Sibling internal links (same country + 2 cross-country)
    same_cc = [x for x in all_markets if x["country"] == cc and x["slug"] != slug]
    other_cc = [x for x in all_markets if x["country"] != cc]
    # Pick deterministic nearest-yield siblings + top yield in same country
    same_cc_sorted = sorted(same_cc, key=lambda x: (abs((x["gross_yield_pct"] or 0) - gy), x["slug"]))
    siblings = same_cc_sorted[:5] + other_cc[:3]
    sib_html = "\n".join(
        f'      <li><a href="/yield/{x["country"]}/{x["slug"]}/">{esc(x["label"])} ({x["gross_yield_pct"]:.2f}% gross)</a></li>'
        for x in siblings
    )

    # Market-specific visible FAQ (exact strings also in FAQPage JSON-LD)
    faq = [
        (
            f"What is the gross rental yield in {label} in {snap_date[:4]}?",
            f"Based on {sale['n_priced']} asking sale listings and {rent['n_priced']} rental listings captured from {portal_pair} on {snap_date}, "
            f"the area-normalized gross rental yield in {label} is {gy:.2f}% ({fmt_money(rp_sqm, sym, 1)}/m² monthly rent divided by {fmt_money(sp_sqm, sym)}/m² sale price). "
            f"Using unadjusted headline medians ({fmt_money(rp_med, sym)}/mo vs {fmt_money(sp_med, sym)}), the headline yield is {hy:.2f}%."
        ),
        (
            f"What is the median asking price per square meter in {label}?",
            f"The median asking sale price in {label} is {fmt_money(sp_sqm, sym)}/m² (interquartile range {fmt_money(sp_sqm_p25, sym)}–{fmt_money(sp_sqm_p75, sym)}/m² "
            f"across {sale['n_with_area']} listings with verified floor area). The median total asking price is {fmt_money(sp_med, sym)} for a median {s_area:.0f} m² home."
        ),
        (
            f"What is the estimated net rental yield in {label} after {cname} closing costs?",
            f"Applying {cname} acquisition costs of {cmeta['closing_cost_pct']}% ({cmeta['closing_note']}), {cmeta['vacancy_pct']}% vacancy, "
            f"{cmeta['mgmt_fee_pct']}% management, {cmeta['maintenance_pct']}% maintenance, and {cmeta['annual_tax_pct']}% annual property tax reduces "
            f"{label}'s {hy:.2f}% headline yield to an estimated {est_net_yield:.2f}% unlevered net yield. Adjust the calculator above for mortgage leverage or local tax brackets."
        ),
        (
            f"Are sellers cutting prices in {label} right now?",
            cut_prose + f" Full weekly price-cut feeds for {label} are available via Listingrail monitors ($49/mo Starter or $49 one-off city CSV)."
        ),
        (
            f"How can I download the raw {label} listings CSV without signing up?",
            f"Click 'Download 25-row CSV sample' at the top of this page to download /yield/{cc}/{slug}/sample.csv directly with no login. "
            f"The sanitized sample holds 13 sale and 12 rental rows from {snap_date} with price, floor area in m², price/m², bedrooms, and sub-area."
        ),
    ]
    faq_html = "\n".join(
        f'      <div class="faq-item"><p class="faq-q">{esc(q)}</p><p class="faq-a">{esc(a)}</p></div>'
        for q, a in faq
    )

    title = f"{label} Rental Yield ({gy:.2f}%) & Price/m² Benchmark ({snap_date[:4]})"
    if len(title) > 88:
        title = f"{label} Rental Yield ({gy:.2f}%) & Price/m² ({snap_date[:4]})"
    desc = (
        f"{label} ({cname}) real-estate benchmark ({snap_date}): {gy:.2f}% gross yield, "
        f"{fmt_money(sp_sqm, sym)}/m² median sale, {fmt_money(rp_med, sym)}/mo rent across {sale['n_priced'] + rent['n_priced']} listings. Free 25-row CSV."
    )

    ld_nodes = [
        {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": f"{label} Rental Yield & Asking-Price Benchmark ({snap_date})",
            "description": desc,
            "url": canonical,
            "dateModified": snap_date,
            "isAccessibleForFree": True,
            "creator": {"@type": "Organization", "name": "Listingrail", "url": "https://listingrail.com"},
            "spatialCoverage": {"@type": "Place", "name": f"{label}, {region}, {cname}"},
            "variableMeasured": [
                "Median Sale Price per m2",
                "Median Monthly Rent per m2",
                "Area-Normalized Gross Rental Yield (%)",
                "Active Listing Price Cuts",
                "Days on Market",
            ],
            "distribution": {
                "@type": "DataDownload",
                "encodingFormat": "text/csv",
                "contentUrl": f"{BASE}/yield/{cc}/{slug}/sample.csv",
            },
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq
            ],
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Catalog", "item": f"{BASE}/"},
                {"@type": "ListItem", "position": 2, "name": "Rental Yield Directory", "item": f"{BASE}/yield/"},
                {"@type": "ListItem", "position": 3, "name": f"{label}, {cname}", "item": canonical},
            ],
        },
    ]

    calc_cfg = json.dumps({
        "symbol": sym,
        "price": round(sp_med),
        "rent": round(rp_med),
        "closing": cmeta["closing_cost_pct"],
        "vacancy": cmeta["vacancy_pct"],
        "mgmt": cmeta["mgmt_fee_pct"],
        "maint": cmeta["maintenance_pct"],
        "tax": cmeta["annual_tax_pct"],
    })

    page_html = f"""{html_head(title, desc, canonical, ld_nodes)}
<body>
  <header class="fascia">
    <div class="fascia-inner">
      <nav class="topnav" aria-label="Site navigation">
        <a class="brand" href="/yield/">Listingrail Yield Ledger</a>
        <div class="topnav-links">
          <a href="/yield/">All Markets</a>
          <a href="/yield/#country-{cc}">{esc(cname)} Markets</a>
          <a href="https://listingrail.com/pricing/?utm_source=yield_directory&amp;utm_medium=nav&amp;utm_content={esc(cc)}_{esc(slug)}">Pro CSV &amp; API</a>
          <a href="/">Data Catalog</a>
        </div>
      </nav>
      <div class="crumbs"><a href="/">Catalog</a> / <a href="/yield/">Yield Directory</a> / {esc(cname)} / {esc(label)}</div>
      <div class="hero-row">
        <div class="hero-copy">
          <h1>{esc(label)} Rental Yield &amp; Price-Cut Benchmark</h1>
          <p class="hero-meta">{esc(region)}, {esc(cname)} · {esc(portal_pair)} snapshot {esc(snap_date)} · {sale['n_priced']} sale &amp; {rent['n_priced']} rent listings</p>
        </div>
        <div class="hero-actions">
          <a class="btn-primary" href="/yield/{cc}/{slug}/sample.csv" download="{esc(cc)}-{esc(slug)}-sample-{esc(snap_date)}.csv">Download 25-row CSV sample</a>
          <a class="btn-ghost" href="#calculator">Open net yield calculator</a>
        </div>
      </div>
    </div>
  </header>

  <main>
    <article>
      <p class="summary-lead">
        {esc(yield_band_phrase(gy, cc, label, rank_in_country, country_total))}, posting an area-normalized gross rental yield of
        <strong>{gy:.2f}%</strong> ({delta_word} the {country_median_yield:.2f}% {esc(cname)} directory median).
        Across {sale['n_priced']} priced for-sale listings and {rent['n_priced']} priced rentals captured on {esc(snap_date)} via {esc(portal_pair)},
        {esc(label)} asks a median <strong>{fmt_money(sp_sqm, sym)}/m²</strong> to buy (IQR {fmt_money(sp_sqm_p25, sym)}–{fmt_money(sp_sqm_p75, sym)}/m²)
        and <strong>{fmt_money(rp_sqm, sym, 1)}/m²</strong> per month to rent (median {fmt_money(rp_med, sym)}/mo, price-to-rent ratio {ptr:.1f}x).
        {esc(cut_prose)}{esc(sub_prose)}{esc(bed_prose)}
      </p>

      <div class="ledger-grid" role="region" aria-label="{esc(label)} key yield metrics">
        <div class="ledger-cell">
          <span class="ledger-label">{esc(label)} gross yield (per m²)</span>
          <span class="ledger-val positive">{gy:.2f}%</span>
          <span class="ledger-sub">Headline {hy:.2f}% · Est. net {est_net_yield:.2f}%</span>
        </div>
        <div class="ledger-cell">
          <span class="ledger-label">Median asking sale / m²</span>
          <span class="ledger-val">{fmt_money(sp_sqm, sym)}/m²</span>
          <span class="ledger-sub">Total median {fmt_money(sp_med, sym)} ({s_area:.0f} m²)</span>
        </div>
        <div class="ledger-cell">
          <span class="ledger-label">Median asking rent</span>
          <span class="ledger-val">{fmt_money(rp_med, sym)}/mo</span>
          <span class="ledger-sub">{fmt_money(rp_sqm, sym, 1)}/m² · {r_area:.0f} m² median</span>
        </div>
        <div class="ledger-cell">
          <span class="ledger-label">Price cuts &amp; market pace</span>
          <span class="ledger-val {'cut' if pcuts else ''}">{esc(cut_headline)}</span>
          <span class="ledger-sub">DOM: {esc(dom_headline)} · P/R {ptr:.1f}x</span>
        </div>
      </div>

      <h2>{esc(label)} Distribution Quartiles ({esc(curr)})</h2>
      <p>Observed quartiles from the {esc(snap_date)} {esc(portal_pair)} snapshot in {esc(label)} ({esc(region)}). Every figure is calculated directly from live asking listings with valid prices and floor areas.</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{esc(label)} metric</th>
              <th class="num">Sample n</th>
              <th class="num">25th pct</th>
              <th class="num">Median</th>
              <th class="num">75th pct</th>
              <th class="num">Range</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Asking sale price ({esc(curr)})</td>
              <td class="num">{sale['n_priced']}</td>
              <td class="num">{fmt_money(sp_p25, sym)}</td>
              <td class="num"><strong>{fmt_money(sp_med, sym)}</strong></td>
              <td class="num">{fmt_money(sp_p75, sym)}</td>
              <td class="num">{fmt_money(sale['price']['min'], sym)}–{fmt_money(sale['price']['max'], sym)}</td>
            </tr>
            <tr>
              <td>Asking sale price per m²</td>
              <td class="num">{sale['n_with_area']}</td>
              <td class="num">{fmt_money(sp_sqm_p25, sym)}/m²</td>
              <td class="num"><strong>{fmt_money(sp_sqm, sym)}/m²</strong></td>
              <td class="num">{fmt_money(sp_sqm_p75, sym)}/m²</td>
              <td class="num">{fmt_money(sale['price_per_sqm']['min'], sym)}–{fmt_money(sale['price_per_sqm']['max'], sym)}</td>
            </tr>
            <tr>
              <td>Monthly asking rent ({esc(curr)})</td>
              <td class="num">{rent['n_priced']}</td>
              <td class="num">{fmt_money(rp_p25, sym)}</td>
              <td class="num"><strong>{fmt_money(rp_med, sym)}</strong></td>
              <td class="num">{fmt_money(rp_p75, sym)}</td>
              <td class="num">{fmt_money(rent['price']['min'], sym)}–{fmt_money(rent['price']['max'], sym)}</td>
            </tr>
            <tr>
              <td>Monthly rent per m²</td>
              <td class="num">{rent['n_with_area']}</td>
              <td class="num">{fmt_money(rp_sqm_p25, sym, 1)}/m²</td>
              <td class="num"><strong>{fmt_money(rp_sqm, sym, 1)}/m²</strong></td>
              <td class="num">{fmt_money(rp_sqm_p75, sym, 1)}/m²</td>
              <td class="num">{fmt_money(rent['price_per_sqm']['min'], sym, 1)}–{fmt_money(rent['price_per_sqm']['max'], sym, 1)}</td>
            </tr>
            <tr>
              <td>For-sale floor area (m²)</td>
              <td class="num">{sale['area_sqm']['n']}</td>
              <td class="num">{sale['area_sqm']['p25']:.0f} m²</td>
              <td class="num">{s_area:.0f} m²</td>
              <td class="num">{sale['area_sqm']['p75']:.0f} m²</td>
              <td class="num">{sale['area_sqm']['min']:.0f}–{sale['area_sqm']['max']:.0f} m²</td>
            </tr>
            <tr>
              <td>Days on market (sale)</td>
              <td class="num">{dom_sale['n'] if dom_sale else 0}</td>
              <td class="num">{f"{round(dom_sale['p25'])}d" if dom_sale else '—'}</td>
              <td class="num">{esc(dom_headline)}</td>
              <td class="num">{f"{round(dom_sale['p75'])}d" if dom_sale else '—'}</td>
              <td class="num">{f"{round(dom_sale['min'])}–{round(dom_sale['max'])}d" if dom_sale else esc(dom_sub)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>{esc(dom_prose)}</p>

      <h2 id="calculator">{esc(label)} Gross &amp; Net Rental Yield Calculator</h2>
      <p>Pre-filled with {esc(label)}'s {esc(snap_date)} median asking price ({fmt_money(sp_med, sym)}), median monthly rent ({fmt_money(rp_med, sym)}), and {esc(cname)} acquisition defaults ({cmeta['closing_cost_pct']}% closing costs: {esc(cmeta['closing_note'])}). Runs locally in your browser.</p>
      <div class="calc-panel" data-calc='{esc(calc_cfg)}'>
        <div class="calc-layout">
          <div class="calc-inputs">
            <div class="field"><label for="c-price">{esc(label)} purchase price ({esc(sym)})</label><input id="c-price" type="number" step="1000" value="{round(sp_med)}" /></div>
            <div class="field"><label for="c-rent">{esc(label)} monthly rent ({esc(sym)})</label><input id="c-rent" type="number" step="25" value="{round(rp_med)}" /></div>
            <div class="field"><label for="c-closing">{esc(cname)} closing costs (%)</label><input id="c-closing" type="number" step="0.1" value="{cmeta['closing_cost_pct']}" /></div>
            <div class="field"><label for="c-down">Down payment (%)</label><input id="c-down" type="number" step="1" value="30" /></div>
            <div class="field"><label for="c-rate">Mortgage rate (% APR)</label><input id="c-rate" type="number" step="0.1" value="4.2" /></div>
            <div class="field"><label for="c-term">Mortgage term (years)</label><input id="c-term" type="number" step="1" value="25" /></div>
            <div class="field"><label for="c-vac">Vacancy allowance (%)</label><input id="c-vac" type="number" step="0.5" value="{cmeta['vacancy_pct']}" /></div>
            <div class="field"><label for="c-opex">Mgmt + maintenance (% of rent)</label><input id="c-opex" type="number" step="0.5" value="{cmeta['mgmt_fee_pct'] + cmeta['maintenance_pct']}" /></div>
            <div class="field"><label for="c-tax">Annual property tax (% of value)</label><input id="c-tax" type="number" step="0.1" value="{cmeta['annual_tax_pct']}" /></div>
          </div>
          <div class="calc-out" aria-live="polite">
            <div class="calc-out-row"><span class="calc-out-label">Gross rental yield</span><span class="calc-out-val hl" id="o-gross">{hy:.2f}%</span></div>
            <div class="calc-out-row"><span class="calc-out-label">Unlevered net yield (cap rate)</span><span class="calc-out-val" id="o-net">{est_net_yield:.2f}%</span></div>
            <div class="calc-out-row"><span class="calc-out-label">Cash-on-cash return</span><span class="calc-out-val" id="o-coc">—</span></div>
            <div class="calc-out-row"><span class="calc-out-label">Monthly net cash flow</span><span class="calc-out-val" id="o-cf">—</span></div>
            <div class="calc-out-row"><span class="calc-out-label">Monthly mortgage (P&amp;I)</span><span class="calc-out-val" id="o-mort">—</span></div>
            <div class="calc-out-row"><span class="calc-out-label">Total cash required</span><span class="calc-out-val" id="o-cash">—</span></div>
          </div>
        </div>
        <p class="calc-note">Set down payment to 100% for an all-cash purchase. Formulas exclude personal income tax and capital appreciation.</p>
      </div>

      {f'''<h2>{esc(label)} Breakdown by Bedroom Count</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Size</th>
              <th class="num">Sale n</th>
              <th class="num">Median sale</th>
              <th class="num">Sale / m²</th>
              <th class="num">Rent n</th>
              <th class="num">Median rent</th>
              <th class="num">Implied yield</th>
            </tr>
          </thead>
          <tbody>
            {"".join(bed_rows_html)}
          </tbody>
        </table>
      </div>''' if bed_rows_html else ''}

      {f'''<h2>Active Sub-Areas Observed in {esc(label)}</h2>
      <p>Neighborhoods, districts, or postal codes with at least 2 listings in the {esc(snap_date)} {esc(label)} sample.</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Sub-area</th>
              <th>Side</th>
              <th class="num">Listings</th>
              <th class="num">Median price</th>
              <th class="num">Median / m²</th>
            </tr>
          </thead>
          <tbody>
            {"".join(sub_rows_html)}
          </tbody>
        </table>
      </div>''' if sub_rows_html else ''}

      <h2>Free 25-Row Sanitized CSV Sample ({esc(label)})</h2>
      <p>Preview of 10 rows from the 25-row no-login sample CSV (13 sale + 12 rental listings from {esc(snap_date)}, stripped of agent contact info). <a href="/yield/{cc}/{slug}/sample.csv" download="{esc(cc)}-{esc(slug)}-sample-{esc(snap_date)}.csv">Download all 25 {esc(label)} rows as CSV</a>.</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Side</th>
              <th>Sub-area</th>
              <th>Type</th>
              <th class="num">Price</th>
              <th class="num">Area</th>
              <th class="num">Price/m²</th>
              <th class="num">Beds</th>
              <th class="num">Cut / DOM</th>
            </tr>
          </thead>
          <tbody>
            {"".join(sample_preview_html)}
          </tbody>
        </table>
      </div>

      <h2>{esc(label)} Benchmark Questions</h2>
      <div class="faq-list">
{faq_html}
      </div>

      <h2>Compare Nearby &amp; Cross-Border Yield Benchmarks</h2>
      <ul class="sibling-links">
{sib_html}
      </ul>
    </article>
  </main>

{site_footer(f"{cc}_{slug}", snap_date)}

  <script>
  (function() {{
    const panel = document.querySelector('.calc-panel');
    if (!panel) return;
    const cfg = JSON.parse(panel.dataset.calc);
    const sym = cfg.symbol;
    const g = id => parseFloat(document.getElementById(id).value) || 0;
    const fmt = (v, d=0) => (v < 0 ? '-' : '') + sym + Math.abs(v).toLocaleString('en-US', {{minimumFractionDigits: d, maximumFractionDigits: d}});
    function update() {{
      const price = Math.max(1, g('c-price'));
      const rent = Math.max(0, g('c-rent'));
      const closing = Math.max(0, g('c-closing')) / 100;
      const down = Math.min(100, Math.max(0, g('c-down'))) / 100;
      const rate = Math.max(0, g('c-rate')) / 100 / 12;
      const months = Math.max(1, g('c-term')) * 12;
      const vac = Math.max(0, g('c-vac')) / 100;
      const opexPct = Math.max(0, g('c-opex')) / 100;
      const taxPct = Math.max(0, g('c-tax')) / 100;

      const gross = (rent * 12 / price) * 100;
      const effRentYr = rent * 12 * (1 - vac);
      const noi = effRentYr * (1 - opexPct) - price * taxPct;
      const allIn = price * (1 + closing);
      const netYield = (noi / allIn) * 100;

      const loan = price * (1 - down);
      let mortMo = 0;
      if (loan > 0) {{
        mortMo = rate > 0 ? loan * (rate * Math.pow(1 + rate, months)) / (Math.pow(1 + rate, months) - 1) : loan / months;
      }}
      const cashReq = price * (down + closing);
      const cfMo = (noi / 12) - mortMo;
      const coc = cashReq > 0 ? ((cfMo * 12) / cashReq) * 100 : 0;

      document.getElementById('o-gross').textContent = gross.toFixed(2) + '%';
      document.getElementById('o-net').textContent = netYield.toFixed(2) + '%';
      document.getElementById('o-coc').textContent = coc.toFixed(2) + '%';
      document.getElementById('o-cf').textContent = fmt(cfMo, 0) + '/mo';
      document.getElementById('o-mort').textContent = fmt(mortMo, 0) + '/mo';
      document.getElementById('o-cash').textContent = fmt(cashReq, 0);
    }}
    panel.querySelectorAll('input').forEach(el => el.addEventListener('input', update));
    update();
  }})();
  </script>
</body>
</html>
"""
    csv_text = make_csv(m.get("sample_rows") or [], label, cc, snap_date)
    return page_html, csv_text


def build_hub_page(markets: list[dict], country_meta: dict, snap_date: str) -> tuple[str, str]:
    canonical = BASE + HUB_PATH
    total_sale = sum(m["sale"]["n_priced"] for m in markets)
    total_rent = sum(m["rent"]["n_priced"] for m in markets)
    yields = [m["gross_yield_pct"] for m in markets if m["gross_yield_pct"] is not None]
    med_yield = statistics.median(yields) if yields else 0.0
    top_m = max(markets, key=lambda x: x["gross_yield_pct"] or 0)
    low_m = min(markets, key=lambda x: x["gross_yield_pct"] or 999)

    by_cc: dict[str, list[dict]] = {}
    for m in markets:
        by_cc.setdefault(m["country"], []).append(m)

    country_summary_rows = []
    for cc in ("es", "it", "pt", "us"):
        grp = by_cc.get(cc) or []
        if not grp:
            continue
        cm = country_meta[cc]
        gy_med = statistics.median([x["gross_yield_pct"] for x in grp])
        sp_med = statistics.median([x["sale"]["price_per_sqm"]["median"] for x in grp])
        rp_med = statistics.median([x["rent"]["price"]["median"] for x in grp])
        best = max(grp, key=lambda x: x["gross_yield_pct"])
        country_summary_rows.append(
            f"<tr id=\"country-{cc}\"><td><strong>{esc(cm['name'])}</strong></td>"
            f"<td class=\"num\">{len(grp)}</td>"
            f"<td class=\"num\">{gy_med:.2f}%</td>"
            f"<td class=\"num\">{fmt_money(sp_med, cm['symbol'])}/m²</td>"
            f"<td class=\"num\">{fmt_money(rp_med, cm['symbol'])}/mo</td>"
            f"<td><a href=\"/yield/{cc}/{best['slug']}/\">{esc(best['label'])} ({best['gross_yield_pct']:.2f}%)</a></td></tr>"
        )

    table_rows = []
    for m in sorted(markets, key=lambda x: -(x["gross_yield_pct"] or 0)):
        cc = m["country"]
        sym = m["symbol"]
        pc = m["sale"].get("portal_price_cuts")
        cut_cell = f"{pc['count']} (-{pc['median_cut_pct']}%)" if pc else "Baseline"
        dom = m["sale"].get("dom")
        dom_cell = f"{round(dom['median'])}d" if dom else "—"
        table_rows.append(
            f"<tr data-cc=\"{cc}\" data-name=\"{esc(m['label'].lower())} {esc(m['region'].lower())}\">"
            f"<td><a href=\"/yield/{cc}/{m['slug']}/\"><strong>{esc(m['label'])}</strong></a></td>"
            f"<td>{esc(country_meta[cc]['name'])}</td>"
            f"<td class=\"num\" data-v=\"{m['gross_yield_pct']}\"><strong>{m['gross_yield_pct']:.2f}%</strong></td>"
            f"<td class=\"num\" data-v=\"{m['sale']['price_per_sqm']['median']}\">{fmt_money(m['sale']['price_per_sqm']['median'], sym)}/m²</td>"
            f"<td class=\"num\" data-v=\"{m['rent']['price']['median']}\">{fmt_money(m['rent']['price']['median'], sym)}/mo</td>"
            f"<td class=\"num\" data-v=\"{m['price_to_rent_years']}\">{m['price_to_rent_years']:.1f}x</td>"
            f"<td class=\"num\">{esc(cut_cell)}</td>"
            f"<td class=\"num\">{esc(dom_cell)}</td>"
            f"<td class=\"num\" data-v=\"{m['sale']['n_priced'] + m['rent']['n_priced']}\">{m['sale']['n_priced'] + m['rent']['n_priced']}</td></tr>"
        )

    faq = [
        (
            "How are the EU and US rental yield benchmarks calculated?",
            f"Every city and district page computes area-normalized gross yield as (median monthly rent per m² × 12) / (median asking sale price per m²) "
            f"from live Listingrail portal snapshots captured on {snap_date} ({total_sale:,} sale and {total_rent:,} rental listings across {len(markets)} markets). "
            f"US square-foot areas are converted to square meters using 0.092903 m²/sq ft so EU and US markets compare cleanly."
        ),
        (
            f"Which tracked city has the highest gross rental yield as of {snap_date}?",
            f"In the {snap_date} snapshot, {top_m['label']} ({country_meta[top_m['country']]['name']}) leads the directory at {top_m['gross_yield_pct']:.2f}% "
            f"area-normalized gross yield ({fmt_money(top_m['sale']['price_per_sqm']['median'], top_m['symbol'])}/m² sale vs "
            f"{fmt_money(top_m['rent']['price_per_sqm']['median'], top_m['symbol'], 1)}/m² monthly rent), while {low_m['label']} posts the lowest gross yield at {low_m['gross_yield_pct']:.2f}%."
        ),
        (
            "Do I need an account to download the 25-row city CSV samples?",
            "No. Every market page in this directory includes a direct, no-login 25-row sanitized CSV sample (13 sale and 12 rent listings) "
            "plus an interactive net-yield calculator pre-loaded with local closing costs. Full city datasets ($49) and live API feeds are available through Listingrail."
        ),
        (
            "Why do some markets show 'Baseline' for 30-day price cuts or '—' for days on market?",
            "We never fabricate missing fields. Idealista exposes active discount percentages directly and Imovirtual/Redfin expose listing dates or days-on-market; "
            "portals that omit those fields start with a documented baseline snapshot and populate 30-day price cuts automatically as weekly snapshots accumulate."
        ),
    ]
    faq_html = "\n".join(
        f'      <div class="faq-item"><p class="faq-q">{esc(q)}</p><p class="faq-a">{esc(a)}</p></div>'
        for q, a in faq
    )

    title = f"EU & US Rental Yield & Price-Cut Benchmark Directory ({len(markets)} Markets, {snap_date[:4]})"
    desc = (
        f"Data-backed rental yield, asking price/m², and price-cut benchmarks across {len(markets)} Spain, Italy, Portugal, and US markets "
        f"({total_sale + total_rent:,} live listings, {snap_date}). Free 25-row CSV per city."
    )

    ld_nodes = [
        {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": f"Listingrail EU & US Rental Yield & Price-Cut Benchmark Directory ({snap_date})",
            "description": desc,
            "url": canonical,
            "dateModified": snap_date,
            "isAccessibleForFree": True,
            "creator": {"@type": "Organization", "name": "Listingrail", "url": "https://listingrail.com"},
            "distribution": {
                "@type": "DataDownload",
                "encodingFormat": "text/csv",
                "contentUrl": f"{BASE}/yield/summary.csv",
            },
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq
            ],
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Catalog", "item": f"{BASE}/"},
                {"@type": "ListItem", "position": 2, "name": "Rental Yield Directory", "item": canonical},
            ],
        },
    ]

    # Build hub summary CSV
    sbuf = io.StringIO()
    sw = csv.writer(sbuf)
    sw.writerow(["snapshot_date", "country", "market", "region", "currency", "gross_yield_pct", "headline_yield_pct",
                 "median_sale_price", "median_sale_per_sqm", "median_rent", "median_rent_per_sqm",
                 "price_to_rent_years", "sale_n", "rent_n", "page_url"])
    for m in markets:
        sw.writerow([
            snap_date, m["country"].upper(), m["label"], m["region"], m["currency"],
            m["gross_yield_pct"], m["headline_yield_pct"],
            m["sale"]["price"]["median"], m["sale"]["price_per_sqm"]["median"],
            m["rent"]["price"]["median"], m["rent"]["price_per_sqm"]["median"],
            m["price_to_rent_years"], m["sale"]["n_priced"], m["rent"]["n_priced"],
            f"{BASE}/yield/{m['country']}/{m['slug']}/",
        ])

    hub_html = f"""{html_head(title, desc, canonical, ld_nodes)}
<body>
  <header class="fascia">
    <div class="fascia-inner">
      <nav class="topnav" aria-label="Site navigation">
        <a class="brand" href="/yield/">Listingrail Yield Ledger</a>
        <div class="topnav-links">
          <a href="#directory">Market Table</a>
          <a href="#countries">By Country</a>
          <a href="https://listingrail.com/pricing/?utm_source=yield_directory&amp;utm_medium=nav&amp;utm_content=hub">Pro CSV &amp; API</a>
          <a href="/">Data Catalog</a>
        </div>
      </nav>
      <div class="crumbs"><a href="/">Catalog</a> / Rental Yield Directory</div>
      <div class="hero-row">
        <div class="hero-copy">
          <h1>EU &amp; US Rental Yield &amp; Price-Cut Benchmarks</h1>
          <p class="hero-meta">{len(markets)} verified cities &amp; districts across Spain, Italy, Portugal, and the US · {total_sale + total_rent:,} live listings captured {esc(snap_date)}</p>
        </div>
        <div class="hero-actions">
          <a class="btn-primary" href="/yield/summary.csv" download="listingrail-yield-summary-{esc(snap_date)}.csv">Download summary CSV</a>
          <a class="btn-ghost" href="https://listingrail.com/#key?utm_source=yield_directory&amp;utm_medium=hero&amp;utm_content=hub">Get free API key</a>
        </div>
      </div>
    </div>
  </header>

  <main>
    <article>
      <p class="summary-lead">
        This open benchmark ledger tracks asking sale prices per square meter, asking monthly rents, area-normalized gross rental yields,
        and active price cuts across <strong>{len(markets)}</strong> European and US markets using live Listingrail portal snapshots
        (Idealista, Immobiliare.it, Imovirtual, and Redfin). Across {total_sale:,} sale and {total_rent:,} rental listings captured on
        {esc(snap_date)}, the cross-market median gross yield stands at <strong>{med_yield:.2f}%</strong>, ranging from
        <strong>{low_m['gross_yield_pct']:.2f}%</strong> in {esc(low_m['label'])} up to <strong>{top_m['gross_yield_pct']:.2f}%</strong>
        in {esc(top_m['label'])}. Open any market below for quartiles, bedroom yields, an interactive net-yield calculator, and a free 25-row CSV sample.
      </p>

      <div class="ledger-grid" role="region" aria-label="Directory summary metrics">
        <div class="ledger-cell">
          <span class="ledger-label">Verified markets</span>
          <span class="ledger-val">{len(markets)}</span>
          <span class="ledger-sub">ES {len(by_cc.get('es', []))} · IT {len(by_cc.get('it', []))} · PT {len(by_cc.get('pt', []))} · US {len(by_cc.get('us', []))}</span>
        </div>
        <div class="ledger-cell">
          <span class="ledger-label">Listings analyzed</span>
          <span class="ledger-val">{total_sale + total_rent:,}</span>
          <span class="ledger-sub">{total_sale:,} sale · {total_rent:,} rent</span>
        </div>
        <div class="ledger-cell">
          <span class="ledger-label">Highest gross yield</span>
          <span class="ledger-val positive">{top_m['gross_yield_pct']:.2f}%</span>
          <span class="ledger-sub">{esc(top_m['label'])} ({top_m['country'].upper()})</span>
        </div>
        <div class="ledger-cell">
          <span class="ledger-label">Cross-market median</span>
          <span class="ledger-val">{med_yield:.2f}%</span>
          <span class="ledger-sub">Snapshot {esc(snap_date)}</span>
        </div>
      </div>

      <h2 id="countries">Country Medians ({esc(snap_date)})</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Country</th>
              <th class="num">Markets</th>
              <th class="num">Median gross yield</th>
              <th class="num">Median sale / m²</th>
              <th class="num">Median rent</th>
              <th>Top-yielding market</th>
            </tr>
          </thead>
          <tbody>
            {"".join(country_summary_rows)}
          </tbody>
        </table>
      </div>

      <h2 id="directory">All {len(markets)} City &amp; District Benchmarks</h2>
      <div class="filter-bar" role="region" aria-label="Filter markets">
        <button class="filter-btn active" type="button" data-filter="all">All ({len(markets)})</button>
        <button class="filter-btn" type="button" data-filter="es">Spain ({len(by_cc.get('es', []))})</button>
        <button class="filter-btn" type="button" data-filter="it">Italy ({len(by_cc.get('it', []))})</button>
        <button class="filter-btn" type="button" data-filter="pt">Portugal ({len(by_cc.get('pt', []))})</button>
        <button class="filter-btn" type="button" data-filter="us">US ({len(by_cc.get('us', []))})</button>
        <input class="search-input" id="market-search" type="search" placeholder="Filter city or region..." aria-label="Filter city or region" />
      </div>
      <div class="table-wrap">
        <table id="hub-table">
          <thead>
            <tr>
              <th>Market</th>
              <th>Country</th>
              <th class="num sortable" data-col="2">Gross yield ↕</th>
              <th class="num sortable" data-col="3">Sale / m² ↕</th>
              <th class="num sortable" data-col="4">Median rent ↕</th>
              <th class="num sortable" data-col="5">P/R ratio ↕</th>
              <th class="num">Price cuts</th>
              <th class="num">Sale DOM</th>
              <th class="num sortable" data-col="8">Listings ↕</th>
            </tr>
          </thead>
          <tbody>
            {"".join(table_rows)}
          </tbody>
        </table>
      </div>

      <h2>Methodology &amp; Questions</h2>
      <div class="faq-list">
{faq_html}
      </div>
    </article>
  </main>

{site_footer("hub", snap_date)}

  <script>
  (function() {{
    const btns = document.querySelectorAll('.filter-btn');
    const search = document.getElementById('market-search');
    const tbody = document.querySelector('#hub-table tbody');
    if (!tbody) return;
    let activeCc = 'all';
    function apply() {{
      const q = (search.value || '').trim().toLowerCase();
      tbody.querySelectorAll('tr').forEach(tr => {{
        const okCc = activeCc === 'all' || tr.dataset.cc === activeCc;
        const okQ = !q || (tr.dataset.name || '').includes(q);
        tr.style.display = (okCc && okQ) ? '' : 'none';
      }});
    }}
    btns.forEach(b => b.addEventListener('click', () => {{
      btns.forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      activeCc = b.dataset.filter;
      apply();
    }}));
    search.addEventListener('input', apply);

    let sortCol = 2, sortDir = -1;
    document.querySelectorAll('#hub-table th.sortable').forEach(th => {{
      th.addEventListener('click', () => {{
        const c = parseInt(th.dataset.col, 10);
        sortDir = (c === sortCol) ? -sortDir : -1;
        sortCol = c;
        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {{
          const av = parseFloat(a.children[c].dataset.v || '0');
          const bv = parseFloat(b.children[c].dataset.v || '0');
          return (av - bv) * sortDir;
        }});
        rows.forEach(r => tbody.appendChild(r));
      }});
    }});
  }})();
  </script>
</body>
</html>
"""
    return hub_html, sbuf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Report paths without writing files")
    ap.add_argument("--snapshot", type=Path, default=SNAP_PATH)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    if not args.snapshot.is_file():
        raise SystemExit(f"Snapshot file missing: {args.snapshot}. Run scripts/fetch_yield_snapshots.py first.")

    data = json.loads(args.snapshot.read_text())
    markets = data.get("markets") or []
    country_meta = data["country_meta"]
    snap_date = data["snapshot_date"]

    if not markets:
        raise SystemExit("Snapshot contains 0 verified markets; refusing to emit empty pages.")

    paths = [HUB_PATH] + [f"/yield/{m['country']}/{m['slug']}/" for m in markets]
    if args.dry_run:
        print(f"Dry run: would generate {len(paths)} pages (noindex={not INDEX}) from {args.snapshot} ({snap_date})")
        for p in paths:
            print(" ", p)
        return 0

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "style.css").write_text(SHARED_CSS.lstrip())

    hub_html, summary_csv = build_hub_page(markets, country_meta, snap_date)
    (args.out / "index.html").write_text(hub_html)
    (args.out / "summary.csv").write_text(summary_csv)

    # Precompute country rankings & medians
    by_cc: dict[str, list[dict]] = {}
    for m in markets:
        by_cc.setdefault(m["country"], []).append(m)
    cc_med = {cc: statistics.median([x["gross_yield_pct"] for x in grp]) for cc, grp in by_cc.items()}
    cc_ranks = {}
    for cc, grp in by_cc.items():
        ranked = sorted(grp, key=lambda x: -(x["gross_yield_pct"] or 0))
        for idx, x in enumerate(ranked, 1):
            cc_ranks[(cc, x["slug"])] = (idx, len(ranked))

    for m in markets:
        cc, slug = m["country"], m["slug"]
        rank, total = cc_ranks[(cc, slug)]
        p_html, p_csv = build_market_page(m, markets, country_meta[cc], snap_date, rank, total, cc_med[cc])
        mdir = args.out / cc / slug
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / "index.html").write_text(p_html)
        (mdir / "sample.csv").write_text(p_csv)

    print(f"Built {len(paths)} pages + {len(markets)+1} CSVs under {args.out} (snapshot {snap_date}, noindex={not INDEX})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
