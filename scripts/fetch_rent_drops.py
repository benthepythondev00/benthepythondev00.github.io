"""Weekly 50-metro US apartment concession & rent-drop snapshot for /rent-drops/.

Queries the Listingrail API (source=apartments-com and source=zumper, type=rent,
limit=100) for a fixed, ordered list of candidate US metros, keeps the first 50 with
>= 60 priced listings across both portals, and writes:

  data/rent-drops/latest.json            sanitized metro aggregates + 25-row samples
  data/rent-drops/history/<date>.json    listing id -> asking rent (ids and numbers only)
  data/rent-drops/samples/<slug>.csv     25-row sanitized CSV sample per metro

Nothing raw is written: rows are rebuilt from named fields (scripts/rent_drops_lib.py).
A failed API call aborts the whole run (exit 1) instead of silently dropping a metro.

Usage:
    python scripts/fetch_rent_drops.py --dry-run
    python scripts/fetch_rent_drops.py                     # live (needs LISTINGRAIL_API_KEY)
    python scripts/fetch_rent_drops.py --cache-dir $TMPDIR/rd-cache   # reuse raw responses
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import io
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rent_drops_lib as R  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "rent-drops"
HISTORY_DIR = OUT_DIR / "history"
SAMPLES_DIR = OUT_DIR / "samples"
DEFAULT_KEY_PATH = Path("/home/paseo/.secrets/listingrail-feed-sample-key.txt")
API_URL = "https://listingrail.com/v1/listings/search"
SOURCES = ("apartments-com", "zumper")
TARGET_METROS = 50
MIN_PRICED = 60

# Ordered candidates (largest apartment inventories first). The first TARGET_METROS that
# pass the MIN_PRICED gate are kept; the list is never padded.
CANDIDATES = [
    ("new-york-ny", "New York", "NY"), ("los-angeles-ca", "Los Angeles", "CA"), ("chicago-il", "Chicago", "IL"),
    ("houston-tx", "Houston", "TX"), ("dallas-tx", "Dallas", "TX"), ("atlanta-ga", "Atlanta", "GA"),
    ("phoenix-az", "Phoenix", "AZ"), ("austin-tx", "Austin", "TX"), ("denver-co", "Denver", "CO"),
    ("charlotte-nc", "Charlotte", "NC"), ("nashville-tn", "Nashville", "TN"), ("san-antonio-tx", "San Antonio", "TX"),
    ("fort-worth-tx", "Fort Worth", "TX"), ("seattle-wa", "Seattle", "WA"), ("miami-fl", "Miami", "FL"),
    ("orlando-fl", "Orlando", "FL"), ("tampa-fl", "Tampa", "FL"), ("jacksonville-fl", "Jacksonville", "FL"),
    ("raleigh-nc", "Raleigh", "NC"), ("las-vegas-nv", "Las Vegas", "NV"), ("san-diego-ca", "San Diego", "CA"),
    ("san-jose-ca", "San Jose", "CA"), ("san-francisco-ca", "San Francisco", "CA"), ("washington-dc", "Washington", "DC"),
    ("boston-ma", "Boston", "MA"), ("philadelphia-pa", "Philadelphia", "PA"), ("baltimore-md", "Baltimore", "MD"),
    ("minneapolis-mn", "Minneapolis", "MN"), ("columbus-oh", "Columbus", "OH"), ("indianapolis-in", "Indianapolis", "IN"),
    ("kansas-city-mo", "Kansas City", "MO"), ("st-louis-mo", "St. Louis", "MO"), ("salt-lake-city-ut", "Salt Lake City", "UT"),
    ("portland-or", "Portland", "OR"), ("sacramento-ca", "Sacramento", "CA"), ("oklahoma-city-ok", "Oklahoma City", "OK"),
    ("louisville-ky", "Louisville", "KY"), ("memphis-tn", "Memphis", "TN"), ("richmond-va", "Richmond", "VA"),
    ("cincinnati-oh", "Cincinnati", "OH"), ("cleveland-oh", "Cleveland", "OH"), ("pittsburgh-pa", "Pittsburgh", "PA"),
    ("detroit-mi", "Detroit", "MI"), ("milwaukee-wi", "Milwaukee", "WI"), ("albuquerque-nm", "Albuquerque", "NM"),
    ("tucson-az", "Tucson", "AZ"), ("mesa-az", "Mesa", "AZ"), ("scottsdale-az", "Scottsdale", "AZ"),
    ("irving-tx", "Irving", "TX"), ("plano-tx", "Plano", "TX"), ("arlington-tx", "Arlington", "TX"),
    ("durham-nc", "Durham", "NC"), ("charleston-sc", "Charleston", "SC"), ("greenville-sc", "Greenville", "SC"),
    ("birmingham-al", "Birmingham", "AL"), ("new-orleans-la", "New Orleans", "LA"), ("omaha-ne", "Omaha", "NE"),
    ("tulsa-ok", "Tulsa", "OK"), ("boise-id", "Boise", "ID"), ("el-paso-tx", "El Paso", "TX"),
    ("fort-lauderdale-fl", "Fort Lauderdale", "FL"), ("alexandria-va", "Alexandria", "VA"), ("aurora-co", "Aurora", "CO"),
    ("chandler-az", "Chandler", "AZ"), ("henderson-nv", "Henderson", "NV"),
]


def metro_dict(slug: str, city: str, state: str) -> dict:
    return {"slug": slug, "label": f"{city}, {state}", "city": city, "state": state, "location": f"{city}, {state}"}


def load_key() -> str:
    k = os.environ.get("LISTINGRAIL_API_KEY", "").strip()
    if k:
        return k
    if DEFAULT_KEY_PATH.is_file():
        return DEFAULT_KEY_PATH.read_text().strip()
    raise SystemExit("ERROR: LISTINGRAIL_API_KEY is not set and no key file exists; nothing written.")


class FetchError(RuntimeError):
    pass


def api_search(key: str, source: str, location: str, limit: int, cache_dir: Path | None) -> list[dict]:
    cache = cache_dir / f"{source}__{location.replace(', ', '_').replace(' ', '-')}.json" if cache_dir else None
    if cache and cache.is_file():
        return json.loads(cache.read_text()).get("listings") or []
    payload = json.dumps({"source": source, "location": location, "type": "rent", "limit": limit}).encode()
    last = None
    for attempt in range(3):
        req = urllib.request.Request(API_URL, data=payload,
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = resp.read().decode()
            data = json.loads(body)
            if cache:
                cache.write_text(body)
            return data.get("listings") or []
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3 * (attempt + 1))
    raise FetchError(f"{source} {location}: {last}")


def load_prior(today: str) -> dict[str, dict[str, dict]]:
    """date -> {metro slug -> history record}, excluding today's (same-day reruns overwrite)."""
    out: dict[str, dict[str, dict]] = {}
    if not HISTORY_DIR.is_dir():
        return out
    for p in sorted(HISTORY_DIR.glob("*.json")):
        if p.stem >= today:
            continue
        try:
            out[p.stem] = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
    # Same ISO week as today: keep only the latest earlier file of that week (one per week).
    by_week: dict[str, str] = {}
    for d in sorted(out):
        by_week[R.iso_week(d)] = d
    return {d: out[d] for d in by_week.values()}


def build_metro(key: str, m: dict, limit: int, today: str, prior_all: dict, cache_dir: Path | None):
    raw_a = api_search(key, "apartments-com", m["location"], limit, cache_dir)
    raw_z = api_search(key, "zumper", m["location"], limit, cache_dir)
    apts = [c for r in raw_a if (c := R.clean_apartments_property(r, m["state"]))]
    zum = [c for r in raw_z if (c := R.clean_zumper(r, m["state"]))]
    prior = {d: rec[m["slug"]] for d, rec in prior_all.items() if m["slug"] in rec}
    return R.summarize_metro(m, apts, zum, today, prior)


def csv_text(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=R.CSV_FIELDS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in R.CSV_FIELDS})
    return buf.getvalue()


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def collect(metros: list[dict], fn, workers: int) -> tuple[dict, dict]:
    results: dict[str, tuple[dict, dict]] = {}
    errors: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fn, m): m for m in metros}
        for fut in concurrent.futures.as_completed(futs):
            m = futs[fut]
            try:
                results[m["slug"]] = fut.result()
            except FetchError as exc:
                errors[m["slug"]] = str(exc)
                print(f"{m['slug']:22s} FETCH FAILED: {exc}", file=sys.stderr, flush=True)
                continue
            rec = results[m["slug"]][0]
            print(f"{m['slug']:22s} apts={rec['n_apartments_com']:3d} zumper={rec['n_zumper']:3d} "
                  f"conc={rec['concessions']['share_pct']}%", flush=True)
    return results, errors


def select_roster(metros: list[dict], results: dict, errors: dict) -> tuple[list[dict], dict]:
    """First TARGET_METROS passing metros in candidate order. A fetch failure aborts only when it
    falls inside that roster (it would otherwise silently swap a metro out)."""
    kept, hist = [], {}
    for m in metros:
        if len(kept) >= TARGET_METROS:
            break
        if m["slug"] in errors:
            raise FetchError(f"{m['slug']} failed inside the roster: {errors[m['slug']]}")
        rec, h = results[m["slug"]]
        if rec["n_priced"] >= MIN_PRICED:
            kept.append(rec)
            hist[m["slug"]] = h
    return kept, hist


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--cache-dir", type=Path, default=None, help="Store/reuse raw API responses (outside the repo)")
    ap.add_argument("--date", default=None, help="Override snapshot date (YYYY-MM-DD), for backfills/tests")
    args = ap.parse_args(argv)

    metros = [metro_dict(*c) for c in CANDIDATES]
    if args.dry_run:
        print(f"Dry run: {len(metros)} candidates, keep first {TARGET_METROS} with >= {MIN_PRICED} priced listings; "
              f"{len(metros) * 2} searches, max {len(metros) * 2 * args.limit} credits")
        for m in metros:
            print(f"  /rent-drops/{m['slug']}/  ({m['location']})")
        return 0

    key = load_key()
    now = datetime.now(timezone.utc)
    today = args.date or now.date().isoformat()
    if args.cache_dir:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
    prior_all = load_prior(today)

    results, errors = collect(metros, lambda m: build_metro(key, m, args.limit, today, prior_all, args.cache_dir),
                              args.workers)
    try:
        kept, hist = select_roster(metros, results, errors)
    except FetchError as exc:
        print(f"ERROR: {exc}. Nothing written.", file=sys.stderr)
        return 1
    if len(kept) < TARGET_METROS:
        print(f"WARN: only {len(kept)} metros passed the {MIN_PRICED}-listing gate", file=sys.stderr)

    for rec in kept:
        write_atomic(SAMPLES_DIR / f"{rec['slug']}.csv", csv_text(rec["sample_rows"]))
    payload = {
        "generated_at": now.isoformat(timespec="seconds"),
        "snapshot_date": today,
        "iso_week": R.iso_week(today),
        "sources": list(SOURCES),
        "min_priced_per_metro": MIN_PRICED,
        "method": R.METHOD,
        "metros": kept,
    }
    write_atomic(HISTORY_DIR / f"{today}.json", json.dumps(hist, separators=(",", ":"), sort_keys=True) + "\n")
    write_atomic(OUT_DIR / "latest.json", json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    print(f"Done: kept {len(kept)}/{len(metros)} metros -> {OUT_DIR / 'latest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
