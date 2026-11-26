#!/usr/bin/env python3
"""Build the static /rent-drops/ directory from data/rent-drops/latest.json.

Reads only the public snapshot JSON written by scripts/fetch_rent_drops.py (no portal blobs, no contact data) and writes:
  rent-drops/index.html             hub: 50-metro table, calculator, method, FAQ
  rent-drops/<slug>/index.html      one page per metro

Pages start noindex (pSEO gate) unless RENT_DROPS_INDEX=1 is set; the sitemap entry belongs to the pSEO step.

Usage: python3 scripts/build_rent_drops.py [--snapshot PATH] [--out DIR] [--dry-run]
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT = ROOT / "data" / "rent-drops" / "latest.json"
DEFAULT_OUT = ROOT / "rent-drops"
SITE = "https://benthepythondev00.github.io"
BASE = "/rent-drops/"
CSV_BASE = "/data/rent-drops/samples/"
INDEX = os.environ.get("RENT_DROPS_INDEX", "").strip() == "1"

BEDS = ("0", "1", "2", "3")
SUMMARY_MIN, SUMMARY_MAX = 130, 170
FEEDS_URL = "/feeds/"
LISTINGRAIL_PRICING = "https://listingrail.com/pricing/"
LISTINGRAIL_DOCS = "https://listingrail.com/docs/"
APIFY_ACTORS = {
    "apartments-com": ("Apartments.com Rent Monitor", "https://apify.com/benthepythondev/apartments-com-rent-monitor"),
    "zumper": ("Zumper Rental Scraper", "https://apify.com/benthepythondev/zumper-rental-scraper"),
}
CONCESSION_KINDS = {
    "free_time": "weeks or months free",
    "pct_off": "percent off for a set number of months",
    "dollar_off": "a dollar amount off",
    "look_and_lease": "look-and-lease (sign within days of a tour)",
    "waived_fees": "waived application, admin or amenity fees",
}
REQUIRED_TOP = ("snapshot_date", "method", "metros")
REQUIRED_METRO = ("slug", "label", "city", "state", "snapshot_date", "n_apartments_com", "n_zumper", "n_priced",
                  "concessions", "bedrooms", "zumper_spread", "rent_cuts_30d", "sample_rows")
SAMPLE_FIELDS = ("listing_id", "source", "property_name", "city", "zip", "beds", "sqft", "asking_rent",
                 "rent_per_sqft", "concession_verified", "concession_type", "free_weeks", "net_effective_rent",
                 "snapshot_date", "listing_url")
SAFE_URL = re.compile(r"^https://(www\.)?(apartments\.com|zumper\.com)/", re.I)
CONTACT_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")


class SnapshotError(ValueError):
    pass


# ------------------------------------------------------------------ helpers
def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def usd(x) -> str:
    return f"${round(float(x)):,}"


def pct(x, d=0) -> str:
    return f"{float(x):.{d}f}%"


def fmt_date(d: str) -> str:
    dt = date.fromisoformat(d)
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def wk(x) -> str:
    x = float(x)
    return f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}"


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9$%.,'/-]+", text))


def ld(obj) -> str:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s.replace("</", "<\\/")


def utm(url: str, medium: str, campaign: str) -> str:
    sep = "&" if "?" in url.split("#")[0] else "?"
    frag = ""
    if "#" in url:
        url, frag = url.split("#", 1)
        frag = "#" + frag
    return f"{url}{sep}utm_source=rent_drops&utm_medium={medium}&utm_campaign={campaign}{frag}"


# ------------------------------------------------------------------ validation
def load_snapshot(path: Path) -> dict:
    try:
        snap = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise SnapshotError(f"{path} not found: run scripts/fetch_rent_drops.py first") from exc
    validate(snap)
    return snap


def validate(snap: dict) -> None:
    for k in REQUIRED_TOP:
        if k not in snap:
            raise SnapshotError(f"snapshot is missing '{k}'")
    d = snap["snapshot_date"]
    date.fromisoformat(d)
    if not snap["metros"]:
        raise SnapshotError("snapshot has no metros")
    if "label" not in snap["method"]:
        raise SnapshotError("method block has no label")
    seen = set()
    for m in snap["metros"]:
        for k in REQUIRED_METRO:
            if k not in m:
                raise SnapshotError(f"{m.get('slug', '?')}: missing '{k}'")
        if not re.fullmatch(r"[a-z0-9-]+", m["slug"]) or m["slug"] in seen:
            raise SnapshotError(f"bad or duplicate slug {m['slug']!r}")
        seen.add(m["slug"])
        if m["snapshot_date"] != d:
            raise SnapshotError(f"{m['slug']}: snapshot_date {m['snapshot_date']} != {d}")
        for row in m["sample_rows"]:
            if row.get("snapshot_date") != d:
                raise SnapshotError(f"{m['slug']}: sample row dated {row.get('snapshot_date')} != {d}")
            extra = set(row) - set(SAMPLE_FIELDS)
            if extra:
                raise SnapshotError(f"{m['slug']}: sample row has unexpected fields {sorted(extra)}")
        rc = m["rent_cuts_30d"]
        if not rc.get("unlocked") and rc.get("count") is not None:
            raise SnapshotError(f"{m['slug']}: rent-cut count present while locked")
        for b in BEDS:
            e = m["bedrooms"].get(b)
            if e is None:
                raise SnapshotError(f"{m['slug']}: bedroom bucket {b} missing")
            if e.get("published") and e.get("n", 0) < 20:
                raise SnapshotError(f"{m['slug']}: bucket {b} published with n={e.get('n')}")


def published(m: dict) -> list[tuple[str, dict]]:
    return [(b, m["bedrooms"][b]) for b in BEDS if m["bedrooms"][b].get("published")]


def unlock_date(snapshot_date: str, rc: dict) -> str:
    left = max(0, int(rc.get("weeks_needed", 4)) - int(rc.get("weeks_collected", 1)))
    return (date.fromisoformat(snapshot_date) + timedelta(days=7 * left)).isoformat()


# ------------------------------------------------------------------ copy
def summary_text(m: dict, snap_date: str) -> str:
    """130-170 word citable answer block. Built from optional sentences until it lands in range."""
    c = m["concessions"]
    city = m["label"]
    pub = published(m)
    when = fmt_date(snap_date)
    core = [
        f"In the {when} snapshot of {city}, {m['n_apartments_com']} Apartments.com properties and "
        f"{m['n_zumper']} Zumper listings advertised a price.",
    ]
    if c.get("share_pct") is not None:
        core.append(
            f"{pct(c['share_pct'])} of the Apartments.com properties ({c['n_verified']} of {c['n_properties']}) "
            f"advertised a concrete move-in concession such as weeks free or a dollar amount off; generic "
            f"marketing taglines were not counted.")
    if c.get("median_free_weeks"):
        core.append(f"Where the special was free time, the median offer was {wk(c['median_free_weeks'])} weeks free"
                    + (f" and the largest was {wk(c['max_free_weeks'])} weeks." if c.get("max_free_weeks") else "."))
    one = m["bedrooms"].get("1", {})
    if one.get("published"):
        gap = one["headline_median"] - one["net_effective_median"]
        core.append(
            f"The median one-bedroom floor plan asked {usd(one['headline_median'])} a month; spread over a "
            f"12-month lease with the advertised special, that is {usd(one['net_effective_median'])} net-effective, "
            f"{usd(gap)} less.")
    elif pub:
        b, e = pub[0]
        core.append(f"The median {e['label']} floor plan asked {usd(e['headline_median'])} a month, or "
                    f"{usd(e['net_effective_median'])} net-effective over a 12-month lease.")
    optional = []
    if c.get("median_effective_discount_pct"):
        optional.append(f"Among properties with a priced special, the median saving was "
                        f"{pct(c['median_effective_discount_pct'], 1)} of a year's rent.")
    if len(pub) > 1:
        optional.append(f"Bedroom medians are published for {', '.join(e['label'] for _, e in pub)}, each from at "
                        f"least 20 floor plans.")
    else:
        optional.append("Bedroom medians are only published where at least 20 floor plans exist.")
    optional.append("These are publicly advertised asking rents and specials, not signed leases.")
    if m.get("rent_per_sqft_median"):
        optional.append(f"Across all published floor plans the median asking rent was "
                        f"${m['rent_per_sqft_median']:.2f} per square foot.")
    extra = (c.get("n_with_specials_text") or 0) - (c.get("n_verified") or 0)
    if extra > 0:
        optional.append(f"Another {extra} propert{'y' if extra == 1 else 'ies'} showed special text without a "
                        f"stated value and {'was' if extra == 1 else 'were'} left out of the share.")
    rc = m["rent_cuts_30d"]
    if rc.get("unlocked") and rc.get("count") is not None:
        optional.append(f"Over the last 30 days, {rc['count']} of {rc['n_matched']} repeat listings cut their "
                        f"asking rent.")
    else:
        optional.append(f"Thirty-day rent cuts are reported once four weekly snapshots exist, from "
                        f"{fmt_date(unlock_date(snap_date, rc))}.")
    optional.append("The free 25-row CSV sample below needs no login.")
    optional.append("Snapshots refresh weekly from the same public listings.")

    text = " ".join(core)
    for s in optional:
        if words(text) >= SUMMARY_MIN:
            break
        if words(text + " " + s) <= SUMMARY_MAX:
            text += " " + s
    n = words(text)
    if not SUMMARY_MIN <= n <= SUMMARY_MAX:
        raise SnapshotError(f"{m['slug']}: summary is {n} words, outside {SUMMARY_MIN}-{SUMMARY_MAX}")
    return text


def hub_summary(snap: dict) -> str:
    ms = snap["metros"]
    shares = [m["concessions"]["share_pct"] for m in ms if m["concessions"].get("share_pct") is not None]
    top = sorted((m for m in ms if m["concessions"].get("share_pct") is not None),
                 key=lambda m: -m["concessions"]["share_pct"])[:3]
    low = min((m for m in ms if m["concessions"].get("share_pct") is not None),
              key=lambda m: m["concessions"]["share_pct"])
    n_props = sum(m["n_apartments_com"] for m in ms)
    n_z = sum(m["n_zumper"] for m in ms)
    ver = sum(m["concessions"]["n_verified"] for m in ms)
    base = sum(m["concessions"]["n_properties"] for m in ms)
    shares.sort()
    med = shares[len(shares) // 2] if len(shares) % 2 else (shares[len(shares) // 2 - 1] + shares[len(shares) // 2]) / 2
    text = (
        f"The {fmt_date(snap['snapshot_date'])} snapshot covers {len(ms)} US metros, {n_props:,} Apartments.com "
        f"properties and {n_z:,} Zumper listings with an advertised price. Across all metros, {ver:,} of "
        f"{base:,} Apartments.com properties ({pct(ver / base * 100)}) advertised a concrete move-in concession "
        f"such as weeks free, a dollar amount off or look-and-lease; generic taglines were not counted. The median "
        f"metro sat at {pct(med)}. The highest shares were in {', '.join(f'{m['label']} ({pct(m['concessions']['share_pct'])})' for m in top)}; "
        f"the lowest was {low['label']} at {pct(low['concessions']['share_pct'])}. Each metro page shows Studio to "
        f"3BR headline and net-effective asking rents (published only from 20 or more floor plans), the "
        f"Zumper-to-Apartments.com price gap, a 25-row CSV sample with no login, and a calculator for any special. "
        f"Figures are publicly advertised asking rents and specials, not signed leases or private rent rolls."
    )
    gaps = sorted(m["bedrooms"]["1"]["headline_median"] - m["bedrooms"]["1"]["net_effective_median"]
                  for m in ms if m["bedrooms"].get("1", {}).get("published"))
    optional = []
    if gaps:
        optional.append(f"The median gap between 1BR asking and net-effective rent was "
                        f"{usd(gaps[len(gaps) // 2])} a month.")
    optional += ["Snapshots refresh weekly from the same public listings.",
                 "Thirty-day rent cuts appear once four weekly snapshots exist."]
    for sentence in optional:
        if words(text) >= SUMMARY_MIN:
            break
        if words(text + " " + sentence) <= SUMMARY_MAX:
            text += " " + sentence
    n = words(text)
    if not SUMMARY_MIN <= n <= SUMMARY_MAX:
        raise SnapshotError(f"hub summary is {n} words, outside {SUMMARY_MIN}-{SUMMARY_MAX}")
    return text


def metro_faq(m: dict, snap_date: str) -> list[tuple[str, str]]:
    c = m["concessions"]
    city = m["label"]
    rc = m["rent_cuts_30d"]
    one = m["bedrooms"].get("1", {})
    qa = []
    if c.get("share_pct") is not None:
        qa.append((f"How many {city} apartments are offering move-in specials right now?",
                   f"In the {fmt_date(snap_date)} snapshot, {c['n_verified']} of {c['n_properties']} priced "
                   f"Apartments.com properties in {city} ({pct(c['share_pct'])}) advertised a concrete concession. "
                   f"Only specials with a value we can parse count, such as weeks free, months free, a dollar "
                   f"amount off or a look-and-lease deal."))
    if one.get("published"):
        qa.append((f"What is the net-effective rent for a one-bedroom in {city}?",
                   f"The median one-bedroom floor plan advertised {usd(one['headline_median'])} a month. Applying "
                   f"each property's advertised special over a 12-month lease gives a median net-effective rent of "
                   f"{usd(one['net_effective_median'])}, from {one['n']} floor plans. Specials marked 'up to' or "
                   f"'select units' are taken at their largest value, so this is the most a renter could save."))
    qa.append(("How is net-effective rent calculated?",
               "Net-effective rent spreads the value of the concession over the lease: asking rent times (1 minus "
               "free months divided by lease months). Weeks free convert to months at 52/12 weeks a month, and a "
               "dollar amount off is divided by the lease length. Waived fees are a one-time saving and do not "
               "change the monthly rent."))
    if rc.get("unlocked") and rc.get("count") is not None:
        qa.append((f"Are {city} landlords cutting asking rents?",
                   f"Over the 30 days to {fmt_date(snap_date)}, {rc['count']} of {rc['n_matched']} listings seen in "
                   f"earlier snapshots advertised a lower asking rent than their 30-day high."))
    else:
        qa.append((f"Are {city} landlords cutting asking rents?",
                   f"We report 30-day asking-rent cuts only after four weekly snapshots of the same listing ids exist. "
                   f"{rc.get('weeks_collected', 1)} of {rc.get('weeks_needed', 4)} weeks are collected, so the first "
                   f"count appears with the snapshot of {fmt_date(unlock_date(snap_date, rc))}. Until then this page "
                   f"shows no rent-cut figure."))
    qa.append(("Are these signed lease rents?",
               "No. Every figure is a publicly advertised asking rent or move-in special on Apartments.com or Zumper "
               "on the snapshot date. It is not a signed lease, not private rent-roll data and not pricing or legal "
               "advice."))
    qa.append((f"Can I download the {city} data?",
               f"Yes. A 25-row CSV sample of {city} floor plans and listings is free with no login. The full weekly "
               f"feed for this metro is available through the Listingrail API (free tier 250 listings a month, paid "
               f"plans $10 to $149 a month) or as a managed CSV, JSON or webhook feed from $199 a month."))
    return qa


def hub_faq(snap: dict) -> list[tuple[str, str]]:
    ms = snap["metros"]
    return [
        ("Which US cities have the most apartment concessions right now?",
         "Sorted by the share of priced Apartments.com properties advertising a concrete special in the "
         f"{fmt_date(snap['snapshot_date'])} snapshot: "
         + ", ".join(f"{m['label']} {pct(m['concessions']['share_pct'])}" for m in sorted(
             (m for m in ms if m["concessions"].get("share_pct") is not None),
             key=lambda m: -m["concessions"]["share_pct"])[:5]) + "."),
        ("What counts as a concession here?",
         "Only specials with a value we can parse: weeks or months free, a percent off for a set number of months, "
         "a dollar amount off, look-and-lease deals and waived fees. Taglines such as 'ask about our specials', gift "
         "cards and 'rents starting at' prices are not counted."),
        ("How is net-effective rent calculated?",
         "Asking rent times (1 minus free months divided by lease months). Weeks free convert to months at 52/12 "
         "weeks a month; a dollar amount off is divided by the lease length. Waived fees are one-time and do not "
         "change the monthly rent."),
        ("Why are some bedroom medians missing?",
         "A median is shown only when at least 20 floor plans of that size exist in the metro sample, after "
         "removing student, co-living and per-bed plans. Below that, the page shows the count and no number."),
        ("When do the 30-day rent cuts appear?",
         "After four weekly snapshots of the same listing ids. Until then no rent-cut count is published."),
        ("Are these signed lease rents?",
         "No. They are publicly advertised asking rents and move-in specials, not signed leases, not private "
         "rent-roll data and not pricing or legal advice."),
    ]


# ------------------------------------------------------------------ html parts
def head(title: str, desc: str, path: str, jsonld: list, snap_date: str) -> str:
    robots = "index,follow" if INDEX else "noindex,follow"
    url = SITE + path
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}" />
<meta name="robots" content="{robots}" />
<link rel="canonical" href="{esc(url)}" />
<meta property="og:type" content="article" />
<meta property="og:title" content="{esc(title)}" />
<meta property="og:description" content="{esc(desc)}" />
<meta property="og:url" content="{esc(url)}" />
<meta property="article:modified_time" content="{snap_date}" />
<meta name="color-scheme" content="light dark" />
<link rel="preload" href="{BASE}fonts/newsreader-latin-opsz-normal.woff2" as="font" type="font/woff2" crossorigin />
<link rel="stylesheet" href="{BASE}style.css" />
{"".join(f'<script type="application/ld+json">{ld(o)}</script>' for o in jsonld)}
</head>
"""


def masthead(crumbs: list[tuple[str, str | None]], snap_date: str) -> str:
    trail = " <span aria-hidden=\"true\">/</span> ".join(
        f'<a href="{esc(h)}">{esc(t)}</a>' if h else f'<span aria-current="page">{esc(t)}</span>' for t, h in crumbs)
    return f"""<body>
<a class="skip" href="#main">Skip to content</a>
<header class="mast">
  <div class="wrap mast-row">
    <a class="brand" href="{BASE}"><span class="brand-mark" aria-hidden="true"></span>Rent Drops</a>
    <nav class="crumbs" aria-label="Breadcrumb">{trail}</nav>
    <span class="mast-date">Snapshot <time datetime="{snap_date}">{fmt_date(snap_date)}</time></span>
  </div>
</header>
"""


def calculator(preset: dict, presets: list[tuple[str, dict]], heading: str, intro: str) -> str:
    p = {"asking": 1500, "lease": 12, "kind": "weeks", "amount": 6, "fees": 0, **preset}
    btns = "".join(
        f'<button type="button" class="chip" data-preset="{esc(json.dumps(v))}">{esc(t)}</button>' for t, v in presets)
    sel = lambda k: " selected" if p["kind"] == k else ""  # noqa: E731
    return f"""<section class="calc" id="calculator" aria-labelledby="calc-h">
  <h2 id="calc-h">{esc(heading)}</h2>
  <p class="lede">{esc(intro)}</p>
  <form data-ner novalidate>
    <div class="calc-grid">
      <div class="calc-in">
        <label>Advertised monthly rent <span class="in-pre"><span aria-hidden="true">$</span><input name="asking" inputmode="decimal" value="{p['asking']}" autocomplete="off" /></span></label>
        <label>Lease term (months) <input name="lease" inputmode="numeric" value="{p['lease']}" autocomplete="off" /></label>
        <label>Concession type
          <select name="kind">
            <option value="weeks"{sel('weeks')}>Weeks free</option>
            <option value="months"{sel('months')}>Months free</option>
            <option value="dollars"{sel('dollars')}>Dollar amount off</option>
            <option value="none"{sel('none')}>No concession</option>
          </select>
        </label>
        <label>Concession amount <span class="in-post"><input name="amount" inputmode="decimal" value="{p['amount']}" autocomplete="off" /><span data-unit>weeks free</span></span></label>
        <label>Waived one-time fees <span class="in-pre"><span aria-hidden="true">$</span><input name="fees" inputmode="decimal" value="{p['fees']}" autocomplete="off" /></span></label>
        {f'<div class="chips" role="group" aria-label="Load a typical special">{btns}</div>' if btns else ''}
      </div>
      <div class="calc-out" aria-live="polite">
        <p class="out-label">Net-effective rent</p>
        <p class="out-big" data-out="net">&nbsp;</p>
        <div class="bar" data-bar aria-hidden="true"><span></span></div>
        <dl class="out-list">
          <div><dt>Monthly discount</dt><dd data-out="discount"></dd></div>
          <div><dt>Free time, in months</dt><dd data-out="free"></dd></div>
          <div><dt>Rent saved over the lease</dt><dd data-out="rent-saving"></dd></div>
          <div><dt>Total saving incl. waived fees</dt><dd data-out="total-saving"></dd></div>
          <div><dt>Rent paid over the lease</dt><dd data-out="lease-total"></dd></div>
          <div><dt>Rise at renewal if asking rent holds</dt><dd data-out="renewal"></dd></div>
        </dl>
        <p class="err" data-error role="alert" hidden></p>
      </div>
    </div>
    <noscript><p class="note">The calculator needs JavaScript. By hand: asking rent x (1 - free months / lease months).</p></noscript>
  </form>
</section>
"""


def bedroom_section(m: dict) -> str:
    pub = published(m)
    hi = max(e["headline_median"] for _, e in pub) * 1.03 if pub else 1.0
    lo = min(e["net_effective_median"] for _, e in pub) * 0.9 if pub else 0.0
    span = max(hi - lo, 1.0)
    scale = lambda v: (v - lo) / span  # noqa: E731
    rows = []
    for b in BEDS:
        e = m["bedrooms"][b]
        if e.get("published"):
            h, n = e["headline_median"], e["net_effective_median"]
            gap = h - n
            psf = f"${e['rent_per_sqft_median']:.2f}" if e.get("rent_per_sqft_median") else "<span class=\"na\">n/a</span>"
            sq = f"{e['sqft_median']:,}" if e.get("sqft_median") else "<span class=\"na\">n/a</span>"
            q = e.get("headline") or {}
            rng = f"{usd(q['p25'])} to {usd(q['p75'])}" if q.get("p25") else ""
            rows.append(f"""<tr>
  <th scope="row">{esc(e['label'])}</th>
  <td class="num">{usd(h)}</td>
  <td class="num strong">{usd(n)}</td>
  <td class="num cut">{'-' + usd(gap) if gap >= 0.5 else '$0'}</td>
  <td class="viz" aria-hidden="true"><span class="dumb" style="--h:{scale(h):.4f};--n:{scale(n):.4f}"><i class="dn"></i><i class="dh"></i></span></td>
  <td class="num">{psf}</td>
  <td class="num">{sq}</td>
  <td class="num">{e['n']:,}</td>
  <td class="rng">{rng}</td>
</tr>""")
        else:
            rows.append(f"""<tr class="held">
  <th scope="row">{esc(e['label'])}</th>
  <td colspan="7" class="held-note">Not shown: {e['n']} floor plan{'s' if e['n'] != 1 else ''} in the sample, below the 20 needed for a median.</td>
  <td class="num">{e['n']:,}</td>
</tr>""")
    removed = m.get("n_plans_removed_per_bed") or 0
    return f"""<section id="bedrooms" aria-labelledby="beds-h">
  <h2 id="beds-h">Headline vs net-effective asking rent by bedroom</h2>
  <p>Median of {m.get('n_floor_plans', 0):,} Apartments.com floor plans{f', after removing {removed:,} student, co-living or per-bed plans' if removed else ''}. Net-effective applies each property's advertised special over a 12-month lease.</p>
  <div class="scroll" tabindex="0" role="region" aria-label="Bedroom rent table">
  <table class="beds">
    <thead><tr><th scope="col">Size</th><th scope="col" class="num">Headline</th><th scope="col" class="num">Net-effective</th><th scope="col" class="num">Gap</th><th scope="col" class="viz"><span class="key"><i class="dn"></i>net <i class="dh"></i>headline</span></th><th scope="col" class="num">$/sq ft</th><th scope="col" class="num">Sq ft</th><th scope="col" class="num">Plans (n)</th><th scope="col">Middle half</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  </div>
</section>
"""


def concession_section(m: dict) -> str:
    c = m["concessions"]
    if c.get("share_pct") is None:
        return ""
    kinds = sorted((c.get("kinds") or {}).items(), key=lambda kv: -kv[1])
    items = "".join(
        f'<li><span class="k-n">{v}</span> {esc(CONCESSION_KINDS.get(k, k.replace("_", " ")))}</li>' for k, v in kinds)
    facts = []
    if c.get("median_free_weeks"):
        facts.append(f"<div><dt>Median free time</dt><dd>{wk(c['median_free_weeks'])} weeks</dd></div>")
    if c.get("max_free_weeks"):
        facts.append(f"<div><dt>Largest free time</dt><dd>{wk(c['max_free_weeks'])} weeks</dd></div>")
    if c.get("median_effective_discount_pct"):
        facts.append(f"<div><dt>Median saving on a year's rent</dt><dd>{pct(c['median_effective_discount_pct'], 1)}</dd></div>")
    if c.get("n_already_net"):
        facts.append(f"<div><dt>Rate already net of the special</dt><dd>{c['n_already_net']} properties</dd></div>")
    share = float(c["share_pct"])
    return f"""<section id="concessions" aria-labelledby="conc-h">
  <h2 id="conc-h">Move-in concessions</h2>
  <div class="conc">
    <div class="conc-share">
      <p class="share-num">{pct(share)}</p>
      <p class="share-cap">of {c['n_properties']} priced Apartments.com properties advertised a concrete special ({c['n_verified']} properties). {c.get('n_with_specials_text', 0) - c['n_verified'] if c.get('n_with_specials_text', 0) > c['n_verified'] else 0} more had special text that did not name a value and were not counted.</p>
      <div class="meter" role="img" aria-label="{pct(share)} of properties"><span style="width:{share:.1f}%"></span></div>
    </div>
    <div>
      <h3>Type of special</h3>
      <ul class="kinds">{items}</ul>
      <dl class="facts">{''.join(facts)}</dl>
    </div>
  </div>
  <p class="note">A property can carry more than one type. 'Up to' and 'select units' specials are read at their largest stated value. Zumper listings have no specials field, so the share uses Apartments.com only.</p>
</section>
"""


def spread_section(m: dict) -> str:
    rows = []
    for b in BEDS:
        s = (m.get("zumper_spread") or {}).get(b)
        label = m["bedrooms"][b]["label"]
        if s:
            rows.append(f"<tr><th scope=\"row\">{esc(label)}</th><td class=\"num\">{usd(s['apartments_com_median'])}</td>"
                        f"<td class=\"num\">{usd(s['zumper_median'])}</td><td class=\"num\">{s['spread_pct']:+.1f}%</td>"
                        f"<td class=\"num\">{s['n_apartments_com']} / {s['n_zumper']}</td></tr>")
        else:
            rows.append(f"<tr class=\"held\"><th scope=\"row\">{esc(label)}</th><td colspan=\"4\" class=\"held-note\">"
                        f"Not compared: fewer than 20 listings of this size on one of the two sites.</td></tr>")
    return f"""<section id="spread" aria-labelledby="spread-h">
  <h2 id="spread-h">Zumper vs Apartments.com listing prices</h2>
  <p>Median listing-level 'from' price on each site, same metro and snapshot. A negative gap means Zumper listings asked less.</p>
  <div class="scroll" tabindex="0" role="region" aria-label="Cross-site price table">
  <table>
    <thead><tr><th scope="col">Size</th><th scope="col" class="num">Apartments.com</th><th scope="col" class="num">Zumper</th><th scope="col" class="num">Gap</th><th scope="col" class="num">Listings (n)</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  </div>
</section>
"""


def cuts_section(m: dict, snap_date: str) -> str:
    rc = m["rent_cuts_30d"]
    if rc.get("unlocked") and rc.get("count") is not None:
        body = (f"<p class=\"cuts-num\">{rc['count']:,} <span>of {rc['n_matched']:,} repeat listings</span></p>"
                f"<p>advertised a lower asking rent than their highest in the 30 days since "
                f"{fmt_date(rc['baseline_date'])}"
                + (f", a median cut of {rc['median_cut_pct']:.1f}%" if rc.get("median_cut_pct") is not None else "")
                + ".</p>")
    else:
        got, need = int(rc.get("weeks_collected", 1)), int(rc.get("weeks_needed", 4))
        ticks = "".join(f'<li class="{"on" if i < got else ""}"><span>Week {i + 1}</span></li>' for i in range(need))
        body = (f"<ol class=\"weeks\" aria-label=\"{got} of {need} weekly snapshots collected\">{ticks}</ol>"
                f"<p>{got} of {need} weekly snapshots collected. A rent cut is the same listing id advertising less "
                f"than its 30-day high, so the first count appears with the snapshot of "
                f"<time datetime=\"{unlock_date(snap_date, rc)}\">{fmt_date(unlock_date(snap_date, rc))}</time>. "
                f"No figure is shown before then.</p>")
    return f"""<section id="rent-cuts" aria-labelledby="cuts-h">
  <h2 id="cuts-h">30-day asking-rent cuts</h2>
  {body}
</section>
"""


def sample_section(m: dict) -> str:
    rows = []
    for r in m["sample_rows"]:
        url = r.get("listing_url") or ""
        name = esc(r.get("property_name") or "")
        cell = f'<a href="{esc(url)}" rel="nofollow noopener" target="_blank">{name}</a>' if SAFE_URL.match(url) else name
        beds = {0: "Studio", "0": "Studio"}.get(r.get("beds"), f"{r.get('beds')}BR" if r.get("beds") != "" else "")
        rows.append(
            f"<tr><td>{cell}</td><td>{esc(r.get('source'))}</td><td>{esc(r.get('zip'))}</td><td>{esc(beds)}</td>"
            f"<td class=\"num\">{usd(r['asking_rent'])}</td>"
            f"<td class=\"num\">{usd(r['net_effective_rent']) if r.get('net_effective_rent') not in ('', None) else '<span class=na>n/a</span>'}</td>"
            f"<td>{esc((r.get('concession_type') or '').replace('_', ' ').replace('+', ', ')) or '<span class=na>none</span>'}</td>"
            f"<td class=\"num\">{esc(wk(r['free_weeks'])) if r.get('free_weeks') not in ('', None) else ''}</td>"
            f"<td class=\"num\">{esc(r.get('sqft'))}</td></tr>")
    csv = f"{CSV_BASE}{m['slug']}.csv"
    already = any(r.get("free_weeks") not in ("", None) and r.get("net_effective_rent") == r.get("asking_rent")
                  for r in m["sample_rows"])
    already_note = ('<p class="note">Where weeks free are listed but net-effective equals asking, the property says its '
                    'advertised rate already includes the special, so it is not discounted twice.</p>') if already else ""
    return f"""<section id="sample" aria-labelledby="sample-h">
  <h2 id="sample-h">Free 25-row sample</h2>
  <p>{len(m['sample_rows'])} rows from this snapshot: Apartments.com floor plans first, then Zumper listings. Ids, prices and public listing pages only; no agent names, phone numbers or emails. <a class="dl" href="{esc(csv)}" download>Download {esc(m['slug'])}.csv</a></p>
  <div class="scroll" tabindex="0" role="region" aria-label="Sample rows">
  <table class="sample">
    <thead><tr><th scope="col">Property</th><th scope="col">Source</th><th scope="col">ZIP</th><th scope="col">Size</th><th scope="col" class="num">Asking</th><th scope="col" class="num">Net-effective</th><th scope="col">Special</th><th scope="col" class="num">Weeks free</th><th scope="col" class="num">Sq ft</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  </div>
  {already_note}
</section>
"""


def reproduce_section(m: dict | None) -> str:
    loc = m["location"] if m else "Austin, TX"
    slug = m["slug"] if m else "hub"
    snippet = (
        "curl -s https://listingrail.com/v1/listings/search \\\n"
        "  -H \"Authorization: Bearer $LISTINGRAIL_API_KEY\" \\\n"
        "  -H \"Content-Type: application/json\" \\\n"
        f"  -d '{{\"source\":\"apartments-com\",\"location\":\"{loc}\",\"type\":\"rent\",\"limit\":100}}'"
    )
    actors = " and ".join(
        f'<a href="{esc(utm(u, "apify", slug))}" rel="noopener" target="_blank">{esc(n)}</a>' for n, u in APIFY_ACTORS.values())
    return f"""<section id="reproduce" aria-labelledby="rep-h">
  <h2 id="rep-h">Reproduce this snapshot</h2>
  <p>The same pull, from the Listingrail API (repeat with <code>"source":"zumper"</code>). The free tier covers 250 listings a month; see the <a href="{esc(utm(LISTINGRAIL_DOCS, 'docs', slug))}" rel="noopener" target="_blank">API docs</a>.</p>
  <pre class="code"><code>{esc(snippet)}</code></pre>
  <p>Or run the self-serve Apify actors: {actors}.</p>
</section>
"""


def cta_section(slug: str) -> str:
    feeds = utm(FEEDS_URL + "#real-estate", "cta", slug)
    lr = utm(LISTINGRAIL_PRICING, "cta", slug)
    zum = utm(APIFY_ACTORS["zumper"][1], "cta", slug)
    return f"""<section class="cta" id="get-data" aria-labelledby="cta-h">
  <h2 id="cta-h">Get the full weekly data</h2>
  <div class="cta-rows">
    <div class="cta-row primary">
      <div><h3>Managed feed</h3><p>Every metro, weekly CSV, JSON or webhook with rent-cut diffs. $199, $499 or $999 a month, month to month.</p></div>
      <a class="btn" href="{esc(feeds)}">See feed plans</a>
    </div>
    <div class="cta-row">
      <div><h3>Listingrail API</h3><p>Query Apartments.com, Zumper and other portals yourself. Free 250 listings a month; $10, $49 or $149 a month after that.</p></div>
      <a class="btn ghost" href="{esc(lr)}" rel="noopener" target="_blank">Listingrail pricing</a>
    </div>
    <div class="cta-row">
      <div><h3>Apify actors</h3><p>Pay per run on Apify, no subscription.</p></div>
      <a class="btn ghost" href="{esc(zum)}" rel="noopener" target="_blank">Open on Apify</a>
    </div>
  </div>
</section>
"""


def faq_html(qa: list[tuple[str, str]]) -> str:
    items = "".join(f"<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>" for q, a in qa)
    return f"""<section id="faq" aria-labelledby="faq-h">
  <h2 id="faq-h">Questions</h2>
  <div class="faq">{items}</div>
</section>
"""


def method_html(method: dict) -> str:
    return f"""<section id="method" aria-labelledby="method-h">
  <h2 id="method-h">Method</h2>
  <p class="label-strong">{esc(method['label'])}</p>
  <dl class="method">
    <div><dt>Net-effective rent</dt><dd>{esc(method.get('net_effective_formula', ''))}</dd></div>
    <div><dt>Concession value</dt><dd>{esc(method.get('concession_value', ''))}</dd></div>
    <div><dt>Already-net rates</dt><dd>{esc(method.get('already_net', ''))}</dd></div>
    <div><dt>Concession share</dt><dd>{esc(method.get('concession_share_basis', ''))}</dd></div>
    <div><dt>Bedroom medians</dt><dd>Published only from {esc(method.get('bedroom_floor_n', 20))} or more floor plans. {esc(method.get('per_bed_filter', ''))}</dd></div>
    <div><dt>Rent cuts</dt><dd>{esc(method.get('rent_cuts', ''))}</dd></div>
  </dl>
</section>
"""


def footer(snap: dict) -> str:
    return f"""<footer class="foot">
  <div class="wrap">
    <p>Sources: publicly advertised listings on Apartments.com and Zumper, captured <time datetime="{snap['snapshot_date']}">{fmt_date(snap['snapshot_date'])}</time> through the Listingrail API. Not affiliated with either site. {esc(snap['method']['label'])}</p>
    <p><a href="{BASE}">All metros</a> · <a href="/feeds/">Data feeds</a> · <a href="/">Apify actor catalog</a></p>
  </div>
</footer>
<script type="module" src="{BASE}calc.mjs"></script>
</body>
</html>
"""


# ------------------------------------------------------------------ pages
def dataset_ld(name: str, desc: str, url: str, snap: dict, csv: str | None, place: str | None, n: int) -> dict:
    o = {
        "@context": "https://schema.org", "@type": "Dataset", "name": name, "description": desc, "url": url,
        "dateModified": snap["snapshot_date"], "temporalCoverage": snap["snapshot_date"],
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "Listingrail", "url": "https://listingrail.com/"},
        "measurementTechnique": "Publicly advertised asking rents and move-in specials; strict concession regex; "
                                "medians from 20 or more floor plans",
        "variableMeasured": ["concession share", "headline asking rent", "net-effective asking rent",
                             "rent per square foot", "weeks free"],
        "size": f"{n} priced listings",
        "keywords": ["apartment concessions", "net effective rent", "asking rent", "rent drops"],
    }
    if place:
        o["spatialCoverage"] = {"@type": "Place", "name": place}
    else:
        o["spatialCoverage"] = {"@type": "Place", "name": "United States"}
    if csv:
        o["distribution"] = [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": SITE + csv}]
    return o


def faq_ld(qa) -> dict:
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]}


def crumbs_ld(items: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": SITE + u}
                                for i, (n, u) in enumerate(items)]}


def neighbours(m: dict, metros: list[dict], k: int = 6) -> list[dict]:
    same = [x for x in metros if x["state"] == m["state"] and x["slug"] != m["slug"]]
    rest = [x for x in metros if x["state"] != m["state"] and x["slug"] != m["slug"]]
    idx = {x["slug"]: i for i, x in enumerate(metros)}
    rest.sort(key=lambda x: abs(idx[x["slug"]] - idx[m["slug"]]))
    return (same + rest)[:k]


def metro_page(m: dict, snap: dict) -> str:
    d = snap["snapshot_date"]
    city = m["label"]
    c = m["concessions"]
    one = m["bedrooms"].get("1", {})
    year = date.fromisoformat(d).year
    title = f"{city} apartment concessions & net-effective rent ({fmt_date(d)})"
    if len(title) > 70:
        title = f"{city} apartment concessions & net-effective rent {year}"
    bits = []
    if c.get("share_pct") is not None:
        bits.append(f"{pct(c['share_pct'])} of {c['n_properties']} properties advertise move-in specials")
    if one.get("published"):
        bits.append(f"1BR {usd(one['headline_median'])} asking, {usd(one['net_effective_median'])} net-effective")
    desc = f"{city}, {fmt_date(d)}: " + "; ".join(bits) + ". Studio-3BR medians, free 25-row CSV, calculator."
    path = f"{BASE}{m['slug']}/"
    summary = summary_text(m, d)
    qa = metro_faq(m, d)
    csv = f"{CSV_BASE}{m['slug']}.csv"
    jsonld = [
        dataset_ld(f"{city} apartment asking rents and move-in concessions, {d}", summary, SITE + path, snap, csv,
                   city, m["n_priced"]),
        faq_ld(qa),
        crumbs_ld([("Rent Drops", BASE), (city, path)]),
    ]
    presets = []
    if one.get("published"):
        presets.append((f"{city} 1BR median", {"asking": round(one["headline_median"]), "kind": "weeks",
                                               "amount": wk(c["median_free_weeks"]) if c.get("median_free_weeks") else 0}))
    for b in ("0", "2"):
        e = m["bedrooms"][b]
        if e.get("published"):
            presets.append((f"{e['label']} median", {"asking": round(e["headline_median"])}))
    preset = {}
    if one.get("published"):
        preset["asking"] = round(one["headline_median"])
    if c.get("median_free_weeks"):
        preset["amount"] = wk(c["median_free_weeks"])
    near = neighbours(m, snap["metros"])
    near_html = "".join(
        f'<li><a href="{BASE}{x["slug"]}/">{esc(x["label"])}</a>'
        + (f' <span>{pct(x["concessions"]["share_pct"])}</span>' if x["concessions"].get("share_pct") is not None else "")
        + "</li>" for x in near)
    lead_facts = []
    if c.get("share_pct") is not None:
        lead_facts.append(f"<div><dt>With a concrete special</dt><dd>{pct(c['share_pct'])}</dd></div>")
    if one.get("published"):
        lead_facts.append(f"<div><dt>1BR net-effective</dt><dd>{usd(one['net_effective_median'])}</dd></div>")
    if c.get("median_free_weeks"):
        lead_facts.append(f"<div><dt>Median free time</dt><dd>{wk(c['median_free_weeks'])} wk</dd></div>")
    lead_facts.append(f"<div><dt>Priced listings</dt><dd>{m['n_priced']:,}</dd></div>")
    return (
        head(title, desc, path, jsonld, d)
        + masthead([("All metros", BASE), (city, None)], d)
        + f"""<main id="main" class="wrap">
<article>
<header class="lead">
  <h1>{esc(city)} apartment concessions and net-effective rents</h1>
  <p class="dateline">Snapshot <time datetime="{d}">{fmt_date(d)}</time> · {m['n_apartments_com']} Apartments.com properties ({m.get('n_floor_plans', 0):,} floor plans) and {m['n_zumper']} Zumper listings · publicly advertised asking rents</p>
  <div class="lead-grid">
    <p class="answer" id="summary">{esc(summary)}</p>
    <dl class="lead-facts">{''.join(lead_facts)}</dl>
  </div>
</header>
{bedroom_section(m)}
{concession_section(m)}
{calculator(preset, presets, f'Net-effective rent calculator for {city}', 'Type the advertised rent and special from any listing. Prefilled with this metro’s 1BR median asking rent and the median free time among properties that offer one, so it shows a typical deal rather than the metro-wide median above.')}
{cuts_section(m, d)}
{spread_section(m)}
{sample_section(m)}
{cta_section(m['slug'])}
{reproduce_section(m)}
{method_html(snap['method'])}
{faq_html(qa)}
<nav class="near" aria-labelledby="near-h"><h2 id="near-h">Nearby and similar metros</h2><ul>{near_html}</ul><p><a href="{BASE}">All {len(snap['metros'])} metros</a></p></nav>
</article>
</main>
"""
        + footer(snap)
    )


def hub_page(snap: dict) -> str:
    d = snap["snapshot_date"]
    ms = snap["metros"]
    summary = hub_summary(snap)
    qa = hub_faq(snap)
    title = f"US apartment concessions & net-effective rents: {len(ms)} metros ({fmt_date(d)})"
    desc = (f"Weekly benchmark of move-in specials and net-effective asking rents in {len(ms)} US metros from "
            f"Apartments.com and Zumper. Studio-3BR medians, free CSV samples, calculator.")
    jsonld = [dataset_ld(f"US metro apartment concessions and net-effective asking rents, {d}", summary, SITE + BASE,
                         snap, None, None, sum(m["n_priced"] for m in ms)),
              faq_ld(qa), crumbs_ld([("Rent Drops", BASE)])]
    rows = []
    for m in sorted(ms, key=lambda m: -(m["concessions"].get("share_pct") or -1)):
        c = m["concessions"]
        one = m["bedrooms"].get("1", {})
        sh = c.get("share_pct")
        fw = c.get("median_free_weeks")
        oh = one.get("headline_median") if one.get("published") else None
        on = one.get("net_effective_median") if one.get("published") else None
        na = '<span class="na">n/a</span>'
        rows.append(
            f'<tr data-metro="{esc(m["label"])}" data-share="{sh if sh is not None else ""}" data-weeks="{fw or ""}" '
            f'data-head="{oh or ""}" data-net="{on or ""}" data-n="{m["n_priced"]}">'
            f'<th scope="row"><a href="{BASE}{m["slug"]}/">{esc(m["label"])}</a></th>'
            f'<td class="num">{pct(sh) if sh is not None else na}</td>'
            f'<td class="bar-cell" aria-hidden="true"><span class="mini" style="width:{(sh or 0):.1f}%"></span></td>'
            f'<td class="num">{wk(fw) + " wk" if fw else na}</td>'
            f'<td class="num">{usd(oh) if oh else na}</td>'
            f'<td class="num strong">{usd(on) if on else na}</td>'
            f'<td class="num">{m["n_priced"]:,}</td></tr>')
    sortbtn = lambda key, label, t="num": f'<button type="button" data-key="{key}" data-type="{t}">{label}</button>'  # noqa: E731
    return (
        head(title, desc, BASE, jsonld, d)
        + masthead([("All metros", None)], d)
        + f"""<main id="main" class="wrap">
<header class="lead">
  <h1>Apartment concessions and net-effective rents in {len(ms)} US metros</h1>
  <p class="dateline">Snapshot <time datetime="{d}">{fmt_date(d)}</time> · {sum(m['n_apartments_com'] for m in ms):,} Apartments.com properties and {sum(m['n_zumper'] for m in ms):,} Zumper listings · publicly advertised asking rents · updated weekly</p>
  <p class="answer" id="summary">{esc(summary)}</p>
</header>
<section id="metros" aria-labelledby="metros-h">
  <h2 id="metros-h">All metros</h2>
  <p>Sorted by concession share. Select a column heading to re-sort. 1BR figures are medians of Apartments.com floor plans; n/a means fewer than 20 plans.</p>
  <div class="scroll" tabindex="0" role="region" aria-label="Metro table">
  <table class="hub" data-sortable>
    <thead><tr>
      <th scope="col">{sortbtn('metro', 'Metro', 'text')}</th>
      <th scope="col" class="num" aria-sort="descending">{sortbtn('share', 'With a special')}</th>
      <th scope="col" class="bar-cell"><span class="sr">Share bar</span></th>
      <th scope="col" class="num">{sortbtn('weeks', 'Median free')}</th>
      <th scope="col" class="num">{sortbtn('head', '1BR asking')}</th>
      <th scope="col" class="num">{sortbtn('net', '1BR net-effective')}</th>
      <th scope="col" class="num">{sortbtn('n', 'Listings')}</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  </div>
</section>
{calculator({}, [('6 weeks free', {'kind': 'weeks', 'amount': 6}), ('1 month free', {'kind': 'months', 'amount': 1}), ('$500 off', {'kind': 'dollars', 'amount': 500})], 'Net-effective rent and concession calculator', 'Turn any advertised special into a monthly net-effective rent and a total saving over the lease.')}
<section id="rent-cuts" aria-labelledby="cuts-h">
  <h2 id="cuts-h">30-day asking-rent cuts</h2>
  <p>Rent cuts compare the same listing ids week to week. They appear on each metro page once four weekly snapshots exist{f", from {fmt_date(unlock_date(d, ms[0]['rent_cuts_30d']))}" if not ms[0]['rent_cuts_30d'].get('unlocked') else ''}. Until then no count is published.</p>
</section>
{cta_section('hub')}
{reproduce_section(None)}
{method_html(snap['method'])}
{faq_html(qa)}
</main>
"""
        + footer(snap)
    )


def check_page(page: str) -> None:
    """Red-line guard: no contact data in rendered HTML."""
    text = re.sub(r'<script type="application/ld\+json">.*?</script>', "", page, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    hit = CONTACT_RE.search(text)
    if hit:
        raise SnapshotError(f"contact-like text in page: {hit.group(0)!r}")


def build(snap: dict, out: Path) -> list[Path]:
    validate(snap)
    pages = {out / "index.html": hub_page(snap)}
    for m in snap["metros"]:
        pages[out / m["slug"] / "index.html"] = metro_page(m, snap)
    for p, txt in pages.items():
        check_page(txt)
    keep = {m["slug"] for m in snap["metros"]}
    for p, txt in pages.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt)
    # drop pages of metros that left the roster
    for d in out.iterdir() if out.exists() else []:
        if d.is_dir() and (d / "index.html").is_file() and d.name not in keep and d.name != "fonts":
            (d / "index.html").unlink()
            if not any(d.iterdir()):
                d.rmdir()
    return list(pages)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        snap = load_snapshot(a.snapshot)
        if a.dry_run:
            for m in snap["metros"]:
                summary_text(m, snap["snapshot_date"])
            hub_summary(snap)
            print(f"Dry run: {len(snap['metros']) + 1} pages from {a.snapshot} ({snap['snapshot_date']}), noindex={not INDEX}")
            return 0
        paths = build(snap, a.out)
    except SnapshotError as exc:
        print(f"ERROR: {exc}. Nothing written.", file=sys.stderr)
        return 1
    print(f"Built {len(paths)} pages under {a.out} (snapshot {snap['snapshot_date']}, noindex={not INDEX})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
