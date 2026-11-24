"""Fetch live weekly real-estate snapshots from the Listingrail API for the
Listingrail Rental Yield & Weekly Price-Cut Benchmark Directory (/yield/).

Data-backed only: never invents numbers. Strips agent contact details and raw
portal blobs before writing sanitized market aggregates and 25-row samples into
data/yield-snapshots/latest.json (plus compact id->price history for 30-day
weekly price-cut diffs).

Usage:
    python scripts/fetch_yield_snapshots.py --dry-run
    python scripts/fetch_yield_snapshots.py
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "data" / "yield-snapshots"
HISTORY_DIR = SNAP_DIR / "history"
LATEST_PATH = SNAP_DIR / "latest.json"
DEFAULT_KEY_PATH = Path("/home/paseo/.secrets/listingrail-feed-sample-key.txt")
API_URL = "https://listingrail.com/v1/listings/search"
SQFT_TO_SQM = 0.09290304

# Closing-cost & tax defaults per country (for the client-side net yield calculator)
COUNTRY_META = {
    "es": {
        "name": "Spain",
        "currency": "EUR",
        "symbol": "€",
        "closing_cost_pct": 10.5,
        "closing_note": "ITP transfer tax (6–10% by autonomous community) + notary/registry (~1.5%)",
        "annual_tax_pct": 0.6,
        "mgmt_fee_pct": 8.0,
        "vacancy_pct": 5.0,
        "maintenance_pct": 8.0,
        "unit_label": "m²",
    },
    "it": {
        "name": "Italy",
        "currency": "EUR",
        "symbol": "€",
        "closing_cost_pct": 9.5,
        "closing_note": "Imposta di registro (9% second home on cadastral value) + notary/agency fees",
        "annual_tax_pct": 0.9,
        "mgmt_fee_pct": 8.0,
        "vacancy_pct": 6.0,
        "maintenance_pct": 8.0,
        "unit_label": "m²",
    },
    "pt": {
        "name": "Portugal",
        "currency": "EUR",
        "symbol": "€",
        "closing_cost_pct": 7.5,
        "closing_note": "IMT progressive transfer tax + 0.8% Imposto do Selo + deed/registry",
        "annual_tax_pct": 0.4,
        "mgmt_fee_pct": 8.0,
        "vacancy_pct": 5.0,
        "maintenance_pct": 7.0,
        "unit_label": "m²",
    },
    "us": {
        "name": "United States",
        "currency": "USD",
        "symbol": "$",
        "closing_cost_pct": 3.5,
        "closing_note": "Title insurance, lender origination, transfer & recording fees",
        "annual_tax_pct": 1.4,
        "mgmt_fee_pct": 8.0,
        "vacancy_pct": 6.0,
        "maintenance_pct": 10.0,
        "unit_label": "m²",
    },
}

# Candidate markets for Batch 1 (54 markets across ES, IT, PT, US)
MARKETS = [
    # Spain (Idealista) — 18 markets
    {"country": "es", "slug": "madrid", "label": "Madrid", "region": "Community of Madrid", "sale_source": "idealista", "rent_source": "idealista", "location": "Madrid"},
    {"country": "es", "slug": "madrid-salamanca", "label": "Salamanca, Madrid", "region": "Madrid", "sale_source": "idealista", "rent_source": "idealista", "location": "Salamanca, Madrid"},
    {"country": "es", "slug": "madrid-chamberi", "label": "Chamberí, Madrid", "region": "Madrid", "sale_source": "idealista", "rent_source": "idealista", "location": "Chamberí, Madrid"},
    {"country": "es", "slug": "madrid-chamartin", "label": "Chamartín, Madrid", "region": "Madrid", "sale_source": "idealista", "rent_source": "idealista", "location": "Chamartín, Madrid"},
    {"country": "es", "slug": "madrid-retiro", "label": "Retiro, Madrid", "region": "Madrid", "sale_source": "idealista", "rent_source": "idealista", "location": "Retiro, Madrid"},
    {"country": "es", "slug": "madrid-centro", "label": "Centro, Madrid", "region": "Madrid", "sale_source": "idealista", "rent_source": "idealista", "location": "Centro, Madrid"},
    {"country": "es", "slug": "madrid-tetuan", "label": "Tetuán, Madrid", "region": "Madrid", "sale_source": "idealista", "rent_source": "idealista", "location": "Tetuán, Madrid"},
    {"country": "es", "slug": "barcelona", "label": "Barcelona", "region": "Catalonia", "sale_source": "idealista", "rent_source": "idealista", "location": "Barcelona"},
    {"country": "es", "slug": "barcelona-eixample", "label": "Eixample, Barcelona", "region": "Barcelona", "sale_source": "idealista", "rent_source": "idealista", "location": "Eixample, Barcelona"},
    {"country": "es", "slug": "barcelona-gracia", "label": "Gràcia, Barcelona", "region": "Barcelona", "sale_source": "idealista", "rent_source": "idealista", "location": "Gràcia, Barcelona"},
    {"country": "es", "slug": "barcelona-sarria-sant-gervasi", "label": "Sarrià-Sant Gervasi, Barcelona", "region": "Barcelona", "sale_source": "idealista", "rent_source": "idealista", "location": "Sarrià-Sant Gervasi, Barcelona"},
    {"country": "es", "slug": "valencia", "label": "Valencia", "region": "Valencian Community", "sale_source": "idealista", "rent_source": "idealista", "location": "Valencia"},
    {"country": "es", "slug": "malaga", "label": "Málaga", "region": "Andalusia", "sale_source": "idealista", "rent_source": "idealista", "location": "Málaga"},
    {"country": "es", "slug": "sevilla", "label": "Seville", "region": "Andalusia", "sale_source": "idealista", "rent_source": "idealista", "location": "Sevilla"},
    {"country": "es", "slug": "alicante", "label": "Alicante", "region": "Valencian Community", "sale_source": "idealista", "rent_source": "idealista", "location": "Alicante"},
    {"country": "es", "slug": "palma-de-mallorca", "label": "Palma de Mallorca", "region": "Balearic Islands", "sale_source": "idealista", "rent_source": "idealista", "location": "Palma de Mallorca"},
    {"country": "es", "slug": "bilbao", "label": "Bilbao", "region": "Basque Country", "sale_source": "idealista", "rent_source": "idealista", "location": "Bilbao"},
    {"country": "es", "slug": "zaragoza", "label": "Zaragoza", "region": "Aragon", "sale_source": "idealista", "rent_source": "idealista", "location": "Zaragoza"},
    # Italy (Immobiliare.it) — 12 markets
    {"country": "it", "slug": "milan", "label": "Milan", "region": "Lombardy", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Milano"},
    {"country": "it", "slug": "rome", "label": "Rome", "region": "Lazio", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Roma"},
    {"country": "it", "slug": "turin", "label": "Turin", "region": "Piedmont", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Torino"},
    {"country": "it", "slug": "florence", "label": "Florence", "region": "Tuscany", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Firenze"},
    {"country": "it", "slug": "bologna", "label": "Bologna", "region": "Emilia-Romagna", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Bologna"},
    {"country": "it", "slug": "naples", "label": "Naples", "region": "Campania", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Napoli"},
    {"country": "it", "slug": "genoa", "label": "Genoa", "region": "Liguria", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Genova"},
    {"country": "it", "slug": "palermo", "label": "Palermo", "region": "Sicily", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Palermo"},
    {"country": "it", "slug": "verona", "label": "Verona", "region": "Veneto", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Verona"},
    {"country": "it", "slug": "padua", "label": "Padua", "region": "Veneto", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Padova"},
    {"country": "it", "slug": "bari", "label": "Bari", "region": "Apulia", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Bari"},
    {"country": "it", "slug": "venice", "label": "Venice", "region": "Veneto", "sale_source": "immobiliare", "rent_source": "immobiliare", "location": "Venezia"},
    # Portugal (Imovirtual) — 10 markets
    {"country": "pt", "slug": "lisbon", "label": "Lisbon", "region": "Lisbon District", "sale_source": "imovirtual", "rent_source": "imovirtual", "location": "Lisboa"},
    {"country": "pt", "slug": "porto", "label": "Porto", "region": "Porto District", "sale_source": "imovirtual", "rent_source": "imovirtual", "location": "Porto"},
    {"country": "pt", "slug": "cascais", "label": "Cascais", "region": "Lisbon District", "sale_source": "imovirtual", "rent_source": "imovirtual", "location": "Cascais"},
    {"country": "pt", "slug": "braga", "label": "Braga", "region": "Braga District", "sale_source": "imovirtual", "rent_source": "imovirtual", "location": "Braga"},
    {"country": "pt", "slug": "coimbra", "label": "Coimbra", "region": "Coimbra District", "sale_source": "imovirtual", "rent_source": "imovirtual", "location": "Coimbra"},
    {"country": "pt", "slug": "setubal", "label": "Setúbal", "region": "Setúbal District", "sale_source": "imovirtual", "rent_source": "imovirtual", "location": "Setúbal"},
    {"country": "pt", "slug": "faro", "label": "Faro", "region": "Algarve", "sale_source": "imovirtual", "rent_source": "imovirtual", "location": "Faro"},
    {"country": "pt", "slug": "aveiro", "label": "Aveiro", "region": "Aveiro District", "sale_source": "imovirtual", "rent_source": "imovirtual", "location": "Aveiro"},
    {"country": "pt", "slug": "funchal", "label": "Funchal", "region": "Madeira", "sale_source": "imovirtual", "rent_source": "imovirtual", "location": "Funchal"},
    {"country": "pt", "slug": "vila-nova-de-gaia", "label": "Vila Nova de Gaia", "region": "Porto District", "sale_source": "imovirtual", "rent_source": "imovirtual", "location": "Vila Nova de Gaia"},
    # United States (Redfin + Redfin Rentals) — 14 markets
    {"country": "us", "slug": "austin-tx", "label": "Austin, TX", "region": "Texas", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Austin, TX"},
    {"country": "us", "slug": "miami-fl", "label": "Miami, FL", "region": "Florida", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Miami, FL"},
    {"country": "us", "slug": "tampa-fl", "label": "Tampa, FL", "region": "Florida", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Tampa, FL"},
    {"country": "us", "slug": "orlando-fl", "label": "Orlando, FL", "region": "Florida", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Orlando, FL"},
    {"country": "us", "slug": "dallas-tx", "label": "Dallas, TX", "region": "Texas", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Dallas, TX"},
    {"country": "us", "slug": "houston-tx", "label": "Houston, TX", "region": "Texas", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Houston, TX"},
    {"country": "us", "slug": "phoenix-az", "label": "Phoenix, AZ", "region": "Arizona", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Phoenix, AZ"},
    {"country": "us", "slug": "atlanta-ga", "label": "Atlanta, GA", "region": "Georgia", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Atlanta, GA"},
    {"country": "us", "slug": "charlotte-nc", "label": "Charlotte, NC", "region": "North Carolina", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Charlotte, NC"},
    {"country": "us", "slug": "nashville-tn", "label": "Nashville, TN", "region": "Tennessee", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Nashville, TN"},
    {"country": "us", "slug": "denver-co", "label": "Denver, CO", "region": "Colorado", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Denver, CO"},
    {"country": "us", "slug": "chicago-il", "label": "Chicago, IL", "region": "Illinois", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Chicago, IL"},
    {"country": "us", "slug": "raleigh-nc", "label": "Raleigh, NC", "region": "North Carolina", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "Raleigh, NC"},
    {"country": "us", "slug": "san-diego-ca", "label": "San Diego, CA", "region": "California", "sale_source": "redfin", "rent_source": "redfin-rentals", "location": "San Diego, CA"},
]


def load_key() -> str:
    k = os.environ.get("LISTINGRAIL_API_KEY", "").strip()
    if k:
        return k
    if DEFAULT_KEY_PATH.is_file():
        return DEFAULT_KEY_PATH.read_text().strip()
    raise RuntimeError("No LISTINGRAIL_API_KEY and default key file not found")


def api_search(key: str, source: str, location: str, ltype: str, limit: int = 100) -> list[dict]:
    payload = json.dumps({"source": source, "location": location, "type": ltype, "limit": limit}).encode()
    for attempt in range(2):
        req = urllib.request.Request(
            API_URL,
            data=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                return data.get("listings") or []
        except Exception as exc:
            if attempt == 0:
                time.sleep(2.5)
                continue
            print(f"WARN {source} {location} {ltype}: {exc}", file=sys.stderr)
            return []
    return []


def to_sqm(area: float | int | None, unit: str | None) -> float | None:
    if not area or area <= 0:
        return None
    u = (unit or "sqm").lower()
    if u in ("sqft", "sq_ft", "ft2"):
        val = float(area) * SQFT_TO_SQM
    else:
        val = float(area)
    if val < 10 or val > 2500:
        return None
    return round(val, 1)


def parse_dom(row: dict, now_utc: datetime) -> int | None:
    raw = row.get("raw") or {}
    dom = raw.get("days_on_market")
    if isinstance(dom, (int, float)) and 0 <= dom <= 1500:
        return int(dom)
    ts = row.get("listed_at") or raw.get("date_created")
    if isinstance(ts, str) and len(ts) >= 10:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = (now_utc - dt).days
            if 0 <= days <= 1500:
                return int(days)
        except ValueError:
            pass
    return None


def parse_drop_pct(row: dict) -> float | None:
    raw = row.get("raw") or {}
    pct = raw.get("price_drop_percentage")
    if isinstance(pct, (int, float)) and 0 < pct < 80:
        return round(float(pct), 1)
    return None


def parse_subarea(row: dict, country: str) -> str | None:
    raw = row.get("raw") or {}
    for k in ("neighborhood", "district"):
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()[:48]
    if country == "us" and row.get("postal_code"):
        return f"ZIP {str(row['postal_code']).strip()}"
    addr = row.get("address") or ""
    if "," in addr:
        parts = [p.strip() for p in addr.split(",") if p.strip()]
        if len(parts) >= 2 and len(parts[-2]) <= 40:
            return parts[-2]
    return None


def clean_row(row: dict, ltype: str, country: str, now_utc: datetime) -> dict | None:
    price = row.get("price")
    if not isinstance(price, (int, float)) or price <= 0:
        return None
    # Guard against obvious outlier/garbage prices
    if ltype == "sale" and (price < 20000 or price > 50000000):
        return None
    if ltype == "rent" and (price < 200 or price > 50000):
        return None
    sqm = to_sqm(row.get("area"), row.get("area_unit"))
    beds = row.get("beds")
    if beds is None and isinstance(row.get("rooms"), int):
        beds = max(1, row["rooms"] - 1) if row["rooms"] > 1 else 1
    return {
        "id": str(row.get("id") or ""),
        "type": ltype,
        "source": str(row.get("source") or ""),
        "price": round(float(price), 2),
        "currency": str(row.get("currency") or COUNTRY_META[country]["currency"]),
        "area_sqm": sqm,
        "price_per_sqm": round(float(price) / sqm, 2) if sqm else None,
        "beds": int(beds) if isinstance(beds, (int, float)) and 0 <= beds <= 12 else None,
        "baths": int(row["baths"]) if isinstance(row.get("baths"), (int, float)) and 0 <= row["baths"] <= 12 else None,
        "property_type": str(row.get("property_type") or "residential").strip()[:32],
        "subarea": parse_subarea(row, country),
        "dom_days": parse_dom(row, now_utc),
        "price_drop_pct": parse_drop_pct(row),
        "listed_at": str(row["listed_at"])[:10] if row.get("listed_at") else None,
        "url": str(row.get("url") or ""),
    }


def quantiles(vals: list[float]) -> dict:
    if not vals:
        return {}
    s = sorted(vals)
    n = len(s)
    p25 = s[max(0, int(0.25 * (n - 1)))]
    p50 = statistics.median(s)
    p75 = s[min(n - 1, int(0.75 * (n - 1)))]
    return {
        "n": n,
        "min": round(s[0], 2),
        "p25": round(p25, 2),
        "median": round(p50, 2),
        "p75": round(p75, 2),
        "max": round(s[-1], 2),
    }


def summarize_side(rows: list[dict]) -> dict:
    prices = [r["price"] for r in rows]
    pps = [r["price_per_sqm"] for r in rows if r["price_per_sqm"]]
    areas = [r["area_sqm"] for r in rows if r["area_sqm"]]
    doms = [r["dom_days"] for r in rows if r["dom_days"] is not None]
    drops = [r["price_drop_pct"] for r in rows if r["price_drop_pct"] is not None]

    by_beds: dict[str, dict] = {}
    bed_buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["beds"] is not None:
            k = "4+" if r["beds"] >= 4 else str(r["beds"])
            bed_buckets[k].append(r)
    for k in ("1", "2", "3", "4+"):
        b = bed_buckets.get(k) or []
        if len(b) >= 3:
            bpps = [x["price_per_sqm"] for x in b if x["price_per_sqm"]]
            by_beds[k] = {
                "n": len(b),
                "median_price": round(statistics.median([x["price"] for x in b]), 2),
                "median_price_sqm": round(statistics.median(bpps), 2) if bpps else None,
                "median_area_sqm": round(statistics.median([x["area_sqm"] for x in b if x["area_sqm"]]), 1)
                if any(x["area_sqm"] for x in b) else None,
            }

    sub_buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["subarea"]:
            sub_buckets[r["subarea"]].append(r)
    top_subareas = []
    for name, items in sorted(sub_buckets.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(items) < 2:
            continue
        spps = [x["price_per_sqm"] for x in items if x["price_per_sqm"]]
        top_subareas.append({
            "name": name,
            "n": len(items),
            "median_price": round(statistics.median([x["price"] for x in items]), 2),
            "median_price_sqm": round(statistics.median(spps), 2) if spps else None,
        })
        if len(top_subareas) >= 8:
            break

    ptypes = Counter(r["property_type"] for r in rows).most_common(5)
    return {
        "n_priced": len(rows),
        "n_with_area": len(pps),
        "price": quantiles(prices),
        "price_per_sqm": quantiles(pps),
        "area_sqm": quantiles(areas),
        "dom": quantiles([float(d) for d in doms]) if len(doms) >= 5 else None,
        "portal_price_cuts": {
            "count": len(drops),
            "share_pct": round(len(drops) / len(rows) * 100, 1) if rows else 0.0,
            "median_cut_pct": round(statistics.median(drops), 1) if drops else None,
            "max_cut_pct": round(max(drops), 1) if drops else None,
        } if drops else None,
        "by_beds": by_beds,
        "top_subareas": top_subareas,
        "property_types": [{"type": t, "count": c} for t, c in ptypes],
    }


def load_prior_prices(country: str, slug: str, today_iso: str) -> dict[str, float]:
    """Read earlier weekly snapshot files (up to 30 days back) to compute real price-cut diffs."""
    prior: dict[str, float] = {}
    if not HISTORY_DIR.is_dir():
        return prior
    for p in sorted(HISTORY_DIR.glob("*.json")):
        if p.stem >= today_iso:
            continue
        try:
            d = json.loads(p.read_text())
            m = d.get(f"{country}/{slug}") or {}
            for lid, pr in m.items():
                if lid not in prior or pr > prior[lid]:
                    prior[lid] = float(pr)
        except Exception:
            continue
    return prior


def fetch_one(key: str, m: dict, limit: int, now_utc: datetime, today_iso: str) -> tuple[dict, dict[str, float]]:
    sale_raw = api_search(key, m["sale_source"], m["location"], "sale", limit=limit)
    rent_raw = api_search(key, m["rent_source"], m["location"], "rent", limit=limit)

    sale_rows = [c for r in sale_raw if (c := clean_row(r, "sale", m["country"], now_utc))]
    rent_rows = [c for r in rent_raw if (c := clean_row(r, "rent", m["country"], now_utc))]

    sale_sum = summarize_side(sale_rows)
    rent_sum = summarize_side(rent_rows)

    # Compute real yields (area-normalized and headline)
    s_pps = (sale_sum["price_per_sqm"] or {}).get("median")
    r_pps = (rent_sum["price_per_sqm"] or {}).get("median")
    s_med = (sale_sum["price"] or {}).get("median")
    r_med = (rent_sum["price"] or {}).get("median")

    gross_yield_sqm = round((r_pps * 12.0 / s_pps) * 100.0, 2) if (s_pps and r_pps) else None
    gross_yield_headline = round((r_med * 12.0 / s_med) * 100.0, 2) if (s_med and r_med) else None
    price_to_rent = round(s_med / (r_med * 12.0), 1) if (s_med and r_med) else None

    # Compare against prior weekly snapshots for 30-day diff price cuts
    prior = load_prior_prices(m["country"], m["slug"], today_iso)
    diff_cuts = []
    if prior:
        for r in sale_rows:
            old = prior.get(r["id"])
            if old and r["price"] < old * 0.995:
                diff_cuts.append(round((old - r["price"]) / old * 100.0, 1))

    # Build deterministic 25-row sanitized CSV sample (13 sale + 12 rent)
    sale_sorted = sorted(sale_rows, key=lambda x: (x["price_per_sqm"] is None, x["price_per_sqm"] or x["price"], x["id"]))
    rent_sorted = sorted(rent_rows, key=lambda x: (x["price_per_sqm"] is None, x["price_per_sqm"] or x["price"], x["id"]))
    sample_rows = sale_sorted[:13] + rent_sorted[:12]

    rec = {
        **m,
        "snapshot_date": today_iso,
        "currency": COUNTRY_META[m["country"]]["currency"],
        "symbol": COUNTRY_META[m["country"]]["symbol"],
        "sale": sale_sum,
        "rent": rent_sum,
        "gross_yield_pct": gross_yield_sqm,
        "headline_yield_pct": gross_yield_headline,
        "price_to_rent_years": price_to_rent,
        "snapshot_diff_cuts": {
            "prior_snapshots_used": bool(prior),
            "count": len(diff_cuts),
            "median_cut_pct": round(statistics.median(diff_cuts), 1) if diff_cuts else None,
        },
        "sample_rows": sample_rows,
    }
    id_prices = {r["id"]: r["price"] for r in sale_rows if r["id"]}
    return rec, id_prices


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Print plan without calling Listingrail API")
    ap.add_argument("--limit", type=int, default=100, help="Listings per sale/rent query (default 100)")
    ap.add_argument("--workers", type=int, default=4, help="Concurrent API requests (default 4)")
    ap.add_argument("--min-rows", type=int, default=40, help="Minimum priced rows on each side to keep a market")
    args = ap.parse_args()

    if args.dry_run:
        print(f"Dry run: {len(MARKETS)} candidate markets, {len(MARKETS)*2} API searches, max {len(MARKETS)*2*args.limit} credits")
        for m in MARKETS:
            print(f"  /yield/{m['country']}/{m['slug']}/  ({m['sale_source']} / {m['rent_source']} | {m['location']})")
        return 0

    key = load_key()
    now_utc = datetime.now(timezone.utc)
    today_iso = now_utc.date().isoformat()
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    history_prices: dict[str, dict[str, float]] = {}
    t0 = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(fetch_one, key, m, args.limit, now_utc, today_iso): m for m in MARKETS}
        for fut in concurrent.futures.as_completed(futs):
            m = futs[fut]
            rec, id_prices = fut.result()
            sp, rp = rec["sale"]["n_priced"], rec["rent"]["n_priced"]
            sa, ra = rec["sale"]["n_with_area"], rec["rent"]["n_with_area"]
            ok = sp >= args.min_rows and rp >= args.min_rows and sa >= 25 and ra >= 25 and rec["gross_yield_pct"] is not None
            status = "KEEP" if ok else "DROP"
            print(f"[{status}] {m['country']}/{m['slug']:30s} sale={sp:3d}({sa:3d}m2) rent={rp:3d}({ra:3d}m2) yield={rec['gross_yield_pct']}%", flush=True)
            if ok:
                results.append(rec)
                history_prices[f"{m['country']}/{m['slug']}"] = id_prices

    # Sort deterministically by country, then gross yield desc
    order = {"es": 0, "it": 1, "pt": 2, "us": 3}
    results.sort(key=lambda r: (order.get(r["country"], 9), -(r["gross_yield_pct"] or 0), r["slug"]))

    payload = {
        "generated_at": now_utc.isoformat(),
        "snapshot_date": today_iso,
        "min_rows_floor": args.min_rows,
        "country_meta": COUNTRY_META,
        "markets": results,
    }
    LATEST_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    (HISTORY_DIR / f"{today_iso}.json").write_text(json.dumps(history_prices, separators=(",", ":")) + "\n")
    print(f"Done in {time.time()-t0:.1f}s: kept {len(results)}/{len(MARKETS)} markets -> {LATEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
