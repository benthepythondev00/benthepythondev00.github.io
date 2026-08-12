#!/usr/bin/env python3
"""Build public Actor catalog JSON from Apify Store API (auto, no manual cards)."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

API = "https://api.apify.com/v2"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "actors.json"
USERNAME = os.environ.get("APIFY_USER", "benthepythondev")

CHIP_RULES: list[tuple[str, set[str], list[str]]] = [
    ("Jobs & hiring", {"JOBS"}, ["job", "hiring", "greenhouse", "lever", "workday", "remotive", "ats", "arbeitsagentur"]),
    ("Real estate & rentals", {"REAL_ESTATE", "TRAVEL"}, ["rent", "zumper", "craigslist", "redfin", "immowelt", "wg-gesucht", "hotpads", "casa", "apartment", " immobil"]),
    ("Lead gen", {"LEAD_GENERATION"}, ["email", "lead", "contact", "gelbe", "yelp", "maps", "domain-intelligence", "ads-txt"]),
    ("E‑commerce", {"ECOMMERCE", "SHOPPING"}, ["shopify", "amazon", "ebay", "bestbuy", "price", "deal", "vinted", "grailed", "mydealz", "geizhals"]),
    ("Social & Reddit", {"SOCIAL_MEDIA"}, ["reddit", "tiktok", "instagram", "twitter", "youtube", "hacker-news", "devto", "podcast"]),
    ("Finance", {"FINANCE", "CRYPTO"}, ["finance", "yahoo", "stock", "crypto", "forex", "sec-", "coingecko", "edgar"]),
    ("Research & open data", {"OPEN_SOURCE", "NEWS"}, ["arxiv", "pubmed", "openalex", "fda", "nasa", "noaa", "congress", "federal", "open-food", "osm", "earthquake"]),
]


def chip_for(actor: dict) -> str:
    cats = {c.upper() for c in (actor.get("categories") or [])}
    blob = f"{actor.get('name','')} {actor.get('title','')}".lower()
    for chip, cat_keys, kws in CHIP_RULES:
        if cats & cat_keys:
            return chip
        if any(k in blob for k in kws):
            return chip
    return "Other"


def one_liner(actor: dict) -> str:
    text = (actor.get("seoDescription") or actor.get("description") or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > 120:
        text = text[:117].rstrip() + "…"
    return text


def success_rate(stats: dict) -> float | None:
    pr = (stats or {}).get("publicActorRunStats30Days") or {}
    total = pr.get("TOTAL") or 0
    if not total:
        return None
    ok = pr.get("SUCCEEDED") or 0
    return round(100.0 * ok / total, 2)


def fetch_token() -> str:
    tok = os.environ.get("APIFY_TOKEN")
    if tok:
        return tok
    auth = Path.home() / ".apify" / "auth.json"
    if auth.exists():
        data = json.loads(auth.read_text())
        return data.get("token") or data.get("id") or ""
    raise SystemExit("APIFY_TOKEN missing and ~/.apify/auth.json not found")


def list_store_actors(client: httpx.Client, token: str) -> list[dict]:
    items: list[dict] = []
    offset = 0
    limit = 100
    while True:
        r = client.get(
            f"{API}/store",
            headers={"Authorization": f"Bearer {token}"},
            params={"username": USERNAME, "limit": limit, "offset": offset},
            timeout=90,
        )
        r.raise_for_status()
        payload = r.json()["data"]
        batch = payload.get("items") or []
        if not batch:
            break
        items.extend(batch)
        offset += len(batch)
        total = payload.get("total") or offset
        if offset >= total:
            break
    return items


def main() -> None:
    token = fetch_token()
    with httpx.Client() as client:
        actors = list_store_actors(client, token)
    catalog = []
    for a in actors:
        if (a.get("username") or "") != USERNAME:
            continue
        # skip maintenance/deprecated notices when present
        notice = (a.get("notice") or "NONE").upper()
        if notice in {"DEPRECATED", "DELETED"}:
            continue
        stats = a.get("stats") or {}
        name = a.get("name") or ""
        catalog.append(
            {
                "name": name,
                "title": a.get("title") or name,
                "categories": a.get("categories") or [],
                "chip": chip_for(a),
                "users30d": stats.get("totalUsers30Days") or 0,
                "successRate30d": success_rate(stats),
                "storeUrl": f"https://apify.com/{USERNAME}/{name}?utm_source=catalog&utm_medium=site",
                "oneLiner": one_liner(a),
                "iconUrl": a.get("pictureUrl") or None,
            }
        )
    # Prefer unique actor names (Store is already unique); drop near-dupe titles
    # keeping the higher users30d when titles normalize equal.
    def _norm_title(s: str) -> str:
        s = (s or "").lower()
        s = re.sub(r"[^a-z0-9]+", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    by_name = {}
    for row in catalog:
        prev = by_name.get(row["name"])
        if prev is None or (row["users30d"] or 0) >= (prev["users30d"] or 0):
            by_name[row["name"]] = row
    catalog = list(by_name.values())

    by_title = {}
    for row in catalog:
        key = _norm_title(row.get("title") or row.get("name"))
        prev = by_title.get(key)
        if prev is None or (row["users30d"] or 0) > (prev["users30d"] or 0):
            by_title[key] = row
    catalog = list(by_title.values())

    catalog.sort(key=lambda x: (-(x["users30d"] or 0), (x["title"] or "").lower()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(catalog),
        "chips": [
            "All",
            "Jobs & hiring",
            "Real estate & rentals",
            "Lead gen",
            "E‑commerce",
            "Social & Reddit",
            "Finance",
            "Research & open data",
            "Other",
        ],
        "actors": catalog,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {OUT} ({len(catalog)} public actors)", file=sys.stderr)


if __name__ == "__main__":
    main()
