#!/usr/bin/env python3
"""Click depth from the homepage for every sitemap URL, walking the static HTML in this checkout.

Only links present in the initial HTML count (no JavaScript), which is what a first crawl sees.
Usage: python scripts/check_reachability.py [--max-depth 2] [--json out.json]
Exit code 1 when a sitemap URL is deeper than --max-depth or unreachable.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://benthepythondev00.github.io/"
HREF = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*["']([^"']+)["']""", re.I)
STRIP = re.compile(r"<script\b.*?</script>|<!--.*?-->", re.S | re.I)


def local_file(url: str) -> Path | None:
    p = urlparse(url).path
    f = ROOT / p.lstrip("/")
    if p.endswith("/") or p == "":
        f = f / "index.html"
    return f if f.is_file() else None


def norm(url: str) -> str:
    u = urldefrag(url)[0].split("?")[0]
    if u.endswith("/index.html"):
        u = u[: -len("index.html")]
    return u


def links(url: str) -> list[str]:
    f = local_file(url)
    if not f or f.suffix != ".html":
        return []
    html = STRIP.sub("", f.read_text(errors="ignore"))
    out = []
    for h in HREF.findall(html):
        if h.startswith(("mailto:", "tel:", "javascript:")):
            continue
        u = norm(urljoin(url, h))
        if u.startswith(BASE):
            out.append(u)
    return out


def depths() -> dict[str, int]:
    seen = {BASE: 0}
    q = deque([BASE])
    while q:
        u = q.popleft()
        for v in links(u):
            if v not in seen:
                seen[v] = seen[u] + 1
                q.append(v)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--json")
    a = ap.parse_args()
    sm = re.findall(r"<loc>([^<]+)</loc>", (ROOT / "sitemap.xml").read_text())
    d = depths()
    home = set(links(BASE))
    rows = [(u, d.get(norm(u))) for u in sm]
    bad = [(u, x) for u, x in rows if x is None or x > a.max_depth]
    by = {}
    for u, x in rows:
        sect = "/" + (urlparse(u).path.strip("/").split("/")[0] or "")
        by.setdefault(sect, []).append(x)
    print(f"sitemap URLs: {len(sm)}  linked from homepage: {sum(1 for u in sm if norm(u) in home)}")
    print(f"depth 0-1: {sum(1 for _, x in rows if x is not None and x <= 1)}  depth 2: {sum(1 for _, x in rows if x == 2)}"
          f"  deeper: {sum(1 for _, x in rows if x is not None and x > 2)}  unreachable: {sum(1 for _, x in rows if x is None)}")
    for s, xs in sorted(by.items()):
        if len(xs) > 1 or None in xs or max(x or 0 for x in xs) > 1:
            print(f"  {s:42} n={len(xs):3} max_depth={'none' if None in xs else max(xs)}")
    for u, x in bad:
        print(f"  TOO DEEP/UNREACHABLE: {u} depth={x}")
    if a.json:
        Path(a.json).write_text(json.dumps({u: x for u, x in rows}, indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
