#!/usr/bin/env python3
"""Render the data-driven blocks of index.html as static HTML, so crawlers see them without JavaScript.

Fills the regions between <!-- gen:NAME:start --> and <!-- gen:NAME:end --> markers:
  yield          every market in yield/summary.csv, grouped by country, with gross yield and snapshot date
  reddit         every sample page under data/reddit-archive-scraper/ (title from its <title>)
  catalog-intro  actor count and sync date from data/actors.json
  catalog        the 48 most used actors from data/actors.json as plain cards (JS replaces them on load)

Usage: python scripts/build_home_hubs.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
SUMMARY = ROOT / "yield" / "summary.csv"
ACTORS = ROOT / "data" / "actors.json"
REDDIT = ROOT / "data" / "reddit-archive-scraper"
BASE = "https://benthepythondev00.github.io/"
TOP = 48
COUNTRIES = {"ES": "Spain", "IT": "Italy", "PT": "Portugal", "US": "United States"}

esc = lambda s: html.escape(str(s), quote=True)  # noqa: E731


def rel(url: str) -> str:
    return "./" + url[len(BASE):] if url.startswith(BASE) else url


def block_yield() -> str:
    rows = list(csv.DictReader(SUMMARY.open(encoding="utf-8")))
    if not rows:
        return ""
    date = max(r["snapshot_date"] for r in rows)
    listings = sum(int(r["sale_n"] or 0) + int(r["rent_n"] or 0) for r in rows)
    out = [f'<p class="facts">{len(rows)} markets · {listings:,} listings · snapshot {esc(date)} · '
           f'<a href="./yield/summary.csv">summary.csv</a></p>', '<div class="markets">']
    for cc, name in COUNTRIES.items():
        grp = [r for r in rows if r["country"] == cc]
        if not grp:
            continue
        grp.sort(key=lambda r: (-float(r["gross_yield_pct"] or 0), r["market"]))
        out.append(f'  <div class="country"><h4>{esc(name)} · {len(grp)} markets</h4><ul>')
        for r in grp:
            y = f'{float(r["gross_yield_pct"]):.2f}%' if r["gross_yield_pct"] else "n/a"
            out.append(f'    <li class="mk"><a href="{esc(rel(r["page_url"]))}">{esc(r["market"])} rental yield</a>'
                       f'<b>{y}</b></li>')
        out.append("  </ul></div>")
    out.append("</div>")
    return "\n".join(out)


def block_reddit() -> str:
    pages = sorted(p for p in REDDIT.rglob("index.html"))
    items = []
    for p in pages:
        m = re.search(r"<title>(.*?)</title>", p.read_text(encoding="utf-8"), re.S)
        title = html.unescape(m.group(1).strip()) if m else p.parent.name
        href = "./" + p.parent.relative_to(ROOT).as_posix() + "/"
        items.append((0 if p.parent == REDDIT else 1, href, title))
    items.sort()
    lines = ['<ul class="links">'] + [f'  <li><a href="{esc(h)}">{esc(t)}</a></li>' for _, h, t in items] + ["</ul>"]
    return "\n".join(lines)


def load_actors() -> dict:
    return json.loads(ACTORS.read_text(encoding="utf-8"))


def block_catalog_intro(d: dict) -> str:
    n = d.get("count") or len(d.get("actors", []))
    chips = [c for c in d.get("chips", []) if c != "All"]
    synced = str(d.get("generatedAt", ""))[:10]
    return (f'<p>{n} public scrapers on the Apify Store, grouped into {esc(", ".join(chips[:-1]))} and {esc(chips[-1] if chips else "")}. '
            f'The {TOP} most used are listed below as plain links (catalog synced {esc(synced)}); search, filters and the rest load with JavaScript.</p>'
            if chips else f'<p>{n} public scrapers on the Apify Store.</p>')


def block_catalog(d: dict) -> str:
    actors = sorted(d.get("actors", []), key=lambda a: (-(a.get("users30d") or 0), a.get("name", "")))[:TOP]
    cards = []
    for a in actors:
        icon = (f'<img src="{esc(a["iconUrl"])}" alt="" loading="lazy" width="36" height="36" />' if a.get("iconUrl")
                else '<div style="width:36px;height:36px;border-radius:8px;background:#101a2b;flex:none"></div>')
        cards.append(
            '<article class="card">'
            f'<div class="card-top">{icon}<h3>{esc(a.get("title") or a.get("name"))}</h3></div>'
            f'<p>{esc(a.get("oneLiner") or "")}</p>'
            f'<a class="cta" href="{esc(a.get("storeUrl", ""))}" target="_blank" rel="noopener">View on Apify →</a>'
            '</article>')
    return "\n".join(cards)


def fill(src: str, name: str, body: str) -> str:
    pat = re.compile(rf"(<!-- gen:{re.escape(name)}:start -->)(.*?)(\n[ \t]*<!-- gen:{re.escape(name)}:end -->)", re.S)
    if not pat.search(src):
        raise SystemExit(f"marker gen:{name} missing in index.html")
    return pat.sub(lambda m: m.group(1) + "\n" + body + m.group(3), src, count=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    d = load_actors()
    src = INDEX.read_text(encoding="utf-8")
    new = src
    for name, body in [("yield", block_yield()), ("reddit", block_reddit()),
                       ("catalog-intro", block_catalog_intro(d)), ("catalog", block_catalog(d))]:
        new = fill(new, name, body)
        print(f"gen:{name}: {body.count('<a ')} links, {len(body):,} bytes")
    text = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "", new, flags=re.S)
    words = len(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())
    print(f"static words in index.html: {words}")
    if new == src:
        print("index.html unchanged")
    elif a.dry_run:
        print("dry run: index.html would change (not written)")
    else:
        INDEX.write_text(new, encoding="utf-8")
        print("index.html written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
