"""Build the Reddit Archive Scraper free-sample pages (/data/reddit-archive-scraper/ and one page per subreddit the
sample rows hold) from data/reddit-archive-sample-2026-11-21.json, a real cloud run of the actor.

Every number on the pages comes from that file or from the actor's public pricing (PRICES below, read from
https://api.apify.com/v2/acts/benthepythondev~reddit-archive-scraper on 2026-11-24). Pages start noindex and stay out
of sitemap.xml until the Income Engine's pSEO gate approves their batch (INDEX = False).

    python scripts/build_reddit_archive_pages.py          # write the pages
    python scripts/build_reddit_archive_pages.py --dry-run # print what would be written
"""
from __future__ import annotations

import collections
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "reddit-archive-sample-2026-11-21.json"
BASE = "https://benthepythondev00.github.io"
HUB = "/data/reddit-archive-scraper/"
ACTOR = "https://apify.com/benthepythondev/reddit-archive-scraper"
INDEX = True  # pSEO batch 1 approved and live (job_5827a2e92783404b)
CHECKED = "2026-11-24"
# Free-tier and discounted prices per event in USD, from the actor's pricingInfos (checked CHECKED).
PRICES = {"FREE": 0.003, "BRONZE": 0.0027, "SILVER": 0.00255, "GOLD": 0.0024, "PLATINUM": 0.00225, "DIAMOND": 0.0021}
THREAD = 0.005
START = 0.00005

CSS = """
    :root { --bg:#0b1220; --card:#121a2b; --ink:#e8eefc; --muted:#9db0d0; --accent:#6ea8ff; --line:#243149; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background:var(--bg); color:var(--ink); }
    .wrap { max-width:760px; margin:0 auto; padding:28px 18px 72px; }
    a { color:var(--accent); }
    h1 { font-size:1.7rem; margin:0 0 10px; line-height:1.25; }
    h2 { font-size:1.15rem; margin:28px 0 10px; }
    h3 { font-size:1rem; margin:18px 0 6px; }
    p, li { line-height:1.6; }
    .sub, .note { color:var(--muted); }
    .note { font-size:.9rem; }
    pre { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; overflow:auto; font-size:.85rem; }
    code { font-size:.9em; }
    .btn { display:inline-block; padding:10px 14px; border-radius:10px; text-decoration:none; font-weight:600; background:var(--accent); color:#061018; margin:8px 8px 0 0; }
    .btn-ghost { background:transparent; border:1px solid var(--line); color:var(--ink); }
    ol, ul { padding-left:1.2rem; }
    .scroll { overflow-x:auto; border:1px solid var(--line); border-radius:12px; }
    table { border-collapse:collapse; width:100%; font-size:.86rem; }
    table.wide { min-width:720px; }
    td { overflow-wrap:anywhere; }
    th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
    th { color:var(--muted); font-weight:600; background:var(--card); }
    tr:last-child td { border-bottom:0; }
    td.n { text-align:right; font-variant-numeric:tabular-nums; }
    .faq dt { font-weight:600; margin-top:14px; }
    .faq dd { margin:4px 0 0; color:var(--ink); line-height:1.6; }
"""


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def usd(x: float) -> str:
    return f"${x:.5f}".rstrip("0").rstrip(".")


def page(path: str, title: str, desc: str, body: str, faq: list[tuple[str, str]], crumbs: list[tuple[str, str]],
         dataset: dict) -> str:
    url = BASE + path
    ld = [
        {"@context": "https://schema.org", "@type": "Dataset", "url": url, **dataset,
         "creator": {"@type": "Person", "name": "benthepythondev", "url": "https://apify.com/benthepythondev"},
         "isAccessibleForFree": True, "dateModified": CHECKED},
        {"@context": "https://schema.org", "@type": "FAQPage",
         "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
        {"@context": "https://schema.org", "@type": "BreadcrumbList",
         "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": BASE + p} for i, (n, p) in enumerate(crumbs)]},
    ]
    faq_html = "\n".join(f"      <dt>{esc(q)}</dt>\n      <dd>{esc(a)}</dd>" for q, a in faq)
    nav = " · ".join(f'<a href="{p}">{esc(n)}</a>' for n, p in crumbs[:-1]) + f" · {esc(crumbs[-1][0])}"
    robots = "index,follow" if INDEX else "noindex,follow"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}" />
  <link rel="canonical" href="{url}" />
  <meta name="robots" content="{robots}" />
  <meta name="author" content="benthepythondev" />
  <meta property="og:type" content="article" />
  <meta property="og:url" content="{url}" />
  <meta property="og:title" content="{esc(title)}" />
  <meta property="og:description" content="{esc(desc)}" />
  <meta name="twitter:card" content="summary" />
  <style>{CSS}  </style>
  <script type="application/ld+json">
{json.dumps(ld, indent=2, ensure_ascii=False)}
  </script>
</head>
<body>
  <article class="wrap">
    <p class="note">{nav}</p>
{body}
    <h2>Questions</h2>
    <dl class="faq">
{faq_html}
    </dl>
    <p class="note">Affiliate if you still need an Apify account: <a href="https://apify.com/?fpr=qolupv">apify.com/?fpr=qolupv</a>. I may earn a commission; the price you pay does not change.</p>
  </article>
</body>
</html>
"""


def when(r) -> datetime:
    return datetime.fromtimestamp(r["created_utc"], tz=timezone.utc)


def hub(s: dict) -> tuple[str, str]:
    rows, run = s["items"], s
    fields = list(rows[0].keys())
    ex = next(r for r in rows if r["link_flair_text"] and r["selftext"] == "[removed]")
    subs = collections.Counter(r["subreddit"] for r in rows)
    first, last = min(map(when, rows)), max(map(when, rows))
    title = "Reddit archive data sample: 22 fields per post, free JSON excerpt"
    desc = (f"A free sample of the Reddit Archive Scraper: {len(rows)} real post rows from a {run['verifiedOn']} run, "
            f"all {len(fields)} field names with example values, and the per-row price.")
    field_rows = "\n".join(
        f"        <tr><td><code>{esc(k)}</code></td><td>{esc(type(v).__name__ if v is not None else 'null')}</td><td>{esc(json.dumps(v, ensure_ascii=False))}</td></tr>"
        for k, v in ex.items())
    tiers = "\n".join(f'        <tr><td>{k.title()}</td><td class="n">{usd(v)}</td><td class="n">{usd(v * 1000)}</td></tr>'
                      for k, v in PRICES.items())
    sub_links = "\n".join(
        f'      <li><a href="{HUB}{k.lower()}/">r/{esc(k)}</a>: {n} posts from {first:%Y-%m-%d}, with the full table and per-post numbers</li>'
        for k, n in subs.items())
    c100 = 100 * PRICES["FREE"] + START
    c1000 = 1000 * PRICES["FREE"] + START
    c50t = 50 * PRICES["FREE"] + 50 * THREAD + START
    body = f"""    <h1>Reddit archive data: free sample, fields and price</h1>
    <p class="note">Sample run {esc(run['runId'])} · build {esc(run['build'])} · {esc(run['verifiedOn'])} · page checked {CHECKED}</p>
    <p>The <a href="{ACTOR}">Reddit Archive Scraper</a> on Apify returns historical Reddit posts and comments from public archives, filtered by subreddit, user or post ID and an exact UTC date range. This page shows what one real run returned, so you can check the shape of the data before you pay for a larger pull. The sample below is {len(rows)} post rows from a single cloud run with the input <code>{esc(json.dumps(run['input']))}</code>, which finished in {run['seconds']} seconds and wrote {run['bytes']:,} bytes of JSON.</p>
    <p><a class="btn" href="{ACTOR}">Run it on Apify</a><a class="btn btn-ghost" href="/{SAMPLE.relative_to(ROOT).as_posix()}">Download the sample JSON</a></p>

    <h2>What a buyer gets</h2>
    <p>Each post row carries {len(fields)} fields. The <code>type</code> field says <code>post</code> or <code>comment</code>, so posts and their archived comments can share one dataset and still be split later. Time comes twice: <code>created_utc</code> as a Unix timestamp and <code>created_iso</code> as an ISO 8601 string in UTC. Engagement comes as the archived <code>score</code>, <code>upvote_ratio</code> and <code>num_comments</code>, which are the values the archive captured, not the post's live numbers today. You can download the dataset as JSON, CSV, Excel or JSONL from Apify, or read it through the Apify API.</p>

    <h2>One real row</h2>
    <p>This is the post published at {when(ex):%H:%M} UTC on {when(ex):%Y-%m-%d} in r/{esc(ex['subreddit'])}, exactly as the run saved it:</p>
    <pre><code>{esc(json.dumps(ex, indent=2, ensure_ascii=False))}</code></pre>

    <h2>Field dictionary</h2>
    <p>Every field of the row above, its JSON type and the value it held. Nulls are kept, so a missing flair shows up as <code>null</code> rather than a dropped column.</p>
    <div class="scroll"><table>
      <thead><tr><th>Field</th><th>Type</th><th>Value in this row</th></tr></thead>
      <tbody>
{field_rows}
      </tbody>
    </table></div>

    <h2>Sample pages by subreddit</h2>
    <p>The sample run covered {len(subs)} subreddit{'s' if len(subs) != 1 else ''} between {first:%H:%M} and {last:%H:%M} UTC. Its page lists all {len(rows)} rows with their scores, comment counts and flairs:</p>
    <ul>
{sub_links}
    </ul>

    <h2>Price per row</h2>
    <p>The actor charges per event. These are the prices per saved post or comment on each Apify plan, checked on {CHECKED}. A run also has a start event of {usd(START)} on the Free plan, and with <code>includeComments</code> on, each post that returns at least one comment adds a thread charge of {usd(THREAD)}.</p>
    <div class="scroll"><table>
      <thead><tr><th>Apify plan</th><th>Per row</th><th>Per 1,000 rows</th></tr></thead>
      <tbody>
{tiers}
      </tbody>
    </table></div>
    <p>Worked out on the Free plan: 100 posts cost {usd(c100)}, 1,000 posts cost {usd(c1000)}, and 50 posts with comments (each post with at least one comment, before the comment rows themselves) cost {usd(c50t)}. The sample run of {len(rows)} rows was charged for {run['charged']['apify-default-dataset-item']} results, {run['charged']['apify-actor-start']} start and {run['charged']['comment-thread']} comment threads.</p>

    <h2>Related guides</h2>
    <ul>
      <li><a href="/how-to-get-historical-reddit-posts-and-comments.html">How to get historical Reddit posts and comments by subreddit and date range</a></li>
      <li><a href="/reddit-historical-data-by-date-range.html">Reddit history by date range: options and a curl example</a></li>
      <li><a href="/reddit-rag-dump.html">Reddit RAG dump</a></li>
      <li><a href="/">All actors in the catalog</a></li>
    </ul>"""
    faq = [
        ("What fields does the Reddit Archive Scraper return for a post?",
         f"{len(fields)} fields per post row: " + ", ".join(fields) + "."),
        ("How much does the Reddit archive data cost per row?",
         f"{usd(PRICES['FREE'])} per saved post or comment on the Apify Free plan, down to {usd(PRICES['DIAMOND'])} on Diamond, "
         f"plus a {usd(START)} start event and {usd(THREAD)} per post whose archived comments are fetched (prices checked {CHECKED})."),
        ("How fast was the sample run?",
         f"Run {run['runId']} returned {len(rows)} rows in {run['seconds']} seconds and {run['bytes']:,} bytes of JSON on {run['verifiedOn']}."),
        ("Are the scores live Reddit values?",
         "No. score, upvote_ratio and num_comments are what the public archive captured. In the sample, scores range from "
         f"{min(r['score'] for r in rows)} to {max(r['score'] for r in rows)}, because the posts were archived within hours of being published."),
    ]
    ds = {"name": title, "description": desc, "variableMeasured": fields,
          "distribution": {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{BASE}/{SAMPLE.relative_to(ROOT).as_posix()}"}}
    return page(HUB, title, desc, body, faq, [("Catalog", "/"), ("Reddit Archive Scraper data", HUB)], ds), title


def sub_page(s: dict, sub: str) -> tuple[str, str, str]:
    rows = sorted((r for r in s["items"] if r["subreddit"] == sub), key=lambda r: r["created_utc"])
    path = f"{HUB}{sub.lower()}/"
    n = len(rows)
    first, last = when(rows[0]), when(rows[-1])
    span = last - first
    hours, mins = divmod(int(span.total_seconds()) // 60, 60)
    scores = collections.Counter(r["score"] for r in rows)
    comments = sum(r["num_comments"] for r in rows)
    zero_c = sum(1 for r in rows if r["num_comments"] == 0)
    removed = sum(1 for r in rows if r["selftext"] == "[removed]")
    kept = [r for r in rows if r["selftext"] not in ("", "[removed]")]
    flairs = collections.Counter(r["link_flair_text"] or "no flair" for r in rows)
    domains = collections.Counter(r["domain"] for r in rows)
    ratio = collections.Counter(r["upvote_ratio"] for r in rows)
    top = max(rows, key=lambda r: (r["score"], r["num_comments"]))
    most_c = max(rows, key=lambda r: r["num_comments"])
    by_part = collections.Counter("00:00-11:59" if when(r).hour < 12 else "12:00-23:59" for r in rows)
    title = f"r/{sub} archived posts sample: {n} rows from {first:%Y-%m-%d} (JSON)"
    desc = (f"{n} archived r/{sub} posts from {first:%Y-%m-%d}, {first:%H:%M} to {last:%H:%M} UTC: scores, comment counts, "
            f"flairs and removal status, from a real Reddit Archive Scraper run.")
    table = "\n".join(
        f'        <tr><td>{when(r):%H:%M:%S}</td><td>{esc(r["title"])}</td><td>{esc(r["author"])}</td>'
        f'<td class="n">{r["score"]}</td><td class="n">{r["upvote_ratio"]}</td><td class="n">{r["num_comments"]}</td>'
        f'<td>{esc(r["link_flair_text"] or "")}</td><td>{esc(r["domain"])}</td><td><a href="{esc(r["permalink"])}" rel="nofollow">{esc(r["id"])}</a></td></tr>'
        for r in rows)
    score_li = "\n".join(f"      <li>score {k}: {v} post{'s' if v != 1 else ''}</li>" for k, v in sorted(scores.items()))
    flair_li = "\n".join(f"      <li>{esc(k)}: {v}</li>" for k, v in flairs.most_common())
    kept_p = "".join(
        f"<p>The only post whose body survived is &ldquo;{esc(k['title'])}&rdquo; by {esc(k['author'])} at {when(k):%H:%M} UTC: "
        f"{len(k['selftext']):,} characters of text, score {k['score']}, flair {esc(k['link_flair_text'] or 'none')}. "
        f"Its body opens: &ldquo;{esc(k['selftext'][:160].strip())}&hellip;&rdquo;</p>" for k in kept[:1])
    body = f"""    <h1>r/{esc(sub)} archive sample: {n} posts from {first:%d %b %Y}</h1>
    <p class="note">Rows from run {esc(s['runId'])} · input sortOrder {esc(s['input'].get('sortOrder'))}, maxPosts {esc(s['input'].get('maxPosts'))} · page checked {CHECKED}</p>
    <p>These are the {n} newest r/{esc(sub)} posts the <a href="{ACTOR}">Reddit Archive Scraper</a> returned on {s['verifiedOn']}. They were published on {first:%Y-%m-%d} between {first:%H:%M} and {last:%H:%M} UTC, a window of {hours} hours {mins} minutes, and the run saved every one of them as a post row with the same {len(rows[0])} fields. Use this page to judge what an r/{esc(sub)} pull looks like before you set a larger date range.</p>
    <p><a class="btn" href="{ACTOR}">Pull more r/{esc(sub)} history</a><a class="btn btn-ghost" href="{HUB}">All fields and prices</a></p>

    <h2>All {n} rows</h2>
    <div class="scroll"><table class="wide">
      <thead><tr><th>UTC time</th><th>Title</th><th>Author</th><th>Score</th><th>Ratio</th><th>Comments</th><th>Flair</th><th>Domain</th><th>Post id</th></tr></thead>
      <tbody>
{table}
      </tbody>
    </table></div>

    <h2>What the numbers show</h2>
    <p>Scores are low because the archive captured these posts within hours of publication. Across the {n} rows the scores add up to {sum(scores.elements())}, and the highest is {top['score']} for &ldquo;{esc(top['title'])}&rdquo;. The distribution:</p>
    <ul>
{score_li}
    </ul>
    <p>Comments: {comments} in total, and {zero_c} of {n} posts had none when archived. The most discussed was &ldquo;{esc(most_c['title'])}&rdquo; with {most_c['num_comments']}. Upvote ratio is {ratio.get(1, 0)} posts at 1 and {ratio.get(0, 0)} at 0, which on posts this young mostly reflects one or two votes.</p>
    <p>Timing: {by_part['00:00-11:59']} posts arrived between 00:00 and 11:59 UTC and {by_part['12:00-23:59']} between 12:00 and 23:59 UTC.</p>

    <h3>Flairs</h3>
    <ul>
{flair_li}
    </ul>

    <h3>Removed bodies and link posts</h3>
    <p>{removed} of {n} posts have the body <code>[removed]</code>: the archive kept the title, author, score and timestamps, but the text was removed. Plan for this if you need post bodies from r/{esc(sub)}: titles are complete for all {n} rows. {sum(1 for r in rows if r['is_self'])} rows are text posts (<code>is_self</code> true) and {sum(1 for r in rows if not r['is_self'])} links to {esc(', '.join(d for d in domains if not d.startswith('self.')))}.</p>
    {kept_p}

    <h2>Pull it yourself</h2>
    <p>The input that produced these rows:</p>
    <pre><code>{esc(json.dumps(s['input'], indent=2))}</code></pre>
    <p>Add <code>afterDate</code> and <code>beforeDate</code> for an exact UTC window, switch <code>sortOrder</code> to oldest-first for a backfill, and turn on <code>includeComments</code> to get each post's archived comments as rows of their own. More on the options in the <a href="/how-to-get-historical-reddit-posts-and-comments.html">historical Reddit guide</a> and the <a href="/reddit-historical-data-by-date-range.html">date-range reference</a>.</p>"""
    faq = [
        (f"How many r/{sub} posts are in this sample?",
         f"{n} posts, published on {first:%Y-%m-%d} between {first:%H:%M} and {last:%H:%M} UTC, from run {s['runId']}."),
        (f"How many r/{sub} posts in the sample have a removed body?",
         f"{removed} of {n}. Their titles, authors, scores and timestamps are still in the rows; only the selftext reads [removed]."),
        (f"What were the scores and comment counts of the archived r/{sub} posts?",
         f"Scores ranged from {min(scores)} to {max(scores)} and added up to {sum(scores.elements())}; the posts had {comments} comments in total, "
         f"and {zero_c} had none when archived."),
        (f"Which flairs appear in the r/{sub} sample?",
         "; ".join(f"{k}: {v}" for k, v in flairs.most_common()) + "."),
    ]
    ds = {"name": title, "description": desc, "temporalCoverage": f"{first:%Y-%m-%dT%H:%M:%SZ}/{last:%Y-%m-%dT%H:%M:%SZ}",
          "variableMeasured": list(rows[0].keys())}
    return path, page(path, title, desc, body, faq,
                      [("Catalog", "/"), ("Reddit Archive Scraper data", HUB), (f"r/{sub}", path)], ds), title


def build(dry: bool = False) -> list[str]:
    s = json.loads(SAMPLE.read_text())
    out = {HUB: hub(s)[0]}
    for sub in sorted({r["subreddit"] for r in s["items"]}):
        p, h, _ = sub_page(s, sub)
        out[p] = h
    for p, h in out.items():
        f = ROOT / p.strip("/") / "index.html"
        print(("would write " if dry else "wrote ") + f"{f.relative_to(ROOT)} ({len(h):,} bytes)")
        if not dry:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(h)
    return list(out)


if __name__ == "__main__":
    print(",".join(build("--dry-run" in sys.argv)))
