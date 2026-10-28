"""Build jobs-in-denmark/index.html: English openings in Denmark at SIRI's Fast-Track certified employers.

SIRI publishes the certified companies only as an HTML table. We map each company to a public job-board API
(Greenhouse, Lever, Ashby, SmartRecruiters, Teamtailor, Workable, Recruitee) by guessing its board slug from the
name; a board counts only when it lists jobs located in Denmark. Mappings live in data/denmark-ats.json, so the
daily run probes only companies it has not checked in the last 30 days. Only facts are published (title, employer,
place, salary fields); every card links the employer's own posting.
"""

from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PAGE_DIR = ROOT / "jobs-in-denmark"
TEMPLATE = PAGE_DIR / "template.html"
DATA = ROOT / "data" / "denmark-jobs.json"
ATS_FILE = ROOT / "data" / "denmark-ats.json"

SIRI = "https://www.nyidanmark.dk/en-GB/Words-and-concepts/SIRI/Certified-companies"
UA = {"User-Agent": "benthepythondev-jobs-in-denmark/1.0 (+https://benthepythondev00.github.io/jobs-in-denmark/)"}
# Pay limit track of the Fast-Track scheme, 2026 level, set every 1 January
# (https://www.nyidanmark.dk/en-GB/You-want-to-apply/Work/Fast-track). Update both each January.
PAY_LIMIT = 552_000
PAY_LIMIT_SUPPLEMENTARY = 446_000
RECHECK_DAYS = 30
MAX_AGE_DAYS = 120  # older postings are stale or demo boards (a 2022 Teamtailor demo account is named "maersk")
# Slugs that match a certified company's name but belong to someone else, checked by hand.
NOT_THEIRS = {("lever", "dnb"),  # Dun & Bradstreet, not DNB Carnegie
              ("teamtailor", "maersk"),  # Teamtailor's own demo board
              ("teamtailor", "jks")}  # JKS recruits for client companies that are not on the list
MIN_JOBS = 30  # fewer means the feeds failed: keep yesterday's page

DK_PLACE = re.compile(
    r"\b(denmark|danmark|dk|copenhagen|k[øo]benhavn|kobenhavn|aarhus|[åa]rhus|odense|aalborg|esbjerg|kolding|vejle|horsens"
    r"|roskilde|lyngby|billund|herning|ballerup|s[øo]borg|h[øo]rsholm|bagsv[æa]rd|kalundborg|silkeborg|randers|s[øo]nderborg"
    r"|hellerup|glostrup|taastrup|frederiksberg|herlev|br[øo]ndby|risskov|skanderborg|fredericia|viborg|hiller[øo]d|m[åa]l[øo]v"
    r"|gentofte|valby|n[æa]stved|holstebro|nordborg|vojens|hj[øo]rring|frederikshavn|skovlunde|albertslund|kastrup|dragør)\b", re.I)
LEGAL = re.compile(r"\b(a/s|aps|i/s|p/s|k/s|amba|a\.m\.b\.a\.?|smba|f\.m\.b\.a\.?|ivs|as|ab|inc|ltd|gmbh|bv|sa|plc|llc|holding|"
                   r"group|danmark|denmark|nordic|scandinavia|dk|filial af.*|branch.*|af \d{4})\b", re.I)
DA_WORDS = set("og til med af er vi du som på det en at har for der vil vores dig din kan skal også ikke eller hos fra".split())
EN_WORDS = set("the and to of you we with in for our your is are will be as on at this that have an or from who".split())


def norm(s: str) -> str:
    s = html.unescape(s or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_siri(page: str) -> list[dict]:
    """Rows of SIRI's table as {name, cvr}; the header row and rows without an 8-digit CVR are dropped."""
    out, seen = [], set()
    for row in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", page):
        cells = [norm(re.sub(r"<[^>]+>", " ", c)) for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>", row)]
        if len(cells) < 2:
            continue
        cvr = re.sub(r"\D", "", cells[1])
        if len(cvr) != 8 or cvr in seen:
            continue
        seen.add(cvr)
        out.append({"name": cells[0], "cvr": cvr})
    return out


def ascii_fold(s: str) -> str:
    s = s.lower().replace("æ", "ae").replace("ø", "o").replace("å", "a").replace("&", " and ")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def slugs(name: str) -> list[str]:
    """Board slugs a company is likely to use: 'Pleo Technologies A/S' -> pleotechnologies, pleo-technologies, pleo."""
    base = re.sub(r"\(.*?\)", " ", ascii_fold(name))
    base = LEGAL.sub(" ", base.replace(" and ", " "))
    words = re.findall(r"[a-z0-9]+", base)
    if not words:
        return []
    out = ["".join(words), "-".join(words), words[0]]
    return [s for i, s in enumerate(out) if len(s) >= 3 and s not in out[:i]]


def is_english(text: str) -> bool:
    """English when English function words clearly outnumber Danish ones."""
    words = re.findall(r"[a-zæøå]+", (text or "").lower())
    en, da = sum(w in EN_WORDS for w in words), sum(w in DA_WORDS for w in words)
    return en >= 3 and en > 2 * da


def strip_tags(s: str) -> str:
    return norm(re.sub(r"<[^>]+>", " ", html.unescape(s or "")))


def in_denmark(*places: str) -> bool:
    return any(p and DK_PLACE.search(ascii_fold(p) + " " + p) for p in places)


def annual_dkk(lo, hi, currency: str | None, interval: str | None) -> tuple[int | None, int | None]:
    """Yearly DKK from a posted range; other currencies or unknown intervals give no figure."""
    if not lo or (currency or "").upper() != "DKK":
        return None, None
    iv = (interval or "").lower()
    factor = 12 if "month" in iv else 1 if "year" in iv or "annual" in iv else 52 * 37 if "hour" in iv else None
    if not factor:
        return None, None
    return round(lo * factor), round((hi or lo) * factor)


def pay_check(lo: int | None, hi: int | None) -> str | None:
    """'clears' the Fast-Track pay limit, 'maybe' (range straddles it), 'below', or None when no DKK salary is posted."""
    if not lo:
        return None
    if lo >= PAY_LIMIT:
        return "clears"
    return "maybe" if (hi or lo) >= PAY_LIMIT else "below"


def dk_place(place: str | None) -> str:
    """The Danish part of a multi-city location like 'Amsterdam, NL; København, Denmark; Paris'."""
    parts = re.split(r"\s*[;|]\s*", norm(place))
    return next((p for p in parts if in_denmark(p)), parts[0])


def job(title, url, place, text, published=None, lo=None, hi=None, currency=None, interval=None) -> dict:
    ylo, yhi = annual_dkk(lo, hi, currency, interval)
    return {"title": norm(title), "url": url, "place": dk_place(place), "english": is_english(norm(title) + " " + strip_tags(text)),
            "published": (published or "")[:10] or None, "salary_min": ylo, "salary_max": yhi}


# One reader per job board. Each returns the board's postings in Denmark ([] when it has none) or None when the slug
# has no board.
def greenhouse(c: httpx.Client, s: str):
    r = c.get(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs", params={"content": "true"})
    if r.status_code != 200:
        return None
    return [job(j["title"], j["absolute_url"], (j.get("location") or {}).get("name"), j.get("content"), j.get("updated_at"))
            for j in r.json().get("jobs", []) if in_denmark((j.get("location") or {}).get("name"))]  # offices list every office the team has


def lever(c: httpx.Client, s: str):
    for host in ("api.lever.co", "api.eu.lever.co"):
        r = c.get(f"https://{host}/v0/postings/{s}", params={"mode": "json"})
        if r.status_code == 200 and isinstance(r.json(), list) and r.json():
            out = []
            for j in r.json():
                cat, sal = j.get("categories") or {}, j.get("salaryRange") or {}
                if not in_denmark(cat.get("location"), *(cat.get("allLocations") or []), j.get("country")):
                    continue
                pub = date.fromtimestamp(j["createdAt"] / 1000).isoformat() if j.get("createdAt") else None
                out.append(job(j["text"], j["hostedUrl"], cat.get("location"), j.get("descriptionPlain"), pub,
                               sal.get("min"), sal.get("max"), sal.get("currency"), sal.get("interval")))
            return out
    return None


def ashby(c: httpx.Client, s: str):
    r = c.get(f"https://api.ashbyhq.com/posting-api/job-board/{s}", params={"includeCompensation": "true"})
    if r.status_code != 200:
        return None
    out = []
    for j in r.json().get("jobs", []):
        places = [j.get("location")] + [x.get("location") for x in j.get("secondaryLocations") or []]
        addr = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry")
        if not in_denmark(*places, addr):
            continue
        lo = hi = cur = iv = None
        for comp in (j.get("compensation") or {}).get("summaryComponents") or []:
            if comp.get("compensationType") == "Salary":
                lo, hi, cur, iv = comp.get("minValue"), comp.get("maxValue"), comp.get("currencyCode"), comp.get("interval")
        dk = next((p for p in places if in_denmark(p)), places[0])
        out.append(job(j["title"], j["jobUrl"], dk, j.get("descriptionPlain"), j.get("publishedAt"), lo, hi, cur, iv))
    return out


def smartrecruiters(c: httpx.Client, s: str):
    r = c.get(f"https://api.smartrecruiters.com/v1/companies/{s}/postings", params={"country": "dk", "limit": 100})
    if r.status_code != 200 or not r.json().get("totalFound"):
        return None  # the API answers 200 for every slug, so an empty Danish list is no proof of a board
    out = []
    for j in r.json().get("content", []):
        out.append(job(j["name"], f"https://jobs.smartrecruiters.com/{s}/{j['id']}", (j.get("location") or {}).get("city"),
                       j["name"], j.get("releasedDate")))
        out[-1]["english"] = (j.get("language") or {}).get("code", "").startswith("en")  # the list has no ad text, only its language
    return out


def teamtailor(c: httpx.Client, s: str):
    r = c.get(f"https://{s}.teamtailor.com/jobs.rss")
    if r.status_code != 200 or "<rss" not in r.text[:300]:
        return None
    out = []
    for item in re.findall(r"(?s)<item>(.*?)</item>", r.text):
        tag = lambda t: html.unescape((re.search(rf"(?s)<{t}>(.*?)</{t}>", item) or [None, ""])[1])  # noqa: E731
        places = [html.unescape(p) for p in re.findall(r"<tt:(?:city|country|name)>(.*?)</tt:", item)]
        if in_denmark(*places):
            pub = tag("pubDate")
            try:
                from email.utils import parsedate_to_datetime
                pub = parsedate_to_datetime(pub).date().isoformat()
            except (TypeError, ValueError):
                pub = None
            out.append(job(tag("title"), tag("link"), next((p for p in places if in_denmark(p)), ""), tag("description"), pub))
    return out


def workable(c: httpx.Client, s: str):
    r = c.get(f"https://apply.workable.com/api/v1/widget/accounts/{s}", params={"details": "true"})
    if r.status_code != 200:
        return None
    return [job(j["title"], j.get("shortlink") or j.get("url"), ", ".join(filter(None, [j.get("city"), j.get("country")])),
                j.get("description"), j.get("published_on"))
            for j in r.json().get("jobs", []) if in_denmark(j.get("city"), j.get("country"))]


def recruitee(c: httpx.Client, s: str):
    r = c.get(f"https://{s}.recruitee.com/api/offers/")
    if r.status_code != 200:
        return None
    out = []
    for j in r.json().get("offers", []):
        if not in_denmark(j.get("city"), j.get("country"), j.get("location")):
            continue
        sal = j.get("salary") or {}
        out.append(job(j["title"], j["careers_url"], j.get("location") or j.get("city"), j.get("description"), j.get("published_at"),
                       sal.get("min"), sal.get("max"), sal.get("currency"), sal.get("period")))
    return out


BOARDS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "smartrecruiters": smartrecruiters,
          "teamtailor": teamtailor, "workable": workable, "recruitee": recruitee}
BOARD_NAME = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "smartrecruiters": "SmartRecruiters",
              "teamtailor": "Teamtailor", "workable": "Workable", "recruitee": "Recruitee"}


def read(c: httpx.Client, board: str, slug: str):
    try:
        return BOARDS[board](c, slug)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return None


def fresh(jobs: list[dict] | None, today: date) -> list[dict]:
    cutoff = (today - timedelta(days=MAX_AGE_DAYS)).isoformat()
    return [j for j in jobs or [] if not j["published"] or j["published"] >= cutoff]


def discover(c: httpx.Client, company: dict, today: date) -> dict | None:
    """First board whose slug matches the name and lists current jobs in Denmark."""
    for slug in slugs(company["name"]):
        for board in BOARDS:
            if (board, slug) not in NOT_THEIRS and fresh(read(c, board, slug), today):
                return {"board": board, "slug": slug}
    return None


def main() -> int:
    today = date.today()
    known = json.loads(ATS_FILE.read_text()) if ATS_FILE.exists() else {}
    with httpx.Client(headers=UA, timeout=25, follow_redirects=True) as c:
        r = c.get(SIRI)
        companies = parse_siri(r.text) if r.status_code == 200 else []
        if len(companies) < 500:  # the page moved or failed: keep the last list instead of dropping employers
            print(f"SIRI list gave {len(companies)} companies, keeping the saved list", file=sys.stderr)
            companies = [{"name": v["name"], "cvr": k} for k, v in known.items()]
        stale = (today - timedelta(days=RECHECK_DAYS)).isoformat()
        todo = [co for co in companies if co["cvr"] not in known or (not known[co["cvr"]].get("board") and known[co["cvr"]]["checked"] < stale)]
        with ThreadPoolExecutor(12) as pool:
            for co, hit in zip(todo, pool.map(lambda co: discover(c, co, today), todo)):
                known[co["cvr"]] = {"name": co["name"], "checked": today.isoformat(), **(hit or {})}
        current = {co["cvr"] for co in companies}
        mapped = [(cvr, v) for cvr, v in known.items() if cvr in current and v.get("board") and (v["board"], v["slug"]) not in NOT_THEIRS]
        jobs = []
        with ThreadPoolExecutor(12) as pool:
            for (cvr, v), found in zip(mapped, pool.map(lambda m: read(c, m[1]["board"], m[1]["slug"]), mapped)):
                for j in fresh(found, today):
                    if j["english"] and (j["url"] or "").startswith("https://"):  # feed links go straight into href
                        jobs.append({**j, "employer": v["name"], "cvr": cvr, "board": v["board"],
                                     "pay": pay_check(j["salary_min"], j["salary_max"])})
    ATS_FILE.write_text(json.dumps(dict(sorted(known.items())), ensure_ascii=False, indent=1))
    if len(jobs) < MIN_JOBS:
        print(f"only {len(jobs)} jobs, page not rebuilt", file=sys.stderr)
        return 1
    jobs = sorted({j["url"]: j for j in jobs}.values(), key=lambda j: j["published"] or "", reverse=True)
    DATA.write_text(json.dumps({"updated": today.isoformat(), "companies": len(companies), "mapped": len(mapped), "jobs": jobs},
                               ensure_ascii=False, indent=1))
    (PAGE_DIR / "index.html").write_text(render(jobs, len(companies), len(mapped), today.isoformat()))
    print(f"{len(companies)} certified companies, {len(mapped)} with a job board, {len(jobs)} English jobs in Denmark")
    return 0


PAY_LABEL = {"clears": "Salary clears the DKK 552,000 pay limit", "maybe": "Salary range reaches the DKK 552,000 pay limit",
             "below": "Salary below the DKK 552,000 pay limit"}


def fmt_dkk(n: int) -> str:
    return f"DKK {n:,}"


def card(j: dict) -> str:
    e = html.escape
    salary = ""
    if j["salary_min"]:
        salary = fmt_dkk(j["salary_min"]) + (f" to {fmt_dkk(j['salary_max'])}" if j["salary_max"] != j["salary_min"] else "") + " a year"
    pay = f'<p class="tags"><span class="tag tag-{j["pay"]}">{PAY_LABEL[j["pay"]]}</span></p>' if j["pay"] else ""
    when = f'<span class="dot">·</span><time datetime="{e(j["published"])}">{e(j["published"])}</time>' if j["published"] else ""
    return (
        f'<li class="job" data-pay="{j["pay"] or ""}" data-employer="{e(j["employer"].lower())}" data-text="{e((j["title"] + " " + j["employer"] + " " + j["place"]).lower())}">'
        f'<h3>{e(j["title"])}</h3>'
        f'<p class="where">{e(j["employer"])}<span class="dot">·</span>{e(j["place"] or "Denmark")}{when}</p>'
        f'<p class="sum">{e(salary) + ". " if salary else ""}Fast-Track certified employer (CVR {e(j["cvr"])}).</p>{pay}'
        f'<a class="orig" href="{e(j["url"])}" target="_blank" rel="noopener">Apply on the employer\'s {BOARD_NAME[j["board"]]} page</a></li>'
    )


def render(jobs: list[dict], companies: int, mapped: int, today: str) -> str:
    employers = sorted({j["employer"] for j in jobs}, key=str.lower)
    out = TEMPLATE.read_text()
    out = out.replace("<!--JOBS-->", "\n".join(card(j) for j in jobs))
    out = out.replace("<!--EMPLOYERS-->", "".join(f'<option value="{html.escape(x.lower())}">{html.escape(x)}</option>' for x in employers))
    return (out.replace("__N_ALL__", str(len(jobs))).replace("__N_EMPLOYERS__", str(len(employers)))
            .replace("__N_COMPANIES__", str(companies)).replace("__N_MAPPED__", str(mapped))
            .replace("__N_PAY__", str(sum(j["pay"] == "clears" for j in jobs)))
            .replace("__PAY_LIMIT__", fmt_dkk(PAY_LIMIT)).replace("__PAY_SUPP__", fmt_dkk(PAY_LIMIT_SUPPLEMENTARY))
            .replace("__UPDATED__", today))


if __name__ == "__main__":
    sys.exit(main())
