"""Build jobs-in-germany/index.html: fresh BA listings with English titles and who-can-apply checks.

Only facts, our own English summary and a short quoted sentence are published; the full ad text stays on
arbeitsagentur.de (its terms reserve the ad texts), every card links the original.
"""

from __future__ import annotations

import base64
import html
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parent.parent
PAGE_DIR = ROOT / "jobs-in-germany"
TEMPLATE = PAGE_DIR / "template.html"
DATA = ROOT / "data" / "germany-jobs.json"
CACHE = ROOT / "data" / "germany-jobs-translations.json"

API = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEADERS = {"X-API-Key": "jobboerse-jobsuche", "Accept": "application/json", "User-Agent": "benthepythondev-jobs-in-germany/1.0"}
SITE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/"
MT = "https://api.mymemory.translated.net/get"
MT_EMAIL = "benthepythondev0@gmail.com"  # raises the free MyMemory quota from 5k to 50k chars a day

# Search terms as German employers write them; the last four match ads aimed at applicants from abroad.
QUERIES = ["Pflegefachkraft", "Altenpfleger", "Elektroniker", "Anlagenmechaniker", "Mechatroniker", "Ingenieur",
           "Softwareentwickler", "Erzieher", "Berufskraftfahrer", "Visum", "ausländische Fachkräfte", "Anpassungslehrgang",
           "Anerkennung Ausland"]
FIELDS = [("Nursing", r"pflege|kranken|hebamme"), ("IT", r"informati|software|entwickler|it-|daten|devops"),
          ("Engineering", r"ingenieur|techniker"), ("Childcare", r"erzieh|pädagog|kinder"),
          ("Logistics", r"kraftfahr|fahrer|lager|logisti"), ("Medicine", r"arzt|ärzt|mediziner"),
          ("Skilled trades", r"elektr|mechani|monteur|anlagen|install|schweiß|schlosser|tischler|maurer|dachdecker|maler|zimmer|kfz|handwerk")]
PER_QUERY = 25
DAYS = 14

# Restrictive statuses win when one ad says several things.
RULES = [
    ("permit", re.compile(r"(arbeitserlaubnis|arbeitsgenehmigung|aufenthaltstitel|aufenthaltserlaubnis|work permit|gültige[sm]? visum)"), re.compile(r"(erforderlich|voraussetzung|vorausgesetzt|benötigt|zwingend|muss|müssen|vorhanden|gültige|required)")),
    ("eu", re.compile(r"(eu-bürger|eu-staatsangehörig|staatsangehörigkeit eines eu|aus der eu\b|aus eu-|eu citizens|eu-pass)"), None),
    ("abroad", re.compile(r"((bewerb\w*|ausbildung|abschlu\w*|qualifikation\w*|fachkr\w*|pflegekr\w*|kandidat\w*) aus dem ausland|aus dem ausland .{0,40}(willkommen|bewerb|anerkannt)"
                          r"|ausländische[nrm]? (berufs)?(abschl|qualifikation|ausbildung|fachkr|pflegefachkr|pflegekr|bewerber|kolleg)"
                          r"|internationale[nr]? (bewerber|fachkr|pflegefachkr|pflegekr|kandidat)|gleichwertigkeitsbescheid|anerkennungsverfahren"
                          r"|berufsanerkennung|anerkennungspraktikum|anpassungslehrgang|anpassungsqualifizierung|kenntnisprüfung"
                          r"|anerkennung (ihres|deines|eures) (ausländischen )?(berufs)?abschl|(?<!ptv-)(?<!ptv )visum|visa\b|relocation|drittstaat|nicht-eu"
                          r"|applicants from abroad|international applicants)"), None),
]
SUPPORT = re.compile(r"(unterstütz|helfen|begleite|kümmern|übernehmen|support)")
# EU Blue Card gross salary per year, 2026 (https://digital.diplo.de/Blaue-Karte, § 18g AufenthG). The reduced
# threshold applies to shortage occupations (IT, engineering, science, medicine, health); update both each January.
BLUE_CARD = 50_700
BLUE_CARD_SHORTAGE = 45_934.20
SHORTAGE_FIELDS = {"IT", "Engineering", "Medicine", "Nursing"}
ORDER = {"permit": 0, "eu": 1, "abroad": 2}
GERMAN = re.compile(r"deutsch")
LEVEL = re.compile(r"\b([abc]) ?([12])\b")
FLUENT = re.compile(r"(fließend|verhandlungssicher|sehr gute|muttersprach|exzellente|perfekte)")
GOOD = re.compile(r"(gute|solide|sichere)")
BASIC = re.compile(r"(grundkenntnisse|basiskenntnisse|erste|einfache)")


def sentences(text: str) -> list[str]:
    text = re.sub(r"\*\*|__|#+ ", "", html.unescape(text or "")).replace("\xa0", " ")
    parts = re.split(r"(?<=[.!?])\s+|\n+|\s\|\s", text)
    return [re.sub(r"\s+", " ", p).strip(" -•*·|") for p in parts if len(p.strip()) > 8]


def short(s: str, n: int = 220) -> str:
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def who_can_apply(text: str) -> dict:
    """Status from the employer's own sentence: abroad, eu, permit or unknown."""
    found = []
    for s in sentences(text):
        low = s.lower()
        for status, term, need in RULES:
            if not term.search(low):
                continue
            if status == "permit":
                if SUPPORT.search(low):  # "we help with your work permit" invites applicants from abroad
                    status = "abroad"
                elif not need.search(low):
                    continue
            found.append((ORDER[status], status, s))
            break
    if not found:
        return {"status": "unknown", "sentence": None}
    _, status, s = min(found, key=lambda f: f[0])
    return {"status": status, "sentence": short(s)}


def german_level(text: str) -> dict:
    for s in sentences(text):
        low = s.lower()
        if not GERMAN.search(low) or "deutschland" in low and "deutschkennt" not in low and "sprach" not in low:
            continue
        m = LEVEL.search(low)
        if m:
            return {"level": (m.group(1) + m.group(2)).upper(), "sentence": short(s)}
        for name, rx in (("Fluent", FLUENT), ("Good", GOOD), ("Basic", BASIC)):
            if "kenntnis" in low and rx.search(low):
                return {"level": name, "sentence": short(s)}
    return {"level": None, "sentence": None}


def annual_salary(job: dict) -> tuple[float | None, float | None]:
    """Yearly euros from the structured salary fields; hourly pay counts 40 h x 52 weeks."""
    lo, hi = job.get("gehaltsspanneVon") or job.get("festgehalt"), job.get("gehaltsspanneBis") or job.get("festgehalt")
    kind = job.get("verguetungsangabe")
    factor = {"JAHRESGEHALT": 1, "MONATSGEHALT": 12, "STUNDENLOHN": 40 * 52}.get(kind)
    if not factor or not lo:
        return None, None
    return round(lo * factor), round((hi or lo) * factor)


class Translator:
    def __init__(self, client: httpx.Client, cache: dict):
        self.client, self.cache, self.failed, self.used = client, cache, False, set()

    def __call__(self, text: str | None) -> str | None:
        if not text:
            return None
        self.used.add(text)
        if text in self.cache:
            return self.cache[text]
        if self.failed:  # quota or outage: keep the German, retry tomorrow
            return None
        try:
            r = self.client.get(MT, params={"q": text[:480], "langpair": "de|en", "de": MT_EMAIL}, timeout=20)
            body = r.json()
            out = (body.get("responseData") or {}).get("translatedText")
            if body.get("responseStatus") != 200 or not out or "MYMEMORY WARNING" in out.upper():
                self.failed = True
                return None
        except (httpx.HTTPError, ValueError):
            self.failed = True
            return None
        out = html.unescape(out)
        self.cache[text] = out
        time.sleep(0.3)
        return out


def get(client: httpx.Client, url: str, params=None):
    for attempt in range(3):
        try:
            r = client.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.json()
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(1 + attempt)
    return None


def city(job: dict) -> str | None:
    locs = job.get("stellenlokationen") or []
    addr = (locs[0] or {}).get("adresse", {}) if locs else {}
    return (addr.get("ort") or "").split(",")[0] or None


def strip_gender(title: str) -> str:
    return re.sub(r"\s*\((?:[mwdfix]\s*[/|,]\s*)+[mwdfix]\)|\s*[mwd]/[mwd]/[mwd]", "", title, flags=re.I).strip()


def field_of(occupation: str | None) -> str:
    low = (occupation or "").lower()
    return next((name for name, rx in FIELDS if re.search(rx, low)), "Other")


def build_job(job: dict, detail: dict | None, tr: Translator) -> dict:
    text = (detail or {}).get("stellenangebotsBeschreibung") or ""
    ref = job["referenznummer"]
    title_de = strip_gender(job.get("stellenangebotsTitel") or job.get("hauptberuf") or "")
    who, lang = who_can_apply(text), german_level(text)
    lo, hi = annual_salary(job)
    return {
        "ref": ref,
        "url": SITE + quote(ref, safe=""),
        "title_de": title_de,
        "title_en": tr(title_de),
        "occupation_de": job.get("hauptberuf"),
        "occupation_en": tr(job.get("hauptberuf")),
        "field": field_of(job.get("hauptberuf") or job.get("stellenangebotsTitel")),
        "employer": job.get("firma"),
        "city": city(job),
        "region": ((job.get("stellenlokationen") or [{}])[0].get("adresse") or {}).get("region"),
        "published": job.get("datumErsteVeroeffentlichung") or (job.get("veroeffentlichungszeitraum") or {}).get("von"),
        "full_time": bool(job.get("arbeitszeitVollzeit")),
        "part_time": any(job.get(k) for k in ("arbeitszeitTeilzeitFlexibel", "arbeitszeitTeilzeitVormittag", "arbeitszeitTeilzeitNachmittag", "arbeitszeitTeilzeitAbend")),
        "permanent": job.get("vertragsdauer") == "UNBEFRISTET",
        "home_office": bool(job.get("homeofficemoeglich")),
        "salary_min": lo,
        "salary_max": hi,
        "salary_hourly": job.get("verguetungsangabe") == "STUNDENLOHN",
        "who": who["status"],
        "who_de": who["sentence"],
        "who_en": tr(who["sentence"]),
        "german": lang["level"],
        "german_de": lang["sentence"],
    }


def blue_card(j: dict) -> str | None:
    """'yes', 'shortage' (clears only the reduced threshold), 'below', or None when no full-time yearly salary is stated."""
    if not j["salary_min"] or (j["salary_hourly"] and not j["full_time"]):
        return None
    if j["salary_min"] >= BLUE_CARD:
        return "yes"
    if j["salary_min"] >= BLUE_CARD_SHORTAGE and j["field"] in SHORTAGE_FIELDS:
        return "shortage"
    return "below"


def opportunity_card(j: dict) -> bool:
    """Part-time hours fit the Opportunity Card's 20 hours a week, and the ad doesn't exclude non-EU applicants."""
    return j["part_time"] and j["who"] in ("abroad", "unknown")


def summary(j: dict) -> str:
    """One plain English line built from the structured fields, so it never misquotes the ad."""
    bits = [("Full-time" if j["full_time"] else "Part-time") + (", permanent" if j["permanent"] else "")]
    if j["salary_min"] and j["salary_hourly"] and not j["full_time"]:  # a yearly figure at 40 h would overstate part-time pay
        lo, hi = j["salary_min"] / 2080, j["salary_max"] / 2080
        bits.append(f"€{lo:.2f}" + (f" to €{hi:.2f}" if hi != lo else "") + " an hour")
    elif j["salary_min"]:
        pay = f"€{j['salary_min']:,}" + (f" to €{j['salary_max']:,}" if j["salary_max"] != j["salary_min"] else "")
        bits.append(pay + " a year" + (" (from the hourly rate, 40 h a week)" if j["salary_hourly"] else ""))
    else:
        bits.append("salary not stated")
    if j["home_office"]:
        bits.append("some home office")
    bits.append({"A1": "basic German (A1)", "A2": "basic German (A2)", "B1": "German B1", "B2": "German B2", "C1": "German C1", "C2": "German C2",
                 "Fluent": "fluent German", "Good": "good German", "Basic": "basic German"}.get(j["german"], "German level not stated"))
    return ". ".join(b[0].upper() + b[1:] for b in bits) + "."


WHO_LABEL = {
    "abroad": ("Applicants from abroad welcome", "abroad"),
    "eu": ("EU/EEA residents only", "eu"),
    "permit": ("Asks for an existing work permit", "permit"),
    "unknown": ("Ad doesn't say who can apply", "unknown"),
}


def card(j: dict) -> str:
    e = html.escape
    title = j["title_en"] or j["title_de"]
    label, cls = WHO_LABEL[j["who"]]
    quote_html = ""
    if j["who_de"]:
        en = f'<span class="q-en">{e(j["who_en"])}</span>' if j["who_en"] else ""
        quote_html = f'<blockquote lang="de">“{e(j["who_de"])}”</blockquote>{en}'
    sub = f'<p class="de" lang="de">{e(j["title_de"])}</p>' if j["title_en"] and j["title_en"] != j["title_de"] else ""
    where = ", ".join(x for x in [j["employer"], j["city"]] if x)
    bc, oc = blue_card(j), opportunity_card(j)
    tags = "".join([
        {"yes": f'<span class="tag tag-bc">Salary clears the Blue Card threshold (€{BLUE_CARD:,})</span>',
         "shortage": f'<span class="tag tag-bc">Clears the reduced Blue Card threshold (€{BLUE_CARD_SHORTAGE:,.0f})</span>',
         "below": '<span class="tag tag-low">Salary below the Blue Card threshold</span>'}.get(bc, ""),
        '<span class="tag tag-oc">Opportunity Card friendly: part-time hours</span>' if oc else "",
    ])
    tags = f'<p class="tags">{tags}</p>' if tags else ""
    return (
        f'<li class="job" data-who="{cls}" data-field="{e(j["field"])}" data-bc="{bc or ""}" data-oc="{int(oc)}" data-text="{e((title + " " + j["title_de"] + " " + where).lower())}">'
        f'<div class="job-head"><h3>{e(title)}</h3><span class="who who-{cls}">{label}</span></div>{sub}'
        f'<p class="where">{e(where)}<span class="dot">·</span><time datetime="{e(j["published"] or "")}">{e(j["published"] or "")}</time></p>'
        f'<p class="sum">{e(summary(j))}</p>{tags}{quote_html}'
        f'<a class="orig" href="{e(j["url"])}" target="_blank" rel="noopener">Original listing on arbeitsagentur.de</a></li>'
    )


def render(jobs: list[dict], today: str) -> str:
    counts = {k: sum(j["who"] == k for j in jobs) for k in WHO_LABEL}
    fields = sorted({j["field"] for j in jobs})
    out = TEMPLATE.read_text()
    out = out.replace("<!--JOBS-->", "\n".join(card(j) for j in jobs))
    out = out.replace("<!--FIELDS-->", "".join(f'<option value="{html.escape(f)}">{html.escape(f)}</option>' for f in fields))
    for k, v in counts.items():
        out = out.replace(f"__N_{k.upper()}__", str(v))
    out = out.replace("__N_BC__", str(sum(blue_card(j) in ("yes", "shortage") for j in jobs)))
    out = out.replace("__N_OC__", str(sum(opportunity_card(j) for j in jobs)))
    out = out.replace("__BC__", f"€{BLUE_CARD:,}").replace("__BC_SHORT__", f"€{BLUE_CARD_SHORTAGE:,.2f}")
    return out.replace("__N_ALL__", str(len(jobs))).replace("__UPDATED__", today)


def main() -> int:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    jobs, seen = [], set()
    with httpx.Client() as client:
        tr = Translator(client, cache)
        for q in QUERIES:
            res = get(client, f"{API}/pc/v6/jobs", {"was": q, "size": PER_QUERY, "page": 1, "angebotsart": 1, "veroeffentlichtseit": DAYS}) or {}
            for job in res.get("ergebnisliste") or []:
                ref = job.get("referenznummer")
                land = (((job.get("stellenlokationen") or [{}])[0] or {}).get("adresse") or {}).get("land")
                if not ref or ref in seen or land not in (None, "DEUTSCHLAND"):  # the board also carries jobs abroad
                    continue
                seen.add(ref)
                enc = base64.b64encode(ref.encode()).decode()
                detail = get(client, f"{API}/pc/v4/jobdetails/{quote(enc, safe='')}")
                jobs.append(build_job(job, detail, tr))
    if len(jobs) < 20:  # the API failed: keep yesterday's page instead of publishing an empty one
        print(f"only {len(jobs)} jobs, page not rebuilt", file=sys.stderr)
        return 1
    rank = {"abroad": 0, "unknown": 1, "eu": 2, "permit": 3}
    jobs.sort(key=lambda j: j["published"] or "", reverse=True)
    jobs.sort(key=lambda j: rank[j["who"]])
    today = date.today().isoformat()
    DATA.write_text(json.dumps({"updated": today, "jobs": jobs}, ensure_ascii=False, indent=1))
    CACHE.write_text(json.dumps({k: cache[k] for k in tr.used if k in cache}, ensure_ascii=False, indent=0, sort_keys=True))
    (PAGE_DIR / "index.html").write_text(render(jobs, today))
    print(f"{len(jobs)} jobs, {sum(j['who'] == 'abroad' for j in jobs)} welcome applicants from abroad, translator failed: {tr.failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
