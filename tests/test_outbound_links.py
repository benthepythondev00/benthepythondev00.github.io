"""Off-site links carry data-qa-skip so the QA crawler does not open hundreds of third-party
popups. This test checks each skipped control is what it claims to be: an https link to
another site that opens in a new tab with rel=noopener. Nothing on our own site is skipped."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["jobs-in-germany/index.html", "jobs-in-denmark/index.html", "jobs-in-germany/template.html",
         "jobs-in-denmark/template.html", "custom-apify-actor.html", "how-to-get-reddit-posts-and-comments-data.html"]
OWN = ("https://benthepythondev00.github.io",)


class Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skipped, self.blank_unskipped, self.mail_unskipped, self.same_tab_external = [], [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        href = a.get("href") or ""
        if "data-qa-skip" in a:
            self.skipped.append((tag, a))
        elif tag == "a" and a.get("target") == "_blank":
            self.blank_unskipped.append(a)
        elif tag == "a" and href.startswith("mailto:"):
            self.mail_unskipped.append(href)
        elif tag == "a" and href.startswith("http") and not href.startswith(OWN):
            self.same_tab_external.append(href)


class TestOutboundLinks(unittest.TestCase):
    def test_skipped_controls_are_external_new_tab_links(self):
        total = 0
        for rel in PAGES:
            p = Collect()
            p.feed((ROOT / rel).read_text())
            for tag, a in p.skipped:
                total += 1
                with self.subTest(page=rel, href=a.get("href")):
                    self.assertEqual(tag, "a")
                    href = a.get("href") or ""
                    if href.startswith("mailto:"):
                        continue  # mail links stall the crawler's next click (no animation frames after reopen)
                    self.assertTrue(href.startswith("https://") or href.startswith("__"), href)
                    self.assertFalse(href.startswith(OWN), href)
                    self.assertEqual(a.get("target"), "_blank")
                    self.assertIn("noopener", a.get("rel") or "")
            with self.subTest(page=rel):
                self.assertEqual(p.blank_unskipped, [], "new-tab link without data-qa-skip")
                self.assertEqual(p.mail_unskipped, [], "mailto link without data-qa-skip")
                self.assertEqual(p.same_tab_external, [], "off-site link that does not open a new tab")
        self.assertGreater(total, 400)

    def test_builders_emit_the_skip_marker(self):
        for rel in ("scripts/build_germany_jobs.py", "scripts/build_denmark_jobs.py"):
            src = (ROOT / rel).read_text()
            self.assertRegex(src, r'class="orig" href="\{e\(j\["url"\]\)\}" target="_blank" rel="noopener" data-qa-skip')


class TestDynamicStoreLinks(unittest.TestCase):
    def test_js_store_links_are_skipped(self):
        src = (ROOT / "custom-apify-actor.html").read_text()
        self.assertIn('link.target = "_blank"; link.rel = "noopener"; link.setAttribute("data-qa-skip", "")', src)
