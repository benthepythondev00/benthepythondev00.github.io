"""Pure logic for the US metro apartment concession & rent-drop snapshot (/rent-drops/).

Everything here is offline and deterministic so it can be unit tested from fixtures.
The fetcher (scripts/fetch_rent_drops.py) calls the Listingrail API and hands the raw
responses to these functions.

Rules this module enforces (venture red lines):
- Output rows are built from a whitelist of named fields; raw portal blobs, agent
  names, phones and emails never leave this module.
- A move-in special counts as a concession only when the strict regex finds a concrete
  rent concession (weeks/months free, percent or dollar off rent, waived fees, look &
  lease). Generic marketing taglines ("Ask about our specials!", "Terms apply") do not.
- Bedroom medians are published only for buckets with n >= 20 after removing
  co-living / per-bed priced floor plans.
- 30-day rent-cut counts stay null until 4 distinct ISO weeks of snapshots exist.
"""
from __future__ import annotations

import re
import statistics
from datetime import date

LEASE_MONTHS = 12
WEEKS_PER_MONTH = 52 / 12
MIN_BUCKET_N = 20
MIN_SPREAD_N = 20
WEEKS_NEEDED = 4
BED_BUCKETS = ("0", "1", "2", "3")
BED_LABELS = {"0": "Studio", "1": "1BR", "2": "2BR", "3": "3BR"}
# A 2BR+ floor plan advertised below this share of the metro's 1BR median is treated as
# per-bed (student / co-living) pricing and excluded from the bedroom medians.
PER_BED_FLOOR_RATIO = 0.75
COLIVING_RE = re.compile(
    r"\b(student|co-?living|by the bed|per bed|per-bed|private (bed)?room|shared (suite|unit|apartment)|"
    r"individual lease|rent by the (bed|room)|campus)\b",
    re.I,
)

METHOD = {
    "label": "Publicly advertised asking rents and move-in specials. Not signed lease transactions, "
             "not private rent-roll data, not pricing or legal advice.",
    "lease_months_assumed": LEASE_MONTHS,
    "net_effective_formula": "asking rent x (1 - free months / 12) for weeks or months free; "
                             "asking rent - dollar-off / 12 for dollar-off and look & lease; "
                             "asking rent x (1 - pct x months / 12) for percent-off. Waived fees do not change rent.",
    "concession_value": "Largest concrete value in the advertised special ('up to', 'select units'), so the "
                        "net-effective figure is the maximum advertised saving, not a guaranteed one.",
    "already_net": "Specials saying the advertised rate already reflects the concession are counted as "
                   "concessions but never discounted twice.",
    "concession_share_basis": "Share of priced Apartments.com properties in the metro sample whose special "
                              "matches the strict concession regex. Zumper has no specials field.",
    "bedroom_floor_n": MIN_BUCKET_N,
    "per_bed_filter": f"Floor plans with 2+ bedrooms advertised below {int(PER_BED_FLOOR_RATIO * 100)}% of the "
                      "metro 1BR median, below the same property's cheapest 1BR, or named as student / "
                      "co-living are excluded.",
    "rent_cuts": f"A rent cut is the same listing id advertising a lower asking rent than its highest rent in "
                 f"the last 30 days. Shown only once {WEEKS_NEEDED} distinct ISO weeks of snapshots exist.",
}

# ---------------------------------------------------------------- concession parser

_NUM_WORDS = {
    "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "half a": 0.5, "half": 0.5,
}
_NUM = r"(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|an?|half a)"
_FREE = r"(?:free|off|of free|rent[- ]free|free (?:base )?rent|(?:of )?free base rent)"

# "6 weeks free", "up to 10 weeks of free base rent", "Six Weeks OFF", "1 month free"
FREE_TIME_RE = re.compile(
    rf"\b{_NUM}\s*(?:\(\d+\)\s*)?(week|wk|month|mo)s?\b(?:\s+(?:of\s+)?(?:base\s+)?)?\s*{_FREE}",
    re.I,
)
# "first month free", "month free" without a number
FIRST_MONTH_RE = re.compile(
    r"\b(first|1st|second|2nd)\s+(full\s+)?month(\s+of\s+(base\s+)?rent)?\s+(free|rent[- ]free|off)\b", re.I
)
# "50% off rent for 5 months"
PCT_OFF_RE = re.compile(
    rf"(?:\b(\d{{1,2}})\s?%|\b(1/2|half))\s*off\b[^.;!|]{{0,40}}?\bfor\s+(?:the\s+first\s+)?{_NUM}\s+(month|week)s?\b", re.I
)
# "$500 off", "$1,000 off rent", "$300 off your first month"
DOLLAR_OFF_RE = re.compile(r"\$\s?(\d{1,2},?\d{3}|\d{2,4})\s*(?:off|discount|rent credit|in rent credit|move-in credit|concession)\b", re.I)
# "$1,000 Look & Lease Incentive", "look and lease ... $500"
LOOK_LEASE_RE = re.compile(
    r"(\$\s?(\d{1,2},?\d{3}|\d{2,4})[^.;!|]{0,25}look\s*(?:&|and|n)\s*lease)|(look\s*(?:&|and|n)\s*lease[^.;!|]{0,40}?\$\s?(\d{1,2},?\d{3}|\d{2,4}))",
    re.I,
)
LOOK_LEASE_ANY_RE = re.compile(r"\blook\s*(?:&|and|n)\s*lease\b", re.I)
# "waived application fee", "no admin fee", "$0 application fee", "application fee waived"
WAIVED_RE = re.compile(
    r"(\bwaived?\s+(?:\w+\s+){0,2}(?:application|app|admin|administration|amenity|deposit|security deposit|fees?)\b)|"
    r"(\b(?:application|app|admin|administration|amenity|deposit)\s*(?:/\s*\w+\s*)?(?:fees?\s+)?(?:is\s+|are\s+)?waived\b)|"
    r"((?:\bno|\$0|\bzero)\s+(?:application|app|admin|administration|amenity)(?:\s*/\s*\w+)?\s+fees?\b)|"
    r"(\$0\s+(?:security\s+)?deposit\b)",
    re.I,
)
ALREADY_NET_RE = re.compile(
    r"(rates?|pric(?:es|ing)|rent)\s+(?:shown\s+)?(?:reflects?|includes?|already include)\s+(?:the\s+)?(?:[\d.]+|\w+)?\s*"
    r"(?:weeks?|months?|concessions?|special)|rolled into|net effective|effective rent",
    re.I,
)


def _num(token: str) -> float | None:
    t = token.strip().lower()
    if t in _NUM_WORDS:
        return float(_NUM_WORDS[t])
    try:
        return float(t)
    except ValueError:
        return None


def _money(token: str) -> float:
    return float(token.replace(",", "").replace("$", "").strip())


def _dedupe_specials(specials) -> str:
    """Join a property's specials into one text, dropping exact repeats ("A; A")."""
    if not specials:
        return ""
    if isinstance(specials, str):
        specials = [specials]
    parts: list[str] = []
    for s in specials:
        if not isinstance(s, str):
            continue
        for p in s.split("; "):
            p = " ".join(p.split())
            if p and p not in parts:
                parts.append(p)
    return " | ".join(parts)


def parse_concession(specials) -> dict:
    """Parse move-in specials with a strict regex.

    Returns {"verified": bool, "kinds": [...], "free_weeks": float|None, "pct_off": ...,
    "dollar_off": float|None, "waived_fees": bool, "already_net": bool, "matched": [phrases]}.
    "matched" holds only the short matched phrases, never the full marketing text.
    """
    text = _dedupe_specials(specials)
    out = {
        "verified": False, "kinds": [], "free_weeks": None, "pct_off_months": None,
        "dollar_off": None, "waived_fees": False, "already_net": False, "matched": [],
    }
    if not text:
        return out

    weeks: list[float] = []
    for m in FREE_TIME_RE.finditer(text):
        n = _num(m.group(1))
        if n is None or n <= 0:
            continue
        unit = m.group(2).lower()
        w = n if unit.startswith("w") else n * WEEKS_PER_MONTH
        if 0 < w <= 26:  # never more than half a 12-month lease
            weeks.append(round(w, 2))
            out["matched"].append(m.group(0).strip())
    for m in FIRST_MONTH_RE.finditer(text):
        weeks.append(round(WEEKS_PER_MONTH, 2))
        out["matched"].append(m.group(0).strip())
    if weeks:
        out["free_weeks"] = max(weeks)
        out["kinds"].append("free_time")

    pct = []
    for m in PCT_OFF_RE.finditer(text):
        p = float(m.group(1)) if m.group(1) else 50.0
        n = _num(m.group(3))
        if n and 0 < p <= 100:
            months = n if m.group(4).lower().startswith("m") else n / WEEKS_PER_MONTH
            if months <= LEASE_MONTHS:
                pct.append(round(p / 100 * months, 3))
                out["matched"].append(m.group(0).strip())
    if pct:
        out["pct_off_months"] = max(pct)  # equivalent free months
        out["kinds"].append("pct_off")

    dollars = []
    for m in DOLLAR_OFF_RE.finditer(text):
        if re.match(r"\s*(?:\w+\s+){0,2}(app|application|admin|administration|fees?|deposit)\b", text[m.end(): m.end() + 30], re.I):
            continue  # "$50 off application fee" is a fee discount, not rent off
        v = _money(m.group(1))
        if 25 <= v <= 10000:
            dollars.append(v)
            out["matched"].append(m.group(0).strip())
    for m in LOOK_LEASE_RE.finditer(text):
        after = text[m.end(): m.end() + 30].lower()
        if re.match(r"\s*(app|application|admin|administration|fee|deposit)", after):
            continue  # "$99 app/admin special" is a fee, not rent off
        v = _money(m.group(2) or m.group(4))
        if 25 <= v <= 10000:
            dollars.append(v)
            out["matched"].append(m.group(0).strip())
    if dollars:
        out["dollar_off"] = max(dollars)
        out["kinds"].append("dollar_off")
    if LOOK_LEASE_ANY_RE.search(text) and "look_and_lease" not in out["kinds"]:
        out["kinds"].append("look_and_lease")
        if not any("look" in x.lower() for x in out["matched"]):
            out["matched"].append(LOOK_LEASE_ANY_RE.search(text).group(0))

    wm = WAIVED_RE.search(text)
    if wm:
        out["waived_fees"] = True
        out["kinds"].append("waived_fees")
        out["matched"].append(wm.group(0).strip())

    out["verified"] = bool(out["kinds"])
    out["already_net"] = bool(out["verified"] and ALREADY_NET_RE.search(text))
    out["matched"] = [x[:60] for x in out["matched"]][:4]
    return out


def free_months_equiv(c: dict) -> float:
    """Months of free rent a concession equals over a 12-month lease (without dollar-off)."""
    m = 0.0
    if c.get("free_weeks"):
        m = max(m, c["free_weeks"] / WEEKS_PER_MONTH)
    if c.get("pct_off_months"):
        m = max(m, c["pct_off_months"])
    return min(m, LEASE_MONTHS / 2)


def net_effective(asking: float, c: dict) -> float:
    """Monthly net-effective asking rent over a 12-month lease."""
    if not c or not c.get("verified") or c.get("already_net"):
        return round(asking, 2)
    ner = asking * (1 - free_months_equiv(c) / LEASE_MONTHS)
    if c.get("dollar_off"):
        ner = min(ner, asking - c["dollar_off"] / LEASE_MONTHS)
    return round(max(ner, 0.0), 2)


def discount_pct(asking: float, c: dict) -> float:
    if not asking:
        return 0.0
    return round((1 - net_effective(asking, c) / asking) * 100, 2)


# ---------------------------------------------------------------- cleaning

def _f(v, lo, hi):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi else None


def clean_apartments_property(row: dict, state: str) -> dict | None:
    """Whitelist one apartments-com listing (a property with floor plans)."""
    if str(row.get("region") or "").upper() != state.upper():
        return None
    price = _f(row.get("price"), 300, 30000)
    if price is None:
        return None
    raw = row.get("raw") or {}
    name = str(row.get("title") or raw.get("name") or "")[:80]
    conc = parse_concession(raw.get("moveInSpecials"))
    plans = []
    seen = set()
    for fp in raw.get("floorPlans") or []:
        if not isinstance(fp, dict):
            continue
        beds = fp.get("beds")
        rent = _f(fp.get("rentMin"), 300, 30000)
        if not isinstance(beds, (int, float)) or beds < 0 or beds > 8 or rent is None:
            continue
        sqft = _f(fp.get("sqftMin"), 150, 6000)
        key = (str(fp.get("name") or "")[:60], int(beds), rent, sqft)
        if key in seen:
            continue
        seen.add(key)
        plans.append({"plan": key[0], "beds": int(beds), "rent": rent, "sqft": sqft,
                      "coliving": bool(COLIVING_RE.search(key[0]))})
    return {
        "id": str(row.get("id") or ""),
        "source": "apartments-com",
        "name": name,
        "city": str(row.get("city") or "")[:48],
        "zip": str(row.get("postal_code") or "")[:10],
        "beds": int(row["beds"]) if isinstance(row.get("beds"), int) and 0 <= row["beds"] <= 8 else None,
        "price": price,
        "sqft": _f(row.get("area"), 150, 6000),
        "url": str(row.get("url") or "") if str(row.get("url") or "").startswith("https://www.apartments.com/") else "",
        "coliving": bool(COLIVING_RE.search(name) or COLIVING_RE.search(str(row.get("property_type") or ""))),
        "had_specials": bool(_dedupe_specials(raw.get("moveInSpecials"))),
        "concession": conc,
        "plans": plans,
    }


def clean_zumper(row: dict, state: str) -> dict | None:
    if str(row.get("region") or "").upper() != state.upper():
        return None
    price = _f(row.get("price"), 300, 30000)
    if price is None:
        return None
    url = str(row.get("url") or "")
    return {
        "id": str(row.get("id") or ""),
        "source": "zumper",
        "name": str(row.get("title") or "")[:80],
        "city": str(row.get("city") or "")[:48],
        "zip": str(row.get("postal_code") or "")[:10],
        "beds": int(row["beds"]) if isinstance(row.get("beds"), int) and 0 <= row["beds"] <= 8 else None,
        "price": price,
        "sqft": _f(row.get("area"), 150, 6000),
        "url": url if url.startswith("https://www.zumper.com/") else "",
        "coliving": bool(COLIVING_RE.search(str(row.get("title") or ""))),
    }


# ---------------------------------------------------------------- aggregates

def _q(vals: list[float]) -> dict | None:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return {"n": n, "p25": round(s[int(0.25 * (n - 1))], 2), "median": round(statistics.median(s), 2),
            "p75": round(s[int(0.75 * (n - 1))], 2)}


def usable_plans(props: list[dict]) -> tuple[list[tuple[dict, dict]], int]:
    """(property, plan) pairs after the co-living / per-bed filter, plus how many were removed."""
    pairs = [(p, fp) for p in props if not p["coliving"] for fp in p["plans"] if not fp["coliving"]]
    removed = sum(len(p["plans"]) for p in props) - len(pairs)
    one = [fp["rent"] for _, fp in pairs if fp["beds"] == 1]
    floor = statistics.median(one) * PER_BED_FLOOR_RATIO if len(one) >= MIN_BUCKET_N else None
    out = []
    for p, fp in pairs:
        if fp["beds"] >= 2:
            own_1br = [x["rent"] for x in p["plans"] if x["beds"] == 1]
            if (floor and fp["rent"] < floor) or (own_1br and fp["rent"] < min(own_1br)):
                removed += 1
                continue
        out.append((p, fp))
    return out, removed


def bedroom_table(props: list[dict]) -> tuple[dict, int]:
    pairs, removed = usable_plans(props)
    table = {}
    for b in BED_BUCKETS:
        rows = [(p, fp) for p, fp in pairs if fp["beds"] == int(b)]
        n = len(rows)
        entry = {"label": BED_LABELS[b], "n": n, "n_properties": len({p["id"] for p, _ in rows}),
                 "published": n >= MIN_BUCKET_N}
        if n >= MIN_BUCKET_N:
            heads = [fp["rent"] for _, fp in rows]
            ners = [net_effective(fp["rent"], p["concession"]) for p, fp in rows]
            psf = [fp["rent"] / fp["sqft"] for _, fp in rows if fp["sqft"]]
            entry.update({
                "headline_median": round(statistics.median(heads), 2),
                "net_effective_median": round(statistics.median(ners), 2),
                "headline": _q(heads),
                "rent_per_sqft_median": round(statistics.median(psf), 3) if len(psf) >= MIN_BUCKET_N else None,
                "sqft_median": round(statistics.median([fp["sqft"] for _, fp in rows if fp["sqft"]]))
                if any(fp["sqft"] for _, fp in rows) else None,
            })
        table[b] = entry
    return table, removed


def concession_summary(props: list[dict]) -> dict:
    n = len(props)
    ver = [p for p in props if p["concession"]["verified"]]
    with_text = sum(1 for p in props if p["concession"]["verified"] or p.get("had_specials"))
    kinds: dict[str, int] = {}
    for p in ver:
        for k in p["concession"]["kinds"]:
            kinds[k] = kinds.get(k, 0) + 1
    fw = [p["concession"]["free_weeks"] for p in ver if p["concession"]["free_weeks"]]
    disc = [discount_pct(p["price"], p["concession"]) for p in ver if not p["concession"]["already_net"]]
    disc = [d for d in disc if d > 0]
    return {
        "basis": "apartments-com properties",
        "n_properties": n,
        "n_with_specials_text": with_text,
        "n_verified": len(ver),
        "share_pct": round(len(ver) / n * 100, 1) if n else None,
        "kinds": kinds,
        "median_free_weeks": round(statistics.median(fw), 1) if fw else None,
        "max_free_weeks": round(max(fw), 1) if fw else None,
        "median_effective_discount_pct": round(statistics.median(disc), 2) if disc else None,
        "n_already_net": sum(1 for p in ver if p["concession"]["already_net"]),
    }


def cross_portal_spread(apts: list[dict], zum: list[dict]) -> dict:
    """Zumper vs Apartments.com listing-level 'from' price per bedroom bucket (n>=20 both)."""
    out = {}
    for b in BED_BUCKETS:
        a = [p["price"] for p in apts if p["beds"] == int(b) and not p["coliving"]]
        z = [p["price"] for p in zum if p["beds"] == int(b) and not p["coliving"]]
        if len(a) >= MIN_SPREAD_N and len(z) >= MIN_SPREAD_N:
            am, zm = statistics.median(a), statistics.median(z)
            out[b] = {"label": BED_LABELS[b], "n_apartments_com": len(a), "n_zumper": len(z),
                      "apartments_com_median": round(am, 2), "zumper_median": round(zm, 2),
                      "spread_pct": round((zm - am) / am * 100, 1)}
        else:
            out[b] = None
    return out


def history_record(apts: list[dict], zum: list[dict]) -> dict:
    """Ids and numbers only (served publicly): listing price per source + plan-level rentMin."""
    plans = {}
    for p in apts:
        for fp in p["plans"]:
            plans[f"{p['id']}|{fp['beds']}|{fp['plan']}"] = fp["rent"]
    return {
        "apartments-com": {p["id"]: p["price"] for p in apts if p["id"]},
        "zumper": {p["id"]: p["price"] for p in zum if p["id"]},
        "plans": plans,
    }


def iso_week(d: str) -> str:
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


def rent_cuts(today: str, current: dict, prior: dict[str, dict]) -> dict:
    """30-day asking-rent cuts by listing id. prior maps snapshot date -> history_record for this metro.

    Locked (count null) until WEEKS_NEEDED distinct ISO weeks (including today) exist.
    """
    t = date.fromisoformat(today)
    window = {d: rec for d, rec in prior.items() if d < today and (t - date.fromisoformat(d)).days <= 30}
    weeks = sorted({iso_week(d) for d in window} | {iso_week(today)})
    base = {
        "weeks_collected": len(weeks),
        "weeks_needed": WEEKS_NEEDED,
        "unlocked": len(weeks) >= WEEKS_NEEDED,
        "baseline_date": min(window) if window else None,
        "span_days": (t - date.fromisoformat(min(window))).days if window else 0,
        "count": None, "n_matched": None, "share_pct": None, "median_cut_pct": None,
        "plan_cuts": None, "n_plans_matched": None,
    }
    if not base["unlocked"]:
        return base
    high: dict[str, float] = {}
    plan_high: dict[str, float] = {}
    for rec in window.values():
        for src in ("apartments-com", "zumper"):
            for lid, pr in (rec.get(src) or {}).items():
                k = f"{src}|{lid}"
                high[k] = max(high.get(k, 0.0), float(pr))
        for k, pr in (rec.get("plans") or {}).items():
            plan_high[k] = max(plan_high.get(k, 0.0), float(pr))
    cuts, matched = [], 0
    for src in ("apartments-com", "zumper"):
        for lid, pr in (current.get(src) or {}).items():
            old = high.get(f"{src}|{lid}")
            if old:
                matched += 1
                if pr < old * 0.995:
                    cuts.append((old - pr) / old * 100)
    pcuts, pmatched = 0, 0
    for k, pr in (current.get("plans") or {}).items():
        old = plan_high.get(k)
        if old:
            pmatched += 1
            if pr < old * 0.995:
                pcuts += 1
    base.update({
        "count": len(cuts), "n_matched": matched,
        "share_pct": round(len(cuts) / matched * 100, 1) if matched else None,
        "median_cut_pct": round(statistics.median(cuts), 1) if cuts else None,
        "plan_cuts": pcuts, "n_plans_matched": pmatched,
    })
    return base


CSV_FIELDS = ["listing_id", "source", "property_name", "city", "zip", "beds", "sqft", "asking_rent",
              "rent_per_sqft", "concession_verified", "concession_type", "free_weeks", "net_effective_rent",
              "snapshot_date", "listing_url"]


def sample_rows(apts: list[dict], zum: list[dict], snapshot_date: str, n: int = 25) -> list[dict]:
    """Deterministic 25-row sample: 18 Apartments.com floor plans (one per property) + 7 Zumper listings."""
    pairs, _ = usable_plans(apts)
    first: dict[str, tuple[dict, dict]] = {}
    for p, fp in sorted(pairs, key=lambda x: (x[0]["id"], x[1]["beds"], x[1]["rent"])):
        first.setdefault(p["id"], (p, fp))
    a_rows = []
    for p, fp in sorted(first.values(), key=lambda x: (not x[0]["concession"]["verified"], x[0]["id"])):
        c = p["concession"]
        a_rows.append({
            "listing_id": p["id"], "source": "apartments-com", "property_name": p["name"], "city": p["city"],
            "zip": p["zip"], "beds": fp["beds"], "sqft": int(fp["sqft"]) if fp["sqft"] else "",
            "asking_rent": int(fp["rent"]),
            "rent_per_sqft": round(fp["rent"] / fp["sqft"], 2) if fp["sqft"] else "",
            "concession_verified": "yes" if c["verified"] else "no",
            "concession_type": "+".join(c["kinds"]),
            "free_weeks": c["free_weeks"] if c["free_weeks"] else "",
            "net_effective_rent": int(round(net_effective(fp["rent"], c))),
            "snapshot_date": snapshot_date, "listing_url": p["url"],
        })
    z_rows = [{
        "listing_id": z["id"], "source": "zumper", "property_name": z["name"], "city": z["city"], "zip": z["zip"],
        "beds": z["beds"] if z["beds"] is not None else "", "sqft": int(z["sqft"]) if z["sqft"] else "",
        "asking_rent": int(z["price"]), "rent_per_sqft": round(z["price"] / z["sqft"], 2) if z["sqft"] else "",
        "concession_verified": "", "concession_type": "", "free_weeks": "", "net_effective_rent": "",
        "snapshot_date": snapshot_date, "listing_url": z["url"],
    } for z in sorted(zum, key=lambda x: x["id"]) if not z["coliving"]]
    nz = min(7, len(z_rows))
    rows = a_rows[: n - nz] + z_rows[:nz]
    if len(rows) < n:
        rows += z_rows[nz: nz + n - len(rows)]
    return rows[:n]


def summarize_metro(metro: dict, apts: list[dict], zum: list[dict], today: str, prior: dict[str, dict]) -> dict:
    beds, removed = bedroom_table(apts)
    hist = history_record(apts, zum)
    all_psf = [fp["rent"] / fp["sqft"] for _, fp in usable_plans(apts)[0] if fp["sqft"]]
    return {
        **metro,
        "snapshot_date": today,
        "n_apartments_com": len(apts),
        "n_zumper": len(zum),
        "n_priced": len(apts) + len(zum),
        "n_floor_plans": sum(len(p["plans"]) for p in apts),
        "n_plans_removed_per_bed": removed,
        "concessions": concession_summary(apts),
        "bedrooms": beds,
        "rent_per_sqft_median": round(statistics.median(all_psf), 3) if len(all_psf) >= MIN_BUCKET_N else None,
        "zumper_spread": cross_portal_spread(apts, zum),
        "rent_cuts_30d": rent_cuts(today, hist, prior),
        "sample_rows": sample_rows(apts, zum, today),
    }, hist
